"""
Çekirdek tarama mantığı — çok profilli.
run_scan(profile_key=None) verilen kişiyi, verilmezse TÜM profilleri tarar.
Hem zamanlayıcı hem web 'Scan Now' butonu çağırır.
"""
import logging
import os
import re
import yaml
import threading
from datetime import datetime, timedelta
from pathlib import Path

import db
from models import Job
from filter_engine import (
    score_job,
    should_exclude,
    location_allowed,
    is_remote_job,
    relevance_score,
    matched_keywords,
    tr_norm,
    work_mode_allowed,
)
from notifier import notify_jobs, notify_summary
from profiles import list_profiles, get_profile, profile_scoring
from scrapers.jobspy_scraper import scrape_jobspy
from scrapers.rss_scraper import scrape_rss_feeds
from scrapers.kariyer_scraper import scrape_kariyer

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.yaml"
_scan_lock = threading.Lock()


def _source_blocked_in_cooldown(source: str, cooldown_hours: float) -> tuple[bool, str]:
    """Return whether a blocked source should be skipped until the cooldown expires."""
    if cooldown_hours <= 0:
        return False, ""
    for item in db.get_source_health():
        if item.get("source") != source or item.get("status") != "blocked":
            continue
        checked_at = item.get("checked_at")
        if not checked_at:
            return False, ""
        try:
            checked = datetime.strptime(checked_at, "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            return False, ""
        retry_at = checked + timedelta(hours=cooldown_hours)
        if datetime.now() < retry_at:
            return True, retry_at.strftime("%H:%M")
    return False, ""


def _load_dotenv() -> dict:
    """Proje kökündeki .env dosyasini (varsa) oku. KEY=VALUE formati."""
    env = {}
    p = Path(__file__).parent / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # Telegram secret'lari ortam degiskeni / .env'den al (${VAR} kaliplari)
    env = {**_load_dotenv(), **os.environ}  # gercek ortam .env'i ezer
    tg = cfg.get("telegram", {}) or {}
    for k in ("bot_token", "chat_id"):
        val = str(tg.get(k, ""))
        m = re.fullmatch(r"\$\{(\w+)\}", val.strip())
        if m:
            tg[k] = env.get(m.group(1), "")
    cfg["telegram"] = tg
    return cfg


def telegram_ready(tg: dict | None) -> bool:
    """Telegram bildirimi için bot token ve chat id gerçekten ayarlı mı?"""
    tg = tg or {}
    token = str(tg.get("bot_token", "") or "").strip()
    chat_id = str(tg.get("chat_id", "") or "").strip()
    return bool(token and chat_id and not token.startswith("${") and not chat_id.startswith("${"))


def _scan_one_profile(
    prof: dict, cfg: dict, blocked_sources: set[str] | None = None
) -> dict:
    """Tek bir kişi (profil) için tarama."""
    key = prof.get("key", "")
    name = prof.get("name", key)
    search = prof.get("search", {}) or {}

    base_scoring = cfg.get("scoring", {}) or {}
    base_exclude = (cfg.get("filters", {}) or {}).get("exclude_keywords", []) or []
    tg = cfg["telegram"]
    min_score = cfg["schedule"]["min_score_to_notify"]

    # puanlama = ortak + kişinin becerileri
    scoring = dict(base_scoring)
    for kw, w in profile_scoring(prof).items():
        scoring[kw] = max(scoring.get(kw, 0), w)
    # Konum önceliği: profilin ilk tercih şehri en yüksek puanla üstte görünür.
    LOC_W = [6, 3, 2]
    for i, city in enumerate(prof.get("preferred_locations", []) or []):
        ck = tr_norm(str(city))
        if ck:
            scoring[ck] = LOC_W[i] if i < len(LOC_W) else 2
    exclude_kw = list(base_exclude) + list(prof.get("exclude_keywords", []) or [])

    scan_id = db.start_scan(key)
    raw_jobs: list[Job] = []
    blocked_sources = blocked_sources if blocked_sources is not None else set()
    try:
        logger.info("=" * 50)
        logger.info(f"🔍 Tarama başladı — 👤 {name}")

        # RSS (varsa; varsayılan kapalı)
        feeds = search.get("rss_feeds") or cfg.get("rss_feeds")
        if feeds:
            try:
                raw_jobs.extend(scrape_rss_feeds(feeds))
            except Exception as e:
                logger.error(f"RSS hatası: {e}")

        # JobSpy (Indeed / Google / LinkedIn)
        if search.get("jobspy_queries"):
            try:
                jobspy_jobs = scrape_jobspy(
                    queries=search["jobspy_queries"],
                    hours_old=search.get("hours_old", 168),
                    results_wanted=search.get("results_wanted", 25),
                )
                raw_jobs.extend(jobspy_jobs)
                db.set_source_health("jobspy", "ok", f"{len(jobspy_jobs)} ilan cekildi")
            except Exception as e:
                logger.error(f"JobSpy hatası: {e}")
                db.set_source_health("jobspy", "error", str(e))

        # Kariyer.net
        if search.get("kariyer_queries"):
            source_cfg = cfg.get("sources", {}) or {}
            cooldown_hours = float(source_cfg.get("kariyer_block_cooldown_hours", 6))
            cooling_down, retry_at = _source_blocked_in_cooldown(
                "kariyer.net", cooldown_hours
            )
            if "kariyer.net" in blocked_sources:
                msg = "Bu taramada daha once 403 alindi; Kariyer sorgulari atlandi"
                logger.info(f"[Kariyer] {msg}.")
                db.set_source_health("kariyer.net", "blocked", msg, touch=False)
            elif cooling_down:
                msg = (
                    f"Kariyer.net 403 engeli suruyor; yaklasik {retry_at} sonrasina "
                    "kadar yeniden denenmeyecek"
                )
                logger.info(f"[Kariyer] {msg}.")
                db.set_source_health("kariyer.net", "blocked", msg, touch=False)
            else:
                try:
                    kariyer_result = scrape_kariyer(
                        search["kariyer_queries"], return_status=True
                    )
                    if isinstance(kariyer_result, tuple):
                        kariyer_jobs, health = kariyer_result
                    else:
                        kariyer_jobs = kariyer_result
                        health = {
                            "source": "kariyer.net",
                            "status": "ok",
                            "message": f"{len(kariyer_jobs)} ilan cekildi",
                        }
                    raw_jobs.extend(kariyer_jobs)
                    db.set_source_health(
                        health.get("source", "kariyer.net"),
                        health.get("status", "unknown"),
                        health.get("message", ""),
                    )
                    if health.get("status") == "blocked":
                        blocked_sources.add("kariyer.net")
                except Exception as e:
                    logger.error(f"Kariyer hatası: {e}")
                    db.set_source_health("kariyer.net", "error", str(e))

        logger.info(f"[{name}] Ham toplam: {len(raw_jobs)} ilan")

        cities = prof.get("preferred_locations", []) or []
        allowed_work_modes = prof.get("work_modes", []) or []
        min_store = float(cfg["schedule"].get("min_score_to_store", 1.0))
        min_rel = float(cfg["schedule"].get("min_relevance", 1.0))
        # Rol uygunluğu = beceriler + kişinin ARADIĞI pozisyon terimleri
        role_weights = dict(profile_scoring(prof))
        for q in (search.get("jobspy_queries") or []):
            t = str(q.get("term", "")).strip().lower()
            if t:
                role_weights.setdefault(t, 2.0)
        for q in (search.get("kariyer_queries") or []):
            t = str(q).strip().lower()
            if t:
                role_weights.setdefault(t, 2.0)

        # Eski/alakasiz 'new' kayitlari temizle (Istanbul vb. yerinde, dusuk skor)
        try:
            from models import Job as _J
            for jr in db.get_jobs(profile=key, status="new", min_score=0, limit=2000):
                _tmp = _J(jr.get("title",""), jr.get("company",""), jr.get("location",""),
                          jr.get("url",""), jr.get("source",""), description=jr.get("description","") or "")
                _tmp.job_type = jr.get("job_type")
                _tmp.is_remote = bool(jr.get("is_remote"))
                _tmp.score = score_job(_tmp, scoring)
                rel = relevance_score(_tmp, role_weights)
                if (
                    _tmp.score < min_store
                    or rel < min_rel
                    or not work_mode_allowed(_tmp, allowed_work_modes)
                    or not location_allowed(jr.get("location", ""), cities, jr.get("is_remote"))
                ):
                    db.delete_job(jr["url_hash"], key)
        except Exception as e:
            logger.warning(f"Temizlik hatasi: {e}")

        new_count = 0
        n_excluded = n_lowscore = n_lowrel = n_wrongmode = n_wrongloc = n_stored = 0
        for job in raw_jobs:
            if should_exclude(job, exclude_kw):
                n_excluded += 1
                continue
            job.score = score_job(job, scoring)        # gösterim/sıralama skoru
            if job.score < min_store:
                n_lowscore += 1
                continue
            if relevance_score(job, role_weights) < min_rel:  # rol uygunluğu
                n_lowrel += 1
                continue
            job.is_remote = is_remote_job(job)  # uzaktan/remote -> is_remote=1
            if not work_mode_allowed(job, allowed_work_modes):
                n_wrongmode += 1
                continue
            if not location_allowed(job.location, cities, job.is_remote):
                n_wrongloc += 1
                continue
            n_stored += 1
            if db.upsert_job(job, profile=key):
                new_count += 1
        logger.info(
            f"[{name}] filtre: ham={len(raw_jobs)} "
            f"elendi(kelime)={n_excluded} dusuk_skor(<{min_store})={n_lowscore} "
            f"dusuk_rol(<{min_rel})={n_lowrel} yanlis_calisma={n_wrongmode} "
            f"yanlis_konum={n_wrongloc} -> kabul={n_stored} (yeni={new_count})"
        )

        # eşik üstü + bildirilmemişleri Telegram'a gönder (kişi adıyla)
        to_notify = db.get_unnotified(min_score, profile=key)
        notified_count = 0
        if to_notify and telegram_ready(tg):
            for job in to_notify:
                job.match_terms = matched_keywords(job, role_weights)
                job.match_score = relevance_score(job, role_weights)
            notify_jobs(tg["bot_token"], tg["chat_id"], to_notify, label=name)
            db.mark_notified([j.url_hash for j in to_notify], profile=key)
            notified_count = len(to_notify)
        elif to_notify:
            logger.info(
                f"[{name}] Telegram bilgileri eksik; {len(to_notify)} bildirim beklemede kaldı."
            )

        db.finish_scan(scan_id, len(raw_jobs), new_count, notified_count, "done")
        logger.info(f"✅ [{name}] bitti — {new_count} yeni, {notified_count} bildirildi.\n")
        return {"profile": key, "name": name, "raw": len(raw_jobs),
                "new": new_count, "notified": notified_count}

    except Exception as e:
        logger.error(f"[{name}] Tarama hatası: {e}", exc_info=True)
        db.finish_scan(scan_id, len(raw_jobs), 0, 0, "error")
        return {"profile": key, "name": name, "error": str(e)}


def run_scan(cfg: dict | None = None, profile_key: str | None = None) -> dict:
    """
    profile_key verilirse o kişiyi, verilmezse TÜM profilleri tarar.
    Aynı anda iki tarama çalışmasını engeller (lock).
    """
    if not _scan_lock.acquire(blocking=False):
        logger.info("Tarama zaten çalışıyor, atlanıyor.")
        return {"skipped": True}

    try:
        cfg = cfg or load_config()

        if profile_key:
            prof = get_profile(profile_key)
            profiles = [prof] if prof else []
        else:
            profiles = list_profiles()

        if not profiles:
            logger.warning("Profil bulunamadı (profiles/ klasörü boş?).")
            return {"error": "profil yok"}

        blocked_sources: set[str] = set()
        results = [_scan_one_profile(p, cfg, blocked_sources) for p in profiles]

        # Tarama bitince Telegram'a özet rapor
        try:
            tg = cfg.get("telegram", {}) or {}
            if telegram_ready(tg):
                notify_summary(tg["bot_token"], tg["chat_id"], results)
            else:
                logger.info("Telegram bilgileri eksik; özet rapor atlandı.")
        except Exception as e:
            logger.warning(f"Özet rapor gönderilemedi: {e}")

        return {
            "profiles": results,
            "new": sum(r.get("new", 0) for r in results),
            "notified": sum(r.get("notified", 0) for r in results),
        }
    finally:
        _scan_lock.release()
