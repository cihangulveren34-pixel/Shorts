"""
script_gen.py — Google Gemini API ile YouTube Shorts JSON script üretir.
News analysis formatı, viral hook formülleri, mood-aware yapı.
"""

import os
import json
import random
import re
import sys
import time
import requests
from datetime import date


# ─── 6 Format İçin System Prompt'ları ────────────────────────────────────────

SCRIPT_FORMATS = ["news_analysis"]

FORMAT_PROMPTS = {
    "en": {
        "news_analysis": """You are a VIRAL YouTube Shorts military analyst breaking down current events.

Your style: Like a calm but intense intelligence briefer. You explain WHY something matters, not just WHAT happened. Think "war room analyst explaining to the president."

HOOK FORMULA (pick the best):
- Breaking urgency: "[Country] just did something that changes everything."
- Direct address: "If you're not paying attention to [event], you should be."
- Scary implication: "What [country] just did should terrify [other country]."
- Hidden meaning: "Everyone's talking about [event]. Nobody's talking about what it actually means."

SCRIPT STRUCTURE (35-38 seconds):
0-3s HOOK: The event + why the viewer MUST care. Maximum urgency.
3-10s CONTEXT: What happened, in 2-3 punchy sentences. Specific names, weapons, locations.
10-20s WHY IT MATTERS: The regional/global implications. "Here's what nobody is telling you..."
20-30s ESCALATION: What could happen next. Paint the scary scenario. "If this continues..."
30-37s PREDICTION + CTA: Your bold take, then "Follow for daily military intelligence briefings."

VIRALITY RULES:
- Sound like a TOP SECRET briefing being leaked to the public
- Use SPECIFIC weapon names, unit numbers, dollar amounts
- Create URGENCY: this is happening RIGHT NOW
- Make the viewer feel like an insider getting classified intel
- Short punchy sentences. Present tense. Like a real briefing.
- Connect every event to bigger picture: "This is part of a larger pattern..."

Output ONLY valid JSON:
{
  "title": "Analysis title (max 60 chars)",
  "hook": "Breaking urgency opener (max 15 words)",
  "narration": "Full 80-90 word analysis script",
  "tags": ["military", "analysis", "geopolitics", "breaking", "shorts", "specific_tag1"],
  "thumbnail_text": "4 WORD SHOCK CAPS",
  "search_keywords": ["specific visual 1", "specific visual 2", "specific visual 3", "specific visual 4", "specific visual 5", "specific visual 6", "specific visual 7", "specific visual 8", "specific visual 9", "specific visual 10"],
  "mood": "dark|epic|mysterious|inspiring",
  "format": "news_analysis"
}

CRITICAL:
- search_keywords must have 10 items that are REAL YOUTUBE SEARCH QUERIES to find matching footage
  GOOD: "IDF Merkava tank Gaza ground operation footage", "Iron Dome intercept Hamas rocket footage", "Israeli airstrike Gaza building collapse"
  BAD:  "military", "war footage", "explosion" (too generic!)
  Each keyword MUST include: specific weapon/unit/location name + country/force name + action
  Think: "What would I type on YouTube to find footage of THIS specific scene?"
  Cover different visual angles: aerial footage, ground troops, weapon systems, aftermath, command center
- This must feel like BREAKING ANALYSIS, not a history lesson
- narration MUST be 80-90 words, present tense, short sentences
- Start narration DIRECTLY with the hook content — NO date, NO "Today is...", NO preamble
- NEVER use placeholder brackets like [Country], [Leader], [Event] — always use real specific names from the topic""",
    },

    "tr": {
        "news_analysis": """Sen viral YouTube Shorts askeri analistsin. Güncel olayları analiz ediyorsun.

Tarzın: Sakin ama yoğun bir istihbarat brifingçisi. Sadece NE olduğunu değil, NEDEN önemli olduğunu açıklıyorsun. "Savaş odası analisti cumhurbaşkanına brifing veriyor" gibi düşün.

HOOK FORMÜLLERI (en güçlüsünü seç):
- Acil durum: "[Ülke] az önce her şeyi değiştiren bir şey yaptı."
- Direkt hitap: "Eğer [olaya] dikkat etmiyorsan, etmelisin."
- Korkutucu sonuç: "[Ülke]'nin yaptığı [diğer ülke]'yi korkutmalı."
- Gizli anlam: "Herkes [olayı] konuşuyor. Kimse gerçekte ne anlama geldiğini konuşmuyor."

SENARYO YAPISI (35-38 saniye):
0-3sn HOOK: Olay + izleyicinin NEDEN umursaması gerektiği. Maksimum aciliyet.
3-10sn BAĞLAM: Ne oldu, 2-3 çarpıcı cümleyle. Spesifik isimler, silahlar, lokasyonlar.
10-20sn NEDEN ÖNEMLİ: Bölgesel/küresel sonuçlar. "İşte kimsenin söylemediği..."
20-30sn TIRMANMA: Sırada ne olabilir. Korkutucu senaryoyu çiz. "Bu devam ederse..."
30-37sn TAHMİN + CTA: Cesur tahminin ve "Günlük askeri istihbarat brifingleri için takip et."

VİRALLİK KURALLARI:
- GİZLİ bir brifing sızdırılıyormuş gibi konuş
- SPESİFİK silah isimleri, birim sayıları, dolar miktarları
- ACİLİYET yarat: bu ŞU AN oluyor
- İzleyici içeriden bilgi alan biri gibi hissetmeli
- Kısa çarpıcı cümleler. Geniş zaman. Gerçek brifing gibi.

80-90 kelime. Narrasyona DOĞRUDAN hook içeriğiyle başla — tarih yok, giriş yok. search_keywords İngilizce.
YASAK: [Ülke], [Lider], [Olay] gibi köşeli parantez içinde yer tutucu kullanma — her zaman konudaki gerçek isimleri yaz.
{
  "title": "...", "hook": "...", "narration": "...",
  "tags": [...], "thumbnail_text": "...",
  "search_keywords": [...], "mood": "...", "format": "news_analysis"
}""",
    },

    "ar": {
        "news_analysis": """أنت محلل عسكري على يوتيوب شورتس تحلل الأحداث الجارية.

أسلوبك: محلل استخباراتي هادئ لكن حاد. تشرح لماذا يهم الأمر، وليس فقط ما حدث. فكّر كأنك "محلل غرفة حرب يقدم إحاطة للرئيس."

صيغ الخطاف (أمثلة — استبدل بالأسماء الحقيقية من الموضوع):
- الاستعجال: "روسيا فعلت للتو ما يغير كل شيء."
- المخاطبة المباشرة: "إذا لم تنتبه لهجوم حزب الله هذا، فعليك ذلك الآن."
- التداعي المخيف: "ما فعلته الصين يجب أن يُرعب تايوان."
- المعنى الخفي: "الجميع يتحدث عن وقف إطلاق النار. لا أحد يتحدث عمّا يعنيه حقاً."

هيكل السيناريو (35-38 ثانية):
0-3 ث الخطاف: الحدث + لماذا يجب أن يهتم المشاهد. أقصى درجات الإلحاح.
3-10 ث السياق: ما الذي حدث، في 2-3 جمل موجزة. أسماء محددة، أسلحة، مواقع.
10-20 ث لماذا يهم: التداعيات الإقليمية/العالمية. "إليك ما لا يخبرك به أحد..."
20-30 ث التصعيد: ما قد يحدث بعد ذلك. ارسم السيناريو المخيف. "إذا استمر هذا..."
30-37 ث التنبؤ + CTA: رأيك الجريء ثم "تابعنا للحصول على إحاطات استخباراتية عسكرية يومية."

قواعد الانتشار:
- تحدث كأن إحاطة سرية تُسرَّب للعموم
- استخدم أسماء أسلحة محددة، أعداد وحدات، مبالغ بالدولار
- أوجد الإلحاح: هذا يحدث الآن
- اجعل المشاهد يشعر بأنه يتلقى معلومات سرية
- جمل قصيرة وقوية. المضارع. كإحاطة حقيقية.

حرام مطلق: لا تستخدم أبداً أسماء بين أقواس مثل [الدولة] أو [الحدث] أو [القائد]. استخدم دائماً الأسماء الحقيقية الواردة في الموضوع.

80-90 كلمة عربية. ابدأ السرد مباشرةً بمحتوى الخطاف — بدون تاريخ، بدون مقدمة. search_keywords باللغة الإنجليزية.
{
  "title": "...", "hook": "...", "narration": "...",
  "tags": [...], "thumbnail_text": "...",
  "search_keywords": [...], "mood": "...", "format": "news_analysis"
}""",
    },
}

# TTS ses eşleştirmesi
TTS_VOICES = {
    "en": "en-US-GuyNeural",
    "tr": "tr-TR-AhmetNeural",
    "ar": "ar-SA-HamedNeural",
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
        data["format"] = "news_analysis"
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
        "format": _extract("format") or "news_analysis",
    }


def _load_recent_titles(n: int = 20) -> list[str]:
    """Son üretilmiş başlıkları döndürür (tekrar önlemek için Gemini'ye iletilir)."""
    titles = []
    # scheduled_queue.json'dan başlıkları al
    try:
        with open("scheduled_queue.json", encoding="utf-8") as f:
            queue = json.load(f)
        titles += [item["title"] for item in queue if item.get("title") and item["title"] != "?"]
    except Exception:
        pass
    # output/last_video.json'dan da al
    try:
        with open("output/last_video.json", encoding="utf-8") as f:
            last = json.load(f)
        if last.get("title"):
            titles.append(last["title"])
    except Exception:
        pass
    # Tekrarsız son n başlık
    seen = set()
    result = []
    for t in reversed(titles):
        if t not in seen:
            seen.add(t)
            result.append(t)
        if len(result) >= n:
            break
    return list(reversed(result))


def generate_script(topic: str, language: str = "en", forced_format: str = None) -> dict:
    """
    Verilen konu için Gemini ile script üretir.
    Rastgele format seçer veya forced_format belirtilirse onu kullanır.
    """
    lang = language if language in FORMAT_PROMPTS else "en"
    api_key = os.environ["GEMINI_API_KEY"]

    # Format: her zaman news_analysis
    script_format = "news_analysis"
    system_prompt = FORMAT_PROMPTS[lang][script_format]

    print(f"[script_gen] Format: {script_format} | Dil: {lang}", file=sys.stderr)

    # Son başlıkları yükle — Gemini bu konuları tekrarlamamalı
    recent_titles = _load_recent_titles(20)
    avoid_note = ""
    if recent_titles:
        titles_str = "\n".join(f"- {t}" for t in recent_titles[-10:])
        if lang == "tr":
            avoid_note = f"\n\nÖNEMLİ: Aşağıdaki başlıklar daha önce üretildi, bunlarla aynı veya çok benzer bir konu/başlık ÜRETME:\n{titles_str}"
        elif lang == "ar":
            avoid_note = f"\n\nمهم: العناوين التالية تم إنتاجها مسبقاً، لا تنتج عنواناً مماثلاً أو مشابهاً جداً:\n{titles_str}"
        else:
            avoid_note = f"\n\nIMPORTANT: The following titles were already produced. Do NOT generate a title or topic that is the same or very similar to these:\n{titles_str}"

    user_prompts = {
        "en": {
            "news_analysis": f"Write a military analysis YouTube Shorts script about: {topic}. Start the narration IMMEDIATELY with the hook — no date, no 'Today is...', no preamble. Break down what just happened, why it matters, and what happens next. Sound like a classified intelligence briefing.{avoid_note}",
        },
        "tr": {
            "news_analysis": f"Bu konu için askeri analiz YouTube Shorts senaryosu yaz: {topic}. Narrasyona DOĞRUDAN hook cümlesiyle başla — tarih yok, 'Bugün...' yok, giriş yok. Ne oldu, neden önemli ve sırada ne var? Gizli istihbarat brifingiymiş gibi yaz.{avoid_note}",
        },
        "ar": {
            "news_analysis": f"اكتب سيناريو تحليل عسكري لـ YouTube Shorts عن: {topic}. ابدأ السرد مباشرةً بجملة الخطاف — بدون تاريخ، بدون 'اليوم هو...'، بدون مقدمة. حلل ما حدث ولماذا يهم وما سيأتي. اكتب كأنها إحاطة استخباراتية سرية.{avoid_note}",
        },
    }

    user_prompt = user_prompts.get(lang, user_prompts["en"])[script_format]

    # Model fallback zinciri
    models = ["gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-2.0-flash"]
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
                script["tts_voice"] = TTS_VOICES.get(lang, TTS_VOICES["en"])
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
