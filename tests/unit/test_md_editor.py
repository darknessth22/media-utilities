"""Markdown editor/viewer sub-tab.

Rendering itself is Qt's `setMarkdown()`, so these cover the wiring around it:
the debounce, dirty tracking, save/load, and scroll retention.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def section(qapp):
    from core.settings import SettingsManager
    from gui.tabs.document_section import DocumentSection

    sec = DocumentSection(SettingsManager.load())
    sec.on_sub_tab_changed(1)
    return sec


def _settle(ms: int = 400) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_sub_tab_switches_page(section) -> None:
    section.on_sub_tab_changed(0)
    assert section._stack.currentIndex() == 0
    section.on_sub_tab_changed(1)
    assert section._stack.currentIndex() == 1


def test_render_is_debounced_then_applied(section) -> None:
    """Typing must not re-parse on every keystroke."""
    section._md_view.setMarkdown("")
    section._md_edit.setPlainText("# Typed")
    assert section._md_timer.isActive()
    assert section._md_view.toPlainText() == ""
    _settle()
    assert "Typed" in section._md_view.toPlainText()


def test_markdown_actually_renders(section) -> None:
    section._md_edit.setPlainText("# H\n\n- a\n- b\n\n**bold**")
    section._md_render()
    html = section._md_view.toHtml()
    assert html.count("<li") == 2
    assert "font-weight" in html          # bold survived
    assert section._md_view.toPlainText().startswith("H")


def test_dirty_flag_and_save_round_trip(section, tmp_path) -> None:
    section._md_edit.setPlainText("# hello")
    assert section._md_dirty
    assert section._md_status.text().endswith("*")

    path = tmp_path / "note.md"
    assert section._md_write(str(path))
    assert not section._md_dirty
    assert not section._md_status.text().endswith("*")
    assert path.read_text(encoding="utf-8") == "# hello"

    section._md_edit.setPlainText("")
    section._md_load(str(path))
    assert section._md_edit.toPlainText() == "# hello"
    assert not section._md_dirty


def test_scroll_position_kept_across_render(section) -> None:
    """setMarkdown resets the scrollbar; the viewer must restore it."""
    section._md_edit.setPlainText("\n".join(f"line {i}" for i in range(200)))
    _settle()
    bar = section._md_view.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    keep = bar.value()
    section._md_render()
    assert bar.value() == keep


def test_empty_document_is_safe(section) -> None:
    section._md_edit.setPlainText("")
    section._md_render()
    assert section._md_view.toPlainText() == ""


def test_primary_action_saves_on_editor_tab(section, tmp_path) -> None:
    """The convert button must not try to convert while the editor is open."""
    section._md_path = str(tmp_path / "p.md")
    section._md_edit.setPlainText("# via primary")
    section.trigger_primary_action()
    assert (tmp_path / "p.md").read_text(encoding="utf-8") == "# via primary"


def test_load_reports_unreadable_file(section, tmp_path) -> None:
    seen: list[tuple[str, bool]] = []
    section.status_message.connect(lambda m, e: seen.append((m, e)))
    section._md_load(str(tmp_path / "nope.md"))
    assert seen and seen[-1][1] is True


@pytest.mark.parametrize("source,expected", [
    # Void tags must be self-closed or Qt's setMarkdown stops parsing there.
    ('<img src="x.gif" width="400px">', '<img src="x.gif" width="400px"/>'),
    ("<br>", "<br/>"),
    ("<IMG SRC='y.gif'>", "<IMG SRC='y.gif'/>"),
    # A '>' inside a quoted attribute must not end the tag early.
    ('<img src="a>b.gif" alt="has > in it">', '<img src="a>b.gif" alt="has > in it"/>'),
    # Already correct, or not a void tag — leave alone.
    ('<img src="x.gif"/>', '<img src="x.gif"/>'),
    ("<hr />", "<hr/>"),
    ("<span>keep</span>", "<span>keep</span>"),
    ("plain text", "plain text"),
])
def test_void_html_is_self_closed(source, expected) -> None:
    from gui.tabs.document_section import _close_void_html
    assert _close_void_html(source) == expected


def test_unclosed_img_does_not_truncate_render(section) -> None:
    """Regression: a real README rendered only the text above its first <img>.

    Qt's setMarkdown() consumes the remainder of the document at an unclosed
    void tag, so everything after the first image silently disappeared.
    """
    section._md_edit.setPlainText(
        'intro\n\n<img src="x.gif" width="400px">\n\n### Later\n\ntail text\n')
    section._md_render()
    rendered = section._md_view.toPlainText()
    assert "Later" in rendered
    assert "tail text" in rendered


# ── scroll sync ───────────────────────────────────────────────────────────

def _long_doc(section, app_events=True):
    section._md_edit.setPlainText("\n".join(f"# H{i}\n\npara {i}\n" for i in range(300)))
    section._md_render()
    QApplication.processEvents()


def test_scroll_sync_is_proportional_both_ways(section) -> None:
    section.show()
    _long_doc(section)
    edit = section._md_edit.verticalScrollBar()
    view = section._md_view.verticalScrollBar()
    if edit.maximum() == 0 or view.maximum() == 0:
        pytest.skip("no scrollable range in this environment")

    for frac in (0.25, 0.5, 0.75):
        edit.setValue(round(edit.maximum() * frac))
        # QTextBrowser lays out lazily and its range keeps shrinking, so let
        # the queued rangeChanged re-seat land before measuring. Without this
        # the assert is a race and fails intermittently.
        for _ in range(5):
            QApplication.processEvents()
        got = view.value() / max(view.maximum(), 1)
        want = edit.value() / max(edit.maximum(), 1)
        assert abs(got - want) < 0.05, f"{frac}: {got} vs {want}"


def test_scroll_sync_does_not_recurse(section) -> None:
    """Setting one bar emits valueChanged on it; without a guard the two
    scrollbars ping-pong forever."""
    section.show()
    _long_doc(section)
    calls = {"n": 0}
    original = section._md_sync_scroll

    def counting(src, dst):
        calls["n"] += 1
        assert calls["n"] < 100, "runaway scroll sync"
        return original(src, dst)

    section._md_sync_scroll = counting
    section._md_edit.verticalScrollBar().setValue(
        section._md_edit.verticalScrollBar().maximum() // 3)
    QApplication.processEvents()
    section._md_sync_scroll = original
    assert calls["n"] < 10


def test_scroll_sync_can_be_disabled(section) -> None:
    section.show()
    _long_doc(section)
    view = section._md_view.verticalScrollBar()
    if view.maximum() == 0:
        pytest.skip("no scrollable range")
    view.setValue(view.maximum() // 2)
    QApplication.processEvents()
    section._md_sync_check.setChecked(False)
    before = view.value()
    section._md_edit.verticalScrollBar().setValue(0)
    QApplication.processEvents()
    assert view.value() == before


@pytest.mark.parametrize("text", ["", "# one line", "a\n\nb"])
def test_sync_safe_with_no_scroll_range(section, text) -> None:
    section._md_edit.setPlainText(text)
    section._md_render()
    section._md_edit.verticalScrollBar().setValue(0)
    section._md_view.verticalScrollBar().setValue(0)


# ── large documents ───────────────────────────────────────────────────────

def test_preview_steps_aside_for_huge_documents(section) -> None:
    """setMarkdown is synchronous; a multi-MB re-render per keystroke freezes
    the window, so the preview bows out instead."""
    from gui.tabs.document_section import _MD_PREVIEW_LIMIT
    section._md_edit.setPlainText("x" * (_MD_PREVIEW_LIMIT + 1000))
    section._md_render()
    assert "MB" in section._md_view.toPlainText()


# ── editor chrome ─────────────────────────────────────────────────────────

def test_line_number_gutter_grows_with_line_count(section) -> None:
    section._md_edit.setPlainText("a")
    narrow = section._md_edit.line_number_area_width()
    section._md_edit.setPlainText("\n".join("x" for _ in range(10_000)))
    assert section._md_edit.line_number_area_width() > narrow


def test_goto_line_clamps(section) -> None:
    section._md_edit.setPlainText("\n".join(f"L{i}" for i in range(100)))
    for line in (-5, 0, 1, 50, 100, 9999):
        section._md_edit.goto_line(line)


def test_theme_switch_does_not_crash(section) -> None:
    for dark in (False, True, False):
        section.apply_theme(dark)


def test_stats_line_updates(section) -> None:
    section._md_edit.setPlainText("one two\nthree")
    section._md_update_status()
    text = section._md_stats.text()
    assert "2" in text and "3" in text      # 2 lines, 3 words


def test_highlighter_handles_pathological_input(section) -> None:
    """The highlighter runs on every keystroke; it must never raise."""
    for text in ("*" * 5000, "`" * 5000, "#" * 200 + " h", "[" * 2000 + "]" * 2000,
                 "```\nunclosed fence\n", "a" + "́" * 2000, "\x00\x01\x02"):
        section._md_edit.setPlainText(text)
        QApplication.processEvents()
