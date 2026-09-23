"""OS-level hotkey registration (core/hotkey.py).

Qt shortcuts need keyboard focus: measured on Windows, both WindowShortcut and
ApplicationShortcut deliver nothing once the window is minimised. A shortcut
that must work while Videl sits in the tray has to go through the OS.
"""
from __future__ import annotations

import os
import sys

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

_WINDOWS = sys.platform == "win32"


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    "sequence,expected",
    [
        ("Ctrl+Shift+B", (0x0002 | 0x0004, ord("B"))),
        ("Ctrl+B", (0x0002, ord("B"))),
        ("Alt+Shift+K", (0x0001 | 0x0004, ord("K"))),
        ("F5", (0, 0x74)),
        ("Ctrl+F12", (0x0002, 0x7B)),
    ],
)
def test_sequence_parsing(sequence, expected):
    from core.hotkey import parse_sequence

    assert parse_sequence(sequence) == expected


@pytest.mark.parametrize("bad", ["", "Ctrl+", "Ctrl+A+B", "Ctrl+F99", "Ctrl+Escape"])
def test_unparseable_sequences_return_none(bad):
    """register() must refuse rather than claim the wrong combination."""
    from core.hotkey import parse_sequence

    assert parse_sequence(bad) is None


@pytest.mark.skipif(not _WINDOWS, reason="RegisterHotKey is Windows-only")
def test_register_and_release(app):
    """A leaked registration reserves the combo until the process dies."""
    from core.hotkey import GlobalHotkey

    hotkey = GlobalHotkey()
    assert hotkey.sequence == ""
    assert hotkey.register("Ctrl+Alt+F9", lambda: None) is True
    assert hotkey.sequence == "Ctrl+Alt+F9"

    hotkey.unregister()
    assert hotkey.sequence == ""

    # Registering the same combination again proves the release was real.
    other = GlobalHotkey()
    assert other.register("Ctrl+Alt+F9", lambda: None) is True
    other.unregister()


@pytest.mark.skipif(not _WINDOWS, reason="RegisterHotKey is Windows-only")
def test_a_taken_combination_fails_cleanly(app):
    """Returning False lets the caller fall back to the in-app shortcut."""
    from core.hotkey import GlobalHotkey

    first = GlobalHotkey()
    assert first.register("Ctrl+Alt+F10", lambda: None) is True
    try:
        second = GlobalHotkey()
        assert second.register("Ctrl+Alt+F10", lambda: None) is False
        assert second.sequence == ""
    finally:
        first.unregister()


def test_unregister_is_safe_when_nothing_is_registered():
    from core.hotkey import GlobalHotkey

    GlobalHotkey().unregister()      # must not raise


def test_global_hotkey_is_not_plain_ctrl_b():
    """RegisterHotKey is EXCLUSIVE — it takes the combo from every other app.

    Ctrl+B is bold in word processors and the bookmarks bar in browsers, so
    the global binding deliberately differs from the in-app one.
    """
    from gui.app import _GLOBAL_PICK_HOTKEY

    assert _GLOBAL_PICK_HOTKEY != "Ctrl+B"
    assert "Shift" in _GLOBAL_PICK_HOTKEY
