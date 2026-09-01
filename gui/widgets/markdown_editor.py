"""VSCode-style Markdown source editor: line numbers + syntax highlighting.

Two pieces:

* `MarkdownHighlighter` — a `QSyntaxHighlighter` colouring headings, emphasis,
  code, links, lists, quotes and tables. Colours come from a small palette the
  owner swaps when the app theme changes, so light and dark both look right.
* `CodeEditor` — a `QPlainTextEdit` with a line-number gutter and a
  current-line highlight, following Qt's own code-editor pattern.

Deliberately no external dependency: a `QSyntaxHighlighter` over a handful of
regexes is enough for markdown, and pulling in Pygments to colour six token
types would cost more than it saves.
"""
from __future__ import annotations

import re

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import (
    QColor, QFont, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

# Token colours. Two sets so the editor tracks the app theme; keys are shared.
DARK_THEME = {
    "heading": "#4FC1FF", "emphasis": "#CE9178", "strong": "#569CD6",
    "code": "#CE9178", "link": "#4EC9B0", "list": "#D7BA7D",
    "quote": "#6A9955", "html": "#808080", "rule": "#808080",
    "gutter_bg": "#1E1E1E", "gutter_fg": "#858585", "gutter_cur": "#C6C6C6",
    "current_line": "#2A2D2E",
    "editor_bg": "#1E1E1E", "editor_fg": "#D4D4D4",
    "selection": "#264F78", "border": "#333842", "gutter_line": "#2B2B2B",
}
LIGHT_THEME = {
    "heading": "#0000FF", "emphasis": "#A31515", "strong": "#0451A5",
    "code": "#A31515", "link": "#267F99", "list": "#795E26",
    "quote": "#008000", "html": "#808080", "rule": "#808080",
    "gutter_bg": "#F3F3F3", "gutter_fg": "#237893", "gutter_cur": "#0B216F",
    "current_line": "#EFEFEF",
    "editor_bg": "#FFFFFF", "editor_fg": "#1F2328",
    "selection": "#ADD6FF", "border": "#D8DEE4", "gutter_line": "#E6E6E6",
}


def _fmt(color: str, *, bold: bool = False, italic: bool = False,
         mono: bool = False, size_delta: int = 0) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    if italic:
        f.setFontItalic(True)
    if mono:
        f.setFontFamilies(["Consolas", "Cascadia Mono", "Courier New", "monospace"])
    if size_delta:
        # Relative sizing keeps headings proportional whatever the base font is.
        f.setProperty(QTextFormat.Property.FontSizeAdjustment, size_delta)
    return f


class MarkdownHighlighter(QSyntaxHighlighter):
    """Colours markdown source. Fenced code blocks span lines, so they use the
    block state that `QSyntaxHighlighter` maintains for exactly this case."""

    _FENCE = re.compile(r"^\s*(```|~~~)")

    def __init__(self, document, dark: bool = True) -> None:
        super().__init__(document)
        self._rules: list[tuple[re.Pattern, QTextCharFormat, int]] = []
        self.set_theme(dark)

    def set_theme(self, dark: bool) -> None:
        c = DARK_THEME if dark else LIGHT_THEME
        self._code_fmt = _fmt(c["code"], mono=True)
        # (pattern, format, capture group to paint; 0 = whole match)
        self._rules = [
            (re.compile(r"^#{1,6}\s.*$"), _fmt(c["heading"], bold=True, size_delta=1), 0),
            (re.compile(r"^\s{0,3}(?:[-*_]\s*){3,}$"), _fmt(c["rule"]), 0),
            (re.compile(r"^\s*>\s?.*$"), _fmt(c["quote"], italic=True), 0),
            (re.compile(r"^\s*(?:[-*+]|\d{1,9}[.)])\s"), _fmt(c["list"], bold=True), 0),
            (re.compile(r"\*\*\*(?!\s)(.+?)(?<!\s)\*\*\*|___(?!\s)(.+?)(?<!\s)___"),
             _fmt(c["strong"], bold=True, italic=True), 0),
            (re.compile(r"\*\*(?!\s)(.+?)(?<!\s)\*\*|__(?!\s)(.+?)(?<!\s)__"),
             _fmt(c["strong"], bold=True), 0),
            (re.compile(r"(?<![\w*])\*(?!\s)([^*]+?)(?<!\s)\*(?![\w*])"),
             _fmt(c["emphasis"], italic=True), 0),
            (re.compile(r"~~(?!\s)(.+?)(?<!\s)~~"), _fmt(c["emphasis"]), 0),
            (re.compile(r"`[^`\n]+`"), self._code_fmt, 0),
            (re.compile(r"!?\[[^\]\n]*\]\([^)\n]*\)"), _fmt(c["link"]), 0),
            (re.compile(r"</?[A-Za-z][^>\n]*/?>"), _fmt(c["html"]), 0),
            (re.compile(r"^\s*\|.*\|\s*$"), _fmt(c["list"]), 0),
        ]
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802 (Qt override)
        # State 1 = inside a fenced code block. A fence line toggles it, and the
        # fence itself is coloured as code so the block reads as one unit.
        in_fence = self.previousBlockState() == 1
        fence = self._FENCE.match(text)

        if in_fence:
            self.setFormat(0, len(text), self._code_fmt)
            self.setCurrentBlockState(0 if fence else 1)
            return
        if fence:
            self.setFormat(0, len(text), self._code_fmt)
            self.setCurrentBlockState(1)
            return

        self.setCurrentBlockState(0)
        for pattern, fmt, group in self._rules:
            for m in pattern.finditer(text):
                start, end = m.span(group)
                if end > start:
                    self.setFormat(start, end - start, fmt)


class _LineNumberArea(QWidget):
    """Gutter. Painting is delegated to the editor, which knows the layout."""

    def __init__(self, editor: "CodeEditor") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: N802
        self._editor.paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    """Plain-text editor with a line-number gutter and current-line highlight."""

    def __init__(self, parent=None, dark: bool = True) -> None:
        super().__init__(parent)
        self._colors = DARK_THEME if dark else LIGHT_THEME
        self._gutter = _LineNumberArea(self)

        font = QFont()
        font.setFamilies(["Consolas", "Cascadia Mono", "Courier New", "monospace"])
        font.setPointSize(10)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_gutter_width()
        self._apply_palette()
        self._highlight_current_line()

    def set_theme(self, dark: bool) -> None:
        self._colors = DARK_THEME if dark else LIGHT_THEME
        self._apply_palette()
        self._highlight_current_line()
        self._gutter.update()

    def _apply_palette(self) -> None:
        """Colour the text area explicitly.

        Without this the gutter (painted here) and the body (styled by the app
        QSS) disagree — a dark gutter against a white page.
        """
        c = self._colors
        self.setStyleSheet(
            "QPlainTextEdit {"
            f" background-color: {c['editor_bg']};"
            f" color: {c['editor_fg']};"
            f" selection-background-color: {c['selection']};"
            f" selection-color: {c['editor_fg']};"
            " border: none; padding: 6px 4px 6px 6px; }"
        )

    def line_number_area_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 16 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_gutter_width(self) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_gutter(self, rect: QRect, dy: int) -> None:
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._gutter.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def _highlight_current_line(self) -> None:
        selections: list[QTextEdit.ExtraSelection] = []
        if not self.isReadOnly():
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor(self._colors["current_line"]))
            sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            selections.append(sel)
        self.setExtraSelections(selections)

    def paint_line_numbers(self, event) -> None:
        painter = QPainter(self._gutter)
        painter.fillRect(event.rect(), QColor(self._colors["gutter_bg"]))
        # Hairline between gutter and text.
        painter.setPen(QColor(self._colors["gutter_line"]))
        right = self._gutter.width() - 1
        painter.drawLine(right, event.rect().top(), right, event.rect().bottom())

        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()
        current = self.textCursor().blockNumber()
        width = self._gutter.width() - 8
        height = self.fontMetrics().height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor(self._colors[
                    "gutter_cur" if number == current else "gutter_fg"]))
                painter.drawText(0, int(top), width, height,
                                 Qt.AlignmentFlag.AlignRight, str(number + 1))
            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            number += 1
        painter.end()

    def goto_line(self, line: int) -> None:
        """Scroll so 1-based *line* is visible, without stealing focus."""
        block = self.document().findBlockByNumber(max(0, line - 1))
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        self.setTextCursor(cursor)
        self.centerCursor()
