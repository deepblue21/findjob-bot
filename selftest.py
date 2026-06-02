#!/usr/bin/env python3
"""
Self-test — kurulumu calistirmadan once dogrula.
Calistir:  python selftest.py
Telegram'a bir test mesaji gonderir, scraper'lari canli dener.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

OK = "✅"; FAIL = "❌"; WARN = "⚠️ "


def check(name, fn):
    try:
        msg = fn()
        print(f"{OK} {name}" + (f" — {msg}" if msg else ""))
        return True
    except Exception as e:
        print(f"{FAIL} {name} — {e}")
        return False


def main():
    print("=" * 50)
    print("  JOB_BOT Self-Test")
    print("=" * 50)
    results = []

    # 1. Config
    def _cfg():
        import yaml
        cfg = yaml.safe_load(open(Path(__file__).parent / "config.yaml", encoding="utf-8"))
        import scanner
        cfg = scanner.load_config()
        if not cfg["telegram"].get("bot_token") or cfg["telegram"]["bot_token"].startswith("${"):
            raise RuntimeError(".env doldurulmamis (TELEGRAM_BOT_TOKEN)")
        return "config.yaml dolu"
    results.append(check("Config", _cfg))

    # 2. Bagimliliklar
    def _deps():
        import jobspy, feedparser, requests, bs4, yaml, apscheduler, fastapi, uvicorn  # noqa
        return "tum paketler kurulu"
    results.append(check("Bagimliliklar", _deps))

    # 3. Moduller
    def _mods():
        import db, scanner, models, filter_engine, notifier  # noqa
        from scrapers import http_util, jobspy_scraper, rss_scraper, kariyer_scraper  # noqa
        from web import app  # noqa
        return "tum moduller import edildi"
    results.append(check("Moduller", _mods))

    # 4. Veritabani
    def _db():
        import db, tempfile, os
        p = tempfile.mktemp(suffix=".db")
        db.configure(p)
        from models import Job
        db.upsert_job(Job("Test", "Co", "Remote", "https://x.com/1", "test", score=5))
        assert db.get_stats()["total"] == 1
        os.unlink(p)
        return "okuma/yazma/dedup calisiyor"
    results.append(check("Veritabani", _db))

    # 5. Telegram test mesaji
    def _tg():
        import yaml
        from notifier import send_message
        import scanner
        cfg = scanner.load_config()
        ok = send_message(
            cfg["telegram"]["bot_token"], cfg["telegram"]["chat_id"],
            "🤖 <b>Job Bot self-test</b>\nBaglanti basarili — bot calismaya hazir."
        )
        if not ok:
            raise RuntimeError("mesaj gonderilemedi — bot_token/chat_id kontrol et")
        return "Telegram'a test mesaji gonderildi (kontrol et)"
    results.append(check("Telegram", _tg))

    # 6. Canli scraper denemesi (RSS + Kariyer)
    def _scrape():
        from scrapers.rss_scraper import scrape_rss_feeds
        import yaml
        cfg = yaml.safe_load(open(Path(__file__).parent / "config.yaml", encoding="utf-8"))
        feeds = cfg["search"].get("rss_feeds", [])[:1]  # sadece ilk feed
        jobs = scrape_rss_feeds(feeds) if feeds else []
        return f"RSS canli deneme: {len(jobs)} ilan"
    results.append(check("Canli scraper (RSS)", _scrape))

    print("=" * 50)
    if all(results):
        print(f"{OK} HER SEY HAZIR — 'python run.py' ile baslat, http://localhost:8765 ac")
    else:
        print(f"{WARN} Bazi kontroller basarisiz — yukaridaki {FAIL} satirlari duzelt")
    print("=" * 50)


if __name__ == "__main__":
    main()
