"""
topic_expander.py — Gemini ile topic_pool.json'ı otomatik genişletir.

topic_pool.json'daki konu sayısı eşiğin altına düştüğünde
Gemini'ye mevcut konulara benzer, farklı 20 yeni "What if" senaryosu
ürettirir ve pool'a ekler.

Ayrıca belirli kategorilerde (Antik Dünya, Ortaçağ, WW1/2, Soğuk Savaş...)
dengeli konu dağılımı sağlar.

Gereksinim: GEMINI_API_KEY
"""

import json
import os
import re

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


TOPIC_POOL_PATH = "topic_pool.json"
USED_TOPICS_PATH = "used_topics.json"
MIN_POOL_SIZE = 30          # Bu sayının altına düşünce genişlet
EXPAND_COUNT = 20           # Her genişletmede eklenecek yeni konu sayısı

# Konu kategorileri ve hedef dağılım oranları
CATEGORIES = {
    "Ancient World":    ["rome", "greek", "persia", "egypt", "babylon", "carthage", "sparta"],
    "Medieval":         ["mongol", "crusade", "viking", "feudal", "plague", "byzantine"],
    "Early Modern":     ["napoleon", "ottoman", "colonial", "aztec", "inca", "ming"],
    "World War I":      ["ww1", "great war", "trench", "western front"],
    "World War II":     ["ww2", "nazi", "d-day", "pacific", "stalingrad", "hiroshima"],
    "Cold War":         ["cold war", "soviet", "nuclear", "vietnam", "korea", "space race"],
    "American History": ["civil war", "revolution", "confederate", "manifest destiny"],
}

EXPANSION_PROMPT = """You are a creative history writer specializing in alternate history "What if" scenarios.

Current topics in the pool (for reference):
{existing_sample}

Generate exactly {count} NEW alternate history "What if" questions that:
1. Are NOT similar to the existing ones above
2. Cover diverse time periods and civilizations
3. Are dramatic, thought-provoking, and suitable for 60-second YouTube Shorts
4. Follow this format: "What if [historical entity] had [alternate action/outcome]?"
5. Cover these categories proportionally: Ancient World, Medieval, WW2, Cold War, American History, Asian History

Return ONLY a JSON array of strings, no explanation:
["What if ...", "What if ...", ...]"""


def _load_pool() -> list[str]:
    try:
        with open(TOPIC_POOL_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def _load_used() -> set:
    try:
        with open(USED_TOPICS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("used", []))
    except FileNotFoundError:
        return set()


def _save_pool(pool: list[str]) -> None:
    with open(TOPIC_POOL_PATH, "w", encoding="utf-8") as f:
        json.dump(pool, f, indent=2, ensure_ascii=False)


def _count_available(pool: list[str], used: set) -> int:
    return sum(1 for t in pool if t not in used)


def _get_category_distribution(pool: list[str]) -> dict[str, int]:
    """Mevcut pool'daki kategori dağılımını hesaplar."""
    dist = {cat: 0 for cat in CATEGORIES}
    for topic in pool:
        lower = topic.lower()
        for cat, keywords in CATEGORIES.items():
            if any(kw in lower for kw in keywords):
                dist[cat] += 1
                break
    return dist


def _generate_with_gemini(existing_sample: list[str], count: int) -> list[str]:
    """Gemini ile yeni konular üretir."""
    if not GEMINI_AVAILABLE:
        print("[expander] google-generativeai kurulu değil.")
        return []

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[expander] GEMINI_API_KEY yok.")
        return []

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=1.0,        # Yaratıcılık için yüksek temperature
                max_output_tokens=1024,
            ),
        )

        sample_text = "\n".join(f"- {t}" for t in existing_sample[:15])
        prompt = EXPANSION_PROMPT.format(
            existing_sample=sample_text,
            count=count,
        )

        response = model.generate_content(prompt)
        raw = response.text.strip()

        # JSON parse
        topics = json.loads(raw)
        if isinstance(topics, list):
            # Temizle ve doğrula
            clean = []
            for t in topics:
                if isinstance(t, str) and len(t) > 15 and "what if" in t.lower():
                    clean.append(t.strip())
            return clean[:count]

        return []

    except json.JSONDecodeError as e:
        # JSON parse başarısız → regex ile çıkar
        print(f"[expander] JSON parse hatası: {e}. Regex ile deneniyor...")
        raw = response.text if 'response' in dir() else ""
        found = re.findall(r'"(What if[^"]{10,100})"', raw, re.IGNORECASE)
        return found[:count]

    except Exception as e:
        print(f"[expander] Gemini hatası: {e}")
        return []


def expand_topic_pool(force: bool = False) -> dict:
    """
    Topic pool'u gerektiğinde Gemini ile genişletir.

    Args:
        force: True ise minimum eşik kontrolü yapmadan genişlet

    Returns:
        {"expanded": bool, "added": int, "pool_size": int, "available": int}
    """
    pool = _load_pool()
    used = _load_used()
    available = _count_available(pool, used)

    print(f"[expander] Pool: {len(pool)} konu, {available} kullanılabilir")

    if not force and available >= MIN_POOL_SIZE:
        print(f"[expander] Pool yeterli ({available} ≥ {MIN_POOL_SIZE}), genişletme atlandı.")
        return {
            "expanded": False,
            "added": 0,
            "pool_size": len(pool),
            "available": available,
        }

    print(f"[expander] Genişletiliyor: {EXPAND_COUNT} yeni konu üretilecek...")

    # Mevcut pool'dan örnek al (çeşitlilik için karıştır)
    import random
    sample = pool.copy()
    random.shuffle(sample)
    sample = sample[:20]

    # Dağılım raporu
    dist = _get_category_distribution(pool)
    print(f"[expander] Mevcut dağılım: {dist}")

    new_topics = _generate_with_gemini(sample, EXPAND_COUNT)

    if not new_topics:
        print("[expander] Yeni konu üretilemedi.")
        return {
            "expanded": False,
            "added": 0,
            "pool_size": len(pool),
            "available": available,
        }

    # Mevcut olanları filtrele
    existing_lower = {t.lower() for t in pool}
    fresh = [t for t in new_topics if t.lower() not in existing_lower]

    pool.extend(fresh)
    _save_pool(pool)

    print(f"[expander] ✓ {len(fresh)} yeni konu eklendi. Pool: {len(pool)}")
    if fresh:
        print(f"[expander] Örnek: {fresh[0]}")

    return {
        "expanded": True,
        "added": len(fresh),
        "pool_size": len(pool),
        "available": _count_available(pool, used),
        "sample": fresh[:3],
    }


def expand_if_low(threshold: int = MIN_POOL_SIZE) -> None:
    """
    topic_selector.py veya main.py'den çağrılan kısa yardımcı.
    Pool düşükse sessizce genişletir.
    """
    try:
        pool = _load_pool()
        used = _load_used()
        available = _count_available(pool, used)
        if available < threshold:
            print(f"[expander] Pool düşük ({available} < {threshold}), genişletiliyor...")
            expand_topic_pool()
    except Exception as e:
        print(f"[expander] Genişletme hatası (kritik değil): {e}")


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    result = expand_topic_pool(force=force)
    print(json.dumps(result, indent=2, ensure_ascii=False))
