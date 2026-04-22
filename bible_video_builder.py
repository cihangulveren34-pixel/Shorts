"""
bible_video_builder.py — İncil hikaye videoları için video montajı.

Format: 1080x1920 YouTube Shorts, ≤60s
Katman yapısı (alttan üste):
  1. Pexels stok video (mood'a göre spiritual/epic footage)
  2. Karartma overlay (opacity ~0.55)
  3. Akan altyazı — VTT timing ile senkronize, ekranın ortasında
  4. Üst bar — kitap referansı ("1 Samuel 17:45-50")
  5. Hook overlay — ilk 4s büyük çarpıcı metin
  6. Moral overlay — son 5s ders/moral
  7. Ses — TTS narration
"""

import os
import json
import random
import math
import tempfile
import requests

import numpy as np
from PIL import Image, ImageDraw, ImageFont

if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    CompositeVideoClip,
    CompositeAudioClip,
    ImageClip,
    ColorClip,
    concatenate_videoclips,
)

from tts import parse_vtt

TARGET_W = 1080
TARGET_H = 1920
OUTPUT_PATH = os.path.join("output", "bible_short.mp4")

# ─── Renk paletleri (mood'a göre) ───────────────────────────────────────────

MOOD_PALETTES = {
    "epic":        {"bg": (15, 10, 5),   "accent": (255, 180, 50),  "text": (255, 245, 220)},
    "peaceful":    {"bg": (5, 20, 35),   "accent": (100, 200, 255), "text": (220, 240, 255)},
    "dramatic":    {"bg": (20, 5, 10),   "accent": (255, 80, 80),   "text": (255, 220, 220)},
    "miraculous":  {"bg": (10, 10, 30),  "accent": (255, 215, 80),  "text": (255, 245, 210)},
    "sorrowful":   {"bg": (10, 10, 15),  "accent": (140, 140, 200), "text": (210, 210, 240)},
    "redemptive":  {"bg": (10, 20, 15),  "accent": (100, 220, 150), "text": (210, 245, 225)},
}
DEFAULT_PALETTE = {"bg": (10, 10, 25), "accent": (255, 215, 80), "text": (255, 245, 220)}


def _get_palette(mood: str) -> dict:
    return MOOD_PALETTES.get(mood, DEFAULT_PALETTE)


# ─── Font yardımcısı ─────────────────────────────────────────────────────────

FONT_CANDIDATES = [
    "assets/fonts/Montserrat-Bold.ttf",
    "assets/fonts/Roboto-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

FONT_REGULAR_CANDIDATES = [
    "assets/fonts/Montserrat-Regular.ttf",
    "assets/fonts/Roboto-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates = FONT_CANDIDATES if bold else FONT_REGULAR_CANDIDATES
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    # Fallback: try bold list for regular too
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


# ─── Pexels görsel dedup ─────────────────────────────────────────────────────

BIBLE_SEEN_PEXELS_PATH = os.path.join("output", "bible_seen_pexels_ids.json")
MAX_SEEN_IDS = 500


def _load_seen_ids() -> set:
    try:
        with open(BIBLE_SEEN_PEXELS_PATH, "r") as f:
            ids = json.load(f)
            if isinstance(ids, list):
                return set(ids)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return set()


def _save_seen_ids(seen: set) -> None:
    os.makedirs(os.path.dirname(BIBLE_SEEN_PEXELS_PATH) or ".", exist_ok=True)
    id_list = list(seen)
    if len(id_list) > MAX_SEEN_IDS:
        id_list = id_list[-MAX_SEEN_IDS:]
    with open(BIBLE_SEEN_PEXELS_PATH, "w") as f:
        json.dump(id_list, f)
    print(f"[bible_video] Seen Pexels IDs kaydedildi: {len(id_list)} adet")


# ─── Pexels footage indir ────────────────────────────────────────────────────

def _fetch_pexels_clips(keywords: list, n: int = 3, seen_ids: set = None) -> tuple:
    """Pexels'ten spiritual/epic klipleri indirir. Daha önce kullanılanları atlar."""
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if seen_ids is None:
        seen_ids = set()
    new_ids = set()

    if not api_key:
        print("[bible_video] PEXELS_API_KEY eksik — gradient arka plan kullanılacak")
        return [], new_ids

    downloaded = []
    session_seen = set()

    kw_pool = list(keywords)
    random.shuffle(kw_pool)
    queries = kw_pool[:5]

    for query in queries:
        if len(downloaded) >= n:
            break
        try:
            page = random.randint(1, 3)
            resp = requests.get(
                "https://api.pexels.com/videos/search",
                params={"query": query, "per_page": 10, "orientation": "portrait", "page": page},
                headers={"Authorization": api_key},
                timeout=15,
            )
            if resp.status_code != 200:
                continue
            videos = resp.json().get("videos", [])
            random.shuffle(videos)
            for video in videos:
                if len(downloaded) >= n:
                    break
                vid_id = video["id"]
                vid_key = f"pexels_{vid_id}"
                if vid_key in session_seen or vid_id in seen_ids:
                    continue
                session_seen.add(vid_key)
                best = None
                for vf in video.get("video_files", []):
                    if vf.get("file_type") == "video/mp4" and vf.get("height", 0) >= 1080:
                        if best is None or vf.get("height", 0) > best.get("height", 0):
                            best = vf
                if not best:
                    continue
                try:
                    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, prefix="bible_pexels_")
                    tmp.close()
                    r = requests.get(best["link"], timeout=60, stream=True)
                    r.raise_for_status()
                    with open(tmp.name, "wb") as f:
                        for chunk in r.iter_content(chunk_size=256 * 1024):
                            f.write(chunk)
                    downloaded.append(tmp.name)
                    new_ids.add(vid_id)
                    print(f"[bible_video] Pexels klip indirildi: {query!r} (id={vid_id})")
                except Exception as e:
                    print(f"[bible_video] Pexels indirme hatası: {e}")
        except Exception as e:
            print(f"[bible_video] Pexels arama hatası ({query!r}): {e}")

    return downloaded, new_ids


# ─── Arka plan müzik (Freesound API) ─────────────────────────────────────────

BGM_QUERIES = {
    "epic":       "epic orchestral cinematic",
    "peaceful":   "peaceful ambient piano",
    "dramatic":   "dramatic cinematic tension",
    "miraculous": "spiritual ambient mysterious",
    "sorrowful":  "sad ambient piano",
    "redemptive": "hopeful ambient piano",
}
BGM_DEFAULT_QUERY = "spiritual ambient calm"


def _fetch_bgm(mood: str, min_duration: float = 30.0) -> str | None:
    """Freesound API'den mood'a uygun arka plan müziği indirir."""
    api_key = os.environ.get("FREESOUND_API_KEY", "")
    if not api_key:
        print("[bible_video] FREESOUND_API_KEY eksik — bgm olmadan devam")
        return None

    query = BGM_QUERIES.get(mood, BGM_DEFAULT_QUERY)

    try:
        resp = requests.get(
            "https://freesound.org/apiv2/search/text/",
            params={
                "query": query,
                "filter": f"duration:[{min_duration} TO 300] license:\"Creative Commons 0\"",
                "fields": "id,name,duration,previews",
                "page_size": 15,
                "sort": "rating_desc",
                "token": api_key,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"[bible_video] Freesound arama hatası: {resp.status_code}")
            return None

        results = resp.json().get("results", [])
        if not results:
            print(f"[bible_video] Freesound sonuç bulunamadı: {query!r}")
            return None

        # Rastgele birini seç
        sound = random.choice(results[:10])
        preview_url = sound.get("previews", {}).get("preview-hq-mp3")
        if not preview_url:
            print("[bible_video] Freesound preview URL bulunamadı")
            return None

        # İndir
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False, prefix="bible_bgm_")
        tmp.close()
        r = requests.get(preview_url, timeout=30)
        r.raise_for_status()
        with open(tmp.name, "wb") as f:
            f.write(r.content)

        print(f"[bible_video] BGM indirildi: {sound['name']} ({sound['duration']:.0f}s)")
        return tmp.name

    except Exception as e:
        print(f"[bible_video] Freesound hatası: {e}")
        return None


# ─── Yardımcı fonksiyonlar ──────────────────────────────────────────────────

def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
    """Metni satırlara böler."""
    words = text.split()
    lines = []
    current = ""
    tmp_img = Image.new("RGB", (1, 1))
    tmp_draw = ImageDraw.Draw(tmp_img)
    for word in words:
        test = (current + " " + word).strip()
        try:
            w = tmp_draw.textlength(test, font=font)
        except AttributeError:
            bbox = font.getbbox(test)
            w = bbox[2] - bbox[0]
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _make_gradient_bg(palette: dict, duration: float) -> ImageClip:
    """Dikey renk geçişli arka plan."""
    img = Image.new("RGB", (TARGET_W, TARGET_H))
    draw = ImageDraw.Draw(img)
    bg = palette["bg"]
    accent = palette["accent"]
    for y in range(TARGET_H):
        t = y / TARGET_H
        mid_factor = math.exp(-((t - 0.5) ** 2) / 0.08) * 0.3
        r = int(bg[0] + (accent[0] - bg[0]) * mid_factor)
        g = int(bg[1] + (accent[1] - bg[1]) * mid_factor)
        b = int(bg[2] + (accent[2] - bg[2]) * mid_factor)
        draw.line([(0, y), (TARGET_W, y)], fill=(r, g, b))
    arr = np.array(img)
    return ImageClip(arr).set_duration(duration)


def _prepare_bg_clip(path: str, duration: float) -> VideoFileClip:
    """Klip yükle, 1080x1920 kırp/yakınlaştır, sesi kaldır, karartma ekle."""
    clip = VideoFileClip(path, audio=False)

    target_ratio = TARGET_W / TARGET_H
    clip_ratio = clip.w / clip.h

    if clip_ratio > target_ratio:
        new_h = TARGET_H
        new_w = int(clip.w * (TARGET_H / clip.h))
    else:
        new_w = TARGET_W
        new_h = int(clip.h * (TARGET_W / clip.w))

    clip = clip.resize((new_w, new_h))
    x1 = (new_w - TARGET_W) // 2
    y1 = (new_h - TARGET_H) // 2
    clip = clip.crop(x1=x1, y1=y1, x2=x1 + TARGET_W, y2=y1 + TARGET_H)

    if clip.duration < duration:
        n_loops = int(math.ceil(duration / clip.duration))
        clip = concatenate_videoclips([clip] * n_loops).subclip(0, duration)
    else:
        clip = clip.subclip(0, duration)

    # Karartma overlay (opacity 0.55)
    darken = ColorClip(size=(TARGET_W, TARGET_H), color=[0, 0, 0]).set_opacity(0.55).set_duration(duration)
    return CompositeVideoClip([clip, darken])


# ─── Overlay oluşturucular ───────────────────────────────────────────────────

def _make_verse_ref_bar(verse_ref: str, palette: dict, duration: float) -> ImageClip:
    """Üst bar — kitap referansı (tüm video boyunca)."""
    img = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    accent = palette["accent"]

    # Yarı saydam bar
    bar_h = 70
    draw.rectangle([(0, 50), (TARGET_W, 50 + bar_h)], fill=(0, 0, 0, 140))

    # Accent alt çizgi
    draw.rectangle([(0, 50 + bar_h - 3), (TARGET_W, 50 + bar_h)], fill=(*accent, 200))

    # Referans metni
    font = _load_font(32, bold=False)
    ref_upper = verse_ref.upper()
    try:
        tw = draw.textlength(ref_upper, font=font)
    except AttributeError:
        bbox = font.getbbox(ref_upper)
        tw = bbox[2] - bbox[0]
    x = (TARGET_W - tw) // 2
    y = 50 + (bar_h - 32) // 2
    draw.text((x + 2, y + 2), ref_upper, font=font, fill=(0, 0, 0, 150))
    draw.text((x, y), ref_upper, font=font, fill=(255, 255, 255, 220))

    arr = np.array(img)
    return ImageClip(arr, ismask=False).set_duration(duration)


def _make_hook_overlay(hook_line: str, palette: dict, duration: float = 4.0) -> ImageClip:
    """İlk 4 saniyede gösterilen büyük hook metni."""
    img = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    accent = palette["accent"]
    text_color = palette["text"]

    font = _load_font(58)
    max_w = TARGET_W - 120
    lines = _wrap_text(hook_line, font, max_w)

    line_h = 72
    total_h = len(lines) * line_h
    y_start = int(TARGET_H * 0.35) - total_h // 2

    # Arka plan kutu
    pad = 30
    draw.rectangle(
        [(50, y_start - pad), (TARGET_W - 50, y_start + total_h + pad)],
        fill=(0, 0, 0, 170),
    )

    for i, line in enumerate(lines):
        y = y_start + i * line_h
        try:
            lw = draw.textlength(line, font=font)
        except AttributeError:
            bbox = font.getbbox(line)
            lw = bbox[2] - bbox[0]
        x = (TARGET_W - lw) // 2
        draw.text((x + 3, y + 3), line, font=font, fill=(0, 0, 0, 200))
        draw.text((x, y), line, font=font, fill=(*accent, 255))

    arr = np.array(img)
    clip = ImageClip(arr, ismask=False).set_duration(duration)
    # Fade out
    clip = clip.crossfadeout(0.5)
    return clip


def _make_moral_overlay(moral_text: str, cta_line: str, palette: dict, duration: float = 5.0) -> ImageClip:
    """Son 5 saniyede gösterilen moral/ders metni + CTA."""
    img = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    accent = palette["accent"]
    text_color = palette["text"]

    # Moral metni (büyük)
    font_moral = _load_font(52)
    max_w = TARGET_W - 120
    lines = _wrap_text(moral_text, font_moral, max_w)

    line_h = 66
    total_h = len(lines) * line_h
    y_start = int(TARGET_H * 0.38) - total_h // 2

    # Arka plan kutu
    pad = 30
    box_y2 = y_start + total_h + pad
    draw.rectangle(
        [(50, y_start - pad), (TARGET_W - 50, box_y2)],
        fill=(0, 0, 0, 180),
    )

    for i, line in enumerate(lines):
        y = y_start + i * line_h
        try:
            lw = draw.textlength(line, font=font_moral)
        except AttributeError:
            bbox = font_moral.getbbox(line)
            lw = bbox[2] - bbox[0]
        x = (TARGET_W - lw) // 2
        draw.text((x + 3, y + 3), line, font=font_moral, fill=(0, 0, 0, 200))
        draw.text((x, y), line, font=font_moral, fill=(*text_color, 255))

    # Accent çizgi
    draw.rectangle(
        [(TARGET_W // 2 - 80, box_y2 + 10), (TARGET_W // 2 + 80, box_y2 + 13)],
        fill=(*accent, 220),
    )

    # CTA metni (küçük)
    font_cta = _load_font(36, bold=False)
    try:
        cw = draw.textlength(cta_line, font=font_cta)
    except AttributeError:
        bbox = font_cta.getbbox(cta_line)
        cw = bbox[2] - bbox[0]
    cx = (TARGET_W - cw) // 2
    cy = box_y2 + 30
    draw.text((cx + 2, cy + 2), cta_line, font=font_cta, fill=(0, 0, 0, 160))
    draw.text((cx, cy), cta_line, font=font_cta, fill=(*accent, 230))

    arr = np.array(img)
    clip = ImageClip(arr, ismask=False).set_duration(duration)
    # Fade in
    clip = clip.crossfadein(0.5)
    return clip


def _make_subtitle_clips(chunks: list, palette: dict) -> list:
    """
    VTT chunk'larından akan altyazı klipleri üretir.
    Her chunk: {start, end, text}
    """
    text_color = palette["text"]
    clips = []

    for chunk in chunks:
        text = chunk["text"]
        start = chunk["start"]
        end = chunk["end"]
        dur = end - start

        if dur <= 0 or not text.strip():
            continue

        # Altyazı frame'i oluştur
        img = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        font = _load_font(56)
        max_w = TARGET_W - 100
        lines = _wrap_text(text, font, max_w)

        line_h = 68
        total_h = len(lines) * line_h
        # Ekranın ortasında (biraz aşağı — verse ref bar'ı ve hook'un altında)
        y_start = int(TARGET_H * 0.50) - total_h // 2

        # Yarı saydam arka plan kutu
        pad = 18
        draw.rounded_rectangle(
            [(60, y_start - pad), (TARGET_W - 60, y_start + total_h + pad)],
            radius=16,
            fill=(0, 0, 0, 160),
        )

        for i, line in enumerate(lines):
            y = y_start + i * line_h
            try:
                lw = draw.textlength(line, font=font)
            except AttributeError:
                bbox = font.getbbox(line)
                lw = bbox[2] - bbox[0]
            x = (TARGET_W - lw) // 2
            # Gölge
            draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 180))
            # Ana metin
            draw.text((x, y), line, font=font, fill=(*text_color, 245))

        arr = np.array(img)
        clip = (
            ImageClip(arr, ismask=False)
            .set_duration(dur)
            .set_start(start)
        )
        clips.append(clip)

    return clips


# ─── Ana video builder ────────────────────────────────────────────────────────

def build_bible_video(
    script: dict,
    audio_path: str,
    vtt_path: str,
    output_path: str = OUTPUT_PATH,
) -> str:
    """
    İncil hikaye videosu üretir.

    Args:
        script: bible_script_gen.py çıktısı
        audio_path: TTS narration MP3
        vtt_path: TTS VTT dosyası (altyazı zamanlama)
        output_path: Çıktı MP4 yolu

    Returns:
        output_path
    """
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    mood = script.get("mood", "miraculous")
    hook_line = script["hook_line"]
    verse_ref = script.get("verse_ref", "")
    moral_text = script.get("moral_text", script.get("moral", ""))
    cta_line = script.get("cta_line", "Follow for daily Bible stories.")
    pexels_keywords = script.get("pexels_keywords", ["spiritual light", "ancient temple"])

    palette = _get_palette(mood)

    # ─── Ses ──────────────────────────────────────────────────────────────────
    audio_clip = AudioFileClip(audio_path)
    total_duration = min(audio_clip.duration + 1.0, 60.0)  # +1s buffer, max 60s
    print(f"[bible_video] Toplam süre: {total_duration:.1f}s")

    # ─── Arka plan müzik (Freesound) ─────────────────────────────────────────
    bgm_path = _fetch_bgm(mood, min_duration=total_duration * 0.5)
    bgm_tmp = bgm_path  # temizlik için sakla

    # ─── VTT chunk'ları ──────────────────────────────────────────────────────
    chunks = parse_vtt(vtt_path, words_per_chunk=4)
    print(f"[bible_video] {len(chunks)} altyazı chunk'ı yüklendi")

    # ─── Pexels footage ──────────────────────────────────────────────────────
    seen_pexels = _load_seen_ids()
    clip_paths, new_pexels_ids = _fetch_pexels_clips(pexels_keywords, n=2, seen_ids=seen_pexels)
    seen_pexels.update(new_pexels_ids)
    _save_seen_ids(seen_pexels)
    tmp_files = list(clip_paths)

    # ─── Arka plan ───────────────────────────────────────────────────────────
    print("[bible_video] Arka plan hazırlanıyor...")
    if clip_paths:
        bg_clips = []
        per_clip = total_duration / max(len(clip_paths), 1)
        for p in clip_paths:
            try:
                bg_clips.append(_prepare_bg_clip(p, per_clip))
            except Exception as e:
                print(f"[bible_video] Klip yüklenemedi ({p}): {e}")
        if bg_clips:
            bg_video = concatenate_videoclips(bg_clips)
            if bg_video.duration < total_duration:
                fill = _make_gradient_bg(palette, total_duration - bg_video.duration)
                bg_video = concatenate_videoclips([bg_video, fill])
        else:
            bg_video = _make_gradient_bg(palette, total_duration)
    else:
        bg_video = _make_gradient_bg(palette, total_duration)

    # ─── Overlay katmanları ──────────────────────────────────────────────────
    layers = [bg_video]

    # 1) Verse referansı bar (tüm video)
    print("[bible_video] Verse ref bar oluşturuluyor...")
    verse_bar = _make_verse_ref_bar(verse_ref, palette, total_duration)
    layers.append(verse_bar)

    # 2) Akan altyazılar
    print("[bible_video] Altyazı klipleri oluşturuluyor...")
    subtitle_clips = _make_subtitle_clips(chunks, palette)
    layers.extend(subtitle_clips)

    # 3) Hook overlay (ilk 4 saniye)
    print("[bible_video] Hook overlay oluşturuluyor...")
    hook_duration = min(4.0, total_duration)
    hook_overlay = _make_hook_overlay(hook_line, palette, hook_duration).set_start(0)
    layers.append(hook_overlay)

    # 4) Moral overlay (son 5 saniye)
    print("[bible_video] Moral overlay oluşturuluyor...")
    moral_duration = min(5.0, total_duration)
    moral_start = max(total_duration - moral_duration, 0)
    moral_overlay = _make_moral_overlay(moral_text, cta_line, palette, moral_duration).set_start(moral_start)
    layers.append(moral_overlay)

    # ─── Birleştir ───────────────────────────────────────────────────────────
    print("[bible_video] Katmanlar birleştiriliyor...")
    final_video = CompositeVideoClip(layers, size=(TARGET_W, TARGET_H)).set_duration(total_duration)

    # Ses ekle — TTS narration + arka plan müzik mix
    narration_audio = audio_clip.subclip(0, min(audio_clip.duration, total_duration))

    if bgm_path:
        try:
            bgm_clip = AudioFileClip(bgm_path)
            # Loop veya kırp
            if bgm_clip.duration < total_duration:
                import math as _math
                n_loops = int(_math.ceil(total_duration / bgm_clip.duration))
                from moviepy.editor import concatenate_audioclips
                bgm_clip = concatenate_audioclips([bgm_clip] * n_loops)
            bgm_clip = bgm_clip.subclip(0, total_duration).volumex(0.22)  # %22 volume
            mixed_audio = CompositeAudioClip([narration_audio, bgm_clip])
            final_video = final_video.set_audio(mixed_audio)
            print("[bible_video] BGM mix edildi (volume: 22%)")
        except Exception as e:
            print(f"[bible_video] BGM mix hatası, sadece TTS kullanılacak: {e}")
            final_video = final_video.set_audio(narration_audio)
    else:
        final_video = final_video.set_audio(narration_audio)

    # ─── Export ──────────────────────────────────────────────────────────────
    print(f"[bible_video] Export ediliyor: {output_path}")
    final_video.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        bitrate="5000k",
        audio_bitrate="192k",
        threads=4,
        preset="fast",
        ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        logger=None,
    )

    # ─── Temizlik ────────────────────────────────────────────────────────────
    audio_clip.close()
    final_video.close()
    if bgm_tmp:
        tmp_files.append(bgm_tmp)
    for p in tmp_files:
        try:
            os.unlink(p)
        except OSError:
            pass

    print(f"[bible_video] Video tamamlandı: {output_path}")
    return output_path
