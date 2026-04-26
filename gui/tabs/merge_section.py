"""Merge Videos tab — concatenates multiple video files via FFmpeg concat demuxer."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker
from utils.ffmpeg import ffmpeg_path


def _card() -> QFrame:
    f = QFrame()
    f.setObjectName("Card")
    return f


def _section_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("TextSecondary")
    lbl.setStyleSheet(
        "font-size: 11px; font-weight: bold; letter-spacing: 1px; margin-bottom: 2px;"
    )
    return lbl


class MergeSection(QWidget):
    """Section widget: merge multiple video files into one."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_result_path: str | None = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_files_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

        scroll.setWidget(inner)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    # ── Cards ──────────────────────────────────────────────────────────────────

    def _build_files_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("VIDEO FILES  (drag to reorder — top = first)"))

        self._file_list = QListWidget()
        self._file_list.setObjectName("FileList")
        self._file_list.setFixedHeight(180)
        self._file_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        layout.addWidget(self._file_list)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        add_btn = QPushButton("Add Files…")
        add_btn.setObjectName("BrowseBtn")
        add_btn.clicked.connect(self._add_files)
        btn_row.addWidget(add_btn)

        up_btn = QPushButton("▲")
        up_btn.setObjectName("BrowseBtn")
        up_btn.setFixedWidth(36)
        up_btn.setToolTip("Move selected item up")
        up_btn.clicked.connect(self._move_up)
        btn_row.addWidget(up_btn)

        down_btn = QPushButton("▼")
        down_btn.setObjectName("BrowseBtn")
        down_btn.setFixedWidth(36)
        down_btn.setToolTip("Move selected item down")
        down_btn.clicked.connect(self._move_down)
        btn_row.addWidget(down_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.setObjectName("BrowseBtn")
        remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(remove_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("BrowseBtn")
        clear_btn.clicked.connect(self._file_list.clear)
        btn_row.addWidget(clear_btn)

        layout.addLayout(btn_row)
        return card

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("OUTPUT"))

        layout.addWidget(QLabel("Output filename"))
        self._name_input = QLineEdit()
        self._name_input.setObjectName("PillInput")
        self._name_input.setPlaceholderText("merged.mp4")
        layout.addWidget(self._name_input)

        layout.addWidget(QLabel("Output folder"))
        row = QHBoxLayout()
        self._out_input = QLineEdit()
        self._out_input.setObjectName("PillInput")
        self._out_input.setPlaceholderText("Same directory as first video file")
        if self._settings.output_folder:
            self._out_input.setText(self._settings.output_folder)
        row.addWidget(self._out_input)

        browse_btn = QPushButton("Browse…")
        browse_btn.setObjectName("BrowseBtn")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_output)
        row.addWidget(browse_btn)
        layout.addLayout(row)
        return card

    def _build_progress_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("TaskProgressBar")
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._progress_label = QLabel()
        self._progress_label.setObjectName("TextSecondary")
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)
        return card

    # ── List helpers ───────────────────────────────────────────────────────────

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Video Files",
            os.path.expanduser("~"),
            "Video files (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.m4v)",
        )
        for p in paths:
            existing = [self._file_list.item(i).text() for i in range(self._file_list.count())]
            if p not in existing:
                self._file_list.addItem(QListWidgetItem(p))

    def _move_up(self) -> None:
        row = self._file_list.currentRow()
        if row > 0:
            item = self._file_list.takeItem(row)
            self._file_list.insertItem(row - 1, item)
            self._file_list.setCurrentRow(row - 1)

    def _move_down(self) -> None:
        row = self._file_list.currentRow()
        if 0 <= row < self._file_list.count() - 1:
            item = self._file_list.takeItem(row)
            self._file_list.insertItem(row + 1, item)
            self._file_list.setCurrentRow(row + 1)

    def _remove_selected(self) -> None:
        row = self._file_list.currentRow()
        if row >= 0:
            self._file_list.takeItem(row)

    def _browse_output(self) -> None:
        start = self._out_input.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if d:
            self._out_input.setText(d)

    def add_files_from_paths(self, paths: list[str]) -> None:
        for p in paths:
            existing = [self._file_list.item(i).text() for i in range(self._file_list.count())]
            if p not in existing:
                self._file_list.addItem(QListWidgetItem(p))

    # ── Action ─────────────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        paths = [self._file_list.item(i).text() for i in range(self._file_list.count())]
        if len(paths) < 2:
            self.status_message.emit("Please add at least 2 video files.", True)
            return

        out_name = self._name_input.text().strip() or "merged.mp4"
        if not os.path.splitext(out_name)[1]:
            out_name += ".mp4"
        out_dir = self._out_input.text().strip() or os.path.dirname(paths[0])

        self._set_busy(True)
        self.status_message.emit(f"Merging {len(paths)} file(s)…", False)

        def do_merge():
            os.makedirs(out_dir, exist_ok=True)
            dest = os.path.join(out_dir, out_name)
            flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

            # Write FFmpeg concat list to a temp file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                concat_file = f.name
                for p in paths:
                    # Escape single quotes in file paths for the concat format
                    safe_path = p.replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")

            try:
                cmd = [
                    ffmpeg_path, "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_file,
                    "-c", "copy",
                    dest,
                ]
                subprocess.run(cmd, check=True, capture_output=True, timeout=7200, **flags)
                return {"success": True, "file_path": dest, "count": len(paths)}
            except Exception as exc:
                return {"success": False, "error": str(exc)}
            finally:
                try:
                    os.unlink(concat_file)
                except OSError:
                    pass

        self._worker = Worker(do_merge)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if busy:
            self._progress_label.setText("Merging videos…")
        self.busy_changed.emit(busy)

    def _on_result(self, result: dict) -> None:
        self._set_busy(False)
        self._worker = None
        if result.get("success"):
            fp = result["file_path"]
            self._last_result_path = fp
            fn = os.path.basename(fp)
            count = result.get("count", 0)
            get_history_manager().add_item(
                HistoryItem(task_type="merge", file_name=fn, file_path=fp, status="success")
            )
            self.status_message.emit(f"Done → {fn}  ({count} clips merged)", False)
        else:
            err = result.get("error") or "Merge failed."
            self.status_message.emit(f"Error: {err}", True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
