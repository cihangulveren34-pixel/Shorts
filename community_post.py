"""
community_post.py — YouTube Community sekmesine otomatik gönderi.

Video yüklendikten sonra Community tab'a "Yeni video çıktı!" gönderisi atar.
Bağlantı, thumbnail ve CTA butonu içerir.

Not: YouTube Data API Community Posts endpoint'i sadece doğrulanmış kanallarda
(10K+ abone) tam olarak çalışır. Küçük kanallarda API erişimi kısıtlıdır.
Bu durumda hata sessizce yakalanır.

Gereksinim: YOUTUBE_TOKEN_JSON
"""

import json
import os
import tempfile

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False


SCOPES = ["https://www.googleapis.com/auth/youtube"]

# Community gönderi şablonları (her video için rastgele seçilir)
POST_TEMPLATES = [
    (
        "🔥 NEW SHORT is LIVE!\n\n"
        "{title}\n\n"
        "{hook}\n\n"
        "👉 Watch now: https://youtube.com/shorts/{video_id}\n\n"
        "💬 What alternate scenario should we cover next? Drop it below! 👇"
    ),
    (
        "⚔️ What would have happened?\n\n"
        "{title}\n\n"
        "New Short is up — watch the full breakdown!\n"
        "🔗 https://youtube.com/shorts/{video_id}\n\n"
        "🔔 Hit the bell to never miss a 'What If' history drop!"
    ),
    (
        "📺 Just dropped: {title}\n\n"
        "{hook}\n\n"
        "Full Short → https://youtube.com/shorts/{video_id}\n\n"
        "#History #WhatIf #Shorts"
    ),
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


def _pick_template(video_id: str) -> str:
    """Video ID hash'ine göre deterministik şablon seç."""
    idx = int(video_id[-1], 36) % len(POST_TEMPLATES)
    return POST_TEMPLATES[idx]


def post_community_update(video_id: str, script: dict) -> bool:
    """
    YouTube Community sekmesine video duyurusu gönderir.

    Args:
        video_id: YouTube video ID
        script: Script dict (title + hook kullanılır)

    Returns:
        True if successful
    """
    if not YOUTUBE_AVAILABLE:
        print("[community] google-api-python-client kurulu değil.")
        return False

    title = script.get("title", "New Video")
    hook = script.get("hook", "Watch our latest history short!")

    template = _pick_template(video_id)
    post_text = template.format(
        title=title,
        hook=hook,
        video_id=video_id,
    )

    try:
        creds = _get_credentials()
        youtube = build("youtube", "v3", credentials=creds)

        # Community post endpoint (postThread)
        result = youtube.postThreads().insert(
            part="id,snippet",
            body={
                "snippet": {
                    "textOriginal": post_text,
                }
            },
        ).execute()

        post_id = result.get("id", "?")
        print(f"[community] Community gönderisi oluşturuldu: {post_id}")
        return True

    except AttributeError:
        # Eski google-api-python-client sürümleri postThreads() desteklemez
        print("[community] postThreads API desteklenmiyor — google-api-python-client güncellemesi gerekebilir.")
        return _fallback_via_commentthread(video_id, post_text)

    except Exception as e:
        # Community API erişimi kanala göre değişir — kritik değil
        print(f"[community] Community gönderisi oluşturulamadı (kritik değil): {e}")
        return False


def _fallback_via_commentthread(video_id: str, text: str) -> bool:
    """
    Community post API çalışmazsa video altına sabitlenmiş yorum atar.
    (Zaten main.py'de post_pinned_comment var — bu sadece fallback)
    """
    try:
        creds = _get_credentials()
        youtube = build("youtube", "v3", credentials=creds)
        youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {"textOriginal": text[:2000]}
                    },
                }
            },
        ).execute()
        print(f"[community] Fallback: Video yorumu eklendi: {video_id}")
        return True
    except Exception as e:
        print(f"[community] Fallback yorum da eklenemedi: {e}")
        return False


def post_poll(question: str, options: list[str]) -> bool:
    """
    YouTube Community anket gönderisi oluşturur.
    (Kanal sahipliği + yeterli abone gerektirir)

    Args:
        question: Anket sorusu
        options: 2-5 seçenek listesi

    Returns:
        True if successful
    """
    if not YOUTUBE_AVAILABLE:
        return False
    if not (2 <= len(options) <= 5):
        print(f"[community] Anket 2-5 seçenek içermelidir (verildi: {len(options)})")
        return False

    try:
        creds = _get_credentials()
        youtube = build("youtube", "v3", credentials=creds)

        result = youtube.postThreads().insert(
            part="id,snippet",
            body={
                "snippet": {
                    "textOriginal": question,
                    "poll": {
                        "options": [{"text": opt} for opt in options]
                    },
                }
            },
        ).execute()

        print(f"[community] Anket gönderildi: {result.get('id', '?')}")
        return True

    except Exception as e:
        print(f"[community] Anket gönderilemedi (kritik değil): {e}")
        return False


def post_weekly_poll(top_topics: list[str]) -> bool:
    """
    Haftanın konusu oylaması — haftalık rapor sonrası çağrılır.
    """
    if not top_topics or len(top_topics) < 2:
        return False

    question = "⚔️ Which 'What If' scenario should we cover this week?"
    options = [t[:80] for t in top_topics[:4]]

    return post_poll(question, options)


if __name__ == "__main__":
    import sys
    vid = sys.argv[1] if len(sys.argv) > 1 else input("Video ID: ")
    test_script = {
        "title": "What if Rome Never Fell?",
        "hook": "The Roman Empire never collapsed — what would 2025 look like?",
    }
    post_community_update(vid, test_script)
