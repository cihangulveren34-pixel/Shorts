"""
tts.py — Edge TTS ile narration metnini MP3'e çevirir.
"""

import asyncio
import os
import edge_tts

VOICE = "en-US-GuyNeural"
RATE = "+5%"
PITCH = "+5Hz"


async def _synthesize(text: str, output_path: str) -> None:
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH)
    await communicate.save(output_path)


def generate_audio(narration: str, output_path: str = "output/narration.mp3") -> str:
    """
    Narration metnini Edge TTS ile MP3'e çevirir.
    Çıktı dosya yolunu döndürür.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    asyncio.run(_synthesize(narration, output_path))
    print(f"[tts] Ses dosyası oluşturuldu: {output_path}")
    return output_path


if __name__ == "__main__":
    import json, sys

    script_path = sys.argv[1] if len(sys.argv) > 1 else "output/script.json"
    with open(script_path, encoding="utf-8") as f:
        script = json.load(f)

    narration = script["narration"]
    generate_audio(narration)
    print("[tts] Tamamlandı.")
