"""
binaural_anim_gen.py — Manim Community Edition ile 1080x1920 (9:16) TRIPPY animasyonlar.

Konsept: Hipnotik, psychedelic, scroll-stopping gorseller.
- Surekli hareket, hic durmuyor
- Renk degisimleri, neon glow, patlamalar
- Animasyondan animasyona gecis (morph)
- Ekranda kayma, donme, zoom in/out
- "Trippy videos" kafasi

MVP: 3 Scene tipi
  - FibonacciSpiralScene  — Sonsuz buyuyen spiral + parcacik yagmuru + morph
  - MandelbrotZoomScene    — Psychedelic infinite zoom + renk dalgasi
  - SacredFlowerScene      — Hipnotik Flower of Life + isik patlamalari + morph
"""

import argparse
import os
import shutil
import tempfile
import math

import numpy as np

from manim import (
    Scene,
    config,
    Square,
    Arc,
    VGroup,
    Create,
    FadeIn,
    Flash,
    GrowFromCenter,
    ShowPassingFlash,
    Circle,
    Dot,
    ImageMobject,
    AnimationGroup,
    LaggedStart,
    ReplacementTransform,
    LEFT, RIGHT, UP, DOWN, ORIGIN, PI,
    smooth,
    ManimColor,
    tempconfig,
    ValueTracker,
    WHITE,
)


# ─── Mood renkleri ────────────────────────────────────────────────────────────

MOOD_COLORS = {
    "calm":       {"bg": "#020510", "primary": "#64B4FF", "secondary": "#3878B4", "hot": "#FF6490", "alt": "#50FFD0"},
    "healing":    {"bg": "#020A05", "primary": "#50DC82", "secondary": "#2D9650", "hot": "#FFD700", "alt": "#FF6464"},
    "cosmic":     {"bg": "#02020A", "primary": "#FFC83C", "secondary": "#B48C28", "hot": "#FF4080", "alt": "#64FFFF"},
    "sleep":      {"bg": "#020208", "primary": "#5050B4", "secondary": "#3232A0", "hot": "#B464FF", "alt": "#6496FF"},
    "meditation": {"bg": "#030610", "primary": "#78A0DC", "secondary": "#506EA0", "hot": "#FFB450", "alt": "#B464FF"},
    "energy":     {"bg": "#0A0402", "primary": "#FF7828", "secondary": "#C85A1E", "hot": "#FFFF00", "alt": "#FF3264"},
    "spiritual":  {"bg": "#050210", "primary": "#A050FF", "secondary": "#7832C8", "hot": "#FF50A0", "alt": "#64FFBE"},
    "clarity":    {"bg": "#020810", "primary": "#00C8FF", "secondary": "#0096C8", "hot": "#50FF96", "alt": "#FFA050"},
    "focus":      {"bg": "#020810", "primary": "#00C8FF", "secondary": "#0096C8", "hot": "#50FF96", "alt": "#FFA050"},
}
DEFAULT_MOOD = {"bg": "#020410", "primary": "#64B4FF", "secondary": "#3264B4", "hot": "#FF6490", "alt": "#50FFD0"}

PHI = (1 + math.sqrt(5)) / 2


def _get_mood_colors(mood: str) -> dict:
    return MOOD_COLORS.get(mood, DEFAULT_MOOD)


def _make_particle_field(n: int, color, spread_x: float = 6.0, spread_y: float = 9.0) -> VGroup:
    """Floating neon parcaciklar."""
    dots = VGroup()
    for _ in range(n):
        x = np.random.uniform(-spread_x, spread_x)
        y = np.random.uniform(-spread_y, spread_y)
        size = np.random.uniform(0.015, 0.055)
        d = Dot(point=[x, y, 0], radius=size, color=color)
        d.set_opacity(np.random.uniform(0.1, 0.45))
        # Her parcacigin kendi hizi
        d.velocity = np.array([
            np.random.uniform(-0.15, 0.15),
            np.random.uniform(0.05, 0.25),
            0,
        ])
        dots.add(d)
    return dots


def _particle_updater(mob, dt):
    """Parcaciklari yukari surukle, ekrandan cikinca alta tasi."""
    for d in mob:
        d.shift(d.velocity * dt)
        # Yanip sonme
        new_op = d.get_fill_opacity() + np.random.uniform(-0.02, 0.02)
        d.set_opacity(np.clip(new_op, 0.05, 0.5))
        if d.get_y() > 10:
            d.move_to([np.random.uniform(-6, 6), -10, 0])
        if d.get_x() > 7 or d.get_x() < -7:
            d.velocity[0] *= -1


# ─── Scene 1: Fibonacci Spiral — TRIPPY ──────────────────────────────────────

class FibonacciSpiralScene(Scene):
    """
    Surekli hareket eden Fibonacci spiral.
    - Hizlanan insa + flash patlamalar
    - Tamamlaninca spiral ekranda kayar ve doner
    - Renk degisimi (primary → hot → alt cycle)
    - Parcacik yagmuru arka plan
    - Son 10s: spiral zoom-in + kaleidoscope efekti
    """

    mood = "calm"
    anim_duration = 30.0

    def construct(self):
        colors = _get_mood_colors(self.mood)
        bg_color = ManimColor(colors["bg"])
        primary = ManimColor(colors["primary"])
        secondary = ManimColor(colors["secondary"])
        hot = ManimColor(colors["hot"])
        alt = ManimColor(colors["alt"])

        self.camera.background_color = bg_color

        # Arka plan parcaciklari
        particles = _make_particle_field(80, primary)
        self.add(particles)
        particles.add_updater(_particle_updater)

        # ─── Spiral build (ilk %45) ──────────────────────────────────────────
        fibs = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89]
        n_sq = len(fibs)
        scale = 0.032
        dirs = [RIGHT, UP, LEFT, DOWN]

        squares = []
        arcs = []
        glows = []
        cur = np.array([0.0, 0.0, 0.0])

        for i, fib in enumerate(fibs):
            sz = fib * scale
            sq = Square(side_length=sz)
            sq.set_stroke(primary, width=1.5, opacity=0.5)
            sq.set_fill(secondary, opacity=0.08)

            d = dirs[i % 4]
            if i > 0:
                prev_sz = fibs[i - 1] * scale
                offset = (prev_sz / 2 + sz / 2) * d
                sq.move_to(cur + offset)
                cur = cur + offset
            else:
                sq.move_to(cur)

            squares.append(sq)

            ac = sq.get_corner(dirs[(i + 1) % 4] + dirs[(i + 2) % 4])
            glow = Arc(radius=sz, start_angle=PI/2*((i+2)%4), angle=PI/2, arc_center=ac)
            glow.set_stroke(primary, width=16, opacity=0.15)
            glows.append(glow)

            arc = Arc(radius=sz, start_angle=PI/2*((i+2)%4), angle=PI/2, arc_center=ac)
            # Renk gecisi: primary → hot → alt
            if i < 4:
                arc.set_stroke(primary, width=3.5, opacity=1.0)
            elif i < 8:
                arc.set_stroke(hot, width=4, opacity=1.0)
            else:
                arc.set_stroke(alt, width=4.5, opacity=1.0)
            arcs.append(arc)

        spiral = VGroup(*squares, *glows, *arcs)
        spiral.move_to(ORIGIN)

        build_time = self.anim_duration * 0.40
        for i in range(n_sq):
            # Gittikce hizlanan: ilk yavas, son cok hizli
            progress = i / n_sq
            step = build_time / n_sq * (1.8 - progress * 1.2)
            step = max(step, 0.15)

            self.play(
                FadeIn(squares[i], scale=0.2, run_time=step * 0.25),
                AnimationGroup(Create(glows[i]), Create(arcs[i]), lag_ratio=0),
                run_time=step * 0.75,
            )

            # Flash her 2 kutuda + sondakinde
            if i % 2 == 1 or i == n_sq - 1:
                fc = alt if i >= 8 else (hot if i >= 4 else primary)
                self.play(Flash(
                    arcs[i].get_end(), color=fc,
                    flash_radius=0.2 + i * 0.06, line_length=0.1 + i * 0.03,
                    num_lines=6 + i, run_time=0.2,
                ))

        # ─── Kayan isik (%10) ─────────────────────────────────────────────────
        full_arcs = VGroup(*arcs).copy().set_stroke(hot, width=9, opacity=0.85)
        self.play(ShowPassingFlash(full_arcs, time_width=0.25, run_time=self.anim_duration * 0.08))

        # ─── Trippy bolum: spiral hareket ediyor + donerek buyuyor (%35) ──────
        remaining = self.anim_duration - self.renderer.time
        if remaining > 2:
            # Surekli donus
            rot_tracker = ValueTracker(0)
            spiral.add_updater(lambda m, dt: m.rotate(dt * 0.4))

            # Phase 1: Sola kay + zoom in
            p1 = remaining * 0.3
            self.play(
                spiral.animate.shift(LEFT * 1.5).scale(1.4),
                run_time=p1, rate_func=smooth,
            )

            # Phase 2: Merkeze don + zoom out + flash
            p2 = remaining * 0.25
            self.play(
                spiral.animate.move_to(ORIGIN).scale(0.5),
                run_time=p2, rate_func=smooth,
            )
            self.play(Flash(ORIGIN, color=alt, flash_radius=2.5, line_length=0.6,
                           num_lines=20, run_time=0.4))

            # Phase 3: Saga kay + buyut + renk degis (hot → alt arcs)
            p3 = remaining * 0.25
            for arc in arcs[:4]:
                arc.set_stroke(hot, width=4)
            self.play(
                spiral.animate.shift(RIGHT * 1.0).scale(2.0),
                run_time=p3, rate_func=smooth,
            )

            # Phase 4: Son patlama
            p4 = remaining * 0.2
            self.play(
                spiral.animate.move_to(ORIGIN).scale(0.7),
                run_time=p4 * 0.6, rate_func=smooth,
            )
            spiral.clear_updaters()
            self.play(Flash(ORIGIN, color=WHITE, flash_radius=3.0, line_length=0.8,
                           num_lines=24, run_time=p4 * 0.4))


# ─── Scene 2: Mandelbrot Zoom — TRIPPY ───────────────────────────────────────

class MandelbrotZoomScene(Scene):
    """
    Psychedelic Mandelbrot zoom.
    - Surekli zoom (ease-in-out hiz degisimi)
    - Parlak neon renk dalgalari (zaman bazli)
    - Yavas rotasyon
    - Yuksek kontrast (karanliktaki neon)
    """

    mood = "cosmic"
    anim_duration = 30.0

    def construct(self):
        colors = _get_mood_colors(self.mood)
        bg_color = ManimColor(colors["bg"])
        self.camera.background_color = bg_color

        target_x, target_y = -0.7436, 0.1318
        start_scale = 3.0
        end_scale = 0.0003
        n_frames = max(1, int(self.anim_duration * 15))
        w, h = 360, 640

        def mandelbrot_frame(cx, cy, scale, time_t, max_iter=100):
            aspect = w / h
            re = np.linspace(cx - scale * aspect / 2, cx + scale * aspect / 2, w)
            im = np.linspace(cy - scale / 2, cy + scale / 2, h)
            Re, Im = np.meshgrid(re, im)
            C = Re + 1j * Im

            Z = np.zeros_like(C)
            M = np.zeros(C.shape, dtype=float)

            for it in range(max_iter):
                mask = np.abs(Z) <= 2
                Z[mask] = Z[mask] ** 2 + C[mask]
                M[mask] = it

            M = M / max_iter
            img = np.zeros((h, w, 3), dtype=np.uint8)
            inside = M >= (max_iter - 1) / max_iter

            # Neon psychedelic renklendirme — zaman bazli kayma
            t = M[~inside] * 18.0 + time_t * 6 * np.pi

            r = np.sin(t) * 0.5 + 0.5
            g = np.sin(t + 2 * np.pi / 3) * 0.5 + 0.5
            b = np.sin(t + 4 * np.pi / 3) * 0.5 + 0.5

            # Ekstra parlaklik boost
            brightness = 0.3 + 0.7 * (M[~inside] ** 0.5)
            r = np.clip(r * brightness * 1.5, 0, 1)
            g = np.clip(g * brightness * 1.5, 0, 1)
            b = np.clip(b * brightness * 1.5, 0, 1)

            img[~inside, 0] = (r * 255).astype(np.uint8)
            img[~inside, 1] = (g * 255).astype(np.uint8)
            img[~inside, 2] = (b * 255).astype(np.uint8)

            # Ici koyu mor/mavi
            img[inside, 0] = 8
            img[inside, 1] = 3
            img[inside, 2] = 18

            return img

        # S-curve zoom (yavas → hizli → yavas)
        t_vals = np.linspace(0, 1, n_frames)
        ease = 0.5 - 0.5 * np.cos(np.pi * t_vals)
        scales = start_scale * (end_scale / start_scale) ** ease
        frame_dur = self.anim_duration / n_frames

        prev_mob = None
        for idx, sc in enumerate(scales):
            time_t = idx / n_frames
            img_arr = mandelbrot_frame(target_x, target_y, sc, time_t)

            from PIL import Image
            pil_img = Image.fromarray(img_arr)
            tmp_path = os.path.join(tempfile.gettempdir(), f"mb_{idx:04d}.png")
            pil_img.save(tmp_path)

            mob = ImageMobject(tmp_path)
            mob.height = config.frame_height * 1.7
            mob.move_to(ORIGIN)
            mob.rotate(time_t * PI * 0.7)

            if prev_mob is not None:
                self.remove(prev_mob)
            self.add(mob)
            self.wait(frame_dur)
            prev_mob = mob

            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ─── Scene 3: Sacred Flower of Life — TRIPPY ─────────────────────────────────

class SacredFlowerScene(Scene):
    """
    Hipnotik Flower of Life.
    - Flash patlamali dramatik insa
    - Tamamlaninca nefes aliyor (pulse)
    - Donerek buyuyor/kuculuyor
    - Arka planda orbiting parcaciklar
    - Son 10s: ikinci bir flower morph + patlama
    """

    mood = "spiritual"
    anim_duration = 30.0

    def construct(self):
        colors = _get_mood_colors(self.mood)
        bg_color = ManimColor(colors["bg"])
        primary = ManimColor(colors["primary"])
        secondary = ManimColor(colors["secondary"])
        hot = ManimColor(colors["hot"])
        alt = ManimColor(colors["alt"])

        self.camera.background_color = bg_color

        # Orbiting parcaciklar
        particles = _make_particle_field(60, secondary)
        self.add(particles)

        def _orbit(mob, dt):
            for d in mob:
                pos = d.get_center()
                angle = math.atan2(pos[1], pos[0]) + dt * 0.1
                r = np.sqrt(pos[0]**2 + pos[1]**2)
                d.move_to([r * math.cos(angle), r * math.sin(angle), 0])
                new_op = d.get_fill_opacity() + np.random.uniform(-0.02, 0.02)
                d.set_opacity(np.clip(new_op, 0.05, 0.5))
        particles.add_updater(_orbit)

        radius = 1.0

        def _make_flower(r, primary_c, secondary_c, glow_width=16):
            """Bir Flower of Life deseni olustur."""
            center_glow = Circle(radius=r).set_stroke(primary_c, width=glow_width, opacity=0.2)
            center = Circle(radius=r).set_stroke(primary_c, width=3.5, opacity=1.0)
            cg = VGroup(center_glow, center).move_to(ORIGIN)

            r1 = VGroup()
            for i in range(6):
                angle = i * PI / 3
                pos = np.array([r * math.cos(angle), r * math.sin(angle), 0])
                gl = Circle(radius=r).set_stroke(primary_c, width=glow_width * 0.8, opacity=0.15)
                c = Circle(radius=r).set_stroke(primary_c, width=2.8, opacity=0.9)
                r1.add(VGroup(gl, c).move_to(pos))

            r2 = VGroup()
            for i in range(6):
                angle = i * PI / 3 + PI / 6
                pos = np.array([
                    r * math.sqrt(3) * math.cos(angle),
                    r * math.sqrt(3) * math.sin(angle), 0,
                ])
                gl = Circle(radius=r).set_stroke(secondary_c, width=glow_width * 0.6, opacity=0.1)
                c = Circle(radius=r).set_stroke(secondary_c, width=2, opacity=0.7)
                r2.add(VGroup(gl, c).move_to(pos))

            outer_gl = Circle(radius=r * 2.5).set_stroke(primary_c, width=glow_width * 1.2, opacity=0.12)
            outer = Circle(radius=r * 2.5).set_stroke(primary_c, width=4, opacity=0.85)
            og = VGroup(outer_gl, outer).move_to(ORIGIN)

            flower = VGroup(cg, r1, r2, og)
            return flower

        # ─── Ana flower build (%45) ───────────────────────────────────────────
        flower1 = _make_flower(radius, primary, secondary)
        flower1.scale_to_fit_height(config.frame_height * 0.6)
        flower1.move_to(ORIGIN)

        cg, r1, r2, og = flower1[0], flower1[1], flower1[2], flower1[3]

        # Merkez: flash ile basla
        build_time = self.anim_duration * 0.35
        self.play(GrowFromCenter(cg, run_time=build_time * 0.12))
        self.play(Flash(ORIGIN, color=primary, flash_radius=0.8, line_length=0.2,
                       num_lines=12, run_time=0.3))

        # Ring 1: hizli cascade + flash'lar
        per_r1 = build_time * 0.25 / 6
        for i, c in enumerate(r1):
            self.play(GrowFromCenter(c, run_time=per_r1 * 0.65))
            if i % 2 == 0:
                self.play(Flash(c.get_center(), color=hot, flash_radius=0.35,
                               line_length=0.1, num_lines=6, run_time=per_r1 * 0.35))

        # Ring 2: LaggedStart
        self.play(
            LaggedStart(*[Create(c) for c in r2], lag_ratio=0.12),
            run_time=build_time * 0.18,
        )
        # Buyuk patlama
        self.play(Flash(ORIGIN, color=hot, flash_radius=1.5, line_length=0.35,
                       num_lines=18, run_time=0.35))

        # Dis halka
        self.play(Create(og, run_time=build_time * 0.1))
        self.play(Flash(ORIGIN, color=alt, flash_radius=2.2, line_length=0.5,
                       num_lines=20, run_time=0.35))

        # ─── Trippy transition: nefes + hareket + morph (%55) ─────────────────

        remaining = self.anim_duration - self.renderer.time
        if remaining < 3:
            return

        # Surekli donus
        flower1.add_updater(lambda m, dt: m.rotate(dt * 0.2))

        # Phase 1: Pulse + ShowPassingFlash (%20)
        p1 = remaining * 0.20
        outer_flash = og[1].copy().set_stroke(hot, width=10, opacity=0.8)
        self.play(
            flower1.animate.scale(1.15),
            ShowPassingFlash(outer_flash.copy(), time_width=0.35, run_time=p1),
            run_time=p1, rate_func=smooth,
        )
        self.play(flower1.animate.scale(1 / 1.15), run_time=p1 * 0.5, rate_func=smooth)

        # Phase 2: Ekranda kayma — sola git, merkeze don (%20)
        p2 = remaining * 0.20
        self.play(
            flower1.animate.shift(LEFT * 2).scale(0.7),
            run_time=p2 * 0.5, rate_func=smooth,
        )
        self.play(
            flower1.animate.move_to(ORIGIN).scale(1.3),
            run_time=p2 * 0.5, rate_func=smooth,
        )
        self.play(Flash(ORIGIN, color=hot, flash_radius=1.8, line_length=0.4,
                       num_lines=16, run_time=0.3))

        # Phase 3: Morph — ikinci farkli renkli flower'a donusum (%25)
        p3 = remaining * 0.25
        flower2 = _make_flower(radius, hot, alt, glow_width=20)
        flower2.scale_to_fit_height(config.frame_height * 0.65)
        flower2.move_to(ORIGIN)
        flower2.rotate(PI / 6)  # Hafif donuk (fark yaratir)

        flower1.clear_updaters()
        self.play(
            ReplacementTransform(flower1, flower2),
            run_time=p3 * 0.7, rate_func=smooth,
        )

        # Yeni flower da donuyor
        flower2.add_updater(lambda m, dt: m.rotate(-dt * 0.25))

        # Patlama
        self.play(Flash(ORIGIN, color=alt, flash_radius=2.5, line_length=0.6,
                       num_lines=24, run_time=p3 * 0.3))

        # Phase 4: Son pulse + patlama (%35)
        p4 = remaining * 0.35
        pulse_n = max(1, int(p4 / 2.5))
        per_p = p4 / pulse_n

        for j in range(pulse_n):
            outer_flash2 = flower2[3][1].copy().set_stroke(alt, width=12, opacity=0.9)
            self.play(
                flower2.animate.scale(1.08),
                ShowPassingFlash(outer_flash2, time_width=0.4, run_time=per_p * 0.5),
                run_time=per_p * 0.5, rate_func=smooth,
            )
            self.play(
                flower2.animate.scale(1 / 1.08),
                run_time=per_p * 0.5, rate_func=smooth,
            )

        flower2.clear_updaters()

        # Final flash
        self.play(Flash(ORIGIN, color=WHITE, flash_radius=3.5, line_length=1.0,
                       num_lines=30, run_time=0.4))


# ─── Registry ────────────────────────────────────────────────────────────────

SCENE_MAP = {
    "fibonacci_spiral": FibonacciSpiralScene,
    "mandelbrot_zoom": MandelbrotZoomScene,
    "sacred_flower": SacredFlowerScene,
}


def generate_math_animation(
    math_type: str,
    duration_sec: float = 30.0,
    output_path: str = "output/binaural_anim.mp4",
    mood: str = "calm",
) -> str:
    """
    Manim ile matematik animasyonu uretir.

    Args:
        math_type: fibonacci_spiral | mandelbrot_zoom | sacred_flower
        duration_sec: Animasyon suresi (saniye)
        output_path: Cikti MP4 yolu
        mood: Renk paleti secimi

    Returns:
        Uretilen MP4 dosya yolu
    """
    scene_cls = SCENE_MAP.get(math_type)
    if not scene_cls:
        available = ", ".join(SCENE_MAP.keys())
        raise ValueError(f"Bilinmeyen math_type: {math_type!r}. Mevcut: {available}")

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    scene_cls.mood = mood
    scene_cls.anim_duration = duration_sec

    abs_output = os.path.abspath(output_path)
    media_dir = tempfile.mkdtemp(prefix="manim_binaural_")

    print(f"[binaural_anim] {math_type} animasyonu uretiliyor ({duration_sec}s, mood={mood})...")

    with tempconfig({
        "pixel_width": 1080,
        "pixel_height": 1920,
        "frame_rate": 30,
        "media_dir": media_dir,
        "disable_caching": True,
        "output_file": os.path.basename(output_path).replace(".mp4", ""),
    }):
        scene = scene_cls()
        scene.render()

    rendered = None
    for root, dirs, files in os.walk(media_dir):
        for f in files:
            if f.endswith(".mp4"):
                rendered = os.path.join(root, f)
                break
        if rendered:
            break

    if not rendered or not os.path.exists(rendered):
        raise RuntimeError(f"Manim ciktisi bulunamadi: {media_dir}")

    shutil.move(rendered, abs_output)

    try:
        shutil.rmtree(media_dir)
    except OSError:
        pass

    print(f"[binaural_anim] Animasyon tamamlandi: {abs_output}")
    return abs_output


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Binaural Math Animation Generator")
    parser.add_argument("--type", required=True, choices=list(SCENE_MAP.keys()),
                        help="Animasyon tipi")
    parser.add_argument("--duration", type=float, default=30.0,
                        help="Animasyon suresi (saniye)")
    parser.add_argument("--output", default="output/binaural_anim.mp4",
                        help="Cikti dosya yolu")
    parser.add_argument("--mood", default="calm",
                        help="Renk paleti (calm, sleep, energy, spiritual, ...)")
    args = parser.parse_args()

    result = generate_math_animation(
        math_type=args.type,
        duration_sec=args.duration,
        output_path=args.output,
        mood=args.mood,
    )
    print(f"Cikti: {result}")
