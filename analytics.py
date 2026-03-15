"""
analytics.py — YouTube Analytics API ile haftalık performans raporu üretir
ve Telegram'a gönderir.

Her Pazartesi 08:00 UTC'de weekly_report.yml workflow'u tarafından çağrılır.
Ayrıca python analytics.py ile manuel çalıştırılabilir.
"""

import os
import json
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from notifier import _send


SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def _get_credentials() -> Credentials:
    import tempfile

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


def _format_number(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def fetch_weekly_stats() -> dict:
    """
    Son 7 günün kanal istatistiklerini çeker.
    Döndürür: {views, watch_minutes, subscribers_gained, avg_view_duration, top_videos}
    """
    creds = _get_credentials()

    # Kanal ID'sini bul
    yt = build("youtube", "v3", credentials=creds)
    channel_resp = yt.channels().list(part="id,snippet", mine=True).execute()
    channel_id = channel_resp["items"][0]["id"]
    channel_name = channel_resp["items"][0]["snippet"]["title"]

    # Tarih aralığı: son 7 gün
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=7)

    yta = build("youtubeAnalytics", "v2", credentials=creds)

    # Genel metrikler
    report = yta.reports().query(
        ids=f"channel=={channel_id}",
        startDate=str(start_date),
        endDate=str(end_date),
        metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost,averageViewDuration",
        dimensions="",
    ).execute()

    row = report.get("rows", [[0, 0, 0, 0, 0]])[0]
    views = int(row[0])
    watch_min = int(row[1])
    subs_gained = int(row[2])
    subs_lost = int(row[3])
    avg_dur = int(row[4])

    # En iyi 5 video (views'e göre)
    top_report = yta.reports().query(
        ids=f"channel=={channel_id}",
        startDate=str(start_date),
        endDate=str(end_date),
        metrics="views,averageViewDuration",
        dimensions="video",
        sort="-views",
        maxResults=5,
    ).execute()

    top_videos = []
    if top_report.get("rows"):
        video_ids = [r[0] for r in top_report["rows"]]
        vids_resp = yt.videos().list(
            part="snippet",
            id=",".join(video_ids),
        ).execute()
        id_to_title = {v["id"]: v["snippet"]["title"] for v in vids_resp.get("items", [])}

        for r in top_report["rows"]:
            vid_id = r[0]
            top_videos.append({
                "id": vid_id,
                "title": id_to_title.get(vid_id, "—"),
                "views": int(r[1]),
                "avg_dur": int(r[2]),
            })

    return {
        "channel_name": channel_name,
        "period": f"{start_date} → {end_date}",
        "views": views,
        "watch_minutes": watch_min,
        "subscribers_gained": subs_gained,
        "subscribers_lost": subs_lost,
        "net_subs": subs_gained - subs_lost,
        "avg_view_duration": avg_dur,
        "top_videos": top_videos,
    }


def send_weekly_report() -> None:
    """İstatistikleri çeker ve Telegram'a haftalık rapor gönderir."""
    print("[analytics] Haftalık rapor hazırlanıyor...")

    try:
        stats = fetch_weekly_stats()
    except Exception as e:
        _send(f"❌ *Analytics Raporu Başarısız*\n`{e}`")
        raise

    net_sign = "+" if stats["net_subs"] >= 0 else ""
    avg_dur_fmt = f"{stats['avg_view_duration'] // 60}:{stats['avg_view_duration'] % 60:02d}"

    # Top 3 video listesi
    top_lines = ""
    for i, v in enumerate(stats["top_videos"][:3], 1):
        url = f"https://youtube.com/shorts/{v['id']}"
        top_lines += f"\n{i}. [{v['title'][:40]}]({url}) — {_format_number(v['views'])} görüntülenme"

    message = (
        f"📊 *WAR SHORTS — Haftalık Rapor*\n"
        f"📅 {stats['period']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👁  Görüntülenme: *{_format_number(stats['views'])}*\n"
        f"⏱️  İzlenme: *{_format_number(stats['watch_minutes'])} dk*\n"
        f"⏩  Ort. İzlenme Süresi: *{avg_dur_fmt}*\n"
        f"👥  Net Abone: *{net_sign}{stats['net_subs']}*\n"
        f"   (+{stats['subscribers_gained']} kazanılan / -{stats['subscribers_lost']} kaybedilen)\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 *Bu Haftanın En İyileri:*"
        f"{top_lines if top_lines else chr(10) + '—'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📺 [{stats['channel_name']}](https://youtube.com)"
    )

    ok = _send(message)
    if ok:
        print("[analytics] Haftalık rapor Telegram'a gönderildi.")
    else:
        print("[analytics] Telegram gönderimi başarısız.")


if __name__ == "__main__":
    send_weekly_report()
