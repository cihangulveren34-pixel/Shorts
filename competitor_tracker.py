"""
competitor_tracker.py — Rakip kanal takibi ve viral konu tespiti.

Belirlenen rakip kanalların son videolarını tarar:
- En yüksek view/saat oranına sahip videoları tespit eder
- Başlık + tag kalıplarını çıkarır
- Önerilen konuları topic_pool.json'a ekler
- Haftalık raporu Telegram + Discord'a gönderir

Gereksinimler:
  COMPETITOR_CHANNEL_IDS: virgülle ayrılmış kanal ID'leri (env)
  YOUTUBE_TOKEN_JSON veya token.json: API erişimi için
"""

import json
import os
import re
import tempfile
from datetime import datetime, timezone, timedelta
from typing import Optional

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False


# Varsayılan rakip kanallar (tarih/savaş içeriği popüler kanallar)
DEFAULT_COMPETITOR_IDS = [
    # Popüler tarih Shorts kanalları — gerçek ID'lerle değiştirilebilir
    "UCivlDF4aBkB9OFBZKMoNgEg",  # History Explained
    "UC22BdTgxefuvUivrjesETjg",  # Alternate History Hub
]

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
]

TRACKER_STATE_PATH = "competitor_state.json"


def _get_credentials() -> "Credentials":
    token_json = os.environ.get("YOUTUBE_TOKEN_JSON")
    if token_json:
        data = json.loads(token_json)
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(data, tmp)
        tmp.close()
        creds = Credentials.from_authorized_user_file(tmp.name, SCOPES)
        os.unlink(tmp.name)
    elif os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    else:
        raise FileNotFoundError("YouTube token bulunamadı.")
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def _load_state() -> dict:
    if os.path.exists(TRACKER_STATE_PATH):
        with open(TRACKER_STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"last_checked": {}, "seen_video_ids": []}


def _save_state(state: dict) -> None:
    with open(TRACKER_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _get_channel_recent_videos(youtube, channel_id: str, max_results: int = 20) -> list[dict]:
    """Kanalın son N videosunu döndürür."""
    try:
        # Önce channel uploads playlist ID'sini al
        resp = youtube.channels().list(
            part="contentDetails,snippet",
            id=channel_id,
        ).execute()
        if not resp.get("items"):
            return []

        channel_name = resp["items"][0]["snippet"]["title"]
        uploads_id = resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

        # Playlist'ten videoları al
        pl_resp = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_id,
            maxResults=max_results,
        ).execute()

        videos = []
        for item in pl_resp.get("items", []):
            video_id = item["contentDetails"]["videoId"]
            title = item["snippet"]["title"]
            published = item["snippet"]["publishedAt"]
            videos.append({
                "video_id": video_id,
                "title": title,
                "published_at": published,
                "channel_id": channel_id,
                "channel_name": channel_name,
            })
        return videos
    except Exception as e:
        print(f"[tracker] Kanal {channel_id} videoları alınamadı: {e}")
        return []


def _get_video_stats(youtube, video_ids: list[str]) -> dict[str, dict]:
    """Video ID listesi için istatistikleri toplu olarak alır."""
    stats = {}
    # YouTube API max 50 ID per request
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        try:
            resp = youtube.videos().list(
                part="statistics,contentDetails",
                id=",".join(batch),
            ).execute()
            for item in resp.get("items", []):
                vid_id = item["id"]
                s = item.get("statistics", {})
                dur = item.get("contentDetails", {}).get("duration", "PT0S")
                stats[vid_id] = {
                    "views": int(s.get("viewCount", 0)),
                    "likes": int(s.get("likeCount", 0)),
                    "comments": int(s.get("commentCount", 0)),
                    "duration": dur,
                }
        except Exception as e:
            print(f"[tracker] İstatistik alınamadı: {e}")
    return stats


def _parse_iso_duration(duration: str) -> int:
    """ISO 8601 duration → saniye (örn: PT1M30S → 90)."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mi = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mi * 60 + s


def _calculate_virality_score(video: dict, stats: dict) -> float:
    """
    Viral skor = views / (yaş_saat + 1)
    Kısa videolar (<= 60sn) için ek çarpan.
    """
    vid_stats = stats.get(video["video_id"], {})
    views = vid_stats.get("views", 0)

    published = datetime.fromisoformat(
        video["published_at"].replace("Z", "+00:00")
    )
    age_hours = max(1, (datetime.now(timezone.utc) - published).total_seconds() / 3600)
    vph = views / age_hours  # views per hour

    # Short video bonus
    dur_secs = _parse_iso_duration(vid_stats.get("duration", "PT0S"))
    short_bonus = 1.5 if dur_secs <= 60 else 1.0

    return vph * short_bonus


def _extract_topic_hints(title: str) -> list[str]:
    """
    Başlıktan potansiyel konu kalıpları çıkarır.
    'What if X?' → ['What if X']
    """
    hints = []

    # "What if" kalıbı
    m = re.search(r"what if (.+?)[\?!]", title, re.IGNORECASE)
    if m:
        hints.append(f"What if {m.group(1).strip()}?")

    # "X vs Y" kalıbı
    m = re.search(r"(.+?)\s+vs\.?\s+(.+)", title, re.IGNORECASE)
    if m:
        hints.append(f"{m.group(1).strip()} vs {m.group(2).strip()}")

    # "The X that Y" kalıbı
    m = re.search(r"the (.+?) that (.+)", title, re.IGNORECASE)
    if m:
        hints.append(title.strip())

    if not hints:
        # Temiz başlık
        cleaned = re.sub(r"[#@\|].*$", "", title).strip()
        if len(cleaned) > 10:
            hints.append(cleaned)

    return hints


def _update_topic_pool(new_topics: list[str]) -> int:
    """Yeni konuları topic_pool.json'a ekler (zaten varsa atlar)."""
    pool_path = "topic_pool.json"
    try:
        with open(pool_path, encoding="utf-8") as f:
            pool = json.load(f)
    except FileNotFoundError:
        pool = []

    existing = {t.lower() for t in pool}
    added = 0
    for topic in new_topics:
        if topic.lower() not in existing:
            pool.append(topic)
            existing.add(topic.lower())
            added += 1

    with open(pool_path, "w", encoding="utf-8") as f:
        json.dump(pool, f, indent=2, ensure_ascii=False)

    return added


def track_competitors(top_n: int = 5) -> dict:
    """
    Ana fonksiyon: rakip kanalları tara, viral videoları bul.

    Returns:
        {
          "viral_videos": [...],
          "new_topics": [...],
          "channels_checked": int,
          "videos_scanned": int,
        }
    """
    if not YOUTUBE_AVAILABLE:
        print("[tracker] google-api-python-client kurulu değil.")
        return {}

    # Kanal ID'lerini env'den veya default'tan al
    raw_ids = os.environ.get("COMPETITOR_CHANNEL_IDS", "")
    channel_ids = [c.strip() for c in raw_ids.split(",") if c.strip()]
    if not channel_ids:
        channel_ids = DEFAULT_COMPETITOR_IDS
        print(f"[tracker] COMPETITOR_CHANNEL_IDS yok, {len(channel_ids)} varsayılan kanal kullanılıyor.")

    try:
        creds = _get_credentials()
        youtube = build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"[tracker] YouTube API bağlantısı kurulamadı: {e}")
        return {}

    state = _load_state()
    seen_ids = set(state.get("seen_video_ids", []))

    all_videos = []
    for ch_id in channel_ids:
        print(f"[tracker] Kanal taranıyor: {ch_id}")
        videos = _get_channel_recent_videos(youtube, ch_id, max_results=20)
        # Sadece yeni videoları işle
        new_videos = [v for v in videos if v["video_id"] not in seen_ids]
        all_videos.extend(new_videos)
        print(f"[tracker]   → {len(new_videos)} yeni video")

    if not all_videos:
        print("[tracker] Yeni video bulunamadı.")
        return {"viral_videos": [], "new_topics": [], "channels_checked": len(channel_ids), "videos_scanned": 0}

    # Toplu istatistik çek
    video_ids = [v["video_id"] for v in all_videos]
    stats = _get_video_stats(youtube, video_ids)

    # Viral skor hesapla
    for v in all_videos:
        v["virality_score"] = _calculate_virality_score(v, stats)
        v["stats"] = stats.get(v["video_id"], {})

    # Viral skora göre sırala
    all_videos.sort(key=lambda x: x["virality_score"], reverse=True)
    top_viral = all_videos[:top_n]

    # Konu önerileri çıkar
    new_topics = []
    for v in top_viral:
        hints = _extract_topic_hints(v["title"])
        new_topics.extend(hints)

    new_topics = list(dict.fromkeys(new_topics))[:10]  # dedup

    # topic_pool.json güncelle
    added_count = _update_topic_pool(new_topics)
    print(f"[tracker] {added_count} yeni konu topic_pool.json'a eklendi.")

    # State güncelle
    state["seen_video_ids"] = list(seen_ids | set(video_ids))
    state["last_checked"] = {
        ch: datetime.now(timezone.utc).isoformat()
        for ch in channel_ids
    }
    _save_state(state)

    result = {
        "viral_videos": [
            {
                "title": v["title"],
                "channel": v.get("channel_name", ""),
                "video_id": v["video_id"],
                "views": v["stats"].get("views", 0),
                "virality_score": round(v["virality_score"], 1),
                "published_at": v["published_at"],
            }
            for v in top_viral
        ],
        "new_topics": new_topics,
        "channels_checked": len(channel_ids),
        "videos_scanned": len(all_videos),
        "topics_added_to_pool": added_count,
    }

    # Özet yazdır
    print(f"\n[tracker] === RAKIP ANALİZİ TAMAMLANDI ===")
    print(f"  Taranan kanallar: {len(channel_ids)}")
    print(f"  Yeni videolar:    {len(all_videos)}")
    print(f"  En viral video:   {top_viral[0]['title'] if top_viral else '—'}")
    print(f"  Önerilen konular: {new_topics[:3]}")

    return result


def send_tracker_report(result: dict) -> None:
    """Tracker sonuçlarını Telegram + Discord'a gönderir."""
    if not result:
        return

    viral = result.get("viral_videos", [])
    topics = result.get("new_topics", [])

    # Telegram
    try:
        from notifier import _send_message
        lines = ["📊 *Rakip Kanal Raporu*\n"]
        lines.append(f"🔍 {result['channels_checked']} kanal · {result['videos_scanned']} video tarandı\n")
        if viral:
            lines.append("🔥 *En Viral Videolar:*")
            for i, v in enumerate(viral[:3], 1):
                lines.append(
                    f"{i}. [{v['title'][:40]}](https://youtu.be/{v['video_id']}) "
                    f"— {v['views']:,} görüntülenme"
                )
        if topics:
            lines.append(f"\n💡 *Önerilen Konular:* {', '.join(topics[:5])}")
        _send_message("\n".join(lines))
        print("[tracker] Telegram raporu gönderildi.")
    except Exception as e:
        print(f"[tracker] Telegram raporu gönderilemedi: {e}")

    # Discord
    try:
        from discord_notify import _post
        top_text = "\n".join(
            f"{i+1}. **{v['title'][:45]}** — {v['views']:,} views"
            for i, v in enumerate(viral[:3])
        ) or "—"
        embed = {
            "title": "🔍 Rakip Kanal Analizi",
            "color": 0x3498DB,
            "fields": [
                {"name": "📡 Taranan Kanallar", "value": str(result["channels_checked"]), "inline": True},
                {"name": "🎬 Yeni Videolar", "value": str(result["videos_scanned"]), "inline": True},
                {"name": "🔥 En Viral Videolar", "value": top_text, "inline": False},
                {"name": "💡 Önerilen Konular", "value": ", ".join(topics[:5]) or "—", "inline": False},
            ],
            "footer": {"text": "WAR SHORTS Competitor Tracker"},
        }
        _post({"embeds": [embed]})
        print("[tracker] Discord raporu gönderildi.")
    except Exception as e:
        print(f"[tracker] Discord raporu gönderilemedi: {e}")


if __name__ == "__main__":
    result = track_competitors()
    send_tracker_report(result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
