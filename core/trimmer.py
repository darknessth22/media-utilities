"""Media trimming via FFmpeg."""
import json
import os
import subprocess
import sys

from core.downloader import parse_time
from utils.ffmpeg import ffmpeg_path, ffprobe_path

_WIN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def _probe_video(file_path: str) -> dict | None:
    """Probe main video for width, height, fps, and audio sample_rate.

    Returns dict with keys: width, height, fps, sample_rate — or None on failure.
    """
    try:
        result = subprocess.run(
            [
                ffprobe_path, "-v", "quiet", "-print_format", "json",
                "-show_streams", file_path,
            ],
            capture_output=True, text=True, timeout=30, **_WIN_FLAGS,
        )
        streams = json.loads(result.stdout).get("streams", [])
        info: dict = {}
        for s in streams:
            if s.get("codec_type") == "video" and "width" not in info:
                info["width"]  = s["width"]
                info["height"] = s["height"]
                info["fps"]    = s.get("r_frame_rate", "30/1")
            if s.get("codec_type") == "audio" and "sample_rate" not in info:
                info["sample_rate"] = s.get("sample_rate", "44100")
        return info if info else None
    except Exception:
        return None

_SUPPORTED_FORMATS = {
    "audio": {"mp3", "wav", "aac", "flac", "ogg", "m4a"},
    "video": {"mp4", "mkv", "avi", "mov", "webm", "flv"},
}


def trim_media(file_path: str, start_time: str, end_time: str, output_dir: str | None = None) -> bool:
    """Trim an audio or video file between start_time and end_time."""
    ext = os.path.splitext(file_path)[1][1:].lower()
    media_type = next((k for k, v in _SUPPORTED_FORMATS.items() if ext in v), None)

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


def ripple_delete_media(file_path: str, cut_start: str, cut_end: str, output_dir: str | None = None) -> bool:
    """Delete a single segment (stream copy, keyframe-accurate). Delegates to multi."""
    return ripple_delete_multi(file_path, [(cut_start, cut_end)], output_dir)


def ripple_delete_multi(
    file_path: str,
    segments: list[tuple[str, str]],
    output_dir: str | None = None,
) -> bool:
    """Delete multiple segments and join the remaining parts (stream copy, keyframe-accurate).

    segments: list of (cut_start, cut_end) strings in HH:MM:SS format, sorted or unsorted.
    """
    ext = os.path.splitext(file_path)[1][1:].lower()
    media_type = next((k for k, v in _SUPPORTED_FORMATS.items() if ext in v), None)
    if media_type not in ("audio", "video"):
        return False

    try:
        parsed = sorted((parse_time(s), parse_time(e)) for s, e in segments)
    except ValueError:
        return False

    # Validate: no segment where start >= end
    if any(s >= e for s, e in parsed):
        return False

    base, ext_with_dot = os.path.splitext(os.path.basename(file_path))
    out_dir = output_dir if output_dir else os.path.dirname(file_path)
    output_path = os.path.join(out_dir, f"{base}_trimmed{ext_with_dot}")

    # Build list of kept ranges: gaps between delete segments
    kept: list[tuple[float, float | None]] = []
    prev_end = 0.0
    for seg_start, seg_end in parsed:
        if seg_start > prev_end:
            kept.append((prev_end, seg_start))
        prev_end = max(prev_end, seg_end)
    kept.append((prev_end, None))  # from last delete end to end of file

    temps: list[str] = []
    list_file = os.path.join(out_dir, f"_rd_list_{base}.txt")

    try:
        for i, (keep_start, keep_end) in enumerate(kept):
            tmp = os.path.join(out_dir, f"_rd_part{i}_{base}{ext_with_dot}")
            temps.append(tmp)
            cmd = [ffmpeg_path, "-y", "-i", file_path, "-ss", str(keep_start)]
            if keep_end is not None:
                cmd += ["-to", str(keep_end)]
            cmd += ["-c", "copy", tmp]
            subprocess.run(cmd, check=True, capture_output=True, timeout=3600, **_WIN_FLAGS)

        with open(list_file, "w") as f:
            for tmp in temps:
                f.write(f"file '{tmp}'\n")

        cmd_concat = [
            ffmpeg_path, "-y", "-f", "concat", "-safe", "0",
            "-i", list_file, "-c", "copy", output_path,
        ]
        subprocess.run(cmd_concat, check=True, capture_output=True, timeout=3600, **_WIN_FLAGS)

        return True
    except subprocess.CalledProcessError:
        return False
    finally:
        for tmp in temps:
            try:
                os.remove(tmp)
            except OSError:
                pass
        try:
            os.remove(list_file)
        except OSError:
            pass


def insert_clip(
    main_path: str,
    clip_path: str,
    insert_at: str,
    output_dir: str | None = None,
) -> bool:
    """Insert clip_path into main_path at insert_at timestamp (re-encodes to H.264/AAC)."""
    for p in (main_path, clip_path):
        ext = os.path.splitext(p)[1][1:].lower()
        if not any(ext in v for v in _SUPPORTED_FORMATS.values()):
            return False

    try:
        at = parse_time(insert_at)
    except ValueError:
        return False

    base, ext_with_dot = os.path.splitext(os.path.basename(main_path))
    out_dir = output_dir if output_dir else os.path.dirname(main_path)
    output_path = os.path.join(out_dir, f"{base}_inserted{ext_with_dot}")

    # Probe main video — only the clip is re-encoded to match; before/after are stream-copied
    probe = _probe_video(main_path)
    if probe:
        w          = probe["width"]
        h          = probe["height"]
        fps        = probe["fps"]
        sample_rate = probe.get("sample_rate", "44100")
        _CLIP_VIDEO = [
            "-vf", f"scale={w}:{h},fps={fps}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        ]
        _CLIP_AUDIO = ["-c:a", "aac", "-b:a", "192k", "-ar", sample_rate]
    else:
        _CLIP_VIDEO = ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]
        _CLIP_AUDIO = ["-c:a", "aac", "-b:a", "192k"]

    temp_before = os.path.join(out_dir, f"_ins_before_{base}{ext_with_dot}")
    temp_after  = os.path.join(out_dir, f"_ins_after_{base}{ext_with_dot}")
    temp_clip   = os.path.join(out_dir, f"_ins_clip_{base}{ext_with_dot}")
    list_file   = os.path.join(out_dir, f"_ins_list_{base}.txt")

    try:
        # Stream copy before/after — fast, no re-encode of main video
        subprocess.run(
            [ffmpeg_path, "-y", "-i", main_path, "-to", str(at), "-c", "copy", temp_before],
            check=True, capture_output=True, timeout=3600, **_WIN_FLAGS,
        )
        subprocess.run(
            [ffmpeg_path, "-y", "-i", main_path, "-ss", str(at), "-c", "copy", temp_after],
            check=True, capture_output=True, timeout=3600, **_WIN_FLAGS,
        )
        # Re-encode only the clip to match main video's resolution, FPS, and audio sample rate
        subprocess.run(
            [ffmpeg_path, "-y", "-i", clip_path, *_CLIP_VIDEO, *_CLIP_AUDIO, temp_clip],
            check=True, capture_output=True, timeout=3600, **_WIN_FLAGS,
        )

        with open(list_file, "w") as f:
            f.write(f"file '{temp_before}'\n")
            f.write(f"file '{temp_clip}'\n")
            f.write(f"file '{temp_after}'\n")

        subprocess.run(
            [ffmpeg_path, "-y", "-f", "concat", "-safe", "0",
             "-i", list_file, "-c", "copy", output_path],
            check=True, capture_output=True, timeout=3600, **_WIN_FLAGS,
        )

        return True
    except subprocess.CalledProcessError:
        return False
    finally:
        for tmp in (temp_before, temp_after, temp_clip, list_file):
            try:
                os.remove(tmp)
            except OSError:
                pass
