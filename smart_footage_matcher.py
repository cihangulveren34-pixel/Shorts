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

import datetime as _dt
_CURRENT_YEAR = _dt.datetime.now().year
_PREV_YEAR = _CURRENT_YEAR - 1

# Generic/alakasız içerik getiren sorgular engellenir
QUERY_BLACKLIST_TERMS = [
    "news anchor", "press conference talking head", "studio interview",
    "generic military", "stock footage military", "training classroom",
    "signing ceremony", "politician speech podium", "flag ceremony parade",
    "marching band", "military band", "honor guard ceremony",
    "reporter live report", "tv news studio", "anchor desk broadcast",
    "documentary narrator", "talking head expert", "panel discussion",
    "map animation", "infographic", "stock photo", "getty images",
    "military funeral", "medal ceremony", "retirement ceremony",
    "recruitment advertisement", "military recruitment poster",
]

# Türkçe/Arapça askeri arama terimleri — bu dillerde yalnızca YouTube'da bulunan içerikler
ALT_LANG_TERMS = {
    "turkey":     ["Türk ordusu operasyon", "TSK hava harekâtı", "Bayraktar TB2 saldırı", "KAAN savaş uçağı",
                   "İHA saldırısı Türkiye", "TSK Kuzey Irak operasyon", "Türk Silahlı Kuvvetleri"],
    "israel":     ["IDF צבא ישראל", "כיפת ברזל יירוט", "IDF tsva",
                   "צבא ישראל עזה", "חיל האוויר הישראלי תקיפה", "IDF Gaza operation footage"],
    "iran":       ["سپاه پاسداران عملیات", "موشک ایران آزمایش", "IRGC operation footage",
                   "پهپاد شاهد حمله", "سپاه پاسداران موشک", "ایران پهپاد کامیکازه"],
    "hamas":      ["حماس غزة هجوم", "Hamas Gaza attack", "حماس عملیات"],
    "russia":     ["Российская армия операция", "ВКС удар", "Армия России Украина",
                   "Российская армия наступление", "ВКС бомбардировка", "армия России дроны"],
    "ukraine":    ["ЗСУ бойові дії", "Украина фронт бой", "Ukrainian army combat",
                   "ЗСУ дрони атака", "Украина БПЛА FPV", "Ukrainian FPV drone strike"],
    "syria":      ["الجيش السوري عملية", "Syria military operation footage", "قوات سورية قتال"],
    "iraq":       ["القوات العراقية عملية", "Iraq military footage", "الحشد الشعبي"],
    "yemen":      ["الحوثيون هجوم", "Houthi attack footage", "اليمن ضربة"],
    "saudi":      ["الجيش السعودي عملية", "Saudi Arabia military", "حرب اليمن السعودية"],
    "uae":        ["الإمارات القوات المسلحة", "طيران الإمارات العسكري", "القوات الجوية الإماراتية"],
    "azerbaijan": ["Azərbaycan ordusu hücum", "Azərbaycan Silahlı Qüvvələri", "Qarabağ əməliyyatı"],
    "taiwan":     ["中華民國國軍演習", "台灣軍事演練", "中华民国空军战机", "台湾海峡军演"],
}

# Ülke → askeri terminoloji eşleşmesi
COUNTRY_MILITARY_TERMS = {
    "turkey": ["Turkish Armed Forces", "TSK", "Turkey military", "Bayraktar", "KAAN", "Akinci", "TAI", "Turkish defense", "Turkish Army", "Turkish Navy", "Turkish Air Force"],
    "russia": ["Russian military", "Russian Armed Forces", "Spetsnaz", "S-400", "Su-57", "T-90", "Wagner", "Russian Navy", "Russian airstrike", "Russian troops", "Moscow military"],
    "usa": ["US military", "Pentagon", "US Armed Forces", "USAF", "US Navy", "Marines", "US Army", "American troops", "US warship", "US airstrike", "US defense"],
    "china": ["PLA", "Chinese military", "PLAN", "Chinese navy", "J-20", "DF-41", "Chinese defense", "Chinese troops", "PLA Navy", "Chinese missile", "Beijing military"],
    "iran": ["IRGC", "Iranian military", "Iranian missile", "Shahed drone", "Iran navy", "Iranian defense", "Iranian proxy", "Iran ballistic missile", "IRGC navy", "Iran nuclear facility", "Iran missile test", "Iranian attack drone", "IRGC speedboat", "Iran underground missile base", "Iran vs USA confrontation", "Iran vs Israel airstrike", "Iran retaliation strike", "Natanz nuclear plant", "Iranian warship"],
    "israel": ["IDF", "Israel Defense Forces", "Iron Dome", "Israeli Air Force", "Mossad", "Israeli military", "Israeli airstrike", "IDF ground forces", "Israeli tank", "Merkava tank", "Israeli Navy", "IDF operation", "Israeli F-35", "Israeli strike", "Iron Beam"],
    "palestine": ["Gaza Strip", "Palestinian territory", "Gaza war", "Hamas fighters", "Gaza airstrike", "Gaza bombardment", "West Bank violence", "Palestinian conflict", "Rafah operation", "Gaza ground invasion"],
    "hamas": ["Hamas military wing", "Al-Qassam Brigades", "Hamas rocket launch", "Hamas tunnel", "Hamas attack", "Hamas fighters footage"],
    "hezbollah": ["Hezbollah fighters", "Hezbollah missile launch", "Lebanon Hezbollah", "Hezbollah drone", "Hezbollah attack", "southern Lebanon conflict"],
    "ukraine": ["Ukrainian military", "Ukrainian Armed Forces", "Ukraine frontline", "Ukrainian drone", "Ukraine war", "Ukrainian troops", "Kyiv defense", "Ukrainian artillery", "Ukraine battlefield"],
    "nato": ["NATO forces", "NATO exercise", "NATO military", "Allied forces", "NATO deployment", "NATO troops", "NATO warship", "NATO air defense"],
    "north korea": ["DPRK military", "North Korean missile", "Korean People's Army", "North Korea military", "Kim Jong Un military", "ICBM North Korea"],
    "india": ["Indian military", "Indian Armed Forces", "Indian Navy", "Tejas fighter", "Indian Army", "Indian Air Force", "India defense"],
    "pakistan": ["Pakistan military", "Pakistan Armed Forces", "JF-17", "Pakistan Navy", "Pakistan Army"],
    "uk": ["British military", "Royal Navy", "RAF", "British Armed Forces", "SAS", "British troops", "UK warship"],
    "france": ["French military", "French Armed Forces", "Rafale fighter", "French Navy", "French Foreign Legion"],
    "germany": ["Bundeswehr", "German military", "Leopard tank", "German defense", "German troops"],
    "japan": ["JSDF", "Japan Self-Defense Forces", "Japanese military", "Japanese Navy", "Japan defense"],
    "south korea": ["ROK military", "South Korean military", "K2 tank", "KF-21 fighter", "Korean military"],
    "saudi arabia": ["Saudi military", "Royal Saudi Air Force", "Saudi Arabia defense", "Saudi airstrike", "Arab coalition"],
    "houthi": ["Houthi rebels", "Houthi drone attack", "Houthi missile launch", "Yemen Houthi", "Ansarallah fighters"],
    "jordan": ["Jordanian military", "Jordan Armed Forces", "Jordan air force"],
    "egypt": ["Egyptian military", "Egypt Armed Forces", "Egyptian Navy"],
    "syria": ["Syrian military", "Syria conflict", "Syrian civil war", "Damascus military"],
    "iraq": ["Iraqi military", "Iraq Armed Forces", "Iraqi PMF", "Iraq conflict"],
    "lebanon":    ["Lebanese military", "Lebanon conflict", "Lebanon border", "south Lebanon"],
    "uae":        ["UAE military", "UAEAF", "United Arab Emirates Armed Forces", "UAE F-16", "UAE Mirage fighter",
                   "UAE defense", "UAE special forces", "Emirati military", "UAE air strikes"],
    "azerbaijan": ["Azerbaijani military", "Azerbaijan Armed Forces", "Azerbaijan drone Karabakh",
                   "Azerbaijani Bayraktar", "Azerbaijan offensive footage"],
    "armenia":    ["Armenian military", "Armenian Armed Forces", "Armenia Karabakh footage",
                   "Armenia defense operations"],
    "ethiopia":   ["Ethiopian military", "ENDF footage", "Ethiopia conflict Tigray", "Ethiopian air strike"],
    "taiwan":     ["Taiwanese military", "ROC Armed Forces", "Taiwan Air Force", "Taiwan Navy F-16",
                   "Taiwan military exercise", "Taiwan strait patrol"],
    "sudan":      ["Sudan military", "RSF Sudan footage", "Sudan conflict war footage", "Khartoum fighting"],
    "myanmar":    ["Myanmar military junta", "Tatmadaw footage", "Myanmar civil war", "Myanmar airstrike"],
}

# Silah sistemi → spesifik arama terimleri
WEAPON_SEARCH_TERMS = {
    "f-35": ["F-35 Lightning II flight", "F-35 stealth fighter takeoff", "F-35 combat operations footage", "Israeli F-35 airstrike"],
    "f-22": ["F-22 Raptor dogfight", "F-22 air superiority maneuver", "F-22 formation flight footage"],
    "f-16": ["F-16 Fighting Falcon combat", "F-16 airstrike footage", "F-16 fighter jet operations"],
    "su-57": ["Su-57 Felon stealth fighter", "Sukhoi Su-57 test flight", "Russian 5th gen fighter"],
    "su-35": ["Su-35 Flanker-E dogfight", "Su-35 combat maneuver", "Russian Su-35 operations"],
    "kaan": ["KAAN fighter jet Turkey", "TFX KAAN stealth fighter", "Turkish 5th generation jet"],
    "bayraktar": ["Bayraktar TB2 drone strike", "Bayraktar combat footage Ukraine", "Turkish drone warfare footage"],
    "akinci": ["Bayraktar Akinci UCAV", "Akinci combat drone footage", "Turkish unmanned combat aircraft"],
    "shahed": ["Shahed drone attack footage", "Iranian kamikaze drone", "Shahed-136 strike footage", "Shahed-238 jet drone", "Iran one-way attack drone", "Iranian drone swarm footage"],
    "iran nuclear": ["Iran nuclear enrichment footage", "Natanz nuclear plant aerial", "Iranian centrifuge facility", "Iran uranium enrichment", "IAEA Iran inspection footage"],
    "iran missile": ["Iran ballistic missile launch", "Iranian missile test IRGC", "Shahab missile launch footage", "Fateh missile Iran", "Iran hypersonic missile test", "Fattah hypersonic Iran"],
    "s-400": ["S-400 missile system deployment", "S-400 Triumf launch footage", "Russian air defense S-400"],
    "s-300": ["S-300 missile launch footage", "S-300 air defense system", "anti-aircraft S-300"],
    "patriot": ["Patriot missile intercept", "MIM-104 Patriot battery", "Patriot air defense live fire"],
    "iron dome": ["Iron Dome intercept footage", "Israel Iron Dome missile defense", "Iron Dome rockets incoming"],
    "iron beam": ["Iron Beam laser defense Israel", "Israeli laser weapon system", "directed energy weapon Israel"],
    "merkava": ["Merkava tank Israel", "IDF Merkava battle tank", "Israeli tank operations Gaza"],
    "abrams": ["M1 Abrams tank combat", "Abrams tank live fire range", "M1A2 Abrams armor operations"],
    "leopard": ["Leopard 2 tank combat", "Leopard 2A7 operations", "German tank battle footage"],
    "himars": ["HIMARS rocket system launch", "M142 HIMARS Ukraine footage", "precision rocket artillery HIMARS"],
    "javelin": ["Javelin anti-tank missile firing", "FGM-148 Javelin strike", "portable anti-tank weapon"],
    "qassam": ["Qassam rocket launch Gaza", "Hamas rocket fire Israel", "Palestinian rocket attack footage"],
    "kornet": ["Kornet anti-tank missile", "ATGM Kornet strike footage", "missile vs tank footage"],
    "rpg": ["RPG anti-tank rocket footage", "rocket propelled grenade combat", "RPG urban warfare footage"],
    "hypersonic": ["hypersonic missile test launch", "hypersonic glide vehicle footage", "Mach 5 missile test"],
    "nuclear": ["nuclear missile ICBM launch test", "nuclear submarine patrol", "nuclear warhead footage"],
    "aircraft carrier": ["aircraft carrier flight operations", "carrier strike group underway", "carrier deck fighter launch"],
    "warship": ["warship naval operations footage", "destroyer missile launch at sea", "frigate naval combat footage"],
    "submarine": ["submarine surfacing footage", "submarine missile salvo launch", "nuclear submarine dive footage"],
    "drone": ["military drone strike footage", "combat UAV surveillance footage", "loitering munition attack footage"],
    "helicopter": ["attack helicopter gunship footage", "Apache helicopter combat", "military helicopter assault footage"],
    "tank": ["tank battle live fire exercise", "armored column advance footage", "main battle tank combat operations"],
    "artillery": ["howitzer artillery barrage footage", "self-propelled artillery firing", "rocket artillery salvo footage"],
    "missile": ["ballistic missile launch footage", "cruise missile strike footage", "anti-ship missile test"],
    "radar": ["military radar system footage", "air defense radar tracking", "early warning radar installation"],
    "tunnel": ["Hamas tunnel Gaza footage", "military tunnel complex", "underground tunnel warfare footage"],
    "sniper": ["military sniper footage", "special forces sniper operations", "long range precision shooting footage"],
    # Ukraine conflict weapons
    "atacms":           ["ATACMS missile launch Ukraine", "US long range missile Ukraine strike", "Army Tactical Missile System footage"],
    "storm shadow":     ["Storm Shadow cruise missile Ukraine", "SCALP-EG cruise missile footage", "UK cruise missile Ukraine strike"],
    "lancet":           ["Lancet loitering munition Russia", "Lancet drone strike footage", "Russian kamikaze drone Lancet"],
    "fpv drone":        ["FPV drone strike footage Ukraine", "first person view drone bomb Ukraine", "FPV kamikaze drone combat"],
    "gepard":           ["Gepard anti-aircraft tank Ukraine", "Flakpanzer Gepard firing footage", "German air defense Ukraine"],
    "nasams":           ["NASAMS missile defense Ukraine", "Norwegian air defense system launch", "NASAMS intercept footage"],
    "caesar":           ["CAESAR howitzer artillery France Ukraine", "wheeled artillery self-propelled footage", "CAESAR cannon firing"],
    "m270 mlrs":        ["M270 MLRS rocket launch footage", "multiple launch rocket system fire", "MLRS salvo footage"],
    # Russian weapons
    "kinzhal":          ["Kinzhal hypersonic missile Russia", "MiG-31 Kinzhal launch footage", "Russian air-launched hypersonic"],
    "zircon":           ["Zircon hypersonic missile launch", "Russian Tsirkon cruise missile", "3M22 Zircon sea launch"],
    "sarmat":           ["Sarmat ICBM test launch Russia", "RS-28 Sarmat ballistic missile", "Satan 2 missile footage"],
    "iskander":         ["Iskander missile launch Russia", "9K720 Iskander strike footage", "Russian tactical ballistic missile"],
    "kalibr":           ["Kalibr cruise missile launch", "Russian Kalibr warship salvo", "Russian cruise missile sea launch"],
    "buk":              ["Buk missile system launch", "SA-11 Buk air defense footage", "Russian Buk radar launch"],
    # New platforms
    "b-21 raider":      ["B-21 Raider stealth bomber", "US new stealth bomber footage", "Northrop Grumman B-21 flight"],
    "kf-21":            ["KF-21 Boramae fighter South Korea", "Korean fighter jet KF-21 test flight", "South Korea 4.5 gen fighter"],
    "k2 tank":          ["K2 Black Panther tank South Korea", "K2 main battle tank firing", "Korean tank combat footage"],
    "poseidon":         ["Poseidon nuclear torpedo Russia", "Russian underwater drone nuclear", "Status-6 nuclear weapon footage"],
    "white phosphorus": ["white phosphorus artillery footage", "smoke screen military operation", "incendiary weapon military use"],
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

# Arapça/Türkçe ülke adları → İngilizce key eşlemesi
ARABIC_COUNTRY_ALIASES = {
    "إيران": "iran", "إيراني": "iran", "الحرس الثوري": "iran", "الإيراني": "iran",
    "إسرائيل": "israel", "إسرائيلي": "israel", "الجيش الإسرائيلي": "israel",
    "أمريكا": "usa", "الولايات المتحدة": "usa", "أمريكي": "usa", "البنتاغون": "usa",
    "روسيا": "russia", "روسي": "russia", "الكرملين": "russia",
    "الصين": "china", "صيني": "china", "الجيش الصيني": "china",
    "حزب الله": "hezbollah", "حماس": "hamas", "الحوثيون": "houthi", "الحوثي": "houthi",
    "غزة": "palestine", "الضفة الغربية": "palestine", "فلسطين": "palestine",
    "الإمارات": "uae", "السعودية": "saudi arabia", "تركيا": "turkey", "تركي": "turkey",
    "لبنان": "lebanon", "سوريا": "syria", "العراق": "iraq", "اليمن": "houthi",
    "أوكرانيا": "ukraine", "كوريا الشمالية": "north korea",
}

def _detect_countries(text: str) -> list[str]:
    """Metinden bahsedilen ülkeleri tespit eder (İngilizce + Arapça)."""
    text_lower = text.lower()
    found = set()
    # İngilizce eşleşme
    for country in COUNTRY_MILITARY_TERMS:
        if country in text_lower:
            found.add(country)
        elif any(term.lower() in text_lower for term in COUNTRY_MILITARY_TERMS[country][:2]):
            found.add(country)
    # Arapça alias eşleşme
    for ar_name, en_key in ARABIC_COUNTRY_ALIASES.items():
        if ar_name in text and en_key in COUNTRY_MILITARY_TERMS:
            found.add(en_key)
    return list(found)


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
    "ceasefire":        ["ceasefire agreement signing footage", "soldiers laying down arms footage", "war zone aftermath destruction", "military withdrawal footage", "troops returning base footage"],
    "negotiation":      ["military diplomacy meeting footage", "peace summit defense ministers", "military negotiations table footage", "diplomatic talks security footage", "hostage deal negotiation footage"],
    "sanction":         ["economic sanctions military footage", "arms embargo enforcement footage", "sanctioned military hardware footage", "weapons transfer blocked footage"],
    "nuclear":          ["nuclear ICBM missile launch footage", "nuclear submarine operations footage", "nuclear warhead facility footage", "nuclear test explosion footage", "nuclear site satellite imagery"],
    "missile":          ["ballistic missile launch pad footage", "cruise missile strike building footage", "missile salvo barrage footage", "missile interception footage", "missile trajectory footage"],
    "airstrike":        ["airstrike explosion footage", "fighter jet bombing run footage", "precision guided bomb strike", "aerial bombardment footage", "building collapse airstrike footage"],
    "invasion":         ["military invasion troops crossing border", "armored column advance footage", "amphibious assault landing footage", "paratroopers airborne invasion", "tanks crossing border footage"],
    "offensive":        ["military offensive troops advancing", "infantry assault footage", "combined arms attack footage", "battlefield advance footage", "armored offensive footage"],
    "blockade":         ["naval blockade warship footage", "ships intercepted at sea footage", "maritime blockade enforcement", "coast guard intercept footage", "naval standoff footage"],
    "deployment":       ["troops deployment airfield footage", "soldiers boarding aircraft footage", "military convoy deployment footage", "rapid deployment forces footage", "carrier strike group deployment"],
    "exercise":         ["joint military exercise footage", "combined arms drill footage", "military war games exercise", "multinational exercise troops", "live fire exercise footage"],
    "summit":           ["NATO summit footage", "defense ministers meeting footage", "military alliance summit footage", "security council meeting footage"],
    "attack":           ["military attack operation footage", "combat strike footage", "surprise attack footage", "ambush military footage", "terrorist attack response footage"],
    "retreat":          ["military retreat troops footage", "tactical withdrawal footage", "soldiers retreating footage", "military pullback convoy footage"],
    "occupation":       ["military occupation checkpoint footage", "soldiers checkpoint city footage", "occupied territory patrol footage", "urban military occupation footage"],
    "ground invasion":  ["ground invasion troops footage", "infantry urban warfare footage", "IDF ground operation Gaza", "urban combat footage", "soldiers entering city footage"],
    "bombing":          ["bombing raid footage", "air bombardment explosion", "building bombed footage", "bomb damage aerial footage", "precision bombing footage"],
    "assassination":    ["military targeted killing footage", "drone strike assassination footage", "special forces operation footage"],
    "hostage":          ["hostage rescue operation footage", "kidnapped soldiers footage", "POW prisoner exchange footage"],
    "humanitarian":     ["humanitarian corridor footage", "civilian evacuation war zone", "refugee camp footage", "aid trucks war zone footage", "civilian casualties war footage"],
    "protest":          ["anti-war protest footage", "military protest rally footage", "soldiers protest footage"],
    "border":           ["border military standoff footage", "troops border deployment footage", "border crossing military footage", "border tension soldiers footage"],
    "urban warfare":    ["urban combat footage", "street fighting footage", "soldiers clearing building footage", "infantry city warfare footage", "house to house combat footage"],
    "conflict":         ["military conflict footage", "frontline combat footage", "war zone footage", "active combat footage", "battlefield warfare footage"],
    "drone warfare":    ["FPV drone strike Ukraine footage", "loitering munition attack footage", "drone swarm military footage", "kamikaze drone impact footage", "drone intercepted footage"],
    "electronic warfare": ["electronic warfare jamming footage", "military EW system footage", "GPS jamming military", "electronic warfare vehicle footage"],
    "siege":            ["city under siege military footage", "siege warfare frontline", "encircled city military footage", "supply convoy blocked footage"],
    "naval battle":     ["naval battle warship footage", "naval confrontation footage", "warships firing missiles at sea", "naval standoff footage", "coast guard vs navy footage"],
    "naval blockade":   ["naval blockade enforcement footage", "Red Sea ship attack Houthi", "maritime interdiction footage"],
    "trench warfare":   ["trench warfare footage Ukraine", "soldiers trench assault footage", "frontline trench positions footage"],
    "mine clearing":    ["mine clearing demining footage", "explosive ordnance disposal footage", "military mine sweep footage"],
    "cyber attack":     ["critical infrastructure attack footage", "power grid failure military sabotage", "cyber warfare operations center"],
    "space":            ["military satellite launch footage", "anti-satellite missile test footage", "GPS military satellite footage"],
}

# Savaş alanı/coğrafi konumlar → görsel arama terimleri
LOCATION_VISUAL_TERMS = {
    # Gaza
    "rafah":            ["Rafah Gaza military footage", "IDF Rafah operation", "Rafah crossing destruction"],
    "khan younis":      ["Khan Younis IDF operation footage", "southern Gaza combat footage"],
    "northern gaza":    ["northern Gaza airstrikes footage", "IDF north Gaza ground forces"],
    "gaza city":        ["Gaza City bombing footage", "Gaza urban warfare footage"],
    # Ukraine
    "bakhmut":          ["Bakhmut battle footage", "Wagner Bakhmut combat", "Bakhmut frontline footage"],
    "kharkiv":          ["Kharkiv shelling footage", "Ukraine Kharkiv frontline", "Kharkiv Russian strike footage"],
    "zaporizhzhia":     ["Zaporizhzhia frontline Ukraine", "Zaporizhzhia nuclear plant tension"],
    "donbas":           ["Donbas frontline footage", "eastern Ukraine combat", "Donbas artillery footage"],
    "avdiivka":         ["Avdiivka battle footage", "Ukraine Avdiivka defense footage"],
    "kursk":            ["Kursk Ukraine incursion footage", "Ukrainian troops Kursk Russia"],
    # Seas / Straits
    "red sea":          ["Red Sea Houthi attack footage", "US Navy Red Sea operations", "Red Sea cargo ship attack"],
    "strait of hormuz": ["Strait of Hormuz naval standoff", "Iran IRGC speedboat Hormuz", "Hormuz tanker seizure"],
    "south china sea":  ["South China Sea military confrontation", "PLA Navy South China Sea patrol", "Philippines China sea clash"],
    "taiwan strait":    ["Taiwan Strait military exercise", "China Taiwan strait warships", "PLAN Taiwan strait patrol"],
    "black sea":        ["Black Sea naval warfare", "Russia Ukraine Black Sea battle", "Ukrainian naval drone Black Sea"],
    # Middle East
    "beirut":           ["Beirut military footage", "Lebanon Beirut airstrike", "Hezbollah south Lebanon footage"],
    "homs":             ["Syria Homs military footage", "Syrian airstrike Homs"],
    "aleppo":           ["Aleppo battle footage", "Syria Aleppo military operations"],
    "fallujah":         ["Fallujah battle urban warfare", "Iraq Fallujah military footage"],
    # Other
    "karabakh":         ["Nagorno-Karabakh offensive footage", "Azerbaijan Karabakh drone attack", "Karabakh 2020 war footage"],
    "tigray":           ["Tigray conflict Ethiopia footage", "Tigray war military footage"],
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
        'Return JSON with these fields — ALL VALUES MUST BE IN ENGLISH regardless of input language:\n'
        '{"countries": ["country1", "country2"], '
        '"event_type": "one of: ceasefire/negotiation/sanction/nuclear/missile/airstrike/invasion/offensive/blockade/deployment/exercise/summit/attack/retreat/occupation/conflict/drone warfare/siege/naval battle/trench warfare/electronic warfare/cyber attack/space", '
        '"weapons": ["weapon1 in english"], '
        '"locations": ["city or region in english"], '
        '"key_actors": ["military unit or leader in english"]}'
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
        loc_lower = loc.lower()
        matched = False
        for known_loc, loc_terms in LOCATION_VISUAL_TERMS.items():
            if known_loc in loc_lower or loc_lower in known_loc:
                for lt in loc_terms[:2]:
                    queries.append(FootageQuery(lt, relevance=0.88, source="entity_location", scene_index=scene_index))
                matched = True
                break
        if not matched:
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

    system = """You are an expert military video editor sourcing B-roll footage on YouTube for a news analysis short.
Given a scene from a military news video, generate highly specific YouTube search queries to find
VISUALLY MATCHING Creative Commons or public domain footage.

CRITICAL RULES:
1. Queries must target footage that ACTUALLY EXISTS on YouTube — real events, real military hardware
2. Prioritize: official military/government channels, Reuters, AP, AFP, Al Jazeera, BBC footage
3. Use EXACT military terminology: unit names, weapon model numbers, operation names, locations
4. For airstrikes/bombardment: include explosion, smoke, damage aftermath queries
5. For ground operations: include infantry advance, armored column, urban combat queries
6. For specific weapons: use exact model name + action (e.g. "Iron Dome missile intercept footage")
7. For negotiations/diplomacy: use military buildup, naval presence, troops at border as visual proxy
8. Include the specific country/region in EVERY query for maximum relevance
9. Mix query types: very specific (weapon+country+action) + moderately specific (event+location) + visual fallback

Reply ONLY in JSON — no explanation:
{"queries": ["query 1", "query 2", "query 3", "query 4", "query 5", "query 6", "query 7", "query 8", "query 9", "query 10"]}"""

    prompt = (
        f"Scene {scene_index + 1} text:\n\"{scene_text}\"\n\n"
        f"Full video context: {full_context[:300]}"
        f"{entity_hint}\n\n"
        f"Generate 10 YouTube B-roll search queries for this scene. "
        f"Be extremely specific — include country names, weapon models, location names, military unit names. "
        f"Think about what a viewer would see on screen that best represents this scene visually."
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
    scenes = _split_narration_to_scenes(narration, num_scenes=5)
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

    # 4) Recency sorguları — yıl ekleyerek YouTube'da daha güncel sonuçlar
    countries = entities.get("countries", [])
    event = entities.get("event_type", "")
    for country in countries[:2]:
        for yr in [str(_CURRENT_YEAR), str(_PREV_YEAR)]:
            base = EVENT_VISUAL_TERMS.get(event, ["military operation footage"])[0]
            all_queries.append(FootageQuery(
                query=f"{country} {base} {yr}",
                relevance=0.88, source="recency", scene_index=0,
            ))

    # 5) Alternatif dil sorguları — bazı içerikler yalnızca TR/AR/RU'da bulunuyor
    for country in countries[:2]:
        ck = country.lower()
        for alt_q in ALT_LANG_TERMS.get(ck, [])[:2]:
            all_queries.append(FootageQuery(
                query=alt_q, relevance=0.82, source="alt_lang", scene_index=0,
            ))

    # 6) Orijinal search_keywords (fallback — düşük relevance)
    for kw in original_keywords:
        q = kw if ("footage" in kw.lower() or "operations" in kw.lower()) else f"{kw} footage"
        all_queries.append(FootageQuery(query=q, relevance=0.55, source="original"))

    # 7) Blacklist filtresi: generic/alakasız sorgular çıkarılır
    def _is_blacklisted(query_text: str) -> bool:
        ql = query_text.lower()
        return any(b in ql for b in QUERY_BLACKLIST_TERMS)

    # 8) Deduplicate (query metni bazında) + relevance sıralaması
    seen: set[str] = set()
    unique_queries: list[FootageQuery] = []
    for q in all_queries:
        key = q.query.lower().strip()
        if key not in seen and not _is_blacklisted(q.query):
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

    # İlk 30 sorguyu keyword olarak döndür
    keywords = [q.query for q in queries[:30]]

    if not keywords:
        # Fallback: orijinal search_keywords
        keywords = script.get("search_keywords", [])

    return keywords


def get_scene_based_keywords(script: dict, min_per_scene: int = 20) -> list[list[str]]:
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
    scene_groups: list[list[str]] = [[], [], [], [], []]
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
