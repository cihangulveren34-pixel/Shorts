"""
hashtag_optimizer.py — Trending hashtag araştırması ve YouTube açıklama SEO optimizasyonu.

YouTube Search API + pytrends ile popüler hashtag'leri bulur,
video açıklamasını SEO dostu hale getirir.
"""

import os
import re
import time
from typing import Optional

import requests

try:
    from pytrends.request import TrendReq
    PYTRENDS_AVAILABLE = True
except ImportError:
    PYTRENDS_AVAILABLE = False

# YouTube Data API için
try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    import json, tempfile
    YOUTUBE_API_AVAILABLE = True
except ImportError:
    YOUTUBE_API_AVAILABLE = False


# Savaş/tarih temasına uygun temel hashtag'ler (fallback)
BASE_HASHTAGS = [
    "Shorts", "History", "WhatIf", "WarHistory", "AlternateHistory",
    "HistoryFacts", "AncientHistory", "WorldWar", "MilitaryHistory",
    "HistoricalFacts", "LearnHistory", "HistoryLovers", "WhatIfHistory",
    "BattleHistory", "HistoryNerd",
]

# Trend aramasında kullanılan kelimeler
TREND_KEYWORDS = [
    "history", "war history", "what if history", "ancient rome",
    "world war", "military history", "alternate history",
]


def _get_trending_hashtags_pytrends(topic: str, region: str = "US") -> list[str]:
    """pytrends ile ilgili trend aramaları alır, hashtag formatına çevirir."""
    if not PYTRENDS_AVAILABLE:
        return []
    try:
        pt = TrendReq(hl="en-US", tz=0, timeout=(10, 25))
        # Konuyla ilgili 3 kelimeyi birleştir
        keywords = [topic[:100], "war history", "what if"]
        pt.build_payload(keywords[:3], cat=0, timeframe="now 7-d", geo=region)
        related = pt.related_queries()

        hashtags = []
        for kw in keywords[:3]:
            if kw in related and related[kw]["top"] is not None:
                top_df = related[kw]["top"]
                for _, row in top_df.head(5).iterrows():
                    term = str(row.get("query", ""))
                    if term:
                        tag = re.sub(r"[^a-zA-Z0-9]", "", term.title().replace(" ", ""))
                        if 3 <= len(tag) <= 30:
                            hashtags.append(tag)
        return list(dict.fromkeys(hashtags))[:10]  # dedup + ilk 10
    except Exception as e:
        print(f"[hashtag] pytrends hatası: {e}")
        return []


def _get_youtube_search_hashtags(topic: str, api_key: str) -> list[str]:
    """YouTube Search API ile ilgili video başlıklarından hashtag çıkarır."""
    try:
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "q": f"{topic} history shorts",
            "type": "video",
            "videoDuration": "short",
            "order": "relevance",
            "maxResults": 10,
            "key": api_key,
        }
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            return []

        data = resp.json()
        hashtags = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            # Başlık ve açıklamadan hashtag'leri çıkar
            text = snippet.get("title", "") + " " + snippet.get("description", "")
            found = re.findall(r"#(\w{2,25})", text)
            hashtags.extend(found)

        # Frekansa göre sırala
        from collections import Counter
        counts = Counter(hashtags)
        return [tag for tag, _ in counts.most_common(15)]
    except Exception as e:
        print(f"[hashtag] YouTube search hatası: {e}")
        return []


def get_trending_hashtags(topic: str, script_tags: list[str] = None) -> list[str]:
    """
    Konu ile ilgili trend hashtag'leri toplar ve önceliklendirir.
    Returns: ['Shorts', 'History', ...] — # prefix olmadan, max 30 tag
    """
    all_tags = []

    # 1) Script'ten gelen taglar en yüksek öncelik
    if script_tags:
        for t in script_tags:
            cleaned = re.sub(r"[^a-zA-Z0-9]", "", t.title().replace(" ", ""))
            if cleaned:
                all_tags.append(cleaned)

    # 2) pytrends trend araması
    trend_tags = _get_trending_hashtags_pytrends(topic)
    all_tags.extend(trend_tags)

    # 3) YouTube Search API (PEXELS_API_KEY yerine GEMINI_API_KEY fallback)
    yt_api_key = (
        os.environ.get("YOUTUBE_API_KEY") or
        os.environ.get("PEXELS_API_KEY")  # yanlış olur ama deneme
    )
    # NOT: YouTube Data API key ≠ OAuth. Burada public search için API key lazım.
    # Eğer yoksa atla.
    if yt_api_key and len(yt_api_key) > 20:
        yt_tags = _get_youtube_search_hashtags(topic, yt_api_key)
        all_tags.extend(yt_tags)

    # 4) Temel hashtag'ler (her zaman eklenir)
    all_tags.extend(BASE_HASHTAGS)

    # Dedup + ilk 30
    seen = set()
    result = []
    for tag in all_tags:
        low = tag.lower()
        if low not in seen and re.match(r"^[a-zA-Z0-9]{2,30}$", tag):
            seen.add(low)
            result.append(tag)
        if len(result) >= 30:
            break

    return result


def build_optimized_description(
    script: dict,
    video_id: str,
    hashtags: list[str] = None,
) -> str:
    """
    YouTube SEO'ya uygun, hashtag optimizeli video açıklaması oluşturur.

    Yapı:
    1. Hook (ilk 2 satır — arama snippet'ında görünür)
    2. Kısa özet
    3. Zaman damgaları (varsa)
    4. Kanal harekete geçirme çağrısı
    5. Hashtag'ler (son bölüm — YouTube bunu analiz eder)
    """
    title = script.get("title", "")
    hook = script.get("hook", "")
    narration = script.get("narration", "")
    tags = script.get("tags", [])

    if not hashtags:
        hashtags = get_trending_hashtags(title, tags)

    # Açıklama metni
    yt_url = f"https://youtube.com/shorts/{video_id}" if video_id else ""

    # İlk 125 karakter arama sonuçlarında görünür — hook en üste
    lines = []
    lines.append(hook if hook else title)
    lines.append("")

    # Kısa özet (narration ilk 150 karakter)
    if narration:
        summary = narration[:150].rsplit(" ", 1)[0] + "..."
        lines.append(summary)
        lines.append("")

    # Kanal CTA
    lines.append("👊 What alternate history scenario should we cover next? Comment below!")
    lines.append("🔔 Subscribe for daily history shorts!")
    if yt_url:
        lines.append(f"🔗 {yt_url}")
    lines.append("")

    # Hashtag bölümü — her hashtag ayrı mı yoksa inline mı?
    # YouTube max 15 hashtag gösterir, fazlası yok sayılır
    ht_line = " ".join(f"#{t}" for t in hashtags[:15])
    lines.append(ht_line)

    return "\n".join(lines)


def update_video_description(video_id: str, new_description: str) -> bool:
    """
    YouTube API ile video açıklamasını günceller.
    Mevcut title/category korunur — sadece description değişir.
    """
    if not YOUTUBE_API_AVAILABLE:
        print("[hashtag] google-api-python-client kurulu değil.")
        return False

    try:
        token_json = os.environ.get("YOUTUBE_TOKEN_JSON")
        SCOPES = ["https://www.googleapis.com/auth/youtube"]

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

        youtube = build("youtube", "v3", credentials=creds)

        # Önce mevcut video bilgilerini al (title + categoryId zorunlu)
        resp = youtube.videos().list(
            part="snippet",
            id=video_id,
        ).execute()

        if not resp.get("items"):
            print(f"[hashtag] Video bulunamadı: {video_id}")
            return False

        snippet = resp["items"][0]["snippet"]
        snippet["description"] = new_description

        youtube.videos().update(
            part="snippet",
            body={"id": video_id, "snippet": snippet},
        ).execute()

        print(f"[hashtag] Açıklama güncellendi: {video_id}")
        return True

    except Exception as e:
        print(f"[hashtag] Açıklama güncellenemedi: {e}")
        return False


def optimize_video_hashtags(video_id: str, script: dict) -> bool:
    """
    Ana fonksiyon: hashtag araştır → açıklama oluştur → YouTube'da güncelle.
    main.py'den çağrılır.
    """
    topic = script.get("title", "")
    tags = script.get("tags", [])

    print("[hashtag] Trend hashtag'ler araştırılıyor...")
    hashtags = get_trending_hashtags(topic, tags)
    print(f"[hashtag] {len(hashtags)} hashtag bulundu: {hashtags[:8]}...")

    description = build_optimized_description(script, video_id, hashtags)
    return update_video_description(video_id, description)


if __name__ == "__main__":
    import sys
    # Test modu
    test_script = {
        "title": "What if Rome Never Fell?",
        "hook": "The Roman Empire never collapsed — but what would the world look like TODAY?",
        "narration": "Imagine waking up in 2025 where Roman legions still patrol the borders...",
        "tags": ["rome", "whatif", "history", "alternate"],
        "thumbnail_text": "ROME NEVER FELL?",
    }
    vid = sys.argv[1] if len(sys.argv) > 1 else "TEST_ID"
    desc = build_optimized_description(test_script, vid)
    print("=== OPTİMİZE AÇIKLAMA ===")
    print(desc)
