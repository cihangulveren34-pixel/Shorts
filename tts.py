"""
tts.py — Edge TTS ile narration metnini MP3 + VTT (kelime zamanlama) dosyasına çevirir.
VTT dosyası video_builder.py'de kesin zamanlı altyazı için kullanılır.
"""

import asyncio
import os
import re
import edge_tts

DEFAULT_VOICE = "en-US-GuyNeural"
RATE = "+40%"
PITCH = "-5Hz"


async def _synthesize(text: str, audio_path: str, vtt_path: str, voice: str = DEFAULT_VOICE, rate: str = None, pitch: str = None) -> None:
    communicate = edge_tts.Communicate(text, voice, rate=rate or RATE, pitch=pitch or PITCH)
    subs = edge_tts.SubMaker()
    sub_type = None  # Track which boundary type we use
    with open(audio_path, "wb") as audio_f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_f.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                # SubMaker only accepts one type, use whichever comes first
                if sub_type is None:
                    sub_type = chunk["type"]
                if chunk["type"] == sub_type:
                    try:
                        subs.feed(chunk)
                    except Exception:
                        pass
    # get_srt() returns SRT format, convert to VTT
    srt_content = subs.get_srt()
    vtt_content = _srt_to_vtt(srt_content)
    with open(vtt_path, "w", encoding="utf-8") as vtt_f:
        vtt_f.write(vtt_content)


def _srt_to_vtt(srt: str) -> str:
    """SRT formatını WebVTT'ye çevirir."""
    vtt = "WEBVTT\n\n"
    # SRT uses comma for milliseconds, VTT uses period
    srt = srt.replace(",", ".")
    # Remove sequence numbers (lines that are just digits)
    lines = srt.strip().split("\n")
    result_lines = []
    for line in lines:
        if line.strip().isdigit():
            continue
        result_lines.append(line)
    vtt += "\n".join(result_lines)
    return vtt


def parse_vtt(vtt_path: str, words_per_chunk: int = 4) -> list:
    """
    VTT dosyasını okuyarak [{start, end, text}] listesi döndürür.
    Cümle bazlı altyazıları kelime gruplarına böler.
    """
    with open(vtt_path, encoding="utf-8") as f:
        content = f.read()

    # Her VTT cue: timestamp + metin
    pattern = r"(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})\s+(.+)"
    cues = re.findall(pattern, content)

    def to_sec(ts: str) -> float:
        h, m, s = ts.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    if not cues:
        return []

    # Cümle bazlı cue'ları kelime gruplarına böl
    chunks = []
    for start_ts, end_ts, text in cues:
        text = text.strip()
        if not text:
            continue
        start = to_sec(start_ts)
        end = to_sec(end_ts)
        words = text.split()
        duration = end - start
        secs_per_word = duration / max(len(words), 1)

        for i in range(0, len(words), words_per_chunk):
            group = words[i:i + words_per_chunk]
            chunk_start = start + i * secs_per_word
            chunk_end = start + min(i + words_per_chunk, len(words)) * secs_per_word
            chunks.append({
                "start": chunk_start,
                "end": chunk_end,
                "text": " ".join(group),
            })

    return chunks


def generate_audio(narration: str, output_dir: str = "output", voice: str = None, rate: str = None, pitch: str = None) -> tuple:
    """
    Narration metnini Edge TTS ile MP3 + VTT'e çevirir.
    voice: None ise DEFAULT_VOICE kullanılır.
    rate/pitch: None ise modül sabitleri kullanılır.
    (audio_path, vtt_path) tuple döndürür.
    """
    os.makedirs(output_dir, exist_ok=True)
    audio_path = os.path.join(output_dir, "narration.mp3")
    vtt_path = os.path.join(output_dir, "narration.vtt")
    selected_voice = voice or DEFAULT_VOICE

    asyncio.run(_synthesize(narration, audio_path, vtt_path, selected_voice, rate, pitch))
    print(f"[tts] Ses: {audio_path} (ses: {selected_voice})")
    print(f"[tts] Altyazı zamanlaması: {vtt_path}")
    return audio_path, vtt_path


if __name__ == "__main__":
    import json, sys

    script_path = sys.argv[1] if len(sys.argv) > 1 else "output/script.json"
    with open(script_path, encoding="utf-8") as f:
        script = json.load(f)

    audio, vtt = generate_audio(script["narration"])
    chunks = parse_vtt(vtt)
    print(f"[tts] {len(chunks)} altyazı chunk'ı üretildi.")
