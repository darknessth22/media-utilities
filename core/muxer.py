"""Audio/Video muxing operations — mute video and replace audio track."""
from __future__ import annotations

import os
import subprocess
import sys
import uuid

from utils.ffmpeg import ffmpeg_path
from utils.process_registry import tracked_run

_WIN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v"}


def mute_video(video_path: str, output_dir: str | None = None) -> bool:
    """Strip the audio track from *video_path*, writing a *_muted* file."""
    ext = os.path.splitext(video_path)[1].lower()
    if ext not in _VIDEO_EXTS:
        return False

    base = os.path.splitext(os.path.basename(video_path))[0]
    out_dir = output_dir or os.path.dirname(video_path)
    output_path = os.path.join(out_dir, f"{base}_muted{ext}")

    cmd = [ffmpeg_path, "-y", "-i", video_path, "-an", "-c:v", "copy", output_path]
    try:
        tracked_run(cmd, str(uuid.uuid4()), check=True, capture_output=True, timeout=3600, **_WIN_FLAGS)
        return True
    except subprocess.CalledProcessError:
        return False


def mix_audio_overlay(
    video_path: str,
    audio_path: str,
    overlay_volume: float = 1.0,
    output_dir: str | None = None,
) -> bool:
    """Mix *audio_path* on top of the video's existing audio at *overlay_volume* (0.0–2.0).

    Uses amix duration=first so the output length matches the video's audio,
    discarding any overlay audio that extends past it.
    """
    ext = os.path.splitext(video_path)[1].lower()
    if ext not in _VIDEO_EXTS:
        return False

    volume = max(0.0, min(2.0, overlay_volume))
    base = os.path.splitext(os.path.basename(video_path))[0]
    out_dir = output_dir or os.path.dirname(video_path)
    output_path = os.path.join(out_dir, f"{base}_mixed{ext}")

    filter_graph = (
        f"[1:a]volume={volume:.3f}[ov];"
        "[0:a][ov]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
    )
    cmd = [
        ffmpeg_path, "-y",
        "-i", video_path,
        "-i", audio_path,
        "-filter_complex", filter_graph,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        output_path,
    ]
    try:
        tracked_run(cmd, str(uuid.uuid4()), check=True, capture_output=True, timeout=3600, **_WIN_FLAGS)
        return True
    except subprocess.CalledProcessError:
        return False


def replace_audio(video_path: str, audio_path: str, output_dir: str | None = None) -> bool:
    """Replace the audio track of *video_path* with *audio_path*.

    Uses -shortest so the output ends at whichever stream finishes first,
    preventing a frozen black screen when audio outlasts video.
    """
    ext = os.path.splitext(video_path)[1].lower()
    if ext not in _VIDEO_EXTS:
        return False

    base = os.path.splitext(os.path.basename(video_path))[0]
    out_dir = output_dir or os.path.dirname(video_path)
    output_path = os.path.join(out_dir, f"{base}_remuxed{ext}")

    cmd = [
        ffmpeg_path, "-y",
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path,
    ]
    try:
        tracked_run(cmd, str(uuid.uuid4()), check=True, capture_output=True, timeout=3600, **_WIN_FLAGS)
        return True
    except subprocess.CalledProcessError:
        return False
