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


_HW_ENCODER_IDS = {
    "h264_nvenc": "nvidia",
    "h264_amf": "amd",
    "h264_qsv": "intel",
}


def detect_hw_encoders() -> set[str]:
    """Return set of available HW encoder keys: 'nvidia', 'amd', 'intel'.

    Runs `ffmpeg -encoders` once; silently returns empty set on any failure.
    """
    import subprocess
    try:
        flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
        result = subprocess.run(
            [ffmpeg_path, "-encoders"],
            capture_output=True, text=True, timeout=10, **flags,
        )
        available: set[str] = set()
        for line in result.stdout.splitlines():
            for enc_id, label in _HW_ENCODER_IDS.items():
                if enc_id in line:
                    available.add(label)
        return available
    except Exception:
        return set()
