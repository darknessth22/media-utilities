"""System-wide hotkey registration (Windows).

Qt's ``QShortcut`` only fires while the application has keyboard focus — even
``ApplicationShortcut`` context does nothing once the window is minimised or
another app is in front (measured: both contexts delivered zero events while
minimised). A shortcut that has to work while Videl sits in the tray therefore
has to be registered with the OS.

Windows' ``RegisterHotKey`` claims a combination **exclusively**: no other
application receives it while the registration is live, and registration fails
outright if something else already holds it. That is why the default is
Ctrl+Shift+B rather than plain Ctrl+B — Ctrl+B is bold in every word processor
and the bookmarks bar in browsers.

No-ops on non-Windows platforms, so callers need no guards of their own.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QObject

_IS_WINDOWS = sys.platform == "win32"

# WinUser.h
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000       # do not re-fire while the key is held down
WM_HOTKEY = 0x0312

_MOD_NAMES = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "meta": MOD_WIN,
}


def parse_sequence(sequence: str) -> tuple[int, int] | None:
    """"Ctrl+Shift+B" -> (modifiers, virtual-key). None if unparseable.

    Only single-character keys and F1-F24 are supported, which covers every
    hotkey this app needs.
    """
    parts = [p.strip().lower() for p in sequence.split("+") if p.strip()]
    if not parts:
        return None
    mods = 0
    key = None
    for part in parts:
        if part in _MOD_NAMES:
            mods |= _MOD_NAMES[part]
        elif key is None:
            key = part
        else:
            return None          # two non-modifier keys
    if not key:
        return None
    if len(key) == 1:
        return mods, ord(key.upper())
    if key.startswith("f") and key[1:].isdigit():
        number = int(key[1:])
        if 1 <= number <= 24:
            return mods, 0x70 + number - 1   # VK_F1 = 0x70
    return None


class GlobalHotkey(QObject):
    """One OS-level hotkey, delivered to a Python callback.

    Usage::

        self._hotkey = GlobalHotkey(self)
        self._hotkey.register("Ctrl+Shift+B", self._pick_screen_color)

    ``register`` returns False when the platform is unsupported, the sequence
    cannot be parsed, or another application already owns the combination —
    callers should treat that as "the in-app shortcut still works" rather than
    as an error.
    """

    _next_id = 1

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._id: int | None = None
        self._callback: Callable[[], None] | None = None
        self._filter: _HotkeyEventFilter | None = None
        self._sequence: str = ""

    @property
    def sequence(self) -> str:
        """The registered sequence, or "" when nothing is registered."""
        return self._sequence if self._id is not None else ""

    def register(self, sequence: str, callback: Callable[[], None]) -> bool:
        self.unregister()
        if not _IS_WINDOWS:
            return False
        parsed = parse_sequence(sequence)
        if parsed is None:
            return False
        mods, vk = parsed

        hotkey_id = GlobalHotkey._next_id
        GlobalHotkey._next_id += 1

        # hwnd=None registers against the calling THREAD, so the message
        # arrives even when no window is visible — which is the whole point.
        # MOD_NOREPEAT stops a held key firing continuously.
        try:
            ok = ctypes.windll.user32.RegisterHotKey(
                None, hotkey_id, mods | MOD_NOREPEAT, vk
            )
        except Exception:
            return False
        if not ok:
            return False

        self._id = hotkey_id
        self._callback = callback
        self._sequence = sequence
        self._filter = _HotkeyEventFilter(hotkey_id, self._fire)
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._filter)
        return True

    def _fire(self) -> None:
        if self._callback is not None:
            self._callback()

    # Removed filters are parked here rather than dropped. PySide6 does not
    # take ownership of a QAbstractNativeEventFilter, so releasing the last
    # Python reference can free an object Qt still touches during shutdown —
    # which manifested as the interpreter hanging after every test passed.
    _retired: list = []

    def unregister(self) -> None:
        if self._filter is not None:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.removeNativeEventFilter(self._filter)
            GlobalHotkey._retired.append(self._filter)
            self._filter = None
        if self._id is not None and _IS_WINDOWS:
            try:
                ctypes.windll.user32.UnregisterHotKey(None, self._id)
            except Exception:
                pass
        self._id = None
        self._callback = None
        self._sequence = ""


class _HotkeyEventFilter(QAbstractNativeEventFilter):
    """Turns WM_HOTKEY for one id into a Python call."""

    def __init__(self, hotkey_id: int, on_fire: Callable[[], None]) -> None:
        super().__init__()
        self._id = hotkey_id
        self._on_fire = on_fire

    def nativeEventFilter(self, event_type, message):
        try:
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == WM_HOTKEY and int(msg.wParam) == self._id:
                self._on_fire()
        except Exception:
            # A malformed message must never break event delivery.
            pass
        return False, 0
