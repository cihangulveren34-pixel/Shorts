"""
discord_notify.py — Discord Webhook ile kanal bildirimleri.

Gereksinim: DISCORD_WEBHOOK_URL (Discord sunucusu → Kanal Ayarları → Entegrasyonlar → Webhook)
Tamamen ücretsiz, API key gerekmez.
"""

import os
import json
import requests
from datetime import datetime, timezone

TIMEOUT = 15


def _post(payload: dict) -> bool:
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        print("[discord] DISCORD_WEBHOOK_URL yok, atlandı.")
        return False
    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
        if resp.status_code == 204:
            print("[discord] Bildirim gönderildi.")
            return True
        print(f"[discord] Hata: {resp.status_code} — {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"[discord] İstek hatası: {e}")
        return False


def send_video_live(title: str, video_id: str, duration_sec: float, tags: list, thumbnail_url: str = None) -> bool:
    """Yeni video yayınlandığında Discord'a embed mesaj gönderir."""
    now = datetime.now(timezone.utc).strftime("%d %b %Y — %H:%M UTC")
    yt_url = f"https://youtube.com/shorts/{video_id}"
    tags_str = " · ".join(f"#{t}" for t in tags[:4])

    embed = {
        "title": f"⚔️ {title}",
        "url": yt_url,
        "description": f"**{tags_str}**\n\n🔗 [{yt_url}]({yt_url})",
        "color": 0xC41E1E,   # koyu kırmızı
        "fields": [
            {"name": "⏱️ Süre",   "value": f"{int(duration_sec)} sn", "inline": True},
            {"name": "📅 Tarih",  "value": now,                         "inline": True},
        ],
        "footer": {"text": "WAR SHORTS Pipeline"},
    }
    if thumbnail_url:
        embed["thumbnail"] = {"url": thumbnail_url}

    return _post({
        "content": "✅ **Yeni Short YAYINDA!**",
        "embeds": [embed],
    })


def send_error(step: str, error: str, topic: str = "") -> bool:
    """Pipeline hatası bildirir."""
    embed = {
        "title": f"❌ Pipeline Hatası — {step}",
        "description": f"```{error[:500]}```",
        "color": 0xFF0000,
        "fields": [
            {"name": "🎯 Konu", "value": topic or "—", "inline": True},
            {"name": "📅 Zaman", "value": datetime.now(timezone.utc).strftime("%H:%M UTC"), "inline": True},
        ],
        "footer": {"text": "WAR SHORTS Pipeline"},
    }
    return _post({"content": "⚠️ **Pipeline Hatası**", "embeds": [embed]})


def send_weekly_report(stats: dict) -> bool:
    """Haftalık analytics raporunu Discord'a gönderir."""
    top = stats.get("top_videos", [])
    top_text = "\n".join(
        f"{i+1}. **{v['title'][:40]}** — {v['views']:,} görüntülenme"
        for i, v in enumerate(top[:3])
    ) or "—"

    embed = {
        "title": "📊 Haftalık Rapor",
        "description": f"📅 {stats.get('period', '—')}",
        "color": 0x2ECC71,
        "fields": [
            {"name": "👁️ Görüntülenme",     "value": f"{stats.get('views', 0):,}",          "inline": True},
            {"name": "⏱️ İzlenme (dk)",      "value": f"{stats.get('watch_minutes', 0):,}",  "inline": True},
            {"name": "👥 Net Abone",         "value": f"+{stats.get('net_subs', 0)}",         "inline": True},
            {"name": "🏆 En İyi Videolar",   "value": top_text, "inline": False},
        ],
        "footer": {"text": "WAR SHORTS Pipeline"},
    }
    return _post({"embeds": [embed]})


if __name__ == "__main__":
    send_video_live(
        title="What if Rome Never Fell?",
        video_id="test_id",
        duration_sec=52,
        tags=["history", "whatif", "war", "shorts"],
    )
