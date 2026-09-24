"""Always On Top (core/window_tools.py)."""
from __future__ import annotations

import os
import sys

import pytest

pytest.importorskip("PySide6")

_WINDOWS = sys.platform == "win32"
# NOT offscreen for this module: that platform hands out fake window handles
# (winId() == 1), so there is no real HWND to pin and every call correctly
# reports failure. These tests need a genuine window manager.
_OFFSCREEN = os.environ.get("QT_QPA_PLATFORM") == "offscreen"

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


def test_everything_is_safe_with_a_zero_handle():
    """Callers pass whatever GetForegroundWindow returned, including 0."""
    from core import window_tools as wt

    assert wt.is_window(0) is False
    assert wt.is_topmost(0) is False
    assert wt.set_topmost(0, True) is False
    assert wt.toggle_topmost(0) is None
    assert wt.window_title(0) == ""


@pytest.mark.skipif(not _WINDOWS, reason="SetWindowPos is Windows-only")
@pytest.mark.skipif(_OFFSCREEN, reason="offscreen has no real HWNDs")
def test_pin_unpin_and_toggle(app):
    from core import window_tools as wt

    widget = QWidget()
    widget.setWindowTitle("pin target")
    widget.show()
    app.processEvents()
    hwnd = int(widget.winId())
    try:
        assert wt.is_window(hwnd)
        assert wt.is_topmost(hwnd) is False

        assert wt.set_topmost(hwnd, True) is True
        assert wt.is_topmost(hwnd) is True

        assert wt.set_topmost(hwnd, False) is True
        assert wt.is_topmost(hwnd) is False

        assert wt.toggle_topmost(hwnd) is True
        assert wt.is_topmost(hwnd) is True
        assert wt.toggle_topmost(hwnd) is False
        assert wt.is_topmost(hwnd) is False
    finally:
        wt.set_topmost(hwnd, False)
        widget.close()


@pytest.mark.skipif(not _WINDOWS, reason="SetWindowPos is Windows-only")
@pytest.mark.skipif(_OFFSCREEN, reason="offscreen has no real HWNDs")
def test_a_closed_window_is_reported_stale(app):
    """Pinned handles outlive their windows; acting on one must not crash."""
    from core import window_tools as wt

    widget = QWidget()
    widget.show()
    app.processEvents()
    hwnd = int(widget.winId())
    widget.close()
    widget.deleteLater()
    app.processEvents()

    assert wt.is_window(hwnd) is False
    assert wt.toggle_topmost(hwnd) is None
