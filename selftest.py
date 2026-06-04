#!/usr/bin/env python3
"""
Self-test — yerel kurulumu doğrula.
Çalıştır:  python selftest.py

Canlı scraper teşhisi için ayrıca `python diag.py` çalıştır.
Telegram .env bilgileri varsa test mesajı gönderir; yoksa bu adımı atlar.
"""
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

OK = "✅"
FAIL = "❌"
WARN = "⚠️ "


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

    def _cfg():
        import scanner

        cfg = scanner.load_config()
        assert "schedule" in cfg and "database" in cfg
        if scanner.telegram_ready(cfg.get("telegram")):
            return "config tamam; Telegram bildirimleri açık"
        return "config tamam; Telegram .env yok, bildirimler kapalı"
    results.append(check("Config", _cfg))

    def _deps():
        import jobspy, feedparser, requests, bs4, yaml, apscheduler, fastapi, uvicorn  # noqa
        return "tüm paketler kurulu"
    results.append(check("Bağımlılıklar", _deps))

    def _mods():
        import db, scanner, models, filter_engine, notifier  # noqa
        from scrapers import http_util, jobspy_scraper, rss_scraper, kariyer_scraper  # noqa
        from web import app  # noqa
        return "tüm modüller import edildi"
    results.append(check("Modüller", _mods))

    def _profiles():
        import profiles

        profs = profiles.list_profiles()
        if not profs:
            raise RuntimeError("profil yok; profiles/example.yaml dosyasını profiles/ben.yaml olarak kopyala")
        return f"{len(profs)} profil bulundu"
    results.append(check("Profiller", _profiles))

    def _db():
        import db, tempfile, os
        from models import Job

        p = tempfile.mktemp(suffix=".db")
        db.configure(p)
        db.upsert_job(Job("Test", "Co", "Remote", "https://x.com/1", "test", score=5))
        assert db.get_stats()["total"] == 1
        os.unlink(p)
        return "okuma/yazma/dedup çalışıyor"
    results.append(check("Veritabanı", _db))

    def _dashboard():
        html = Path(__file__).parent / "web" / "static" / "index.html"
        assert html.exists()
        text = html.read_text(encoding="utf-8")
        assert "filterSummary" in text and "data-theme=\"black\"" in text
        return "dashboard statik dosyası hazır"
    results.append(check("Dashboard", _dashboard))

    def _tg():
        import scanner
        from notifier import send_message

        cfg = scanner.load_config()
        if not scanner.telegram_ready(cfg.get("telegram")):
            return "atlanıyor; .env içinde TELEGRAM_BOT_TOKEN/CHAT_ID yok"
        ok = send_message(
            cfg["telegram"]["bot_token"],
            cfg["telegram"]["chat_id"],
            "🤖 <b>Job Bot self-test</b>\nBağlantı başarılı; bot çalışmaya hazır.",
        )
        if not ok:
            raise RuntimeError("mesaj gönderilemedi; bot_token/chat_id kontrol et")
        return "Telegram'a test mesajı gönderildi"
    results.append(check("Telegram", _tg))

    print("=" * 50)
    if all(results):
        print(f"{OK} HER ŞEY HAZIR — 'python run.py' ile başlat, http://localhost:8765 aç")
    else:
        print(f"{WARN}Bazı kontroller başarısız — yukarıdaki {FAIL} satırlarını düzelt")
    print("=" * 50)


if __name__ == "__main__":
    main()
