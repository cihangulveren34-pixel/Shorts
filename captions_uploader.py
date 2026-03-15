"""
captions_uploader.py — YouTube videosuna resmi altyazı yükler.

VTT dosyasını YouTube'a caption (altyazı) olarak yükler:
- YouTube bu altyazıları full-text search'te indeksler (SEO boost)
- Erişilebilirlik sağlar
- İzlenme süresi artışına katkı sağlar

Gereksinim: YOUTUBE_TOKEN_JSON (mevcut OAuth2 token yeterli)
"""

import json
import os
import re
import tempfile

try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False


SCOPES = [
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


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


def _vtt_to_srt(vtt_path: str) -> str:
    """
    VTT formatını SRT formatına dönüştürür.
    YouTube her ikisini de kabul eder ama SRT daha geniş uyumlu.
    """
    with open(vtt_path, encoding="utf-8") as f:
        content = f.read()

    # WEBVTT başlığını kaldır
    content = re.sub(r"^WEBVTT.*?\n\n", "", content, flags=re.DOTALL)

    # --> zaman formatını dönüştür: 00:00:01.500 → 00:00:01,500
    content = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", content)

    # Blok numaralarını ekle
    blocks = [b.strip() for b in content.split("\n\n") if b.strip()]
    srt_lines = []
    counter = 1
    for block in blocks:
        lines = block.splitlines()
        # Zaman satırı içeriyorsa bloğu dahil et
        if any("-->" in l for l in lines):
            srt_lines.append(str(counter))
            srt_lines.extend(lines)
            srt_lines.append("")
            counter += 1

    return "\n".join(srt_lines)


def upload_captions(
    video_id: str,
    vtt_path: str,
    language: str = "en",
    name: str = "Auto-generated",
) -> bool:
    """
    VTT altyazı dosyasını YouTube'a yükler.

    Args:
        video_id: YouTube video ID
        vtt_path: .vtt dosya yolu
        language: BCP-47 dil kodu ('en', 'tr', ...)
        name: Altyazı listesinde görünen ad

    Returns:
        True if successful
    """
    if not YOUTUBE_AVAILABLE:
        print("[captions] google-api-python-client kurulu değil.")
        return False

    if not os.path.exists(vtt_path):
        print(f"[captions] VTT dosyası bulunamadı: {vtt_path}")
        return False

    try:
        creds = _get_credentials()
        youtube = build("youtube", "v3", credentials=creds)

        # Önce mevcut caption'ları kontrol et — aynı dil varsa sil
        existing = youtube.captions().list(
            part="snippet",
            videoId=video_id,
        ).execute()

        for caption in existing.get("items", []):
            if caption["snippet"]["language"] == language:
                youtube.captions().delete(id=caption["id"]).execute()
                print(f"[captions] Eski altyazı silindi: {caption['id']}")

        # VTT → geçici SRT dönüşümü
        srt_content = _vtt_to_srt(vtt_path)
        tmp_srt = tempfile.NamedTemporaryFile(
            mode="w", suffix=".srt", delete=False, encoding="utf-8"
        )
        tmp_srt.write(srt_content)
        tmp_srt.close()

        # Yükle
        insert_result = youtube.captions().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "language": language,
                    "name": name,
                    "isDraft": False,
                }
            },
            media_body=MediaFileUpload(
                tmp_srt.name,
                mimetype="application/octet-stream",
                resumable=False,
            ),
        ).execute()

        os.unlink(tmp_srt.name)

        caption_id = insert_result.get("id", "?")
        print(f"[captions] Altyazı yüklendi: {video_id} → caption_id={caption_id} ({language})")
        return True

    except Exception as e:
        print(f"[captions] Altyazı yüklenemedi (kritik değil): {e}")
        return False


if __name__ == "__main__":
    import sys
    vid = sys.argv[1] if len(sys.argv) > 1 else input("Video ID: ")
    vtt = sys.argv[2] if len(sys.argv) > 2 else "output/narration.vtt"
    lang = sys.argv[3] if len(sys.argv) > 3 else "en"
    upload_captions(vid, vtt, language=lang)
