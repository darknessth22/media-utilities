"""Zoom & Draw overlay, the new shortcuts, and the guide entries for them."""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6.QtWidgets")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt              # noqa: E402
from PySide6.QtWidgets import QApplication          # noqa: E402

from gui.widgets import screen_zoom                 # noqa: E402
from gui.widgets.screen_zoom import ScreenZoom, visible_origin   # noqa: E402


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


# ── Transform ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("zoom", [1.0, 2.0, 3.7, 8.0])
@pytest.mark.parametrize("cursor", [(0, 0), (960, 540), (1919, 1079), (300, 900)])
def test_point_under_cursor_stays_under_cursor(zoom, cursor):
    """The one property that makes zoom feel right: no jump as you scroll."""
    origin = QPointF(0, 0)
    c = QPointF(*cursor)
    view = visible_origin(c, origin, zoom)
    on_screen = origin + (c - view) * zoom
    assert abs(on_screen.x() - c.x()) < 1e-6 and abs(on_screen.y() - c.y()) < 1e-6


def test_desktop_edges_are_reachable():
    """Cursor at a screen corner shows that corner of the desktop."""
    origin = QPointF(0, 0)
    assert visible_origin(QPointF(0, 0), origin, 4.0) == QPointF(0, 0)
    bottom_right = QPointF(1920, 1080)
    view = visible_origin(bottom_right, origin, 4.0)
    # Visible slice is 480x270 and must end exactly at the desktop corner.
    assert abs(view.x() + 480 - 1920) < 1e-6 and abs(view.y() + 270 - 1080) < 1e-6


# ── Overlay behaviour ────────────────────────────────────────────────────────

@pytest.fixture()
def overlay(app):
    widget = ScreenZoom()
    yield widget
    widget.close()


def test_zoom_is_clamped(overlay):
    overlay.set_zoom(100)
    assert overlay._zoom == screen_zoom.MAX_ZOOM
    overlay.set_zoom(0.01)
    assert overlay._zoom == screen_zoom.MIN_ZOOM


def test_strokes_are_stored_in_desktop_coordinates(overlay):
    """So a circle drawn around a button stays around it when you zoom."""
    overlay.set_zoom(2.0)
    overlay._cursor = QPointF(overlay._region.center())
    before = overlay.to_desktop(QPointF(overlay._region.center()))

    overlay.set_zoom(4.0)
    # Same screen point, different zoom -> the SAME desktop point, because the
    # cursor anchors the view.
    after = overlay.to_desktop(QPointF(overlay._region.center()))
    assert abs(before.x() - after.x()) < 1e-6


def _key(key, mods=Qt.KeyboardModifier.NoModifier):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    return QKeyEvent(QEvent.Type.KeyPress, key, mods)


def _mouse(kind, pos, button=Qt.MouseButton.LeftButton, buttons=None):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    kinds = {"press": QEvent.Type.MouseButtonPress,
             "move": QEvent.Type.MouseMove,
             "release": QEvent.Type.MouseButtonRelease}
    held = buttons if buttons is not None else (
        button if kind != "release" else Qt.MouseButton.NoButton)
    return QMouseEvent(kinds[kind], pos, pos, pos,
                       Qt.MouseButton.NoButton if kind == "move" else button,
                       held, Qt.KeyboardModifier.NoModifier)


def _drag(overlay, start, end, steps=8, button=Qt.MouseButton.LeftButton):
    overlay.mousePressEvent(_mouse("press", start, button))
    for i in range(1, steps + 1):
        t = i / steps
        p = QPointF(start.x() + (end.x() - start.x()) * t,
                    start.y() + (end.y() - start.y()) * t)
        overlay.mouseMoveEvent(_mouse("move", p, buttons=button))
    overlay.mouseReleaseEvent(_mouse("release", end, button))


def test_moving_the_mouse_does_not_pan(overlay):
    """What the user asked for: zoom holds still until you choose to move it."""
    overlay.set_zoom(3.0, QPointF(overlay._region.center()))
    view = QPointF(overlay._view)
    c = QPointF(overlay._region.center())
    for dx in (-300, 250, 400):
        overlay.mouseMoveEvent(_mouse("move", c + QPointF(dx, dx / 2),
                                      buttons=Qt.MouseButton.NoButton))
    assert overlay._view == view


def test_drawing_while_zoomed_does_not_move_the_view(overlay):
    overlay.set_zoom(4.0, QPointF(overlay._region.center()))
    view = QPointF(overlay._view)
    c = QPointF(overlay._region.center())
    _drag(overlay, c, c + QPointF(200, 120))
    assert overlay._view == view
    assert len(overlay._strokes) == 1


def test_pan_tool_moves_the_view_with_the_drag(overlay):
    overlay.set_zoom(4.0, QPointF(overlay._region.center()))
    overlay.set_tool("pan")
    view = QPointF(overlay._view)
    c = QPointF(overlay._region.center())
    _drag(overlay, c, c + QPointF(80, 40))
    # Content follows the hand: dragging right shows what was to the left.
    assert overlay._view.x() < view.x() and overlay._view.y() < view.y()
    assert overlay._strokes == [], "panning must not draw"


def test_middle_button_pans_whatever_the_tool(overlay):
    overlay.set_zoom(4.0, QPointF(overlay._region.center()))
    view = QPointF(overlay._view)
    c = QPointF(overlay._region.center())
    _drag(overlay, c, c + QPointF(-60, 0), button=Qt.MouseButton.MiddleButton)
    assert overlay._view.x() > view.x()
    assert overlay._strokes == []


def test_space_held_pans_then_returns_to_the_pen(overlay):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    overlay.set_zoom(4.0, QPointF(overlay._region.center()))
    overlay.keyPressEvent(_key(Qt.Key.Key_Space))
    view = QPointF(overlay._view)
    c = QPointF(overlay._region.center())
    _drag(overlay, c, c + QPointF(50, 0))
    assert overlay._view != view and overlay._strokes == []

    overlay.keyReleaseEvent(QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Space,
                                      Qt.KeyboardModifier.NoModifier))
    _drag(overlay, c, c + QPointF(50, 30))
    assert len(overlay._strokes) == 1, "back to drawing once Space is released"


def test_view_cannot_be_panned_off_the_desktop(overlay):
    overlay.set_zoom(2.0, QPointF(overlay._region.center()))
    overlay.pan_by(QPointF(1e6, 1e6))
    assert overlay._view == QPointF(overlay._region.topLeft())


def test_eraser_removes_the_stroke_it_touches_and_undo_brings_it_back(overlay):
    c = QPointF(overlay._region.center())
    _drag(overlay, c, c + QPointF(100, 0))
    _drag(overlay, c + QPointF(0, 300), c + QPointF(100, 300))
    assert len(overlay._strokes) == 2

    overlay.set_tool("eraser")
    _drag(overlay, c + QPointF(50, -20), c + QPointF(50, 20))
    assert len(overlay._strokes) == 1, "only the touched stroke goes"

    overlay.undo()
    assert len(overlay._strokes) == 2


def test_clear_is_undoable(overlay):
    c = QPointF(overlay._region.center())
    _drag(overlay, c, c + QPointF(100, 0))
    overlay.keyPressEvent(_key(Qt.Key.Key_C))
    assert overlay._strokes == []
    overlay.keyPressEvent(_key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier))
    assert len(overlay._strokes) == 1


def test_toolbar_reflects_colour_and_size(overlay):
    """The visual state must follow the keyboard, not just the other way."""
    overlay.keyPressEvent(_key(Qt.Key.Key_G))
    assert overlay._swatches["#22C55E"].isChecked()
    assert overlay._size_dot.colour.name().upper() == "#22C55E"

    overlay.keyPressEvent(_key(Qt.Key.Key_BracketRight))
    assert overlay._size_slider.value() == overlay._width == overlay._size_dot.width_px

    overlay.keyPressEvent(_key(Qt.Key.Key_E))
    assert overlay._tool_buttons["eraser"].isChecked()


def test_toolbar_buttons_never_take_keyboard_focus(overlay):
    """If they did, R/G/B and Esc would stop working after the first click."""
    from PySide6.QtWidgets import QPushButton, QSlider

    for w in overlay._toolbar.findChildren(QPushButton) + overlay._toolbar.findChildren(QSlider):
        assert w.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_escape_closes_and_emits(overlay):
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent

    fired = []
    overlay.closed.connect(lambda: fired.append(True))
    overlay.start()
    overlay.keyPressEvent(_key(Qt.Key.Key_Escape))
    assert fired and not overlay.isVisible()


def test_overlay_never_grabs_input(overlay):
    """A system-wide grab that is not released froze the whole desktop once."""
    from PySide6.QtWidgets import QWidget

    overlay.start()
    assert QWidget.mouseGrabber() is not overlay
    assert QWidget.keyboardGrabber() is not overlay


# ── Shortcuts ─────────────────────────────────────────────────────────────────

def test_section_jumps_open_the_section_they_are_named_after():
    """Ctrl+9 said History but was hardcoded to index 15 — Vocal Isolator."""
    from core.keybinds import SECTION_JUMP_TARGETS
    from gui.app import _SECTIONS_META

    ids = {m["id"] for m in _SECTIONS_META}
    assert SECTION_JUMP_TARGETS["section_9"] == "history"
    for target in SECTION_JUMP_TARGETS.values():
        assert target in ids, target


def test_new_shortcuts_have_no_conflicts():
    from core.keybinds import action, conflicts, resolve

    assert action("open_folder_rules") is not None
    assert action("zoom_screen").global_hotkey
    # Redo in most editors; a global claim would break it everywhere.
    assert action("zoom_screen").default != "Ctrl+Shift+Z"
    assert not conflicts(resolve({}))


# ── Guide ─────────────────────────────────────────────────────────────────────

def test_guide_covers_the_new_features_in_both_languages():
    from gui.tabs.tutorial_section import (
        _TUTORIAL_DATA_AR, _TUTORIAL_DATA_EN, _TUTORIAL_SECTION_IDS,
    )

    assert len(_TUTORIAL_DATA_EN) == len(_TUTORIAL_DATA_AR) == len(_TUTORIAL_SECTION_IDS)
    text = " ".join(" ".join([e["title"], e["description"], *e["steps"], *e["tips"]])
                    for e in _TUTORIAL_DATA_EN)
    for shortcut in ("Ctrl+Shift+F", "Ctrl+Shift+T", "Ctrl+Shift+X",
                     "Ctrl+Alt+Z", "Ctrl+Shift+R", "Settings → Shortcuts"):
        assert shortcut in text, shortcut
    assert "folder_rules" in _TUTORIAL_SECTION_IDS
