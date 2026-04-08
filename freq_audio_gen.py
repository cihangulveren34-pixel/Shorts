"""
freq_audio_gen.py — Belirli bir frekansta saf sinüs dalgası sesi üretir.

Özellikler:
  - Saf sinüs dalgası (pure tone) at target Hz
  - Fade-in / fade-out (5 saniye)
  - Opsiyonel binaural beat katmanı (sol/sağ kulak farkı)
  - Opsiyonel yumuşak ambient pad karışımı
  - 60 saniye varsayılan süre
  - 44100 Hz stereo WAV → MP3 çıktı
"""

import os
import struct
import wave
import subprocess
import tempfile
import math

SAMPLE_RATE = 44100
CHANNELS = 2
SAMPLE_WIDTH = 2  # 16-bit
DEFAULT_DURATION = 62  # saniye (bitiş fade hesabı için 2 sn fazla)
FADE_SEC = 5          # fade-in ve fade-out süresi


def _sine_wave(freq_hz: float, duration_sec: float, amplitude: float = 0.7) -> list[float]:
    """Verilen frekansta saf sinüs dalgası üretir. [-1, 1] aralığında float listesi döner."""
    n_samples = int(SAMPLE_RATE * duration_sec)
    return [
        amplitude * math.sin(2 * math.pi * freq_hz * i / SAMPLE_RATE)
        for i in range(n_samples)
    ]


def _apply_fade(samples: list[float], fade_sec: float) -> list[float]:
    """Başa ve sona fade uygular."""
    fade_n = int(SAMPLE_RATE * fade_sec)
    result = list(samples)
    total = len(result)
    for i in range(min(fade_n, total)):
        factor = i / fade_n
        result[i] *= factor
        if total - 1 - i >= 0:
            result[total - 1 - i] *= factor
    return result


def _mix(a: list[float], b: list[float], ratio: float = 0.5) -> list[float]:
    """İki ses kanalını karıştırır. ratio: b'nin ağırlığı (0=sadece a, 1=sadece b)."""
    n = max(len(a), len(b))
    out = []
    for i in range(n):
        va = a[i] if i < len(a) else 0.0
        vb = b[i] if i < len(b) else 0.0
        out.append(va * (1 - ratio) + vb * ratio)
    return out


def _samples_to_bytes(left: list[float], right: list[float]) -> bytes:
    """Float örnekleri stereo 16-bit PCM baytına dönüştürür."""
    n = min(len(left), len(right))
    frames = bytearray()
    for i in range(n):
        l_val = max(-1.0, min(1.0, left[i]))
        r_val = max(-1.0, min(1.0, right[i]))
        l_int = int(l_val * 32767)
        r_int = int(r_val * 32767)
        frames += struct.pack("<hh", l_int, r_int)
    return bytes(frames)


def generate_frequency_audio(
    hz: float,
    output_mp3: str,
    duration_sec: float = DEFAULT_DURATION,
    binaural_offset: float = 4.0,
    ambient_ratio: float = 0.08,
) -> str:
    """
    Belirtilen frekansta frekans sesi üretir ve MP3 olarak kaydeder.

    Args:
        hz: Hedef frekans (örn. 528.0)
        output_mp3: Çıktı MP3 dosya yolu
        duration_sec: Ses süresi (saniye)
        binaural_offset: Binaural beat farkı Hz (sağ kulak = hz + offset)
                         0 ise binaural devre dışı (mono pure tone)
        ambient_ratio: Ambient pad karışım oranı (0.0 = sadece ton, 0.15 = hafif pad)

    Returns:
        output_mp3 yolu
    """
    print(f"[freq_audio_gen] {hz} Hz ses üretiliyor ({duration_sec:.0f}s)...")

    # ─── 1) Ana frekans dalgaları ─────────────────────────────────────────────
    left_tone = _sine_wave(hz, duration_sec, amplitude=0.65)
    if binaural_offset > 0:
        right_tone = _sine_wave(hz + binaural_offset, duration_sec, amplitude=0.65)
    else:
        right_tone = list(left_tone)

    # ─── 2) Opsiyonel ambient pad (alt harmonikler) ───────────────────────────
    if ambient_ratio > 0:
        sub_hz = hz / 2.0  # oktav altı
        pad_left = _sine_wave(sub_hz, duration_sec, amplitude=0.3)
        # 3. harmonik hafifçe
        harm3 = _sine_wave(hz * 3, duration_sec, amplitude=0.08)
        pad_left = _mix(pad_left, harm3, ratio=0.2)

        pad_right = list(pad_left)
        left_tone = _mix(left_tone, pad_left, ratio=ambient_ratio)
        right_tone = _mix(right_tone, pad_right, ratio=ambient_ratio)

    # ─── 3) Fade-in / fade-out ────────────────────────────────────────────────
    left_tone = _apply_fade(left_tone, FADE_SEC)
    right_tone = _apply_fade(right_tone, FADE_SEC)

    # ─── 4) WAV yaz ──────────────────────────────────────────────────────────
    tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False, prefix="freq_")
    tmp_wav.close()

    pcm_data = _samples_to_bytes(left_tone, right_tone)
    with wave.open(tmp_wav.name, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_data)

    print(f"[freq_audio_gen] WAV yazıldı: {tmp_wav.name} ({os.path.getsize(tmp_wav.name) // 1024} KB)")

    # ─── 5) WAV → MP3 (ffmpeg) ───────────────────────────────────────────────
    os.makedirs(os.path.dirname(output_mp3) if os.path.dirname(output_mp3) else ".", exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", tmp_wav.name,
        "-codec:a", "libmp3lame",
        "-b:a", "192k",
        "-ar", str(SAMPLE_RATE),
        output_mp3,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(tmp_wav.name)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg WAV→MP3 dönüşümü başarısız:\n{result.stderr}")

    print(f"[freq_audio_gen] MP3 kaydedildi: {output_mp3} ({os.path.getsize(output_mp3) // 1024} KB)")
    return output_mp3


if __name__ == "__main__":
    # Test: 528 Hz, 30 saniye
    out = generate_frequency_audio(528.0, "/tmp/test_528hz.mp3", duration_sec=30)
    print(f"Test çıktısı: {out}")
