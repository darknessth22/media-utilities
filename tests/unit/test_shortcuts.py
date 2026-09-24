"""Application-level keyboard shortcuts."""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QShortcut  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def window():
    app = QApplication.instance() or QApplication([])
    from core.settings import SettingsManager
    from gui.app import MainWindow
    from gui.theme import ThemeManager

    win = MainWindow(SettingsManager.load(), ThemeManager(app))
    app.processEvents()
    yield win, app


def _sequences(win):
    return [s.key().toString() for s in win.findChildren(QShortcut)]


def test_no_shortcut_is_bound_twice(window):
    """Two handlers on one sequence means one of them silently never fires."""
    win, _ = window
    seqs = [s for s in _sequences(win) if s]
    dupes = sorted({s for s in seqs if seqs.count(s) > 1})
    assert not dupes, f"duplicate shortcut bindings: {dupes}"


def test_ctrl_b_opens_the_screen_colour_picker(window):
    """Ctrl+B is global on purpose.

    The point of a screen picker is to grab a colour while looking at
    something else, so it must work from any section — not only when the
    Palette tool already happens to be open.
    """
    win, app = window
    from gui.app import _section_index

    assert "Ctrl+B" in _sequences(win)

    win._navigate_to(_section_index("download"))
    app.processEvents()
    assert win._current_section == _section_index("download")

    try:
        win._pick_screen_color()
        app.processEvents()

        assert win._current_section == _section_index("palette")
        assert win._section_tab_bar.currentIndex() == 1, "colour wheel tab"
        assert win._palette_section._screen_picker is not None
    finally:
        picker = win._palette_section._screen_picker
        if picker is not None:
            picker.releaseMouse()
            picker.releaseKeyboard()
            picker.close()
            win._palette_section._screen_picker = None


def test_global_hotkey_is_registered(window):
    """Ctrl+B cannot fire while minimised — that needs an OS-level hotkey."""
    import sys

    win, _ = window
    if sys.platform != "win32":
        pytest.skip("RegisterHotKey is Windows-only")
    from gui.app import _GLOBAL_PICK_HOTKEY

    # A GlobalHotkey object must exist for the action, but the registration
    # itself can legitimately FAIL: RegisterHotKey is exclusive system-wide, so
    # if a real Videl is already running (or another app owns the combo) it
    # returns ERROR_HOTKEY_ALREADY_REGISTERED and .sequence stays "". Asserting
    # on the sequence made this test fail whenever the app was open.
    assert "pick_color_global" in win._global_hotkeys

    registered = {hk.sequence for hk in win._global_hotkeys.values() if hk.sequence}
    if registered:
        assert _GLOBAL_PICK_HOTKEY in registered
    else:
        pytest.skip("the combos are held by another process (Videl running?)")


def test_picking_does_not_raise_the_window(window):
    """The window must stay exactly as it was.

    The point of the global hotkey is to grab a colour off something you are
    already looking at, so popping Videl to the front would defeat it. The
    overlay is its own top-level window and takes focus by itself, so the
    picker works fine over a minimised app — and the colour still reaches the
    wheel and the clipboard.
    """
    from PySide6.QtGui import QColor

    win, app = window
    win.showMinimized()
    app.processEvents()

    try:
        win._pick_screen_color()
        app.processEvents()

        assert win.isMinimized(), "the window must NOT be restored"
        assert win._palette_section._screen_picker is not None

        win._palette_section._screen_picker.picked.emit(QColor("#C0FFEE"))
        app.processEvents()
        assert win.isMinimized(), "still minimised after the pick"
        assert win._palette_section._wheel.hex_color().upper() == "#C0FFEE"
        assert QApplication.clipboard().text().upper() == "#C0FFEE"
    finally:
        picker = win._palette_section._screen_picker
        if picker is not None:
            picker.releaseMouse()
            picker.releaseKeyboard()
            picker.close()
            win._palette_section._screen_picker = None


def test_hidden_pick_is_reported_through_the_tray(window, monkeypatch):
    """The status bar is invisible when the window is down.

    A pick from the global hotkey would otherwise give no feedback at all, so
    it goes to a tray toast instead — but only while hidden, or an on-screen
    pick would toast on top of the status bar it already updated.
    """
    win, app = window
    sent = []
    monkeypatch.setattr(win._tray, "notify",
                        lambda title, body, *a, **k: sent.append((title, body)))
    monkeypatch.setattr("gui.app.SystemTrayIcon.is_available", staticmethod(lambda: True))

    win.showNormal()
    app.processEvents()
    win._on_color_picked("#123456")
    assert sent == [], "a visible window already shows the status bar message"

    win.showMinimized()
    app.processEvents()
    win._on_color_picked("#123456")
    assert len(sent) == 1, "a hidden pick must surface somewhere"
    assert "#123456" in sent[0][1]


def test_shortcuts_menu_lists_both_picker_shortcuts(window):
    """The shortcuts menu is where users look — it must stay in sync.

    Ctrl+K was already missing from it before the picker was added, so this
    guards the whole table, not just the new rows.
    """
    from PySide6.QtWidgets import QMenu

    import gui.app as app_module
    from gui.app import TitleBar, _GLOBAL_PICK_HOTKEY

    win, _ = window
    bar = win.findChild(TitleBar)
    assert bar is not None

    seen: list[str] = []

    class _Spy(QMenu):
        def addAction(self, *args, **kwargs):
            if args and isinstance(args[0], str):
                seen.append(args[0])
            return super().addAction(*args, **kwargs)

        def exec(self, *args, **kwargs):
            return None

    original = app_module.QMenu
    app_module.QMenu = _Spy
    try:
        bar._on_shortcuts_btn()
    finally:
        app_module.QMenu = original

    text = "\n".join(seen)
    assert "Ctrl+B" in text
    assert _GLOBAL_PICK_HOTKEY in text
    assert "Ctrl+K" in text


@pytest.mark.parametrize("lang", ["en", "ar"])
def test_shortcut_descriptions_are_translated(lang):
    """They used to be hardcoded English, shown as-is in the Arabic UI."""
    from core.i18n import I18n, tr

    i18n = I18n.instance()
    previous = i18n.current_language
    try:
        i18n.set_language(lang)
        for key in ("sc_primary", "sc_cancel", "sc_paste", "sc_home", "sc_tools",
                    "sc_sections", "sc_search", "sc_pick", "sc_pick_global",
                    "sc_settings", "sc_guide", "sc_quit"):
            assert tr(key) != key, f"{key} missing from {lang}.json"
            assert "�" not in tr(key), f"{key} is corrupted in {lang}.json"
    finally:
        i18n.set_language(previous)
