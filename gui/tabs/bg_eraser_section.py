"""AI Background Eraser — offline rembg-powered background removal."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from core.bg_eraser import remove_background, IMAGE_EXTS
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker


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


class BgEraserSection(QScrollArea):
    """Single-image background remover powered by rembg (fully offline)."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_result_path: str | None = None

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_source_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())
        layout.addWidget(self._build_preview_card())

        self.setWidget(content)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._load_input_preview)

    # ── Source card ───────────────────────────────────────────────────────────

    def _build_source_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("SOURCE IMAGE"))

        hint = QLabel(
            "Accepts JPG, PNG, WEBP, BMP. Output is always a PNG with transparent background. "
            "First run downloads the AI model (~170 MB) and caches it locally."
        )
        hint.setObjectName("TextMuted")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(hint)

        row = QHBoxLayout()
        self._input_edit = QLineEdit()
        self._input_edit.setObjectName("PillInput")
        self._input_edit.setPlaceholderText("Path to image…")
        self._input_edit.textChanged.connect(self._on_input_changed)
        row.addWidget(self._input_edit)

        browse_btn = QPushButton("Browse…")
        browse_btn.setObjectName("BrowseBtn")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_input)
        row.addWidget(browse_btn)
        layout.addLayout(row)

        # Input preview thumbnail
        self._input_preview = QLabel("No preview")
        self._input_preview.setFixedSize(220, 140)
        self._input_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._input_preview.setObjectName("Card")
        self._input_preview.setStyleSheet(
            "QLabel#Card { border-radius: 6px; background: #1C2128;"
            " color: #8B949E; font-size: 12px; }"
        )
        layout.addWidget(self._input_preview)
        return card

    # ── Output card ───────────────────────────────────────────────────────────

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("OUTPUT FILE"))

        row = QHBoxLayout()
        self._output_edit = QLineEdit()
        self._output_edit.setObjectName("PillInput")
        self._output_edit.setPlaceholderText("Auto — <source_name>_nobg.png")
        row.addWidget(self._output_edit)

        browse_btn = QPushButton("Browse…")
        browse_btn.setObjectName("BrowseBtn")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_output)
        row.addWidget(browse_btn)
        layout.addLayout(row)
        return card

    # ── Progress card ─────────────────────────────────────────────────────────

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
        return card

    # ── Result preview card ───────────────────────────────────────────────────

    def _build_preview_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("RESULT PREVIEW"))

        self._result_preview = QLabel("Run the eraser to see the result here.")
        self._result_preview.setMinimumSize(400, 200)
        self._result_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._result_preview.setObjectName("Card")
        self._result_preview.setWordWrap(True)
        self._result_preview.setStyleSheet(
            "QLabel#Card { border-radius: 6px; background: repeating-conic-gradient("
            "#2A2A3A 0% 25%, #1C1C2A 0% 50%) 0 0 / 20px 20px;"
            " color: #8B949E; font-size: 12px; }"
        )
        layout.addWidget(self._result_preview)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self._open_btn = QPushButton("Open in Explorer")
        self._open_btn.setObjectName("BrowseBtn")
        self._open_btn.setVisible(False)
        self._open_btn.clicked.connect(self._open_result_folder)
        btn_row.addWidget(self._open_btn)
        layout.addLayout(btn_row)

        card.setVisible(False)
        self._result_card = card
        return card

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _browse_input(self) -> None:
        ext_filter = "Images (" + " ".join(f"*{e}" for e in sorted(IMAGE_EXTS)) + ")"
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", os.path.expanduser("~"), ext_filter
        )
        if path:
            self._input_edit.setText(path)

    def _browse_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Output PNG", os.path.expanduser("~"), "PNG image (*.png)"
        )
        if path:
            if not path.lower().endswith(".png"):
                path += ".png"
            self._output_edit.setText(path)

    def _on_input_changed(self, path: str) -> None:
        self._preview_timer.start()
        # Auto-fill output path
        path = path.strip()
        if path and os.path.isfile(path) and not self._output_edit.text().strip():
            stem = os.path.splitext(path)[0]
            self._output_edit.setPlaceholderText(f"{stem}_nobg.png")

    def _load_input_preview(self) -> None:
        path = self._input_edit.text().strip()
        if not path or not os.path.isfile(path):
            self._input_preview.setPixmap(QPixmap())
            self._input_preview.setText("No preview")
            return
        px = QPixmap(path)
        if not px.isNull():
            self._input_preview.setPixmap(
                px.scaled(220, 140, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
            self._input_preview.setText("")
        else:
            self._input_preview.setText("Cannot load image")

    def populate_file(self, path: str) -> None:
        self._input_edit.setText(path)

    def _set_busy(self, busy: bool, msg: str = "") -> None:
        self._progress_bar.setVisible(busy)
        if busy and msg:
            self.status_message.emit(msg, False)
        self.busy_changed.emit(busy)

    def _open_result_folder(self) -> None:
        if self._last_result_path and os.path.isfile(self._last_result_path):
            import subprocess, sys
            if sys.platform == "win32":
                subprocess.Popen(
                    ["explorer", "/select,", os.path.normpath(self._last_result_path)]
                )
            else:
                from PySide6.QtGui import QDesktopServices
                from PySide6.QtCore import QUrl
                QDesktopServices.openUrl(
                    QUrl.fromLocalFile(os.path.dirname(self._last_result_path))
                )

    # ── Primary action ────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        input_path = self._input_edit.text().strip()
        if not input_path or not os.path.isfile(input_path):
            self.status_message.emit("Select a valid image file.", True)
            return

        output_path = self._output_edit.text().strip() or None

        self._result_card.setVisible(False)
        self._set_busy(True, "Removing background (first run downloads ~170 MB model)…")

        self._worker = Worker(remove_background, input_path, output_path)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _on_result(self, result: dict) -> None:
        self._set_busy(False)
        self._worker = None

        if not result["success"]:
            self.status_message.emit(f"Failed: {result['error']}", True)
            return

        out_path = result["file_path"]
        self._last_result_path = out_path

        px = QPixmap(out_path)
        if not px.isNull():
            self._result_preview.setPixmap(
                px.scaled(600, 400, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
            self._result_preview.setText("")
        else:
            self._result_preview.setText(out_path)

        self._open_btn.setVisible(True)
        self._result_card.setVisible(True)

        get_history_manager().add_item(HistoryItem(
            task_type="bg_erase",
            file_name=os.path.basename(self._input_edit.text()),
            file_path=out_path,
            status="success",
        ))

        self.status_message.emit(f"Done → {os.path.basename(out_path)}", False)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
