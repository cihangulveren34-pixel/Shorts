"""
rss_monitor.py — Haber RSS beslemelerini izleyerek güncel konu önerir.

Tarih, savaş ve "what if" içerikleriyle ilgili RSS beslemelerini tarar,
trend olan konuları topic_pool.json'a ekler.

Besleme kaynakları (ücretsiz, kayıt gerekmez):
  - BBC History RSS
  - History.com RSS
  - Ancient History Encyclopedia
  - Wikipedia Current Events
  - Google News (history/war) RSS

Ayrıca Wikipedia "On This Day" API'sini kullanır:
  Her gün o günün tarihi olaylarından konu üretir.
"""

import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, date, timezone
from typing import Optional

import requests

TIMEOUT = 15
MONITOR_STATE_PATH = "rss_state.json"

RSS_FEEDS = [
    {
        "name": "BBC History",
        "url": "https://feeds.bbci.co.uk/news/topics/c7zzmg45lnyt/rss.xml",
        "keywords": ["war", "battle", "history", "empire", "ancient", "medieval"],
    },
    {
        "name": "Ancient History Encyclopedia",
        "url": "https://www.worldhistory.org/feeds/articles/",
        "keywords": [],  # Tüm makaleler tarihle ilgili
    },
    {
        "name": "Google News — War History",
        "url": "https://news.google.com/rss/search?q=war+history+what+if&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["what if", "war", "battle", "empire"],
    },
    {
        "name": "Google News — Ancient History",
        "url": "https://news.google.com/rss/search?q=ancient+history+discovery&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["ancient", "discovery", "archaeolog"],
    },
    {
        "name": "Google News — Current Conflicts",
        "url": "https://news.google.com/rss/search?q=war+conflict+military+operation&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["war", "conflict", "military", "invasion", "attack", "troops", "missile", "drone", "ceasefire", "NATO"],
    },
    {
        "name": "Google News — Geopolitics",
        "url": "https://news.google.com/rss/search?q=geopolitics+military+tension+what+if&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["tension", "military", "nuclear", "alliance", "sanctions", "escalat"],
    },
    {
        "name": "Reuters — World Conflicts",
        "url": "https://news.google.com/rss/search?q=site:reuters.com+war+conflict&hl=en-US&gl=US&ceid=US:en",
        "keywords": ["war", "conflict", "military", "crisis"],
    },
]

# "What if" konu üretim kalıpları
WHATIF_TEMPLATES = [
    "What if {subject} had {action}?",
    "What if {subject} never {action}?",
    "What if {subject} won the {battle}?",
    "What if {subject} lost at {battle}?",
]

# Yaygın konu filtre kelimeleri (alakasız haberleri eler)
EXCLUDE_KEYWORDS = [
    "stock", "crypto", "bitcoin", "celebrity", "sports", "football",
    "soccer", "basketball", "entertainment", "movie", "film", "music",
    "album", "singer", "actor", "fashion",
]


def _load_state() -> dict:
    if os.path.exists(MONITOR_STATE_PATH):
        with open(MONITOR_STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"seen_titles": [], "last_run": None}


def _save_state(state: dict) -> None:
    with open(MONITOR_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _fetch_rss(url: str) -> list[dict]:
    """RSS URL'sini fetch edip item listesi döndürür."""
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers={
            "User-Agent": "Mozilla/5.0 (compatible; WAR-SHORTS-Bot/1.0)"
        })
        if resp.status_code != 200:
            return []

        root = ET.fromstring(resp.content)
        items = []

        # Standart RSS
        for item in root.findall(".//item"):
            title_el = item.find("title")
            desc_el = item.find("description")
            link_el = item.find("link")
            if title_el is not None and title_el.text:
                items.append({
                    "title": title_el.text.strip(),
                    "description": desc_el.text.strip() if desc_el is not None and desc_el.text else "",
                    "link": link_el.text.strip() if link_el is not None and link_el.text else "",
                })

        # Atom feed desteği
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns)
            if title_el is not None and title_el.text:
                items.append({
                    "title": title_el.text.strip(),
                    "description": summary_el.text.strip() if summary_el is not None and summary_el.text else "",
                    "link": "",
                })

        return items
    except Exception as e:
        print(f"[rss] Fetch hatası ({url[:60]}): {e}")
        return []


def _is_history_relevant(title: str, desc: str, keywords: list[str]) -> bool:
    """Başlık + açıklamanın tarih/savaş içeriğiyle alakalı olup olmadığını kontrol eder."""
    combined = (title + " " + desc).lower()

    # Alakasız içerikleri ele
    for excl in EXCLUDE_KEYWORDS:
        if excl in combined:
            return False

    # Beslemeye özgü filtre
    if keywords:
        return any(kw.lower() in combined for kw in keywords)

    # Genel tarih/savaş/güncel çatışma tespiti
    history_kws = ["war", "battle", "empire", "ancient", "history", "king", "queen",
                   "army", "conquest", "invasion", "revolution", "dynasty", "medieval",
                   "roman", "greek", "egypt", "ottoman", "mongol", "napoleon",
                   "conflict", "military", "troops", "missile", "drone", "nuclear",
                   "nato", "sanctions", "ceasefire", "escalat", "tension", "geopolit",
                   "ukraine", "russia", "china", "taiwan", "iran", "israel", "korea"]
    return any(kw in combined for kw in history_kws)


def _extract_topic_from_headline(title: str) -> Optional[str]:
    """
    Haber başlığından YouTube Shorts konusu üretir.
    Olası formatlar:
      "Ancient Roman coin hoard found in Britain" → "What if Rome had conquered Britain?"
      "New evidence of battle of Marathon discovered" → "What if Greece lost at Marathon?"
    """
    title_clean = re.sub(r"\s*[-|:]\s*.*$", "", title).strip()

    # "What if" kalıbı zaten varsa direkt kullan
    if re.search(r"what if", title_clean, re.IGNORECASE):
        return title_clean[:100]

    # Tarihi olaylar içeren başlıklar için "What if?" konu üret
    battle_match = re.search(
        r"battle of (\w[\w\s]{2,30})", title_clean, re.IGNORECASE
    )
    if battle_match:
        battle = battle_match.group(1).title()
        return f"What if the Battle of {battle} had a different outcome?"

    # Kişi/imparatorluk içeren başlıklar
    empire_match = re.search(
        r"(roman|greek|ottoman|mongol|byzantine|persian|british|french|spanish)\s+empire",
        title_clean, re.IGNORECASE,
    )
    if empire_match:
        empire = empire_match.group(0).title()
        return f"What if the {empire} Never Fell?"

    # Güncel çatışma/geopolitik olaylar
    conflict_match = re.search(
        r"(ukraine|russia|china|taiwan|iran|israel|nato|north korea|syria|yemen)",
        title_clean, re.IGNORECASE,
    )
    if conflict_match:
        subject = conflict_match.group(0).title()
        return f"What if {subject} scenario escalates? {title_clean[:60]}"

    # Genel dönüştürme
    if len(title_clean) > 20:
        return f"What if: {title_clean[:80]}"

    return None


def fetch_wikipedia_on_this_day() -> list[str]:
    """
    Wikipedia 'On This Day' API'si: bugünün tarihi olaylarını getirir.
    Her gün farklı, güncel ve alakalı konular.
    """
    today = date.today()
    url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{today.month:02d}/{today.day:02d}"

    try:
        resp = requests.get(url, timeout=TIMEOUT, headers={
            "User-Agent": "WAR-SHORTS-Bot/1.0 (educational pipeline)"
        })
        if resp.status_code != 200:
            return []

        data = resp.json()
        events = data.get("events", [])
        topics = []

        for event in events[:10]:
            text = event.get("text", "")
            year = event.get("year", "")

            # Savaş/imparatorluk/tarih olaylarını filtrele
            if _is_history_relevant(text, "", []):
                # "What if?" sorusu üret
                topic = f"What if {year}: {text[:80]}?"
                topics.append(topic)

        print(f"[rss] Wikipedia 'On This Day': {len(topics)} konu bulundu")
        return topics

    except Exception as e:
        print(f"[rss] Wikipedia API hatası: {e}")
        return []


def _update_topic_pool(new_topics: list[str]) -> int:
    """Yeni konuları topic_pool.json'a ekler."""
    pool_path = "topic_pool.json"
    try:
        with open(pool_path, encoding="utf-8") as f:
            pool = json.load(f)
    except FileNotFoundError:
        pool = []

    existing = {t.lower() for t in pool}
    added = 0
    for topic in new_topics:
        if topic.lower() not in existing and len(topic) > 15:
            pool.append(topic)
            existing.add(topic.lower())
            added += 1

    with open(pool_path, "w", encoding="utf-8") as f:
        json.dump(pool, f, indent=2, ensure_ascii=False)

    return added


def monitor_and_update(max_topics: int = 10) -> dict:
    """
    RSS beslemelerini tara, topic_pool.json'a yeni konular ekle.

    Returns:
        {"topics_found": int, "topics_added": int, "sources_checked": int}
    """
    state = _load_state()
    seen = set(state.get("seen_titles", []))

    all_topics = []

    # RSS beslemeleri
    for feed in RSS_FEEDS:
        print(f"[rss] Taranıyor: {feed['name']}")
        items = _fetch_rss(feed["url"])
        for item in items:
            title = item["title"]
            if title in seen:
                continue
            if not _is_history_relevant(title, item["description"], feed["keywords"]):
                continue
            topic = _extract_topic_from_headline(title)
            if topic:
                all_topics.append(topic)
                seen.add(title)

    # Wikipedia "On This Day"
    wiki_topics = fetch_wikipedia_on_this_day()
    all_topics.extend(wiki_topics)

    # Dedup + limit
    unique = list(dict.fromkeys(all_topics))[:max_topics]

    # topic_pool.json güncelle
    added = _update_topic_pool(unique)

    # State güncelle
    state["seen_titles"] = list(seen)[-500:]  # son 500 başlığı tut
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    result = {
        "topics_found": len(unique),
        "topics_added": added,
        "sources_checked": len(RSS_FEEDS) + 1,
        "sample_topics": unique[:3],
    }
    print(f"[rss] Tamamlandı: {added} yeni konu eklendi → topic_pool.json")
    return result


if __name__ == "__main__":
    result = monitor_and_update()
    print(json.dumps(result, indent=2, ensure_ascii=False))
