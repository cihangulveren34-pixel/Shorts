"""
rss_monitor.py — Günlük savaş/jeopolitik haberlerini izler, analiz videosu konusu üretir.

RSS beslemelerinden güncel askeri gelişmeleri çeker, Gemini ile
"Bu ne anlama geliyor?" tarzı analiz videosu konusuna dönüştürür.

Kaynaklar:
  - Google News (military, geopolitics, defense)
  - Reuters / Al Jazeera / BBC (conflict, military)
  - Defense News RSS

Konu formatları:
  - "Turkey just tested [weapon]: Here's what it means"
  - "Iran's latest move changes EVERYTHING in the Middle East"
  - "Why [country]'s new [weapon] should terrify [country]"
"""

import json
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, date, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional

import requests

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

TIMEOUT = 15
MONITOR_STATE_PATH = "rss_state.json"
# Kaç saatlik haberler işlensin (varsayılan: son 48 saat — günlük pipeline uyumlu)
NEWS_MAX_AGE_HOURS = int(os.environ.get("NEWS_MAX_AGE_HOURS", "48"))

_YEAR = str(datetime.now().year)

RSS_FEEDS = [
    # --- Doğrudan wire service / haber ajansı RSS'leri (en güncel, en hızlı) ---
    {
        "name": "Reuters — World News",
        "url": "https://feeds.reuters.com/reuters/topNews",
        "keywords": ["military", "war", "missile", "troops", "attack", "strike", "conflict", "ceasefire", "sanctions", "nuclear"],
    },
    {
        "name": "BBC — World",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "keywords": ["military", "war", "conflict", "missile", "troops", "attack", "nato", "ukraine", "russia", "china", "iran"],
    },
    {
        "name": "Al Jazeera — News",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "keywords": ["military", "war", "missile", "troops", "conflict", "attack", "israel", "iran", "ukraine", "russia"],
    },
    {
        "name": "Kyiv Independent — War Updates",
        "url": "https://kyivindependent.com/feed/",
        "keywords": ["ukraine", "russia", "war", "frontline", "attack", "drone", "missile", "ceasefire", "troops", "offensive"],
    },
    {
        "name": "Defense News",
        "url": "https://www.defensenews.com/arc/outboundfeeds/rss/",
        "keywords": ["military", "weapon", "missile", "drone", "navy", "army", "air force", "defense", "pentagon", "nato"],
    },
    {
        "name": "Military Times",
        "url": "https://www.militarytimes.com/arc/outboundfeeds/rss/",
        "keywords": ["military", "weapon", "troops", "army", "navy", "marine", "air force", "pentagon", "defense"],
    },
    # --- Google News arama RSS'leri (geniş kapsam) ---
    {
        "name": "Google News — Military",
        "url": f"https://news.google.com/rss/search?q=military+weapon+defense+{_YEAR}&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["military", "weapon", "missile", "drone", "fighter", "tank", "navy", "army", "defense"],
    },
    {
        "name": "Google News — Turkey Military",
        "url": "https://news.google.com/rss/search?q=Turkey+military+drone+bayraktar+kaan&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["turkey", "turkish", "bayraktar", "kaan", "drone", "defense"],
    },
    {
        "name": "Google News — Iran Military",
        "url": "https://news.google.com/rss/search?q=Iran+military+missile+nuclear+drone&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["iran", "missile", "nuclear", "drone", "hormuz", "irgc"],
    },
    {
        "name": "Google News — Russia Ukraine War",
        "url": "https://news.google.com/rss/search?q=Russia+Ukraine+war+military+weapon&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["russia", "ukraine", "war", "missile", "drone", "front", "offensive"],
    },
    {
        "name": "Google News — Ukraine Latest News",
        "url": "https://news.google.com/rss/search?q=ukraine+war+latest+news+today&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["ukraine", "war", "latest", "frontline", "attack", "counterattack", "ceasefire", "peace"],
    },
    {
        "name": "Google News — Russia Ukraine Update",
        "url": "https://news.google.com/rss/search?q=russia+ukraine+war+update+ceasefire+peace+talks&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["ukraine", "russia", "ceasefire", "peace", "negotiations", "offensive", "troops", "frontline"],
    },
    {
        "name": "Google News — Ukraine Battlefield",
        "url": "https://news.google.com/rss/search?q=ukraine+battlefield+frontline+russian+troops+advance&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["battlefield", "frontline", "troops", "advance", "retreat", "capture", "ukraine", "russia"],
    },
    {
        "name": "Google News — China Taiwan",
        "url": "https://news.google.com/rss/search?q=China+Taiwan+military+navy+south+china+sea&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["china", "taiwan", "navy", "carrier", "military", "pla"],
    },
    {
        "name": "Google News — Israel Middle East",
        "url": "https://news.google.com/rss/search?q=Israel+Iran+military+strike+missile+defense&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["israel", "iran", "strike", "missile", "hezbollah", "hamas", "iron dome"],
    },
    {
        "name": "Google News — Iran vs USA",
        "url": "https://news.google.com/rss/search?q=Iran+United+States+military+confrontation+nuclear+sanctions&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["iran", "united states", "us", "nuclear deal", "sanctions", "irgc", "hormuz", "confrontation", "american", "pentagon iran"],
    },
    {
        "name": "Google News — Iran vs Israel",
        "url": "https://news.google.com/rss/search?q=Iran+Israel+war+attack+retaliation+missile+drone&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["iran", "israel", "retaliation", "attack", "missile", "drone", "idf", "mossad", "nuclear", "shadow war", "proxy"],
    },
    {
        "name": "Google News — Iran Nuclear Program",
        "url": "https://news.google.com/rss/search?q=Iran+nuclear+program+enrichment+IAEA+weapon&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["iran", "nuclear", "enrichment", "iaea", "uranium", "bomb", "weapon grade", "natanz", "fordow"],
    },
    {
        "name": "Google News — Iran IRGC Proxy",
        "url": "https://news.google.com/rss/search?q=IRGC+Iran+proxy+Hezbollah+Houthi+Hamas+attack&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["irgc", "iran", "proxy", "hezbollah", "houthi", "hamas", "axis of resistance", "revolutionary guard"],
    },
    {
        "name": "Google News — NATO Defense",
        "url": "https://news.google.com/rss/search?q=NATO+defense+military+spending+weapon&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["nato", "defense", "military", "alliance", "spending"],
    },
    {
        "name": "Google News — Hypersonic Nuclear",
        "url": "https://news.google.com/rss/search?q=hypersonic+missile+nuclear+weapon+test&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["hypersonic", "nuclear", "missile", "test", "icbm", "warhead"],
    },
    {
        "name": "Google News — AI Warfare Drones",
        "url": "https://news.google.com/rss/search?q=AI+warfare+autonomous+drone+military+robot&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["ai", "autonomous", "drone", "robot", "warfare", "swarm"],
    },
    {
        "name": "Google News — Gulf Military UAE Saudi",
        "url": "https://news.google.com/rss/search?q=UAE+Saudi+Arabia+military+arms+deal+defense&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["uae", "saudi", "qatar", "arms", "defense", "deal", "military"],
    },
    # --- Amerika / ABD askeri operasyonları ---
    {
        "name": "Google News — US Military Operations",
        "url": "https://news.google.com/rss/search?q=US+military+operation+airstrike+troops+deployed&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["us military", "american", "pentagon", "airstrike", "troops", "deployed", "operation", "special forces", "centcom", "pacom"],
    },
    {
        "name": "Google News — US Navy Carrier Strike",
        "url": "https://news.google.com/rss/search?q=US+navy+carrier+strike+group+deployed+warship&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["carrier", "strike group", "navy", "warship", "destroyer", "submarine", "7th fleet", "6th fleet", "indo-pacific"],
    },
    {
        "name": "Google News — US Air Force Stealth B-21",
        "url": "https://news.google.com/rss/search?q=US+air+force+B-21+F-35+stealth+bomber+fighter&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["b-21", "b-2", "f-35", "f-22", "stealth", "bomber", "air force", "usaf", "aircraft"],
    },
    {
        "name": "Google News — US Pentagon Defense Budget",
        "url": "https://news.google.com/rss/search?q=Pentagon+defense+budget+weapon+contract+military+spending&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["pentagon", "defense budget", "contract", "spending", "lockheed", "raytheon", "northrop", "general dynamics", "boeing defense"],
    },
    {
        "name": "Google News — US Special Forces SOCOM",
        "url": "https://news.google.com/rss/search?q=US+special+forces+SOCOM+Delta+Force+Rangers+operation&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["special forces", "socom", "delta force", "rangers", "seal", "green berets", "psyop", "covert", "classified"],
    },
    {
        "name": "Google News — US Middle East Houthi Yemen",
        "url": "https://news.google.com/rss/search?q=US+military+Houthi+Yemen+Red+Sea+airstrike&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["houthi", "yemen", "red sea", "airstrike", "us navy", "centcom", "shipping", "tanker", "drone attack"],
    },
    {
        "name": "Google News — US China Pacific Tension",
        "url": "https://news.google.com/rss/search?q=US+China+military+Pacific+Taiwan+strait+confrontation&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["us china", "pacific", "taiwan strait", "south china sea", "confrontation", "indopacom", "freedom of navigation"],
    },
    {
        "name": "Google News — US Sanctions Arms Embargo",
        "url": "https://news.google.com/rss/search?q=US+sanctions+arms+embargo+military+aid+weapon+transfer&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["sanctions", "arms embargo", "military aid", "weapon transfer", "defense package", "lend-lease", "military assistance"],
    },
    {
        "name": "Stars and Stripes — US Military News",
        "url": "https://www.stripes.com/arc/outboundfeeds/rss/",
        "keywords": ["military", "troops", "deployment", "operation", "pentagon", "army", "navy", "air force", "marines", "combat"],
    },
]

# Alakasız içerik filtreleri
EXCLUDE_KEYWORDS = [
    "stock", "crypto", "bitcoin", "celebrity", "sports", "football",
    "soccer", "basketball", "entertainment", "movie", "film", "music",
    "album", "singer", "actor", "fashion", "weather", "recipe",
]

# Gemini ile haber → analiz konusu dönüştürme prompt'u
NEWS_TO_TOPIC_PROMPT = """You generate VIRAL YouTube Shorts topics from breaking military/geopolitics news.

Here are today's headlines:
{headlines}

Convert these into {count} YouTube Shorts topics. Each topic should be an ANALYSIS angle:
- "What does [event] mean for [region/country]?"
- "[Country] just [action]: Here's why it changes everything"
- "Why [weapon/event] should terrify [country]"
- "[Event] explained: What nobody is telling you"
- "The REAL reason behind [event]"
- "America's [operation/weapon/move]: What it really means"
- "Why the US [action] changes everything in [region]"
- "The Pentagon just [action]: Here's what nobody is saying"

RULES:
- Focus on ANALYSIS and IMPLICATIONS, not just restating the news
- Make it sound URGENT and TERRIFYING
- Use specific names, weapons, countries (include US military actions when relevant)
- Cover US operations, deployments, airstrikes, carrier movements, sanctions
- Each topic must create massive CURIOSITY
- Topics must work as standalone Shorts (viewer doesn't need to know the news)
- NO ancient history — ONLY current events (2024-2025)
- Mix "What does this mean?" analysis with "What if this escalates?" scenarios

Return ONLY a JSON array of strings:
["Topic 1", "Topic 2", ...]"""


def _load_state() -> dict:
    if os.path.exists(MONITOR_STATE_PATH):
        with open(MONITOR_STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"seen_titles": [], "last_run": None}


def _save_state(state: dict) -> None:
    with open(MONITOR_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _normalize_title(title: str) -> str:
    """Başlığı karşılaştırma için normalize eder: küçük harf, özel karakter yok."""
    title = title.lower().strip()
    # Unicode normalizasyonu
    title = unicodedata.normalize("NFKD", title)
    # Özel karakterleri kaldır, boşluklara dönüştür
    title = re.sub(r"[^\w\s]", " ", title)
    # Çoklu boşlukları tek boşluğa indir
    title = re.sub(r"\s+", " ", title).strip()
    return title


def _parse_pub_date(date_str: str) -> Optional[datetime]:
    """RSS pubDate string'ini datetime nesnesine çevirir."""
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str.strip())
    except Exception:
        pass
    # Bazı feed'ler ISO 8601 kullanır
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str.strip()[:19], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _is_recent(pub_date_str: str, max_hours: int = NEWS_MAX_AGE_HOURS) -> bool:
    """Haberin son max_hours saat içinde yayınlanıp yayınlanmadığını kontrol eder."""
    if not pub_date_str:
        # Tarih yoksa dahil et (dışlamak yerine güvenli taraf)
        return True
    dt = _parse_pub_date(pub_date_str)
    if dt is None:
        return True
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt) <= timedelta(hours=max_hours)


def _fetch_rss(url: str) -> list[dict]:
    """RSS URL'sini fetch edip item listesi döndürür (pubDate dahil)."""
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers={
            "User-Agent": "Mozilla/5.0 (compatible; WAR-SHORTS-Bot/1.0)"
        })
        if resp.status_code != 200:
            return []

        root = ET.fromstring(resp.content)
        items = []

        for item in root.findall(".//item"):
            title_el = item.find("title")
            desc_el = item.find("description")
            pub_el = item.find("pubDate")
            if title_el is not None and title_el.text:
                items.append({
                    "title": title_el.text.strip(),
                    "description": desc_el.text.strip() if desc_el is not None and desc_el.text else "",
                    "pub_date": pub_el.text.strip() if pub_el is not None and pub_el.text else "",
                })

        # Atom feed desteği
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns)
            updated_el = entry.find("atom:updated", ns)
            if title_el is not None and title_el.text:
                items.append({
                    "title": title_el.text.strip(),
                    "description": summary_el.text.strip() if summary_el is not None and summary_el.text else "",
                    "pub_date": updated_el.text.strip() if updated_el is not None and updated_el.text else "",
                })

        return items
    except Exception as e:
        print(f"[rss] Fetch hatası ({url[:60]}): {e}")
        return []


def _is_relevant(title: str, desc: str, keywords: list[str]) -> bool:
    """Başlığın askeri/jeopolitik içerikle alakalı olup olmadığını kontrol eder."""
    combined = (title + " " + desc).lower()

    for excl in EXCLUDE_KEYWORDS:
        if excl in combined:
            return False

    if keywords:
        return any(kw.lower() in combined for kw in keywords)

    # Genel askeri/jeopolitik tespiti
    military_kws = [
        "military", "war", "missile", "drone", "nuclear", "weapon",
        "army", "navy", "air force", "fighter", "bomb", "strike",
        "nato", "troops", "conflict", "invasion", "attack",
        "defense", "sanctions", "escalat", "tension", "geopolit",
        "ukraine", "russia", "china", "taiwan", "iran", "israel",
        "turkey", "saudi", "uae", "korea", "hypersonic", "stealth",
        "submarine", "carrier", "cyber", "satellite",
        # ABD / Amerika askeri operasyonları
        "pentagon", "centcom", "pacom", "indopacom", "socom",
        "us military", "american military", "us army", "us navy", "us air force",
        "us marines", "us troops", "us forces", "us airstrike", "us strike",
        "deployed", "deployment", "operation ", "special forces",
        "delta force", "navy seal", "green beret", "ranger",
        "b-21", "b-2", "f-35", "f-22", "a-10", "ac-130",
        "uss ", "carrier strike", "7th fleet", "6th fleet", "5th fleet",
        "houthi", "red sea", "freedom of navigation",
        "lockheed", "raytheon", "northrop", "general dynamics",
        "arms deal", "military aid", "defense package", "lend-lease",
    ]
    return any(kw in combined for kw in military_kws)


def _headlines_to_topics_gemini(headlines: list[str], count: int = 8) -> list[str]:
    """Gemini ile haber başlıklarını analiz videosu konularına dönüştürür."""
    if not GEMINI_AVAILABLE:
        print("[rss] google-generativeai kurulu değil, fallback kullanılıyor.")
        return _headlines_to_topics_fallback(headlines, count)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[rss] GEMINI_API_KEY yok, fallback kullanılıyor.")
        return _headlines_to_topics_fallback(headlines, count)

    try:
        client = genai.Client(api_key=api_key)
        headlines_text = "\n".join(f"- {h}" for h in headlines[:20])
        prompt = NEWS_TO_TOPIC_PROMPT.format(headlines=headlines_text, count=count)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.9,
                max_output_tokens=1024,
            ),
        )
        raw = response.text.strip()
        topics = json.loads(raw)
        if isinstance(topics, list):
            return [t.strip() for t in topics if isinstance(t, str) and len(t) > 15][:count]
        return []

    except json.JSONDecodeError:
        print("[rss] Gemini JSON parse hatası, fallback kullanılıyor.")
        return _headlines_to_topics_fallback(headlines, count)
    except Exception as e:
        print(f"[rss] Gemini hatası: {e}")
        return _headlines_to_topics_fallback(headlines, count)


def _headlines_to_topics_fallback(headlines: list[str], count: int = 8) -> list[str]:
    """Gemini yoksa kural bazlı dönüştürme."""
    topics = []
    templates = [
        "{headline}: Here's What It Means for the World",
        "Why {headline} Changes Everything",
        "{headline}: The Analysis Nobody Is Giving You",
        "What {headline} Really Means for the Future",
    ]

    for i, headline in enumerate(headlines[:count]):
        # Başlığı temizle
        clean = re.sub(r"\s*[-|:]\s*.*$", "", headline).strip()
        if len(clean) < 15:
            continue
        template = templates[i % len(templates)]
        topics.append(template.format(headline=clean[:70]))

    return topics


# RSS konuları bu prefix ile işaretlenir → script_gen news_analysis formatı kullanır
NEWS_TOPIC_PREFIX = "[NEWS] "


def _load_used_topics_normalized() -> set:
    """used_topics.json'daki konuları normalize edilmiş set olarak döndürür."""
    path = "used_topics.json"
    if not os.path.exists(path):
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        used = data.get("used", [])
        result = set()
        for t in used:
            t_norm = t.lower().strip()
            if t_norm.startswith("[news] "):
                t_norm = t_norm[7:]
            result.add(t_norm)
        return result
    except Exception:
        return set()


def _update_topic_pool(new_topics: list[str]) -> int:
    """Yeni konuları [NEWS] prefix'i ile topic_pool.json'a ekler.
    used_topics.json'daki konularla çakışanları atlar."""
    pool_path = "topic_pool.json"
    try:
        with open(pool_path, encoding="utf-8") as f:
            pool = json.load(f)
    except FileNotFoundError:
        pool = []

    existing = {t.lower() for t in pool}
    used_normalized = _load_used_topics_normalized()
    added = 0
    for topic in new_topics:
        tagged = f"{NEWS_TOPIC_PREFIX}{topic}"
        topic_norm = topic.lower().strip()
        # Hem havuzda hem kullanılmış listesinde yoksa ekle
        if topic_norm not in existing and topic_norm not in used_normalized and len(topic) > 15:
            pool.append(tagged)
            existing.add(topic_norm)
            added += 1

    with open(pool_path, "w", encoding="utf-8") as f:
        json.dump(pool, f, indent=2, ensure_ascii=False)

    return added


def monitor_and_update(max_topics: int = 10) -> dict:
    """
    RSS beslemelerini tara, Gemini ile analiz konusu üret, topic_pool.json'a ekle.

    Returns:
        {"topics_found": int, "topics_added": int, "sources_checked": int}
    """
    state = _load_state()
    # Hem orijinal başlıkları hem normalize edilmiş hallerini tut
    seen_raw = set(state.get("seen_titles", []))
    seen_normalized = {_normalize_title(t) for t in seen_raw}

    all_headlines = []
    skipped_old = 0
    skipped_dup = 0

    for feed in RSS_FEEDS:
        print(f"[rss] Taranıyor: {feed['name']}")
        items = _fetch_rss(feed["url"])
        for item in items:
            title = item["title"]
            pub_date = item.get("pub_date", "")

            # Tarih filtresi: sadece son 48 saat
            if not _is_recent(pub_date):
                skipped_old += 1
                continue

            # Dedup: normalize edilmiş başlıkla karşılaştır
            norm = _normalize_title(title)
            if norm in seen_normalized:
                skipped_dup += 1
                continue

            if not _is_relevant(title, item["description"], feed["keywords"]):
                continue

            all_headlines.append(title)
            seen_raw.add(title)
            seen_normalized.add(norm)

    print(f"[rss] {len(all_headlines)} alakalı haber bulundu "
          f"({skipped_old} eski, {skipped_dup} tekrar atlandı)")

    if not all_headlines:
        state["last_run"] = datetime.now(timezone.utc).isoformat()
        _save_state(state)
        return {"topics_found": 0, "topics_added": 0, "sources_checked": len(RSS_FEEDS)}

    # Gemini ile analiz konularına dönüştür
    topics = _headlines_to_topics_gemini(all_headlines, count=max_topics)
    print(f"[rss] {len(topics)} analiz konusu üretildi")

    # topic_pool.json güncelle
    added = _update_topic_pool(topics)

    # State güncelle
    state["seen_titles"] = list(seen_raw)[-500:]
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    result = {
        "topics_found": len(topics),
        "topics_added": added,
        "sources_checked": len(RSS_FEEDS),
        "sample_topics": topics[:3],
    }
    print(f"[rss] Tamamlandı: {added} yeni analiz konusu eklendi → topic_pool.json")
    return result


if __name__ == "__main__":
    result = monitor_and_update()
    print(json.dumps(result, indent=2, ensure_ascii=False))
