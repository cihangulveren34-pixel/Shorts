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
import random
import re
import time
import unicodedata


TOPIC_POOL_PATH = "topic_pool.json"
USED_TOPICS_PATH = "used_topics.json"


def _normalize(text: str) -> str:
    """Karşılaştırma için normalize eder: küçük harf, özel karakter yok."""
    text = text.lower().strip()
    # [NEWS] prefix varsa kaldır
    if text.startswith("[news] "):
        text = text[7:]
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _load_available_topics() -> tuple[list, dict]:
    with open(TOPIC_POOL_PATH, encoding="utf-8") as f:
        all_topics = json.load(f)

    used_data = {}
    if os.path.exists(USED_TOPICS_PATH):
        with open(USED_TOPICS_PATH, encoding="utf-8") as f:
            used_data = json.load(f)

    # Normalize edilmiş set ile karşılaştır — büyük/küçük harf ve [NEWS] prefix farkı gözetme
    used_normalized = {_normalize(t) for t in used_data.get("used", [])}
    available = [t for t in all_topics if _normalize(t) not in used_normalized]

    if not available:
        # Tümü kullanılmış → sıfırla
        print("[topic_selector] Tüm konular kullanıldı, liste sıfırlanıyor.")
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


def _maybe_refresh_from_rss() -> None:
    """
    RSS monitor'u çalıştırarak topic_pool.json'ı tazeler.
    Hata alınırsa sessizce atlanır.
    """
    try:
        from rss_monitor import monitor_and_update
        result = monitor_and_update(max_topics=5)
        if result.get("topics_added", 0) > 0:
            print(f"[topic_selector] RSS: {result['topics_added']} yeni konu eklendi.")
    except Exception as e:
        print(f"[topic_selector] RSS tarama atlandı: {e}")


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

    # RSS beslemelerinden yeni konular ekle (hata toleranslı)
    _maybe_refresh_from_rss()

    # Pool azaldıysa Gemini ile otomatik genişlet
    try:
        from topic_expander import expand_if_low
        expand_if_low()
    except Exception:
        pass

    available, used_data = _load_available_topics()

    if len(available) == 1:
        topic = available[0]
    else:
        print(f"[topic_selector] {len(available)} konu mevcut, Trends sorgulanıyor...")
        scores = _score_with_trends(available)

        if scores:
            # Top-5 trending'den rastgele seç (çeşitlilik için)
            sorted_topics = sorted(scores, key=scores.get, reverse=True)
            top_n = sorted_topics[:min(5, len(sorted_topics))]
            topic = random.choice(top_n)
            top_score = scores[topic]
            print(f"[topic_selector] Top-5'ten rastgele seçildi: '{topic}' (skor: {top_score:.1f})")
        else:
            # Fallback: rastgele konu seç
            topic = random.choice(available)
            print(f"[topic_selector] Trends kullanılamadı, rastgele: '{topic}'")

    used_data.setdefault("used", []).append(topic)
    used_data["last_run"] = str(date.today())

    return topic, used_data


if __name__ == "__main__":
    topic, _ = pick_trending_topic()
    print(f"Seçilen konu: {topic}")
