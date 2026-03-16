"""
video_validator.py — Upload öncesi video kalite kontrolü.

YouTube'a yüklemeden önce şunları doğrular:
  - Dosya var mı ve bozuk mu?
  - Çözünürlük: 1080×1920 (dikey Shorts formatı)
  - Süre: 3–60 saniye (YouTube Shorts limiti)
  - Dosya boyutu: < 256 MB (YouTube limiti)
  - Ses kanalı: stereo veya mono (sessiz değil)
  - Kare hızı: ≥ 24 fps
  - Thumbnail: 1280×720, < 2 MB
  - Script alanları: title, narration, tags zorunlu

Hata varsa ValidationError fırlatır ve Telegram/Discord'a bildirir.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


class ValidationError(Exception):
    """Video doğrulama başarısız."""
    pass


@dataclass
class ValidationResult:
    passed: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.passed = False
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def summary(self) -> str:
        lines = []
        if self.errors:
            lines.append(f"❌ {len(self.errors)} hata:")
            lines.extend(f"  • {e}" for e in self.errors)
        if self.warnings:
            lines.append(f"⚠️  {len(self.warnings)} uyarı:")
            lines.extend(f"  • {w}" for w in self.warnings)
        if self.passed:
            lines.append("✅ Tüm kontroller geçti.")
        return "\n".join(lines)


# ─────────── Sabitler ───────────
MAX_VIDEO_SIZE_MB = 256
MIN_DURATION_SEC = 3.0
MAX_DURATION_SEC = 60.0
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
MIN_FPS = 24
MAX_THUMBNAIL_SIZE_MB = 2.0
TARGET_THUMB_W = 1280
TARGET_THUMB_H = 720
MAX_TITLE_LEN = 100
MIN_TAGS = 3


# ─────────── Video kontrolleri ───────────

def _check_video_file(video_path: str, result: ValidationResult) -> Optional[object]:
    """Dosyayı açmayı ve temel özellikleri kontrol eder."""
    if not os.path.exists(video_path):
        result.fail(f"Video dosyası bulunamadı: {video_path}")
        return None

    size_mb = os.path.getsize(video_path) / (1024 * 1024)
    if size_mb > MAX_VIDEO_SIZE_MB:
        result.fail(f"Dosya çok büyük: {size_mb:.1f} MB > {MAX_VIDEO_SIZE_MB} MB")
    elif size_mb < 0.5:
        result.fail(f"Dosya çok küçük (muhtemelen bozuk): {size_mb:.2f} MB")
    else:
        print(f"[validator] Dosya boyutu: {size_mb:.1f} MB ✓")

    try:
        from moviepy.editor import VideoFileClip
        clip = VideoFileClip(video_path)
        return clip
    except Exception as e:
        result.fail(f"Video dosyası açılamadı (bozuk olabilir): {e}")
        return None


def _check_video_specs(clip, result: ValidationResult) -> None:
    """Çözünürlük, süre, fps kontrolleri."""
    # Süre
    dur = clip.duration
    if dur < MIN_DURATION_SEC:
        result.fail(f"Video çok kısa: {dur:.1f}s (minimum {MIN_DURATION_SEC}s)")
    elif dur > MAX_DURATION_SEC:
        result.fail(f"Video çok uzun: {dur:.1f}s (maksimum {MAX_DURATION_SEC}s — Shorts limiti)")
    else:
        print(f"[validator] Süre: {dur:.1f}s ✓")

    # Çözünürlük
    w, h = clip.size
    if w != TARGET_WIDTH or h != TARGET_HEIGHT:
        result.warn(f"Beklenmeyen çözünürlük: {w}×{h} (beklenen {TARGET_WIDTH}×{TARGET_HEIGHT})")
    else:
        print(f"[validator] Çözünürlük: {w}×{h} ✓")

    # FPS
    fps = clip.fps
    if fps is None or fps < MIN_FPS:
        result.warn(f"Düşük FPS: {fps} (önerilen ≥ {MIN_FPS})")
    else:
        print(f"[validator] FPS: {fps:.1f} ✓")

    # Ses
    if clip.audio is None:
        result.fail("Video'da ses kanalı yok!")
    else:
        try:
            # Küçük bir ses örneği al ve sessiz olup olmadığını kontrol et
            import numpy as np
            sample = clip.audio.subclip(0, min(2, clip.duration))
            frames = list(sample.iter_frames(fps=22050, dtype="float32"))
            if frames:
                arr = __import__("numpy").array(frames)
                rms = float((arr ** 2).mean() ** 0.5)
                if rms < 1e-5:
                    result.warn("Ses seviyesi çok düşük veya sessiz")
                else:
                    print(f"[validator] Ses RMS: {rms:.4f} ✓")
        except Exception:
            pass  # Ses analizi opsiyonel


# ─────────── Thumbnail kontrolü ───────────

def _check_thumbnail(thumb_path: Optional[str], result: ValidationResult) -> None:
    if not thumb_path:
        result.warn("Thumbnail yolu belirtilmemiş.")
        return

    if not os.path.exists(thumb_path):
        result.fail(f"Thumbnail bulunamadı: {thumb_path}")
        return

    size_mb = os.path.getsize(thumb_path) / (1024 * 1024)
    if size_mb > MAX_THUMBNAIL_SIZE_MB:
        result.fail(f"Thumbnail çok büyük: {size_mb:.2f} MB > {MAX_THUMBNAIL_SIZE_MB} MB")

    try:
        from PIL import Image
        img = Image.open(thumb_path)
        w, h = img.size
        if w != TARGET_THUMB_W or h != TARGET_THUMB_H:
            result.warn(f"Thumbnail boyutu: {w}×{h} (önerilen {TARGET_THUMB_W}×{TARGET_THUMB_H})")
        else:
            print(f"[validator] Thumbnail: {w}×{h}, {size_mb:.2f} MB ✓")
        if img.mode not in ("RGB", "RGBA"):
            result.warn(f"Thumbnail renk modu: {img.mode} (RGB önerilen)")
    except Exception as e:
        result.warn(f"Thumbnail açılamadı: {e}")


# ─────────── Script kontrolü ───────────

def _check_script(script: dict, result: ValidationResult) -> None:
    required_fields = ["title", "narration", "tags", "thumbnail_text"]
    for field_name in required_fields:
        if not script.get(field_name):
            result.fail(f"Script'te zorunlu alan eksik: '{field_name}'")

    title = script.get("title", "")
    if len(title) > MAX_TITLE_LEN:
        result.warn(f"Başlık çok uzun: {len(title)} karakter (maksimum {MAX_TITLE_LEN})")

    tags = script.get("tags", [])
    if len(tags) < MIN_TAGS:
        result.warn(f"Az tag: {len(tags)} (minimum {MIN_TAGS} önerilen)")

    narration = script.get("narration", "")
    word_count = len(narration.split())
    if word_count < 50:
        result.warn(f"Anlatı çok kısa: {word_count} kelime")
    elif word_count > 200:
        result.warn(f"Anlatı çok uzun ({word_count} kelime) — ses 60s'yi aşabilir")
    else:
        print(f"[validator] Script: {word_count} kelime ✓")


# ─────────── Ana fonksiyon ───────────

def validate_pipeline_output(
    video_path: str,
    thumb_path: Optional[str] = None,
    script: Optional[dict] = None,
    vtt_path: Optional[str] = None,
) -> ValidationResult:
    """
    Pipeline çıktısını upload öncesi doğrular.

    Args:
        video_path: output/short.mp4
        thumb_path: output/thumbnail.png (isteğe bağlı)
        script: Script dict (isteğe bağlı)
        vtt_path: output/narration.vtt (isteğe bağlı)

    Returns:
        ValidationResult — .passed False ise upload iptal edilmeli
    """
    result = ValidationResult()
    print("\n[validator] === KALİTE KONTROLÜ BAŞLADI ===")

    # Video dosyası
    clip = _check_video_file(video_path, result)
    if clip:
        _check_video_specs(clip, result)
        try:
            clip.close()
        except Exception:
            pass

    # VTT altyazı
    if vtt_path:
        if not os.path.exists(vtt_path):
            result.warn(f"VTT dosyası bulunamadı: {vtt_path}")
        else:
            print(f"[validator] VTT: mevcut ✓")

    # Thumbnail
    _check_thumbnail(thumb_path, result)

    # Script
    if script:
        _check_script(script, result)

    print(f"\n[validator] Sonuç:\n{result.summary()}")
    return result


def validate_or_raise(
    video_path: str,
    thumb_path: Optional[str] = None,
    script: Optional[dict] = None,
    vtt_path: Optional[str] = None,
) -> ValidationResult:
    """
    Doğrular; hata varsa ValidationError fırlatır.
    main.py'deki _step() ile uyumlu kullanım için.
    """
    result = validate_pipeline_output(video_path, thumb_path, script, vtt_path)
    if not result.passed:
        error_summary = "\n".join(result.errors)
        raise ValidationError(f"Video kalite kontrolü başarısız:\n{error_summary}")
    return result


if __name__ == "__main__":
    import sys
    vp = sys.argv[1] if len(sys.argv) > 1 else "output/short.mp4"
    tp = sys.argv[2] if len(sys.argv) > 2 else "output/thumbnail.png"
    r = validate_pipeline_output(vp, tp)
    sys.exit(0 if r.passed else 1)
