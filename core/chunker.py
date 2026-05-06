"""Split media files into chunks by duration or size (stream copy, no re-encode)."""
import json
import os
import subprocess
import sys
import uuid

from utils.ffmpeg import ffmpeg_path, ffprobe_path
from utils.process_registry import tracked_run

_WIN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def _probe_duration(file_path: str) -> float | None:
    """Return file duration in seconds, or None on failure."""
    try:
        result = subprocess.run(
            [ffprobe_path, "-v", "quiet", "-print_format", "json",
             "-show_format", file_path],
            capture_output=True, text=True, timeout=30, **_WIN_FLAGS,
        )
        return float(json.loads(result.stdout)["format"]["duration"])
    except Exception:
        return None


def split_by_duration(
    file_path: str,
    segment_secs: float,
    output_dir: str | None = None,
) -> bool:
    """Split into segments of *segment_secs* seconds using stream copy (no re-encode).

    Output files are named <base>_part000.<ext>, <base>_part001.<ext>, …
    """
    if segment_secs <= 0:
        return False

    ext = os.path.splitext(file_path)[1].lower()
    base = os.path.splitext(os.path.basename(file_path))[0]
    out_dir = output_dir or os.path.dirname(file_path) or "."
    out_pattern = os.path.join(out_dir, f"{base}_part%03d{ext}")

    cmd = [
        ffmpeg_path, "-y",
        "-i", file_path,
        "-c", "copy",
        "-f", "segment",
        "-segment_time", str(int(segment_secs)),
        "-reset_timestamps", "1",
        out_pattern,
    ]

    job_id = str(uuid.uuid4())
    try:
        tracked_run(cmd, job_id, check=True, capture_output=True, timeout=7200, **_WIN_FLAGS)
        return True
    except subprocess.CalledProcessError:
        return False


def split_by_size(
    file_path: str,
    max_mb: float,
    output_dir: str | None = None,
) -> bool:
    """Split into chunks of approximately *max_mb* MB.

    Estimates segment duration from file size ratio, then delegates to
    split_by_duration. Stream copy only — no re-encode.
    """
    if max_mb <= 0:
        return False

    duration = _probe_duration(file_path)
    if duration is None or duration <= 0:
        return False

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb <= 0:
        return False

    segment_secs = max(1.0, duration * (max_mb / file_size_mb))
    return split_by_duration(file_path, segment_secs, output_dir)
