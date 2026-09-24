"""Windows window-management helpers (Always On Top).

Thin ctypes wrappers around user32. Everything is a no-op returning a falsy
value off Windows, so callers need no platform guards.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

_IS_WINDOWS = sys.platform == "win32"

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008


def _user32():
    return ctypes.windll.user32 if _IS_WINDOWS else None


def foreground_window() -> int | None:
    """HWND of the window the user is currently working in, or None."""
    if not _IS_WINDOWS:
        return None
    try:
        hwnd = _user32().GetForegroundWindow()
    except Exception:
        return None
    return int(hwnd) or None


def window_title(hwnd: int) -> str:
    if not _IS_WINDOWS or not hwnd:
        return ""
    try:
        user32 = _user32()
        length = user32.GetWindowTextLengthW(wintypes.HWND(hwnd))
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(wintypes.HWND(hwnd), buf, length + 1)
        return buf.value
    except Exception:
        return ""


def is_window(hwnd: int) -> bool:
    """False once the window has been closed — pinned handles go stale."""
    if not _IS_WINDOWS or not hwnd:
        return False
    try:
        return bool(_user32().IsWindow(wintypes.HWND(hwnd)))
    except Exception:
        return False


def is_topmost(hwnd: int) -> bool:
    """Read the actual WS_EX_TOPMOST bit rather than trusting our own record.

    Another application (or the user) can change this behind our back, so the
    window itself is the source of truth.
    """
    if not _IS_WINDOWS or not hwnd:
        return False
    try:
        user32 = _user32()
        # GetWindowLongPtrW is absent on 32-bit Python; GetWindowLongW is the
        # documented fallback and carries the same flags.
        getter = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
        return bool(int(getter(wintypes.HWND(hwnd), GWL_EXSTYLE)) & WS_EX_TOPMOST)
    except Exception:
        return False


def set_topmost(hwnd: int, pinned: bool) -> bool:
    """Pin or unpin *hwnd*. Returns True when the change took effect."""
    if not _IS_WINDOWS or not hwnd or not is_window(hwnd):
        return False
    try:
        _user32().SetWindowPos(
            wintypes.HWND(hwnd),
            wintypes.HWND(HWND_TOPMOST if pinned else HWND_NOTOPMOST),
            0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )
    except Exception:
        return False
    return is_topmost(hwnd) == pinned


def toggle_topmost(hwnd: int) -> bool | None:
    """Flip the pin state. Returns the new state, or None on failure."""
    if not is_window(hwnd):
        return None
    target = not is_topmost(hwnd)
    return target if set_topmost(hwnd, target) else None
