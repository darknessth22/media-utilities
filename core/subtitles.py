"""Burn-in subtitles into a video via FFmpeg `subtitles=` filter (libass).

Pure ffmpeg — no extra deps. Hardcodes captions into the video stream so
they render on every player without separate sub track.
"""
from __future__ import annotations

import os
import re
import sys
import uuid

from utils.ffmpeg import ffmpeg_path
from utils.process_registry import tracked_run

_WIN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".m4v", ".wmv"}
_SUB_EXTS = {".srt", ".ass", ".ssa", ".vtt"}


def _escape_filter_path(p: str) -> str:
    """Escape a path for use inside ffmpeg `subtitles=` filter argument.

    libass parses the filter string itself, so colons (drive letter on
    Windows), backslashes, single quotes, brackets, and commas need escaping.
    """
    p = p.replace("\\", "/")
    # Escape special chars in ffmpeg filter graph syntax
    p = p.replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")
    p = p.replace("[", "\\[").replace("]", "\\]")
    return p


def _build_force_style(font: str | None, size: int | None,
                       color: str | None, outline: int | None) -> str | None:
    """Build a libass `force_style` string from optional overrides.

    color is hex `RRGGBB`; libass wants `&HBBGGRR&` (no alpha) — converted here.
    """
    parts: list[str] = []
    if font:
        parts.append(f"FontName={font}")
    if size:
        parts.append(f"FontSize={size}")
    if color:
        m = re.fullmatch(r"#?([0-9A-Fa-f]{6})", color.strip())
        if m:
            rr, gg, bb = m.group(1)[0:2], m.group(1)[2:4], m.group(1)[4:6]
            parts.append(f"PrimaryColour=&H00{bb}{gg}{rr}")
    if outline is not None:
        parts.append(f"Outline={outline}")
    return ",".join(parts) if parts else None


def burn_subtitles(
    video_path: str,
    subtitle_path: str,
    output_path: str | None = None,
    *,
    font: str | None = None,
    font_size: int | None = None,
    font_color: str | None = None,
    outline: int | None = None,
    crf: int = 18,
    preset: str = "medium",
    hw_accel: str = "none",
    cancel_check=None,
    progress_cb=None,
) -> str:
    """Burn `subtitle_path` into `video_path`. Return output file path.

    `hw_accel` ∈ {"none","nvidia","amd","intel"}. Audio stream copied.
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(video_path)
    if not os.path.isfile(subtitle_path):
        raise FileNotFoundError(subtitle_path)

    base, ext = os.path.splitext(video_path)
    if not output_path:
        output_path = f"{base}_subbed{ext or '.mp4'}"

    sub_filter = f"subtitles=filename='{_escape_filter_path(subtitle_path)}'"
    style = _build_force_style(font, font_size, font_color, outline)
    if style:
        sub_filter += f":force_style='{style}'"

    enc: list[str]
    if hw_accel == "nvidia":
        enc = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "constqp", "-qp", str(crf), "-b:v", "0"]
    elif hw_accel == "amd":
        enc = ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "1",
               "-qp_i", str(crf), "-qp_p", str(crf), "-qp_b", str(crf)]
    elif hw_accel == "intel":
        enc = ["-c:v", "h264_qsv", "-preset", "fast", "-global_quality", str(crf)]
    else:
        enc = ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"]

    cmd = [
        ffmpeg_path, "-y",
        "-i", video_path,
        "-vf", sub_filter,
        *enc,
        "-c:a", "copy",
        output_path,
    ]

    job_id = str(uuid.uuid4())
    proc = tracked_run(cmd, job_id, capture_output=True, text=True,
                       timeout=7200, **_WIN_FLAGS)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-2000:]}")
    return output_path
