"""Resolve paths to data files for development and PyInstaller bundles."""
from __future__ import annotations

import os
import sys


def resource_path(*parts: str) -> str:
    """Return an absolute path to a resource next to the app root.

    Development: ``<project>/`` (parent of ``core/``).
    Frozen (PyInstaller): ``sys._MEIPASS`` where bundled ``datas`` are extracted.
    """
    rel = os.path.join(*parts) if parts else ""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, rel)
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def browser_extension_dir() -> str:
    """Resolve the user-facing path to the bundled browser extension.

    The Inno installer places ``browser_extension/`` next to ``Videl.exe`` so
    the user can find it even after Videl is closed. PyInstaller also places
    a copy under ``_MEIPASS`` (used in dev/onedir runs). Prefer the persistent
    location next to the executable when running frozen.
    """
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidate = os.path.join(exe_dir, "browser_extension")
        if os.path.isdir(candidate):
            return candidate
    return resource_path("browser_extension")
