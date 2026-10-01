"""Settings categories and search.

The settings page was one 2801 px column — 3.5 screens. These tests pin the
split so a new card cannot quietly land back in a single endless scroll.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6.QtWidgets")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication            # noqa: E402

from core.settings import SettingsManager             # noqa: E402
from gui.app import SettingsSection                   # noqa: E402
from gui.theme import ThemeManager                    # noqa: E402


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def section(app):
    widget = SettingsSection(SettingsManager.load(), ThemeManager(app))
    yield widget
    widget.close()


def test_every_card_is_on_exactly_one_page(section):
    """A card reachable from no category is a setting nobody can find."""
    placed = [name for _cid, _key, _icon, names in SettingsSection._CATEGORIES
              for name in names]
    assert sorted(placed) == sorted(section._cards), "card missing or duplicated"
    assert len(placed) == len(set(placed))


def test_selecting_a_category_switches_page_and_marks_the_button(section):
    section._select_category(2)

    assert section._stack.currentIndex() == 2
    active = [b.property("active") for b in section._nav_buttons]
    assert active.count("true") == 1 and active[2] == "true"


def test_search_finds_a_setting_in_another_category(section):
    """The point of search: you do not need to know where it lives."""
    section._select_category(0)
    section._search.setText("cookie")

    shown = [n for n, c in section._cards.items() if not c.isHidden()]
    assert shown == ["cookies"]
    assert section._stack.currentIndex() == 2, "should jump to the hit's page"


def test_clearing_search_restores_every_card(section):
    section._search.setText("theme")
    section._search.setText("")

    hidden = [n for n, c in section._cards.items()
              if c.isHidden() and n != "spotify"]
    assert hidden == []


def test_choosing_a_category_mid_search_resets_the_filter(section):
    """clear() re-enters the search slot; the filter must not survive it."""
    section._search.setText("cookie")
    section._select_category(1)

    assert section._search.text() == ""
    hidden = [n for n, c in section._cards.items()
              if c.isHidden() and n != "spotify"]
    assert hidden == [], "cards stayed filtered after leaving search"


def test_no_matches_shows_the_empty_state(section):
    section._search.setText("zzzznotasetting")

    assert section._stack.currentWidget() is section._results_page
    assert section._results_label.text()


def test_ampersand_in_a_category_label_is_escaped(section):
    """Qt reads a bare "&" as a mnemonic: "Files & Output" -> "Files  Output"."""
    for btn in section._nav_buttons:
        if "&" in btn.text():
            assert "&&" in btn.text(), f"unescaped mnemonic in {btn.text()!r}"


def test_every_category_has_an_icon_and_a_description(section):
    """A rail of bare words is hard to scan; a page with no subtitle does not
    explain what it is for."""
    import os
    from gui.app import _ICONS_DIR

    for cid, _key, icon_file, _cards in SettingsSection._CATEGORIES:
        assert os.path.exists(os.path.join(_ICONS_DIR, icon_file)), icon_file
        assert cid in SettingsSection._CATEGORY_HINTS, cid
    for btn in section._nav_buttons:
        assert not btn.icon().isNull(), "rail button has no icon"


def test_page_subtitle_follows_the_category(section):
    section._select_category(0)
    first = section._page_subtitle.text()
    section._select_category(3)

    assert first and section._page_subtitle.text()
    assert section._page_subtitle.text() != first


def test_subtitle_is_hidden_while_searching(section):
    """It names the category, which is misleading once results span pages."""
    section._select_category(0)
    section._search.setText("cookie")

    assert not section._page_subtitle.isVisible()


def test_retranslate_keeps_the_rail_labelled(section):
    section.retranslate_ui()

    labels = [b.text() for b in section._nav_buttons]
    assert all(labels), "a blank rail button means a missing translation key"
    assert len(labels) == len(SettingsSection._CATEGORIES)
