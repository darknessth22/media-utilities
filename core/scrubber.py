"""Strip metadata (EXIF, GPS, timestamps) from media files using FFmpeg stream copy."""
import os
import subprocess
import sys
import uuid

from utils.ffmpeg import ffmpeg_path
from utils.process_registry import tracked_run

_WIN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

_SUPPORTED_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".m4v", ".wmv",
    ".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a",
}


def scrub_metadata(file_path: str, output_dir: str | None = None) -> bool:
    """Strip all metadata from a single media file via stream copy.

    Uses -map_metadata -1 and -map_chapters -1 so no GPS, timestamps, or
    EXIF tags are written to the output. Re-muxes without re-encoding.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in _SUPPORTED_EXTS:
        return False

    base = os.path.splitext(os.path.basename(file_path))[0]
    out_dir = output_dir or os.path.dirname(file_path) or "."
    output_path = os.path.join(out_dir, f"{base}_clean{ext}")

    cmd = [
        ffmpeg_path, "-y",
        "-i", file_path,
        "-map_metadata", "-1",
        "-map_chapters", "-1",
        "-c", "copy",
        output_path,
    ]

    job_id = str(uuid.uuid4())
    try:
        tracked_run(cmd, job_id, check=True, capture_output=True, timeout=3600, **_WIN_FLAGS)
        return True
    except subprocess.CalledProcessError:
        return False


def scrub_batch(
    file_paths: list[str],
    output_dir: str | None = None,
    progress_cb=None,
) -> dict[str, bool]:
    """Scrub metadata from multiple files. Returns {path: success}.

    progress_cb(done: int, total: int) called after each file.
    """
    results: dict[str, bool] = {}
    total = len(file_paths)
    for i, path in enumerate(file_paths):
        results[path] = scrub_metadata(path, output_dir)
        if progress_cb:
            progress_cb(i + 1, total)
    return results
