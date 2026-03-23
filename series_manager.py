"""
series_manager.py — Çok bölümlü içerik serisi yöneticisi.

Tek seferlik videolar yerine birbirine bağlı serilere dönüştürür:
  - "NATO vs Russia: Part 1/3 — The Buildup"
  - Bölümler arası referans ve bağlantı
  - Seri bazlı playlist otomatik oluşturma
  - "Bölüm 2'yi kaçırma!" CTA'ları

Strateji:
  1. Belirli konular seri potansiyeli taşır (tespit)
  2. Gemini ile çok bölümlü plan oluşturulur
  3. Her bölüm önceki bölüme referans verir
  4. Seri state'i kaydedilir

Rakip avantajı: İzleyiciyi "sonraki bölüm" döngüsüne sokar →
binge-watch etkisi → watch time patlaması → YouTube algoritma desteği.
"""

import json
import os
import re
import requests
from datetime import datetime, timezone
from dataclasses import dataclass, field


SERIES_STATE_PATH = "output/series_state.json"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Seri tetikleyici konular — bu kalıplar seri potansiyeli taşır
SERIES_TRIGGERS = [
    r"nato\s+vs\s+russia",
    r"world\s+war\s+(3|iii|three)",
    r"china\s+(taiwan|invasion)",
    r"nuclear\s+war",
    r"middle\s+east\s+(war|conflict|crisis)",
    r"turkey\s+vs",
    r"iran\s+vs\s+israel",
    r"cold\s+war\s+2",
    r"arms\s+race",
    r"doomsday",
    r"global\s+conflict",
    r"superpower",
    r"what\s+if.*war",
    r"invasion\s+of",
]


@dataclass
class SeriesInfo:
    """Aktif bir seri hakkında bilgi."""
    series_id: str
    title: str
    total_parts: int
    current_part: int
    topic_base: str
    parts: list[dict] = field(default_factory=list)
    created_at: str = ""
    status: str = "active"  # active, completed, cancelled


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
            "maxOutputTokens": 512,
            "temperature": 0.7,
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
        print(f"[series] Gemini hatası: {e}")
    return ""


def _load_state() -> dict:
    """Seri state dosyasını yükler."""
    if os.path.exists(SERIES_STATE_PATH):
        with open(SERIES_STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"active_series": [], "completed_series": []}


def _save_state(state: dict) -> None:
    """Seri state'ini kaydeder."""
    os.makedirs("output", exist_ok=True)
    with open(SERIES_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ─── Seri Potansiyeli Tespiti ─────────────────────────────────────────────────

def has_series_potential(topic: str) -> bool:
    """Konu bir seri olarak genişletilebilir mi?"""
    topic_lower = topic.lower()
    return any(re.search(pattern, topic_lower) for pattern in SERIES_TRIGGERS)


def detect_and_plan_series(topic: str) -> dict | None:
    """
    Konu seri potansiyeli taşıyorsa 3 bölümlük plan üretir.

    Returns:
        {"series_title": str, "parts": [{"part": int, "subtitle": str, "focus": str}]}
        veya None (seri uygun değilse)
    """
    if not has_series_potential(topic):
        return None

    system = """You are a YouTube content strategist specializing in military analysis series.

Given a topic, create a 3-part series plan. Each part should:
- Build on the previous one
- Have increasing tension/stakes
- End with a cliffhanger for the next part

Part 1: "The Setup" — Background, context, what led to this
Part 2: "The Escalation" — The crisis point, turning points, shocking revelations
Part 3: "The Endgame" — Predictions, scenarios, what it means for the world

Reply in JSON:
{
  "series_title": "Main series title",
  "parts": [
    {"part": 1, "subtitle": "Part subtitle", "focus": "What this episode covers"},
    {"part": 2, "subtitle": "Part subtitle", "focus": "What this episode covers"},
    {"part": 3, "subtitle": "Part subtitle", "focus": "What this episode covers"}
  ]
}"""

    prompt = f"Create a 3-part YouTube Shorts series plan for: {topic}"
    raw = _call_gemini(prompt, system)

    if not raw:
        return None

    try:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            plan = json.loads(match.group(0))
            if "series_title" in plan and "parts" in plan:
                return plan
    except (json.JSONDecodeError, KeyError):
        pass

    return None


# ─── Seri Başlatma / Devam Etme ──────────────────────────────────────────────

def start_series(topic: str, plan: dict) -> SeriesInfo:
    """Yeni bir seri başlatır ve state'e kaydeder."""
    state = _load_state()

    series_id = f"series_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    series = SeriesInfo(
        series_id=series_id,
        title=plan["series_title"],
        total_parts=len(plan["parts"]),
        current_part=1,
        topic_base=topic,
        parts=plan["parts"],
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    state["active_series"].append({
        "series_id": series.series_id,
        "title": series.title,
        "total_parts": series.total_parts,
        "current_part": series.current_part,
        "topic_base": series.topic_base,
        "parts": series.parts,
        "created_at": series.created_at,
        "status": "active",
        "video_ids": [],
    })

    _save_state(state)
    print(f"[series] Yeni seri başlatıldı: '{series.title}' ({series.total_parts} bölüm)")

    return series


def get_active_series() -> dict | None:
    """Aktif bir seri varsa döndürür."""
    state = _load_state()
    for s in state.get("active_series", []):
        if s.get("status") == "active":
            return s
    return None


def get_series_topic_override() -> str | None:
    """
    Aktif bir serinin sıradaki bölümü varsa, o bölümün konusunu döndürür.
    main.py'de topic_override olarak kullanılır.
    """
    active = get_active_series()
    if not active:
        return None

    current = active["current_part"]
    total = active["total_parts"]

    if current > total:
        return None

    parts = active.get("parts", [])
    if current <= len(parts):
        part = parts[current - 1]
        # Seri başlığı + bölüm bilgisi ile konu override
        series_title = active["title"]
        subtitle = part.get("subtitle", f"Part {current}")
        focus = part.get("focus", "")

        topic = f"{series_title} — {subtitle} (Part {current}/{total}): {focus}"
        print(f"[series] Seri devam ediyor: Bölüm {current}/{total}")
        return topic

    return None


def advance_series(video_id: str) -> None:
    """Seriyi bir sonraki bölüme ilerletir."""
    state = _load_state()

    for s in state.get("active_series", []):
        if s.get("status") != "active":
            continue

        s.setdefault("video_ids", []).append(video_id)
        s["current_part"] += 1

        if s["current_part"] > s["total_parts"]:
            s["status"] = "completed"
            state.setdefault("completed_series", []).append(s)
            state["active_series"].remove(s)
            print(f"[series] ✅ Seri tamamlandı: '{s['title']}'")
        else:
            print(f"[series] Bölüm {s['current_part'] - 1} yayınlandı. "
                  f"Sıradaki: Bölüm {s['current_part']}/{s['total_parts']}")
        break

    _save_state(state)


def get_series_cta(series: dict) -> str:
    """Seri bağlamında CTA metni üretir."""
    current = series.get("current_part", 1)
    total = series.get("total_parts", 3)
    title = series.get("title", "")

    if current < total:
        return (
            f"🔥 This is Part {current}/{total} of the '{title}' series!\n"
            f"Part {current + 1} drops TOMORROW — Follow so you don't miss it! 🔔"
        )
    else:
        return (
            f"🏁 This is the FINAL Part ({current}/{total}) of '{title}'!\n"
            f"What series should I cover next? Comment below! 👇"
        )


def enrich_script_with_series(script: dict, series: dict) -> dict:
    """
    Script'e seri bilgisi ekler.
    Başlığa bölüm numarası, narasyona önceki bölüm referansı ekler.
    """
    current = series.get("current_part", 1)
    total = series.get("total_parts", 3)
    title = series.get("title", "")

    # Başlığa bölüm numarası ekle
    original_title = script.get("title", "")
    if f"Part {current}" not in original_title and f"{current}/{total}" not in original_title:
        script["title"] = f"{original_title} (Part {current}/{total})"

    # Narasyona seri bağlamı ekle
    narration = script.get("narration", "")
    if current > 1:
        # Önceki bölüme referans
        series_intro = (
            f"In Part {current - 1}, we covered the buildup. "
            f"Now, things are about to escalate. "
        )
        script["narration"] = series_intro + narration
    elif current == 1:
        # İlk bölüm — seri duyurusu
        series_outro = (
            f" This is Part 1 of a {total}-part series. "
            f"Follow for Part 2 tomorrow."
        )
        script["narration"] = narration + series_outro

    # Seri tag'leri ekle
    script.setdefault("tags", []).extend([
        f"part {current}", "series", title.lower().replace(" ", "")[:20]
    ])

    return script


if __name__ == "__main__":
    import sys

    topic = sys.argv[1] if len(sys.argv) > 1 else "What if NATO and Russia Go to War?"

    if has_series_potential(topic):
        print(f"✅ Seri potansiyeli var: {topic}")
        plan = detect_and_plan_series(topic)
        if plan:
            print(json.dumps(plan, indent=2, ensure_ascii=False))
        else:
            print("Plan üretilemedi.")
    else:
        print(f"❌ Seri potansiyeli yok: {topic}")
