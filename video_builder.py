"""
video_builder.py — Pexels'ten footage indirir, MoviePy ile 1080×1920 Short üretir.
Özellikler:
  - Çoklu klip montajı (3-5 farklı klip) + crossfade geçiş
  - Ken Burns zoom efekti
  - Numpy renk düzenleme (sinematik savaş tonu)
  - VTT tabanlı kesin zamanlı altyazı
  - Hook overlay (ilk 3 sn, sarı metin)
  - CTA bitiş ekranı (son 3 sn, "FOLLOW FOR MORE WHAT-IFS!")
  - Logo/watermark (sağ üst köşe, assets/logo.png)
  - Kırmızı ilerleme çubuğu (alt kısım, dinamik)
  - Arka plan müziği %20 ses
"""

import os
import json
import requests
import tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Pillow 10+ uyumluluğu: ANTIALIAS kaldırıldı, LANCZOS kullanılmalı
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
from moviepy.video.VideoClip import VideoClip

TARGET_W = 1080
TARGET_H = 1920
PEXELS_API = "https://api.pexels.com/videos/search"
MUSIC_PATH = "assets/music/epic_background.wav"
FONT_PATH = "assets/fonts/Montserrat-Bold.ttf"
LOGO_PATH = "assets/logo.png"
INTRO_PATH = "assets/intro.mp4"     # 2 saniyelik branded intro (opsiyonel)
OUTRO_PATH = "assets/outro.mp4"     # 3 saniyelik branded outro (opsiyonel)
CROSSFADE_DUR = 0.4   # saniye, klip geçiş süresi
CTA_DURATION = 3.0    # son kaç saniye CTA ekranı

# Ses efekti dosyaları (assets/sfx/ altında, yoksa atlanır)
SFX = {
    "hook":      "assets/sfx/drum_hit.wav",      # 0. sn — hook başlangıcı
    "twist":     "assets/sfx/sword_clash.wav",   # ~15. sn — twist bölümü
    "payoff":    "assets/sfx/explosion.wav",     # ~40. sn — payoff
    "cta":       "assets/sfx/trumpet.wav",       # CTA öncesi
}


# ─── Font yardımcısı ─────────────────────────────────────────────────────────

def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in [
        FONT_PATH,
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


# ─── Pexels: çoklu klip ──────────────────────────────────────────────────────

def _download_clip(url: str) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    for chunk in r.iter_content(chunk_size=8192):
        tmp.write(chunk)
    tmp.close()
    return tmp.name


def _best_file_url(video: dict) -> str:
    for q in ("hd", "sd"):
        for vf in video.get("video_files", []):
            if vf.get("quality") == q:
                return vf["link"]
    return video["video_files"][0]["link"]


def _fetch_multiple_clips(keywords: list, api_key: str, n: int = 8) -> list:
    """
    Farklı arama kombinasyonlarıyla Pexels'ten n adet video indirir.
    Her biri için ayrı geçici dosya yolu döndürür.
    """
    headers = {"Authorization": api_key}
    downloaded = []

    # Script'in search_keywords'lerinden dinamik sorgular oluştur
    queries = []

    # Keyword kombinasyonları (en alakalı)
    if len(keywords) >= 2:
        queries.append(" ".join(keywords[:2]))
    if len(keywords) >= 3:
        queries.append(" ".join(keywords[1:3]))

    # Her keyword tek başına
    for kw in keywords:
        queries.append(kw)

    # Keyword'lere dayalı varyasyonlar
    for kw in keywords[:2]:
        queries.append(f"{kw} cinematic")

    # Fallback (yeterli klip bulunamazsa)
    queries.extend([
        "military dramatic cinematic",
        "dramatic aerial landscape",
    ])

    for query in queries:
        if len(downloaded) >= n:
            break
        params = {"query": query, "per_page": 3, "orientation": "portrait", "size": "medium"}
        try:
            resp = requests.get(PEXELS_API, headers=headers, params=params, timeout=20)
            resp.raise_for_status()
            videos = resp.json().get("videos", [])
            for v in videos:
                if len(downloaded) >= n:
                    break
                url = _best_file_url(v)
                print(f"[video_builder] Klip {len(downloaded)+1}/{n} indiriliyor...")
                downloaded.append(_download_clip(url))
        except Exception as e:
            print(f"[video_builder] Klip indirme hatası ({query}): {e}")

    if not downloaded:
        raise RuntimeError("Hiç Pexels klibi indirilemedi.")

    return downloaded


# ─── Resize / crop ───────────────────────────────────────────────────────────

def _resize_to_shorts(clip: VideoFileClip) -> VideoFileClip:
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

def _apply_ken_burns(clip: VideoFileClip, zoom_ratio: float = 0.03) -> VideoFileClip:
    dur = clip.duration

    def zoom(get_frame, t):
        frame = get_frame(t)
        scale = 1 + zoom_ratio * (t / max(dur, 0.01))
        h, w = frame.shape[:2]
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = Image.fromarray(frame).resize((new_w, new_h), Image.LANCZOS)
        x = (new_w - w) // 2
        y = (new_h - h) // 2
        img = img.crop((x, y, x + w, y + h))
        return np.array(img)

    return clip.fl(zoom, apply_to="video")


# ─── Renk düzenleme ──────────────────────────────────────────────────────────

def _color_grade(clip: VideoFileClip) -> VideoFileClip:
    def grade(frame):
        f = frame.astype(np.float32)
        grey = f.mean(axis=2, keepdims=True)
        f = f * 0.70 + grey * 0.30            # desaturasyon
        f = (f - 128) * 1.15 + 128            # kontrast
        f[:, :, 0] = np.clip(f[:, :, 0] - 5, 0, 255)   # R -5
        f[:, :, 2] = np.clip(f[:, :, 2] + 8, 0, 255)   # B +8
        return np.clip(f, 0, 255).astype(np.uint8)

    return clip.fl_image(grade)


# ─── Çoklu klip montajı ──────────────────────────────────────────────────────

def _build_background(clip_paths: list, total_duration: float) -> VideoFileClip:
    """
    İndirilen klipleri işler ve crossfade ile birleştirir.
    total_duration kadar uzayan tek bir arka plan klibi döndürür.
    """
    processed = []
    per_clip = total_duration / len(clip_paths)

    for path in clip_paths:
        c = VideoFileClip(path, audio=False)
        c = _resize_to_shorts(c)
        c = _color_grade(c)
        c = _apply_ken_burns(c)
        # Her klip per_clip kadar sürsün
        if c.duration < per_clip:
            repeats = int(per_clip / c.duration) + 1
            c = concatenate_videoclips([c] * repeats)
        c = c.subclip(0, per_clip)
        processed.append(c)

    if len(processed) == 1:
        return processed[0]

    # crossfade geçiş
    clips_with_fade = [processed[0].crossfadeout(CROSSFADE_DUR)]
    for i, c in enumerate(processed[1:], 1):
        c = c.crossfadein(CROSSFADE_DUR)
        if i < len(processed) - 1:
            c = c.crossfadeout(CROSSFADE_DUR)
        clips_with_fade.append(c)

    bg = concatenate_videoclips(clips_with_fade, method="compose", padding=-CROSSFADE_DUR)

    # Tam uzunluğa getir
    if bg.duration < total_duration:
        bg = concatenate_videoclips([bg, bg]).subclip(0, total_duration)
    else:
        bg = bg.subclip(0, total_duration)

    return bg


# ─── Altyazı ─────────────────────────────────────────────────────────────────

def _render_subtitle_image(text: str) -> np.ndarray:
    font = _load_font(46)
    dummy = Image.new("RGBA", (1, 1))
    dd = ImageDraw.Draw(dummy)
    bbox = dd.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0] + 40
    text_h = bbox[3] - bbox[1] + 24

    img = Image.new("RGBA", (text_w, text_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (text_w, text_h)], fill=(0, 0, 0, 160))
    for dx, dy in [(-2, -2), (2, 2), (-2, 2), (2, -2)]:
        draw.text((20 + dx, 12 + dy), text, font=font, fill=(0, 0, 0, 255))
    draw.text((20, 12), text, font=font, fill=(255, 255, 255, 255))
    return np.array(img)


def _make_subtitle_clips(chunks: list, total_duration: float) -> list:
    clips = []
    for chunk in chunks:
        start = chunk["start"]
        end = min(chunk["end"], total_duration - CTA_DURATION - 0.1)
        dur = end - start
        if dur <= 0:
            continue
        img_arr = _render_subtitle_image(chunk["text"])
        h, w = img_arr.shape[:2]
        clips.append(
            ImageClip(img_arr, ismask=False)
            .set_duration(dur)
            .set_start(start)
            .set_position(((TARGET_W - w) // 2, TARGET_H - h - 140))
        )
    return clips


def _make_fallback_subtitle_clips(narration: str, audio_duration: float) -> list:
    words = narration.split()
    secs_per_word = audio_duration / max(len(words), 1)
    n = 5
    chunks = []
    for i in range(0, len(words), n):
        group = words[i:i + n]
        chunks.append({
            "start": i * secs_per_word,
            "end": min((i + n) * secs_per_word, audio_duration),
            "text": " ".join(group),
        })
    return _make_subtitle_clips(chunks, audio_duration)


# ─── Hook overlay ────────────────────────────────────────────────────────────

def _make_hook_clip(hook_text: str, duration: float = 3.0) -> ImageClip:
    font = _load_font(64)
    max_w = TARGET_W - 80
    words = hook_text.split()
    lines, current = [], []
    dummy = Image.new("RGBA", (1, 1))
    dd = ImageDraw.Draw(dummy)

    for word in words:
        test = " ".join(current + [word])
        if dd.textbbox((0, 0), test, font=font)[2] > max_w and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))

    line_h = 76
    h = line_h * len(lines) + 30
    img = Image.new("RGBA", (TARGET_W, h + 20), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (TARGET_W, h + 20)], fill=(0, 0, 0, 180))

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        x = (TARGET_W - lw) // 2
        y = 15 + i * line_h
        for dx, dy in [(-3, -3), (3, 3), (-3, 3), (3, -3)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 255))
        draw.text((x, y), line, font=font, fill=(255, 220, 0, 255))

    return (
        ImageClip(np.array(img))
        .set_duration(duration)
        .set_start(0)
        .set_position(("center", 160))
        .crossfadeout(0.5)
    )


# ─── CTA bitiş ekranı ────────────────────────────────────────────────────────

def _make_cta_clip(total_duration: float, duration: float = CTA_DURATION) -> list:
    """
    Son {duration} saniye için tam ekran CTA overlay.
    'FOLLOW FOR MORE WHAT-IFS!' + kırmızı accent çubuğu.
    """
    start = total_duration - duration

    # Yarı saydam siyah arka plan
    bg = (
        ColorClip(size=(TARGET_W, TARGET_H), color=(0, 0, 0))
        .set_opacity(0.75)
        .set_duration(duration)
        .set_start(start)
        .crossfadein(0.4)
    )

    # Kırmızı yatay çubuk
    bar = (
        ColorClip(size=(TARGET_W, 8), color=(200, 30, 30))
        .set_duration(duration)
        .set_start(start)
        .set_position(("center", TARGET_H // 2 - 100))
    )

    # Ana CTA metni
    font_big = _load_font(80)
    font_sub = _load_font(44)

    def _text_img(text: str, font: ImageFont.FreeTypeFont, color, outline=(0, 0, 0)) -> np.ndarray:
        dummy = Image.new("RGBA", (1, 1))
        dd = ImageDraw.Draw(dummy)
        bbox = dd.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0] + 20
        h = bbox[3] - bbox[1] + 20
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        for dx, dy in [(-3, -3), (3, 3), (-3, 3), (3, -3), (0, -3), (0, 3), (-3, 0), (3, 0)]:
            draw.text((10 + dx, 10 + dy), text, font=font, fill=(*outline, 255))
        draw.text((10, 10), text, font=font, fill=(*color, 255))
        return np.array(img)

    # "FOLLOW" - büyük sarı
    follow_arr = _text_img("FOLLOW", font_big, (255, 220, 0))
    fh, fw = follow_arr.shape[:2]
    follow_clip = (
        ImageClip(follow_arr)
        .set_duration(duration)
        .set_start(start)
        .set_position(((TARGET_W - fw) // 2, TARGET_H // 2 - 80))
        .crossfadein(0.4)
    )

    # "FOR MORE WHAT-IFS!" - beyaz
    sub_arr = _text_img("FOR MORE WHAT-IFS!", font_sub, (255, 255, 255))
    sh, sw = sub_arr.shape[:2]
    sub_clip = (
        ImageClip(sub_arr)
        .set_duration(duration)
        .set_start(start)
        .set_position(((TARGET_W - sw) // 2, TARGET_H // 2 + 20))
        .crossfadein(0.5)
    )

    # "👆" ok işareti metni
    arrow_arr = _text_img("TAP FOLLOW  ^", font_sub, (200, 30, 30))
    ah, aw = arrow_arr.shape[:2]
    arrow_clip = (
        ImageClip(arrow_arr)
        .set_duration(duration)
        .set_start(start)
        .set_position(((TARGET_W - aw) // 2, TARGET_H // 2 + 90))
        .crossfadein(0.6)
    )

    return [bg, bar, follow_clip, sub_clip, arrow_clip]


# ─── Progress bar ────────────────────────────────────────────────────────────

def _make_progress_bar(total_duration: float, bar_h: int = 8) -> VideoClip:
    """
    Alt kısımda video boyunca büyüyen kırmızı ilerleme çubuğu.
    Her frame'de mevcut zamana göre genişliği hesaplanır.
    """
    def make_frame(t):
        w = int(TARGET_W * min(t / total_duration, 1.0))
        frame = np.zeros((bar_h, TARGET_W, 3), dtype=np.uint8)
        if w > 0:
            frame[:, :w] = [200, 30, 30]   # kırmızı
        return frame

    return (
        VideoClip(make_frame, duration=total_duration)
        .set_position(("center", TARGET_H - bar_h - 2))
    )


# ─── Logo / watermark ────────────────────────────────────────────────────────

def _make_watermark_clip(total_duration: float) -> ImageClip | None:
    """
    assets/logo.png varsa sağ üst köşeye yarı saydam watermark ekler.
    Yoksa None döndürür (opsiyonel özellik).
    """
    if not os.path.exists(LOGO_PATH):
        return None

    logo = Image.open(LOGO_PATH).convert("RGBA")

    # Max 120px genişlik
    max_size = 120
    w, h = logo.size
    if w > max_size:
        ratio = max_size / w
        logo = logo.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    # %60 saydamlık
    r, g, b, a = logo.split()
    a = a.point(lambda x: int(x * 0.6))
    logo.putalpha(a)

    arr = np.array(logo)
    lh, lw = arr.shape[:2]
    x = TARGET_W - lw - 24
    y = 24

    return (
        ImageClip(arr)
        .set_duration(total_duration)
        .set_start(0)
        .set_position((x, y))
    )


# ─── Ses efektleri ───────────────────────────────────────────────────────────

def _build_sfx_audio(audio_duration: float) -> list:
    """
    Script bölüm zamanlamalarına göre sfx klipleri oluşturur.
    Döndürür: AudioFileClip listesi (start zamanı ayarlı, 30% volume).
    Dosya yoksa sessizce atlanır.
    """
    # Sabit zamanlama: script yapısına göre (saniye)
    timings = {
        "hook":   0.1,
        "twist":  15.0,
        "payoff": 40.0,
        "cta":    max(0, audio_duration - 0.5),
    }

    sfx_clips = []
    for key, t in timings.items():
        path = SFX.get(key, "")
        if not path or not os.path.exists(path):
            continue
        try:
            sfx = AudioFileClip(path).volumex(0.35).set_start(t)
            # Sfx audio_duration'ı aşmasın
            if t + sfx.duration > audio_duration + CTA_DURATION:
                sfx = sfx.subclip(0, audio_duration + CTA_DURATION - t)
            sfx_clips.append(sfx)
            print(f"[video_builder] SFX eklendi: {key} @ {t:.1f}s")
        except Exception as e:
            print(f"[video_builder] SFX yüklenemedi ({key}): {e}")

    return sfx_clips


# ─── Ana fonksiyon ───────────────────────────────────────────────────────────

def build_video(
    script: dict,
    audio_path: str,
    vtt_path: str = None,
    output_path: str = "output/short.mp4",
) -> str:
    """
    Script, ses ve (isteğe bağlı) VTT dosyasından 1080×1920 Short üretir.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pexels_key = os.environ["PEXELS_API_KEY"]

    # 1) Çoklu klip indir
    clip_paths = _fetch_multiple_clips(script["search_keywords"], pexels_key, n=8)

    # 2) Ses süresi
    narration_audio = AudioFileClip(audio_path)
    total_duration = narration_audio.duration + CTA_DURATION + 0.3

    # 3) Arka plan: çoklu klip + crossfade
    bg = _build_background(clip_paths, total_duration)

    # 4) Overlay katmanları
    layers = [bg]

    # Hook (ilk 3 sn)
    layers.append(_make_hook_clip(script["hook"], duration=min(3.0, total_duration)))

    # Altyazılar (CTA süresi hariç)
    if vtt_path and os.path.exists(vtt_path):
        from tts import parse_vtt
        chunks = parse_vtt(vtt_path)
        layers.extend(_make_subtitle_clips(chunks, total_duration))
        print(f"[video_builder] VTT: {len(chunks)} altyazı chunk'ı")
    else:
        layers.extend(_make_fallback_subtitle_clips(script["narration"], narration_audio.duration))

    # CTA bitiş ekranı (son 3 sn)
    layers.extend(_make_cta_clip(total_duration))

    # Logo/watermark (opsiyonel)
    wm = _make_watermark_clip(total_duration)
    if wm:
        layers.append(wm)
        print("[video_builder] Watermark eklendi.")

    # İlerleme çubuğu
    layers.append(_make_progress_bar(total_duration))

    # 5) Kompozit
    final_video = CompositeVideoClip(layers, size=(TARGET_W, TARGET_H))
    final_video = final_video.set_duration(total_duration)

    # 6) Ses: TTS + müzik + sfx
    audio_tracks = [narration_audio]
    if os.path.exists(MUSIC_PATH):
        music = AudioFileClip(MUSIC_PATH).volumex(0.2)
        if music.duration < total_duration:
            from moviepy.audio.fx.audio_loop import audio_loop
            music = audio_loop(music, nloops=int(total_duration / music.duration) + 1)
        music = music.subclip(0, total_duration)
        audio_tracks.append(music)

    sfx_clips = _build_sfx_audio(narration_audio.duration)
    audio_tracks.extend(sfx_clips)

    final_video = final_video.set_audio(CompositeAudioClip(audio_tracks))

    # 7) Branded intro / outro ekle
    segments = []

    if os.path.exists(INTRO_PATH):
        try:
            intro = VideoFileClip(INTRO_PATH, audio=True)
            intro = _resize_to_shorts(intro)
            segments.append(intro.crossfadeout(0.3))
            print(f"[video_builder] Intro eklendi ({intro.duration:.1f}s)")
        except Exception as e:
            print(f"[video_builder] Intro yüklenemedi: {e}")

    final_video_faded = final_video.crossfadein(0.3) if segments else final_video
    segments.append(final_video_faded)

    if os.path.exists(OUTRO_PATH):
        try:
            outro = VideoFileClip(OUTRO_PATH, audio=True)
            outro = _resize_to_shorts(outro)
            segments.append(outro.crossfadein(0.3))
            print(f"[video_builder] Outro eklendi ({outro.duration:.1f}s)")
        except Exception as e:
            print(f"[video_builder] Outro yüklenemedi: {e}")

    if len(segments) > 1:
        final_video = concatenate_videoclips(
            segments, method="compose", padding=-0.3
        )

    # 8) Export
    print(f"[video_builder] Render ediliyor → {output_path}")
    final_video.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile=os.path.join(os.path.dirname(output_path), "temp_audio.m4a"),
        remove_temp=True,
        threads=2,
        preset="fast",
        verbose=False,
        logger=None,
    )

    # Cleanup
    narration_audio.close()
    for path in clip_paths:
        try:
            os.unlink(path)
        except OSError:
            pass

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
