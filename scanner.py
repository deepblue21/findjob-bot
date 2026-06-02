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
from pathlib import Path

import db
from models import Job
from filter_engine import score_job, should_exclude, location_allowed, is_remote_job
from notifier import notify_jobs, notify_summary
from profiles import list_profiles, get_profile, profile_scoring
from scrapers.jobspy_scraper import scrape_jobspy
from scrapers.rss_scraper import scrape_rss_feeds
from scrapers.kariyer_scraper import scrape_kariyer

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.yaml"
_scan_lock = threading.Lock()


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


def _scan_one_profile(prof: dict, cfg: dict) -> dict:
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
    exclude_kw = list(base_exclude) + list(prof.get("exclude_keywords", []) or [])

    scan_id = db.start_scan(key)
    raw_jobs: list[Job] = []
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
                raw_jobs.extend(scrape_jobspy(
                    queries=search["jobspy_queries"],
                    hours_old=search.get("hours_old", 168),
                    results_wanted=search.get("results_wanted", 25),
                ))
            except Exception as e:
                logger.error(f"JobSpy hatası: {e}")

        # Kariyer.net
        if search.get("kariyer_queries"):
            try:
                raw_jobs.extend(scrape_kariyer(search["kariyer_queries"]))
            except Exception as e:
                logger.error(f"Kariyer hatası: {e}")

        logger.info(f"[{name}] Ham toplam: {len(raw_jobs)} ilan")

        cities = prof.get("preferred_locations", []) or []
        min_store = float(cfg["schedule"].get("min_score_to_store", 3.0))

        # Eski/alakasiz 'new' kayitlari temizle (Istanbul vb. yerinde, dusuk skor)
        try:
            for jr in db.get_jobs(profile=key, status="new", min_score=0, limit=2000):
                if jr["score"] < min_store or not location_allowed(
                        jr.get("location", ""), cities, jr.get("is_remote")):
                    db.delete_job(jr["url_hash"], key)
        except Exception as e:
            logger.warning(f"Temizlik hatasi: {e}")

        new_count = 0
        for job in raw_jobs:
            if should_exclude(job, exclude_kw):
                continue
            job.score = score_job(job, scoring)
            if job.score < min_store:
                continue
            if not location_allowed(job.location, cities, job.is_remote):
                continue
            job.is_remote = is_remote_job(job)  # uzaktan/remote -> is_remote=1
            if db.upsert_job(job, profile=key):
                new_count += 1

        # eşik üstü + bildirilmemişleri Telegram'a gönder (kişi adıyla)
        to_notify = db.get_unnotified(min_score, profile=key)
        if to_notify:
            notify_jobs(tg["bot_token"], tg["chat_id"], to_notify, label=name)
            db.mark_notified([j.url_hash for j in to_notify], profile=key)

        db.finish_scan(scan_id, len(raw_jobs), new_count, len(to_notify), "done")
        logger.info(f"✅ [{name}] bitti — {new_count} yeni, {len(to_notify)} bildirildi.\n")
        return {"profile": key, "name": name, "raw": len(raw_jobs),
                "new": new_count, "notified": len(to_notify)}

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

        results = [_scan_one_profile(p, cfg) for p in profiles]

        # Tarama bitince Telegram'a özet rapor
        try:
            tg = cfg["telegram"]
            notify_summary(tg["bot_token"], tg["chat_id"], results)
        except Exception as e:
            logger.warning(f"Özet rapor gönderilemedi: {e}")

        return {
            "profiles": results,
            "new": sum(r.get("new", 0) for r in results),
            "notified": sum(r.get("notified", 0) for r in results),
        }
    finally:
        _scan_lock.release()
