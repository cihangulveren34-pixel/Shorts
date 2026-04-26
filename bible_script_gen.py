"""
bible_script_gen.py — İncil hikaye videoları için Gemini ile narration + metadata üretir.

Üretilen alanlar:
  - narration: TTS'e gidecek hikaye metni (~120-150 kelime, 45-55 saniye)
  - title: YouTube başlığı (≤60 karakter)
  - hook_line: İlk 3-4 saniyede ekranda çarpıcı metin
  - description: YouTube açıklaması (SEO)
  - tags: YouTube etiketleri
  - cta_line: Video sonu CTA metni
  - moral_text: Son 5 saniyede ekranda ders/moral
"""

import os
import json
import random

from freq_script_gen import (
    _call_gemini,
    _extract_json,
    _repair_and_extract_json,
    generate_localizations,
)


PROMPT_TEMPLATE = """You are a master storyteller creating a narrated Bible story for a YouTube Short (vertical video, max 60 seconds).

BIBLE STORY DETAILS:
- Story: {title}
- Book & Verse: {book} ({verse_ref})
- Summary: {summary}
- Moral/Lesson: {moral}
- Mood: {mood}

HOOK INSPIRATION:
{hooks_str}

YOUR TASK — Generate a complete script package:

1. **narration**: Write a compelling 120-150 word narration of this Bible story.
   RULES for narration:
   - Start with a gripping hook sentence that stops the viewer from scrolling
   - Tell the story dramatically but accurately to scripture
   - Use vivid, cinematic language (short sentences, active voice)
   - Build tension, reach a climax, then deliver the lesson
   - End with the moral/lesson naturally woven into the conclusion
   - Must be speakable in 45-55 seconds at a moderate pace
   - Do NOT use stage directions or parenthetical notes
   - Write in second person occasionally ("Imagine you are there...")

2. **title**: YouTube title, ≤60 chars. Format: "[Story Name] | [Emotional Hook]"
   Example: "David vs Goliath | Faith Over Fear"

3. **hook_line**: The SINGLE most compelling line shown on screen first 4 seconds. ≤10 words. Must create instant curiosity.

4. **description**: 80-120 word SEO-optimized YouTube description. Mention the Bible book and verse, the story name, and spiritual keywords. End with relevant hashtags.

5. **tags**: 12-15 relevant YouTube tags. Include "bible story", the story name, book name, "bible shorts", spiritual keywords.

6. **cta_line**: End screen CTA, 1 sentence. Example: "Follow for daily Bible stories."

7. **moral_text**: The moral/lesson in ≤12 words, shown on screen at the end. Powerful and memorable.

Output ONLY valid JSON:
{{
  "narration": "...",
  "title": "...",
  "hook_line": "...",
  "description": "...",
  "tags": ["...", "..."],
  "cta_line": "...",
  "moral_text": "..."
}}
"""


def generate_bible_script(topic: dict) -> dict:
    """
    İncil hikayesi için Gemini narration + metadata üretir.

    Args:
        topic: bible_topic_pool.json'dan bir kayıt

    Returns:
        Üretilen script dict (narration, title, hook_line, description, tags, cta_line, moral_text + topic meta)
    """
    hooks_str = "\n".join(f"- {h}" for h in topic.get("hooks", []))

    prompt = PROMPT_TEMPLATE.format(
        title=topic["title"],
        book=topic["book"],
        verse_ref=topic["verse_ref"],
        summary=topic["summary"],
        moral=topic["moral"],
        mood=topic["mood"],
        hooks_str=hooks_str,
    )

    print(f"[bible_script_gen] {topic['title']} için Gemini çağrılıyor...")
    raw = _call_gemini(prompt, max_tokens=2048)
    script = _extract_json(raw)

    # Eksik alan varsa topic pool'dan default al
    script.setdefault("narration", topic["summary"])
    script.setdefault("title", topic["title"])
    script.setdefault("hook_line", random.choice(topic["hooks"]))
    script.setdefault("description", topic["summary"])
    script.setdefault("tags", topic["tags"])
    script.setdefault("cta_line", "Follow for daily Bible stories.")
    script.setdefault("moral_text", topic["moral"])

    # Topic meta bilgilerini ekle
    script["story_id"] = topic["story_id"]
    script["book"] = topic["book"]
    script["verse_ref"] = topic["verse_ref"]
    script["mood"] = topic["mood"]
    script["moral"] = topic["moral"]
    script["pexels_keywords"] = topic.get("pexels_keywords", [])

    print(f"[bible_script_gen] Başlık: {script['title']}")
    print(f"[bible_script_gen] Hook: {script['hook_line']}")
    print(f"[bible_script_gen] Narration: {len(script['narration'].split())} kelime")
    return script


def save_bible_script(script: dict, path: str = "output/bible_script.json") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(script, f, indent=2, ensure_ascii=False)
    print(f"[bible_script_gen] Script kaydedildi: {path}")
