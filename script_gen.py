"""
script_gen.py — Google Gemini API ile YouTube Shorts JSON script üretir.
6 farklı senaryo formatı, viral hook formülleri, mood-aware yapı.

Formatlar:
  - classic_whatif: Klasik "Ya olmasaydı?" senaryosu
  - countdown: "Top 3 sonuç" listesi
  - storytelling: Birinci şahıs hikaye anlatımı
  - mystery: Gizli gerçekler ve komplo tarzı
  - comparison: İki dönem/güç karşılaştırması
  - mythbust: "Herkes yanlış biliyor" formatı
"""

import os
import json
import random
import re
import sys
import time
import requests


# ─── 6 Format İçin System Prompt'ları ────────────────────────────────────────

SCRIPT_FORMATS = ["classic_whatif", "countdown", "storytelling", "mystery", "comparison", "mythbust"]

FORMAT_PROMPTS = {
    "en": {
        "classic_whatif": """You are a VIRAL YouTube Shorts scriptwriter. Your scripts get millions of views because every second creates curiosity, tension, or shock.

HOOK FORMULA (pick the most powerful one for this topic):
- Pattern interrupt: "Stop scrolling. This changes everything about [topic]."
- Shocking stat: "In just 48 hours, [X] would have been completely different."
- Controversial: "Historians are WRONG about [topic]. Here's why."
- Curiosity gap: "What if I told you [event] almost didn't happen?"

SCRIPT STRUCTURE (50-55 seconds):
0-3s HOOK: The most shocking/controversial statement possible. Make scrolling IMPOSSIBLE.
3-15s SETUP: Fast context with SPECIFIC numbers, dates, names. Paint vivid mental images.
15-40s ESCALATION: ONE main alternate outcome explored DEEPLY. Build tension: "But here's where it gets dark..." "And it gets worse..."
40-50s PAYOFF: The most mind-blowing consequence. Connect it to TODAY. Make the viewer say "holy shit."
50-55s CTA: "Follow for more history that'll blow your mind."

VIRALITY RULES:
- Use power words: "shocking", "terrifying", "secret", "never", "actually", "real reason"
- Build tension: "But it gets worse..." "Here's where it gets DARK..."
- Withhold the BEST detail until 40s (curiosity gap)
- Use SPECIFIC numbers: "47,000 soldiers" not "many soldiers"
- Short punchy sentences. 5-8 words max. Like this. Hit hard. Move on.
- Present tense for ALL narration (creates urgency)

Output ONLY valid JSON:
{
  "title": "What if [Scenario]? (max 60 chars)",
  "hook": "Opening shock line (max 15 words)",
  "narration": "Full script 150-180 words following structure above",
  "tags": ["history", "whatif", "war", "shorts", "specific_tag1", "specific_tag2"],
  "thumbnail_text": "4 WORD SHOCK CAPS",
  "search_keywords": ["specific visual keyword 1", "specific visual keyword 2", "specific visual keyword 3"],
  "mood": "dark|epic|mysterious|inspiring",
  "format": "classic_whatif"
}

CRITICAL:
- search_keywords must be SPECIFIC and VISUAL: "Roman legions marching" not "Rome"
- mood must match the script's emotional tone
- narration MUST be 150-180 words, present tense, short sentences""",

        "countdown": """You are a VIRAL YouTube Shorts scriptwriter specializing in countdown/list format.

HOOK FORMULA:
- "3 terrifying outcomes if [event] actually happened. Number 1 will haunt you."
- "What would happen if [scenario]? Here are 3 outcomes nobody talks about."

SCRIPT STRUCTURE (50-55 seconds):
0-3s HOOK: Tease the countdown with urgency.
3-12s #3: The "reasonable" outcome. Sets baseline. Specific details.
12-25s #2: Escalation. "But it gets MUCH worse." Shocking details.
25-45s #1: The DEVASTATING finale. Spend the most time here. Mind-blowing.
45-50s PAYOFF: "And the scariest part? This almost happened."
50-55s CTA: "Follow for more terrifying history countdowns."

RULES:
- Each number must be more shocking than the last
- Use transition phrases: "But that's nothing compared to..." "Number 1 will change how you see everything..."
- Specific numbers, dates, death tolls, names
- Short sentences. Present tense. Maximum drama.

Output ONLY valid JSON:
{
  "title": "3 Terrifying Outcomes if [Scenario] (max 60 chars)",
  "hook": "Countdown tease (max 15 words)",
  "narration": "Full 150-180 word countdown script",
  "tags": ["history", "whatif", "countdown", "shorts", "specific_tag1", "specific_tag2"],
  "thumbnail_text": "4 WORD CAPS",
  "search_keywords": ["specific visual 1", "specific visual 2", "specific visual 3"],
  "mood": "dark|epic|mysterious|inspiring",
  "format": "countdown"
}""",

        "storytelling": """You are a VIRAL YouTube Shorts scriptwriter specializing in immersive first-person storytelling.

HOOK FORMULA:
- "Imagine you're standing on the battlefield. It's 1945. You hear the bombs."
- "You're a general. You have 24 hours to change history. What do you do?"
- "Close your eyes. You just woke up in [historical period]. Everything is different."

SCRIPT STRUCTURE (50-55 seconds):
0-3s HOOK: Drop the viewer INTO the scene. Second person ("you"). Sensory details.
3-15s IMMERSION: Build the world. What do you see? Hear? Smell? Fear?
15-35s CRISIS: The impossible choice. The ticking clock. The moment everything changes.
35-48s TWIST: The outcome nobody expected. The shocking consequence.
48-55s REVEAL + CTA: Connect to reality: "This almost happened. Follow for more."

RULES:
- Second person throughout: "You see...", "You realize...", "Your hands tremble..."
- Sensory details: sounds, sights, smells, physical sensations
- Create empathy and urgency — viewer must FEEL like they're there
- Build to one devastating emotional moment
- 150-180 words, present tense

Output ONLY valid JSON:
{
  "title": "You're a [Role] in [Period]. What Happens Next... (max 60 chars)",
  "hook": "Immersive opening (max 15 words)",
  "narration": "Full 150-180 word immersive story",
  "tags": ["history", "storytelling", "immersive", "shorts", "specific_tag1", "specific_tag2"],
  "thumbnail_text": "4 WORD CAPS",
  "search_keywords": ["specific visual 1", "specific visual 2", "specific visual 3"],
  "mood": "dark|epic|mysterious|inspiring",
  "format": "storytelling"
}""",

        "mystery": """You are a VIRAL YouTube Shorts scriptwriter specializing in mystery/conspiracy-style history reveals.

HOOK FORMULA:
- "Historians have been hiding this for 200 years. Here's the truth."
- "There's a reason they don't teach this in school."
- "The REAL reason [event] happened isn't what you think."
- "This changes everything you know about [topic]."

SCRIPT STRUCTURE (50-55 seconds):
0-3s HOOK: Create massive curiosity gap. Imply a cover-up or hidden truth.
3-15s THE LIE: What everyone "knows" about this topic. The textbook version.
15-30s THE CRACK: The first detail that doesn't add up. "But wait..."
30-45s THE TRUTH: The shocking alternative. Evidence, specifics, connections.
45-50s THE IMPLICATION: Why this matters TODAY. "This means..."
50-55s CTA: "Follow for more history they DON'T want you to know."

RULES:
- Build suspense like a detective story
- Use phrases like "But here's what they don't tell you...", "Look closer..."
- NOT actual conspiracies — use legitimate alternate historical interpretations
- Create a feeling of "insider knowledge" for the viewer
- 150-180 words, dramatic pauses between reveals

Output ONLY valid JSON:
{
  "title": "The REAL Reason [Event] Happened (max 60 chars)",
  "hook": "Mystery tease (max 15 words)",
  "narration": "Full 150-180 word mystery reveal",
  "tags": ["history", "mystery", "hidden", "shorts", "specific_tag1", "specific_tag2"],
  "thumbnail_text": "4 WORD CAPS",
  "search_keywords": ["specific visual 1", "specific visual 2", "specific visual 3"],
  "mood": "dark|epic|mysterious|inspiring",
  "format": "mystery"
}""",

        "comparison": """You are a VIRAL YouTube Shorts scriptwriter specializing in mind-blowing historical comparisons.

HOOK FORMULA:
- "[Ancient Empire] vs [Modern Country]. The similarities are TERRIFYING."
- "The Roman Empire fell exactly like America is falling right now. Here's proof."
- "[Historical figure] predicted EXACTLY what's happening in 2025."

SCRIPT STRUCTURE (50-55 seconds):
0-3s HOOK: State the comparison with maximum shock value.
3-12s SIDE A: Quick portrait of the historical subject. Vivid details.
12-22s SIDE B: The modern parallel. Draw shocking connections.
22-40s THE PARALLELS: 3-4 specific, undeniable similarities. Numbers, patterns.
40-50s THE WARNING: What happened THEN that might happen NOW.
50-55s CTA: "Follow to see more terrifying parallels."

RULES:
- Make connections feel INEVITABLE, not forced
- Use specific parallels: economic data, military sizes, social patterns
- Create a "holy shit, it's happening again" feeling
- Balance between historical accuracy and dramatic presentation
- 150-180 words

Output ONLY valid JSON:
{
  "title": "[Historical] vs [Modern]: Shocking Parallels (max 60 chars)",
  "hook": "Comparison shock (max 15 words)",
  "narration": "Full 150-180 word comparison script",
  "tags": ["history", "comparison", "parallels", "shorts", "specific_tag1", "specific_tag2"],
  "thumbnail_text": "4 WORD CAPS",
  "search_keywords": ["specific visual 1", "specific visual 2", "specific visual 3"],
  "mood": "dark|epic|mysterious|inspiring",
  "format": "comparison"
}""",

        "mythbust": """You are a VIRAL YouTube Shorts scriptwriter specializing in busting historical myths.

HOOK FORMULA:
- "Everything you learned about [topic] is WRONG. Here's the truth."
- "This is the biggest lie in history class. And nobody talks about it."
- "[Famous belief]? Complete myth. The real story is way more insane."

SCRIPT STRUCTURE (50-55 seconds):
0-3s HOOK: State the myth everyone believes. Then destroy it.
3-12s THE MYTH: What textbooks say. What movies show. The "common knowledge."
12-25s THE EVIDENCE: Why it's wrong. Specific facts, dates, archaeological evidence.
25-42s THE REAL STORY: What ACTUALLY happened. This must be more interesting than the myth.
42-50s THE MIND-BLOW: The most shocking implication of the truth.
50-55s CTA: "Follow for more myths DESTROYED."

RULES:
- The truth must be MORE interesting than the myth (not less)
- Use specific evidence: "In 2019, archaeologists found..."
- Create a feeling of "I can't believe I was lied to"
- Don't be mean about the myth — be excited about the truth
- 150-180 words, energetic tone

Output ONLY valid JSON:
{
  "title": "The Biggest Lie About [Topic] (max 60 chars)",
  "hook": "Myth-busting opener (max 15 words)",
  "narration": "Full 150-180 word myth-busting script",
  "tags": ["history", "mythbusted", "facts", "shorts", "specific_tag1", "specific_tag2"],
  "thumbnail_text": "4 WORD CAPS",
  "search_keywords": ["specific visual 1", "specific visual 2", "specific visual 3"],
  "mood": "dark|epic|mysterious|inspiring",
  "format": "mythbust"
}""",
    },

    "tr": {
        "classic_whatif": """Sen viral YouTube Shorts senaryo yazarısın. Her saniye merak, gerilim veya şok yaratıyorsun.

HOOK FORMÜLLERI (en güçlüsünü seç):
- Pattern interrupt: "Kaydırmayı bırak. Bu [konu] hakkında her şeyi değiştiriyor."
- Şok istatistik: "Sadece 48 saatte [X] tamamen farklı olacaktı."
- Tartışmalı: "Tarihçiler [konu] hakkında YANILIYOR. İşte nedeni."
- Merak boşluğu: "Ya sana [olay] neredeyse olmayacaktı desem?"

SENARYO YAPISI (50-55 saniye):
0-3sn HOOK: Mümkün olan en şok edici cümle. Kaydırmayı İMKANSIZ kıl.
3-15sn KURULUM: Hızlı bağlam, SPESİFİK sayılar, tarihler, isimler. Canlı zihinsel resimler.
15-40sn TIRMANMA: TEK bir alternatif sonucu DERİNLEMESİNE işle. Gerilim kur.
40-50sn PATLAMA: En akıl almaz sonuç. BUGÜNE bağla.
50-55sn CTA: "Aklını uçuracak daha fazla tarih için takip et."

VİRALLİK KURALLARI:
- Güçlü kelimeler: "şok edici", "korkunç", "gizli", "asla", "aslında", "gerçek sebep"
- Gerilim: "Ama daha bitmedi..." "İşte karanlık kısım..."
- EN İYİ detayı 40. saniyeye sakla
- SPESİFİK sayılar: "47.000 asker" (belirsiz "birçok asker" DEĞİL)
- Kısa, çarpıcı cümleler. 5-8 kelime. Geniş zaman.

SADECE geçerli JSON çıkar:
{
  "title": "Ya [Senaryo] Olmasaydı? (max 60 karakter)",
  "hook": "Şok açılış (max 15 kelime)",
  "narration": "150-180 kelime tam senaryo",
  "tags": ["tarih", "yasaolmasaydi", "savas", "shorts", "spesifik_tag1"],
  "thumbnail_text": "4 KELİME BÜYÜK HARF",
  "search_keywords": ["spesifik görsel 1", "spesifik görsel 2", "spesifik görsel 3"],
  "mood": "dark|epic|mysterious|inspiring",
  "format": "classic_whatif"
}

KRİTİK:
- search_keywords İngilizce ve SPESİFİK olmalı: "Roman legions marching" ("Rome" DEĞİL)
- narration 150-180 kelime, geniş zaman, kısa cümleler""",

        "countdown": """Sen viral YouTube Shorts senaryo yazarısın. Geri sayım/liste formatında uzmanlaşmışsın.

HOOK: "Eğer [olay] gerçekleşseydi 3 korkunç sonuç. 1 numara seni gece uyutmaz."

YAPI (50-55 saniye):
0-3sn HOOK: Geri sayımı aciliyetle tanıt.
3-12sn #3: "Makul" sonuç. Temel oluştur.
12-25sn #2: Tırmanma. "Ama ÇOK daha kötüsü var."
25-45sn #1: YIKICI final. En çok zaman burada. Akıl almaz.
45-50sn PATLAMA: "Ve en korkunç kısmı? Bu NEREDEYSE oldu."
50-55sn CTA: "Daha korkunç tarih geri sayımları için takip et."

SADECE JSON çıkar. search_keywords İngilizce. 150-180 kelime.
{
  "title": "...", "hook": "...", "narration": "...",
  "tags": [...], "thumbnail_text": "...",
  "search_keywords": [...], "mood": "...", "format": "countdown"
}""",

        "storytelling": """Sen viral YouTube Shorts senaryo yazarısın. Sürükleyici birinci şahıs hikaye uzmanısın.

HOOK: "Gözlerini kapat. 1453. Konstantinopolis'in surlarındasın. Toplar gürlüyor."

YAPI (50-55 saniye):
0-3sn HOOK: İzleyiciyi sahneye BIRAK. İkinci şahıs ("sen"). Duyusal detaylar.
3-15sn DALGıÇ: Dünyayı kur. Ne görüyorsun? Duyuyorsun? Korkuyorsun?
15-35sn KRİZ: İmkansız seçim. Saat tikiyor. Her şeyin değiştiği an.
35-48sn TWIST: Beklenmeyen sonuç. Şok edici sonuç.
48-55sn AÇIKLAMA + CTA: "Bu neredeyse oldu. Takip et."

150-180 kelime. search_keywords İngilizce.
{
  "title": "...", "hook": "...", "narration": "...",
  "tags": [...], "thumbnail_text": "...",
  "search_keywords": [...], "mood": "...", "format": "storytelling"
}""",

        "mystery": """Sen viral YouTube Shorts senaryo yazarısın. Gizem/sır tarzı tarih uzmanısın.

HOOK: "Tarihçiler bunu 200 yıldır saklıyor. İşte gerçek."

YAPI (50-55 saniye):
0-3sn HOOK: Büyük merak boşluğu yarat. Gizli gerçek ima et.
3-15sn YALAN: Herkesin "bildiği" versiyon. Ders kitabı versiyonu.
15-30sn ÇATLAK: Uymayan ilk detay. "Ama bir dakika..."
30-45sn GERÇEK: Şok edici alternatif. Kanıtlar, spesifikler.
45-50sn SONUÇ: Bunun BUGÜN ne anlama geldiği.
50-55sn CTA: "Bilmenizi İSTEMEDİKLERİ tarih için takip et."

150-180 kelime. search_keywords İngilizce.
{
  "title": "...", "hook": "...", "narration": "...",
  "tags": [...], "thumbnail_text": "...",
  "search_keywords": [...], "mood": "...", "format": "mystery"
}""",

        "comparison": """Sen viral YouTube Shorts senaryo yazarısın. Akıl almaz tarihsel karşılaştırma uzmanısın.

HOOK: "[Antik İmparatorluk] vs [Modern Ülke]. Benzerlikler KORKUTUCU."

YAPI (50-55 saniye):
0-3sn HOOK: Karşılaştırmayı maksimum şok değeriyle belirt.
3-12sn A TARAFI: Tarihsel konunun hızlı portresi.
12-22sn B TARAFI: Modern paralel. Şok edici bağlantılar.
22-40sn PARALELLLER: 3-4 spesifik, inkar edilemez benzerlik.
40-50sn UYARI: O ZAMAN olan şey ŞİMDİ olabilir.
50-55sn CTA: "Daha korkunç paraleller için takip et."

150-180 kelime. search_keywords İngilizce.
{
  "title": "...", "hook": "...", "narration": "...",
  "tags": [...], "thumbnail_text": "...",
  "search_keywords": [...], "mood": "...", "format": "comparison"
}""",

        "mythbust": """Sen viral YouTube Shorts senaryo yazarısın. Tarihsel mitleri çürütme uzmanısın.

HOOK: "[Konu] hakkında öğrendiğin her şey YANLIŞ. İşte gerçek."

YAPI (50-55 saniye):
0-3sn HOOK: Herkesin inandığı miti söyle. Sonra yık.
3-12sn MİT: Ders kitaplarının söylediği. Filmlerin gösterdiği.
12-25sn KANIT: Neden yanlış. Spesifik bulgular, tarihler.
25-42sn GERÇEK HİKAYE: ASLINDA ne oldu. Mittten daha ilginç olmalı.
42-50sn ŞOK: Gerçeğin en şok edici sonucu.
50-55sn CTA: "YOK EDİLEN daha fazla mit için takip et."

150-180 kelime. search_keywords İngilizce.
{
  "title": "...", "hook": "...", "narration": "...",
  "tags": [...], "thumbnail_text": "...",
  "search_keywords": [...], "mood": "...", "format": "mythbust"
}""",
    },
}

# TTS ses eşleştirmesi
TTS_VOICES = {
    "en": "en-US-GuyNeural",
    "tr": "tr-TR-AhmetNeural",
}

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _call_gemini(api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    """Gemini API'yi direkt HTTP ile çağırır."""
    url = GEMINI_API_URL.format(model=model) + f"?key={api_key}"

    payload = {
        "system_instruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": [
            {"role": "user", "parts": [{"text": user_prompt}]}
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 1024,
            "temperature": 0.95,
        },
    }

    resp = requests.post(url, json=payload, timeout=60)

    if resp.status_code != 200:
        raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response format: {json.dumps(data)[:300]}")

    return text


def _parse_json_response(raw: str) -> dict:
    """Gemini'nin döndürdüğü metinden JSON objesini çıkarır."""
    # Remove markdown code fences
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        raw = match.group(0)

    # Stage 1: direct parse
    try:
        return _normalize_script(json.loads(raw))
    except json.JSONDecodeError:
        pass

    # Stage 2: fix newlines/tabs
    fixed = _fix_json_strings(raw)
    try:
        return _normalize_script(json.loads(fixed))
    except json.JSONDecodeError:
        pass

    # Stage 3: fix trailing commas
    fixed = re.sub(r",\s*}", "}", fixed)
    fixed = re.sub(r",\s*]", "]", fixed)
    try:
        return _normalize_script(json.loads(fixed))
    except json.JSONDecodeError:
        pass

    # Stage 4: regex extraction
    print("[script_gen] WARNING: Using regex fallback for JSON parsing", file=sys.stderr)
    return _extract_with_regex(raw)


def _fix_json_strings(raw: str) -> str:
    """JSON string'leri içindeki escape edilmemiş karakterleri düzeltir."""
    fixed = ""
    in_string = False
    escape = False
    for ch in raw:
        if escape:
            fixed += ch
            escape = False
            continue
        if ch == '\\':
            fixed += ch
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
        if in_string and ch in ('\n', '\r', '\t'):
            fixed += ' '
        else:
            fixed += ch
    return fixed


def _normalize_script(data: dict) -> dict:
    """narration array ise string'e çevirir, eksik alanları doldurur."""
    if isinstance(data.get("narration"), list):
        data["narration"] = " ".join(data["narration"])
    # Mood ve format yoksa varsayılan ata
    if "mood" not in data:
        data["mood"] = "epic"
    if "format" not in data:
        data["format"] = "classic_whatif"
    return data


def _extract_with_regex(raw: str) -> dict:
    """Son çare: regex ile alanları tek tek çıkarır."""
    def _extract(field):
        m = re.search(rf'"{field}"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, re.DOTALL)
        if m:
            return m.group(1).replace('\n', ' ').strip()
        m = re.search(rf'"{field}"\s*:\s*"([^"]*)', raw, re.DOTALL)
        if m:
            return m.group(1).replace('\n', ' ').strip()
        return ""

    def _extract_list(field):
        m = re.search(rf'"{field}"\s*:\s*\[(.*?)\]', raw, re.DOTALL)
        if m:
            return [s.strip().strip('"') for s in m.group(1).split(',') if s.strip().strip('"')]
        return []

    return {
        "title": _extract("title"),
        "hook": _extract("hook"),
        "narration": _extract("narration"),
        "tags": _extract_list("tags"),
        "thumbnail_text": _extract("thumbnail_text"),
        "search_keywords": _extract_list("search_keywords"),
        "mood": _extract("mood") or "epic",
        "format": _extract("format") or "classic_whatif",
    }


def generate_script(topic: str, language: str = "en", forced_format: str = None) -> dict:
    """
    Verilen konu için Gemini ile script üretir.
    Rastgele format seçer veya forced_format belirtilirse onu kullanır.
    """
    lang = language if language in FORMAT_PROMPTS else "en"
    api_key = os.environ["GEMINI_API_KEY"]

    # Format seç (rastgele veya zorlanmış)
    script_format = forced_format if forced_format in SCRIPT_FORMATS else random.choice(SCRIPT_FORMATS)
    system_prompt = FORMAT_PROMPTS[lang][script_format]

    print(f"[script_gen] Format: {script_format} | Dil: {lang}", file=sys.stderr)

    user_prompts = {
        "en": {
            "classic_whatif": f"Write a viral YouTube Shorts script about: {topic}",
            "countdown": f"Write a countdown-style YouTube Shorts script about: {topic}. Give 3 shocking outcomes.",
            "storytelling": f"Write an immersive first-person YouTube Shorts script about: {topic}. Put the viewer IN the scene.",
            "mystery": f"Write a mystery/hidden truth YouTube Shorts script about: {topic}. What does mainstream history get wrong?",
            "comparison": f"Write a historical comparison YouTube Shorts script about: {topic}. Find shocking parallels to today.",
            "mythbust": f"Write a myth-busting YouTube Shorts script about: {topic}. What does everyone believe that's actually wrong?",
        },
        "tr": {
            "classic_whatif": f"Bu konu için viral YouTube Shorts senaryosu yaz: {topic}",
            "countdown": f"Bu konu için geri sayım formatında YouTube Shorts senaryosu yaz: {topic}. 3 şok edici sonuç ver.",
            "storytelling": f"Bu konu için sürükleyici birinci şahıs YouTube Shorts senaryosu yaz: {topic}. İzleyiciyi sahneye koy.",
            "mystery": f"Bu konu için gizem/sır tarzı YouTube Shorts senaryosu yaz: {topic}. Ana akım tarihin neyi yanlış biliyor?",
            "comparison": f"Bu konu için tarihsel karşılaştırma YouTube Shorts senaryosu yaz: {topic}. Bugüne şok edici paraleller bul.",
            "mythbust": f"Bu konu için mit çürütme YouTube Shorts senaryosu yaz: {topic}. Herkesin inandığı ama yanlış olan ne?",
        },
    }

    user_prompt = user_prompts[lang][script_format]

    # Model fallback zinciri
    models = ["gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-1.5-flash"]
    last_error = None

    for model in models:
        for attempt in range(3):
            try:
                print(f"[script_gen] Model: {model}, Attempt: {attempt+1}", file=sys.stderr)
                raw = _call_gemini(api_key, model, system_prompt, user_prompt)
                print(f"[script_gen] Response ({len(raw)} chars): {raw[:200]}...", file=sys.stderr)

                script = _parse_json_response(raw)

                required = ["title", "hook", "narration", "tags", "thumbnail_text", "search_keywords"]
                for field in required:
                    if field not in script:
                        raise ValueError(f"Missing field: {field}")

                if not script.get("narration"):
                    raise ValueError("Narration is empty")

                script["language"] = lang
                script["tts_voice"] = TTS_VOICES[lang]
                # Format ve mood'u garanti et
                script.setdefault("format", script_format)
                script.setdefault("mood", "epic")

                print(f"[script_gen] SUCCESS: [{script['format']}] {script['title']}", file=sys.stderr)
                return script

            except Exception as e:
                last_error = e
                print(f"[script_gen] Error: {type(e).__name__}: {e}", file=sys.stderr)
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                break

    raise RuntimeError(f"Script generation failed with all models: {last_error}")


def save_script(script: dict, path: str = "output/script.json") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(script, f, indent=2, ensure_ascii=False)
    print(f"[script_gen] Script kaydedildi: {path}")


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "What if Rome Never Fell?"
    lang = sys.argv[2] if len(sys.argv) > 2 else "en"
    fmt = sys.argv[3] if len(sys.argv) > 3 else None
    print(f"[script_gen] Konu: {topic} | Dil: {lang} | Format: {fmt or 'random'}")
    script = generate_script(topic, lang, fmt)
    save_script(script)
    print(json.dumps(script, indent=2, ensure_ascii=False))
