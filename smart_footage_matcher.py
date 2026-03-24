"""
smart_footage_matcher.py — AI destekli akıllı footage eşleştirme motoru.

Mevcut sorun: Script "Turkey's KAAN stealth fighter" hakkında olsa bile,
YouTube'da "fighter jet takeoff footage" gibi genel aramalar yapılıyor.
Sonuç: Video içeriğiyle alakasız generic askeri görüntüler.

Çözüm: Gemini ile script'in her sahnesine özel, spesifik arama sorguları üretir.

Akış:
  1. Script narasyonunu sahne sahne böl (her 10-12 sn)
  2. Her sahne için Gemini'den 3 spesifik YouTube arama sorgusu üret
  3. Ülke + silah + olay bazlı keyword zenginleştirme
  4. Sorguları önem/alaka sırasına göre sırala
  5. video_builder.py'ye entegre et

Örnek:
  Script: "Turkey just unveiled the KAAN stealth fighter..."
  Eski:   ["fighter jet takeoff footage", "military jet formation footage"]
  Yeni:   ["KAAN TFX stealth fighter Turkey", "Turkish Air Force KAAN jet test flight",
           "Turkey 5th generation fighter jet unveiling ceremony"]
"""

import json
import os
import re
import requests
from dataclasses import dataclass, field


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Ülke → askeri terminoloji eşleşmesi
COUNTRY_MILITARY_TERMS = {
    "turkey": ["Turkish Armed Forces", "TSK", "Turkey military", "Bayraktar", "KAAN", "Akinci", "TAI", "Turkish defense"],
    "russia": ["Russian military", "Russian Armed Forces", "Spetsnaz", "S-400", "Su-57", "T-90", "Wagner", "Russian Navy"],
    "usa": ["US military", "Pentagon", "US Armed Forces", "USAF", "US Navy", "Marines", "US Army"],
    "china": ["PLA", "Chinese military", "PLAN", "Chinese navy", "J-20", "DF-41", "Chinese defense"],
    "iran": ["IRGC", "Iranian military", "Iranian missile", "Shahed drone", "Iran navy", "Iranian defense"],
    "israel": ["IDF", "Israel Defense Forces", "Iron Dome", "Israeli Air Force", "Mossad", "Israeli military"],
    "ukraine": ["Ukrainian military", "Ukrainian Armed Forces", "Ukraine frontline", "Ukrainian drone", "Ukraine war"],
    "nato": ["NATO forces", "NATO exercise", "NATO military", "Allied forces", "NATO deployment"],
    "north korea": ["DPRK military", "North Korean missile", "Korean People's Army", "North Korea military"],
    "india": ["Indian military", "Indian Armed Forces", "Indian Navy", "Tejas fighter", "Indian Army"],
    "pakistan": ["Pakistan military", "Pakistan Armed Forces", "JF-17", "Pakistan Navy"],
    "uk": ["British military", "Royal Navy", "RAF", "British Armed Forces", "SAS"],
    "france": ["French military", "French Armed Forces", "Rafale fighter", "French Navy", "Legion"],
    "germany": ["Bundeswehr", "German military", "Leopard tank", "German defense"],
    "japan": ["JSDF", "Japan Self-Defense Forces", "Japanese military", "Japanese Navy"],
    "south korea": ["ROK military", "South Korean military", "K2 tank", "KF-21 fighter"],
}

# Silah sistemi → spesifik arama terimleri
WEAPON_SEARCH_TERMS = {
    "f-35": ["F-35 Lightning II", "F-35 takeoff", "F-35 stealth fighter operations"],
    "f-22": ["F-22 Raptor", "F-22 air superiority", "F-22 formation flight"],
    "su-57": ["Su-57 Felon", "Sukhoi Su-57", "Russian stealth fighter Su-57"],
    "kaan": ["KAAN fighter jet Turkey", "TFX KAAN stealth", "Turkish KAAN 5th gen fighter"],
    "bayraktar": ["Bayraktar TB2 drone", "Bayraktar combat footage", "Turkish Bayraktar UAV"],
    "akinci": ["Bayraktar Akinci UCAV", "Akinci drone Turkey", "Turkish Akinci combat drone"],
    "s-400": ["S-400 missile system", "S-400 air defense", "S-400 Triumf deployment"],
    "patriot": ["Patriot missile system", "MIM-104 Patriot", "Patriot air defense launch"],
    "iron dome": ["Iron Dome interception", "Iron Dome missile defense", "Israel Iron Dome"],
    "abrams": ["M1 Abrams tank", "Abrams tank live fire", "M1A2 Abrams operations"],
    "leopard": ["Leopard 2 tank", "Leopard tank operations", "Leopard 2A7 combat"],
    "himars": ["HIMARS rocket system", "M142 HIMARS launch", "HIMARS Ukraine"],
    "javelin": ["FGM-148 Javelin", "Javelin anti-tank missile", "Javelin missile firing"],
    "hypersonic": ["hypersonic missile test", "hypersonic weapon launch", "hypersonic glide vehicle"],
    "nuclear": ["nuclear missile launch test", "nuclear submarine", "ICBM test launch"],
    "aircraft carrier": ["aircraft carrier operations", "carrier flight deck", "carrier strike group"],
    "submarine": ["submarine surfacing", "submarine missile launch", "nuclear submarine operations"],
    "drone": ["military drone operations", "combat UAV footage", "drone surveillance military"],
    "helicopter": ["attack helicopter operations", "military helicopter combat", "helicopter gunship footage"],
    "tank": ["tank live fire exercise", "armored warfare footage", "tank combat operations"],
}


@dataclass
class FootageQuery:
    """Tek bir footage arama sorgusu."""
    query: str
    relevance: float  # 0.0-1.0 — ne kadar script'e özel
    source: str       # "gemini", "weapon", "country", "category", "generic"
    scene_index: int = 0  # Hangi sahne için


def _call_gemini(prompt: str, system: str = "") -> str:
    """Gemini API çağrısı."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return ""

    model = "gemini-2.5-flash-lite"
    url = f"{GEMINI_API_URL.format(model=model)}?key={api_key}"

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 400,
            "temperature": 0.4,
        },
    }
    if system:
        payload["system_instruction"] = {"parts": [{"text": system}]}

    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"[footage_matcher] Gemini hatası: {e}")
    return ""


# ─── Narasyonu Sahnelere Böl ─────────────────────────────────────────────────

def _split_narration_to_scenes(narration: str, num_scenes: int = 3) -> list[str]:
    """
    Narasyonu eşit parçalara böler (her biri bir video klibi temsil eder).
    """
    sentences = re.split(r'(?<=[.!?])\s+', narration.strip())
    if len(sentences) <= num_scenes:
        return sentences

    # Eşit bölme
    chunk_size = len(sentences) // num_scenes
    scenes = []
    for i in range(num_scenes):
        start = i * chunk_size
        end = start + chunk_size if i < num_scenes - 1 else len(sentences)
        scene_text = " ".join(sentences[start:end])
        scenes.append(scene_text)

    return scenes


# ─── Ülke/Silah Tespiti ──────────────────────────────────────────────────────

def _detect_countries(text: str) -> list[str]:
    """Metinden bahsedilen ülkeleri tespit eder."""
    text_lower = text.lower()
    found = []
    for country in COUNTRY_MILITARY_TERMS:
        # Ülke adı veya askeri terimleri metinde geçiyor mu?
        if country in text_lower:
            found.append(country)
        elif any(term.lower() in text_lower for term in COUNTRY_MILITARY_TERMS[country][:2]):
            found.append(country)
    return found


def _detect_weapons(text: str) -> list[str]:
    """Metinden bahsedilen silah sistemlerini tespit eder."""
    text_lower = text.lower()
    found = []
    for weapon in WEAPON_SEARCH_TERMS:
        if weapon in text_lower:
            found.append(weapon)
    return found


# ─── Gemini ile Akıllı Sorgu Üretimi ─────────────────────────────────────────

def _generate_scene_queries(scene_text: str, scene_index: int, full_context: str) -> list[FootageQuery]:
    """
    Tek bir sahne için Gemini'den spesifik YouTube arama sorguları üretir.
    """
    system = """You are a military footage research specialist. Given a scene from a military
analysis video script, generate the MOST SPECIFIC YouTube search queries to find
MATCHING video footage.

Rules:
- Each query MUST be a realistic YouTube search that would find relevant footage
- Include SPECIFIC weapon names, country names, military unit names
- Add "footage" or "operations" at the end of each query
- Prefer real military operation footage over stock/generic
- If a specific weapon/country is mentioned, include it in the query
- Think: what would a military video editor search to find B-roll for this scene?

Reply in JSON:
{"queries": ["query 1", "query 2", "query 3"]}"""

    prompt = (
        f"Scene {scene_index + 1} of a military analysis video:\n"
        f'"{scene_text}"\n\n'
        f"Full video context: {full_context[:200]}\n\n"
        f"Generate 3 SPECIFIC YouTube search queries to find matching military footage for this scene."
    )

    raw = _call_gemini(prompt, system)
    queries = []

    if raw:
        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                for q in data.get("queries", []):
                    if q and len(q) > 5:
                        queries.append(FootageQuery(
                            query=q,
                            relevance=0.95,
                            source="gemini",
                            scene_index=scene_index,
                        ))
        except (json.JSONDecodeError, KeyError):
            pass

    return queries


# ─── Ülke/Silah Bazlı Sorgu Zenginleştirme ──────────────────────────────────

def _enrich_with_country_terms(text: str, scene_index: int = 0) -> list[FootageQuery]:
    """Tespit edilen ülkelere göre spesifik arama sorguları ekler."""
    queries = []
    countries = _detect_countries(text)

    for country in countries[:2]:  # Max 2 ülke
        terms = COUNTRY_MILITARY_TERMS.get(country, [])
        for term in terms[:2]:  # Her ülke için 2 spesifik terim
            queries.append(FootageQuery(
                query=f"{term} footage",
                relevance=0.85,
                source="country",
                scene_index=scene_index,
            ))

    return queries


def _enrich_with_weapon_terms(text: str, scene_index: int = 0) -> list[FootageQuery]:
    """Tespit edilen silah sistemlerine göre spesifik arama sorguları ekler."""
    queries = []
    weapons = _detect_weapons(text)

    for weapon in weapons[:3]:  # Max 3 silah sistemi
        terms = WEAPON_SEARCH_TERMS.get(weapon, [])
        for term in terms[:2]:  # Her silah için 2 terim
            queries.append(FootageQuery(
                query=term,
                relevance=0.90,
                source="weapon",
                scene_index=scene_index,
            ))

    return queries


# ─── Ana Fonksiyon ────────────────────────────────────────────────────────────

def generate_smart_queries(script: dict) -> list[FootageQuery]:
    """
    Script için akıllı footage arama sorguları üretir.

    Pipeline:
      1. Narasyonu 3 sahneye böl
      2. Her sahne için Gemini'den spesifik sorgular al
      3. Ülke/silah bazlı zenginleştirme ekle
      4. Orijinal search_keywords'ü düşük relevance ile ekle
      5. Relevance'a göre sırala ve deduplicate et

    Returns:
        Sıralı FootageQuery listesi (en alakalı en önde)
    """
    narration = script.get("narration", "")
    title = script.get("title", "")
    original_keywords = script.get("search_keywords", [])
    full_context = f"{title}. {narration}"

    all_queries: list[FootageQuery] = []

    # 1) Narasyonu sahnelere böl
    scenes = _split_narration_to_scenes(narration, num_scenes=3)
    print(f"[footage_matcher] {len(scenes)} sahne tespit edildi")

    # 2) Her sahne için Gemini sorguları
    for i, scene in enumerate(scenes):
        gemini_queries = _generate_scene_queries(scene, i, full_context)
        all_queries.extend(gemini_queries)
        print(f"[footage_matcher]   Sahne {i+1}: {len(gemini_queries)} Gemini sorgusu")

    # 3) Tüm metinden ülke/silah zenginleştirme
    country_queries = _enrich_with_country_terms(full_context)
    all_queries.extend(country_queries)
    if country_queries:
        countries = list({q.query.split(" footage")[0] for q in country_queries})
        print(f"[footage_matcher]   Ülke terimleri: {', '.join(countries[:3])}")

    weapon_queries = _enrich_with_weapon_terms(full_context)
    all_queries.extend(weapon_queries)
    if weapon_queries:
        print(f"[footage_matcher]   Silah terimleri: {len(weapon_queries)} sorgu")

    # 4) Orijinal search_keywords (düşük relevance — fallback)
    for kw in original_keywords:
        all_queries.append(FootageQuery(
            query=f"{kw} footage",
            relevance=0.50,
            source="original",
        ))

    # 5) Deduplicate ve sırala
    seen = set()
    unique_queries = []
    for q in all_queries:
        q_normalized = q.query.lower().strip()
        if q_normalized not in seen:
            seen.add(q_normalized)
            unique_queries.append(q)

    # Relevance'a göre sırala (en alakalı en önde)
    unique_queries.sort(key=lambda q: q.relevance, reverse=True)

    print(f"[footage_matcher] Toplam: {len(unique_queries)} benzersiz sorgu (alakaya göre sıralı)")

    return unique_queries


def get_prioritized_keywords(script: dict) -> list[str]:
    """
    video_builder.py için basit arayüz.
    Akıllı sorguları düz keyword listesine dönüştürür.

    Returns:
        Öncelikli keyword listesi (en alakalı en önde)
    """
    queries = generate_smart_queries(script)

    # İlk 15 sorguyu keyword olarak döndür
    keywords = [q.query for q in queries[:15]]

    if not keywords:
        # Fallback: orijinal search_keywords
        keywords = script.get("search_keywords", [])

    return keywords


def get_scene_based_keywords(script: dict) -> list[list[str]]:
    """
    Sahne bazlı keyword grupları döndürür.
    Her grup bir video klibi için kullanılır.

    Returns:
        [[sahne1_kw1, sahne1_kw2, ...], [sahne2_kw1, ...], [sahne3_kw1, ...]]
    """
    queries = generate_smart_queries(script)

    # 3 sahneye grupla
    scene_groups = [[], [], []]
    for q in queries:
        idx = min(q.scene_index, 2)
        scene_groups[idx].append(q.query)

    # Her grup boşsa, genel sorgulardan doldur
    general = [q.query for q in queries if q.source in ("country", "weapon", "original")]
    for i, group in enumerate(scene_groups):
        if not group:
            scene_groups[i] = general[:5] if general else script.get("search_keywords", [])

    return scene_groups


if __name__ == "__main__":
    import sys

    test_script = {
        "title": "Turkey's KAAN Fighter Just Changed Everything",
        "narration": (
            "Turkey just unveiled the KAAN, its first fifth-generation stealth fighter jet. "
            "This isn't just another plane — it's a direct challenge to the F-35. "
            "The KAAN can carry air-to-air missiles internally, has low radar signature, "
            "and can reach speeds over Mach 1.8. But here's what nobody is talking about: "
            "Turkey is also developing the Bayraktar Kizilelma unmanned fighter. "
            "Combined with the TB2 and Akinci drones, Turkey now has the most diverse "
            "combat drone fleet in NATO. If this continues, Turkey could become the "
            "third largest air power in the alliance by 2030."
        ),
        "search_keywords": [
            "stealth fighter jet", "military drone fleet",
            "Turkish air force", "KAAN fighter", "combat drone", "NATO air power"
        ],
        "mood": "epic",
    }

    queries = generate_smart_queries(test_script)
    print(f"\n{'='*60}")
    print(f"Toplam: {len(queries)} sorgu\n")
    for i, q in enumerate(queries, 1):
        print(f"  {i:2d}. [{q.relevance:.2f}] ({q.source:8s}) S{q.scene_index+1}: {q.query}")
