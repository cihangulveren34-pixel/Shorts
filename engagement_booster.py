"""
engagement_booster.py — Akıllı etkileşim güçlendirici.

Her video için izleyici etkileşimini artıracak öğeler üretir:
  1. Akıllı anket/soru (Community tab veya pinned yorum için)
  2. Tartışma kışkırtıcı yorumlar
  3. Seri bağlantıları ("Bölüm 2'yi kaçırma!" tarzı CTA'lar)
  4. İzleyici tahmin oyunu ("Sence ne olur?")
  5. Emoji anket formatları

Gemini API kullanarak bağlama uygun, etkileşim odaklı içerik üretir.

Rakip avantajı: Rakipler sadece video yüklerken, biz her videoda
aktif izleyici etkileşimi yaratıyoruz → daha fazla yorum → daha fazla push.
"""

import json
import os
import random
import requests
from datetime import datetime, timezone


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _call_gemini(prompt: str, system: str = "", max_tokens: int = 256) -> str:
    """Gemini API çağrısı."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return ""

    model = "gemini-2.5-flash-lite"
    url = f"{GEMINI_API_URL.format(model=model)}?key={api_key}"

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.8,
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
        print(f"[engagement] Gemini hatası: {e}")

    return ""


# ─── Pinned Yorum Üretici ────────────────────────────────────────────────────

def generate_pinned_comment(script: dict) -> str:
    """
    Video için etkileşim odaklı pinned yorum üretir.
    Basit "What do you think?" yerine kışkırtıcı bir soru.
    """
    title = script.get("title", "")
    narration = script.get("narration", "")[:200]

    system = """You are a YouTube engagement specialist. Generate a PINNED COMMENT
that will maximize replies and engagement. The comment must:
- Ask a SPECIFIC, provocative question related to the video topic
- Include 2-3 answer options (A/B/C format or emoji voting)
- Be under 200 characters
- Create FOMO: "Only 10% get this right..."
- Use emojis strategically

Reply with ONLY the comment text, nothing else."""

    prompt = f'Video: "{title}"\nContent summary: {narration}\n\nGenerate the pinned comment:'

    result = _call_gemini(prompt, system)

    if not result:
        # Fallback şablonları
        fallbacks = [
            f"🔥 Bold prediction time: How does this end?\n\nA) Escalation 💥\nB) Diplomacy 🤝\nC) Surprise twist 🔄\n\nDrop your answer! 👇",
            f"⚡ Hot take: What happens next?\n\n🔴 Full-scale war\n🟡 Cold war standoff\n🟢 Peace deal\n\nVote below! Most get this WRONG 👇",
            f"🎯 Prediction challenge: Only 5% get this right!\n\nWhat's the REAL endgame here? Comment your theory 👇",
        ]
        result = random.choice(fallbacks)

    return result[:500]


# ─── Community Tab Anket ──────────────────────────────────────────────────────

def generate_community_poll(script: dict) -> dict:
    """
    YouTube Community tab için anket/gönderi üretir.

    Returns:
        {"text": str, "poll_options": list[str]} veya {"text": str}
    """
    title = script.get("title", "")
    tags = script.get("tags", [])

    system = """You are a YouTube community engagement expert. Generate a COMMUNITY POST
with a poll that will get maximum votes and engagement.

Requirements:
- The post text must be 1-2 sentences, provocative and opinion-driven
- Include 4 poll options that are interesting and debatable
- Each option under 25 characters
- Use 1-2 emojis in the post text

Reply in this exact JSON format:
{"text": "post text here", "poll_options": ["Option A", "Option B", "Option C", "Option D"]}"""

    prompt = f'Latest video: "{title}"\nTags: {", ".join(tags[:5])}\n\nGenerate community poll:'

    raw = _call_gemini(prompt, system, max_tokens=200)

    try:
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception:
        pass

    # Fallback
    return {
        "text": f"🔥 After watching today's analysis on {title[:40]}... What's YOUR prediction?",
        "poll_options": [
            "Full escalation 💥",
            "Diplomatic solution 🤝",
            "Status quo continues",
            "Something nobody expects 🔮",
        ]
    }


# ─── Tartışma Kışkırtıcı ────────────────────────────────────────────────────

def generate_debate_starter(script: dict) -> str:
    """
    İlk yorum olarak tartışma başlatıcı bir yorum üretir.
    Pinned yorumdan farklı: bu daha "unpopular opinion" tarzı.
    """
    title = script.get("title", "")
    narration = script.get("narration", "")[:150]

    system = """You create CONTROVERSIAL but thoughtful YouTube comments that spark debate.
Your comments:
- Take a bold, unpopular stance on the topic
- Are under 150 characters
- End with a question that forces replies
- Never be offensive, just thought-provoking
- Use 1 emoji maximum

Reply with ONLY the comment, nothing else."""

    prompt = f'Video: "{title}"\nSummary: {narration}\n\nDebate starter:'

    result = _call_gemini(prompt, system, max_tokens=100)
    return result[:200] if result else ""


# ─── İzleyici Tahmin Oyunu ────────────────────────────────────────────────────

def generate_prediction_game(script: dict) -> str:
    """
    İzleyicileri tahmin yapmaya teşvik eden interaktif yorum.
    "Sence 2026'da ne olur?" tarzı.
    """
    title = script.get("title", "")
    mood = script.get("mood", "epic")

    templates = [
        "🎯 PREDICTION GAME: What happens by end of {year}?\n\n"
        "Drop your prediction — I'll pin the best one! 📌\n\n"
        "Most creative prediction wins a shoutout! 🏆",

        "🔮 CRYSTAL BALL TIME: {title}\n\n"
        "Comment your wildest theory about what happens next.\n"
        "Wrong answers only 😂👇",

        "⚡ 30-SECOND CHALLENGE: After watching this video...\n\n"
        "What's the ONE thing that could change everything?\n"
        "Best answer gets pinned! 📌👇",

        "🧠 INTEL TEST: Based on this briefing...\n\n"
        "What would YOU do as commander-in-chief?\n"
        "Most strategic answer wins! 🎖️👇",
    ]

    template = random.choice(templates)
    year = datetime.now().year
    return template.format(
        year=year,
        title=title[:40],
    )


# ─── Tüm Etkileşim Öğelerini Üret ──────────────────────────────────────────

def generate_engagement_pack(script: dict) -> dict:
    """
    Video için tam etkileşim paketi üretir.

    Returns:
        {
            "pinned_comment": str,
            "community_poll": dict,
            "debate_starter": str,
            "prediction_game": str,
        }
    """
    print("[engagement] Etkileşim paketi üretiliyor...")

    pack = {
        "pinned_comment": generate_pinned_comment(script),
        "community_poll": generate_community_poll(script),
        "debate_starter": generate_debate_starter(script),
        "prediction_game": generate_prediction_game(script),
    }

    # Özet
    print(f"[engagement] ✅ Paket hazır:")
    print(f"  Pinned: {pack['pinned_comment'][:60]}...")
    print(f"  Poll: {pack['community_poll'].get('text', '')[:60]}...")
    if pack['debate_starter']:
        print(f"  Debate: {pack['debate_starter'][:60]}...")

    return pack


if __name__ == "__main__":
    test_script = {
        "title": "Turkey's New KAAN Fighter Changes Everything",
        "narration": "Turkey just unveiled the KAAN stealth fighter...",
        "tags": ["turkey", "kaan", "fighter", "stealth", "military"],
        "mood": "epic",
    }
    pack = generate_engagement_pack(test_script)
    print(json.dumps(pack, indent=2, ensure_ascii=False))
