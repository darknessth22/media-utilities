"""Auto-silence removal (Jump-Cutter) via FFmpeg silencedetect + filter_complex concat."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid

from utils.ffmpeg import ffmpeg_path, ffprobe_path
from utils.process_registry import tracked_run

_WIN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

_AUDIO_EXTS = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"}
_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}

_SILENCE_START_RE = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
_SILENCE_END_RE   = re.compile(r"silence_end:\s*(-?\d+(?:\.\d+)?)")


def _parse_timestamp(token: str) -> float | None:
    """Parse 'SS', 'SS.s', 'M:SS', 'M:SS.s', 'H:M:SS' to seconds. Return None on failure."""
    token = token.strip()
    if not token:
        return None
    try:
        if ":" in token:
            parts = token.split(":")
            if len(parts) > 3:
                return None
            nums = [float(p) for p in parts]
            total = 0.0
            for n in nums:
                total = total * 60.0 + n
            return total if total >= 0 else None
        v = float(token)
        return v if v >= 0 else None
    except ValueError:
        return None


def parse_protected_ranges(text: str) -> tuple[list[tuple[float, float]], list[str]]:
    """Parse multi-line user input into (ranges, errors).

    Each non-empty, non-comment line: '<start> - <end>' where each side accepts
    seconds (e.g. '90', '12.5'), 'M:SS', or 'H:MM:SS'. '#' starts a comment.
    Returns ranges sorted and merged; errors list per offending line.
    """
    ranges: list[tuple[float, float]] = []
    errors: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        sep = "-" if "-" in line else ("→" if "→" in line else None)
        if sep is None:
            errors.append(raw)
            continue
        idx = line.rfind(sep)
        a, b = line[:idx], line[idx + len(sep):]
        s = _parse_timestamp(a)
        e = _parse_timestamp(b)
        if s is None or e is None or e <= s:
            errors.append(raw)
            continue
        ranges.append((s, e))
    ranges.sort()
    merged: list[tuple[float, float]] = []
    for s, e in ranges:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged, errors


def _subtract_protected(
    silences: list[tuple[float, float]],
    protected: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Remove protected sub-intervals from each silence; split when needed."""
    if not protected:
        return list(silences)
    out: list[tuple[float, float]] = []
    for s, e in silences:
        chunks = [(s, e)]
        for ps, pe in protected:
            new_chunks: list[tuple[float, float]] = []
            for cs, ce in chunks:
                if pe <= cs or ps >= ce:
                    new_chunks.append((cs, ce))
                    continue
                if ps > cs:
                    new_chunks.append((cs, ps))
                if pe < ce:
                    new_chunks.append((pe, ce))
            chunks = new_chunks
            if not chunks:
                break
        out.extend(chunks)
    return out


def _probe_duration(file_path: str) -> float | None:
    try:
        result = subprocess.run(
            [ffprobe_path, "-v", "quiet", "-print_format", "json",
             "-show_format", file_path],
            capture_output=True, text=True, timeout=30, **_WIN_FLAGS,
        )
        return float(json.loads(result.stdout)["format"]["duration"])
    except Exception:
        return None


def detect_silences(
    file_path: str,
    noise_db: float = -30.0,
    min_duration: float = 0.5,
    job_id: str | None = None,
) -> list[tuple[float, float]] | None:
    """Run ffmpeg silencedetect and return list of (start, end) silence ranges in seconds."""
    cmd = [
        ffmpeg_path, "-hide_banner", "-nostats", "-i", file_path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
        "-f", "null", "-",
    ]
    jid = job_id or str(uuid.uuid4())
    try:
        proc = tracked_run(
            cmd, jid, capture_output=True, timeout=3600, **_WIN_FLAGS,
        )
    except subprocess.CalledProcessError:
        return None

    text = (proc.stderr.decode("utf-8", errors="replace")
            if isinstance(proc.stderr, (bytes, bytearray)) else (proc.stderr or ""))

    starts = [float(m.group(1)) for m in _SILENCE_START_RE.finditer(text)]
    ends   = [float(m.group(1)) for m in _SILENCE_END_RE.finditer(text)]

    silences: list[tuple[float, float]] = []
    duration = _probe_duration(file_path)
    for i, s in enumerate(starts):
        if i < len(ends):
            silences.append((s, ends[i]))
        elif duration is not None:
            silences.append((s, duration))
    return silences


def _kept_ranges(
    silences: list[tuple[float, float]],
    duration: float,
    padding: float = 0.0,
) -> list[tuple[float, float]]:
    """Compute loud ranges between silences. *padding* keeps a margin of silence on each cut edge."""
    kept: list[tuple[float, float]] = []
    cursor = 0.0
    for s_start, s_end in silences:
        keep_end   = max(cursor, s_start + padding)
        next_start = max(keep_end, s_end - padding)
        if keep_end > cursor:
            kept.append((cursor, keep_end))
        cursor = next_start
    if cursor < duration:
        kept.append((cursor, duration))
    return [(a, b) for a, b in kept if b - a > 0.02]


def remove_silence(
    file_path: str,
    noise_db: float = -30.0,
    min_duration: float = 0.5,
    padding: float = 0.05,
    output_dir: str | None = None,
    protected_ranges: list[tuple[float, float]] | None = None,
) -> tuple[bool, str | None, dict]:
    """Detect silences and re-encode keeping only loud parts.

    Returns (success, output_path, stats) where stats has:
      orig_duration, new_duration, silences_removed.
    """
    ext = os.path.splitext(file_path)[1].lower()
    is_audio = ext in _AUDIO_EXTS
    is_video = ext in _VIDEO_EXTS
    if not (is_audio or is_video):
        return False, None, {}

    duration = _probe_duration(file_path)
    if duration is None or duration <= 0:
        return False, None, {}

    job_id = str(uuid.uuid4())
    silences = detect_silences(file_path, noise_db, min_duration, job_id) or []
    effective_silences = _subtract_protected(silences, protected_ranges or [])
    effective_silences.sort()
    kept = _kept_ranges(effective_silences, duration, padding)
    if not kept:
        return False, None, {
            "orig_duration": duration, "new_duration": 0.0,
            "silences_removed": len(silences),
        }

    base, ext_with_dot = os.path.splitext(os.path.basename(file_path))
    out_dir = output_dir or os.path.dirname(file_path) or "."
    output_path = os.path.join(out_dir, f"{base}_jumpcut{ext_with_dot}")

    parts: list[str] = []
    labels: list[str] = []
    for i, (s, e) in enumerate(kept):
        if is_video:
            parts.append(
                f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}];"
                f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]"
            )
            labels.append(f"[v{i}][a{i}]")
        else:
            parts.append(
                f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]"
            )
            labels.append(f"[a{i}]")

    n = len(kept)
    if is_video:
        concat = f"{''.join(labels)}concat=n={n}:v=1:a=1[v][a]"
        filter_complex = ";".join(parts) + ";" + concat
        cmd = [
            ffmpeg_path, "-y", "-i", file_path,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            output_path,
        ]
    else:
        concat = f"{''.join(labels)}concat=n={n}:v=0:a=1[a]"
        filter_complex = ";".join(parts) + ";" + concat
        codec_map = {
            ".mp3": "libmp3lame", ".wav": "pcm_s16le", ".aac": "aac",
            ".flac": "flac", ".ogg": "libvorbis", ".m4a": "aac",
        }
        cmd = [
            ffmpeg_path, "-y", "-i", file_path,
            "-filter_complex", filter_complex,
            "-map", "[a]",
            "-c:a", codec_map.get(ext, "copy"),
            output_path,
        ]

    try:
        tracked_run(cmd, job_id, check=True, capture_output=True, timeout=7200, **_WIN_FLAGS)
    except subprocess.CalledProcessError:
        return False, None, {}

    new_duration = sum(e - s for s, e in kept)
    return True, output_path, {
        "orig_duration": duration,
        "new_duration": new_duration,
        "silences_removed": len(effective_silences),
        "silences_detected": len(silences),
        "protected_ranges": len(protected_ranges or []),
    }
