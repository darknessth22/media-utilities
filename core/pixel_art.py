"""Turn images, GIFs and videos into pixel art.

Shrinking an image and blowing it back up gives a muddy, blocky photo, not
pixel art. What makes it read as pixel art is mostly the PALETTE — a handful
of flat colours — so the pipeline is:

    boost contrast/saturation -> downscale (box average) -> reduce colours
    (optionally dithered) -> upscale with nearest-neighbour (crisp squares)

For animation the palette is built ONCE from frames sampled across the whole
clip and shared by every frame. A palette per frame makes colours jump from
frame to frame — visible as flicker — which is the classic flaw of naive
"pixelate video" tools.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageEnhance, ImageOps, ImageSequence

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
GIF_EXTS = {".gif"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".wmv"}
ALL_EXTS = IMAGE_EXTS | GIF_EXTS | VIDEO_EXTS

DITHER_NONE = "none"
DITHER_FLOYD = "floyd"          # error diffusion: smooth gradients, a bit noisy
DITHER_ORDERED = "ordered"      # Bayer pattern: the classic retro crosshatch

# Fixed palettes from real hardware and well-known pixel-art palettes.
PALETTES: dict[str, list[str]] = {
    "gameboy": ["#0F380F", "#306230", "#8BAC0F", "#9BBC0F"],
    "pico8": ["#000000", "#1D2B53", "#7E2553", "#008751", "#AB5236", "#5F574F",
              "#C2C3C7", "#FFF1E8", "#FF004D", "#FFA300", "#FFEC27", "#00E436",
              "#29ADFF", "#83769C", "#FF77A8", "#FFCCAA"],
    "sweetie16": ["#1A1C2C", "#5D275D", "#B13E53", "#EF7D57", "#FFCD75", "#A7F070",
                  "#38B764", "#257179", "#29366F", "#3B5DC9", "#41A6F6", "#73EFF7",
                  "#F4F4F4", "#94B0C2", "#566C86", "#333C57"],
    "c64": ["#000000", "#FFFFFF", "#68372B", "#70A4B2", "#6F3D86", "#588D43",
            "#352879", "#B8C76F", "#6F4F25", "#433900", "#9A6759", "#444444",
            "#6C6C6C", "#9AD284", "#6C5EB5", "#959595"],
    "cga": ["#000000", "#55FFFF", "#FF55FF", "#FFFFFF"],
    "grayscale": ["#000000", "#555555", "#AAAAAA", "#FFFFFF"],
}
AUTO = "auto"           # build a palette from the image itself

# 4x4 Bayer threshold matrix, normalised to -0.5..0.5.
_BAYER = (np.array([[0, 8, 2, 10],
                    [12, 4, 14, 6],
                    [3, 11, 1, 9],
                    [15, 7, 13, 5]], dtype=np.float32) + 0.5) / 16.0 - 0.5


@dataclass
class PixelSettings:
    pixel_size: int = 8         # source pixels per output pixel
    palette: str = AUTO
    colors: int = 16            # for the AUTO palette
    dither: str = DITHER_NONE
    contrast: float = 1.1       # photos look washed out once colours are cut
    saturation: float = 1.2
    upscale: bool = True        # back to roughly the source size, crisp


# ── Palettes ──────────────────────────────────────────────────────────────────

# Palettes that are a light-to-dark ramp of one hue (a Game Boy screen, plain
# grey). Matching a colour photo to them by RGB distance is wrong: a dark red
# house and a blue sky land on nearly the same green and the picture vanishes.
# They are matched by BRIGHTNESS instead, which is what the hardware did.
RAMPS = frozenset({"gameboy", "grayscale"})


def _rgb(code: str) -> tuple[int, int, int]:
    code = code.lstrip("#")
    return tuple(int(code[i:i + 2], 16) for i in (0, 2, 4))


def _luma(code: str) -> int:
    r, g, b = _rgb(code)
    return int(round(0.299 * r + 0.587 * g + 0.114 * b))


def _palette_image(colours: list[tuple[int, int, int]]) -> Image.Image:
    """A "P" image carrying *colours* as its palette, for Image.quantize."""
    flat = [c for rgb in colours for c in rgb]
    # Pad to 256 entries by repeating the first colour: unused slots left at
    # black would otherwise be picked as a real colour.
    flat += list(colours[0]) * (256 - len(colours))
    img = Image.new("P", (1, 1))
    img.putpalette(flat)
    return img


def build_palette(samples: list[Image.Image], settings: PixelSettings) -> list[str]:
    """The palette every frame will share, as hex codes.

    For a preset that is the preset. For AUTO it is derived from all *samples*
    at once, so one palette fits the whole clip instead of each frame picking
    its own.
    """
    if settings.palette != AUTO:
        return list(PALETTES[settings.palette])

    prepared = [_prepare(s, settings)[0] for s in samples]
    width = sum(p.width for p in prepared)
    height = max(p.height for p in prepared)
    strip = Image.new("RGB", (width, height))
    x = 0
    for p in prepared:
        strip.paste(p, (x, 0))
        x += p.width
    count = max(2, min(256, int(settings.colors)))
    quant = strip.quantize(colors=count, method=Image.Quantize.MEDIANCUT,
                           dither=Image.Dither.NONE)
    raw = quant.getpalette()[: count * 3]
    used = sorted({color for _n, color in quant.getcolors(count) or []})
    return ["#%02X%02X%02X" % tuple(raw[i * 3:i * 3 + 3]) for i in used]


def _gap(levels: list[tuple[int, int, int]]) -> float:
    """Median distance from each palette colour to its nearest neighbour.

    That is how far apart two adjacent shades are, which is exactly how much
    ordered dithering should nudge a pixel: much less and the pattern never
    appears, much more and it drowns the picture.
    """
    if len(levels) < 2:
        return 0.0
    arr = np.array(levels, dtype=np.float32)
    dist = np.linalg.norm(arr[:, None, :] - arr[None, :, :], axis=-1)
    np.fill_diagonal(dist, np.inf)
    return float(np.median(dist.min(axis=1)))


# ── Core transform ────────────────────────────────────────────────────────────

def _prepare(img: Image.Image, s: PixelSettings) -> tuple[Image.Image, Image.Image | None]:
    """Enhanced, downscaled RGB plus a hard-edged alpha mask (or None)."""
    alpha = None
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        alpha = rgba.getchannel("A")
        rgb = rgba.convert("RGB")
    else:
        rgb = img.convert("RGB")

    if s.contrast != 1.0:
        rgb = ImageEnhance.Contrast(rgb).enhance(s.contrast)
    if s.saturation != 1.0:
        rgb = ImageEnhance.Color(rgb).enhance(s.saturation)

    px = max(1, int(s.pixel_size))
    small_size = (max(1, math.ceil(rgb.width / px)), max(1, math.ceil(rgb.height / px)))
    # BOX averages each block, so a block takes its real average colour; the
    # usual NEAREST picks one arbitrary pixel and speckles.
    small = rgb.resize(small_size, Image.Resampling.BOX)
    if alpha is not None:
        # Pixel art has no soft edges: a block is either there or not.
        alpha = alpha.resize(small_size, Image.Resampling.BOX).point(
            lambda v: 255 if v >= 128 else 0)
    return small, alpha


def _apply_palette(small: Image.Image, colours: list[str], dither: str,
                   ramp: bool) -> Image.Image:
    """Snap every pixel to *colours*. Returns RGB."""
    if ramp:
        # Match on brightness: quantize a grey copy against the ramp's own
        # brightness levels, then paint each level with its real colour.
        colours = sorted(colours, key=_luma)
        levels = [(_luma(c),) * 3 for c in colours]
        small = ImageOps.autocontrast(small.convert("L"), cutoff=1).convert("RGB")
    else:
        levels = [_rgb(c) for c in colours]

    if dither == DITHER_ORDERED:
        # Push each pixel up or down by a tiled threshold before snapping to
        # the palette: the snapped result forms the familiar crosshatch.
        arr = np.asarray(small, dtype=np.float32)
        h, w = arr.shape[:2]
        tile = np.tile(_BAYER, (h // 4 + 1, w // 4 + 1))[:h, :w]
        arr = np.clip(arr + tile[..., None] * _gap(levels), 0, 255).astype(np.uint8)
        small = Image.fromarray(arr, "RGB")
        mode = Image.Dither.NONE
    elif dither == DITHER_FLOYD:
        mode = Image.Dither.FLOYDSTEINBERG
    else:
        mode = Image.Dither.NONE

    indexed = small.quantize(palette=_palette_image(levels), dither=mode)
    if ramp:
        indexed.putpalette([c for code in colours for c in _rgb(code)]
                           + list(_rgb(colours[0])) * (256 - len(colours)))
    return indexed.convert("RGB")


def pixelate(img: Image.Image, settings: PixelSettings,
             palette: list[str] | None = None) -> Image.Image:
    """One image -> pixel art. Pass *palette* to share one across frames."""
    if palette is None:
        palette = build_palette([img], settings)
    small, alpha = _prepare(img, settings)
    out = _apply_palette(small, palette, settings.dither,
                         ramp=settings.palette in RAMPS)
    if alpha is not None:
        out = out.convert("RGBA")
        out.putalpha(alpha)
    if settings.upscale and settings.pixel_size > 1:
        px = int(settings.pixel_size)
        out = out.resize((out.width * px, out.height * px), Image.Resampling.NEAREST)
        # Blocks round UP at the right/bottom edge (640 / 6 -> 107 blocks ->
        # 642 px). Trim back so the output is exactly the source size.
        out = out.crop((0, 0, img.width, img.height))
    return out


# ── Files ─────────────────────────────────────────────────────────────────────

def default_output(path: str) -> str:
    stem, ext = os.path.splitext(path)
    ext = ext.lower()
    if ext in VIDEO_EXTS:
        ext = ".mp4"
    elif ext not in GIF_EXTS:
        ext = ".png"            # JPEG would smear the flat colours
    return f"{stem}_pixel{ext}"


def convert(path: str, settings: PixelSettings, output: str | None = None,
            progress=None, cancel=None) -> str:
    """Convert any supported file. Returns the output path."""
    ext = os.path.splitext(path)[1].lower()
    output = output or default_output(path)
    if ext in GIF_EXTS:
        return _convert_gif(path, output, settings, progress, cancel)
    if ext in VIDEO_EXTS:
        return _convert_video(path, output, settings, progress, cancel)
    if ext in IMAGE_EXTS:
        with Image.open(path) as img:
            pixelate(img, settings).save(output)
        return output
    raise ValueError(f"Unsupported file type: {ext}")


def _convert_gif(path, output, settings, progress, cancel) -> str:
    with Image.open(path) as gif:
        frames = [f.convert("RGBA") for f in ImageSequence.Iterator(gif)]
        durations = []
        gif.seek(0)
        for f in ImageSequence.Iterator(gif):
            durations.append(f.info.get("duration", gif.info.get("duration", 100)))
        loop = gif.info.get("loop", 0)

    step = max(1, len(frames) // 16)
    palette = build_palette(frames[::step], settings)
    out = []
    for i, frame in enumerate(frames):
        if cancel is not None and cancel():
            raise InterruptedError("cancelled")
        out.append(pixelate(frame, settings, palette))
        if progress is not None:
            progress(i + 1, len(frames))
    out[0].save(output, save_all=True, append_images=out[1:], duration=durations,
                loop=loop, disposal=2, optimize=False)
    return output


def _probe(path: str) -> tuple[int, int, float, int]:
    """(width, height, fps, approx frame count) of a video's first stream."""
    from utils.ffmpeg import ffprobe_path

    cmd = [ffprobe_path, "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=width,height,avg_frame_rate,nb_frames:format=duration",
           "-of", "json", path]
    data = json.loads(subprocess.run(cmd, capture_output=True, text=True,
                                     creationflags=_NO_WINDOW, check=True).stdout)
    st = data["streams"][0]
    num, _, den = st.get("avg_frame_rate", "30/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    try:
        frames = int(st.get("nb_frames") or 0)
    except ValueError:
        frames = 0
    if not frames:
        frames = int(float(data.get("format", {}).get("duration", 0) or 0) * fps)
    return int(st["width"]), int(st["height"]), fps or 30.0, frames


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _sample_frames(path: str, width: int, height: int, duration_frames: int,
                   fps: float, count: int = 12) -> list[Image.Image]:
    """A few frames spread over the clip, for the shared palette."""
    from utils.ffmpeg import ffmpeg_path

    seconds = max(duration_frames / fps, 1.0)
    rate = count / seconds
    cmd = [ffmpeg_path, "-v", "error", "-i", path, "-vf", f"fps={rate:.6f}",
           "-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW).stdout
    size = width * height * 3
    return [Image.frombytes("RGB", (width, height), raw[i:i + size])
            for i in range(0, len(raw) - size + 1, size)]


def _convert_video(path, output, settings, progress, cancel) -> str:
    """Decode -> pixelate -> encode through pipes; audio is carried across."""
    try:
        return _encode_video(path, output, settings, progress, cancel)
    except BaseException:
        # Never leave a truncated video behind looking like a result.
        try:
            os.remove(output)
        except OSError:
            pass
        raise


def _encode_video(path, output, settings, progress, cancel) -> str:
    from utils.ffmpeg import ffmpeg_path

    width, height, fps, total = _probe(path)
    samples = _sample_frames(path, width, height, total, fps) or []
    palette = build_palette(samples, settings) if samples else None

    frame_size = width * height * 3
    decoder = subprocess.Popen(
        [ffmpeg_path, "-v", "error", "-i", path, "-f", "rawvideo",
         "-pix_fmt", "rgb24", "-"],
        # Closing the pipe early (cancel) makes the decoder complain about a
        # write it no longer needs to make; that is expected, not an error.
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        creationflags=_NO_WINDOW)
    encoder = None
    done = 0
    try:
        while True:
            if cancel is not None and cancel():
                raise InterruptedError("cancelled")
            raw = decoder.stdout.read(frame_size)
            if len(raw) < frame_size:
                break
            frame = Image.frombytes("RGB", (width, height), raw)
            if palette is None:
                palette = build_palette([frame], settings)
            art = pixelate(frame, settings, palette).convert("RGB")
            if encoder is None:
                encoder = subprocess.Popen(
                    [ffmpeg_path, "-y", "-v", "error",
                     "-f", "rawvideo", "-pix_fmt", "rgb24",
                     "-s", f"{art.width}x{art.height}", "-r", f"{fps:.6f}", "-i", "-",
                     "-i", path, "-map", "0:v", "-map", "1:a?",
                     # yuv420p needs even dimensions; pad by one pixel if not.
                     "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                     "-c:v", "libx264", "-crf", "16", "-preset", "medium",
                     "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", output],
                    stdin=subprocess.PIPE, creationflags=_NO_WINDOW)
            try:
                encoder.stdin.write(art.tobytes())
            except BrokenPipeError:
                raise RuntimeError("Video encoding failed") from None
            done += 1
            if progress is not None:
                progress(done, max(total, done))
    finally:
        decoder.stdout.close()
        decoder.wait()
        if encoder is not None:
            encoder.stdin.close()
            encoder.wait()
    if encoder is None or encoder.returncode != 0:
        raise RuntimeError("Video encoding failed")
    return output


def preview_frame(path: str) -> Image.Image:
    """One representative frame of any supported file, as RGB(A).

    For a video that is a frame a tenth of the way in: the very first frame is
    often black or a title card, which would make a misleading preview.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTS:
        from utils.ffmpeg import ffmpeg_path

        width, height, fps, total = _probe(path)
        at = max(0.0, (total / fps) * 0.1) if fps else 0.0
        raw = subprocess.run(
            [ffmpeg_path, "-v", "error", "-ss", f"{at:.3f}", "-i", path,
             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, creationflags=_NO_WINDOW).stdout
        if len(raw) < width * height * 3:
            raise RuntimeError("Could not read a frame from the video")
        return Image.frombytes("RGB", (width, height), raw[: width * height * 3])
    with Image.open(path) as img:
        img.seek(0)
        return img.convert("RGBA") if "A" in img.getbands() or img.mode == "P" else img.convert("RGB")
