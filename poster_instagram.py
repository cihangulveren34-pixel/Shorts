"""
poster_instagram.py — Instagram Graph API ile Reels cross-post.

Gereksinimler:
  - Instagram Business veya Creator hesabı
  - Facebook Developer App (ücretsiz)
  - INSTAGRAM_ACCESS_TOKEN  (uzun süreli token, ~60 gün)
  - INSTAGRAM_USER_ID       (sayısal Instagram kullanıcı ID'si)

Not: Instagram video'yu bir URL'den çektiği için, video dosyasını
önce geçici olarak erişilebilir bir URL'e yüklemek gerekir.
Ücretsiz çözüm: GitHub Release asset URL'si kullanılır (Actions'ta otomatik).
"""

import os
import time
import requests


GRAPH_API = "https://graph.instagram.com/v21.0"
TIMEOUT = 30


def _get_creds() -> tuple[str, str]:
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    user_id = os.environ.get("INSTAGRAM_USER_ID")
    if not token or not user_id:
        raise EnvironmentError(
            "INSTAGRAM_ACCESS_TOKEN veya INSTAGRAM_USER_ID eksik."
        )
    return token, user_id


def _upload_to_github_release(video_path: str) -> str:
    """
    Video dosyasını GitHub Release'e yükler ve indirilebilir URL döndürür.
    GitHub Actions'ta GITHUB_TOKEN ve GITHUB_REPOSITORY otomatik set edilir.
    """
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID", "manual")

    if not token or not repo:
        raise EnvironmentError("GITHUB_TOKEN veya GITHUB_REPOSITORY eksik.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Release oluştur (varsa atla)
    tag = f"video-{run_id}"
    release_resp = requests.post(
        f"https://api.github.com/repos/{repo}/releases",
        headers=headers,
        json={"tag_name": tag, "name": f"Video {run_id}", "draft": False, "prerelease": True},
        timeout=TIMEOUT,
    )

    if release_resp.status_code == 422:
        # Release zaten var, bul
        existing = requests.get(
            f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
            headers=headers, timeout=TIMEOUT
        ).json()
        upload_url = existing["upload_url"].split("{")[0]
        release_id = existing["id"]
    else:
        release_resp.raise_for_status()
        upload_url = release_resp.json()["upload_url"].split("{")[0]
        release_id = release_resp.json()["id"]

    # Asset yükle
    filename = os.path.basename(video_path)
    with open(video_path, "rb") as f:
        asset_resp = requests.post(
            f"{upload_url}?name={filename}",
            headers={**headers, "Content-Type": "video/mp4"},
            data=f,
            timeout=120,
        )
    asset_resp.raise_for_status()
    return asset_resp.json()["browser_download_url"]


def post_reel(
    video_path: str,
    caption: str,
    video_url: str = None,
    share_to_feed: bool = True,
) -> str | None:
    """
    Instagram Reels olarak video yayınlar. Media ID döndürür.

    video_url: Video dosyasının herkese açık URL'si.
               None ise GitHub Release'e yüklenerek otomatik alınır.
    """
    try:
        access_token, user_id = _get_creds()

        # 1) Video URL'si al
        if not video_url:
            print("[instagram] Video GitHub Release'e yükleniyor...")
            video_url = _upload_to_github_release(video_path)
            print(f"[instagram] Video URL: {video_url[:60]}...")

        # 2) Media container oluştur
        print("[instagram] Reels container oluşturuluyor...")
        container_resp = requests.post(
            f"{GRAPH_API}/{user_id}/media",
            params={
                "access_token": access_token,
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "share_to_feed": str(share_to_feed).lower(),
            },
            timeout=TIMEOUT,
        )
        container_resp.raise_for_status()
        container_id = container_resp.json()["id"]
        print(f"[instagram] Container ID: {container_id}")

        # 3) İşleme tamamlanana kadar bekle (max 3 dakika)
        for attempt in range(18):
            time.sleep(10)
            status_resp = requests.get(
                f"{GRAPH_API}/{container_id}",
                params={
                    "access_token": access_token,
                    "fields": "status_code,status",
                },
                timeout=TIMEOUT,
            ).json()
            status = status_resp.get("status_code", "")
            print(f"[instagram] İşleme durumu: {status} ({attempt+1}/18)")
            if status == "FINISHED":
                break
            if status == "ERROR":
                raise RuntimeError(f"Instagram işleme hatası: {status_resp}")
        else:
            raise TimeoutError("Instagram video işleme zaman aşımına uğradı.")

        # 4) Yayınla
        print("[instagram] Reel yayınlanıyor...")
        publish_resp = requests.post(
            f"{GRAPH_API}/{user_id}/media_publish",
            params={
                "access_token": access_token,
                "creation_id": container_id,
            },
            timeout=TIMEOUT,
        )
        publish_resp.raise_for_status()
        media_id = publish_resp.json()["id"]
        print(f"[instagram] Reel yayınlandı! Media ID: {media_id}")
        return media_id

    except Exception as e:
        print(f"[instagram] Hata (kritik değil): {e}")
        return None


def build_caption(script: dict) -> str:
    tags = " ".join(f"#{t}" for t in script.get("tags", []))
    return (
        f"{script['hook']}\n\n"
        f"{script['title']}\n\n"
        f"Follow for daily history what-ifs! 🏛️⚔️\n\n"
        f"{tags} #Reels #HistoryReels #WhatIf #WarHistory"
    )


if __name__ == "__main__":
    import json, sys

    script_path = sys.argv[1] if len(sys.argv) > 1 else "output/script.json"
    video_path = sys.argv[2] if len(sys.argv) > 2 else "output/short.mp4"

    with open(script_path, encoding="utf-8") as f:
        script = json.load(f)

    post_reel(video_path, build_caption(script))
