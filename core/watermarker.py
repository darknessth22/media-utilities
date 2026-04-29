"""Batch watermarking via FFmpeg overlay and drawtext filters."""
import os
import subprocess
import sys
import uuid

from utils.ffmpeg import ffmpeg_path
from utils.process_registry import tracked_run

_WIN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".m4v", ".wmv"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}
_ALL_EXTS = _VIDEO_EXTS | _IMAGE_EXTS

# overlay x:y expressions for logo mode
_OVERLAY_POS = {
    "top-left":     "10:10",
    "top-right":    "W-w-10:10",
    "bottom-left":  "10:H-h-10",
    "bottom-right": "W-w-10:H-h-10",
    "center":       "(W-w)/2:(H-h)/2",
}

# drawtext x/y expressions for text mode
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

    is_image = ext in _IMAGE_EXTS
    base = os.path.splitext(os.path.basename(file_path))[0]
    out_dir = output_dir or os.path.dirname(file_path) or "."
    output_path = os.path.join(out_dir, f"{base}_watermarked{ext}")

    overlay_pos = _OVERLAY_POS.get(position, _OVERLAY_POS["bottom-right"])
    vf = (
        f"[1:v]scale=iw*{scale}:-1,format=rgba,"
        f"colorchannelmixer=aa={opacity:.2f}[wm];"
        f"[0:v][wm]overlay={overlay_pos}"
    )

    if is_image:
        cmd = [
            ffmpeg_path, "-y",
            "-i", file_path,
            "-i", logo_path,
            "-filter_complex", vf,
            "-frames:v", "1",
            "-q:v", "2",
            output_path,
        ]
    else:
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
    """Burn a text watermark onto a video or image via drawtext."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in _ALL_EXTS:
        return False

    is_image = ext in _IMAGE_EXTS
    base = os.path.splitext(os.path.basename(file_path))[0]
    out_dir = output_dir or os.path.dirname(file_path) or "."
    output_path = os.path.join(out_dir, f"{base}_watermarked{ext}")

    x, y = _TEXT_POS.get(position, _TEXT_POS["bottom-right"])
    escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")

    vf = (
        f"drawtext=text='{escaped}'"
        f":fontsize={font_size}"
        f":fontcolor={font_color}@{opacity:.2f}"
        f":x={x}:y={y}"
        f":box=1:boxcolor=black@0.35:boxborderw=6"
    )

    if is_image:
        cmd = [
            ffmpeg_path, "-y",
            "-i", file_path,
            "-vf", vf,
            "-frames:v", "1",
            "-q:v", "2",
            output_path,
        ]
    else:
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
