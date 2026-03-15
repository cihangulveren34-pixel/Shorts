"""
notifier.py — Telegram Bot API ile başarılı upload bildirimi gönderir.
"""

import os
import requests
from datetime import datetime, timezone


def send_notification(
    title: str,
    video_id: str,
    duration_sec: float,
    tags: list,
) -> bool:
    """
    Telegram'a video yükleme bildirimi gönderir. Başarılı ise True döndürür.
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("[notifier] TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID eksik, bildirim atlandı.")
        return False

    url = f"https://youtube.com/shorts/{video_id}"
    tags_str = ", ".join(tags[:4])
    now = datetime.now(timezone.utc).strftime("%d %b %Y — %I:%M %p UTC")
    duration_fmt = f"{int(duration_sec)} sec"

    message = (
        f"✅ *Today's Short is LIVE!*\n\n"
        f"📹 *{title}*\n"
        f"🔗 {url}\n"
        f"⏱️  Duration: {duration_fmt}\n"
        f"🏷️  Tags: {tags_str}\n"
        f"📅  Uploaded: {now}"
    )

    resp = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        },
        timeout=15,
    )

    if resp.ok:
        print(f"[notifier] Telegram bildirimi gönderildi.")
        return True
    else:
        print(f"[notifier] Telegram hatası: {resp.status_code} {resp.text}")
        return False


if __name__ == "__main__":
    # Test
    send_notification(
        title="What if Rome Never Fell?",
        video_id="test_video_id",
        duration_sec=52,
        tags=["history", "whatif", "war", "shorts"],
    )
