import requests
import time
import logging

logger = logging.getLogger(__name__)

BASE_URL = "https://api.telegram.org/bot{token}/{method}"


def send_message(bot_token: str, chat_id: str, text: str) -> bool:
    if not bot_token or not chat_id or bot_token.startswith("${"):
        logger.error("Telegram: bot_token/chat_id eksik (.env doldurulmamis).")
        return False
    if not text:
        return False
    if len(text) > 4096:           # Telegram mesaj limiti
        text = text[:4090] + "…"
    url = BASE_URL.format(token=bot_token, method="sendMessage")
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if not resp.ok:
            logger.error(f"Telegram API hatası: {resp.status_code} {resp.text[:200]}")
        return resp.ok
    except Exception as e:
        logger.error(f"Telegram gönderim hatası: {e}")
        return False


def notify_jobs(bot_token: str, chat_id: str, jobs: list, label: str = "") -> None:
    """İlanları Telegram'a gönder. Flood control için arada bekler.
    label: hangi kişi/CV için olduğunu başlıkta gösterir."""
    if not jobs:
        return

    # Özet başlık (kişi adıyla)
    who = f"👤 {label} — " if label else ""
    header = f"🤖 <b>İş Botu — {who}{len(jobs)} yeni ilan</b>\n{'─' * 30}"
    send_message(bot_token, chat_id, header)
    time.sleep(1)

    for i, job in enumerate(jobs):
        msg = job.to_telegram_message()
        ok = send_message(bot_token, chat_id, msg)
        if not ok:
            logger.warning(f"İlan gönderilemedi: {job.title}")
        # Telegram rate limit: 30 msg/sn — 0.5sn bekle
        time.sleep(0.6)

    footer = f"─ 🏁 Tarama tamamlandı."
    send_message(bot_token, chat_id, footer)


def notify_summary(bot_token: str, chat_id: str, results: list) -> None:
    """Tarama bitince Telegram'a özet rapor gönder.
    results: [{name, raw, new, notified, error?}, ...]"""
    import html
    from datetime import datetime
    if not results:
        return
    lines = ["📊 <b>Tarama Raporu</b>", "─" * 24]
    total_new = total_notif = 0
    for r in results:
        name = html.escape(str(r.get("name", r.get("profile", "?"))))
        if r.get("error"):
            lines.append(f"👤 <b>{name}</b>: ⚠️ hata")
            continue
        new = r.get("new", 0); notif = r.get("notified", 0); raw = r.get("raw", 0)
        total_new += new; total_notif += notif
        lines.append(f"👤 <b>{name}</b>\n   • {new} yeni · {notif} bildirim · {raw} tarandı")
    lines.append("─" * 24)
    lines.append(f"🆕 Toplam yeni: <b>{total_new}</b> · 🔔 bildirim: <b>{total_notif}</b>")
    lines.append(f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    send_message(bot_token, chat_id, "\n".join(lines))


def notify_error(bot_token: str, chat_id: str, error_msg: str) -> None:
    import html
    send_message(bot_token, chat_id, f"⚠️ <b>Job Bot Hata</b>\n<code>{html.escape(error_msg[:300])}</code>")
