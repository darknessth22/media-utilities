"""Temporary file janitor — tracks and cleans up intermediate processing files.

Register files with track() during processing; they are deleted by cleanup()
or automatically on application exit via atexit.
"""
from __future__ import annotations

import atexit
import os
import threading
from utils.app_logger import get_logger

_lock = threading.Lock()
_tracked: set[str] = set()
_log = get_logger()


def track(*paths: str) -> None:
    """Register one or more file paths for cleanup."""
    with _lock:
        for p in paths:
            if p:
                _tracked.add(p)


def release(*paths: str) -> None:
    """Un-track paths that were intentionally kept (e.g. final output)."""
    with _lock:
        for p in paths:
            _tracked.discard(p)


def cleanup(*paths: str) -> int:
    """Delete specific tracked paths now. Returns number of files deleted."""
    to_delete = []
    with _lock:
        for p in paths:
            if p in _tracked:
                _tracked.discard(p)
                to_delete.append(p)

    deleted = 0
    for p in to_delete:
        try:
            os.remove(p)
            deleted += 1
        except OSError as exc:
            _log.warning("Janitor could not delete %r: %s", p, exc)
    return deleted


def cleanup_all() -> int:
    """Delete every tracked file. Called at application exit."""
    with _lock:
        to_delete = list(_tracked)
        _tracked.clear()

    deleted = 0
    for p in to_delete:
        try:
            os.remove(p)
            deleted += 1
        except OSError:
            pass
    return deleted


atexit.register(cleanup_all)
