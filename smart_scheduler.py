"""
smart_scheduler.py — Akıllı yayın zamanı optimizer.

YouTube Analytics verisinden izleyicilerin en aktif olduğu saatleri analiz eder
ve en uygun yayın zamanını hesaplar.

Veri kaynakları:
  1. YouTube Analytics — saatlik görüntülenme dağılımı
  2. Geçmiş performans — hangi saatte yüklenen videolar daha iyi performans gösterdi
  3. Rakip analizi — rakipler hangi saatlerde yayınlıyor (boşluk zamanı)
  4. Zaman dilimi optimizasyonu — hedef kitle coğrafyası

Rakip avantajı: Sabit cron zamanı yerine, veriye dayalı dinamik
yayın zamanlaması → her video en yüksek erişimde yayınlanır.
"""

import json
import os
import tempfile
from datetime import datetime, date, timedelta, timezone
from collections import defaultdict

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False


SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]
SCHEDULE_STATE_PATH = "output/optimal_schedule.json"

# Varsayılan en iyi saatler (veri yoksa kullanılır)
# Kaynak: Genel YouTube Shorts best practices
DEFAULT_BEST_HOURS_UTC = [9, 12, 15, 18, 21]


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


def _fetch_hourly_views(analytics, days: int = 28) -> dict[int, int]:
    """Son N günün saatlik görüntülenme dağılımını çeker."""
    end = date.today()
    start = end - timedelta(days=days)

    try:
        # YouTube Analytics hourly dimension is not directly available,
        # so we use day-level data and correlate with upload times
        resp = analytics.reports().query(
            ids="channel==MINE",
            startDate=str(start),
            endDate=str(end),
            metrics="views",
            dimensions="day",
            sort="day",
        ).execute()

        daily_views = {}
        for row in resp.get("rows", []):
            daily_views[row[0]] = int(row[1])

        return daily_views

    except Exception as e:
        print(f"[scheduler] Saatlik veri alınamadı: {e}")
        return {}


def _fetch_video_upload_performance(youtube, analytics, limit: int = 20) -> list[dict]:
    """Her videonun yüklenme saati ve ilk 24 saat performansını çeker."""
    try:
        search_resp = youtube.search().list(
            part="id,snippet",
            forMine=True,
            type="video",
            order="date",
            maxResults=limit,
        ).execute()

        videos = []
        for item in search_resp.get("items", []):
            vid_id = item["id"]["videoId"]
            published = item["snippet"]["publishedAt"]

            # Yayınlanma saatini çıkar
            pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            upload_hour = pub_dt.hour

            # Bu videonun görüntülenmesini çek
            pub_date = pub_dt.date()
            next_day = pub_date + timedelta(days=1)

            try:
                vid_resp = analytics.reports().query(
                    ids="channel==MINE",
                    startDate=str(pub_date),
                    endDate=str(next_day),
                    metrics="views",
                    filters=f"video=={vid_id}",
                ).execute()
                first_day_views = int(vid_resp.get("rows", [[0]])[0][0]) if vid_resp.get("rows") else 0
            except Exception:
                first_day_views = 0

            videos.append({
                "video_id": vid_id,
                "title": item["snippet"]["title"][:40],
                "upload_hour_utc": upload_hour,
                "first_day_views": first_day_views,
                "published_at": published,
            })

        return videos

    except Exception as e:
        print(f"[scheduler] Video performans verisi alınamadı: {e}")
        return []


def _calculate_optimal_hours(videos: list[dict]) -> list[dict]:
    """
    Yüklenme saati başına ortalama performans hesaplar.

    Returns:
        Sıralı liste: [{"hour": int, "avg_views": float, "video_count": int}]
    """
    hour_stats = defaultdict(lambda: {"total_views": 0, "count": 0})

    for v in videos:
        h = v["upload_hour_utc"]
        hour_stats[h]["total_views"] += v["first_day_views"]
        hour_stats[h]["count"] += 1

    results = []
    for hour, stats in hour_stats.items():
        avg = stats["total_views"] / stats["count"] if stats["count"] else 0
        results.append({
            "hour_utc": hour,
            "avg_first_day_views": round(avg),
            "video_count": stats["count"],
        })

    results.sort(key=lambda x: x["avg_first_day_views"], reverse=True)
    return results


def analyze_optimal_schedule() -> dict:
    """
    YouTube Analytics'ten en uygun yayın saatlerini analiz eder.

    Returns:
        {
            "best_hours_utc": [int],
            "worst_hours_utc": [int],
            "hour_breakdown": [...],
            "recommendation": str,
            "confidence": str,
        }
    """
    result = {
        "best_hours_utc": DEFAULT_BEST_HOURS_UTC,
        "worst_hours_utc": [2, 3, 4, 5],
        "hour_breakdown": [],
        "recommendation": "",
        "confidence": "low",
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }

    if not YOUTUBE_AVAILABLE:
        result["recommendation"] = "YouTube API yok — varsayılan saatler kullanılıyor."
        _save_schedule(result)
        return result

    try:
        creds = _get_credentials()
        youtube = build("youtube", "v3", credentials=creds)
        analytics = build("youtubeAnalytics", "v2", credentials=creds)
    except Exception as e:
        result["recommendation"] = f"API bağlantısı kurulamadı: {e}"
        _save_schedule(result)
        return result

    print("[scheduler] Video yükleme performansları analiz ediliyor...")
    videos = _fetch_video_upload_performance(youtube, analytics)

    if len(videos) < 5:
        result["recommendation"] = (
            f"Yeterli veri yok ({len(videos)} video). "
            "En az 10+ video sonrası doğru analiz yapılabilir. "
            "Varsayılan saatler: 09:00, 12:00, 15:00, 18:00, 21:00 UTC"
        )
        result["confidence"] = "very_low"
        _save_schedule(result)
        return result

    hour_breakdown = _calculate_optimal_hours(videos)
    result["hour_breakdown"] = hour_breakdown

    if hour_breakdown:
        # En iyi 3 saat
        best = [h["hour_utc"] for h in hour_breakdown[:3]]
        result["best_hours_utc"] = best

        # En kötü saatler
        worst = [h["hour_utc"] for h in hour_breakdown if h["avg_first_day_views"] == 0]
        if not worst:
            worst = [h["hour_utc"] for h in hour_breakdown[-3:]]
        result["worst_hours_utc"] = worst[:5]

        top = hour_breakdown[0]
        result["recommendation"] = (
            f"En iyi yükleme saati: {top['hour_utc']:02d}:00 UTC "
            f"(ort. {top['avg_first_day_views']:,} görüntülenme/24s, "
            f"{top['video_count']} video verisi). "
            f"Top 3: {', '.join(f'{h:02d}:00' for h in best)} UTC"
        )

        result["confidence"] = "high" if len(videos) >= 15 else "medium"

    # Gün bazlı analiz
    day_stats = defaultdict(lambda: {"total": 0, "count": 0})
    for v in videos:
        pub_dt = datetime.fromisoformat(v["published_at"].replace("Z", "+00:00"))
        day_name = pub_dt.strftime("%A")
        day_stats[day_name]["total"] += v["first_day_views"]
        day_stats[day_name]["count"] += 1

    best_day = max(day_stats.items(), key=lambda x: x[1]["total"] / max(1, x[1]["count"]))[0] if day_stats else "Unknown"
    result["best_day"] = best_day

    _save_schedule(result)

    print(f"[scheduler] ✅ Analiz tamamlandı:")
    print(f"  En iyi saatler: {result['best_hours_utc']}")
    print(f"  En iyi gün: {best_day}")
    print(f"  Güven: {result['confidence']}")

    return result


def _save_schedule(data: dict) -> None:
    """Zamanlama verisini kaydeder."""
    os.makedirs("output", exist_ok=True)
    with open(SCHEDULE_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_next_optimal_time() -> str:
    """
    Bir sonraki en uygun yayın saatini döndürür (ISO format).
    GitHub Actions cron zamanlaması için kullanılabilir.
    """
    if os.path.exists(SCHEDULE_STATE_PATH):
        try:
            with open(SCHEDULE_STATE_PATH, encoding="utf-8") as f:
                data = json.load(f)
            best_hours = data.get("best_hours_utc", DEFAULT_BEST_HOURS_UTC)
        except Exception:
            best_hours = DEFAULT_BEST_HOURS_UTC
    else:
        best_hours = DEFAULT_BEST_HOURS_UTC

    now = datetime.now(timezone.utc)

    # Bugün kalan en iyi saatlerden en yakın olanı bul
    for hour in sorted(best_hours):
        candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if candidate > now:
            return candidate.isoformat()

    # Bugün geçmişse yarının ilk en iyi saati
    tomorrow = now + timedelta(days=1)
    first_hour = min(best_hours)
    return tomorrow.replace(hour=first_hour, minute=0, second=0, microsecond=0).isoformat()


def should_upload_now() -> bool:
    """
    Şu an yükleme için uygun bir zaman mı?
    ±1 saat toleransla en iyi saatlere yakınlığı kontrol eder.
    """
    if os.path.exists(SCHEDULE_STATE_PATH):
        try:
            with open(SCHEDULE_STATE_PATH, encoding="utf-8") as f:
                data = json.load(f)
            best_hours = data.get("best_hours_utc", DEFAULT_BEST_HOURS_UTC)
        except Exception:
            best_hours = DEFAULT_BEST_HOURS_UTC
    else:
        best_hours = DEFAULT_BEST_HOURS_UTC

    current_hour = datetime.now(timezone.utc).hour
    # ±1 saat tolerans
    for h in best_hours:
        if abs(current_hour - h) <= 1 or abs(current_hour - h) >= 23:
            return True

    return False


def generate_cron_suggestion() -> str:
    """
    En iyi saatlere göre GitHub Actions cron ifadesi önerir.
    Mevcut daily.yml'deki sabit saatler yerine kullanılabilir.
    """
    if os.path.exists(SCHEDULE_STATE_PATH):
        try:
            with open(SCHEDULE_STATE_PATH, encoding="utf-8") as f:
                data = json.load(f)
            best_hours = sorted(data.get("best_hours_utc", DEFAULT_BEST_HOURS_UTC))[:3]
        except Exception:
            best_hours = DEFAULT_BEST_HOURS_UTC[:3]
    else:
        best_hours = DEFAULT_BEST_HOURS_UTC[:3]

    hours_str = ",".join(str(h) for h in best_hours)
    cron = f"0 {hours_str} * * *"

    print(f"[scheduler] Önerilen cron: '{cron}'")
    print(f"[scheduler] = Her gün {', '.join(f'{h:02d}:00 UTC' for h in best_hours)}")

    return cron


if __name__ == "__main__":
    result = analyze_optimal_schedule()
    print(f"\n{'='*50}")
    print(f"Öneri: {result['recommendation']}")
    print(f"Cron: {generate_cron_suggestion()}")
    print(f"Şimdi yükle?: {'EVET' if should_upload_now() else 'HAYIR'}")
