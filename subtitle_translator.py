"""
subtitle_translator.py — VTT altyazısını birden fazla dile çevirir ve YouTube'a yükler.

MyMemory API (ücretsiz, kayıt gerekmez, günlük 5000 kelime) ile çeviri yapar.
Çevrilen altyazılar captions_uploader aracılığıyla YouTube'a eklenir.

Hedef diller (varsayılan):
  es — İspanyolca (600M konuşucu)
  fr — Fransızca (300M konuşucu)
  pt — Portekizce (250M konuşucu)
  de — Almanca (100M konuşucu)
  ar — Arapça (400M konuşucu)

Gereksinim: YOUTUBE_TOKEN_JSON (captions_uploader ile aynı)
"""

import os
import re
import time
import tempfile
from pathlib import Path

import requests

TIMEOUT = 15

# Varsayılan hedef diller: (kod, ad) çiftleri
DEFAULT_TARGET_LANGUAGES = [
    ("es", "Spanish"),
    ("fr", "French"),
    ("pt", "Portuguese"),
    ("de", "German"),
]

# Opsiyonel (TRANSLATE_LANGUAGES env ile açılır)
EXTRA_LANGUAGES = [
    ("ar", "Arabic"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("hi", "Hindi"),
    ("it", "Italian"),
]

MYMEMORY_URL = "https://api.mymemory.translated.net/get"


# ─────────── VTT ayrıştırma ───────────

def _parse_vtt_blocks(vtt_path: str) -> list[dict]:
    """
    VTT dosyasını bloklara ayırır.
    Returns: [{"timing": "00:00:01.000 --> 00:00:03.500", "text": "Hello world"}, ...]
    """
    with open(vtt_path, encoding="utf-8") as f:
        content = f.read()

    # WEBVTT başlığını kaldır
    content = re.sub(r"^WEBVTT[^\n]*\n", "", content).strip()

    blocks = []
    for chunk in content.split("\n\n"):
        lines = [l.strip() for l in chunk.splitlines() if l.strip()]
        timing_line = None
        text_lines = []
        for line in lines:
            if "-->" in line:
                timing_line = line
            elif timing_line and not re.match(r"^\d+$", line):
                text_lines.append(line)
        if timing_line and text_lines:
            blocks.append({
                "timing": timing_line,
                "text": " ".join(text_lines),
            })
    return blocks


def _blocks_to_vtt(blocks: list[dict], translated_texts: list[str]) -> str:
    """Çevrilmiş metinlerle yeni VTT içeriği oluşturur."""
    lines = ["WEBVTT", ""]
    for i, (block, trans) in enumerate(zip(blocks, translated_texts), 1):
        lines.append(str(i))
        lines.append(block["timing"])
        lines.append(trans)
        lines.append("")
    return "\n".join(lines)


# ─────────── Çeviri ───────────

def _translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """
    MyMemory API ile metin çevirir.
    Ücretsiz tier: günlük 5000 kelime / IP.
    """
    if not text.strip():
        return text
    try:
        params = {
            "q": text,
            "langpair": f"{source_lang}|{target_lang}",
            "de": "warshorts@pipeline.auto",  # İsteğe bağlı email — limit artırır
        }
        resp = requests.get(MYMEMORY_URL, params=params, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            translated = data.get("responseData", {}).get("translatedText", "")
            if translated and data.get("responseStatus") == 200:
                return translated
        return text  # Çeviri başarısız → orijinal metin
    except Exception:
        return text


def _translate_blocks(
    blocks: list[dict],
    source_lang: str,
    target_lang: str,
    delay: float = 0.3,
) -> list[str]:
    """
    Tüm blokları çevirir.
    Rate limit için bloklar arasında kısa bekleme.
    """
    translated = []
    for i, block in enumerate(blocks):
        text = block["text"]
        trans = _translate_text(text, source_lang, target_lang)
        translated.append(trans)
        if (i + 1) % 10 == 0:
            time.sleep(delay)  # Her 10 blokta bir bekle
    return translated


# ─────────── Ana fonksiyon ───────────

def translate_and_upload_captions(
    video_id: str,
    vtt_path: str,
    source_language: str = "en",
    target_languages: list[tuple] = None,
) -> dict:
    """
    VTT'yi birden fazla dile çevirir ve YouTube'a yükler.

    Args:
        video_id: YouTube video ID
        vtt_path: Kaynak VTT dosyası
        source_language: Kaynak dil kodu ('en', 'tr', ...)
        target_languages: [(kod, ad), ...] listesi; None ise varsayılan kullanılır

    Returns:
        {"es": True, "fr": False, ...}
    """
    if not os.path.exists(vtt_path):
        print(f"[translator] VTT bulunamadı: {vtt_path}")
        return {}

    # Hedef dilleri belirle
    if target_languages is None:
        target_languages = list(DEFAULT_TARGET_LANGUAGES)
        # Env'den ek diller eklenebilir
        extra_codes = os.environ.get("TRANSLATE_LANGUAGES", "").split(",")
        for code in extra_codes:
            code = code.strip().lower()
            for ec, en in EXTRA_LANGUAGES:
                if ec == code:
                    target_languages.append((ec, en))
                    break

    # Kaynak dili hedef diller arasından çıkar
    target_languages = [(c, n) for c, n in target_languages if c != source_language]

    blocks = _parse_vtt_blocks(vtt_path)
    if not blocks:
        print("[translator] VTT içeriği boş veya ayrıştırılamadı.")
        return {}

    print(f"[translator] {len(blocks)} altyazı bloğu, {len(target_languages)} hedef dil")

    try:
        from captions_uploader import upload_captions
    except ImportError:
        print("[translator] captions_uploader bulunamadı.")
        return {}

    results = {}

    for lang_code, lang_name in target_languages:
        print(f"[translator] {lang_name} ({lang_code}) çevriliyor...")

        try:
            translated_texts = _translate_blocks(blocks, source_language, lang_code)

            # Geçici VTT dosyası oluştur
            vtt_content = _blocks_to_vtt(blocks, translated_texts)
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=f"_{lang_code}.vtt", delete=False, encoding="utf-8"
            )
            tmp.write(vtt_content)
            tmp.close()

            # YouTube'a yükle
            success = upload_captions(
                video_id=video_id,
                vtt_path=tmp.name,
                language=lang_code,
                name=f"Auto-translated ({lang_name})",
            )
            os.unlink(tmp.name)
            results[lang_code] = success

            if success:
                print(f"[translator] ✓ {lang_name} altyazısı yüklendi")
            else:
                print(f"[translator] ✗ {lang_name} yüklenemedi")

            time.sleep(1)  # API rate limit

        except Exception as e:
            print(f"[translator] {lang_name} hatası: {e}")
            results[lang_code] = False

    successful = sum(1 for v in results.values() if v)
    print(f"[translator] Tamamlandı: {successful}/{len(target_languages)} dil yüklendi")
    return results


if __name__ == "__main__":
    import sys
    vid = sys.argv[1] if len(sys.argv) > 1 else input("Video ID: ")
    vtt = sys.argv[2] if len(sys.argv) > 2 else "output/narration.vtt"
    src = sys.argv[3] if len(sys.argv) > 3 else "en"
    result = translate_and_upload_captions(vid, vtt, src)
    print(result)
