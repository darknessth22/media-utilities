"""Customisable keyboard shortcuts (core/keybinds.py)."""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


def test_shipped_defaults_do_not_clash(app):
    """Two QShortcuts on one sequence means one silently never fires."""
    from core.keybinds import conflicts, resolve

    assert conflicts(resolve(None)) == {}


def test_every_action_has_a_unique_id():
    from core.keybinds import ALL_ACTIONS

    ids = [a.id for a in ALL_ACTIONS]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    "sequence,valid",
    [
        ("Ctrl+K", True), ("F1", True), ("Esc", True), ("Ctrl+Shift+B", True),
        ("", False), ("   ", False),
        # Qt does NOT reject nonsense — it yields Key_unknown with an empty
        # toString(), which read as valid until both were checked.
        ("NotAKey", False), ("zzz", False), ("Ctrl+", False),
        # Multi-step sequences cannot be an OS hotkey and confuse capture.
        ("Ctrl+K, Ctrl+B", False),
    ],
)
def test_validation(app, sequence, valid):
    from core.keybinds import is_valid

    assert is_valid(sequence) is valid


def test_normalise_is_case_insensitive(app):
    from core.keybinds import normalise

    assert normalise("ctrl+b") == "Ctrl+B"
    assert normalise("CTRL+SHIFT+b") == "Ctrl+Shift+B"


def test_a_valid_override_wins(app):
    from core.keybinds import resolve

    assert resolve({"quick_search": "ctrl+p"})["quick_search"] == "Ctrl+P"


@pytest.mark.parametrize("bad", ["GARBAGE", "", "   ", 42, None])
def test_a_bad_override_falls_back_to_the_default(app, bad):
    """A broken config must never leave an action unreachable."""
    from core.keybinds import action, resolve

    resolved = resolve({"go_home": bad})
    assert resolved["go_home"] == action("go_home").default


def test_no_action_is_ever_left_unbound(app):
    """An unbindable action with no way to reach the settings page is a lockout.

    An earlier version dropped a duplicate to "" when its default was also
    taken, which could strand the user.
    """
    from core.keybinds import ALL_ACTIONS, resolve

    # Point several actions at one another's keys.
    hostile = {
        "go_tools": "Ctrl+H",          # collides with go_home
        "quick_search": "Ctrl+H",      # and again
        "open_settings": "Ctrl+H",
    }
    resolved = resolve(hostile)
    for act in ALL_ACTIONS:
        assert resolved[act.id], f"{act.id} was left unbound"


def test_conflicts_reports_every_duplicate():
    from core.keybinds import conflicts

    assert conflicts({"a": "Ctrl+X", "b": "Ctrl+X", "c": "Ctrl+Y"}) == {
        "Ctrl+X": ["a", "b"]
    }


def test_labels_resolve_in_both_languages():
    from core.i18n import I18n, tr
    from core.keybinds import ALL_ACTIONS

    i18n = I18n.instance()
    previous = i18n.current_language
    try:
        for lang in ("en", "ar"):
            i18n.set_language(lang)
            for act in ALL_ACTIONS:
                assert tr(act.label_key) != act.label_key, (
                    f"{act.label_key} missing from {lang}.json"
                )
                assert tr(act.group_key) != act.group_key
    finally:
        i18n.set_language(previous)
