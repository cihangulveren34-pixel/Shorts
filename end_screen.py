"""
end_screen.py — YouTube Data API v3 ile video yüklendikten sonra
otomatik end screen (bitiş kartı) ekler.

End screen öğeleri:
  - Subscribe butonu (sol alt)
  - Son yüklenen video (sağ alt)

Not: End screen API'si videoların son 20 saniyesinde çalışır.
Short'lar çok kısa olduğu için YouTube bu özelliği kısıtlayabilir —
hata alınırsa sessizce atlanır.
"""

import json
import os
import tempfile

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request


SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def _get_credentials() -> Credentials:
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


def _get_latest_video_id(youtube, exclude_id: str) -> str | None:
    """Kanalın son yüklenen videosunun ID'sini döndürür (mevcut video hariç)."""
    try:
        resp = youtube.search().list(
            part="id",
            forMine=True,
            type="video",
            order="date",
            maxResults=5,
        ).execute()
        for item in resp.get("items", []):
            vid_id = item["id"]["videoId"]
            if vid_id != exclude_id:
                return vid_id
    except Exception as e:
        print(f"[end_screen] Son video alınamadı: {e}")
    return None


def add_end_screen(video_id: str, video_duration_sec: float) -> bool:
    """
    Videoya end screen ekler.
    video_duration_sec: videonun toplam süresi (end screen son 20 sn'de gösterilir).
    Başarılı ise True döndürür.
    """
    try:
        creds = _get_credentials()
        youtube = build("youtube", "v3", credentials=creds)

        # End screen en az 5 saniyelik videolarda çalışır, son 20 sn'de gösterilir
        end_ms = int(video_duration_sec * 1000)
        start_ms = max(0, end_ms - 20000)   # son 20 sn

        # Son yüklenen başka bir video bul
        last_video_id = _get_latest_video_id(youtube, video_id)

        elements = [
            # Subscribe butonu
            {
                "type": "subscribeEndscreen",
                "endscreenElementStyle": {
                    "left": {"offsetPercent": 5},
                    "top": {"offsetPercent": 75},
                    "width": {"offsetPercent": 30},
                    "height": {"offsetPercent": 18},
                },
                "startMs": start_ms,
                "endMs": end_ms,
            }
        ]

        # Eğer başka video varsa "son video" kartı ekle
        if last_video_id:
            elements.append({
                "type": "recentUploadEndscreen",
                "endscreenElementStyle": {
                    "left": {"offsetPercent": 65},
                    "top": {"offsetPercent": 60},
                    "width": {"offsetPercent": 30},
                    "height": {"offsetPercent": 35},
                },
                "startMs": start_ms,
                "endMs": end_ms,
                "videoId": last_video_id,
            })

        youtube.videos().setEndscreen(
            videoId=video_id,
            body={"endscreen": {"elements": elements}},
        ).execute()

        print(f"[end_screen] End screen eklendi: {video_id} (subscribe + son video)")
        return True

    except Exception as e:
        # End screen API tüm videolarda çalışmaz — kritik değil
        print(f"[end_screen] End screen eklenemedi (kritik değil): {e}")
        return False


if __name__ == "__main__":
    import sys
    vid = sys.argv[1] if len(sys.argv) > 1 else input("Video ID: ")
    dur = float(sys.argv[2]) if len(sys.argv) > 2 else 55.0
    add_end_screen(vid, dur)
