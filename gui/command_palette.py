"""Command palette — Ctrl+K quick tool launcher.

Modal dialog that fuzzy-filters all Videl tools by name + description.
Up/Down navigate, Enter opens, Esc closes.
"""
from __future__ import annotations

from typing import Callable, List, Tuple

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QLabel, QFrame,
)

from core.i18n import tr
from gui.pages.home_page import _ALL_TOOLS_META, _resolved_tools


class CommandPalette(QDialog):
    """Fuzzy search across all tools. Returns selected section_idx via callback."""

    def __init__(self, navigate_cb: Callable[[int], None], parent=None) -> None:
        super().__init__(parent)
        self._navigate_cb = navigate_cb
        self.setObjectName("CommandPalette")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setFixedSize(560, 420)

        outer = QFrame(self)
        outer.setObjectName("CommandPaletteFrame")
        outer.setGeometry(0, 0, 560, 420)

        layout = QVBoxLayout(outer)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._input = QLineEdit()
        self._input.setObjectName("CommandPaletteInput")
        self._input.setPlaceholderText(tr("command_palette_placeholder"))
        self._input.textChanged.connect(self._refilter)
        self._input.installEventFilter(self)
        layout.addWidget(self._input)

        self._list = QListWidget()
        self._list.setObjectName("CommandPaletteList")
        self._list.itemActivated.connect(self._activate)
        layout.addWidget(self._list, 1)

        self._empty = QLabel(tr("command_palette_empty"))
        self._empty.setObjectName("CommandPaletteEmpty")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.hide()
        layout.addWidget(self._empty)

        self._all = _resolved_tools(_ALL_TOOLS_META)
        self._refilter("")

    # ── Filtering ──────────────────────────────────────────────────────────
    def _refilter(self, q: str) -> None:
        q_low = q.strip().lower()
        self._list.clear()
        matches: List[Tuple[str, str, str, str, int]] = []
        for entry in self._all:
            _tid, _icon, title, desc, idx = entry
            if not q_low or q_low in title.lower() or q_low in desc.lower():
                matches.append(entry)
        for entry in matches:
            tid, _icon, title, desc, idx = entry
            item = QListWidgetItem(f"{title}    —    {desc}")
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self._list.addItem(item)
        if matches:
            self._list.setCurrentRow(0)
            self._list.show()
            self._empty.hide()
        else:
            self._list.hide()
            self._empty.show()

    # ── Keyboard ───────────────────────────────────────────────────────────
    def eventFilter(self, obj, event: QEvent) -> bool:  # type: ignore[override]
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            ke: QKeyEvent = event  # type: ignore[assignment]
            key = ke.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self._list.setFocus()
                row = self._list.currentRow()
                if key == Qt.Key.Key_Down:
                    self._list.setCurrentRow(min(row + 1, self._list.count() - 1))
                else:
                    self._list.setCurrentRow(max(row - 1, 0))
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self._list.currentItem()
                if item:
                    self._activate(item)
                return True
        return super().eventFilter(obj, event)

    def _activate(self, item: QListWidgetItem) -> None:
        idx = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        if isinstance(idx, int):
            self._navigate_cb(idx)

    def keyPressEvent(self, ev: QKeyEvent) -> None:  # type: ignore[override]
        if ev.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(ev)
