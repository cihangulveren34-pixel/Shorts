"""
binaural_video_builder.py — Binaural beats + math geometry Shorts icin video montaji.

Format: 1080x1920 YouTube Shorts (30 saniye)
Yapi:
  - Arka plan: Manim math animasyonu (binaural_anim_gen.py ciktisi)
  - Hook overlay: Ust kisim — buyuk metin
  - Binaural info overlay: Alt kisim — Hz + brainwave adi + benefit
  - Ses: freq_audio_gen.py tarafindan uretilen binaural beat MP3

freq_video_builder.py'nin uyarlanmis hali. Pexels yerine Manim MP4 kullanir.
"""

import os
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Pillow 10+ uyumlulugu
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    ColorClip,
    concatenate_videoclips,
)

TARGET_W = 1080
TARGET_H = 1920
OUTPUT_PATH = os.path.join("output", "binaural_short.mp4")

# ─── Renk paletleri (freq_video_builder.py ile ayni) ─────────────────────────

MOOD_PALETTES = {
    "calm":       {"bg": (10, 20, 40),    "accent": (100, 180, 255), "text": (220, 235, 255)},
    "healing":    {"bg": (5, 30, 15),     "accent": (80, 220, 130),  "text": (200, 255, 220)},
    "cosmic":     {"bg": (5, 5, 25),      "accent": (255, 200, 60),  "text": (255, 240, 200)},
    "sleep":      {"bg": (5, 5, 20),      "accent": (80, 80, 180),   "text": (180, 180, 240)},
    "meditation": {"bg": (10, 15, 30),    "accent": (120, 160, 220), "text": (200, 220, 255)},
    "energy":     {"bg": (30, 10, 5),     "accent": (255, 120, 40),  "text": (255, 220, 180)},
    "spiritual":  {"bg": (15, 5, 35),     "accent": (160, 80, 255),  "text": (220, 200, 255)},
    "clarity":    {"bg": (5, 15, 30),     "accent": (0, 200, 255),   "text": (200, 235, 255)},
    "focus":      {"bg": (5, 15, 30),     "accent": (0, 200, 255),   "text": (200, 235, 255)},
}
DEFAULT_PALETTE = {"bg": (5, 10, 30), "accent": (100, 180, 255), "text": (220, 235, 255)}

BEAT_BAND_LABELS = {
    "delta": "Delta Waves",
    "theta": "Theta Waves",
    "alpha": "Alpha Waves",
    "beta": "Beta Waves",
    "gamma": "Gamma Waves",
}


def _get_palette(mood: str) -> dict:
    return MOOD_PALETTES.get(mood, DEFAULT_PALETTE)


# ─── Font yardimcisi ─────────────────────────────────────────────────────────

FONT_CANDIDATES = [
    "assets/fonts/Montserrat-Bold.ttf",
    "assets/fonts/Roboto-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Metni satirlara boler."""
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


# ─── Overlay oluşturucular ───────────────────────────────────────────────────

def _make_hook_overlay(hook_line: str, hook_subtext: str, palette: dict, duration: float) -> ImageClip:
    """Hook metni overlay'i — ekranin ust-orta kisminda."""
    img = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    accent = palette["accent"]
    text_color = palette["text"]

    font_hook = _load_font(58)
    max_w = TARGET_W - 100
    lines = _wrap_text(hook_line, font_hook, max_w)

    line_h = 72
    total_h = len(lines) * line_h
    y_start = int(TARGET_H * 0.12) - total_h // 2

    # Yari saydam kutu
    pad = 20
    draw.rectangle(
        [(40, y_start - pad), (TARGET_W - 40, y_start + total_h + pad)],
        fill=(0, 0, 0, 140),
    )

    for i, line in enumerate(lines):
        y = y_start + i * line_h
        try:
            lw = draw.textlength(line, font=font_hook)
        except AttributeError:
            bbox = font_hook.getbbox(line)
            lw = bbox[2] - bbox[0]
        x = (TARGET_W - lw) // 2
        draw.text((x + 3, y + 3), line, font=font_hook, fill=(0, 0, 0, 180))
        draw.text((x, y), line, font=font_hook, fill=(*text_color, 240))

    # Accent cizgi
    line_y = y_start + total_h + pad + 8
    draw.rectangle(
        [(TARGET_W // 2 - 80, line_y), (TARGET_W // 2 + 80, line_y + 3)],
        fill=(*accent, 220),
    )

    # Alt metin
    if hook_subtext:
        font_sub = _load_font(36)
        sub_y = line_y + 16
        try:
            sw = draw.textlength(hook_subtext, font=font_sub)
        except AttributeError:
            bbox = font_sub.getbbox(hook_subtext)
            sw = bbox[2] - bbox[0]
        sx = (TARGET_W - sw) // 2
        draw.text((sx + 2, sub_y + 2), hook_subtext, font=font_sub, fill=(0, 0, 0, 160))
        draw.text((sx, sub_y), hook_subtext, font=font_sub, fill=(*accent, 230))

    arr = np.array(img)
    return ImageClip(arr, ismask=False).set_duration(duration)


def _make_binaural_overlay(
    beat_hz: float,
    beat_band: str,
    short_benefit: str,
    carrier_hz: float,
    palette: dict,
    duration: float,
) -> ImageClip:
    """
    Alt kisimda binaural beat bilgisi:
      - Buyuk: beat Hz + brainwave band adi
      - Kucuk: benefit label
      - Cok kucuk: carrier Hz bilgisi
    """
    img = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    accent = palette["accent"]
    text_color = palette["text"]

    # ─── Alt kutu ────────────────────────────────────────────────────────────
    box_h = 220
    box_y = TARGET_H - box_h - 60
    draw.rectangle([(0, box_y - 10), (TARGET_W, box_y + box_h)], fill=(0, 0, 0, 140))

    # Beat Hz (buyuk)
    hz_str = f"{beat_hz:g} Hz"
    font_hz = _load_font(90)
    try:
        hw = draw.textlength(hz_str, font=font_hz)
    except AttributeError:
        bbox = font_hz.getbbox(hz_str)
        hw = bbox[2] - bbox[0]
    hx = (TARGET_W - hw) // 2
    # Glow
    draw.text((hx + 3, box_y + 10), hz_str, font=font_hz, fill=(*accent, 50))
    draw.text((hx, box_y + 6), hz_str, font=font_hz, fill=(*text_color, 240))

    # Brainwave band adi
    band_label = BEAT_BAND_LABELS.get(beat_band, beat_band.capitalize())
    font_band = _load_font(40)
    try:
        bw = draw.textlength(band_label, font=font_band)
    except AttributeError:
        bbox = font_band.getbbox(band_label)
        bw = bbox[2] - bbox[0]
    bx = (TARGET_W - bw) // 2
    draw.text((bx, box_y + 105), band_label, font=font_band, fill=(*accent, 220))

    # Benefit
    benefit_upper = short_benefit.upper()
    font_benefit = _load_font(36)
    try:
        sw = draw.textlength(benefit_upper, font=font_benefit)
    except AttributeError:
        bbox = font_benefit.getbbox(benefit_upper)
        sw = bbox[2] - bbox[0]
    sx = (TARGET_W - sw) // 2
    draw.text((sx, box_y + 155), benefit_upper, font=font_benefit, fill=(*text_color, 200))

    # Carrier Hz (cok kucuk, sag alt)
    carrier_str = f"Carrier: {carrier_hz:g} Hz"
    font_small = _load_font(22)
    draw.text((TARGET_W - 250, box_y + box_h - 30), carrier_str, font=font_small, fill=(*text_color, 120))

    arr = np.array(img)
    return ImageClip(arr, ismask=False).set_duration(duration)


def _make_vignette(size: tuple, opacity: float = 0.4) -> ImageClip:
    """Kenarlari karartan sinematik vinyet efekti."""
    w, h = size
    x = np.linspace(-1, 1, w)
    y = np.linspace(-1, 1, h)
    X, Y = np.meshgrid(x, y)
    vignette = 1 - np.sqrt(X**2 + Y**2) / 1.414
    vignette = np.clip(vignette, 0, 1)
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 3] = ( (1 - vignette**2) * 255 * opacity ).astype(np.uint8)
    return ImageClip(arr, ismask=False)


# ─── Ana video builder ────────────────────────────────────────────────────────

def build_binaural_video(
    script: dict,
    audio_path: str,
    anim_path: str,
    output_path: str = OUTPUT_PATH,
    bg_video_path: str = None,
) -> str:
    """
    Binaural beats + math animasyon videosunu olusturur.
    Hibrit Yapi: Stok Video (Arka Plan) + Manim Animasyonu (On Plan).
    """
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    beat_hz = float(script["beat_hz"])
    beat_band = script["beat_band"]
    carrier_hz = float(script["carrier_hz"])
    short_benefit = script["short_benefit"]
    mood = script.get("mood", "calm")
    hook_line = script["hook_line"]
    hook_subtext = script.get("hook_subtext", "")

    palette = _get_palette(mood)

    # ─── Ses ──────────────────────────────────────────────────────────────────
    audio_clip = AudioFileClip(audio_path)
    total_duration = min(audio_clip.duration, 30.0)

    # ─── Katman 1: Arka Plan (Pexels Stok Video veya Siyah) ────────────────────
    if bg_video_path and os.path.exists(bg_video_path):
        print(f"[binaural_video] Stok video yukleniyor: {bg_video_path}")
        bg_clip = VideoFileClip(bg_video_path, audio=False).resize(height=TARGET_H)
        if bg_clip.w < TARGET_W:
            bg_clip = bg_clip.resize(width=TARGET_W)
        bg_clip = bg_clip.set_position("center").crop(
            x1=(bg_clip.w - TARGET_W) // 2,
            y1=(bg_clip.h - TARGET_H) // 2,
            x2=(bg_clip.w + TARGET_W) // 2,
            y2=(bg_clip.h + TARGET_H) // 2,
        )
    else:
        print("[binaural_video] Arka plan: Siyah (Stok video bulunamadi)")
        bg_clip = ColorClip(size=(TARGET_W, TARGET_H), color=(0, 0, 0))
    
    bg_clip = bg_clip.set_duration(total_duration)

    # ─── Katman 2: Manim Animasyonu (On Plan - Parlayan Cizgiler) ─────────────
    print("[binaural_video] Manim animasyonu yukleniyor...")
    anim_clip = VideoFileClip(anim_path, audio=False).resize(height=TARGET_H)
    anim_clip = anim_clip.set_opacity(0.85).set_duration(total_duration)
    if anim_clip.w != TARGET_W:
        anim_clip = anim_clip.crop(x_center=anim_clip.w/2, width=TARGET_W)

    # ─── Katman 3: Sinematik Efektler ──────────────────────────────────────────
    vignette = _make_vignette((TARGET_W, TARGET_H), opacity=0.5).set_duration(total_duration)
    darken = ColorClip(size=(TARGET_W, TARGET_H), color=[0, 0, 0]).set_opacity(0.15).set_duration(total_duration)

    # ─── Overlay katmanlari ───────────────────────────────────────────────────
    print("[binaural_video] Overlayler hazirlaniyor...")
    hook_overlay = _make_hook_overlay(hook_line, hook_subtext, palette, total_duration)
    binaural_overlay = _make_binaural_overlay(
        beat_hz, beat_band, short_benefit, carrier_hz, palette, total_duration
    )

    # ─── Birlestir ────────────────────────────────────────────────────────────
    print("[binaural_video] Katmanlar birlestiriliyor (Cinematic Hybrid)...")
    final_video = CompositeVideoClip(
        [bg_clip, anim_clip, vignette, darken, hook_overlay, binaural_overlay],
        size=(TARGET_W, TARGET_H),
    ).set_duration(total_duration)
    
    final_video = final_video.set_audio(audio_clip.subclip(0, total_duration))

    # ─── Export ───────────────────────────────────────────────────────────────
    print(f"[binaural_video] Export ediliyor: {output_path}")
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

    audio_clip.close()
    anim_clip.close()
    bg_clip.close()
    final_video.close()

    print(f"[binaural_video] Video tamamlandi: {output_path}")
    return output_path
