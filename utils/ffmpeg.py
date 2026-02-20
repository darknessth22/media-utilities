"""FFmpeg and FFprobe binary location helpers."""
import os
import sys
import shutil


def _find_binary(name: str) -> str:
    """Locate a binary using a four-step fallback chain.

    Priority:
    1. PyInstaller bundle (_MEIPASS)
    2. Same directory as this script / frozen executable
    3. Current working directory (legacy)
    4. System PATH via shutil.which
    Falls back to the bare name so the OS produces a clear FileNotFoundError.
    """
    exe_name = f"{name}.exe" if sys.platform == "win32" else name

    # 1. PyInstaller bundle (onefile or onedir)
    if hasattr(sys, "_MEIPASS"):
        bundled = os.path.join(sys._MEIPASS, exe_name)
        if os.path.isfile(bundled):
            return bundled

    # 2. Same directory as this file / frozen exe
    script_dir = os.path.dirname(os.path.abspath(__file__))
    local = os.path.join(script_dir, exe_name)
    if os.path.isfile(local):
        return local

    # 3. Current working directory
    cwd = os.path.join(os.getcwd(), exe_name)
    if os.path.isfile(cwd):
        return cwd

    # 4. System PATH
    which = shutil.which(name)
    if which:
        return which

    # Bare name — callers get a clear FileNotFoundError at call time
    return exe_name


def get_ffmpeg_path() -> str:
    return _find_binary("ffmpeg")


def get_ffprobe_path() -> str:
    return _find_binary("ffprobe")


# Module-level singletons — resolved once at import time
ffmpeg_path: str = get_ffmpeg_path()
ffprobe_path: str = get_ffprobe_path()
