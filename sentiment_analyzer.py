"""
sentiment_analyzer.py — İzleyici yorum duygu analizi ve içerik stratejisi.

YouTube yorumlarından izleyici duygusunu ve taleplerini analiz eder:
  1. Genel duygu skoru (pozitif/negatif/nötr)
  2. En çok talep edilen konular
  3. İzleyici memnuniyet trendi
  4. "Daha fazla X istiyoruz" kalıpları
  5. İçerik stratejisi önerileri

Gemini API ile derin duygu analizi + kural tabanlı hızlı analiz.

Rakip avantajı: İzleyicinin ne istediğini veriye dayalı anlayarak
içerik stratejisini sürekli optimize ediyoruz.
"""

import json
import os
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

import requests

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False


SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
SENTIMENT_PATH = "output/sentiment_report.json"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


@dataclass
class SentimentReport:
    """Yorum duygu analizi raporu."""
    total_comments: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    avg_sentiment: float = 0.0          # -1.0 ~ +1.0
    top_requests: list[str] = field(default_factory=list)
    top_praised: list[str] = field(default_factory=list)
    top_complaints: list[str] = field(default_factory=list)
    content_suggestions: list[str] = field(default_factory=list)

    @property
    def sentiment_label(self) -> str:
        if self.avg_sentiment > 0.3:
            return "VERY_POSITIVE"
        if self.avg_sentiment > 0.1:
            return "POSITIVE"
        if self.avg_sentiment > -0.1:
            return "NEUTRAL"
        if self.avg_sentiment > -0.3:
            return "NEGATIVE"
        return "VERY_NEGATIVE"

    def summary(self) -> str:
        total = self.total_comments
        pos_pct = (self.positive_count / total * 100) if total else 0
        neg_pct = (self.negative_count / total * 100) if total else 0
        return (
            f"Duygu Analizi: {self.sentiment_label} ({self.avg_sentiment:+.2f})\n"
            f"  Toplam: {total} yorum | "
            f"Pozitif: {self.positive_count} ({pos_pct:.0f}%) | "
            f"Negatif: {self.negative_count} ({neg_pct:.0f}%)\n"
            f"  Talepler: {', '.join(self.top_requests[:3]) if self.top_requests else '—'}\n"
            f"  Övgüler: {', '.join(self.top_praised[:3]) if self.top_praised else '—'}\n"
            f"  Şikayetler: {', '.join(self.top_complaints[:3]) if self.top_complaints else '—'}"
        )


# ─── Kural Tabanlı Hızlı Duygu Tespiti ───────────────────────────────────────

POSITIVE_WORDS = {
    "love", "amazing", "awesome", "great", "excellent", "perfect", "best",
    "incredible", "fantastic", "insane", "fire", "goat", "legend", "bro",
    "based", "w", "underrated", "quality", "more", "keep",
    "harika", "mükemmel", "süper", "muhteşem", "efsane", "devam",
}

NEGATIVE_WORDS = {
    "hate", "terrible", "worst", "bad", "boring", "trash", "garbage",
    "fake", "cringe", "lame", "mid", "ratio", "l", "cap",
    "kötü", "saçma", "sıkıcı", "yanlış", "hata",
}

REQUEST_PATTERNS = [
    r"(?:do|make|cover|video about|talk about|please do)\s+(.{5,40})",
    r"(?:can you|could you|pls|please)\s+(?:do|make|cover)\s+(.{5,40})",
    r"(?:more|moar)\s+(.{3,30})\s*(?:please|pls|!)?",
    r"(?:what about|how about)\s+(.{5,40})\??",
    r"(?:we need|i want|i'd love)\s+(.{5,40})",
    r"(?:part|bölüm)\s*(\d+)\s*(?:when|ne zaman)?",
]


def _quick_sentiment(text: str) -> float:
    """Kural tabanlı hızlı duygu skoru: -1.0 ~ +1.0"""
    lower = text.lower()
    words = set(re.findall(r"\b\w+\b", lower))

    pos = len(words & POSITIVE_WORDS)
    neg = len(words & NEGATIVE_WORDS)

    # Emoji analizi
    pos_emojis = len(re.findall(r"[❤️🔥💪👑🎯✅💯🙏👍😍🫡]", text))
    neg_emojis = len(re.findall(r"[💀😡🤮👎😤🚫❌]", text))

    total_signals = pos + neg + pos_emojis + neg_emojis
    if total_signals == 0:
        return 0.0

    return ((pos + pos_emojis) - (neg + neg_emojis)) / total_signals


def _extract_requests(comments: list[dict]) -> list[str]:
    """Yorumlardan konu talepleri çıkarır."""
    requests_found = []
    for c in comments:
        text = c.get("text", "")
        for pattern in REQUEST_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            requests_found.extend(matches)

    # En çok tekrarlanan talepleri bul
    if not requests_found:
        return []

    # Normalize et
    normalized = [r.strip().lower() for r in requests_found if len(r.strip()) > 3]
    counter = Counter(normalized)
    return [req for req, count in counter.most_common(10)]


# ─── YouTube Yorum Çekme ─────────────────────────────────────────────────────

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


def _fetch_all_recent_comments(youtube, days: int = 7, max_comments: int = 200) -> list[dict]:
    """Kanalın son N günündeki tüm video yorumlarını çeker."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    all_comments = []

    # Son videoları bul
    try:
        search_resp = youtube.search().list(
            part="id",
            forMine=True,
            type="video",
            order="date",
            maxResults=15,
        ).execute()

        video_ids = [item["id"]["videoId"] for item in search_resp.get("items", [])]
    except Exception as e:
        print(f"[sentiment] Video listesi alınamadı: {e}")
        return []

    for vid_id in video_ids:
        if len(all_comments) >= max_comments:
            break

        try:
            resp = youtube.commentThreads().list(
                part="snippet",
                videoId=vid_id,
                order="time",
                maxResults=50,
                textFormat="plainText",
            ).execute()

            for item in resp.get("items", []):
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                published = datetime.fromisoformat(
                    snippet["publishedAt"].replace("Z", "+00:00")
                )
                if published < cutoff:
                    break

                all_comments.append({
                    "video_id": vid_id,
                    "text": snippet["textDisplay"],
                    "author": snippet["authorDisplayName"],
                    "like_count": snippet.get("likeCount", 0),
                    "published_at": snippet["publishedAt"],
                })

        except Exception as e:
            print(f"[sentiment] Yorum çekme hatası ({vid_id}): {e}")
            continue

    return all_comments


# ─── Gemini Derin Analiz ──────────────────────────────────────────────────────

def _gemini_deep_analysis(comments_text: str) -> dict:
    """Gemini ile derin yorum analizi."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {}

    system = """You analyze YouTube comments for a military/geopolitics channel.
Identify:
1. What topics viewers want MORE of
2. What they praise most
3. What they complain about
4. Content strategy recommendations

Reply in JSON:
{
  "top_requests": ["topic1", "topic2", "topic3"],
  "top_praised": ["aspect1", "aspect2"],
  "top_complaints": ["issue1", "issue2"],
  "suggestions": ["suggestion1", "suggestion2", "suggestion3"]
}"""

    prompt = f"Analyze these {len(comments_text.splitlines())} YouTube comments:\n\n{comments_text[:3000]}"

    url = f"{GEMINI_API_URL.format(model='gemini-2.5-flash-lite')}?key={api_key}"
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 300,
            "temperature": 0.3,
        },
    }

    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group(0))
    except Exception as e:
        print(f"[sentiment] Gemini analiz hatası: {e}")

    return {}


# ─── Ana Fonksiyon ────────────────────────────────────────────────────────────

def analyze_sentiment(days: int = 7) -> SentimentReport:
    """
    Son N günün yorumlarını analiz eder ve rapor üretir.

    Returns:
        SentimentReport
    """
    report = SentimentReport()

    if not YOUTUBE_AVAILABLE:
        print("[sentiment] YouTube API kullanılamıyor.")
        return report

    try:
        creds = _get_credentials()
        youtube = build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"[sentiment] API bağlantısı kurulamadı: {e}")
        return report

    print(f"[sentiment] Son {days} günün yorumları analiz ediliyor...")
    comments = _fetch_all_recent_comments(youtube, days=days)
    report.total_comments = len(comments)

    if not comments:
        print("[sentiment] Analiz edilecek yorum yok.")
        return report

    # Kural tabanlı hızlı analiz
    sentiments = []
    for c in comments:
        score = _quick_sentiment(c["text"])
        sentiments.append(score)
        if score > 0.15:
            report.positive_count += 1
        elif score < -0.15:
            report.negative_count += 1
        else:
            report.neutral_count += 1

    report.avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0

    # Kural tabanlı talep çıkarma
    report.top_requests = _extract_requests(comments)

    # Gemini derin analiz
    comments_text = "\n".join(f"- {c['text'][:100]}" for c in comments[:50])
    gemini_insights = _gemini_deep_analysis(comments_text)

    if gemini_insights:
        # Gemini sonuçlarını birleştir
        report.top_requests = list(dict.fromkeys(
            gemini_insights.get("top_requests", []) + report.top_requests
        ))[:10]
        report.top_praised = gemini_insights.get("top_praised", [])
        report.top_complaints = gemini_insights.get("top_complaints", [])
        report.content_suggestions = gemini_insights.get("suggestions", [])

    # Kaydet
    _save_report(report)

    print(f"[sentiment] ✅ Analiz tamamlandı:")
    print(report.summary())

    return report


def _save_report(report: SentimentReport) -> None:
    """Raporu dosyaya kaydeder."""
    os.makedirs("output", exist_ok=True)
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_comments": report.total_comments,
        "positive_count": report.positive_count,
        "negative_count": report.negative_count,
        "neutral_count": report.neutral_count,
        "avg_sentiment": report.avg_sentiment,
        "sentiment_label": report.sentiment_label,
        "top_requests": report.top_requests,
        "top_praised": report.top_praised,
        "top_complaints": report.top_complaints,
        "content_suggestions": report.content_suggestions,
    }
    with open(SENTIMENT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[sentiment] Rapor kaydedildi: {SENTIMENT_PATH}")


def load_content_suggestions() -> list[str]:
    """
    Önceki sentiment analizinden içerik önerilerini yükler.
    script_gen.py veya topic_selector.py tarafından kullanılabilir.
    """
    if os.path.exists(SENTIMENT_PATH):
        try:
            with open(SENTIMENT_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("content_suggestions", []) + data.get("top_requests", [])
        except Exception:
            pass
    return []


def get_audience_mood() -> str:
    """
    Mevcut izleyici duygusunu döndürür.
    Script üretiminde mood seçimi için kullanılabilir.
    """
    if os.path.exists(SENTIMENT_PATH):
        try:
            with open(SENTIMENT_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("sentiment_label", "NEUTRAL")
        except Exception:
            pass
    return "NEUTRAL"


def notify_sentiment_report(report: SentimentReport) -> None:
    """Duygu analizi raporunu Telegram/Discord'a gönderir."""
    msg = f"📊 *İzleyici Duygu Analizi*\n\n{report.summary()}"

    if report.content_suggestions:
        msg += "\n\n💡 *İçerik Önerileri:*"
        for s in report.content_suggestions[:3]:
            msg += f"\n  • {s}"

    try:
        from notifier import _send
        _send(msg)
    except Exception:
        pass

    try:
        from discord_notify import _post
        _post({
            "embeds": [{
                "title": "📊 İzleyici Duygu Analizi",
                "color": 0x3498DB,
                "description": report.summary(),
                "footer": {"text": f"{report.total_comments} yorum analiz edildi"},
            }]
        })
    except Exception:
        pass


if __name__ == "__main__":
    report = analyze_sentiment(days=7)
    print(f"\n{'='*50}")
    print(report.summary())
    if report.content_suggestions:
        print("\nİçerik Önerileri:")
        for s in report.content_suggestions:
            print(f"  • {s}")
