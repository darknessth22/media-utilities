"""Image editor — fit/alignment, flip/rotate/crop, filter presets, color grading,
post effects (sharpen/blur/grain/vignette), user presets, aspect-ratio presets.

Pure Pillow pipeline. No new deps.

Pipeline order:
    1. Free-rotate (degrees, expand canvas)
    2. Percent crop (top/left/bottom/right)
    3. Flip (H/V)
    4. Fit into target canvas (cover/fill/center/stretch) + bg color
    5. Enhance tools (denoise, auto-enhance, exposure/gamma, dehaze, vibrance,
       clarity, unsharp mask) — Photoshop-style enhancing pass
    6. Color adjustments (brightness/contrast/saturation/hue/shadows/highlights
       + temperature/tint + black-point/white-point) then the master tone curve
    7. Filter preset, strength-blended against the un-filtered post-adjust image
    8. Local-adjustment masks (radial / linear / color-range), composited in order
    9. Post effects (sharpen/blur, grain, vignette)

Presets stored at  user_config_dir()/image_presets.json.
"""
from __future__ import annotations

import json
import os
import random
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
class EnhanceOptions:
    """Photoshop-style enhancing pass. All sliders default to a no-op."""
    auto_enhance: bool = False     # one-click per-channel autocontrast (white balance + contrast)
    clarity: float = 0.0           # 0..1    midtone local-contrast punch
    dehaze: float = 0.0            # 0..1    haze removal — contrast/saturation lift
    vibrance: float = 0.0          # -1..1   smart saturation; protects already-saturated pixels
    exposure: float = 0.0          # -2..2   stops (multiplies linear light by 2**exposure)
    gamma: float = 1.0             # 0.2..3.0  midtone gamma (>1 brightens)
    denoise: float = 0.0           # 0..1    median/smooth noise reduction
    sharpen_amount: float = 0.0    # 0..3    unsharp-mask amount
    sharpen_radius: float = 2.0    # 0.5..20 unsharp-mask radius (px)
    sharpen_threshold: int = 3     # 0..20   unsharp-mask threshold


@dataclass
class CurvesOptions:
    """Master tone curve. `points` are (x, y) control points in 0..255, sorted
    by x; the default identity line is a no-op."""
    enabled: bool = False
    points: list = field(default_factory=lambda: [[0, 0], [255, 255]])


MASK_TYPES = ("radial", "linear", "color")


@dataclass
class MaskAdjust:
    """Per-mask local adjustments. All channels default to a no-op."""
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    hue: int = 0
    temperature: int = 0
    tint: int = 0
    exposure: float = 0.0     # -2..2 stops
    shadows: float = 0.0      # -1..1
    highlights: float = 0.0   # -1..1


@dataclass
class MaskLayer:
    """One local-adjustment mask. Geometry is stored as fractions (0..1) of the
    canvas so a mask survives a target W×H change.

    radial — feathered ellipse centred at (cx, cy) with radii (rx, ry).
    linear — graduated ramp from point A (x0, y0) to point B (x1, y1).
    color  — selects pixels near `pick_color` within `tolerance` (sky, grass…).
    """
    mask_type: str = "radial"
    invert: bool = False
    feather: float = 0.5      # 0..1 edge softness
    # Radial geometry
    cx: float = 0.5
    cy: float = 0.5
    rx: float = 0.3
    ry: float = 0.3
    # Linear geometry
    x0: float = 0.5
    y0: float = 0.0
    x1: float = 0.5
    y1: float = 1.0
    # Color-range geometry
    pick_color: str = "#808080"
    tolerance: float = 0.12   # 0..1 — radius of colour fully selected (kept tight on purpose)
    adjust: MaskAdjust = field(default_factory=MaskAdjust)


@dataclass
class EditConfig:
    fit: FitOptions = field(default_factory=FitOptions)
    enhance: EnhanceOptions = field(default_factory=EnhanceOptions)
    filter: FilterOptions = field(default_factory=FilterOptions)
    adjust: AdjustOptions = field(default_factory=AdjustOptions)
    curves: CurvesOptions = field(default_factory=CurvesOptions)
    effects: EffectsOptions = field(default_factory=EffectsOptions)
    masks: list[MaskLayer] = field(default_factory=list)


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


def load_image(path: str) -> Image.Image:
    """Open an image, apply its EXIF orientation, return a detached copy.

    Phone cameras store the photo sideways plus an orientation tag; opening with
    plain `Image.open` ignores the tag and the image loads rotated. Always route
    editable-image loads through here.
    """
    with Image.open(path) as im:
        im.load()
        fixed = ImageOps.exif_transpose(im)
        return (fixed if fixed is not None else im).copy()


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


def _build_curve_lut(points: list) -> list[int]:
    """Piecewise-linear 256-entry LUT from (x, y) control points (0..255)."""
    pts = sorted(
        (max(0, min(255, int(p[0]))), max(0, min(255, int(p[1]))))
        for p in points if len(p) >= 2
    )
    if not pts:
        return list(range(256))
    # Anchor the ends so every input 0..255 is covered.
    if pts[0][0] != 0:
        pts.insert(0, (0, pts[0][1]))
    if pts[-1][0] != 255:
        pts.append((255, pts[-1][1]))
    lut: list[int] = []
    j = 0
    for i in range(256):
        while j < len(pts) - 2 and pts[j + 1][0] < i:
            j += 1
        x0, y0 = pts[j]
        x1, y1 = pts[j + 1]
        v = y1 if x1 == x0 else y0 + (y1 - y0) * (i - x0) / (x1 - x0)
        lut.append(max(0, min(255, int(round(v)))))
    return lut


def _apply_curves(img: Image.Image, curves: "CurvesOptions") -> Image.Image:
    """Apply the master tone curve to every channel."""
    if not curves.enabled:
        return img
    lut = _build_curve_lut(curves.points)
    if lut == list(range(256)):
        return img
    return img.point(lut * len(img.getbands()))


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


# ── Enhance tools (Photoshop-style enhancing pass) ────────────────────────────

def _apply_auto_enhance(img: Image.Image) -> Image.Image:
    """One-click fix: stretch each RGB channel independently.

    Per-channel autocontrast removes a colour cast (white balance) AND expands
    the tonal range (contrast) in a single cheap pass — the classic "auto" fix.
    """
    return ImageOps.autocontrast(img.convert("RGB"), cutoff=1)


def _apply_exposure_gamma(img: Image.Image, exposure: float, gamma: float) -> Image.Image:
    """Exposure in stops (×2**exposure) then a midtone gamma curve."""
    if abs(exposure) < 0.001 and abs(gamma - 1.0) < 0.001:
        return img
    mult = 2.0 ** float(exposure)
    inv_g = 1.0 / max(0.01, float(gamma))
    lut = []
    for i in range(256):
        v = (i / 255.0) * mult
        v = max(0.0, min(1.0, v)) ** inv_g
        lut.append(max(0, min(255, int(round(v * 255)))))
    return img.point(lut * len(img.getbands()))


def _apply_dehaze(img: Image.Image, amount: float) -> Image.Image:
    """Lift haze: punch contrast + saturation and deepen blacks. amount 0..1."""
    if amount <= 0.001:
        return img
    a = max(0.0, min(1.0, amount))
    img = img.convert("RGB")
    out = ImageEnhance.Contrast(img).enhance(1.0 + 0.55 * a)
    out = ImageEnhance.Color(out).enhance(1.0 + 0.45 * a)
    out = ImageEnhance.Brightness(out).enhance(1.0 - 0.06 * a)
    bp = int(round(8 * a))
    if bp > 0:
        out = _apply_levels(out, bp, 100)
    return out


def _apply_vibrance(img: Image.Image, amount: float) -> Image.Image:
    """Smart saturation: boosts low-saturation pixels most, protects vivid ones.

    amount -1..1. Negative desaturates. Unlike a flat saturation multiply, the
    gain is weighted by (255 - s) so already-saturated colours (skin, skies)
    don't clip.
    """
    if abs(amount) <= 0.001:
        return img
    a = max(-1.0, min(1.0, amount))
    hsv = img.convert("HSV")
    h, s, v = hsv.split()

    def _f(p: int, a: float = a) -> int:
        gain = a * (255 - p) / 255.0
        return max(0, min(255, int(p + p * gain)))

    s = s.point(_f)
    return Image.merge("HSV", (h, s, v)).convert("RGB")


def _apply_clarity(img: Image.Image, amount: float) -> Image.Image:
    """Local-contrast 'clarity' — a large-radius unsharp mask. amount 0..1."""
    if amount <= 0.001:
        return img
    img = img.convert("RGB")
    w, h = img.size
    radius = max(3, min(w, h) // 40)
    percent = int(max(0.0, min(1.0, amount)) * 110)
    return img.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=0))


def _apply_denoise(img: Image.Image, amount: float) -> Image.Image:
    """Noise reduction: a 3×3 median (plus a light blur at high amounts), blended."""
    if amount <= 0.001:
        return img
    a = max(0.0, min(1.0, amount))
    img = img.convert("RGB")
    den = img.filter(ImageFilter.MedianFilter(size=3))
    if a > 0.5:
        den = den.filter(ImageFilter.GaussianBlur(radius=(a - 0.5) * 1.6))
    return Image.blend(img, den, a)


def _apply_unsharp(img: Image.Image, amount: float, radius: float, threshold: int) -> Image.Image:
    """Real unsharp-mask sharpen with radius / amount / threshold control."""
    if amount <= 0.001:
        return img
    return img.filter(ImageFilter.UnsharpMask(
        radius=max(0.1, float(radius)),
        percent=int(max(0.0, min(3.0, amount)) * 100),
        threshold=int(max(0, threshold)),
    ))


def _apply_enhance(img: Image.Image, enh: "EnhanceOptions") -> Image.Image:
    """Run the enhancing pass. Order: clean → tone → colour → detail."""
    out = img.convert("RGB")
    if enh.denoise > 0:
        out = _apply_denoise(out, enh.denoise)
    if enh.auto_enhance:
        out = _apply_auto_enhance(out)
    if enh.exposure != 0.0 or abs(enh.gamma - 1.0) > 0.001:
        out = _apply_exposure_gamma(out, enh.exposure, enh.gamma)
    if enh.dehaze > 0:
        out = _apply_dehaze(out, enh.dehaze)
    if enh.vibrance != 0.0:
        out = _apply_vibrance(out, enh.vibrance)
    if enh.clarity > 0:
        out = _apply_clarity(out, enh.clarity)
    if enh.sharpen_amount > 0:
        out = _apply_unsharp(out, enh.sharpen_amount, enh.sharpen_radius, enh.sharpen_threshold)
    return out


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
    """Gray noise overlay. amount 0..1 → blend alpha 0..~0.35.

    Uses a fixed-seed RNG so the grain is deterministic — the preview and the
    exported file (and repeated renders) get the identical noise pattern.
    """
    if amount <= 0.001:
        return img
    img = img.convert("RGB")
    w, h = img.size
    noise = Image.frombytes("L", (w, h), random.Random(0x5EED).randbytes(w * h)).convert("RGB")
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


# ── Local-adjustment masks ────────────────────────────────────────────────────

def _build_radial_mask(size: tuple[int, int], layer: MaskLayer) -> Image.Image:
    """Feathered ellipse mask. 'L' image, 255 = full local effect."""
    w, h = size
    mask = Image.new("L", (w, h), 0)
    cx, cy = layer.cx * w, layer.cy * h
    rx = max(1.0, layer.rx * w)
    ry = max(1.0, layer.ry * h)
    ImageDraw.Draw(mask).ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255)
    # Feather softens the edge — blur radius scales with the smaller ellipse axis.
    feather_px = max(0.0, min(1.0, layer.feather)) * 0.6 * min(rx, ry)
    if feather_px > 0.5:
        mask = mask.filter(ImageFilter.GaussianBlur(feather_px))
    return mask


def _build_linear_mask(size: tuple[int, int], layer: MaskLayer) -> Image.Image:
    """Graduated ramp mask from point A→B. 'L' image, 255 = full local effect."""
    w, h = size
    ax, ay = layer.x0 * w, layer.y0 * h
    bx, by = layer.x1 * w, layer.y1 * h
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 < 1.0:
        return Image.new("L", (w, h), 255)
    # feather compresses the 0→1 ramp around its midpoint (0 = hard step).
    f = max(0.05, min(1.0, layer.feather))
    # Build on a downscaled canvas then upsample — keeps it fast.
    sw, sh = max(64, w // 4), max(64, h // 4)
    m = Image.new("L", (sw, sh))
    px = m.load()
    sx, sy = w / sw, h / sh
    for y in range(sh):
        for x in range(sw):
            t = ((x * sx - ax) * dx + (y * sy - ay) * dy) / length2
            t = (t - 0.5) / f + 0.5
            px[x, y] = max(0, min(255, int(t * 255)))
    return m.resize((w, h), Image.Resampling.BILINEAR)


def _build_color_mask(img: Image.Image, layer: MaskLayer) -> Image.Image:
    """Select pixels close to `layer.pick_color`. 'L' mask, 255 = full effect.

    Distance is the **largest** per-channel absolute difference — a pixel matches
    only when red AND green AND blue are all near the target, so a colour that
    differs strongly in just one channel (e.g. blue) is correctly rejected.

    `tolerance` is the radius that is *fully* selected (255). `feather` only adds
    a soft fall-off **beyond** that radius — it never eats into the tolerance —
    so the selection stays tight and predictable. Cheap, no NumPy.
    """
    rgb = img.convert("RGB")
    target = _hex_to_rgb(layer.pick_color)
    d = ImageChops.difference(rgb, Image.new("RGB", rgb.size, target))
    r, g, b = d.split()
    diff = ImageChops.lighter(ImageChops.lighter(r, g), b)  # per-pixel max channel diff
    tol = max(2.0, min(1.0, layer.tolerance) * 255.0)       # fully-selected radius
    soft = max(1.0, min(1.0, layer.feather) * 64.0)         # ramp width past `tol`
    outer = tol + soft
    lut = []
    for i in range(256):
        if i <= tol:
            lut.append(255)
        elif i >= outer:
            lut.append(0)
        else:
            lut.append(int(round(255 * (1.0 - (i - tol) / soft))))
    return diff.point(lut).filter(ImageFilter.GaussianBlur(1.0))


def _apply_mask_adjust(img: Image.Image, adj: MaskAdjust) -> Image.Image:
    """Apply a mask's local adjustments to the whole image (caller composites)."""
    out = _apply_adjusts(img, {
        "brightness": adj.brightness,
        "contrast":   adj.contrast,
        "saturation": adj.saturation,
        "hue":        adj.hue,
        "shadows":    adj.shadows,
        "highlights": adj.highlights,
        "temperature": adj.temperature,
        "tint":       adj.tint,
    })
    if adj.exposure != 0.0:
        out = _apply_exposure_gamma(out, adj.exposure, 1.0)
    return out


def _apply_masks(img: Image.Image, masks: list[MaskLayer]) -> Image.Image:
    """Composite each mask's local adjustment over the image, in order."""
    if not masks:
        return img
    base = img.convert("RGB")
    for layer in masks:
        if layer.mask_type == "linear":
            mask = _build_linear_mask(base.size, layer)
        elif layer.mask_type == "color":
            mask = _build_color_mask(base, layer)
        else:
            mask = _build_radial_mask(base.size, layer)
        if layer.invert:
            mask = ImageChops.invert(mask)
        edited = _apply_mask_adjust(base, layer.adjust)
        base = Image.composite(edited, base, mask)
    return base


def clone_masks(masks: list[MaskLayer]) -> list[MaskLayer]:
    """Deep-copy a mask list (each MaskLayer carries a nested MaskAdjust)."""
    out: list[MaskLayer] = []
    for m in masks:
        nm = MaskLayer(**{k: getattr(m, k) for k in m.__dataclass_fields__ if k != "adjust"})
        nm.adjust = MaskAdjust(**asdict(m.adjust))
        out.append(nm)
    return out


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
    out = _apply_enhance(out, cfg.enhance)

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
    pre_filter = _apply_curves(pre_filter, cfg.curves)

    preset = BUILTIN_FILTERS.get(cfg.filter.preset, BUILTIN_FILTERS["none"])
    if cfg.filter.preset == "none":
        post_filter = pre_filter
    else:
        filtered = _apply_adjusts(pre_filter, preset)
        post_filter = _blend(pre_filter, filtered, cfg.filter.strength)

    # Local-adjustment masks — applied on top of the global grade.
    post_filter = _apply_masks(post_filter, cfg.masks)

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
    result = apply_edits(load_image(in_path), cfg)
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
        "enhance": asdict(cfg.enhance),
        "filter":  asdict(cfg.filter),
        "adjust":  asdict(cfg.adjust),
        "curves":  asdict(cfg.curves),
        "effects": asdict(cfg.effects),
        "masks":   [asdict(m) for m in cfg.masks],
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
        enhance=EnhanceOptions(**asdict(chosen.enhance)),
        filter=FilterOptions(
            preset=chosen.filter.preset,
            strength=chosen.filter.strength,
        ),
        adjust=AdjustOptions(**asdict(chosen.adjust)),
        curves=CurvesOptions(enabled=chosen.curves.enabled,
                             points=[list(p) for p in chosen.curves.points]),
        effects=EffectsOptions(**asdict(chosen.effects)),
        masks=clone_masks(chosen.masks),
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
            cache[path] = load_image(path)
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
        fallback = load_image(src_path)

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
    if "enhance" in blob:
        cfg.enhance = _coerce(EnhanceOptions, blob["enhance"], cfg.enhance)
    if "filter" in blob:
        cfg.filter = _coerce(FilterOptions, blob["filter"], cfg.filter)
    if "adjust" in blob:
        cfg.adjust = _coerce(AdjustOptions, blob["adjust"], cfg.adjust)
    if "curves" in blob and isinstance(blob["curves"], dict):
        cfg.curves = _coerce(CurvesOptions, blob["curves"], cfg.curves)
        if not isinstance(cfg.curves.points, list) or len(cfg.curves.points) < 2:
            cfg.curves.points = [[0, 0], [255, 255]]
    if "effects" in blob:
        cfg.effects = _coerce(EffectsOptions, blob["effects"], cfg.effects)
    if "masks" in blob and isinstance(blob["masks"], list):
        cfg.masks = []
        for mblob in blob["masks"]:
            if not isinstance(mblob, dict):
                continue
            ml = _coerce(MaskLayer, mblob, MaskLayer())
            # _coerce copies the raw 'adjust' dict — rebuild it as a MaskAdjust.
            if isinstance(mblob.get("adjust"), dict):
                ml.adjust = _coerce(MaskAdjust, mblob["adjust"], MaskAdjust())
            else:
                ml.adjust = MaskAdjust()
            cfg.masks.append(ml)
    return cfg
