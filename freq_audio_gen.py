"""
freq_audio_gen.py — Belirli bir frekansta saf sinüs dalgası sesi üretir.

Özellikler:
  - Saf sinüs dalgası (pure tone) at target Hz
  - Fade-in / fade-out (2 saniye)
  - Randomize binaural beat katmanı (sol/sağ kulak farkı)
  - Yumuşak ambient pad + pink noise karışımı (Content ID bypass)
  - 15 saniye varsayılan süre
  - 44100 Hz stereo WAV → MP3 çıktı
"""

import os
import struct
import wave
import subprocess
import tempfile
import math
import random

SAMPLE_RATE = 44100
CHANNELS = 2
SAMPLE_WIDTH = 2  # 16-bit
DEFAULT_DURATION = 15  # saniye (fade-in/out bu süre içinde uygulanır)
FADE_SEC = 2          # fade-in ve fade-out süresi


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


def _pink_noise(n_samples: int, amplitude: float = 0.05) -> list[float]:
    """Voss-McCartney algoritması ile pink noise üretir."""
    rows = 16
    running_total = 0.0
    vals = [0.0] * rows
    out = []
    max_val = 0.0
    for i in range(n_samples):
        idx = 0
        n = i
        while n > 0 and idx < rows:
            if n & 1:
                new_val = random.uniform(-1, 1)
                running_total -= vals[idx]
                vals[idx] = new_val
                running_total += new_val
            n >>= 1
            idx += 1
        white = random.uniform(-1, 1)
        sample = (running_total + white) / (rows + 1)
        out.append(sample)
        max_val = max(max_val, abs(sample))
    if max_val > 0:
        out = [s / max_val * amplitude for s in out]
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
    binaural_offset: float = 0,
    ambient_ratio: float = 0,
) -> str:
    """
    Belirtilen frekansta frekans sesi üretir ve MP3 olarak kaydeder.
    Content ID bypass için parametreler her çalıştırmada randomize edilir.

    Args:
        hz: Hedef frekans (örn. 528.0)
        output_mp3: Çıktı MP3 dosya yolu
        duration_sec: Ses süresi (saniye)
        binaural_offset: Binaural beat farkı Hz (0 = otomatik randomize)
        ambient_ratio: Ambient pad karışım oranı (0 = otomatik randomize)

    Returns:
        output_mp3 yolu
    """
    # ─── Parametreleri randomize et (Content ID benzersizliği) ────────────────
    if binaural_offset == 0:
        binaural_offset = round(random.uniform(3.5, 6.5), 2)
    if ambient_ratio == 0:
        ambient_ratio = round(random.uniform(0.06, 0.14), 3)

    # Ekstra benzersizlik: amplitude ve harmonik oranları da hafif rastgele
    main_amp = round(random.uniform(0.60, 0.70), 3)
    sub_amp = round(random.uniform(0.20, 0.35), 3)
    harm3_amp = round(random.uniform(0.05, 0.12), 3)
    pink_amp = round(random.uniform(0.03, 0.07), 3)

    print(f"[freq_audio_gen] {hz} Hz ses üretiliyor ({duration_sec:.0f}s) "
          f"binaural={binaural_offset}Hz, ambient={ambient_ratio}, pink={pink_amp}")

    n_samples = int(SAMPLE_RATE * duration_sec)

    # ─── 1) Ana frekans dalgaları ─────────────────────────────────────────────
    left_tone = _sine_wave(hz, duration_sec, amplitude=main_amp)
    right_tone = _sine_wave(hz + binaural_offset, duration_sec, amplitude=main_amp)

    # ─── 2) Ambient pad (alt harmonikler) ────────────────────────────────────
    sub_hz = hz / 2.0
    pad_left = _sine_wave(sub_hz, duration_sec, amplitude=sub_amp)
    harm3 = _sine_wave(hz * 3, duration_sec, amplitude=harm3_amp)
    pad_left = _mix(pad_left, harm3, ratio=0.2)

    # Sağ pad hafif farklı fazda (ekstra benzersizlik)
    pad_right = _sine_wave(sub_hz + 0.5, duration_sec, amplitude=sub_amp)
    pad_right = _mix(pad_right, harm3, ratio=0.2)

    left_tone = _mix(left_tone, pad_left, ratio=ambient_ratio)
    right_tone = _mix(right_tone, pad_right, ratio=ambient_ratio)

    # ─── 3) Pink noise katmanı (Content ID fingerprint kırıcı) ───────────────
    pink_l = _pink_noise(n_samples, amplitude=pink_amp)
    pink_r = _pink_noise(n_samples, amplitude=pink_amp)
    left_tone = _mix(left_tone, pink_l, ratio=0.15)
    right_tone = _mix(right_tone, pink_r, ratio=0.15)

    # ─── 4) Fade-in / fade-out ────────────────────────────────────────────────
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
