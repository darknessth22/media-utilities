"""Document Convert tab — PySide6 UI bound to core.document.convert_document.

T015: Reimplement Document Convert tab UI and bind to core document functions.
"""
from __future__ import annotations

import os
import shutil

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.document import convert_document
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker


class DocumentSection(QScrollArea):
    """Document Convert tab — Word to PDF, PDF to Word, Image to PDF."""

    status_message = Signal(str, bool)   # (text, is_error)
    busy_changed   = Signal(bool)

    _INPUT_FILTER = (
        "Documents (*.pdf *.docx *.doc "
        "*.jpg *.jpeg *.png *.bmp *.gif *.webp)"
    )
    _FORMATS = ["PDF", "DOCX"]

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._selected_format = "DOCX"
        self._last_result_path: str | None = None

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_source_card())
        layout.addWidget(self._build_format_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

        self.setWidget(content)

    # ── Card builders ─────────────────────────────────────────────────────────

    @staticmethod
    def _card() -> QFrame:
        f = QFrame()
        f.setObjectName("Card")
        return f

    @staticmethod
    def _section_header(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("TextSecondary")
        lbl.setStyleSheet(
            "font-size: 11px; font-weight: bold; letter-spacing: 1px; margin-bottom: 2px;"
        )
        return lbl

    def _build_source_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(self._section_header("SOURCE DOCUMENT"))

        row = QHBoxLayout()
        self._file_input = QLineEdit()
        self._file_input.setObjectName("PillInput")
        self._file_input.setPlaceholderText("PDF, Word document, or image…")
        row.addWidget(self._file_input)

        browse_btn = QPushButton("Browse…")
        browse_btn.setObjectName("BrowseBtn")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_file)
        row.addWidget(browse_btn)
        layout.addLayout(row)
        return card

    def _build_format_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(self._section_header("TARGET FORMAT"))

        row = QHBoxLayout()
        row.setSpacing(8)
        self._format_btns: dict[str, QPushButton] = {}
        for fmt in self._FORMATS:
            btn = QPushButton(fmt)
            btn.setObjectName("ChipBtn")
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setFixedWidth(72)
            btn.clicked.connect(lambda _checked, f=fmt: self._select_format(f))
            self._format_btns[fmt] = btn
            row.addWidget(btn)
        row.addStretch()
        layout.addLayout(row)

        self._select_format("DOCX")
        return card

    def _build_output_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(self._section_header("OUTPUT FOLDER"))

        row = QHBoxLayout()
        self._out_input = QLineEdit()
        self._out_input.setObjectName("PillInput")
        self._out_input.setPlaceholderText("Same directory as source file")
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
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("TaskProgressBar")
        self._progress_bar.setRange(0, 0)   # indeterminate initially
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._progress_label = QLabel()
        self._progress_label.setObjectName("TextSecondary")
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)
        return card

    # ── Interaction ───────────────────────────────────────────────────────────

    def _select_format(self, fmt: str) -> None:
        self._selected_format = fmt
        for name, btn in self._format_btns.items():
            active = name == fmt
            btn.setChecked(active)
            btn.setProperty("selected", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _browse_file(self) -> None:
        start = os.path.dirname(self._file_input.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Document", start, self._INPUT_FILTER
        )
        if path:
            self._file_input.setText(path)

    def _browse_output(self) -> None:
        start = self._out_input.text() or os.path.expanduser("~")
        directory = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if directory:
            self._out_input.setText(directory)

    def populate_file(self, path: str) -> None:
        """Pre-populate source file input (called by DnD handler)."""
        self._file_input.setText(path)

    # ── Primary action ────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        """Invoked by MainWindow's primary action button."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        src = self._file_input.text().strip()
        if not src:
            self.status_message.emit("Please select a source document.", True)
            return
        if not os.path.exists(src):
            self.status_message.emit("Source file not found.", True)
            return

        fmt = self._selected_format.lower()
        out_dir = self._out_input.text().strip() or None

        self._set_busy(True)
        self.status_message.emit("Converting document…", False)

        # Capture for closure
        _src = src
        _fmt = fmt
        _out_dir = out_dir

        def do_convert():
            success, output_or_err, _summary = convert_document(_src, _fmt)
            if success and _out_dir and output_or_err:
                dest = os.path.join(_out_dir, os.path.basename(output_or_err))
                shutil.move(output_or_err, dest)
                return {"success": True, "file_path": dest}
            return {
                "success": success,
                "file_path": output_or_err if success else None,
                "error": output_or_err if not success else None,
            }

        self._worker = Worker(do_convert)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    # ── Worker callbacks ──────────────────────────────────────────────────────

    def _set_busy(self, busy: bool) -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if busy:
            self._progress_label.setText("Converting…")
        self.busy_changed.emit(busy)

    def _on_result(self, result: dict) -> None:
        self._set_busy(False)
        self._worker = None
        if result.get("success"):
            fp = result.get("file_path") or ""
            self._last_result_path = fp
            fn = os.path.basename(fp) if fp else "output"
            get_history_manager().add_item(
                HistoryItem(task_type="document", file_name=fn, file_path=fp, status="success")
            )
            self.status_message.emit(f"Done → {fn}", False)
        else:
            err = result.get("error") or "Conversion failed."
            get_history_manager().add_item(
                HistoryItem(
                    task_type="document",
                    file_name=os.path.basename(self._file_input.text()),
                    file_path=self._file_input.text(),
                    status="error",
                )
            )
            self.status_message.emit(f"Error: {err}", True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
