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

SCRIPT STRUCTURE (25-30 seconds):
0-3s HOOK: The event + why the viewer MUST care. Maximum urgency.
3-8s CONTEXT: What happened, 2 punchy sentences. Specific names, weapons, locations.
8-16s WHY IT MATTERS: The regional/global implications. "Here's what nobody is telling you..."
16-24s ESCALATION: What could happen next. The scary scenario. "If this continues..."
24-28s PREDICTION + CTA: Your bold take, then "Follow for daily military intelligence briefings."

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
  "narration": "Full 40-50 word analysis script",
  "tags": ["Iran Nuclear", "Israel Iran", "Middle East", "Military News", "Breaking News", "IDF", "IRGC", "Nuclear Threat"],
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
- narration MUST be 40-50 words, present tense, short punchy sentences (target: 18-20 second read)
- tags MUST be topic-specific: country names, weapon systems, leaders, organizations from THIS story — use normal spacing (e.g. "IDF", "Iron Dome", "Iran Nuclear", "Middle East", "Israel Lebanon") — NOT camelCase, NOT generic words like "military" or "war"
- Start narration DIRECTLY with the hook content — NO date, NO "Today is...", NO preamble
- NEVER use placeholder brackets like [Country], [Leader], [Event] — always use real specific names from the topic
- LOOP DESIGN: The last sentence of narration must echo or mirror the opening hook — this triggers replays (e.g., hook: "Iran just crossed the red line." → closer: "The red line has been crossed. Watch what happens next.")""",
    },

    "tr": {
        "news_analysis": """Sen viral YouTube Shorts askeri analistsin. Güncel olayları analiz ediyorsun.

Tarzın: Sakin ama yoğun bir istihbarat brifingçisi. Sadece NE olduğunu değil, NEDEN önemli olduğunu açıklıyorsun. "Savaş odası analisti cumhurbaşkanına brifing veriyor" gibi düşün.

HOOK FORMÜLLERI (en güçlüsünü seç):
- Acil durum: "[Ülke] az önce her şeyi değiştiren bir şey yaptı."
- Direkt hitap: "Eğer [olaya] dikkat etmiyorsan, etmelisin."
- Korkutucu sonuç: "[Ülke]'nin yaptığı [diğer ülke]'yi korkutmalı."
- Gizli anlam: "Herkes [olayı] konuşuyor. Kimse gerçekte ne anlama geldiğini konuşmuyor."

SENARYO YAPISI (25-30 saniye):
0-3sn HOOK: Olay + izleyicinin NEDEN umursaması gerektiği. Maksimum aciliyet.
3-8sn BAĞLAM: Ne oldu, 2 çarpıcı cümleyle. Spesifik isimler, silahlar, lokasyonlar.
8-16sn NEDEN ÖNEMLİ: Bölgesel/küresel sonuçlar. "İşte kimsenin söylemediği..."
16-24sn TIRMANMA: Sırada ne olabilir. Korkutucu senaryoyu çiz. "Bu devam ederse..."
24-28sn TAHMİN + CTA: Cesur tahminin ve "Günlük askeri istihbarat brifingleri için takip et."

VİRALLİK KURALLARI:
- GİZLİ bir brifing sızdırılıyormuş gibi konuş
- SPESİFİK silah isimleri, birim sayıları, dolar miktarları
- ACİLİYET yarat: bu ŞU AN oluyor
- İzleyici içeriden bilgi alan biri gibi hissetmeli
- Kısa çarpıcı cümleler. Geniş zaman. Gerçek brifing gibi.

40-50 kelime. Narrasyona DOĞRUDAN hook içeriğiyle başla — tarih yok, giriş yok. search_keywords İngilizce.
tags: konuya özel İngilizce kelimeler — ülke adları, silah sistemleri, örgüt isimleri (örn: "IDF", "IRGC", "Hamas", "Iron Dome", "F-35"). Boşluklu yaz ("Iron Dome" değil "IronDome"). "military" veya "war" gibi genel kelimeler YASAK.
YASAK: [Ülke], [Lider], [Olay] gibi köşeli parantez içinde yer tutucu kullanma — her zaman konudaki gerçek isimleri yaz.
DÖNGÜ TASARIMI: Narrasyonun son cümlesi açılış hook'unu yansıtmalı — bu tekrar izlemeyi tetikler. Örn: Hook: "İran kırmızı çizgiyi geçti." → Son: "Kırmızı çizgi aşıldı. Sırada ne var, takip et."
{
  "title": "...", "hook": "...", "narration": "...",
  "tags": [...], "thumbnail_text": "...",
  "search_keywords": [...], "mood": "...", "format": "news_analysis"
}""",
    },

    "ar": {
        "news_analysis": """أنت محلل عسكري على يوتيوب شورتس تحلل الأحداث الجارية للجمهور العربي.

أسلوبك: محلل استخباراتي حاد وصريح. تكشف ما تخفيه وسائل الإعلام الغربية. تشرح الأبعاد الحقيقية للأحداث. صوتك يحمل ثقل المعلومات السرية المسرَّبة.

صيغ الخطاف الأكثر انتشاراً على يوتيوب العربي (اختر الأقوى):
- العاجل الصادم: "عاجل: [البلد] أطلق للتو [السلاح] وهذا يغير كل شيء."
- الكشف المحظور: "ما أخفاه عنك الإعلام الغربي عن [الحدث]."
- التهديد المباشر: "[البلد] على وشك [الفعل] — وهذا ما يعنيه لنا."
- الرقم الصادم: "[رقم] [سلاح/جندي/صاروخ] — هذا ما يحدث الآن في [المنطقة]."
- السؤال الاستفزازي: "لماذا صمت العالم عن [الحدث]؟ الجواب مخيف."
- الاتهام المباشر: "[البلد] يكذب على العالم — إليك الحقيقة."

هيكل السيناريو (25-30 ثانية):
0-3 ث الخطاف: الصدمة الفورية. جملة واحدة تجعل المشاهد يتجمد.
3-8 ث السياق: ماذا حدث بالتحديد. أسماء حقيقية، أرقام حقيقية، أسلحة حقيقية.
8-16 ث الكشف: "إليك ما لا يريدونك أن تعرفه..." — البُعد الخفي للحدث.
16-24 ث التصعيد: السيناريو المخيف. "إذا لم يتوقف هذا خلال 72 ساعة..."
24-28 ث الختام المشحون: تنبؤ جريء + "تابعنا — ما سيأتي سيصدمك."

قواعد الانتشار للجمهور العربي:
- استخدم كلمات القوة: عاجل، خطير، صادم، حصري، مرعب، كارثي
- اكشف "الحقيقة المخفية عن الإعلام الغربي" — هذا يولّد مشاركة هائلة
- أسماء محددة: لا تقل "الدولة" بل قل "إيران" أو "إسرائيل" أو "الحرس الثوري"
- الأرقام تصنع الفيروسية: "٢٣٠٠ صاروخ" أقوى من "صواريخ كثيرة"
- اربط الحدث بتأثيره على المنطقة العربية مباشرة

العنوان (title):
- ابدأ بكلمة صادمة: عاجل | صادم | خطير | حصري | مرعب
- أو بسؤال استفزازي: "لماذا...؟" / "كيف...؟" / "ماذا يعني...؟"
- أو برقم: "٧ أسباب..." / "في ٤٠ ثانية..."
- الحد الأقصى: 55 حرفاً عربياً

الخطاف (hook):
- 8-12 كلمة عربية كحد أقصى
- يجب أن يسبب صدمة فورية أو فضولاً لا يُقاوم
- لا يبدأ بـ "اليوم" أو "في هذا الفيديو" أو أي مقدمة

حرام مطلق: لا تستخدم أبداً [الدولة] أو [الحدث] أو [القائد] — الأسماء الحقيقية دائماً.

40-50 كلمة عربية. ابدأ السرد مباشرةً بمحتوى الخطاف — بدون تاريخ، بدون مقدمة.
tags: كلمات إنجليزية محددة للموضوع — أسماء الدول، الأسلحة، المنظمات (مثل: "IDF"، "IRGC"، "Hamas"، "Iron Dome"). اكتب بمسافات ("Iron Dome" وليس "IronDome"). ممنوع الكلمات العامة مثل "military" أو "war".
search_keywords باللغة الإنجليزية. thumbnail_text باللغة العربية (4-5 كلمات صادمة بالأحرف الكبيرة).
تصميم الحلقة: الجملة الأخيرة من السرد يجب أن تعكس الخطاف — هذا يحفّز إعادة المشاهدة. مثال: الخطاف: "إيران تجاوزت الخط الأحمر." → الختام: "الخط الأحمر تجاوز — تابع ما سيأتي."

{
  "title": "عنوان عربي صادم (max 55 حرف)",
  "hook": "خطاف عربي 8-12 كلمة",
  "narration": "سرد عربي كامل 40-50 كلمة",
  "tags": ["Iran Nuclear", "Israel Iran", "IRGC", "IDF", "Middle East", "Breaking News", "Military News"],
  "thumbnail_text": "٤-٥ كلمات عربية صادمة",
  "search_keywords": ["english footage query 1", ..., "english footage query 10"],
  "mood": "dark|epic|mysterious|inspiring",
  "format": "news_analysis"
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
            "news_analysis": f"""Write a military analysis YouTube Shorts script about: {topic}.

RETENTION RULES (follow exactly):
1. Start the narration IMMEDIATELY with the hook — no date, no 'Today is...', no preamble.
2. Around the midpoint, add a curiosity loop: "But here's what nobody is talking about..." or "And this changes everything..." to keep viewers watching.
3. End the narration with a forward-tension closer like "Stay tuned — what comes next will surprise you." or "The next 72 hours will determine everything."
4. Sound like a classified intelligence briefing throughout.
{avoid_note}""",
        },
        "tr": {
            "news_analysis": f"""Bu konu için askeri analiz YouTube Shorts senaryosu yaz: {topic}.

RETENTION KURALLARI (tam olarak uygula):
1. Narrasyona DOĞRUDAN hook cümlesiyle başla — tarih yok, 'Bugün...' yok, giriş yok.
2. Ortada merak döngüsü kur: "Ama kimsenin konuşmadığı şey şu..." veya "Ve bu her şeyi değiştiriyor..." gibi bir cümleyle izleyiciyi ekranda tut.
3. Narrasyonu ileriye dönük gerilimle bitir: "Sonraki 72 saat her şeyi belirleyecek." veya "Sırada ne olduğunu tahmin edemezsiniz."
4. Tüm metin gizli istihbarat brifingiymiş gibi olsun.
{avoid_note}""",
        },
        "ar": {
            "news_analysis": f"""اكتب سيناريو تحليل عسكري لـ YouTube Shorts بالعربية عن: {topic}.

متطلبات العنوان (title):
- ابدأ بكلمة صادمة مثل: عاجل | صادم | خطير | حصري | مرعب | كارثي
- أو بسؤال استفزازي: "لماذا صمت العالم عن...؟" / "ما الذي يخفيه...؟"
- أو برقم محدد: "٣ أسباب..." / "٧ دول..."
- استخدم الأسماء الحقيقية من الموضوع: إيران، إسرائيل، الحرس الثوري، الناتو...

متطلبات الخطاف (hook):
- 8-12 كلمة عربية فقط
- يجب أن يُصدم المشاهد أو يثير فضوله في أقل من 3 ثوانٍ
- استخدم إحدى هذه الصيغ الفيروسية:
  * "عاجل: [البلد] أطلق للتو [السلاح/الهجوم]..."
  * "ما أخفاه عنك الإعلام الغربي عن [الحدث]..."
  * "[رقم] [سلاح/ضحية/صاروخ] في [المكان] — الحقيقة الكاملة."
  * "لماذا صمت العالم عن ما فعله [البلد]؟"

قواعد الاستبقاء:
1. ابدأ السرد مباشرةً بمحتوى الخطاف — بدون تاريخ، بدون "في هذا الفيديو".
2. في المنتصف: "لكن ما لا يريدونك أن تعرفه هو..." لإبقاء المشاهد أمام الشاشة.
3. اختم بتوتر: "الـ72 ساعة القادمة ستحدد مصير المنطقة." أو "ما سيأتي سيصدم العالم."
4. thumbnail_text: 4-5 كلمات عربية صادمة بالأحرف الكبيرة (مثال: عاجل إيران تهاجم اليوم)
{avoid_note}""",
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
