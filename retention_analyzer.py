"""
retention_analyzer.py — YouTube izleyici bırakma noktası analizi.

YouTube Analytics API'den audience retention (izleyici tutma) eğrisi çeker:
  - Videonun hangi saniyesinde kaç % izleyici kaldığını analiz eder
  - Kritik düşüş noktalarını tespit eder (hook, twist, CTA)
  - Bulgulara göre gelecek script'ler için öneriler üretir
  - Haftalık raporda en iyi/en kötü retention videolarını gösterir

Sonuçlar output/retention_insights.json dosyasına kaydedilir.
script_gen.py bu dosyayı okuyarak script üretim talimatlarını iyileştirir.

Gereksinim: YOUTUBE_TOKEN_JSON
"""

import json
import os
import tempfile
from datetime import date, timedelta, datetime, timezone

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
INSIGHTS_PATH = "output/retention_insights.json"


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


def _fetch_recent_video_ids(youtube, limit: int = 10) -> list[dict]:
    """Kanalın son N videosunu döndürür."""
    try:
        resp = youtube.search().list(
            part="id,snippet",
            forMine=True,
            type="video",
            order="date",
            maxResults=limit,
        ).execute()
        return [
            {
                "video_id": item["id"]["videoId"],
                "title": item["snippet"]["title"],
                "published_at": item["snippet"]["publishedAt"],
            }
            for item in resp.get("items", [])
        ]
    except Exception as e:
        print(f"[retention] Video listesi alınamadı: {e}")
        return []


def _fetch_audience_retention(analytics, video_id: str) -> list[float]:
    """
    Belirli bir video için audience retention eğrisini döndürür.
    Her eleman = o zaman diliminde kalan izleyici yüzdesi (0.0–1.0).
    """
    try:
        end = date.today().isoformat()
        start = (date.today() - timedelta(days=60)).isoformat()

        resp = analytics.reports().query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics="audienceWatchRatio",
            dimensions="elapsedVideoTimeRatio",
            filters=f"video=={video_id}",
            sort="elapsedVideoTimeRatio",
        ).execute()

        rows = resp.get("rows", [])
        if not rows:
            return []

        # elapsedVideoTimeRatio → audienceWatchRatio
        return [float(r[1]) for r in rows]

    except Exception as e:
        print(f"[retention] Retention verisi alınamadı ({video_id}): {e}")
        return []


def _analyze_retention_curve(curve: list[float]) -> dict:
    """
    Retention eğrisini analiz eder ve kritik noktaları çıkarır.

    Returns:
        {
          "avg_retention": float,           # Ortalama % tutma
          "hook_retention_3s": float,       # İlk 3 saniye tutma
          "midpoint_retention": float,      # Ortada kalan %
          "cta_retention": float,           # Son 10 saniyede kalan %
          "biggest_drop_at": float,         # En büyük düşüşün yüzdesi (0.0–1.0)
          "biggest_drop_pct": float,        # Düşüş miktarı
        }
    """
    if not curve or len(curve) < 4:
        return {}

    n = len(curve)
    hook_idx = max(1, int(n * 0.05))   # İlk %5 → ~3 saniye (60s video için)
    mid_idx = n // 2
    cta_idx = int(n * 0.85)

    # En büyük tek adımlı düşüş
    drops = [(i, curve[i - 1] - curve[i]) for i in range(1, n) if curve[i - 1] > 0]
    biggest_drop = max(drops, key=lambda x: x[1]) if drops else (0, 0)

    return {
        "avg_retention": round(sum(curve) / n * 100, 1),
        "hook_retention_3s": round(curve[hook_idx] * 100, 1),
        "midpoint_retention": round(curve[mid_idx] * 100, 1),
        "cta_retention": round(curve[cta_idx] * 100, 1),
        "biggest_drop_at_pct": round(biggest_drop[0] / n * 100, 1),
        "biggest_drop_amount": round(biggest_drop[1] * 100, 1),
    }


def _generate_script_recommendations(insights_list: list[dict]) -> list[str]:
    """
    Tüm videolar için retention analizinden script yazım önerileri üretir.
    """
    if not insights_list:
        return []

    recommendations = []
    avg_hooks = [v["analysis"]["hook_retention_3s"] for v in insights_list if v.get("analysis", {}).get("hook_retention_3s")]
    avg_drops = [v["analysis"]["biggest_drop_at_pct"] for v in insights_list if v.get("analysis", {}).get("biggest_drop_at_pct")]

    if avg_hooks:
        mean_hook = sum(avg_hooks) / len(avg_hooks)
        if mean_hook < 70:
            recommendations.append(
                f"Hook zayıf (ort. %{mean_hook:.0f} tutma): "
                "İlk 3 saniyeyi daha şok edici/soru bazlı yap."
            )
        else:
            recommendations.append(f"Hook güçlü: ort. %{mean_hook:.0f} izleyici ilk 3s'yi geçiyor. ✓")

    if avg_drops:
        mean_drop_point = sum(avg_drops) / len(avg_drops)
        recommendations.append(
            f"Ortalama en büyük düşüş videonun %{mean_drop_point:.0f}'inde. "
            "Bu noktaya twist/sürpriz bilgi ekle."
        )

    # En iyi ve en kötü video
    if insights_list:
        sorted_by_avg = sorted(
            insights_list,
            key=lambda v: v.get("analysis", {}).get("avg_retention", 0),
            reverse=True,
        )
        best = sorted_by_avg[0]
        worst = sorted_by_avg[-1]
        recommendations.append(
            f"En iyi retention: '{best['title'][:40]}' "
            f"(%{best['analysis'].get('avg_retention', 0)}). "
            "Bu videonun yapısını örnek al."
        )
        if len(sorted_by_avg) > 1:
            recommendations.append(
                f"En düşük retention: '{worst['title'][:40]}' "
                f"(%{worst['analysis'].get('avg_retention', 0)}). "
                "Bu yapıdan kaçın."
            )

    return recommendations


def analyze_retention(video_limit: int = 10) -> dict:
    """
    Son N videonun retention analizini yapar ve önerileri kaydeder.

    Returns:
        {"videos": [...], "recommendations": [...], "analyzed": int}
    """
    if not YOUTUBE_AVAILABLE:
        print("[retention] google-api-python-client kurulu değil.")
        return {}

    try:
        creds = _get_credentials()
        youtube = build("youtube", "v3", credentials=creds)
        analytics = build("youtubeAnalytics", "v2", credentials=creds)
    except Exception as e:
        print(f"[retention] API bağlantısı kurulamadı: {e}")
        return {}

    videos = _fetch_recent_video_ids(youtube, limit=video_limit)
    print(f"[retention] {len(videos)} video analiz ediliyor...")

    insights_list = []
    for v in videos:
        curve = _fetch_audience_retention(analytics, v["video_id"])
        if not curve:
            continue
        analysis = _analyze_retention_curve(curve)
        insights_list.append({
            "video_id": v["video_id"],
            "title": v["title"],
            "published_at": v["published_at"],
            "analysis": analysis,
        })
        print(
            f"[retention]  {v['title'][:40]}: "
            f"ort.%{analysis.get('avg_retention', '?')} tutma, "
            f"hook %{analysis.get('hook_retention_3s', '?')}"
        )

    recommendations = _generate_script_recommendations(insights_list)

    result = {
        "analyzed": len(insights_list),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "videos": insights_list,
        "recommendations": recommendations,
    }

    # Kaydet — script_gen.py bunu okuyabilir
    os.makedirs("output", exist_ok=True)
    with open(INSIGHTS_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"[retention] İçgörüler kaydedildi: {INSIGHTS_PATH}")

    # Telegram + Discord raporu
    _notify_retention_report(result)

    return result


def _notify_retention_report(result: dict) -> None:
    """Retention özet raporunu bildirim kanallarına gönderir."""
    recs = result.get("recommendations", [])
    if not recs:
        return

    msg = "📊 *Retention Analizi*\n\n" + "\n".join(f"• {r}" for r in recs)

    try:
        from notifier import _send_message
        _send_message(msg)
    except Exception:
        pass

    try:
        from discord_notify import _post
        _post({
            "embeds": [{
                "title": "📊 Audience Retention Analizi",
                "color": 0x9B59B6,
                "description": "\n".join(f"• {r}" for r in recs),
                "footer": {"text": f"{result['analyzed']} video analiz edildi — WAR SHORTS"},
            }]
        })
    except Exception:
        pass


def load_insights() -> dict:
    """script_gen.py veya diğer modüller için kayıtlı içgörüleri yükler."""
    if os.path.exists(INSIGHTS_PATH):
        with open(INSIGHTS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


if __name__ == "__main__":
    result = analyze_retention()
    print(f"\nAnliz tamamlandı: {result.get('analyzed', 0)} video")
    for r in result.get("recommendations", []):
        print(f"  • {r}")
