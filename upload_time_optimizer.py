"""
upload_time_optimizer.py — YouTube Analytics'e göre en iyi yükleme saatini belirler.

Son 90 günün saatlik görüntülenme verisini çekerek:
  - En yüksek trafik saat aralığını bulur
  - GitHub Actions cron schedule önerir
  - Optimal gün/saat bilgisini kaydeder

GitHub Actions cron'u otomatik güncelleyemez (repo write izni gerekir).
Bunun yerine önerilen zamanı bir dosyaya kaydeder; kullanıcı manuel güncelleyebilir
ya da workflow_dispatch ile istediği zaman çalıştırabilir.

Gereksinim: YOUTUBE_TOKEN_JSON
"""

import json
import os
import tempfile
from datetime import date, timedelta, datetime, timezone
from collections import defaultdict

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False


SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly"]
SCHEDULE_INSIGHT_PATH = "output/upload_schedule.json"

DAY_NAMES = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
DAY_NAMES_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


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


def _fetch_hourly_views(analytics) -> dict:
    """
    Son 90 günün saatlik görüntülenme toplamlarını döndürür.
    Returns: {hour_utc: total_views}
    """
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=90)).isoformat()

    hourly = defaultdict(int)

    try:
        resp = analytics.reports().query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics="views",
            dimensions="hour",
        ).execute()
        for row in resp.get("rows", []):
            hour = int(row[0])
            views = int(row[1])
            hourly[hour] += views
    except Exception as e:
        print(f"[upload_time] Saatlik veri alınamadı: {e}")

    return dict(hourly)


def _fetch_daily_views(analytics) -> dict:
    """
    Son 90 günün günlük dağılımını döndürür (haftanın günü bazında).
    Returns: {weekday_0_mon: total_views}
    """
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=90)).isoformat()

    daily = defaultdict(int)

    try:
        resp = analytics.reports().query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics="views",
            dimensions="day",
        ).execute()

        for row in resp.get("rows", []):
            day_str = row[0]  # YYYY-MM-DD
            views = int(row[1])
            weekday = datetime.strptime(day_str, "%Y-%m-%d").weekday()  # 0=Mon
            daily[weekday] += views

    except Exception as e:
        print(f"[upload_time] Günlük veri alınamadı: {e}")

    return dict(daily)


def _best_upload_window(hourly: dict, daily: dict) -> dict:
    """
    En yüksek görüntülenme alan saat + gün kombinasyonunu bulur.
    Yükleme zamanı, pikin 1-2 saat öncesi olmalı (YouTube index süresi).
    """
    if not hourly:
        return {"best_hour_utc": 9, "best_day": 0, "confidence": "low"}

    # En iyi 3 saat
    sorted_hours = sorted(hourly.items(), key=lambda x: x[1], reverse=True)
    best_hours = [h for h, _ in sorted_hours[:3]]

    # Upload için pikin 2 saat öncesi
    peak_hour = sorted_hours[0][0]
    upload_hour = (peak_hour - 2) % 24

    # En iyi gün
    best_day = 0
    if daily:
        best_day = max(daily, key=daily.get)

    # Güven skoru: veri miktarına göre
    total_views = sum(hourly.values())
    confidence = "high" if total_views > 10000 else "medium" if total_views > 1000 else "low"

    return {
        "peak_hour_utc": peak_hour,
        "best_upload_hour_utc": upload_hour,
        "best_day": best_day,
        "best_day_name": DAY_NAMES_EN[best_day],
        "top_3_hours": best_hours,
        "confidence": confidence,
        "total_views_analyzed": total_views,
    }


def _cron_expression(window: dict) -> str:
    """GitHub Actions cron ifadesi üretir."""
    h = window.get("best_upload_hour_utc", 9)
    d = window.get("best_day", 1)  # 0=Mon, cron'da 1=Mon
    cron_day = d + 1 if d < 6 else 0
    # Günlük pipeline için gün önemli değil — sadece saat
    return f"0 {h} * * *"


def optimize_upload_time() -> dict:
    """
    Upload zamanını analiz eder ve önerilen schedule'ı kaydeder.

    Returns:
        {"recommended_cron": str, "best_hour_utc": int, ...}
    """
    if not YOUTUBE_AVAILABLE:
        print("[upload_time] google-api-python-client kurulu değil.")
        return {}

    try:
        creds = _get_credentials()
        analytics = build("youtubeAnalytics", "v2", credentials=creds)
    except Exception as e:
        print(f"[upload_time] API bağlantısı kurulamadı: {e}")
        return {}

    print("[upload_time] Saatlik ve günlük veriler çekiliyor (son 90 gün)...")
    hourly = _fetch_hourly_views(analytics)
    daily = _fetch_daily_views(analytics)

    window = _best_upload_window(hourly, daily)
    cron = _cron_expression(window)

    # Saat dağılımı (top 5)
    top_hours = sorted(hourly.items(), key=lambda x: x[1], reverse=True)[:5]
    top_days = sorted(daily.items(), key=lambda x: x[1], reverse=True)[:3]

    result = {
        **window,
        "recommended_cron": cron,
        "top_hours": [{"hour_utc": h, "views": v} for h, v in top_hours],
        "top_days": [{"day": DAY_NAMES_EN[d], "views": v} for d, v in top_days],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            f"Mevcut cron: '0 9 * * *' → Önerilen: '{cron}' "
            f"(güven: {window['confidence']}). "
            "daily.yml dosyasında manuel güncelleme gerekir."
        ),
    }

    os.makedirs("output", exist_ok=True)
    with open(SCHEDULE_INSIGHT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"[upload_time] Önerilen upload saati: {window['best_upload_hour_utc']:02d}:00 UTC")
    print(f"[upload_time] Önerilen cron: {cron}")
    print(f"[upload_time] En iyi gün: {window['best_day_name']}")

    _notify_schedule_recommendation(result)
    return result


def _notify_schedule_recommendation(result: dict) -> None:
    """Zamanlama önerisini Telegram + Discord'a gönderir."""
    h = result.get("best_upload_hour_utc", 9)
    day = result.get("best_day_name", "?")
    cron = result.get("recommended_cron", "?")
    confidence = result.get("confidence", "?")

    msg = (
        f"⏰ *Upload Zamanı Önerisi*\n\n"
        f"📅 En iyi gün: {day}\n"
        f"🕐 En iyi saat: {h:02d}:00 UTC\n"
        f"⚙️ Cron: `{cron}`\n"
        f"📊 Güven: {confidence}\n\n"
        f"_daily.yml → schedule → cron satırını güncelle_"
    )

    try:
        from notifier import _send_message
        _send_message(msg)
    except Exception:
        pass

    try:
        from discord_notify import _post
        top_hours_text = "\n".join(
            f"{item['hour_utc']:02d}:00 UTC — {item['views']:,} görüntülenme"
            for item in result.get("top_hours", [])[:5]
        )
        _post({
            "embeds": [{
                "title": "⏰ Upload Zamanı Optimizasyonu",
                "color": 0x1ABC9C,
                "fields": [
                    {"name": "En İyi Saat", "value": f"{h:02d}:00 UTC", "inline": True},
                    {"name": "En İyi Gün", "value": day, "inline": True},
                    {"name": "Önerilen Cron", "value": f"`{cron}`", "inline": True},
                    {"name": "Güven", "value": confidence, "inline": True},
                    {"name": "Top 5 Saat", "value": top_hours_text or "—", "inline": False},
                ],
                "footer": {"text": "WAR SHORTS Upload Time Optimizer"},
            }]
        })
    except Exception:
        pass


if __name__ == "__main__":
    result = optimize_upload_time()
    if result:
        print(f"\nÖnerilen cron: {result['recommended_cron']}")
        print(f"Kaydedildi: {SCHEDULE_INSIGHT_PATH}")
