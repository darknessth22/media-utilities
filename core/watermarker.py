"""Batch watermarking. Pillow for images (preserves EXIF/ICC), FFmpeg for videos."""
import os
import subprocess
import sys
import uuid

from PIL import Image, ImageDraw, ImageFont, ImageOps

from utils.ffmpeg import ffmpeg_path
from utils.process_registry import tracked_run

_WIN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".m4v", ".wmv"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}
_ALL_EXTS = _VIDEO_EXTS | _IMAGE_EXTS

_MARGIN = 10

_OVERLAY_POS = {
    "top-left":     "10:10",
    "top-right":    "W-w-10:10",
    "bottom-left":  "10:H-h-10",
    "bottom-right": "W-w-10:H-h-10",
    "center":       "(W-w)/2:(H-h)/2",
}

_TEXT_POS = {
    "top-left":     ("10", "10"),
    "top-right":    ("w-tw-10", "10"),
    "bottom-left":  ("10", "h-th-10"),
    "bottom-right": ("w-tw-10", "h-th-10"),
    "center":       ("(w-tw)/2", "(h-th)/2"),
}

PRESET_OPTIONS = {
    "none":   (["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"], "fast"),
    "nvidia": (["p1", "p2", "p3", "p4", "p5", "p6", "p7"], "p4"),
    "amd":    (["speed", "balanced", "quality"], "balanced"),
    "intel":  (["veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"], "fast"),
}


def _encode_flags(crf: int, preset: str, hw_accel: str) -> list[str]:
    if hw_accel == "nvidia":
        return ["-c:v", "h264_nvenc", "-preset", preset, "-rc", "constqp", "-qp", str(crf), "-b:v", "0"]
    if hw_accel == "amd":
        return ["-c:v", "h264_amf", "-quality", preset, "-rc", "1",
                "-qp_i", str(crf), "-qp_p", str(crf), "-qp_b", str(crf)]
    if hw_accel == "intel":
        return ["-c:v", "h264_qsv", "-preset", preset, "-global_quality", str(crf), "-look_ahead", "1"]
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]


def _anchor_xy(canvas_w: int, canvas_h: int, item_w: int, item_h: int, position: str) -> tuple[int, int]:
    m = _MARGIN
    if position == "top-left":     return (m, m)
    if position == "top-right":    return (canvas_w - item_w - m, m)
    if position == "bottom-left":  return (m, canvas_h - item_h - m)
    if position == "center":       return ((canvas_w - item_w) // 2, (canvas_h - item_h) // 2)
    return (canvas_w - item_w - m, canvas_h - item_h - m)  # bottom-right default


def _save_image(img: Image.Image, src_path: str, out_path: str, src_info: dict, src_format: str | None) -> None:
    """Save while preserving EXIF + ICC. Reset orientation tag (already applied via transpose)."""
    ext = os.path.splitext(out_path)[1].lower()
    save_kwargs: dict = {}

    exif_bytes = src_info.get("exif")
    if exif_bytes:
        try:
            exif = Image.Exif()
            exif.load(exif_bytes)
            if 0x0112 in exif:  # Orientation
                exif[0x0112] = 1
            save_kwargs["exif"] = exif.tobytes()
        except Exception:
            save_kwargs["exif"] = exif_bytes

    icc = src_info.get("icc_profile")
    if icc:
        save_kwargs["icc_profile"] = icc

    if ext in (".jpg", ".jpeg"):
        if img.mode != "RGB":
            img = img.convert("RGB")
        save_kwargs.update(quality=95, subsampling=0, optimize=True)
        if "dpi" in src_info:
            save_kwargs["dpi"] = src_info["dpi"]
    elif ext == ".png":
        save_kwargs["optimize"] = True
    elif ext == ".webp":
        save_kwargs.update(quality=95, method=6)
    elif ext in (".tif", ".tiff"):
        if "compression" in src_info:
            save_kwargs["compression"] = src_info["compression"]

    img.save(out_path, **save_kwargs)


def _watermark_image_logo(file_path: str, logo_path: str, position: str, opacity: float,
                          scale: float, output_path: str) -> bool:
    try:
        with Image.open(file_path) as src:
            src_info = dict(src.info)
            src_format = src.format
            base = ImageOps.exif_transpose(src).convert("RGBA")

        with Image.open(logo_path) as lg:
            logo = lg.convert("RGBA")

        target_w = max(1, int(base.width * scale))
        ratio = target_w / logo.width
        target_h = max(1, int(logo.height * ratio))
        logo = logo.resize((target_w, target_h), Image.LANCZOS)

        if opacity < 1.0:
            r, g, b, a = logo.split()
            a = a.point(lambda v: int(v * opacity))
            logo = Image.merge("RGBA", (r, g, b, a))

        x, y = _anchor_xy(base.width, base.height, logo.width, logo.height, position)
        base.alpha_composite(logo, (x, y))

        _save_image(base, file_path, output_path, src_info, src_format)
        return True
    except Exception:
        return False


def _load_font(size: int) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "DejaVuSans.ttf", "Helvetica.ttc", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _watermark_image_text(file_path: str, text: str, position: str, font_size: int,
                          font_color: str, opacity: float, output_path: str) -> bool:
    try:
        with Image.open(file_path) as src:
            src_info = dict(src.info)
            src_format = src.format
            base = ImageOps.exif_transpose(src).convert("RGBA")

        font = _load_font(font_size)
        # measure
        tmp_draw = ImageDraw.Draw(base)
        bbox = tmp_draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad = 6
        box_w, box_h = tw + pad * 2, th + pad * 2

        x, y = _anchor_xy(base.width, base.height, box_w, box_h, position)

        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        draw.rectangle([x, y, x + box_w, y + box_h], fill=(0, 0, 0, int(255 * 0.35 * opacity)))

        try:
            from PIL import ImageColor
            r, g, b = ImageColor.getrgb(font_color)
        except Exception:
            r, g, b = (255, 255, 255)
        draw.text((x + pad - bbox[0], y + pad - bbox[1]), text, font=font,
                  fill=(r, g, b, int(255 * opacity)))

        base = Image.alpha_composite(base, layer)
        _save_image(base, file_path, output_path, src_info, src_format)
        return True
    except Exception:
        return False


def watermark_logo(
    file_path: str,
    logo_path: str,
    position: str = "bottom-right",
    opacity: float = 0.8,
    scale: float = 0.15,
    output_dir: str | None = None,
    crf: int = 18,
    preset: str = "fast",
    hw_accel: str = "none",
) -> bool:
    """Overlay a logo image onto a video or image file."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in _ALL_EXTS:
        return False

    base_name = os.path.splitext(os.path.basename(file_path))[0]
    out_dir = output_dir or os.path.dirname(file_path) or "."
    output_path = os.path.join(out_dir, f"{base_name}_watermarked{ext}")

    if ext in _IMAGE_EXTS:
        return _watermark_image_logo(file_path, logo_path, position, opacity, scale, output_path)

    overlay_pos = _OVERLAY_POS.get(position, _OVERLAY_POS["bottom-right"])
    vf = (
        f"[1:v]scale=iw*{scale}:-1,format=rgba,"
        f"colorchannelmixer=aa={opacity:.2f}[wm];"
        f"[0:v][wm]overlay={overlay_pos}"
    )
    cmd = [
        ffmpeg_path, "-y",
        "-i", file_path,
        "-i", logo_path,
        "-filter_complex", vf,
        *_encode_flags(crf, preset, hw_accel),
        "-c:a", "copy",
        output_path,
    ]
    job_id = str(uuid.uuid4())
    try:
        tracked_run(cmd, job_id, check=True, capture_output=True, timeout=7200, **_WIN_FLAGS)
        return True
    except subprocess.CalledProcessError:
        return False


def watermark_text(
    file_path: str,
    text: str,
    position: str = "bottom-right",
    font_size: int = 36,
    font_color: str = "white",
    opacity: float = 0.8,
    output_dir: str | None = None,
    crf: int = 18,
    preset: str = "fast",
    hw_accel: str = "none",
) -> bool:
    """Burn a text watermark onto a video or image."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in _ALL_EXTS:
        return False

    base_name = os.path.splitext(os.path.basename(file_path))[0]
    out_dir = output_dir or os.path.dirname(file_path) or "."
    output_path = os.path.join(out_dir, f"{base_name}_watermarked{ext}")

    if ext in _IMAGE_EXTS:
        return _watermark_image_text(file_path, text, position, font_size, font_color, opacity, output_path)

    x, y = _TEXT_POS.get(position, _TEXT_POS["bottom-right"])
    escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    vf = (
        f"drawtext=text='{escaped}'"
        f":fontsize={font_size}"
        f":fontcolor={font_color}@{opacity:.2f}"
        f":x={x}:y={y}"
        f":box=1:boxcolor=black@0.35:boxborderw=6"
    )
    cmd = [
        ffmpeg_path, "-y",
        "-i", file_path,
        "-vf", vf,
        *_encode_flags(crf, preset, hw_accel),
        "-c:a", "copy",
        output_path,
    ]
    job_id = str(uuid.uuid4())
    try:
        tracked_run(cmd, job_id, check=True, capture_output=True, timeout=7200, **_WIN_FLAGS)
        return True
    except subprocess.CalledProcessError:
        return False


def watermark_batch(
    file_paths: list[str],
    mode: str,
    output_dir: str | None = None,
    progress_cb=None,
    **kwargs,
) -> dict[str, bool]:
    """Watermark multiple files. mode='logo' or 'text'. kwargs → watermark_logo/text.

    progress_cb(done: int, total: int) called after each file.
    """
    fn = watermark_logo if mode == "logo" else watermark_text
    results: dict[str, bool] = {}
    total = len(file_paths)
    for i, path in enumerate(file_paths):
        results[path] = fn(path, output_dir=output_dir, **kwargs)
        if progress_cb:
            progress_cb(i + 1, total)
    return results
