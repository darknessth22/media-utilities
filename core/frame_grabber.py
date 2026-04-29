"""Extract high-resolution frames from video as uncompressed PNG or 16-bit TIFF."""
import os
import sys
import uuid

from utils.ffmpeg import ffmpeg_path
from utils.process_registry import tracked_run

_WIN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

VIDEO_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".ts", ".mts", ".mxf", ".ogv",
}


def grab_frame(
    video_path: str,
    timestamp: str,
    output_format: str = "png",
    output_dir: str | None = None,
) -> dict:
    """Extract a single frame at *timestamp* (HH:MM:SS or HH:MM:SS.mmm).

    output_format: "png" → lossless uncompressed PNG
                   "tiff" → 16-bit RGB TIFF (rgb48le, no compression)

    Returns {"success": bool, "file_path": str, "error": str}
    """
    if not os.path.isfile(video_path):
        return {"success": False, "file_path": "", "error": "Source file not found."}

    fmt = output_format.lower().strip(".")
    if fmt not in ("png", "tiff", "tif"):
        fmt = "png"
    ext = ".tiff" if fmt in ("tiff", "tif") else ".png"

    base = os.path.splitext(os.path.basename(video_path))[0]
    ts_tag = timestamp.replace(":", "").replace(".", "")
    out_dir = output_dir or os.path.dirname(video_path) or "."
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{base}_frame_{ts_tag}{ext}")

    if fmt in ("tiff", "tif"):
        cmd = [
            ffmpeg_path, "-y",
            "-ss", timestamp,
            "-i", video_path,
            "-vframes", "1",
            "-pix_fmt", "rgb48le",
            out_path,
        ]
    else:
        cmd = [
            ffmpeg_path, "-y",
            "-ss", timestamp,
            "-i", video_path,
            "-vframes", "1",
            "-compression_level", "0",
            out_path,
        ]

    job_id = str(uuid.uuid4())
    try:
        tracked_run(cmd, job_id, check=True, capture_output=True, timeout=120, **_WIN_FLAGS)
    except Exception as exc:
        return {"success": False, "file_path": "", "error": str(exc)}

    if not os.path.isfile(out_path):
        return {"success": False, "file_path": "", "error": "Output file was not created."}
    return {"success": True, "file_path": out_path, "error": ""}
