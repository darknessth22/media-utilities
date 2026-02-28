"""Media trimming via FFmpeg."""
import os
import subprocess
import sys

from core.downloader import parse_time
from utils.ffmpeg import ffmpeg_path

_WIN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def trim_media(file_path: str, start_time: str, end_time: str, output_dir: str | None = None) -> bool:
    """Trim an audio or video file between start_time and end_time."""
    supported_formats = {
        "audio": {"mp3", "wav", "aac", "flac", "ogg", "m4a"},
        "video": {"mp4", "mkv", "avi", "mov", "webm", "flv"},
    }
    ext = os.path.splitext(file_path)[1][1:].lower()
    media_type = next((k for k, v in supported_formats.items() if ext in v), None)

    if media_type not in ("audio", "video"):
        return False

    try:
        start = parse_time(start_time)
        end = parse_time(end_time)
    except ValueError:
        return False

    filename = os.path.basename(file_path)
    base, ext_with_dot = os.path.splitext(filename)
    out_dir = output_dir if output_dir else os.path.dirname(file_path)
    output_path = os.path.join(out_dir, f"{base}_trimmed{ext_with_dot}")

    cmd = [ffmpeg_path, "-y", "-i", file_path, "-ss", str(start), "-to", str(end)]

    if media_type == "video":
        cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "aac", "-b:a", "192k"]
    elif media_type == "audio":
        codec_map = {
            "mp3": "libmp3lame", "wav": "pcm_s16le", "aac": "aac",
            "flac": "flac", "ogg": "libvorbis", "m4a": "aac",
        }
        cmd += ["-c:a", codec_map.get(ext, "copy")]

    cmd.append(output_path)

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=3600, **_WIN_FLAGS)
        return True
    except subprocess.CalledProcessError:
        return False
