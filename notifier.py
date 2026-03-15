"""
notifier.py — Telegram Bot API ile başarı ve hata bildirimleri gönderir.
"""

import os
import requests
import traceback
from datetime import datetime, timezone


def _send(text: str, parse_mode: str = "Markdown") -> bool:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("[notifier] Telegram env değişkenleri eksik, bildirim atlandı.")
        return False

    resp = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        },
        timeout=15,
    )

    if resp.ok:
        return True
    print(f"[notifier] Telegram hatası: {resp.status_code} — {resp.text[:200]}")
    return False


def send_notification(title: str, video_id: str, duration_sec: float, tags: list) -> bool:
    """Başarılı upload bildirimi."""
    url = f"https://youtube.com/shorts/{video_id}"
    tags_str = ", ".join(tags[:4])
    now = datetime.now(timezone.utc).strftime("%d %b %Y — %I:%M %p UTC")

    message = (
        f"✅ *Today's Short is LIVE!*\n\n"
        f"📹 *{title}*\n"
        f"🔗 {url}\n"
        f"⏱️  Duration: {int(duration_sec)} sec\n"
        f"🏷️  Tags: {tags_str}\n"
        f"📅  Uploaded: {now}"
    )

    ok = _send(message)
    if ok:
        print("[notifier] Telegram başarı bildirimi gönderildi.")
    return ok


def send_error_notification(step: str, error: Exception, topic: str = "") -> bool:
    """
    Pipeline'da bir adım başarısız olduğunda Telegram'a hata bildirimi gönderir.
    step: hangi adımda hata oluştu (örn. "script_gen", "tts", "video_builder")
    """
    now = datetime.now(timezone.utc).strftime("%d %b %Y — %I:%M %p UTC")
    tb = traceback.format_exc()
    # Uzun traceback'i kısalt
    tb_short = tb[-800:] if len(tb) > 800 else tb

    message = (
        f"❌ *WAR SHORTS — Pipeline Hatası*\n\n"
        f"📍 Adım: `{step}`\n"
        f"🎯 Konu: {topic or '—'}\n"
        f"💬 Hata: `{type(error).__name__}: {str(error)[:200]}`\n"
        f"📅 Zaman: {now}\n\n"
        f"```\n{tb_short}\n```"
    )

    ok = _send(message)
    if ok:
        print(f"[notifier] Telegram hata bildirimi gönderildi (adım: {step}).")
    return ok


if __name__ == "__main__":
    # Test: başarı bildirimi
    send_notification(
        title="What if Rome Never Fell?",
        video_id="test_video_id",
        duration_sec=55,
        tags=["history", "whatif", "war", "shorts"],
    )
