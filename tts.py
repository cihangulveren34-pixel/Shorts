"""
tts.py — Edge TTS ile narration metnini MP3 + VTT (kelime zamanlama) dosyasına çevirir.
VTT dosyası video_builder.py'de kesin zamanlı altyazı için kullanılır.
"""

import asyncio
import os
import re
import edge_tts

DEFAULT_VOICE = "en-US-GuyNeural"
RATE = "-5%"
PITCH = "-10Hz"


async def _synthesize(text: str, audio_path: str, vtt_path: str, voice: str = DEFAULT_VOICE) -> None:
    communicate = edge_tts.Communicate(text, voice, rate=RATE, pitch=PITCH)
    subs = edge_tts.SubMaker()
    with open(audio_path, "wb") as audio_f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                subs.create_sub((chunk["offset"], chunk["duration"]), chunk["text"])
    with open(vtt_path, "w", encoding="utf-8") as vtt_f:
        vtt_f.write(subs.generate_subs())


def parse_vtt(vtt_path: str, words_per_chunk: int = 5) -> list:
    """
    VTT dosyasını okuyarak [{start, end, text}] listesi döndürür.
    Kelimeler words_per_chunk gruplara bölünür.
    """
    with open(vtt_path, encoding="utf-8") as f:
        content = f.read()

    # Her VTT cue: timestamp + metin
    pattern = r"(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})\s+(.+)"
    cues = re.findall(pattern, content)

    def to_sec(ts: str) -> float:
        h, m, s = ts.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    # Tek tek kelime cue'larını birleştir
    words = [(to_sec(s), to_sec(e), t.strip()) for s, e, t in cues if t.strip()]
    if not words:
        return []

    chunks = []
    for i in range(0, len(words), words_per_chunk):
        group = words[i:i + words_per_chunk]
        start = group[0][0]
        end = group[-1][1]
        text = " ".join(w[2] for w in group)
        chunks.append({"start": start, "end": end, "text": text})

    return chunks


def generate_audio(narration: str, output_dir: str = "output", voice: str = None) -> tuple:
    """
    Narration metnini Edge TTS ile MP3 + VTT'e çevirir.
    voice: None ise DEFAULT_VOICE kullanılır.
    (audio_path, vtt_path) tuple döndürür.
    """
    os.makedirs(output_dir, exist_ok=True)
    audio_path = os.path.join(output_dir, "narration.mp3")
    vtt_path = os.path.join(output_dir, "narration.vtt")
    selected_voice = voice or DEFAULT_VOICE

    asyncio.run(_synthesize(narration, audio_path, vtt_path, selected_voice))
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
