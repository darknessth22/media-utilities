"""Screen colour picker in the Palette tool's colour-wheel tab."""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def app():
    inst = QApplication.instance() or QApplication([])
    yield inst


class _Settings:
    def value(self, *a, **k):
        return None

    def setValue(self, *a, **k):
        pass

    def get(self, *a, **k):
        return None


def test_sampling_handles_a_screen_at_negative_x(app):
    """A second monitor left of the primary gives the desktop a negative origin.

    Sampling by screen-local coordinates would read the wrong pixel (or none)
    there, so the lookup walks the captured screens and offsets by each one's
    own geometry.
    """
    from gui.tabs.palette_section import ScreenColorPicker

    picker = ScreenColorPicker()
    if not picker._shots:
        pytest.skip("no screen capture available on this platform")

    for geo, image in picker._shots:
        if image.width() < 40 or image.height() < 40:
            continue
        assert picker._colour_at(geo.x() + 17, geo.y() + 23) == image.pixelColor(17, 23)

    # Off-desktop must return a usable colour rather than raising.
    assert picker._colour_at(10**6, 10**6).isValid()


def test_pick_updates_every_readout_and_clipboard(app):
    """ColorWheelWidget.set_color is deliberately silent.

    It is the quiet setter the hex box uses to avoid a feedback loop, so it
    emits nothing — the handler has to refresh the readouts itself. Without
    that the wheel moved but the hex, HSV and RGB labels kept the old colour.
    """
    from gui.tabs.palette_section import PaletteSection

    section = PaletteSection(_Settings())
    section._pick_from_screen()
    assert section._screen_picker is not None

    section._screen_picker.picked.emit(QColor("#3B82F6"))
    app.processEvents()

    assert section._wheel.hex_color().upper() == "#3B82F6"
    assert section._wheel_hex.text().upper() == "#3B82F6"
    assert "59" in section._wheel_rgb_lbl.text()
    assert QApplication.clipboard().text().upper() == "#3B82F6"
    assert section._screen_picker is None, "the overlay must be released"


def test_cancel_leaves_the_colour_alone(app):
    from gui.tabs.palette_section import PaletteSection

    section = PaletteSection(_Settings())
    before = section._wheel_hex.text()
    section._pick_from_screen()
    section._screen_picker.cancelled.emit()
    app.processEvents()

    assert section._wheel_hex.text() == before
    assert section._screen_picker is None


@pytest.mark.parametrize("lang", ["en", "ar"])
def test_button_strings_exist_in_both_locales(lang):
    from core.i18n import I18n, tr

    i18n = I18n.instance()
    previous = i18n.current_language
    try:
        i18n.set_language(lang)
        for key in ("btn_pick_screen", "tip_pick_screen"):
            assert tr(key) != key, f"{key} missing from {lang}.json"
            assert tr(key).strip()
    finally:
        i18n.set_language(previous)


def test_overlay_covers_every_screen_not_just_one(app):
    """showFullScreen() means ONE screen — it cropped the overlay (bug-108).

    Qt resized the window to the primary monitor and left the rest of the
    desktop uncovered, so it looked like half the screen was trimmed and,
    worse, there was no widget under the cursor out there: hovering another
    monitor produced no loupe and no hex readout.
    """
    from gui.tabs.palette_section import ScreenColorPicker

    picker = ScreenColorPicker()
    if not picker._shots:
        pytest.skip("no screen capture available on this platform")
    wanted = picker._region
    try:
        picker.start()
        app.processEvents()
        assert picker.geometry() == wanted, (
            "the overlay must span the union of all screens"
        )
        # Every screen's corners must map inside the widget, or events there
        # never reach it.
        for geo, _image in picker._shots:
            for gx, gy in (
                (geo.x() + 1, geo.y() + 1),
                (geo.x() + geo.width() - 2, geo.y() + geo.height() - 2),
            ):
                local = picker.mapFromGlobal(QPoint(gx, gy))
                assert picker.rect().contains(local), (
                    f"({gx},{gy}) on screen at {geo.x()} falls outside the overlay"
                )
    finally:
        picker.releaseMouse()
        picker.releaseKeyboard()
        picker.close()


def test_readout_is_seeded_before_the_first_mouse_move(app):
    """Otherwise the loupe shows a stale colour until the pointer moves."""
    from gui.tabs.palette_section import ScreenColorPicker
    from PySide6.QtGui import QCursor

    picker = ScreenColorPicker()
    if not picker._shots:
        pytest.skip("no screen capture available on this platform")
    try:
        picker.start()
        app.processEvents()
        assert picker._cursor == QCursor.pos()
        assert picker._colour == picker._colour_at(picker._cursor.x(), picker._cursor.y())
    finally:
        picker.releaseMouse()
        picker.releaseKeyboard()
        picker.close()


def test_start_screen_pick_ignores_a_second_press(app):
    """Holding Ctrl+B must not stack overlays on top of each other."""
    from gui.tabs.palette_section import PaletteSection

    section = PaletteSection(_Settings())
    assert section._screen_picker is None, "must start clean"

    section.start_screen_pick()
    first = section._screen_picker
    assert first is not None

    section.start_screen_pick()
    assert section._screen_picker is first, "a second press must be ignored"

    section._screen_picker.cancelled.emit()
    app.processEvents()
    assert section._screen_picker is None
    # Released, so a later press works again.
    section.start_screen_pick()
    assert section._screen_picker is not None
    section._screen_picker.cancelled.emit()
    app.processEvents()


def test_tooltip_mentions_the_shortcut():
    """The tooltip is where a user looks for it, in both languages."""
    from core.i18n import I18n, tr

    i18n = I18n.instance()
    previous = i18n.current_language
    try:
        for lang in ("en", "ar"):
            i18n.set_language(lang)
            assert "Ctrl+B" in tr("tip_pick_screen"), f"missing from {lang}.json"
    finally:
        i18n.set_language(previous)
