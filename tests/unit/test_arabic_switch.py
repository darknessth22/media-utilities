"""Switching to Arabic must actually translate the newer sections.

Every string existed in ar.json — the widgets simply never re-read them, so a
language switch left whole cards in English. These tests catch that, which a
key-coverage check cannot.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6.QtWidgets")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (                      # noqa: E402
    QApplication, QCheckBox, QLabel, QPushButton,
)

from core import i18n                                # noqa: E402
from core.settings import SettingsManager            # noqa: E402
from gui.app import SettingsSection                  # noqa: E402
from gui.tabs.folder_rules_section import FolderRulesSection   # noqa: E402
from gui.theme import ThemeManager                   # noqa: E402

# Text that is correctly identical in both languages: key names, drive letters,
# file formats and brand names.
_LANGUAGE_NEUTRAL = {
    "GIF", "yt-dlp", "Esc", "EN", "AR", "Videl", "EXIF",
}


def _looks_arabic(text: str) -> bool:
    return any("؀" <= c <= "ۿ" for c in text)


def _untranslated(widget) -> list[str]:
    """Visible strings still in Latin script after switching to Arabic."""
    out = []
    kids = []
    for cls in (QLabel, QPushButton, QCheckBox):
        kids.extend(widget.findChildren(cls))
    for w in kids:
        text = w.text().strip()
        if not text or not any(c.isalpha() for c in text):
            continue
        if _looks_arabic(text) or text in _LANGUAGE_NEUTRAL:
            continue
        # Shortcut sequences and drive paths are not translatable.
        if text.startswith(("Ctrl+", "Alt+", "Shift+", "F")) and len(text) <= 14:
            continue
        if len(text) <= 3 and text.endswith(":"):
            continue
        if ":\\" in text:
            continue
        out.append(text)
    return out


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def arabic(app):
    i18n.I18n.instance().set_language("ar")
    yield
    i18n.I18n.instance().set_language("en")


def test_folder_rules_translates(app, arabic):
    section = FolderRulesSection(SettingsManager.load())
    section.retranslate_ui()

    assert _untranslated(section) == []
    section.close()


def test_file_search_card_translates(app, arabic):
    section = SettingsSection(SettingsManager.load(), ThemeManager(app))
    section.retranslate_ui()

    assert _untranslated(section._cards["file_search"]) == []
    section.close()


def test_keybinds_card_translates(app, arabic):
    section = SettingsSection(SettingsManager.load(), ThemeManager(app))
    section.retranslate_ui()

    assert _untranslated(section._cards["keybinds"]) == []
    section.close()


def test_every_section_with_translatable_text_has_retranslate_ui():
    """A section built once and never re-read keeps its launch language."""
    assert hasattr(FolderRulesSection, "retranslate_ui")
    assert hasattr(SettingsSection, "retranslate_ui")
