"""
poster_tiktok.py — TikTok Content Posting API v2 ile video cross-post.

Gereksinimler:
  - TikTok Developer hesabı (developer.tiktok.com — ücretsiz)
  - Content Posting API erişimi (başvuru gerekli, genellikle onaylanır)
  - TIKTOK_ACCESS_TOKEN  (OAuth2 token)

TikTok 2 yükleme modu destekler:
  - FILE_UPLOAD: doğrudan dosya yükleme (tercih edilir)
  - PULL_FROM_URL: URL'den çekme
"""

import os
import math
import requests


TIKTOK_API = "https://open.tiktokapis.com/v2"
CHUNK_SIZE = 10 * 1024 * 1024   # 10 MB chunk
TIMEOUT = 60


def _get_token() -> str:
    token = os.environ.get("TIKTOK_ACCESS_TOKEN")
    if not token:
        raise EnvironmentError("TIKTOK_ACCESS_TOKEN eksik.")
    return token


def _get_creator_info(token: str) -> dict:
    """Hesabın izin verilen gizlilik/yorum ayarlarını döndürür."""
    resp = requests.post(
        f"{TIKTOK_API}/post/publish/creator_info/query/",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("data", {})


def _init_upload(token: str, video_size: int, title: str) -> dict:
    """Upload oturumu başlatır. publish_id ve upload_url döndürür."""
    chunk_count = math.ceil(video_size / CHUNK_SIZE)

    resp = requests.post(
        f"{TIKTOK_API}/post/publish/video/init/",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={
            "post_info": {
                "title": title[:150],
                "privacy_level": "PUBLIC_TO_EVERYONE",
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": CHUNK_SIZE,
                "total_chunk_count": chunk_count,
            },
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json().get("data", {})
    return data


def _upload_chunks(upload_url: str, video_path: str) -> None:
    """Videoyu chunk'lar halinde yükler."""
    video_size = os.path.getsize(video_path)
    chunk_count = math.ceil(video_size / CHUNK_SIZE)

    with open(video_path, "rb") as f:
        for i in range(chunk_count):
            chunk = f.read(CHUNK_SIZE)
            start = i * CHUNK_SIZE
            end = min(start + len(chunk) - 1, video_size - 1)

            resp = requests.put(
                upload_url,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{video_size}",
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(chunk)),
                },
                data=chunk,
                timeout=120,
            )
            resp.raise_for_status()
            print(f"[tiktok] Chunk {i+1}/{chunk_count} yüklendi.")


def post_video(video_path: str, title: str) -> str | None:
    """
    TikTok'a video yükler. publish_id döndürür.
    """
    try:
        token = _get_token()
        video_size = os.path.getsize(video_path)

        print(f"[tiktok] Upload başlatılıyor ({video_size/1024/1024:.1f} MB)...")
        init_data = _init_upload(token, video_size, title)
        publish_id = init_data.get("publish_id")
        upload_url = init_data.get("upload_url")

        if not publish_id or not upload_url:
            raise RuntimeError(f"TikTok init yanıtı geçersiz: {init_data}")

        _upload_chunks(upload_url, video_path)

        print(f"[tiktok] Video yüklendi! Publish ID: {publish_id}")
        print(f"[tiktok] TikTok'ta işleniyor (1-3 dk)...")
        return publish_id

    except Exception as e:
        print(f"[tiktok] Hata (kritik değil): {e}")
        return None


def build_title(script: dict) -> str:
    tags = " ".join(f"#{t}" for t in script.get("tags", []))
    return f"{script['title']} {tags} #WhatIf #HistoryTikTok #Shorts"


if __name__ == "__main__":
    import json, sys

    script_path = sys.argv[1] if len(sys.argv) > 1 else "output/script.json"
    video_path = sys.argv[2] if len(sys.argv) > 2 else "output/short.mp4"

    with open(script_path, encoding="utf-8") as f:
        script = json.load(f)

    post_video(video_path, build_title(script))
