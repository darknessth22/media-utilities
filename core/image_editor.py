"""Image editor — fit/alignment, flip/rotate/crop, filter presets, color grading,
post effects (sharpen/blur/grain/vignette), user presets, aspect-ratio presets.

Pure Pillow pipeline. No new deps.

Pipeline order:
    1. Free-rotate (degrees, expand canvas)
    2. Percent crop (top/left/bottom/right)
    3. Flip (H/V)
    4. Fit into target canvas (cover/fill/center/stretch) + bg color
    5. Color adjustments (brightness/contrast/saturation/hue/shadows/highlights
       + temperature/tint + black-point/white-point)
    6. Filter preset, strength-blended against the un-filtered post-adjust image
    7. Post effects (sharpen/blur, grain, vignette)

Presets stored at  user_config_dir()/image_presets.json.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from utils.paths import user_config_dir


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

FIT_MODES = ("cover", "fill", "center", "stretch")
# cover   = scale to fully cover canvas, crop overflow (preserves aspect)
# fill    = scale to fit inside canvas, letterbox with bg (preserves aspect)
# center  = no scale; place original centered, crop or letterbox with bg
# stretch = distort to canvas exactly


# Aspect/monitor presets — (key, target_w, target_h). UI shows the label key.
ASPECT_PRESETS: list[tuple[str, int, int]] = [
    ("custom",            0,    0),     # sentinel — keep current W×H
    ("aspect_1_1",        1080, 1080),
    ("aspect_16_9",       1920, 1080),
    ("aspect_9_16",       1080, 1920),
    ("aspect_4_5",        1080, 1350),
    ("aspect_4_3",        1600, 1200),
    ("aspect_3_4",        1200, 1600),
    ("aspect_21_9",       2560, 1080),
    ("monitor_1080p_h",   1920, 1080),
    ("monitor_1080p_v",   1080, 1920),
    ("monitor_1440p_h",   2560, 1440),
    ("monitor_1440p_v",   1440, 2560),
    ("monitor_4k_h",      3840, 2160),
    ("monitor_4k_v",      2160, 3840),
]


# ── Built-in filter presets ───────────────────────────────────────────────────
# Adjust deltas applied multiplicatively (brightness/contrast/saturation are
# ImageEnhance factors centered at 1.0). hue in degrees. shadows/highlights in
# -1..+1. temperature/tint in -100..+100 (added 2026-05-20 v2).

def _f(brightness=1.0, contrast=1.0, saturation=1.0, hue=0,
       shadows=0.0, highlights=0.0, temperature=0, tint=0) -> dict:
    return dict(brightness=brightness, contrast=contrast, saturation=saturation,
                hue=hue, shadows=shadows, highlights=highlights,
                temperature=temperature, tint=tint)


BUILTIN_FILTERS: dict[str, dict] = {
    "none":             _f(),
    "vibrant_contrast": _f(brightness=1.05, contrast=1.35, saturation=1.40, shadows=0.10, highlights=-0.05),
    "vibrant_darkness": _f(brightness=0.85, contrast=1.45, saturation=1.50, shadows=-0.20, highlights=-0.10),
    "color_boost":      _f(brightness=1.02, contrast=1.15, saturation=1.70, shadows=0.05),
    "shadow_boost":     _f(brightness=1.05, contrast=1.10, saturation=1.10, shadows=0.45, highlights=-0.10),
    "moon_light":       _f(brightness=0.92, contrast=1.20, saturation=0.70, hue=-8,  shadows=-0.15, highlights=0.10, temperature=-40),
    "late_night":       _f(brightness=0.78, contrast=1.30, saturation=0.85, hue=-12, shadows=-0.25, highlights=-0.20, temperature=-25),
    "golden_hour":      _f(brightness=1.08, contrast=1.10, saturation=1.25, shadows=0.10, highlights=0.05, temperature=45),
    "cool_cinema":      _f(brightness=0.95, contrast=1.25, saturation=0.95, hue=-15, shadows=-0.10, temperature=-30),
    "warm_film":        _f(brightness=1.03, contrast=1.15, saturation=1.10, shadows=0.05, highlights=-0.05, temperature=25, tint=8),
    "bw_classic":       _f(contrast=1.30, saturation=0.0, shadows=-0.05, highlights=0.05),
    "faded_film":       _f(brightness=1.10, contrast=0.80, saturation=0.85, shadows=0.15, highlights=0.10, temperature=15),
    # New presets (2026-05-20 v2)
    "faded_polaroid":   _f(brightness=1.12, contrast=0.78, saturation=0.80, shadows=0.20, highlights=0.15, temperature=20, tint=-6),
    "teal_orange":      _f(brightness=1.0,  contrast=1.20, saturation=1.30, shadows=-0.15, highlights=0.10, temperature=15, tint=-12),
    "bleach_bypass":    _f(brightness=1.05, contrast=1.50, saturation=0.55, shadows=-0.10, highlights=0.10),
    "cyberpunk":        _f(brightness=0.95, contrast=1.35, saturation=1.60, hue=10,  shadows=-0.20, highlights=0.05, temperature=-20, tint=20),
    "sepia":            _f(contrast=1.10, saturation=0.20, temperature=55, tint=10),
    "lomo":             _f(brightness=0.95, contrast=1.40, saturation=1.45, shadows=-0.25, highlights=-0.10, temperature=10),
    "cross_process":    _f(brightness=1.02, contrast=1.30, saturation=1.35, hue=8,   shadows=-0.10, highlights=0.10, temperature=-15, tint=18),
}


# Channels exposed in the manual Adjust card (UI builds sliders for these).
ADJUST_CHANNELS = (
    "brightness", "contrast", "saturation",
    "hue", "shadows", "highlights",
    "temperature", "tint",
    "black_point", "white_point",
)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class FitOptions:
    target_w: int = 1080
    target_h: int = 1080
    mode: str = "cover"
    bg_color: str = "#000000"
    flip_h: bool = False
    flip_v: bool = False
    rotate_deg: float = 0.0          # -180..180, free rotate (canvas expanded, gaps filled with bg)
    crop_top: float = 0.0            # 0..0.49 fraction of height to crop from top
    crop_left: float = 0.0           # 0..0.49 fraction of width to crop from left
    crop_bottom: float = 0.0         # 0..0.49 fraction of height to crop from bottom
    crop_right: float = 0.0          # 0..0.49 fraction of width to crop from right


@dataclass
class FilterOptions:
    preset: str = "none"
    strength: float = 1.0  # 0..1


@dataclass
class AdjustOptions:
    enabled: bool = False
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    hue: int = 0
    shadows: float = 0.0
    highlights: float = 0.0
    temperature: int = 0     # -100..100   (negative=cool/blue, positive=warm/red)
    tint: int = 0            # -100..100   (negative=green, positive=magenta)
    black_point: int = 0     # 0..50   (input level clipped to 0)
    white_point: int = 100   # 50..100 (input level clipped to 255)


@dataclass
class EffectsOptions:
    sharpen: float = 0.0          # 0..2.0  (ImageEnhance.Sharpness factor minus 1, applied if > 0)
    blur: float = 0.0             # 0..10   (GaussianBlur radius, applied if > 0)
    grain: float = 0.0            # 0..1    (gray noise blend amount)
    vignette: float = 0.0         # 0..1    (radial darken intensity)
    # Gradient overlay
    gradient_amount: float = 0.0  # 0..1
    gradient_color1: str = "#000000"
    gradient_color2: str = "#FFFFFF"
    gradient_angle: int = 0       # 0..359 degrees (0 = left→right, 90 = top→bottom)
    # Duotone — maps luminance to a 2-colour ramp
    duotone_amount: float = 0.0   # 0..1 (blend strength)
    duotone_dark: str = "#1E3A8A"
    duotone_light: str = "#FCD34D"
    # Glass blur — gaussian blur applied to a copy and overlaid at opacity
    glass_blur: float = 0.0       # 0..1
    glass_blur_radius: float = 12.0  # gaussian radius for the glass layer


@dataclass
class EditConfig:
    fit: FitOptions = field(default_factory=FitOptions)
    filter: FilterOptions = field(default_factory=FilterOptions)
    adjust: AdjustOptions = field(default_factory=AdjustOptions)
    effects: EffectsOptions = field(default_factory=EffectsOptions)


# ── Helpers ───────────────────────────────────────────────────────────────────

def dominant_color(img: Image.Image, n_colors: int = 5, palette_size: int = 64) -> str:
    """Most frequent quantised colour in `img` as `#RRGGBB`.

    Uses Pillow's median-cut quantiser. Cheap, no extra deps. Useful as a
    matched letterbox background — visually closer to the photo's mood than the
    edge median when the subject occupies the centre.
    """
    rgb = img.convert("RGB")
    small = rgb.copy()
    small.thumbnail((256, 256), Image.Resampling.BILINEAR)
    q = small.quantize(colors=max(2, palette_size), method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette() or []
    counts = q.getcolors(palette_size) or []
    if not counts:
        return "#000000"
    counts.sort(reverse=True)
    # Skip near-black/near-white if a more vivid colour is available in the top-n.
    candidates = counts[:max(1, n_colors)]
    for count, idx in candidates:
        r, g, b = pal[idx * 3:idx * 3 + 3]
        # Reject extremes; fall through to the next candidate if any.
        if 8 < (r + g + b) / 3 < 247:
            return f"#{r:02X}{g:02X}{b:02X}"
    count, idx = counts[0]
    r, g, b = pal[idx * 3:idx * 3 + 3]
    return f"#{r:02X}{g:02X}{b:02X}"


def smart_fit_for(image_size: tuple[int, int], target_size: tuple[int, int], tolerance: float = 0.08) -> str:
    """Choose a fit mode based on aspect-ratio match.

    Returns ``"cover"`` when the source and target aspect ratios are within
    `tolerance` of each other (cropping is minimal), otherwise ``"fill"`` so
    nothing is cut off. Use this when a row should auto-pick a sensible fit.
    """
    iw, ih = image_size
    tw, th = target_size
    if iw <= 0 or ih <= 0 or tw <= 0 or th <= 0:
        return "fill"
    src = iw / ih
    dst = tw / th
    if abs(src - dst) / max(src, dst) <= tolerance:
        return "cover"
    return "fill"


def sample_edge_color(img: Image.Image, border_px: int = 8) -> str:
    """Median colour along the image's outer border, as `#RRGGBB`.

    Useful as an auto background for letterbox bars so the bars blend into the
    photograph instead of standing out as black.
    """
    rgb = img.convert("RGB")
    w, h = rgb.size
    bp = max(1, min(border_px, w // 4, h // 4))
    strips = [
        rgb.crop((0, 0, w, bp)),
        rgb.crop((0, h - bp, w, h)),
        rgb.crop((0, 0, bp, h)),
        rgb.crop((w - bp, 0, w, h)),
    ]
    pixels: list[tuple[int, int, int]] = []
    for s in strips:
        s.thumbnail((64, 64), Image.Resampling.BILINEAR)
        pixels.extend(list(s.getdata()))
    if not pixels:
        return "#000000"
    n = len(pixels)
    rs = sorted(p[0] for p in pixels)
    gs = sorted(p[1] for p in pixels)
    bs = sorted(p[2] for p in pixels)
    return f"#{rs[n // 2]:02X}{gs[n // 2]:02X}{bs[n // 2]:02X}"


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except (ValueError, IndexError):
        return (0, 0, 0)


# ── Geometry steps ────────────────────────────────────────────────────────────

def _apply_rotate(img: Image.Image, deg: float, bg_hex: str) -> Image.Image:
    if abs(deg) < 0.01:
        return img
    bg = _hex_to_rgb(bg_hex)
    return img.rotate(
        -deg,  # PIL rotates counter-clockwise; users expect "+ = clockwise"
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor=bg,
    )


def _apply_crop(img: Image.Image, top: float, left: float, bottom: float, right: float) -> Image.Image:
    if top <= 0 and left <= 0 and bottom <= 0 and right <= 0:
        return img
    w, h = img.size
    # Clamp each side to <0.49 so they never collapse the image.
    top = max(0.0, min(0.49, top))
    left = max(0.0, min(0.49, left))
    bottom = max(0.0, min(0.49, bottom))
    right = max(0.0, min(0.49, right))
    x0 = int(round(w * left))
    y0 = int(round(h * top))
    x1 = w - int(round(w * right))
    y1 = h - int(round(h * bottom))
    if x1 <= x0 or y1 <= y0:
        return img
    return img.crop((x0, y0, x1, y1))


def _apply_flip(img: Image.Image, flip_h: bool, flip_v: bool) -> Image.Image:
    if flip_h:
        img = ImageOps.mirror(img)
    if flip_v:
        img = ImageOps.flip(img)
    return img


def _apply_fit(img: Image.Image, opts: FitOptions) -> Image.Image:
    tw, th = max(1, opts.target_w), max(1, opts.target_h)
    bg = _hex_to_rgb(opts.bg_color)
    mode = opts.mode

    if mode == "stretch":
        return img.resize((tw, th), Image.Resampling.LANCZOS).convert("RGB")

    if mode == "center":
        canvas = Image.new("RGB", (tw, th), bg)
        x = (tw - img.width) // 2
        y = (th - img.height) // 2
        if img.mode == "RGBA":
            canvas.paste(img.convert("RGB"), (x, y), img.split()[-1])
        else:
            canvas.paste(img.convert("RGB"), (x, y))
        return canvas

    iw, ih = img.size
    src_ratio = iw / ih
    dst_ratio = tw / th

    if mode == "cover":
        if src_ratio > dst_ratio:
            new_h = th
            new_w = int(round(th * src_ratio))
        else:
            new_w = tw
            new_h = int(round(tw / src_ratio))
        scaled = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        x = (new_w - tw) // 2
        y = (new_h - th) // 2
        return scaled.crop((x, y, x + tw, y + th)).convert("RGB")

    # fill (letterbox)
    if src_ratio > dst_ratio:
        new_w = tw
        new_h = int(round(tw / src_ratio))
    else:
        new_h = th
        new_w = int(round(th * src_ratio))
    scaled = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (tw, th), bg)
    x = (tw - new_w) // 2
    y = (th - new_h) // 2
    if scaled.mode == "RGBA":
        canvas.paste(scaled.convert("RGB"), (x, y), scaled.split()[-1])
    else:
        canvas.paste(scaled, (x, y))
    return canvas


# ── Color steps ───────────────────────────────────────────────────────────────

def _apply_hue_shift(img: Image.Image, degrees: int) -> Image.Image:
    if degrees == 0:
        return img
    hsv = img.convert("HSV")
    h, s, v = hsv.split()
    shift = int((degrees % 360) * 255 / 360)
    h = h.point(lambda p: (p + shift) % 256)
    return Image.merge("HSV", (h, s, v)).convert("RGB")


def _apply_shadow_highlight(img: Image.Image, shadows: float, highlights: float) -> Image.Image:
    if shadows == 0.0 and highlights == 0.0:
        return img
    lut = []
    for i in range(256):
        p = i / 255.0
        shadow_w = (1.0 - p) ** 2
        high_w   = p ** 2
        adj = shadows * 80 * shadow_w + highlights * 80 * high_w
        v = max(0, min(255, int(round(i + adj))))
        lut.append(v)
    full_lut = lut * len(img.getbands())
    return img.point(full_lut)


def _apply_temperature_tint(img: Image.Image, temperature: int, tint: int) -> Image.Image:
    """temperature: -100..100 (cool/blue → warm/red). tint: -100..100 (green→magenta)."""
    if temperature == 0 and tint == 0:
        return img
    img = img.convert("RGB")
    r, g, b = img.split()
    t = temperature * 0.30   # gentle shift
    n = tint * 0.30
    if temperature != 0:
        r = r.point(lambda p, t=t: max(0, min(255, int(p + t))))
        b = b.point(lambda p, t=t: max(0, min(255, int(p - t))))
    if tint != 0:
        # Positive tint → magenta (pull green down). Negative → green (push green up).
        g = g.point(lambda p, n=n: max(0, min(255, int(p - n))))
    return Image.merge("RGB", (r, g, b))


def _apply_levels(img: Image.Image, black_point: int, white_point: int) -> Image.Image:
    """Linear stretch [bp%..wp%] → [0..255]."""
    if black_point <= 0 and white_point >= 100:
        return img
    bp = max(0, min(50, black_point)) * 2.55
    wp = max(50, min(100, white_point)) * 2.55
    if wp <= bp + 1:
        return img
    scale = 255.0 / (wp - bp)
    lut = []
    for i in range(256):
        v = (i - bp) * scale
        lut.append(max(0, min(255, int(round(v)))))
    full_lut = lut * len(img.getbands())
    return img.point(full_lut)


def _apply_adjusts(img: Image.Image, adj: dict) -> Image.Image:
    """Apply a dict with the same keys as BUILTIN_FILTERS values + optional bp/wp."""
    out = img
    b = adj.get("brightness", 1.0)
    if b != 1.0:
        out = ImageEnhance.Brightness(out).enhance(b)
    c = adj.get("contrast", 1.0)
    if c != 1.0:
        out = ImageEnhance.Contrast(out).enhance(c)
    s = adj.get("saturation", 1.0)
    if s != 1.0:
        out = ImageEnhance.Color(out).enhance(s)
    h = int(adj.get("hue", 0))
    if h != 0:
        out = _apply_hue_shift(out, h)
    sh = adj.get("shadows", 0.0)
    hi = adj.get("highlights", 0.0)
    if sh != 0.0 or hi != 0.0:
        out = _apply_shadow_highlight(out, sh, hi)
    t = int(adj.get("temperature", 0))
    n = int(adj.get("tint", 0))
    if t != 0 or n != 0:
        out = _apply_temperature_tint(out, t, n)
    bp = int(adj.get("black_point", 0))
    wp = int(adj.get("white_point", 100))
    if bp > 0 or wp < 100:
        out = _apply_levels(out, bp, wp)
    return out


def _blend(a: Image.Image, b: Image.Image, strength: float) -> Image.Image:
    s = max(0.0, min(1.0, strength))
    if s >= 0.999:
        return b
    if s <= 0.001:
        return a
    return Image.blend(a.convert("RGB"), b.convert("RGB"), s)


# ── Effects ───────────────────────────────────────────────────────────────────

def _apply_sharpen_blur(img: Image.Image, sharpen: float, blur: float) -> Image.Image:
    out = img
    if blur > 0:
        out = out.filter(ImageFilter.GaussianBlur(radius=float(blur)))
    if sharpen > 0:
        # ImageEnhance.Sharpness: 1.0 = original, 2.0 = +sharp, 0 = blurred.
        out = ImageEnhance.Sharpness(out).enhance(1.0 + float(sharpen))
    return out


def _apply_grain(img: Image.Image, amount: float) -> Image.Image:
    """Gray noise overlay. amount 0..1 → blend alpha 0..~0.35."""
    if amount <= 0.001:
        return img
    img = img.convert("RGB")
    w, h = img.size
    # os.urandom is fast and cryptographically uniform — good enough as white noise.
    noise = Image.frombytes("L", (w, h), os.urandom(w * h)).convert("RGB")
    alpha = max(0.0, min(1.0, amount)) * 0.35
    return Image.blend(img, noise, alpha)


def _apply_gradient_overlay(img: Image.Image, amount: float, color1: str, color2: str, angle: int) -> Image.Image:
    """Linear gradient between two hex colours, blended at `amount` (0..1)."""
    if amount <= 0.001:
        return img
    import math
    img = img.convert("RGB")
    w, h = img.size
    c1 = _hex_to_rgb(color1)
    c2 = _hex_to_rgb(color2)
    # Project each pixel onto the gradient axis and look up linearly.
    a = math.radians(angle % 360)
    dx, dy = math.cos(a), math.sin(a)
    # Pre-compute the projection extents so the ramp covers the image edge-to-edge.
    proj_min = min(0 * dx + 0 * dy, w * dx + 0 * dy, 0 * dx + h * dy, w * dx + h * dy)
    proj_max = max(0 * dx + 0 * dy, w * dx + 0 * dy, 0 * dx + h * dy, w * dx + h * dy)
    span = max(1.0, proj_max - proj_min)
    # Build the gradient on a downscaled canvas then upsample — keeps it fast.
    sw, sh = max(64, w // 4), max(64, h // 4)
    grad = Image.new("RGB", (sw, sh))
    px = grad.load()
    sx = w / sw
    sy = h / sh
    for y in range(sh):
        for x in range(sw):
            t = ((x * sx) * dx + (y * sy) * dy - proj_min) / span
            t = max(0.0, min(1.0, t))
            r = int(c1[0] + (c2[0] - c1[0]) * t)
            g = int(c1[1] + (c2[1] - c1[1]) * t)
            b = int(c1[2] + (c2[2] - c1[2]) * t)
            px[x, y] = (r, g, b)
    grad = grad.resize((w, h), Image.Resampling.BILINEAR)
    return Image.blend(img, grad, max(0.0, min(1.0, amount)))


def _apply_duotone(img: Image.Image, amount: float, dark_hex: str, light_hex: str) -> Image.Image:
    """Map luminance to a two-colour ramp, blended at `amount`."""
    if amount <= 0.001:
        return img
    img = img.convert("RGB")
    luma = img.convert("L")
    d = _hex_to_rgb(dark_hex)
    l = _hex_to_rgb(light_hex)
    # Build a 256-entry LUT per channel.
    lut_r = [int(d[0] + (l[0] - d[0]) * i / 255) for i in range(256)]
    lut_g = [int(d[1] + (l[1] - d[1]) * i / 255) for i in range(256)]
    lut_b = [int(d[2] + (l[2] - d[2]) * i / 255) for i in range(256)]
    r = luma.point(lut_r)
    g = luma.point(lut_g)
    b = luma.point(lut_b)
    duo = Image.merge("RGB", (r, g, b))
    return Image.blend(img, duo, max(0.0, min(1.0, amount)))


def _apply_glass_blur(img: Image.Image, amount: float, radius: float) -> Image.Image:
    """Frosted-glass effect: a heavily blurred copy blended over the original."""
    if amount <= 0.001 or radius <= 0:
        return img
    img = img.convert("RGB")
    glass = img.filter(ImageFilter.GaussianBlur(radius=float(radius)))
    return Image.blend(img, glass, max(0.0, min(1.0, amount)))


def _apply_vignette(img: Image.Image, amount: float) -> Image.Image:
    """Radial darkening from the corners. amount 0..1."""
    if amount <= 0.001:
        return img
    img = img.convert("RGB")
    w, h = img.size
    # Build a radial luminance mask once: 255 in centre → ~darken_min at corners.
    # Use a small mask then upscale — much cheaper than per-pixel math.
    mw, mh = 256, max(1, int(round(256 * h / w)))
    mask = Image.new("L", (mw, mh), 0)
    draw = ImageDraw.Draw(mask)
    cx, cy = mw / 2, mh / 2
    rmax = (cx ** 2 + cy ** 2) ** 0.5
    # Draw concentric ellipses from outside in, ramping value up.
    steps = 32
    for i in range(steps, 0, -1):
        r = rmax * (i / steps)
        # Falloff curve: brighter centre, deeper edges.
        v = int(255 * (1.0 - (i / steps) ** 2))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=v)
    mask = mask.resize((w, h), Image.Resampling.BILINEAR)
    # Build a black overlay at the inverse-mask alpha.
    overlay = Image.new("RGB", (w, h), (0, 0, 0))
    inv = ImageChops.invert(mask)
    inv = inv.point(lambda p, a=amount: int(p * a * 0.75))
    img.paste(overlay, (0, 0), inv)
    return img


# ── Public pipeline ───────────────────────────────────────────────────────────

def apply_edits(img: Image.Image, cfg: EditConfig) -> Image.Image:
    """Full pipeline. Returns RGB image."""
    out = img
    if out.mode not in ("RGB", "RGBA"):
        out = out.convert("RGBA" if "A" in out.getbands() else "RGB")
    out = _apply_rotate(out, cfg.fit.rotate_deg, cfg.fit.bg_color)
    out = _apply_crop(
        out,
        cfg.fit.crop_top, cfg.fit.crop_left,
        cfg.fit.crop_bottom, cfg.fit.crop_right,
    )
    out = _apply_flip(out, cfg.fit.flip_h, cfg.fit.flip_v)
    out = _apply_fit(out, cfg.fit)

    pre_filter = out
    if cfg.adjust.enabled:
        adj_dict = {
            "brightness": cfg.adjust.brightness,
            "contrast":   cfg.adjust.contrast,
            "saturation": cfg.adjust.saturation,
            "hue":        cfg.adjust.hue,
            "shadows":    cfg.adjust.shadows,
            "highlights": cfg.adjust.highlights,
            "temperature": cfg.adjust.temperature,
            "tint":       cfg.adjust.tint,
            "black_point": cfg.adjust.black_point,
            "white_point": cfg.adjust.white_point,
        }
        pre_filter = _apply_adjusts(out, adj_dict)

    preset = BUILTIN_FILTERS.get(cfg.filter.preset, BUILTIN_FILTERS["none"])
    if cfg.filter.preset == "none":
        post_filter = pre_filter
    else:
        filtered = _apply_adjusts(pre_filter, preset)
        post_filter = _blend(pre_filter, filtered, cfg.filter.strength)

    # Effects last — never wet/dry blended.
    eff = cfg.effects
    post_filter = _apply_sharpen_blur(post_filter, eff.sharpen, eff.blur)
    post_filter = _apply_glass_blur(post_filter, eff.glass_blur, eff.glass_blur_radius)
    post_filter = _apply_duotone(post_filter, eff.duotone_amount, eff.duotone_dark, eff.duotone_light)
    post_filter = _apply_gradient_overlay(
        post_filter, eff.gradient_amount, eff.gradient_color1, eff.gradient_color2, eff.gradient_angle,
    )
    post_filter = _apply_grain(post_filter, eff.grain)
    post_filter = _apply_vignette(post_filter, eff.vignette)
    return post_filter


def process_image(in_path: str, out_path: str, cfg: EditConfig, quality: int = 92) -> str:
    with Image.open(in_path) as im:
        im.load()
        result = apply_edits(im, cfg)
    ext = os.path.splitext(out_path)[1].lower()
    save_kwargs: dict = {}
    if ext in (".jpg", ".jpeg"):
        save_kwargs["quality"] = quality
        save_kwargs["optimize"] = True
        result = result.convert("RGB")
    elif ext == ".webp":
        save_kwargs["quality"] = quality
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    result.save(out_path, **save_kwargs)
    return out_path


def process_batch(
    paths: list[str],
    out_dir: Optional[str],
    cfg: EditConfig,
    suffix: str = "_edited",
    progress_cb: Optional[Callable[[int, int], None]] = None,
    cancel_cb: Optional[Callable[[], bool]] = None,
) -> dict[str, bool]:
    results: dict[str, bool] = {}
    total = len(paths)
    for i, p in enumerate(paths, 1):
        if cancel_cb and cancel_cb():
            break
        try:
            base = os.path.splitext(os.path.basename(p))[0]
            ext = os.path.splitext(p)[1] or ".png"
            tgt_dir = out_dir or os.path.dirname(p) or "."
            out = os.path.join(tgt_dir, f"{base}{suffix}{ext}")
            process_image(p, out, cfg)
            results[p] = True
        except Exception:
            results[p] = False
        if progress_cb:
            progress_cb(i, total)
    return results


# ── Preset storage ────────────────────────────────────────────────────────────

def _presets_file() -> str:
    return str(user_config_dir() / "image_presets.json")


def load_user_presets() -> dict[str, dict]:
    path = _presets_file()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_user_preset(name: str, cfg: EditConfig) -> None:
    name = name.strip()
    if not name:
        raise ValueError("Preset name cannot be empty.")
    presets = load_user_presets()
    presets[name] = {
        "fit":     asdict(cfg.fit),
        "filter":  asdict(cfg.filter),
        "adjust":  asdict(cfg.adjust),
        "effects": asdict(cfg.effects),
    }
    path = _presets_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(presets, f, indent=2)


def delete_user_preset(name: str) -> bool:
    presets = load_user_presets()
    if name not in presets:
        return False
    del presets[name]
    path = _presets_file()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(presets, f, indent=2)
    return True


def _coerce(cls, blob: dict, default):
    """Build a dataclass instance from blob, falling back to default for missing fields.

    Tolerates older preset files that don't carry the newer fields (rotate_deg,
    crop_*, temperature, tint, black_point, white_point, effects, ...).
    """
    out = cls()
    fields = out.__dataclass_fields__
    for k in fields:
        if k in blob:
            setattr(out, k, blob[k])
        else:
            setattr(out, k, getattr(default, k))
    return out


# ── Multi-monitor wallpaper export ────────────────────────────────────────────

@dataclass
class MonitorSpec:
    """One target monitor for wallpaper export.

    Coordinates (x, y) are the monitor's top-left in the combined desktop, in
    pixels. Used only for the spanned composite; per-monitor export ignores it.

    `source_path` lets each monitor use a different image (Wallpaper-Engine
    style). When None / empty, the fallback source (the main editor image) is
    used. The colour grade from `base_cfg` still applies regardless of source.
    """
    label: str = "Monitor 1"
    width: int = 1920
    height: int = 1080
    x: int = 0
    y: int = 0
    fit_mode: str = "fill"  # default = no crop (letterbox); Wallpaper-Engine "Scale and Fit"
    flip_h: bool = False
    flip_v: bool = False
    rotate_deg: float = 0.0
    bg_color: str = "#000000"
    source_path: Optional[str] = None
    # Windows IDesktopWallpaper device path. Set at Detect time so wallpaper
    # apply targets a specific physical monitor regardless of row order/deletion.
    monitor_id: Optional[str] = None
    # Optional per-monitor full edit config (filter / adjust / effects / crop).
    # When None, render falls back to the caller-supplied base_cfg — same colour
    # grade as the global editor. Set this when a monitor wants a different look.
    edit_cfg: Optional["EditConfig"] = None
    # Slideshow: when use_slideshow=True, Apply hands `slideshow_folder` to
    # `IDesktopWallpaper.SetSlideshow` and ignores source_path/exported image.
    use_slideshow: bool = False
    slideshow_folder: Optional[str] = None
    slideshow_interval_minutes: int = 30


def _render_one_monitor(
    src: Image.Image,
    spec: MonitorSpec,
    base_cfg: EditConfig,
) -> Image.Image:
    """Render `src` for a single monitor.

    Per-monitor geometry (width/height/fit/flip/rotate/bg) always comes from
    `spec`. Crop/filter/adjust/effects come from `spec.edit_cfg` when set
    (per-monitor override) — otherwise from `base_cfg` (global editor state).
    """
    chosen = spec.edit_cfg if spec.edit_cfg is not None else base_cfg
    cfg = EditConfig(
        fit=FitOptions(
            target_w=max(1, spec.width),
            target_h=max(1, spec.height),
            mode=spec.fit_mode,
            bg_color=spec.bg_color,
            flip_h=spec.flip_h,
            flip_v=spec.flip_v,
            rotate_deg=spec.rotate_deg,
            crop_top=chosen.fit.crop_top,
            crop_left=chosen.fit.crop_left,
            crop_bottom=chosen.fit.crop_bottom,
            crop_right=chosen.fit.crop_right,
        ),
        filter=FilterOptions(
            preset=chosen.filter.preset,
            strength=chosen.filter.strength,
        ),
        adjust=AdjustOptions(**asdict(chosen.adjust)),
        effects=EffectsOptions(**asdict(chosen.effects)),
    )
    return apply_edits(src, cfg)


def _resolve_source(
    spec: MonitorSpec,
    fallback: Optional[Image.Image],
    cache: dict[str, Image.Image],
) -> Image.Image:
    """Open spec.source_path (cached) or return the fallback main-image."""
    path = (spec.source_path or "").strip()
    if path and os.path.isfile(path):
        if path not in cache:
            with Image.open(path) as im:
                im.load()
                cache[path] = im.copy()
        return cache[path]
    if fallback is None:
        raise ValueError(
            f"Monitor '{spec.label}' has no source image and no fallback was provided."
        )
    return fallback


def render_multi_monitor(
    src: Optional[Image.Image],
    specs: list[MonitorSpec],
    base_cfg: EditConfig,
) -> list[tuple[MonitorSpec, Image.Image]]:
    """Render each monitor, resolving per-spec source overrides against `src`."""
    cache: dict[str, Image.Image] = {}
    return [
        (s, _render_one_monitor(_resolve_source(s, src, cache), s, base_cfg))
        for s in specs
    ]


def render_spanned(
    src: Optional[Image.Image],
    specs: list[MonitorSpec],
    base_cfg: EditConfig,
    gap_color: str = "#000000",
) -> Image.Image:
    """Composite per-monitor renders into one canvas matching the desktop bounding box.

    Each monitor is placed at its (x, y) — supports gaps and offset arrangements.
    Per-spec source overrides honoured: each monitor can show a different image.
    """
    if not specs:
        raise ValueError("No monitors specified.")
    min_x = min(s.x for s in specs)
    min_y = min(s.y for s in specs)
    max_x = max(s.x + s.width for s in specs)
    max_y = max(s.y + s.height for s in specs)
    total_w = max_x - min_x
    total_h = max_y - min_y
    canvas = Image.new("RGB", (total_w, total_h), _hex_to_rgb(gap_color))
    cache: dict[str, Image.Image] = {}
    for spec in specs:
        source = _resolve_source(spec, src, cache)
        rendered = _render_one_monitor(source, spec, base_cfg)
        canvas.paste(rendered, (spec.x - min_x, spec.y - min_y))
    return canvas


def export_wallpapers(
    src_path: Optional[str],
    specs: list[MonitorSpec],
    base_cfg: EditConfig,
    out_dir: str,
    base_name: str,
    do_per_monitor: bool = True,
    do_spanned: bool = True,
    quality: int = 92,
) -> dict[str, str]:
    """Render and save wallpaper files. Returns {label: saved_path}.

    `src_path` is the *fallback* source — monitor rows without their own
    `source_path` use it. Saves PNGs (lossless) since wallpapers are full-screen.
    Raises ValueError if any spec has no source AND no fallback was provided.
    """
    if not specs:
        raise ValueError("No monitors specified.")
    os.makedirs(out_dir, exist_ok=True)
    out: dict[str, str] = {}

    fallback: Optional[Image.Image] = None
    if src_path and os.path.isfile(src_path):
        with Image.open(src_path) as im:
            im.load()
            fallback = im.copy()

    # Validate: every spec must resolve to *some* source.
    for s in specs:
        path = (s.source_path or "").strip()
        if not (path and os.path.isfile(path)) and fallback is None:
            raise ValueError(
                f"Monitor '{s.label}' has no source image — pick one for the row or load a main image."
            )

    if do_per_monitor:
        for spec, img in render_multi_monitor(fallback, specs, base_cfg):
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in spec.label) or "monitor"
            fname = f"{base_name}_{safe}_{spec.width}x{spec.height}.png"
            path = os.path.join(out_dir, fname)
            img.save(path)
            out[spec.label] = path
    if do_spanned:
        spanned = render_spanned(fallback, specs, base_cfg)
        sw, sh = spanned.size
        fname = f"{base_name}_spanned_{sw}x{sh}.png"
        path = os.path.join(out_dir, fname)
        spanned.save(path)
        out["__spanned__"] = path
    return out


def preset_to_config(blob: dict) -> EditConfig:
    cfg = EditConfig()
    if "fit" in blob:
        cfg.fit = _coerce(FitOptions, blob["fit"], cfg.fit)
    if "filter" in blob:
        cfg.filter = _coerce(FilterOptions, blob["filter"], cfg.filter)
    if "adjust" in blob:
        cfg.adjust = _coerce(AdjustOptions, blob["adjust"], cfg.adjust)
    if "effects" in blob:
        cfg.effects = _coerce(EffectsOptions, blob["effects"], cfg.effects)
    return cfg
