"""History tab — PySide6 QAbstractTableModel bound to HistoryManager.

T016: Reimplement History tab using QAbstractTableModel connected to the
      local JSON history store.
"""
from __future__ import annotations

import datetime
import os
import subprocess
import sys

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.history.manager import get_history_manager
from core.history.models import HistoryItem

_COLUMN_KEYS = ["hist_col_type", "hist_col_file", "hist_col_date", "hist_col_status"]
_PAGE_SIZE = 20


# ── Model ─────────────────────────────────────────────────────────────────────


class HistoryTableModel(QAbstractTableModel):
    """QAbstractTableModel wrapping HistoryManager's item list, with lazy loading."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._all_items: list[HistoryItem] = []
        self._items: list[HistoryItem] = []
        self.refresh()

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload items from the persistent store (first page only)."""
        self.beginResetModel()
        self._all_items = list(get_history_manager().get_items())
        self._items = self._all_items[:_PAGE_SIZE]
        self.endResetModel()

    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:
        return len(self._items) < len(self._all_items)

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:
        start = len(self._items)
        fetch_count = min(_PAGE_SIZE, len(self._all_items) - start)
        self.beginInsertRows(QModelIndex(), start, start + fetch_count - 1)
        self._items.extend(self._all_items[start : start + fetch_count])
        self.endInsertRows()

    def clear_all(self) -> None:
        get_history_manager().clear_all()
        self.refresh()

    def get_item(self, row: int) -> HistoryItem | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    # ── QAbstractTableModel protocol ──────────────────────────────────────────

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(_COLUMN_KEYS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._items):
            return None
        item = self._items[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return item.task_type.capitalize()
            if col == 1:
                return item.file_name
            if col == 2:
                ts = datetime.datetime.fromtimestamp(item.timestamp)
                return ts.strftime("%Y-%m-%d  %H:%M")
            if col == 3:
                return (
                    tr("hist_status_success")
                    if item.status == "success"
                    else tr("hist_status_error")
                )

        elif role == Qt.ItemDataRole.ForegroundRole:
            if col == 3:
                if item.status == "success":
                    return QColor("#3FB950")   # --status-success
                return QColor("#F85149")       # --status-error

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (0, 3):
                return Qt.AlignmentFlag.AlignCenter

        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return tr(_COLUMN_KEYS[section])
        return None


# ── View ──────────────────────────────────────────────────────────────────────


class HistorySection(QWidget):
    """History tab using Qt Model/View architecture."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # ── Empty-state label (shown when no items) ───────────────────────────
        self._empty_label = QLabel(tr("lbl_history_empty"))
        self._empty_label.setObjectName("TextMuted")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_label)

        # ── Table ─────────────────────────────────────────────────────────────
        self._model = HistoryTableModel()

        self._table = QTableView()
        self._table.setObjectName("HistoryTable")
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._table.doubleClicked.connect(self._on_double_click)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self._table, 1)

        # ── Separator ─────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("Separator")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # ── Button row ────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self._play_btn = QPushButton(tr("btn_play_selected"))
        self._play_btn.setObjectName("SecondaryBtn")
        self._play_btn.setFixedHeight(36)
        self._play_btn.clicked.connect(self._play_selected)

        self._folder_btn = QPushButton(tr("btn_open_folder"))
        self._folder_btn.setObjectName("SecondaryBtn")
        self._folder_btn.setFixedHeight(36)
        self._folder_btn.clicked.connect(self._open_folder)

        self._clear_btn = QPushButton(tr("btn_clear_all"))
        self._clear_btn.setObjectName("DangerBtn")
        self._clear_btn.setFixedHeight(36)
        self._clear_btn.clicked.connect(self._clear_all)

        btn_row.addWidget(self._play_btn)
        btn_row.addWidget(self._folder_btn)
        btn_row.addWidget(self._clear_btn)
        layout.addLayout(btn_row)

        self._sync_empty_state()

    # ── Public API ────────────────────────────────────────────────────────────


    def retranslate_ui(self) -> None:
        self._empty_label.setText(tr("lbl_history_empty"))
        self._play_btn.setText(tr("btn_play_selected"))
        self._folder_btn.setText(tr("btn_open_folder"))
        self._clear_btn.setText(tr("btn_clear_all"))
        last = self._model.columnCount() - 1
        self._model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, last)
        rows = self._model.rowCount()
        if rows > 0:
            tl = self._model.index(0, 0)
            br = self._model.index(rows - 1, last)
            self._model.dataChanged.emit(tl, br, [Qt.ItemDataRole.DisplayRole])


    def refresh(self) -> None:
        """Reload history from disk and update the view."""
        self._model.refresh()
        self._sync_empty_state()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _sync_empty_state(self) -> None:
        has_items = self._model.rowCount() > 0
        self._empty_label.setVisible(not has_items)
        self._table.setVisible(has_items)
        self._play_btn.setEnabled(has_items)
        self._folder_btn.setEnabled(has_items)
        self._clear_btn.setEnabled(has_items)

    def _selected_item(self) -> HistoryItem | None:
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return None
        return self._model.get_item(indexes[0].row())

    def _open_path(self, path: str) -> None:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_double_click(self, _index: QModelIndex) -> None:
        self._play_selected()

    def _play_selected(self) -> None:
        item = self._selected_item()
        if not item:
            return
        if not os.path.exists(item.file_path):
            QMessageBox.warning(self, "File Not Found", f"Cannot locate:\n{item.file_path}")
            return
        self._open_path(item.file_path)

    def _open_folder(self) -> None:
        item = self._selected_item()
        if not item:
            return
        folder = os.path.dirname(item.file_path)
        if not os.path.isdir(folder):
            QMessageBox.warning(self, "Folder Not Found", f"Cannot locate:\n{folder}")
            return
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", item.file_path])
        else:
            self._open_path(folder)

    def _clear_all(self) -> None:
        reply = QMessageBox.question(
            self,
            "Clear History",
            "Delete all history entries?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._model.clear_all()
            self._sync_empty_state()
