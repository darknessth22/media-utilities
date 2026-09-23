"""Click-to-record shortcut widget and the settings wiring."""
from __future__ import annotations

import os
import tempfile

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QShortcut  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


def _record(button, key, mods=Qt.KeyboardModifier.NoModifier):
    button.setChecked(True)
    button._toggle_recording()
    button.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, mods))


@pytest.mark.parametrize(
    "key,mods,expected",
    [
        (Qt.Key.Key_P, Qt.KeyboardModifier.ControlModifier, "Ctrl+P"),
        (Qt.Key.Key_B,
         Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
         "Ctrl+Shift+B"),
        (Qt.Key.Key_F5, Qt.KeyboardModifier.NoModifier, "F5"),
        (Qt.Key.Key_A, Qt.KeyboardModifier.AltModifier, "Alt+A"),
    ],
)
def test_capture(app, key, mods, expected):
    from gui.widgets.keybind_editor import KeybindButton

    button = KeybindButton("Ctrl+K")
    got = []
    button.captured.connect(got.append)
    _record(button, key, mods)
    assert got == [expected]


def test_a_bare_modifier_does_not_end_capture(app):
    """Holding Ctrl before the real key must not register "Ctrl"."""
    from gui.widgets.keybind_editor import KeybindButton

    button = KeybindButton("Ctrl+K")
    got = []
    button.captured.connect(got.append)
    _record(button, Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier)
    assert got == []
    assert button._recording, "still waiting for the real key"
    button._stop()


def test_escape_cancels_and_backspace_resets(app):
    from gui.widgets.keybind_editor import KeybindButton

    button = KeybindButton("Ctrl+K")
    got = []
    button.captured.connect(got.append)

    _record(button, Qt.Key.Key_Escape)
    assert got == [] and not button._recording
    assert button.sequence() == "Ctrl+K", "cancel must not change the binding"

    _record(button, Qt.Key.Key_Backspace)
    assert got == [""], "empty means 'restore the default'"


def test_rebinding_applies_live_and_persists(app, monkeypatch):
    """The settings page emits the SAME settings object it was handed.

    Comparing old-vs-new keybinds is therefore one dict compared with itself
    and never differs — MainWindow has to compare the RESOLVED maps instead,
    or a rebind saves to disk but never takes effect until a restart.
    """
    monkeypatch.setenv("APPDATA", tempfile.mkdtemp())

    from core.keybinds import action
    from core.settings import SettingsManager
    from gui.app import MainWindow
    from gui.theme import ThemeManager

    window = MainWindow(SettingsManager.load(), ThemeManager(app))
    app.processEvents()
    try:
        section = window._settings_section_widget
        assert section._keybind_buttons, "a row per action"

        def sequences():
            return [s.key().toString() for s in window.findChildren(QShortcut)]

        assert "Ctrl+K" in sequences()

        section._on_keybind_captured(action("quick_search"), "Ctrl+P")
        app.processEvents()

        assert "Ctrl+P" in sequences(), "the new binding must be live"
        assert "Ctrl+K" not in sequences(), "the old one must be gone"
        assert window.settings.keybinds == {"quick_search": "Ctrl+P"}

        # And it survives a fresh load from disk.
        assert SettingsManager.load().keybinds == {"quick_search": "Ctrl+P"}

        section._reset_all_keybinds()
        app.processEvents()
        assert "Ctrl+K" in sequences() and "Ctrl+P" not in sequences()
    finally:
        # Close AND unregister: two live MainWindows with an OS hotkey and a
        # native event filter still installed hang interpreter shutdown.
        window._screen_pick_hotkey.unregister()
        window.close()
        window.deleteLater()
        app.processEvents()


def test_rebinding_does_not_leak_shortcuts(app, monkeypatch):
    """Old QShortcuts must be destroyed, not just shadowed."""
    monkeypatch.setenv("APPDATA", tempfile.mkdtemp())

    from core.settings import SettingsManager
    from gui.app import MainWindow
    from gui.theme import ThemeManager

    window = MainWindow(SettingsManager.load(), ThemeManager(app))
    app.processEvents()
    try:
        before = len(window.findChildren(QShortcut))
        for _ in range(3):
            window._apply_keybinds()
            app.processEvents()
        assert len(window.findChildren(QShortcut)) == before
    finally:
        # Close AND unregister: two live MainWindows with an OS hotkey and a
        # native event filter still installed hang interpreter shutdown.
        window._screen_pick_hotkey.unregister()
        window.close()
        window.deleteLater()
        app.processEvents()
