#!/usr/bin/env python3
"""
Job Bot — Ana giris noktasi.
Web dashboard + arka plan zamanlayici TEK process'te calisir.

Calistir:  python run.py
Sonra ac:  http://localhost:8765
"""
import logging
import sys
import threading
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler

import db
import scanner
from web.app import app

# -- loglama --
LOG_DIR = Path.home() / ".job_bot"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("job_bot")

PORT = 8765


def main():
    cfg = scanner.load_config()

    if not scanner.telegram_ready(cfg.get("telegram")):
        logger.warning("Telegram .env bilgileri yok; dashboard calisacak, bildirimler atlanacak.")
        print("\n⚠️  Telegram .env bilgileri yok; dashboard calisacak, bildirimler atlanacak.")
        print("   Bildirim icin .env dosyasina TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID ekle.\n")

    # DB hazirla
    db.configure(cfg["database"]["path"])
    logger.info("✅ Veritabani hazir.")

    # Ilk taramayi arka planda baslat (web hemen acilsin)
    threading.Thread(target=scanner.run_scan, args=(cfg,), daemon=True).start()
    logger.info("🔍 Ilk tarama arka planda baslatildi.")

    # Zamanlayici
    interval = cfg["schedule"].get("interval_hours", 6)
    sched = BackgroundScheduler(timezone="Europe/Istanbul")
    sched.add_job(scanner.run_scan, "interval", hours=interval,
                  id="scan", name="Periyodik Tarama")
    sched.start()
    logger.info(f"⏰ Zamanlayici aktif — her {interval} saatte taranacak.")

    # Web sunucu
    logger.info("=" * 50)
    logger.info(f"🌐 Dashboard:  http://localhost:{PORT}")
    logger.info("=" * 50)
    print(f"\n  ╭─────────────────────────────────────────╮")
    print(f"  │  JOB_BOT calisiyor                        │")
    print(f"  │  Dashboard:  http://localhost:{PORT}      │")
    print(f"  │  Durdurmak icin: Ctrl+C                    │")
    print(f"  ╰─────────────────────────────────────────╯\n")

    try:
        uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot durduruldu.")
        sched.shutdown()


if __name__ == "__main__":
    main()
