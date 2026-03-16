"""
performance_dashboard.py — Kanal performansını gösteren HTML dashboard üretir.

YouTube Analytics API'den veri çeker ve şu bilgileri içeren tek sayfalık
bir HTML dosyası oluşturur:
  - Son 30 günün görüntülenme grafiği
  - En iyi 10 video tablosu
  - İzlenme süresi, abone, CTR özetleri
  - Son haftalık değişim oranları

GitHub Actions artifact olarak yüklenir; yerel olarak da açılabilir.
Ekstra bağımlılık yok — saf HTML + inline Chart.js (CDN).
"""

import json
import os
import tempfile
from datetime import datetime, date, timedelta, timezone

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
DASHBOARD_PATH = "output/dashboard.html"


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


def _fetch_channel_stats(analytics, start_date: str, end_date: str) -> dict:
    """Son 30 günün kanal toplamlarını getirir."""
    try:
        resp = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost,impressionClickThroughRate",
        ).execute()
        rows = resp.get("rows", [[0, 0, 0, 0, 0]])
        r = rows[0] if rows else [0, 0, 0, 0, 0]
        return {
            "views": int(r[0]),
            "watch_minutes": int(r[1]),
            "subs_gained": int(r[2]),
            "subs_lost": int(r[3]),
            "ctr": round(float(r[4]) * 100, 2),
            "net_subs": int(r[2]) - int(r[3]),
        }
    except Exception as e:
        print(f"[dashboard] Kanal istatistikleri alınamadı: {e}")
        return {}


def _fetch_daily_views(analytics, start_date: str, end_date: str) -> list[dict]:
    """Günlük görüntülenme serisini döndürür."""
    try:
        resp = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views",
            dimensions="day",
        ).execute()
        return [{"date": r[0], "views": int(r[1])} for r in resp.get("rows", [])]
    except Exception as e:
        print(f"[dashboard] Günlük görüntülenme alınamadı: {e}")
        return []


def _fetch_top_videos(analytics, youtube, start_date: str, end_date: str, limit: int = 10) -> list[dict]:
    """En fazla görüntülenen videoları getirir."""
    try:
        resp = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views,estimatedMinutesWatched,averageViewDuration,impressionClickThroughRate",
            dimensions="video",
            sort="-views",
            maxResults=limit,
        ).execute()

        video_ids = [r[0] for r in resp.get("rows", [])]
        if not video_ids:
            return []

        # Video başlıklarını çek
        details_resp = youtube.videos().list(
            part="snippet",
            id=",".join(video_ids),
        ).execute()
        titles = {item["id"]: item["snippet"]["title"] for item in details_resp.get("items", [])}

        videos = []
        for row in resp.get("rows", []):
            vid_id = row[0]
            videos.append({
                "video_id": vid_id,
                "title": titles.get(vid_id, vid_id)[:50],
                "views": int(row[1]),
                "watch_minutes": int(row[2]),
                "avg_duration": round(float(row[3]), 1),
                "ctr": round(float(row[4]) * 100, 2),
                "url": f"https://youtube.com/shorts/{vid_id}",
            })
        return videos
    except Exception as e:
        print(f"[dashboard] Top video listesi alınamadı: {e}")
        return []


def _generate_html(stats: dict, daily: list, top_videos: list, period: str) -> str:
    """Tek sayfalık HTML dashboard oluşturur."""

    daily_labels = json.dumps([d["date"] for d in daily])
    daily_data = json.dumps([d["views"] for d in daily])

    video_rows = ""
    for i, v in enumerate(top_videos, 1):
        video_rows += f"""
        <tr>
          <td>{i}</td>
          <td><a href="{v['url']}" target="_blank">{v['title']}</a></td>
          <td>{v['views']:,}</td>
          <td>{v['watch_minutes']:,} dk</td>
          <td>{v['avg_duration']}s</td>
          <td>{v['ctr']}%</td>
        </tr>"""

    net_subs = stats.get("net_subs", 0)
    net_subs_color = "#2ecc71" if net_subs >= 0 else "#e74c3c"
    net_subs_sign = "+" if net_subs >= 0 else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WAR SHORTS — Performance Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', sans-serif; background: #0d0d0d; color: #e0e0e0; padding: 24px; }}
  h1 {{ color: #c41e1e; font-size: 1.8rem; margin-bottom: 4px; }}
  .period {{ color: #888; font-size: 0.9rem; margin-bottom: 24px; }}
  .cards {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 28px; }}
  .card {{
    background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 10px;
    padding: 18px 22px; flex: 1; min-width: 140px;
  }}
  .card .label {{ font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 1px; }}
  .card .value {{ font-size: 1.9rem; font-weight: 700; margin-top: 4px; }}
  .chart-box {{
    background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 10px;
    padding: 20px; margin-bottom: 28px;
  }}
  .chart-box h2 {{ font-size: 1rem; color: #ccc; margin-bottom: 16px; }}
  table {{ width: 100%; border-collapse: collapse; background: #1a1a1a;
           border: 1px solid #2a2a2a; border-radius: 10px; overflow: hidden; }}
  th {{ background: #222; color: #888; font-size: 0.75rem; text-transform: uppercase;
        padding: 10px 14px; text-align: left; letter-spacing: 0.5px; }}
  td {{ padding: 10px 14px; border-top: 1px solid #222; font-size: 0.9rem; }}
  td a {{ color: #c41e1e; text-decoration: none; }}
  td a:hover {{ text-decoration: underline; }}
  tr:hover td {{ background: #202020; }}
  .footer {{ text-align: center; color: #444; font-size: 0.75rem; margin-top: 24px; }}
</style>
</head>
<body>

<h1>⚔️ WAR SHORTS — Performance Dashboard</h1>
<div class="period">📅 {period} &nbsp;·&nbsp; Oluşturuldu: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</div>

<div class="cards">
  <div class="card">
    <div class="label">Görüntülenme</div>
    <div class="value" style="color:#e74c3c">{stats.get('views', 0):,}</div>
  </div>
  <div class="card">
    <div class="label">İzlenme (dk)</div>
    <div class="value" style="color:#f39c12">{stats.get('watch_minutes', 0):,}</div>
  </div>
  <div class="card">
    <div class="label">Net Abone</div>
    <div class="value" style="color:{net_subs_color}">{net_subs_sign}{net_subs}</div>
  </div>
  <div class="card">
    <div class="label">Ortalama CTR</div>
    <div class="value" style="color:#3498db">{stats.get('ctr', 0)}%</div>
  </div>
</div>

<div class="chart-box">
  <h2>📈 Günlük Görüntülenme (Son 30 Gün)</h2>
  <canvas id="viewsChart" height="100"></canvas>
</div>

<h2 style="margin-bottom:12px;font-size:1rem;color:#ccc">🏆 En İyi {len(top_videos)} Video</h2>
<table>
  <thead>
    <tr>
      <th>#</th><th>Başlık</th><th>Görüntülenme</th>
      <th>İzlenme</th><th>Ort. Süre</th><th>CTR</th>
    </tr>
  </thead>
  <tbody>{video_rows}</tbody>
</table>

<div class="footer">WAR SHORTS Pipeline — github.com</div>

<script>
const ctx = document.getElementById('viewsChart').getContext('2d');
new Chart(ctx, {{
  type: 'bar',
  data: {{
    labels: {daily_labels},
    datasets: [{{
      label: 'Görüntülenme',
      data: {daily_data},
      backgroundColor: 'rgba(196, 30, 30, 0.7)',
      borderColor: '#c41e1e',
      borderWidth: 1,
      borderRadius: 3,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ ticks: {{ color: '#666', maxTicksLimit: 10 }}, grid: {{ color: '#1f1f1f' }} }},
      y: {{ ticks: {{ color: '#666' }}, grid: {{ color: '#1f1f1f' }} }},
    }}
  }}
}});
</script>
</body>
</html>"""


def generate_dashboard(output_path: str = DASHBOARD_PATH) -> str:
    """
    Dashboard HTML'i üretir ve dosyaya kaydeder.

    Returns:
        Dosya yolu
    """
    if not YOUTUBE_AVAILABLE:
        print("[dashboard] google-api-python-client kurulu değil.")
        return ""

    os.makedirs("output", exist_ok=True)

    try:
        creds = _get_credentials()
        analytics = build("youtubeAnalytics", "v2", credentials=creds)
        youtube = build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"[dashboard] API bağlantısı kurulamadı: {e}")
        return ""

    end = date.today()
    start = end - timedelta(days=30)
    start_str = start.isoformat()
    end_str = end.isoformat()
    period = f"{start_str} → {end_str}"

    print("[dashboard] Veriler toplanıyor...")
    stats = _fetch_channel_stats(analytics, start_str, end_str)
    daily = _fetch_daily_views(analytics, start_str, end_str)
    top_videos = _fetch_top_videos(analytics, youtube, start_str, end_str)

    html = _generate_html(stats, daily, top_videos, period)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[dashboard] Dashboard oluşturuldu: {output_path}")
    return output_path


if __name__ == "__main__":
    path = generate_dashboard()
    print(f"Dashboard: {path}")
