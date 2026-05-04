"""Locate the bundled embeddable Python interpreter shipped under runtime/python/."""
from __future__ import annotations

import os
import sys


class BundledRuntimeMissingError(RuntimeError):
    """Raised when the embeddable Python is expected but not found."""


def _candidate_dirs() -> list[str]:
    dirs: list[str] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(meipass)
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        dirs.append(exe_dir)
        # PyInstaller 6+ places COLLECT datas under `_internal/` next to the exe.
        dirs.append(os.path.join(exe_dir, "_internal"))
    dirs.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return dirs


def bundled_python_path() -> str:
    """Return abs path to the bundled python.exe.

    Frozen: looks under runtime/python/python.exe relative to the install dir
    (and _MEIPASS for one-file mode). Dev: same lookup, falls back to
    sys.executable so devs can run without provisioning runtime/.
    """
    exe = "python.exe" if sys.platform == "win32" else "python"
    for base in _candidate_dirs():
        path = os.path.join(base, "runtime", "python", exe)
        if os.path.isfile(path):
            return path
    if not getattr(sys, "frozen", False):
        return sys.executable
    raise BundledRuntimeMissingError(
        "Bundled Python runtime not found under runtime/python/"
    )
