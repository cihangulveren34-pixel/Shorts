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


# ─── Haber Varlık Çıkarıcı ───────────────────────────────────────────────────

# Olay tipi → ilgili görsel arama terimleri (CC'de gerçekten bulunan içerik)
EVENT_VISUAL_TERMS = {
    "ceasefire":     ["ceasefire agreement signing", "peace talks military", "war zone aftermath footage"],
    "negotiation":   ["military diplomacy footage", "peace summit leaders", "military negotiations footage"],
    "sanction":      ["military sanctions footage", "arms embargo news", "economic warfare footage"],
    "nuclear":       ["nuclear facility footage", "nuclear missile launch test", "nuclear submarine operations"],
    "missile":       ["missile launch footage", "ballistic missile test", "cruise missile strike footage"],
    "airstrike":     ["airstrike footage", "precision bombing footage", "fighter jet bombing run"],
    "invasion":      ["military invasion footage", "troops crossing border", "armored column advance"],
    "offensive":     ["military offensive footage", "troops advancing combat", "battlefield offensive"],
    "blockade":      ["naval blockade footage", "warship blockade operations", "maritime blockade footage"],
    "deployment":    ["troops deployment footage", "military deployment airfield", "soldiers boarding aircraft"],
    "exercise":      ["joint military exercise footage", "military drill footage", "war games exercise"],
    "summit":        ["military summit footage", "defense ministers meeting", "NATO summit footage"],
    "attack":        ["military attack footage", "combat operation footage", "military strike footage"],
    "retreat":       ["military retreat footage", "troops withdrawal footage", "military pullback footage"],
    "occupation":    ["military occupation footage", "soldiers checkpoint footage", "occupied territory footage"],
}

def _extract_news_entities(text: str) -> dict:
    """
    Haber metninden WHO/WHAT/WHERE/WEAPON varlıklarını çıkarır.
    Gemini kullanır; başarısız olursa kural tabanlı fallback.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {}

    prompt = (
        f'Extract key entities from this military news text for YouTube footage search:\n"{text[:400]}"\n\n'
        'Return JSON with these fields (strings, empty if not found):\n'
        '{"countries": ["country1", "country2"], '
        '"event_type": "one of: ceasefire/negotiation/sanction/nuclear/missile/airstrike/invasion/offensive/blockade/deployment/exercise/summit/attack/retreat/occupation/conflict", '
        '"weapons": ["weapon1"], '
        '"locations": ["city or region"], '
        '"key_actors": ["military unit or leader"]}'
    )

    raw = _call_gemini(prompt)
    if not raw:
        return {}
    try:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except (json.JSONDecodeError, KeyError):
        pass
    return {}


def _build_entity_queries(entities: dict, scene_index: int) -> list[FootageQuery]:
    """
    Çıkarılan varlıklardan yüksek alaka puanlı arama sorguları üretir.
    Yalnızca YouTube CC'de gerçekten bulunabilecek içerikleri hedefler.
    """
    queries = []
    countries = entities.get("countries", [])[:2]
    weapons   = entities.get("weapons", [])[:2]
    locations = entities.get("locations", [])[:1]
    event     = entities.get("event_type", "").lower()
    actors    = entities.get("key_actors", [])[:1]

    # 1) Ülke + Olay kombinasyonu
    for country in countries:
        for ev_term in EVENT_VISUAL_TERMS.get(event, ["military operation footage"])[:2]:
            q = f"{country} {ev_term}"
            queries.append(FootageQuery(q, relevance=0.97, source="entity", scene_index=scene_index))

    # 2) Silah + Aksiyon
    for weapon in weapons:
        wl = weapon.lower()
        if wl in WEAPON_SEARCH_TERMS:
            for term in WEAPON_SEARCH_TERMS[wl][:2]:
                queries.append(FootageQuery(term, relevance=0.95, source="entity_weapon", scene_index=scene_index))
        else:
            queries.append(FootageQuery(f"{weapon} military footage", relevance=0.90, source="entity_weapon", scene_index=scene_index))

    # 3) Lokasyon + askeri bağlam
    for loc in locations:
        queries.append(FootageQuery(f"{loc} military footage", relevance=0.88, source="entity_location", scene_index=scene_index))
        if countries:
            queries.append(FootageQuery(f"{countries[0]} {loc} conflict footage", relevance=0.85, source="entity_location", scene_index=scene_index))

    # 4) Aktör/birlik bazlı
    for actor in actors:
        al = actor.lower()
        # COUNTRY_MILITARY_TERMS ile eşleştir
        for country_key, terms in COUNTRY_MILITARY_TERMS.items():
            if country_key in al or any(t.lower() in al for t in terms[:2]):
                for term in terms[:2]:
                    queries.append(FootageQuery(f"{term} footage", relevance=0.88, source="entity_actor", scene_index=scene_index))
                break

    # 5) Olay tipi genel görsel (CC'de mutlaka bulunan güvenli fallback)
    for ev_term in EVENT_VISUAL_TERMS.get(event, [])[:2]:
        queries.append(FootageQuery(ev_term, relevance=0.80, source="event_type", scene_index=scene_index))

    return queries


# ─── Gemini ile Akıllı Sorgu Üretimi ─────────────────────────────────────────

def _generate_scene_queries(scene_text: str, scene_index: int, full_context: str,
                             entities: dict = None) -> list[FootageQuery]:
    """
    Tek bir sahne için Gemini'den spesifik YouTube arama sorguları üretir.
    5 sorgu üretir ve CC'de bulunan içeriği hedefler.
    """
    # Varlık bilgisini prompt'a ekle
    entity_hint = ""
    if entities:
        parts = []
        if entities.get("countries"):
            parts.append(f"Countries: {', '.join(entities['countries'])}")
        if entities.get("event_type"):
            parts.append(f"Event type: {entities['event_type']}")
        if entities.get("weapons"):
            parts.append(f"Weapons/equipment: {', '.join(entities['weapons'])}")
        if entities.get("locations"):
            parts.append(f"Location: {', '.join(entities['locations'])}")
        if parts:
            entity_hint = "\nKey entities: " + " | ".join(parts)

    system = """You are a military video editor finding B-roll footage on YouTube.
Given a scene from a news analysis video, generate YouTube search queries to find
VISUALLY MATCHING Creative Commons or public domain footage.

CRITICAL RULES:
1. Generate queries that ACTUALLY EXIST on YouTube (real footage, not imagined)
2. Prioritize: official military channels, news agencies, government sources
3. For diplomatic/political events: use footage of military presence, troops, equipment in that region
4. For specific weapons: use exact model names + "footage" or "test" or "operations"
5. For negotiations/sanctions: show military buildup, naval presence, troops at border
6. Add location or country to make queries specific
7. Mix: 2 very specific queries + 2 moderately specific + 1 general fallback

Reply ONLY in JSON:
{"queries": ["query 1", "query 2", "query 3", "query 4", "query 5"]}"""

    prompt = (
        f"Scene {scene_index + 1}:\n\"{scene_text}\"\n"
        f"Full video context: {full_context[:250]}"
        f"{entity_hint}\n\n"
        f"Generate 5 YouTube search queries for B-roll footage matching this scene. "
        f"Focus on footage that visually represents this event (even if indirect — e.g., troops, ships, aircraft relevant to the story)."
    )

    raw = _call_gemini(prompt, system)
    queries = []

    if raw:
        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                for j, q in enumerate(data.get("queries", [])):
                    if q and len(q) > 5:
                        # İlk 2 sorgu en spesifik — en yüksek relevance
                        relevance = 0.97 if j < 2 else (0.90 if j < 4 else 0.80)
                        queries.append(FootageQuery(
                            query=q,
                            relevance=relevance,
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
      1. Tüm metinden haber varlıklarını çıkar (WHO/WHAT/WHERE/WEAPON)
      2. Narasyonu 3 sahneye böl
      3. Her sahne için:
         a) Varlık bazlı spesifik sorgular
         b) Gemini sahne sorguları (5 adet)
         c) Ülke/silah zenginleştirmesi
      4. Orijinal search_keywords fallback
      5. Deduplicate + relevance sıralaması

    Returns:
        Sıralı FootageQuery listesi (en alakalı en önde)
    """
    narration = script.get("narration", "")
    title = script.get("title", "")
    original_keywords = script.get("search_keywords", [])
    full_context = f"{title}. {narration}"

    all_queries: list[FootageQuery] = []

    # 1) Haber varlık çıkarımı (tüm metin üzerinden — tek Gemini çağrısı)
    print(f"[footage_matcher] Haber varlıkları çıkarılıyor...")
    entities = _extract_news_entities(full_context)
    if entities:
        print(f"[footage_matcher]   Varlıklar: ülkeler={entities.get('countries', [])}, "
              f"olay={entities.get('event_type', '-')}, silahlar={entities.get('weapons', [])}")

    # 2) Narasyonu sahnelere böl
    scenes = _split_narration_to_scenes(narration, num_scenes=3)
    print(f"[footage_matcher] {len(scenes)} sahne")

    # 3) Her sahne için çok katmanlı sorgu üretimi
    for i, scene in enumerate(scenes):
        scene_entities = _extract_news_entities(scene) if scene != full_context else entities

        # 3a) Varlık bazlı yüksek-alaka sorgular
        entity_queries = _build_entity_queries(scene_entities or entities, i)
        all_queries.extend(entity_queries)

        # 3b) Gemini sahne sorguları (5 adet, varlık bağlamıyla)
        gemini_queries = _generate_scene_queries(scene, i, full_context, entities)
        all_queries.extend(gemini_queries)

        # 3c) Ülke/silah zenginleştirme (sahne metninden)
        all_queries.extend(_enrich_with_country_terms(scene, scene_index=i))
        all_queries.extend(_enrich_with_weapon_terms(scene, scene_index=i))

        total_scene = len(entity_queries) + len(gemini_queries)
        print(f"[footage_matcher]   Sahne {i+1}: {total_scene} sorgu "
              f"({len(entity_queries)} varlık, {len(gemini_queries)} Gemini)")

    # 4) Orijinal search_keywords (fallback — düşük relevance)
    for kw in original_keywords:
        q = kw if ("footage" in kw.lower() or "operations" in kw.lower()) else f"{kw} footage"
        all_queries.append(FootageQuery(query=q, relevance=0.55, source="original"))

    # 5) Deduplicate (query metni bazında) + relevance sıralaması
    seen: set[str] = set()
    unique_queries: list[FootageQuery] = []
    for q in all_queries:
        key = q.query.lower().strip()
        if key not in seen:
            seen.add(key)
            unique_queries.append(q)

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


def get_scene_based_keywords(script: dict, min_per_scene: int = 8) -> list[list[str]]:
    """
    Sahne bazlı keyword grupları döndürür.
    Her grup bir video klibi için kullanılır.
    Alakalılık sırasına göre sıralı — en spesifik sorgular başta.

    Args:
        min_per_scene: Her sahne için garanti edilecek minimum sorgu sayısı.

    Returns:
        [[sahne1_kw1, sahne1_kw2, ...], [sahne2_kw1, ...], [sahne3_kw1, ...]]
    """
    queries = generate_smart_queries(script)

    # Sahne bazlı grupla, her sahne kendi içinde relevance'a göre sıralı
    scene_groups: list[list[str]] = [[], [], []]
    for q in sorted(queries, key=lambda x: x.relevance, reverse=True):
        idx = min(q.scene_index, 2)
        scene_groups[idx].append(q.query)

    # Her sahne için minimum sorgu garantisi:
    # Boş/yetersiz sahneleri yüksek-relevance genel sorgularla doldur
    high_relevance = [q.query for q in queries if q.relevance >= 0.85]
    fallback = high_relevance or [q.query for q in queries] or script.get("search_keywords", [])

    for i, group in enumerate(scene_groups):
        if len(group) < min_per_scene:
            # Diğer sahnelerin yüksek-alaka sorgularından tamamla
            extras = [kw for kw in fallback if kw not in group]
            scene_groups[i] = group + extras[:min_per_scene - len(group)]

    for i, group in enumerate(scene_groups):
        print(f"[footage_matcher] Sahne {i+1} keywords: {len(group)} sorgu, "
              f"ilk: '{group[0][:60]}'" if group else f"Sahne {i+1}: BOŞ")

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
