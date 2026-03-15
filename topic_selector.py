"""
topic_selector.py — Google Trends ile topic_pool'dan en popüler konuyu seçer.

Pytrends (ücretsiz, resmi olmayan Google Trends sarmalayıcı) kullanır.
API key gerekmez.

Strateji:
  1. topic_pool.json'dan kullanılmamış konuları al
  2. Her konunun anahtar kelimelerini Google Trends'te sorgula (son 7 gün)
  3. En yüksek ortalama ilgi skoruna sahip konuyu seç
  4. Pytrends hata verirse normal round-robin rotasyona düş (fallback)
"""

import json
import os
import time


TOPIC_POOL_PATH = "topic_pool.json"
USED_TOPICS_PATH = "used_topics.json"


def _load_available_topics() -> tuple[list, dict]:
    with open(TOPIC_POOL_PATH, encoding="utf-8") as f:
        all_topics = json.load(f)

    used_data = {}
    if os.path.exists(USED_TOPICS_PATH):
        with open(USED_TOPICS_PATH, encoding="utf-8") as f:
            used_data = json.load(f)

    used_set = set(used_data.get("used", []))
    available = [t for t in all_topics if t not in used_set]

    if not available:
        # Tümü kullanılmış → sıfırla
        available = all_topics
        used_data["used"] = []

    return available, used_data


def _extract_keywords(topic: str) -> list[str]:
    """
    Konu başlığından arama anahtar kelimelerini çıkarır.
    Örn: "What if Rome Never Fell?" → ["Rome", "Roman Empire"]
    """
    # Yaygın kalıpları çıkar
    topic_clean = topic.replace("What if ", "").replace("?", "").strip()
    words = [w for w in topic_clean.split() if len(w) > 3 and w not in
             {"Never", "Fell", "Won", "Lost", "Didn", "Hadn", "Hadn't", "Never"}]
    return words[:3] if words else [topic_clean[:20]]


def _score_with_trends(topics: list[str], max_topics: int = 8) -> dict[str, float]:
    """
    Google Trends üzerinden her konunun son 7 günlük ilgi skorunu döndürür.
    Hata durumunda boş dict döndürür.
    """
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=0, timeout=(10, 30))
        scores = {}

        # Batch: her seferinde max 5 konu sorgula (Trends limiti)
        batch_topics = topics[:max_topics]

        for i in range(0, len(batch_topics), 5):
            batch = batch_topics[i:i + 5]
            # Her konu için tek anahtar kelime kullan
            keywords = [_extract_keywords(t)[0] for t in batch]

            try:
                pytrends.build_payload(keywords, timeframe="now 7-d", geo="")
                df = pytrends.interest_over_time()

                if df.empty:
                    continue

                for j, topic in enumerate(batch):
                    kw = keywords[j]
                    if kw in df.columns:
                        scores[topic] = float(df[kw].mean())

                time.sleep(1)  # Rate limit
            except Exception:
                continue

        return scores

    except ImportError:
        return {}
    except Exception as e:
        print(f"[topic_selector] Trends hatası: {e}")
        return {}


def pick_trending_topic(override: str = None) -> tuple[str, dict]:
    """
    Google Trends ile en popüler konuyu seçer.
    Döndürür: (seçilen konu, güncellenmiş used_data)

    override verilirse Trends'e bakmadan o konuyu döndürür.
    """
    from datetime import date

    if override:
        available, used_data = _load_available_topics()
        if override not in used_data.get("used", []):
            used_data.setdefault("used", []).append(override)
        used_data["last_run"] = str(date.today())
        return override, used_data

    available, used_data = _load_available_topics()

    if len(available) == 1:
        topic = available[0]
    else:
        print(f"[topic_selector] {len(available)} konu mevcut, Trends sorgulanıyor...")
        scores = _score_with_trends(available)

        if scores:
            # En yüksek skorlu konuyu seç
            topic = max(scores, key=scores.get)
            top_score = scores[topic]
            print(f"[topic_selector] Trending konu: '{topic}' (skor: {top_score:.1f})")
        else:
            # Fallback: sıradan ilk konu
            topic = available[0]
            print(f"[topic_selector] Trends kullanılamadı, fallback: '{topic}'")

    used_data.setdefault("used", []).append(topic)
    used_data["last_run"] = str(date.today())

    return topic, used_data


if __name__ == "__main__":
    topic, _ = pick_trending_topic()
    print(f"Seçilen konu: {topic}")
