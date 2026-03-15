"""
video_builder.py — Pexels'ten footage indirir, MoviePy ile 1080×1920 Short üretir.
Gelişmiş özellikler:
  - Ken Burns zoom efekti
  - Numpy renk düzenleme (sinematik savaş tonu)
  - VTT tabanlı kesin zamanlı altyazı
  - Hook overlay (ilk 3 sn)
  - Arka plan müziği %20 ses
"""

import os
import json
import requests
import tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    CompositeVideoClip,
    CompositeAudioClip,
    ImageClip,
    concatenate_videoclips,
)

TARGET_W = 1080
TARGET_H = 1920
PEXELS_API = "https://api.pexels.com/videos/search"
MUSIC_PATH = "assets/music/epic_background.mp3"
FONT_PATH = "assets/fonts/Montserrat-Bold.ttf"
FONT = FONT_PATH if os.path.exists(FONT_PATH) else "Impact"


# ─── Pexels ──────────────────────────────────────────────────────────────────

def _fetch_pexels_video(keywords: list, api_key: str) -> str:
    """Pexels'ten uygun portrait video indirir, geçici dosya yolunu döndürür."""
    headers = {"Authorization": api_key}

    for query in [" ".join(keywords[:3]), "war battle ancient history"]:
        params = {"query": query, "per_page": 5, "orientation": "portrait", "size": "medium"}
        resp = requests.get(PEXELS_API, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
        if videos:
            break

    if not videos:
        raise RuntimeError("Pexels'te uygun video bulunamadı.")

    best_file = None
    for video in videos:
        for vf in video.get("video_files", []):
            if vf.get("quality") in ("hd", "sd"):
                best_file = vf["link"]
                break
        if best_file:
            break

    if not best_file:
        best_file = videos[0]["video_files"][0]["link"]

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    print(f"[video_builder] Footage indiriliyor...")
    r = requests.get(best_file, stream=True, timeout=60)
    r.raise_for_status()
    for chunk in r.iter_content(chunk_size=8192):
        tmp.write(chunk)
    tmp.close()
    return tmp.name


# ─── Resize / crop ───────────────────────────────────────────────────────────

def _resize_to_shorts(clip: VideoFileClip) -> VideoFileClip:
    """Clip'i 1080×1920 dikey formata crop/resize eder."""
    w, h = clip.size
    target_ratio = TARGET_W / TARGET_H
    current_ratio = w / h

    if current_ratio > target_ratio:
        clip = clip.resize(height=TARGET_H)
        clip = clip.crop(x_center=clip.w // 2, width=TARGET_W, height=TARGET_H)
    else:
        clip = clip.resize(width=TARGET_W)
        clip = clip.crop(y_center=clip.h // 2, width=TARGET_W, height=TARGET_H)

    return clip


# ─── Ken Burns zoom ──────────────────────────────────────────────────────────

def _apply_ken_burns(clip: VideoFileClip, zoom_ratio: float = 0.04) -> VideoFileClip:
    """
    Klibe hafif yakınlaşma (zoom-in) efekti uygular.
    zoom_ratio=0.04 → süre boyunca %4 büyür.
    """
    dur = clip.duration

    def zoom(get_frame, t):
        frame = get_frame(t)
        scale = 1 + zoom_ratio * (t / dur)
        h, w = frame.shape[:2]
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = Image.fromarray(frame).resize((new_w, new_h), Image.LANCZOS)
        # Merkezi kes
        x = (new_w - w) // 2
        y = (new_h - h) // 2
        img = img.crop((x, y, x + w, y + h))
        return np.array(img)

    return clip.fl(zoom, apply_to="video")


# ─── Renk düzenleme ──────────────────────────────────────────────────────────

def _color_grade(clip: VideoFileClip) -> VideoFileClip:
    """
    Sinematik savaş tonu: hafif desaturasyon + kontrast artışı + hafif soğuk renk.
    Tamamen numpy ile, ek kütüphane yok.
    """
    def grade(frame):
        f = frame.astype(np.float32)
        # Desaturasyon: %30 gri karıştır
        grey = f.mean(axis=2, keepdims=True)
        f = f * 0.70 + grey * 0.30
        # Kontrast: factor > 1 = daha fazla kontrast
        f = (f - 128) * 1.15 + 128
        # Hafif soğuk ton: mavi kanalı +8, kırmızıyı -5
        f[:, :, 0] = np.clip(f[:, :, 0] - 5, 0, 255)   # R
        f[:, :, 2] = np.clip(f[:, :, 2] + 8, 0, 255)   # B
        return np.clip(f, 0, 255).astype(np.uint8)

    return clip.fl_image(grade)


# ─── Altyazı (VTT tabanlı) ───────────────────────────────────────────────────

def _render_subtitle_image(text: str) -> np.ndarray:
    """Bir altyazı satırını Pillow ile render eder, numpy array döndürür."""
    font_size = 46
    try:
        if os.path.exists(FONT_PATH):
            font = ImageFont.truetype(FONT_PATH, font_size)
        else:
            font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    # Metin boyutunu ölç
    dummy = Image.new("RGBA", (1, 1))
    dd = ImageDraw.Draw(dummy)
    bbox = dd.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0] + 40
    text_h = bbox[3] - bbox[1] + 24

    img = Image.new("RGBA", (text_w, text_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Yarı şeffaf siyah arka plan
    draw.rectangle([(0, 0), (text_w, text_h)], fill=(0, 0, 0, 160))

    # Gölge
    for dx, dy in [(-2, -2), (2, 2), (-2, 2), (2, -2)]:
        draw.text((20 + dx, 12 + dy), text, font=font, fill=(0, 0, 0, 255))

    # Beyaz metin
    draw.text((20, 12), text, font=font, fill=(255, 255, 255, 255))

    return np.array(img)


def _make_subtitle_clips(vtt_chunks: list, total_duration: float) -> list:
    """VTT chunk listesinden MoviePy ImageClip listesi üretir."""
    clips = []
    for chunk in vtt_chunks:
        start = chunk["start"]
        end = min(chunk["end"], total_duration - 0.1)
        dur = end - start
        if dur <= 0:
            continue

        img_arr = _render_subtitle_image(chunk["text"])
        h, w = img_arr.shape[:2]
        x = (TARGET_W - w) // 2
        y = TARGET_H - h - 140  # Alt kısım, UI'dan uzak

        clip = (
            ImageClip(img_arr, ismask=False)
            .set_duration(dur)
            .set_start(start)
            .set_position((x, y))
        )
        clips.append(clip)

    return clips


def _make_fallback_subtitle_clips(narration: str, audio_duration: float) -> list:
    """VTT yoksa eşit aralıklı altyazı üretir (fallback)."""
    words = narration.split()
    words_per_chunk = 5
    secs_per_word = audio_duration / max(len(words), 1)

    chunks = []
    for i in range(0, len(words), words_per_chunk):
        group = words[i:i + words_per_chunk]
        start = i * secs_per_word
        end = min((i + words_per_chunk) * secs_per_word, audio_duration)
        chunks.append({"start": start, "end": end, "text": " ".join(group)})

    return _make_subtitle_clips(chunks, audio_duration)


# ─── Hook overlay ────────────────────────────────────────────────────────────

def _make_hook_clip(hook_text: str, duration: float = 3.0) -> ImageClip:
    """İlk 3 saniye için büyük hook metni içeren overlay ImageClip."""
    font_size = 64
    try:
        if os.path.exists(FONT_PATH):
            font = ImageFont.truetype(FONT_PATH, font_size)
        else:
            font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    # Metni TARGET_W - 80 genişliğe sığdır
    max_w = TARGET_W - 80
    words = hook_text.split()
    lines = []
    current = []
    dummy = Image.new("RGBA", (1, 1))
    dd = ImageDraw.Draw(dummy)

    for word in words:
        test = " ".join(current + [word])
        w = dd.textbbox((0, 0), test, font=font)[2]
        if w > max_w and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))

    line_h = font_size + 12
    total_text_h = line_h * len(lines) + 30
    img = Image.new("RGBA", (TARGET_W, total_text_h + 20), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (TARGET_W, total_text_h + 20)], fill=(0, 0, 0, 180))

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        x = (TARGET_W - lw) // 2
        y = 15 + i * line_h
        # Gölge
        for dx, dy in [(-3, -3), (3, 3), (-3, 3), (3, -3)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 255))
        # Sarı metin — dikkat çeker
        draw.text((x, y), line, font=font, fill=(255, 220, 0, 255))

    img_arr = np.array(img)
    y_pos = 160

    return (
        ImageClip(img_arr)
        .set_duration(duration)
        .set_start(0)
        .set_position(("center", y_pos))
        .crossfadeout(0.5)
    )


# ─── Ana fonksiyon ───────────────────────────────────────────────────────────

def build_video(
    script: dict,
    audio_path: str,
    vtt_path: str = None,
    output_path: str = "output/short.mp4",
) -> str:
    """
    Script, ses ve (isteğe bağlı) VTT dosyasından 1080×1920 Short videosu üretir.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pexels_key = os.environ["PEXELS_API_KEY"]

    # 1) Footage
    footage_path = _fetch_pexels_video(script["search_keywords"], pexels_key)

    # 2) Ses süresi
    narration_audio = AudioFileClip(audio_path)
    total_duration = narration_audio.duration + 0.5

    # 3) Arka plan videosu hazırla
    raw_clip = VideoFileClip(footage_path, audio=False)

    if raw_clip.duration < total_duration:
        repeats = int(total_duration / raw_clip.duration) + 1
        raw_clip = concatenate_videoclips([raw_clip] * repeats)

    bg = raw_clip.subclip(0, total_duration)
    bg = _resize_to_shorts(bg)
    bg = _color_grade(bg)
    bg = _apply_ken_burns(bg, zoom_ratio=0.03)

    # 4) Overlay katmanları
    layers = [bg]

    # Hook (ilk 3 sn)
    layers.append(_make_hook_clip(script["hook"], duration=min(3.0, total_duration)))

    # Altyazılar
    if vtt_path and os.path.exists(vtt_path):
        from tts import parse_vtt
        chunks = parse_vtt(vtt_path)
        layers.extend(_make_subtitle_clips(chunks, total_duration))
        print(f"[video_builder] VTT tabanlı {len(chunks)} altyazı chunk'ı kullanıldı.")
    else:
        layers.extend(_make_fallback_subtitle_clips(script["narration"], narration_audio.duration))

    # 5) Kompozit
    final_video = CompositeVideoClip(layers, size=(TARGET_W, TARGET_H))
    final_video = final_video.set_duration(total_duration)

    # 6) Ses
    audio_tracks = [narration_audio]
    if os.path.exists(MUSIC_PATH):
        music = AudioFileClip(MUSIC_PATH).volumex(0.2)
        if music.duration < total_duration:
            from moviepy.audio.fx.audio_loop import audio_loop
            music = audio_loop(music, nloops=int(total_duration / music.duration) + 1)
        music = music.subclip(0, total_duration)
        audio_tracks.append(music)

    final_video = final_video.set_audio(CompositeAudioClip(audio_tracks))

    # 7) Export
    print(f"[video_builder] Render ediliyor → {output_path}")
    final_video.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile="output/temp_audio.m4a",
        remove_temp=True,
        threads=2,
        preset="fast",
        verbose=False,
        logger=None,
    )

    # Cleanup
    raw_clip.close()
    narration_audio.close()
    os.unlink(footage_path)

    print(f"[video_builder] Video hazır: {output_path}")
    return output_path


if __name__ == "__main__":
    import sys

    script_path = sys.argv[1] if len(sys.argv) > 1 else "output/script.json"
    audio_path = sys.argv[2] if len(sys.argv) > 2 else "output/narration.mp3"
    vtt_path = sys.argv[3] if len(sys.argv) > 3 else "output/narration.vtt"

    with open(script_path, encoding="utf-8") as f:
        script = json.load(f)

    build_video(script, audio_path, vtt_path if os.path.exists(vtt_path) else None)
