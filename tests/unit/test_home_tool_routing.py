"""Every tool card must open the section it names.

The indices in _ALL_TOOLS_META used to be hardcoded, so inserting a section in
the middle of _SECTIONS_META pointed every later card at the wrong tool — the
History card silently opened Folder Rules. This catches that class of drift.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWidgets")

from gui.app import _SECTIONS_META             # noqa: E402
from gui.pages.home_page import _ALL_TOOLS_META, _all_tools     # noqa: E402


def test_every_tool_card_points_at_its_own_section():
    ids = [m["id"] for m in _SECTIONS_META]
    for tool_id, _icon, _name, _desc, idx in _all_tools():
        assert 0 <= idx < len(ids), f"{tool_id} index {idx} is out of range"
        assert ids[idx] == tool_id, (
            f"tool card {tool_id!r} opens section {ids[idx]!r}")


def test_every_tool_id_exists_as_a_section():
    ids = {m["id"] for m in _SECTIONS_META}
    for tool_id, *_ in _ALL_TOOLS_META:
        assert tool_id in ids, f"tool card {tool_id!r} has no section"


def test_folder_rules_is_on_the_tools_page():
    assert any(t[0] == "folder_rules" for t in _ALL_TOOLS_META)
