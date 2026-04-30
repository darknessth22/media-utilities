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
