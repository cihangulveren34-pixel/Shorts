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
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


TOPIC_POOL_PATH = "topic_pool.json"
USED_TOPICS_PATH = "used_topics.json"
MIN_POOL_SIZE = 30          # Bu sayının altına düşünce genişlet
EXPAND_COUNT = 20           # Her genişletmede eklenecek yeni konu sayısı

# Konu kategorileri ve hedef dağılım oranları
CATEGORIES = {
    "Turkey":           ["turkey", "turkish", "bayraktar", "kaan", "akıncı", "kızılelma", "blue homeland", "nato turkey"],
    "Iran":             ["iran", "iranian", "tehran", "hormuz", "hezbollah", "proxy", "persian gulf"],
    "Russia":           ["russia", "russian", "putin", "kremlin", "wagner", "kinzhal", "poseidon", "nato russia"],
    "China":            ["china", "chinese", "beijing", "taiwan", "pla", "south china sea", "df-41", "rare earth"],
    "Israel":           ["israel", "israeli", "mossad", "iron dome", "idf", "hamas", "hezbollah"],
    "USA":              ["america", "us ", "pentagon", "b-21", "ngad", "ford class", "nato", "pacific"],
    "Gulf States":      ["uae", "emirates", "qatar", "saudi", "gulf", "neom", "edge group", "bahrain"],
    "Military Tech":    ["drone", "hypersonic", "stealth", "missile", "railgun", "laser", "swarm", "submarine", "fighter jet", "carrier", "ai warfare", "emp", "thermobaric", "quantum radar", "microwave weapon"],
    "Cyber & Space":    ["cyber", "satellite", "space weapon", "starlink", "gps", "hack", "internet cable", "anti-satellite"],
    "Nuclear":          ["nuclear", "nuke", "warhead", "icbm", "triad", "dead hand", "doomsday", "fallout"],
    "Asia Pacific":     ["india", "pakistan", "japan", "south korea", "north korea", "australia", "aukus"],
    "Europe Defense":   ["poland", "germany", "france", "europe military", "nato europe", "rearmament"],
    "WW3 Scenarios":    ["world war 3", "ww3", "global war", "first 24 hours", "all satellites", "bioweapon"],
    "Rankings":         ["top 5", "top 10", "most powerful", "most dangerous", "deadliest", "strongest"],
}

EXPANSION_PROMPT = """You are a VIRAL YouTube Shorts scriptwriter generating addictive MODERN military & geopolitics topics.

IMPORTANT: NO ancient history, NO medieval, NO pre-1990 topics. ONLY modern (2000-2025) military, geopolitics, and technology.

Current topics in the pool (for reference — do NOT repeat these):
{existing_sample}

Generate exactly {count} NEW topics that get MILLIONS of views. Mix these types:
- "What if [country] [military action]?" — Turkey, Iran, Russia, China, Israel, USA, UAE, India, Pakistan
- "[Weapon system]: Why It Changes Everything" — drones, hypersonics, stealth, AI, cyber, space weapons
- "[Country A] vs [Country B]: Who Really Wins?" — military comparisons with specific stats
- "Top 5/10 [military category]" — rankings with shocking reveals
- "[Country]'s Secret [Weapon/Program]: What Nobody Knows" — classified/unknown military programs
- "What if [WW3 scenario]?" — modern doomsday scenarios

MUST cover these countries (spread evenly):
- Turkey (Bayraktar, KAAN, Akıncı, Kızılelma, defense industry)
- Iran (missiles, drones, proxies, nuclear program, Hormuz)
- Russia (hypersonics, nuclear arsenal, navy, Wagner, Arctic)
- China (Taiwan, carriers, AI warfare, hypersonics, space)
- Israel (Iron Dome, Mossad, nukes, AI battlefield)
- USA (B-21, NGAD, carriers, nuclear triad, AUKUS)
- UAE/Qatar/Saudi (military rise, arms race, Gulf tensions)
- India/Pakistan/Japan/South Korea (nuclear, rearmament)

VIRALITY RULES:
- Use SPECIFIC weapon names: "Bayraktar TB3" not "Turkish drone"
- Use SHOCKING numbers: "$13 billion carrier" not "expensive ship"
- Create FEAR and CURIOSITY: "Should the world worry?"
- Every topic must make viewer think "I NEED to know this"
- NO historical topics before 1990

Return ONLY a JSON array of strings:
["What if ...", "Turkey's ...", "Top 5 ...", ...]"""


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
        client = genai.Client(api_key=api_key)

        sample_text = "\n".join(f"- {t}" for t in existing_sample[:15])
        prompt = EXPANSION_PROMPT.format(
            existing_sample=sample_text,
            count=count,
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=1.0,
                max_output_tokens=1024,
            ),
        )
        raw = response.text.strip()

        # JSON parse
        topics = json.loads(raw)
        if isinstance(topics, list):
            # Temizle ve doğrula
            clean = []
            for t in topics:
                if isinstance(t, str) and len(t) > 15:
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
