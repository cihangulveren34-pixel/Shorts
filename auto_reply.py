"""
auto_reply.py — Gemini ile YouTube yorumlarına otomatik yanıt.

Son N saatteki yorumları çeker, Gemini ile bağlama uygun kısa yanıtlar
üretir ve YouTube API ile yayınlar.

Strateji:
  - Soru içeren yorumlara öncelik verilir
  - Spam/negatif yorumlar atlanır
  - Aynı yoruma iki kez yanıt verilmez (state dosyası)
  - Günlük yanıt limiti aşılmaz (YouTube kota koruması)

Gereksinimler:
  GEMINI_API_KEY    — Script gen ile aynı key
  YOUTUBE_TOKEN_JSON
"""

import json
import os
import re
import tempfile
from datetime import datetime, timezone, timedelta

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False


SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
REPLIED_STATE_PATH = "output/replied_comments.json"
DAILY_REPLY_LIMIT = 20      # YouTube kota koruması
LOOKBACK_HOURS = 48         # Son kaç saatin yorumlarına yanıt verilecek
MIN_COMMENT_LEN = 10        # Çok kısa yorumları atla

# Spam / olumsuz içerik filtreleri
SPAM_PATTERNS = [
    r"sub4sub", r"check.?out.?my", r"follow.?me", r"www\.", r"http",
    r"😂{3,}", r"!!!{3,}", r"click.?here",
]

NEGATIVE_WORDS = [
    "hate", "stupid", "trash", "garbage", "worst", "terrible",
    "boring", "dumb", "idiot", "fake",
]

SYSTEM_PROMPT = """You are a friendly, knowledgeable YouTube content creator specializing in
alternate history and war history. Reply to viewer comments on your YouTube Shorts in a warm,
engaging, and educational tone.

Rules:
- Keep replies under 150 characters
- Be enthusiastic and encouraging
- If it's a question, answer briefly or say you'll cover it in a future video
- Use 1-2 relevant emojis naturally
- Never be sarcastic or negative
- Don't mention you're an AI
- Reply in the same language as the comment"""


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


def _load_replied_state() -> dict:
    os.makedirs("output", exist_ok=True)
    if os.path.exists(REPLIED_STATE_PATH):
        with open(REPLIED_STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"replied_ids": [], "daily_count": 0, "last_reset": None}


def _save_replied_state(state: dict) -> None:
    with open(REPLIED_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _reset_daily_count_if_needed(state: dict) -> dict:
    today = datetime.now(timezone.utc).date().isoformat()
    if state.get("last_reset") != today:
        state["daily_count"] = 0
        state["last_reset"] = today
    return state


def _is_spam(text: str) -> bool:
    lower = text.lower()
    for pattern in SPAM_PATTERNS:
        if re.search(pattern, lower):
            return True
    for word in NEGATIVE_WORDS:
        if word in lower:
            return True
    return False


def _is_question_or_engaging(text: str) -> bool:
    """Yorum soru mu ya da ilgi çekici mi?"""
    return (
        "?" in text or
        any(w in text.lower() for w in ["what", "why", "how", "when", "who", "which",
                                          "could", "would", "should", "think", "love",
                                          "great", "amazing", "awesome", "interesting"])
    )


def _fetch_recent_comments(youtube, video_id: str, hours: int = LOOKBACK_HOURS) -> list[dict]:
    """Videonun son N saatteki yorumlarını getirir."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    comments = []
    try:
        page_token = None
        while len(comments) < 50:
            kwargs = {
                "part": "snippet",
                "videoId": video_id,
                "order": "time",
                "maxResults": 20,
                "textFormat": "plainText",
            }
            if page_token:
                kwargs["pageToken"] = page_token

            resp = youtube.commentThreads().list(**kwargs).execute()

            for item in resp.get("items", []):
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                published = datetime.fromisoformat(
                    snippet["publishedAt"].replace("Z", "+00:00")
                )
                if published < cutoff:
                    return comments  # Zaman sınırına ulaşıldı

                comments.append({
                    "comment_id": item["id"],
                    "text": snippet["textDisplay"],
                    "author": snippet["authorDisplayName"],
                    "published_at": snippet["publishedAt"],
                    "like_count": snippet.get("likeCount", 0),
                })

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    except Exception as e:
        print(f"[auto_reply] Yorumlar alınamadı: {e}")

    return comments


def _generate_reply(comment_text: str, video_title: str) -> str:
    """Gemini ile bağlama uygun yanıt üretir."""
    if not GEMINI_AVAILABLE:
        return ""

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return ""

    try:
        client = genai.Client(api_key=api_key)
        prompt = f'Video: "{video_title}"\nComment: "{comment_text}"\n\nReply:'
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=80,
                temperature=0.7,
            ),
        )
        reply = response.text.strip().strip('"')
        # 150 karakter limiti
        if len(reply) > 150:
            reply = reply[:147] + "..."
        return reply
    except Exception as e:
        print(f"[auto_reply] Gemini yanıt üretemedi: {e}")
        return ""


def _post_reply(youtube, parent_comment_id: str, reply_text: str) -> bool:
    """YouTube'a yanıt yazar."""
    try:
        youtube.comments().insert(
            part="snippet",
            body={
                "snippet": {
                    "parentId": parent_comment_id,
                    "textOriginal": reply_text,
                }
            },
        ).execute()
        return True
    except Exception as e:
        print(f"[auto_reply] Yanıt gönderilemedi: {e}")
        return False


def reply_to_comments(video_id: str, video_title: str = "") -> dict:
    """
    Ana fonksiyon: son 48 saatin yorumlarına Gemini ile yanıt verir.

    Returns:
        {"replied": int, "skipped": int, "errors": int}
    """
    if not YOUTUBE_AVAILABLE or not GEMINI_AVAILABLE:
        print("[auto_reply] Gerekli kütüphaneler eksik.")
        return {}

    state = _load_replied_state()
    state = _reset_daily_count_if_needed(state)
    replied_set = set(state.get("replied_ids", []))

    if state["daily_count"] >= DAILY_REPLY_LIMIT:
        print(f"[auto_reply] Günlük limit ({DAILY_REPLY_LIMIT}) doldu, atlanıyor.")
        return {"replied": 0, "skipped": 0, "errors": 0}

    try:
        creds = _get_credentials()
        youtube = build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"[auto_reply] YouTube bağlantısı kurulamadı: {e}")
        return {}

    comments = _fetch_recent_comments(youtube, video_id)
    print(f"[auto_reply] {len(comments)} yorum bulundu (son {LOOKBACK_HOURS}s)")

    stats = {"replied": 0, "skipped": 0, "errors": 0}

    # Önce sorular + beğenili yorumlar
    comments.sort(key=lambda c: (
        -int(_is_question_or_engaging(c["text"])),
        -c["like_count"]
    ))

    for comment in comments:
        if state["daily_count"] >= DAILY_REPLY_LIMIT:
            print("[auto_reply] Günlük limit doldu.")
            break

        cid = comment["comment_id"]
        text = comment["text"]

        # Zaten yanıtlandı mı?
        if cid in replied_set:
            stats["skipped"] += 1
            continue

        # Çok kısa veya spam?
        if len(text) < MIN_COMMENT_LEN or _is_spam(text):
            stats["skipped"] += 1
            continue

        # Yanıt üret
        reply = _generate_reply(text, video_title)
        if not reply:
            stats["errors"] += 1
            continue

        # Gönder
        if _post_reply(youtube, cid, reply):
            replied_set.add(cid)
            state["daily_count"] += 1
            stats["replied"] += 1
            print(f"[auto_reply] ✓ @{comment['author'][:20]}: {reply[:60]}...")
        else:
            stats["errors"] += 1

    # State kaydet
    state["replied_ids"] = list(replied_set)[-200:]  # Son 200'ü tut
    _save_replied_state(state)

    print(f"[auto_reply] Tamamlandı: {stats['replied']} yanıt, {stats['skipped']} atlandı")
    return stats


if __name__ == "__main__":
    import sys
    vid = sys.argv[1] if len(sys.argv) > 1 else input("Video ID: ")
    title = sys.argv[2] if len(sys.argv) > 2 else "What if Rome Never Fell?"
    result = reply_to_comments(vid, title)
    print(result)
