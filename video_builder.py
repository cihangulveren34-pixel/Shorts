"""
video_builder.py — Pexels'ten footage indirir, MoviePy ile 1080×1920 Short üretir.
Altyazı overlay, hook metni ve arka plan müziği içerir.
"""

import os
import json
import requests
import tempfile
from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    CompositeVideoClip,
    CompositeAudioClip,
    TextClip,
    ColorClip,
    concatenate_videoclips,
)

TARGET_W = 1080
TARGET_H = 1920
PEXELS_API = "https://api.pexels.com/videos/search"
MUSIC_PATH = "assets/music/epic_background.mp3"
FONT_PATH = "assets/fonts/Montserrat-Bold.ttf"
FONT = FONT_PATH if os.path.exists(FONT_PATH) else "Impact"


def _fetch_pexels_video(keywords: list, api_key: str) -> str:
    """Pexels'ten uygun bir video indirir, geçici dosya yolunu döndürür."""
    query = " ".join(keywords[:3])
    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": 5, "orientation": "portrait", "size": "medium"}

    resp = requests.get(PEXELS_API, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    videos = data.get("videos", [])
    if not videos:
        # Fallback: genel savaş videosu ara
        params["query"] = "war battle ancient"
        resp = requests.get(PEXELS_API, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        videos = data.get("videos", [])

    if not videos:
        raise RuntimeError("Pexels'te uygun video bulunamadı.")

    # En uzun portrait video dosyasını seç
    best_file = None
    for video in videos:
        for vf in video.get("video_files", []):
            if vf.get("quality") in ("hd", "sd") and vf.get("height", 0) >= vf.get("width", 1):
                best_file = vf["link"]
                break
        if best_file:
            break

    if not best_file:
        best_file = videos[0]["video_files"][0]["link"]

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    print(f"[video_builder] Footage indiriliyor: {best_file[:60]}...")
    r = requests.get(best_file, stream=True, timeout=60)
    r.raise_for_status()
    for chunk in r.iter_content(chunk_size=8192):
        tmp.write(chunk)
    tmp.close()
    return tmp.name


def _resize_to_shorts(clip: VideoFileClip) -> VideoFileClip:
    """Clip'i 1080×1920 dikey formata crop/resize eder."""
    w, h = clip.size
    target_ratio = TARGET_W / TARGET_H
    current_ratio = w / h

    if current_ratio > target_ratio:
        # Daha geniş → yüksekliğe göre ölçekle, kenarları kes
        new_h = TARGET_H
        new_w = int(new_h * current_ratio)
        clip = clip.resize(height=new_h)
        x_center = clip.w // 2
        clip = clip.crop(x_center=x_center, width=TARGET_W, height=TARGET_H)
    else:
        # Daha uzun → genişliğe göre ölçekle
        new_w = TARGET_W
        new_h = int(new_w / current_ratio)
        clip = clip.resize(width=new_w)
        y_center = clip.h // 2
        clip = clip.crop(y_center=y_center, width=TARGET_W, height=TARGET_H)

    return clip


def _make_hook_overlay(hook_text: str, duration: float) -> CompositeVideoClip:
    """İlk 3 saniye için büyük hook metni overlay oluşturur."""
    # Yarı şeffaf siyah arka plan
    bg = ColorClip(size=(TARGET_W, 200), color=(0, 0, 0)).set_opacity(0.6)
    bg = bg.set_duration(duration).set_position(("center", 120))

    txt = TextClip(
        hook_text,
        fontsize=58,
        font=FONT,
        color="white",
        stroke_color="black",
        stroke_width=2,
        method="caption",
        size=(TARGET_W - 80, None),
        align="center",
    )
    txt = txt.set_duration(duration).set_position(("center", 130))

    return [bg, txt]


def _make_subtitle_clips(narration: str, audio_duration: float) -> list:
    """Altyazı satırlarını video boyunca yayar."""
    words = narration.split()
    # Yaklaşık: her kelime ~0.35 saniye
    words_per_line = 6
    secs_per_word = audio_duration / max(len(words), 1)

    clips = []
    for i in range(0, len(words), words_per_line):
        line_words = words[i:i + words_per_line]
        line = " ".join(line_words)
        start = i * secs_per_word
        end = min((i + words_per_line) * secs_per_word, audio_duration)
        dur = end - start

        if dur <= 0:
            continue

        # Siyah arka plan şeridi
        bg = ColorClip(size=(TARGET_W, 90), color=(0, 0, 0)).set_opacity(0.7)
        bg = bg.set_duration(dur).set_start(start).set_position(("center", TARGET_H - 180))

        txt = TextClip(
            line,
            fontsize=38,
            font=FONT,
            color="white",
            stroke_color="black",
            stroke_width=1,
            method="caption",
            size=(TARGET_W - 60, None),
            align="center",
        )
        txt = txt.set_duration(dur).set_start(start).set_position(("center", TARGET_H - 175))

        clips.extend([bg, txt])

    return clips


def build_video(script: dict, audio_path: str, output_path: str = "output/short.mp4") -> str:
    """
    Script ve ses dosyasından 1080×1920 Short videosu üretir.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pexels_key = os.environ["PEXELS_API_KEY"]

    # 1) Footage indir
    footage_path = _fetch_pexels_video(script["search_keywords"], pexels_key)

    # 2) Ses dosyasını yükle
    narration_audio = AudioFileClip(audio_path)
    total_duration = narration_audio.duration + 1  # 1 sn buffer

    # 3) Footage'ı hazırla
    raw_clip = VideoFileClip(footage_path, audio=False)

    # Yeterli uzunluğa getir (loop)
    if raw_clip.duration < total_duration:
        repeats = int(total_duration / raw_clip.duration) + 1
        raw_clip = concatenate_videoclips([raw_clip] * repeats)

    bg_clip = raw_clip.subclip(0, total_duration)
    bg_clip = _resize_to_shorts(bg_clip)

    # 4) Overlay katmanları
    layers = [bg_clip]

    # Hook overlay (ilk 3 saniye)
    hook_duration = min(3.0, total_duration)
    layers.extend(_make_hook_overlay(script["hook"], hook_duration))

    # Altyazılar
    layers.extend(_make_subtitle_clips(script["narration"], narration_audio.duration))

    # 5) Video kompozit
    final_video = CompositeVideoClip(layers, size=(TARGET_W, TARGET_H))
    final_video = final_video.set_duration(total_duration)

    # 6) Ses: TTS + arka plan müziği
    audio_tracks = [narration_audio]

    if os.path.exists(MUSIC_PATH):
        music = AudioFileClip(MUSIC_PATH).volumex(0.2)
        if music.duration < total_duration:
            loops = int(total_duration / music.duration) + 1
            from moviepy.audio.fx.audio_loop import audio_loop
            music = audio_loop(music, nloops=loops).subclip(0, total_duration)
        else:
            music = music.subclip(0, total_duration)
        audio_tracks.append(music)

    final_audio = CompositeAudioClip(audio_tracks)
    final_video = final_video.set_audio(final_audio)

    # 7) Export
    print(f"[video_builder] Video render ediliyor: {output_path}")
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

    with open(script_path, encoding="utf-8") as f:
        script = json.load(f)

    build_video(script, audio_path)
    print("[video_builder] Tamamlandı.")
