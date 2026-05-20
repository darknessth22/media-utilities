"""Capture crash logs from failed subprocesses (FFmpeg / Whisper / Demucs / etc).

When an external tool fails, the raw stderr is the only useful diagnostic. The
rest of the app shows the user a short message; this module preserves the last
~50 lines of the real output, writes it to a timestamped ``.txt`` file, and
keeps the most recent crash in memory so the GUI can offer a "Show Raw Logs"
button with copy-to-clipboard.

Crash files live next to ``app.log`` (see ``utils.app_logger``) and are pruned
to the most recent ``_MAX_CRASH_FILES``. All output is run through
``mask_credentials`` before being written to disk.
"""
from __future__ import annotations

import os
import subprocess
import threading
import traceback
from datetime import datetime

from utils.app_logger import get_log_path, get_logger, mask_credentials

_LOCK = threading.Lock()
_last_crash: dict | None = None
_MAX_CRASH_FILES = 30
_TAIL_LINES = 50


def crash_log_dir() -> str:
    """Directory holding crash ``.txt`` files (next to ``app.log``)."""
    d = os.path.join(os.path.dirname(str(get_log_path())), "crash")
    os.makedirs(d, exist_ok=True)
    return d


def tail_text(text: str, n: int = _TAIL_LINES) -> str:
    """Return the last *n* lines of *text*, newline-normalised and stripped."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    return "\n".join(lines[-n:]).strip()


def _decode(data) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


def _prune_old() -> None:
    try:
        directory = crash_log_dir()
        files = [
            os.path.join(directory, f)
            for f in os.listdir(directory)
            if f.startswith("crash_") and f.endswith(".txt")
        ]
        files.sort(key=os.path.getmtime, reverse=True)
        for stale in files[_MAX_CRASH_FILES:]:
            try:
                os.remove(stale)
            except OSError:
                pass
    except OSError:
        pass


def record_crash(source, output, *, cmd=None, returncode=None) -> str | None:
    """Write the last 50 lines of *output* to a timestamped crash file.

    *source* — human label, e.g. ``"FFmpeg (convert)"`` or ``"Whisper"``.
    Returns the crash file path, or ``None`` if writing to disk failed (the
    crash is still kept in memory either way).
    """
    global _last_crash
    body = tail_text(mask_credentials(_decode(output)))
    if not body:
        body = "(no output was captured from the failed process)"
    now = datetime.now()

    cmd_str = ""
    if cmd:
        try:
            raw = " ".join(str(c) for c in cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
            cmd_str = mask_credentials(raw)
        except Exception:
            cmd_str = ""

    header = (
        "Videl crash log\n"
        f"Source     : {source}\n"
        f"Time       : {now.isoformat(timespec='seconds')}\n"
    )
    if returncode is not None:
        header += f"Exit code  : {returncode}\n"
    if cmd_str:
        header += f"Command    : {cmd_str}\n"
    header += "-" * 60 + "\n"
    full = header + body + "\n"

    path: str | None = None
    try:
        path = os.path.join(crash_log_dir(), f"crash_{now:%Y%m%d_%H%M%S}.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(full)
        _prune_old()
    except OSError:
        path = None

    with _LOCK:
        _last_crash = {
            "source": str(source),
            "time": now,
            "path": path,
            "text": full,
        }

    try:
        get_logger().error("Crash recorded [%s] -> %s", source, path)
    except Exception:
        pass
    return path


def record_exception(source, exc, cmd=None) -> str | None:
    """Record a crash from an exception, pulling subprocess stderr when present.

    Handles ``CalledProcessError`` and ``TimeoutExpired`` specially so the real
    FFmpeg/Whisper output is preserved instead of just ``str(exc)``. Any other
    exception falls back to its formatted traceback.
    """
    output = ""
    returncode = None
    if isinstance(exc, subprocess.CalledProcessError):
        output = _decode(exc.stderr) or _decode(exc.output)
        returncode = exc.returncode
    elif isinstance(exc, subprocess.TimeoutExpired):
        output = _decode(exc.stderr) or _decode(exc.output)
        output = (output + f"\n\n[Process timed out after {exc.timeout}s]").strip()
    if not output:
        output = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return record_crash(source, output, cmd=cmd, returncode=returncode)


def last_crash() -> dict | None:
    """Return a copy of the most recent crash dict, or ``None``."""
    with _LOCK:
        return dict(_last_crash) if _last_crash else None


def has_recent_crash() -> bool:
    """True if a crash has been recorded this session."""
    with _LOCK:
        return _last_crash is not None


def clear_last_crash() -> None:
    """Forget the in-memory crash (files on disk are kept)."""
    global _last_crash
    with _LOCK:
        _last_crash = None
