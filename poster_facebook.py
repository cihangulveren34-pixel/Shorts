"""
poster_facebook.py — Facebook sayfasına video Reels gönderisi.

Meta Graph API v21 ile Facebook sayfasına video yükler.
Instagram Reels ile aynı token kullanılabilir (Sayfaya bağlıysa).

Akış:
  1. Video dosyasını chunk'lar halinde yükle (resumable upload)
  2. Video işlenene kadar bekle (polling)
  3. Yayınla (publish)

Gereksinimler (GitHub Secrets):
  FACEBOOK_PAGE_ID         — Facebook Sayfasının ID'si
  FACEBOOK_ACCESS_TOKEN    — Page Access Token (uzun ömürlü)

Token alma:
  developers.facebook.com → App → Tools → Graph API Explorer
  Gerekli izinler: pages_manage_posts, pages_read_engagement, publish_video
"""

import os
import time
import json

import requests

TIMEOUT = 30
CHUNK_SIZE = 10 * 1024 * 1024   # 10 MB
MAX_POLL_ATTEMPTS = 24           # 4 dakika (her 10s)
GRAPH_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"


def _check_credentials() -> bool:
    required = ["FACEBOOK_PAGE_ID", "FACEBOOK_ACCESS_TOKEN"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"[facebook] Eksik env değişkeni: {missing}. Facebook atlandı.")
        return False
    return True


def _init_video_upload(page_id: str, token: str, file_size: int, title: str) -> str:
    """Resumable video upload başlatır ve upload_session_id döndürür."""
    resp = requests.post(
        f"{BASE_URL}/{page_id}/video_reels",
        data={
            "upload_phase": "start",
            "access_token": token,
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    upload_url = data.get("upload_url") or data.get("video_id")
    session_id = data.get("upload_session_id") or data.get("video_id")
    return session_id, data.get("upload_url", "")


def _upload_chunks(upload_url: str, token: str, video_path: str) -> bool:
    """Video dosyasını chunk'lar halinde yükler."""
    file_size = os.path.getsize(video_path)
    offset = 0

    with open(video_path, "rb") as f:
        while offset < file_size:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break

            headers = {
                "Authorization": f"OAuth {token}",
                "offset": str(offset),
                "file_size": str(file_size),
            }
            resp = requests.post(
                upload_url,
                headers=headers,
                data=chunk,
                timeout=120,
            )
            if resp.status_code not in (200, 201):
                print(f"[facebook] Chunk yükleme hatası: {resp.status_code} — {resp.text[:200]}")
                return False

            offset += len(chunk)
            pct = int(offset / file_size * 100)
            print(f"[facebook] Yükleniyor: %{pct}")

    return True


def _finish_upload(page_id: str, token: str, session_id: str,
                   description: str, title: str) -> str | None:
    """Upload'ı tamamlar ve video_id döndürür."""
    resp = requests.post(
        f"{BASE_URL}/{page_id}/video_reels",
        data={
            "upload_phase": "finish",
            "upload_session_id": session_id,
            "access_token": token,
            "description": description,
            "title": title,
            "video_state": "PUBLISHED",
        },
        timeout=TIMEOUT,
    )
    if resp.status_code in (200, 201):
        data = resp.json()
        return data.get("video_id") or data.get("id")
    print(f"[facebook] Finish hatası: {resp.status_code} — {resp.text[:200]}")
    return None


def _post_simple_video(page_id: str, token: str,
                       video_path: str, description: str, title: str) -> str | None:
    """
    Basit (non-chunked) video yükleme — küçük dosyalar için.
    """
    with open(video_path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/{page_id}/videos",
            data={
                "access_token": token,
                "description": description,
                "title": title,
            },
            files={"source": f},
            timeout=300,
        )
    if resp.status_code in (200, 201):
        return resp.json().get("id")
    print(f"[facebook] Video yükleme hatası: {resp.status_code} — {resp.text[:300]}")
    return None


def _build_description(script: dict, video_id: str) -> str:
    """Facebook gönderisi için açıklama oluşturur."""
    title = script.get("title", "")
    hook = script.get("hook", "")
    tags = script.get("tags", [])
    yt_url = f"https://youtube.com/shorts/{video_id}" if video_id else ""

    hashtags = " ".join(f"#{t}" for t in tags[:6] if t.isalpha())
    lines = [
        f"⚔️ {title}",
        "",
        hook,
        "",
    ]
    if yt_url:
        lines.append(f"🎬 Full video: {yt_url}")
    lines.append("")
    lines.append(hashtags)
    return "\n".join(lines)[:2000]  # Facebook açıklama limiti


def post_reel(video_path: str, script: dict, youtube_video_id: str = "") -> bool:
    """
    Facebook sayfasına video Reels olarak yükler.

    Args:
        video_path: MP4 dosya yolu
        script: Script dict
        youtube_video_id: YouTube video ID (açıklamada link için)

    Returns:
        True if successful
    """
    if not _check_credentials():
        return False

    page_id = os.environ["FACEBOOK_PAGE_ID"]
    token = os.environ["FACEBOOK_ACCESS_TOKEN"]
    title = script.get("title", "WAR SHORTS")
    description = _build_description(script, youtube_video_id)

    file_size = os.path.getsize(video_path)
    print(f"[facebook] Video yükleniyor: {file_size / 1024 / 1024:.1f} MB")

    try:
        # 50 MB altı → basit yükleme; üstü → chunked
        if file_size < 50 * 1024 * 1024:
            video_id = _post_simple_video(page_id, token, video_path, description, title)
        else:
            session_id, upload_url = _init_video_upload(page_id, token, file_size, title)
            if not upload_url:
                print("[facebook] Upload URL alınamadı.")
                return False
            if not _upload_chunks(upload_url, token, video_path):
                return False
            video_id = _finish_upload(page_id, token, session_id, description, title)

        if video_id:
            print(f"[facebook] Video yüklendi: {video_id}")
            print(f"[facebook] Sayfa: https://www.facebook.com/{page_id}/videos/{video_id}")
            return True

        return False

    except requests.exceptions.RequestException as e:
        print(f"[facebook] İstek hatası: {e}")
        return False
    except Exception as e:
        print(f"[facebook] Beklenmedik hata: {e}")
        return False


if __name__ == "__main__":
    import sys
    vp = sys.argv[1] if len(sys.argv) > 1 else "output/short.mp4"
    test_script = {
        "title": "What if Rome Never Fell?",
        "hook": "The Roman Empire never collapsed — what would 2025 look like?",
        "tags": ["rome", "history", "whatif", "war"],
    }
    post_reel(vp, test_script, "test_yt_id")
