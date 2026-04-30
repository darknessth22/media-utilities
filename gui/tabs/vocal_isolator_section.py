"""AI Vocal Isolator — HTDemucs v4 (Meta) 2-stem separation tab."""
from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from core.i18n import tr
from core.vocal_isolator import SUPPORTED_EXTS, detect_device, separate_vocals
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


class VocalIsolatorSection(QScrollArea):
    """2-stem AI vocal separator powered by HTDemucs (fully offline after first run)."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_output_dir: str | None = None

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_source_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_device_card())
        layout.addWidget(self._build_progress_card())
        layout.addWidget(self._build_result_card())

        self.setWidget(content)

    # ── Source card ───────────────────────────────────────────────────────────

    def _build_source_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._hdr_src = _section_header(tr("hdr_source_file"))
        layout.addWidget(self._hdr_src)

        self._hint_src = QLabel(tr("hint_vocal_source_formats"))
        self._hint_src.setObjectName("TextMuted")
        self._hint_src.setWordWrap(True)
        self._hint_src.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint_src)

        row = QHBoxLayout()
        self._input_edit = QLineEdit()
        self._input_edit.setObjectName("PillInput")
        self._input_edit.setPlaceholderText(tr("ph_vid_aud"))
        row.addWidget(self._input_edit)

        self._browse_in_btn = QPushButton(tr("btn_browse"))
        self._browse_in_btn.setObjectName("BrowseBtn")
        self._browse_in_btn.setFixedWidth(90)
        self._browse_in_btn.clicked.connect(self._browse_input)
        row.addWidget(self._browse_in_btn)
        layout.addLayout(row)
        return card

    # ── Output folder card ────────────────────────────────────────────────────

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._hdr_out = _section_header(tr("hdr_output_folder"))
        layout.addWidget(self._hdr_out)

        row = QHBoxLayout()
        self._output_edit = QLineEdit()
        self._output_edit.setObjectName("PillInput")
        self._output_edit.setPlaceholderText(tr("ph_same_dir"))
        row.addWidget(self._output_edit)

        self._browse_out_btn = QPushButton(tr("btn_browse"))
        self._browse_out_btn.setObjectName("BrowseBtn")
        self._browse_out_btn.setFixedWidth(90)
        self._browse_out_btn.clicked.connect(self._browse_output)
        row.addWidget(self._browse_out_btn)
        layout.addLayout(row)
        return card

    # ── Device / CPU warning card ──────────────────────────────────────────────

    def _build_device_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(6)

        device = detect_device()
        device_label = "GPU (CUDA)" if device == "cuda" else "CPU"
        color = "#3B82F6" if device == "cuda" else "#F59E0B"

        self._device_lbl = QLabel(
            f"⚡ {tr('lbl_vocal_device')}: <b style='color:{color};'>{device_label}</b>"
        )
        self._device_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._device_lbl.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._device_lbl)

        self._warn_lbl = QLabel(f"⚠ {tr('warn_vocal_cpu_time')}")
        self._warn_lbl.setObjectName("TextMuted")
        self._warn_lbl.setWordWrap(True)
        self._warn_lbl.setStyleSheet(
            "font-size: 12px; color: #F59E0B; "
            "background: rgba(245,158,11,0.08); "
            "border: 1px solid rgba(245,158,11,0.25); "
            "border-radius: 6px; padding: 6px 10px;"
        )
        self._warn_lbl.setVisible(device == "cpu")
        layout.addWidget(self._warn_lbl)
        return card

    # ── Progress card ─────────────────────────────────────────────────────────

    def _build_progress_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("TaskProgressBar")
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._progress_lbl = QLabel("")
        self._progress_lbl.setObjectName("TextMuted")
        self._progress_lbl.setStyleSheet("font-size: 11px;")
        self._progress_lbl.setVisible(False)
        layout.addWidget(self._progress_lbl)
        return card

    # ── Result card ───────────────────────────────────────────────────────────

    def _build_result_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        self._hdr_result = _section_header(tr("hdr_result"))
        layout.addWidget(self._hdr_result)

        self._vocals_lbl = QLabel("")
        self._vocals_lbl.setWordWrap(True)
        self._vocals_lbl.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._vocals_lbl)

        self._accomp_lbl = QLabel("")
        self._accomp_lbl.setWordWrap(True)
        self._accomp_lbl.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._accomp_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._open_btn = QPushButton(tr("btn_open_explorer"))
        self._open_btn.setObjectName("BrowseBtn")
        self._open_btn.setVisible(False)
        self._open_btn.clicked.connect(self._open_output_folder)
        btn_row.addWidget(self._open_btn)
        layout.addLayout(btn_row)

        card.setVisible(False)
        self._result_card = card
        return card

    # ── Helpers ───────────────────────────────────────────────────────────────

    def retranslate_ui(self) -> None:
        self._hdr_src.setText(tr("hdr_source_file"))
        self._hint_src.setText(tr("hint_vocal_source_formats"))
        self._input_edit.setPlaceholderText(tr("ph_vid_aud"))
        self._browse_in_btn.setText(tr("btn_browse"))
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._output_edit.setPlaceholderText(tr("ph_same_dir"))
        self._browse_out_btn.setText(tr("btn_browse"))
        self._warn_lbl.setText(f"⚠ {tr('warn_vocal_cpu_time')}")
        self._hdr_result.setText(tr("hdr_result"))
        self._open_btn.setText(tr("btn_open_explorer"))

    def _browse_input(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTS))
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Audio / Video File",
            os.path.expanduser("~"),
            f"Audio/Video ({exts})",
        )
        if path:
            self._input_edit.setText(path)

    def _browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", os.path.expanduser("~")
        )
        if folder:
            self._output_edit.setText(folder)

    def populate_file(self, path: str) -> None:
        self._input_edit.setText(path)

    def _set_busy(self, busy: bool, msg: str = "") -> None:
        self._progress_bar.setVisible(busy)
        self._progress_lbl.setVisible(busy)
        if busy:
            self._progress_bar.setValue(0)
            if msg:
                self.status_message.emit(msg, False)
        self.busy_changed.emit(busy)

    def _on_progress(self, value: int, _total: int, _label: str) -> None:
        self._progress_bar.setValue(value)
        self._progress_lbl.setText(f"{value}%")

    def _open_output_folder(self) -> None:
        if self._last_output_dir and os.path.isdir(self._last_output_dir):
            if sys.platform == "win32":
                subprocess.Popen(["explorer", os.path.normpath(self._last_output_dir)])
            else:
                from PySide6.QtGui import QDesktopServices
                from PySide6.QtCore import QUrl
                QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_output_dir))

    # ── Primary action ────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        input_path = self._input_edit.text().strip()
        if not input_path or not os.path.isfile(input_path):
            self.status_message.emit(tr("err_vocal_no_input"), True)
            return

        output_dir = self._output_edit.text().strip()
        if not output_dir:
            output_dir = os.path.dirname(input_path)

        self._result_card.setVisible(False)
        self._set_busy(True, tr("dyn_vocal_processing"))

        # Build worker with progress + cancellation callbacks via closures.
        def _progress_cb(pct: int) -> None:
            if self._worker:
                self._worker.signals.progress.emit(pct, 100, "")

        def _cancelled_cb() -> bool:
            return bool(self._worker and self._worker.is_cancelled)

        self._worker = Worker(
            separate_vocals,
            input_path,
            output_dir,
            _progress_cb,
            _cancelled_cb,
        )
        self._worker.signals.progress.connect(self._on_progress)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _on_result(self, result: dict) -> None:
        self._set_busy(False)
        self._worker = None

        if not result.get("success"):
            self.status_message.emit(f"Failed: {result.get('error', 'unknown')}", True)
            return

        self._last_output_dir = result["output_dir"]
        vocals = result["vocals_path"]
        accomp = result["accompaniment_path"]

        self._vocals_lbl.setText(f"🎤 {tr('lbl_vocal_vocals')}: {os.path.basename(vocals)}")
        self._accomp_lbl.setText(f"🎵 {tr('lbl_vocal_accompaniment')}: {os.path.basename(accomp)}")
        self._open_btn.setVisible(True)
        self._result_card.setVisible(True)

        get_history_manager().add_item(HistoryItem(
            task_type="vocal_isolate",
            file_name=os.path.basename(self._input_edit.text()),
            file_path=vocals,
            status="success",
        ))

        self.status_message.emit(
            f"Done [{result['device'].upper()}] → {os.path.basename(vocals)}", False
        )

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
