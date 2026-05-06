"""Extract dominant color palettes from images and video using FFmpeg palettegen."""
import os
import sys
import tempfile
import uuid

from utils.ffmpeg import ffmpeg_path
from utils.process_registry import tracked_run

_WIN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif", ".gif"}
VIDEO_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".ts", ".mts", ".mxf",
}
ALL_EXTS = IMAGE_EXTS | VIDEO_EXTS


def extract_palette(
    input_path: str,
    num_colors: int = 16,
    timestamp: str | None = None,
) -> dict:
    """Analyze media with FFmpeg palettegen; return hex codes only — no files saved.

    timestamp: if set (HH:MM:SS or HH:MM:SS.mmm) and input is a video, only that
               single frame is analyzed — fast regardless of video length.
               If None and input is a video, the entire video is aggregated (slow).

    Returns {"success": bool, "hex_codes": list[str], "error": str}
    """
    if not os.path.isfile(input_path):
        return {"success": False, "hex_codes": [], "error": "Source file not found."}

    ext = os.path.splitext(input_path)[1].lower()
    is_video = ext in VIDEO_EXTS
    num_colors = max(2, min(256, num_colors))

    tmp_dir = tempfile.mkdtemp(prefix="videl_pal_")
    palette_path = os.path.join(tmp_dir, "_palette.png")

    # Single-frame analysis: images always, videos when a timestamp is given.
    # Full-video aggregation: videos with no timestamp (slow for long files).
    single_frame = (not is_video) or (timestamp is not None)
    stats_mode = "single" if single_frame else "full"
    vf = f"palettegen=max_colors={num_colors}:stats_mode={stats_mode}:reserve_transparent=0"

    if is_video and timestamp:
        # Seek before input (fast seek), decode only one frame
        cmd = [
            ffmpeg_path, "-y",
            "-ss", timestamp,
            "-i", input_path,
            "-vframes", "1",
            "-vf", vf,
            palette_path,
        ]
    else:
        cmd = [
            ffmpeg_path, "-y",
            "-i", input_path,
            "-vf", vf,
            palette_path,
        ]

    job_id = str(uuid.uuid4())
    try:
        tracked_run(cmd, job_id, check=True, capture_output=True, timeout=300, **_WIN_FLAGS)
    except Exception as exc:
        _cleanup(tmp_dir, palette_path)
        return {"success": False, "hex_codes": [], "error": str(exc)}

    if not os.path.isfile(palette_path):
        _cleanup(tmp_dir, palette_path)
        return {"success": False, "hex_codes": [], "error": "Palette image not created."}

    hex_codes = _read_palette_colors(palette_path, num_colors)
    _cleanup(tmp_dir, palette_path)
    return {"success": True, "hex_codes": hex_codes, "error": ""}


def _cleanup(tmp_dir: str, palette_path: str) -> None:
    try:
        if os.path.isfile(palette_path):
            os.remove(palette_path)
        os.rmdir(tmp_dir)
    except OSError:
        pass


def _read_palette_colors(palette_path: str, max_colors: int) -> list[str]:
    """Read unique pixel colors from the FFmpeg palette PNG via Pillow."""
    try:
        from PIL import Image
        img = Image.open(palette_path).convert("RGB")
        seen: dict[tuple, str] = {}
        for r, g, b in img.getdata():
            key = (r, g, b)
            if key not in seen:
                seen[key] = f"#{r:02X}{g:02X}{b:02X}"
        return list(seen.values())[:max_colors]
    except ImportError:
        return []
    except Exception:
        return []
