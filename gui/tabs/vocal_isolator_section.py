"""AI Vocal Isolator — HTDemucs 2-stem separation tab."""
from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QProgressBar,
    QPushButton, QRadioButton, QScrollArea,
    QTextEdit, QVBoxLayout, QWidget,
)

from core.i18n import tr
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker
from utils.model_manager import is_demucs_installed, install_demucs


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


# Preset → (model_name, extra_flags, label_key)
_PRESETS = {
    "fast":     ("htdemucs",    ["--no-split"],  "preset_fast"),
    "balanced": ("htdemucs",    [],              "preset_balanced"),
    "quality":  ("htdemucs_ft", [],              "preset_quality"),
}


class VocalIsolatorSection(QScrollArea):
    """2-stem AI vocal separator powered by HTDemucs (fully offline after first run)."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_output_dir: str | None = None
        self._install_worker: Worker | None = None

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._install_banner = self._build_install_banner()
        layout.addWidget(self._install_banner)

        self._tools_container = QWidget()
        tools_layout = QVBoxLayout(self._tools_container)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(16)
        tools_layout.addWidget(self._build_source_card())
        tools_layout.addWidget(self._build_output_card())
        tools_layout.addWidget(self._build_options_card())
        tools_layout.addWidget(self._build_device_card())
        tools_layout.addWidget(self._build_progress_card())
        tools_layout.addWidget(self._build_result_card())
        layout.addWidget(self._tools_container)

        self.setWidget(content)
        self._refresh_install_state()

        # Detect device lazily — avoids torch import blocking startup
        QTimer.singleShot(0, self._detect_device_async)

    # ── Install banner ────────────────────────────────────────────────────────

    def _build_install_banner(self) -> QFrame:
        card = _card()
        card.setStyleSheet(
            "QFrame#Card { border: 1px solid rgba(245,158,11,0.4);"
            " background: rgba(245,158,11,0.06); border-radius: 10px; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        self._install_title = QLabel(f"⚠  {tr('lbl_model_not_installed')}")
        self._install_title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #F59E0B;"
        )
        title_row.addWidget(self._install_title)
        title_row.addStretch()
        layout.addLayout(title_row)

        self._install_desc = QLabel(tr("lbl_model_demucs_desc"))
        self._install_desc.setObjectName("TextMuted")
        self._install_desc.setWordWrap(True)
        self._install_desc.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._install_desc)

        self._install_btn = QPushButton(tr("btn_install_model"))
        self._install_btn.setObjectName("PrimaryBtn")
        self._install_btn.setFixedWidth(160)
        self._install_btn.clicked.connect(self._start_install)
        layout.addWidget(self._install_btn)

        self._install_status = QLabel("")
        self._install_status.setObjectName("TextMuted")
        self._install_status.setStyleSheet("font-size: 12px; color: #3B82F6;")
        self._install_status.setVisible(False)
        layout.addWidget(self._install_status)

        self._install_log = QTextEdit()
        self._install_log.setReadOnly(True)
        self._install_log.setFixedHeight(100)
        self._install_log.setObjectName("PillInput")
        self._install_log.setStyleSheet("font-size: 10px; font-family: monospace;")
        self._install_log.setVisible(False)
        layout.addWidget(self._install_log)

        return card

    def _refresh_install_state(self) -> None:
        installed = is_demucs_installed()
        self._install_banner.setVisible(not installed)
        self._tools_container.setVisible(installed)

    def _start_install(self) -> None:
        self._install_btn.setEnabled(False)
        self._install_status.setText(tr("lbl_model_installing"))
        self._install_status.setVisible(True)
        self._install_log.setVisible(True)
        self._install_log.clear()

        def _log_cb(line: str) -> None:
            if self._install_worker:
                self._install_worker.signals.progress.emit(0, 100, line)

        self._install_worker = Worker(install_demucs, _log_cb)
        self._install_worker.signals.progress.connect(self._on_install_log)
        self._install_worker.signals.result.connect(self._on_install_done)
        self._install_worker.signals.error.connect(self._on_install_error)
        self._install_worker.start()

    def _on_install_log(self, _v: int, _t: int, line: str) -> None:
        if line:
            self._install_log.append(line)

    def _on_install_done(self, _result) -> None:
        self._install_worker = None
        self._install_status.setStyleSheet("font-size: 12px; color: #22C55E;")
        self._install_status.setText(tr("lbl_model_install_done"))
        self._install_btn.setEnabled(True)
        self._refresh_install_state()

    def _on_install_error(self, err_tuple: tuple) -> None:
        self._install_worker = None
        _, msg, _ = err_tuple
        self._install_status.setStyleSheet("font-size: 12px; color: #EF4444;")
        self._install_status.setText(tr("lbl_model_install_failed").format(error=msg))
        self._install_btn.setEnabled(True)

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

    # ── Options card (format + preset) ───────────────────────────────────────

    def _build_options_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        # Output format
        self._hdr_fmt = _section_header(tr("hdr_vocal_output_format"))
        layout.addWidget(self._hdr_fmt)

        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(12)
        self._fmt_group = QButtonGroup(self)
        for i, fmt in enumerate(("WAV", "MP3", "FLAC")):
            rb = QRadioButton(fmt)
            rb.setStyleSheet("font-size: 13px;")
            self._fmt_group.addButton(rb, i)
            fmt_row.addWidget(rb)
            if fmt == "WAV":
                rb.setChecked(True)
        fmt_row.addStretch()
        layout.addLayout(fmt_row)

        # Preset
        self._hdr_preset = _section_header(tr("hdr_vocal_preset"))
        layout.addWidget(self._hdr_preset)

        self._preset_combo = QComboBox()
        self._preset_combo.setObjectName("PillInput")
        self._preset_combo.addItem(tr("preset_fast"),     "fast")
        self._preset_combo.addItem(tr("preset_balanced"), "balanced")
        self._preset_combo.addItem(tr("preset_quality"),  "quality")
        self._preset_combo.setCurrentIndex(1)  # balanced default

        preset_hint = QLabel(tr("hint_vocal_preset"))
        preset_hint.setObjectName("TextMuted")
        preset_hint.setWordWrap(True)
        preset_hint.setStyleSheet("font-size: 11px;")
        self._preset_hint = preset_hint

        layout.addWidget(self._preset_combo)
        layout.addWidget(preset_hint)
        return card

    # ── Device / CPU warning card ─────────────────────────────────────────────

    def _build_device_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(6)

        # Placeholder while detection runs in background
        self._device_lbl = QLabel(f"⚡ {tr('lbl_vocal_device')}: …")
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
        self._warn_lbl.setVisible(False)
        layout.addWidget(self._warn_lbl)
        return card

    def _detect_device_async(self) -> None:
        """Run torch device detection in a Worker so it never blocks the UI."""
        def _do_detect():
            try:
                from core.vocal_isolator import detect_device
                return detect_device()
            except Exception:
                return "cpu"

        w = Worker(_do_detect)
        w.signals.result.connect(self._on_device_detected)
        w.start()
        self._device_worker = w

    def _on_device_detected(self, device: str) -> None:
        device_label = "GPU (CUDA)" if device == "cuda" else "CPU"
        color = "#3B82F6" if device == "cuda" else "#F59E0B"
        self._device_lbl.setText(
            f"⚡ {tr('lbl_vocal_device')}: <b style='color:{color};'>{device_label}</b>"
        )
        self._warn_lbl.setVisible(device == "cpu")
        self._detected_device = device

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
        self._install_title.setText(f"⚠  {tr('lbl_model_not_installed')}")
        self._install_desc.setText(tr("lbl_model_demucs_desc"))
        self._install_btn.setText(tr("btn_install_model"))
        self._hdr_src.setText(tr("hdr_source_file"))
        self._hint_src.setText(tr("hint_vocal_source_formats"))
        self._input_edit.setPlaceholderText(tr("ph_vid_aud"))
        self._browse_in_btn.setText(tr("btn_browse"))
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._output_edit.setPlaceholderText(tr("ph_same_dir"))
        self._browse_out_btn.setText(tr("btn_browse"))
        self._hdr_fmt.setText(tr("hdr_vocal_output_format"))
        self._hdr_preset.setText(tr("hdr_vocal_preset"))
        self._preset_hint.setText(tr("hint_vocal_preset"))
        self._preset_combo.setItemText(0, tr("preset_fast"))
        self._preset_combo.setItemText(1, tr("preset_balanced"))
        self._preset_combo.setItemText(2, tr("preset_quality"))
        self._warn_lbl.setText(f"⚠ {tr('warn_vocal_cpu_time')}")
        self._hdr_result.setText(tr("hdr_result"))
        self._open_btn.setText(tr("btn_open_explorer"))

    def _selected_format(self) -> str:
        btn = self._fmt_group.checkedButton()
        return btn.text().lower() if btn else "wav"

    def _selected_preset(self) -> str:
        return self._preset_combo.currentData() or "balanced"

    def _browse_input(self) -> None:
        try:
            from core.vocal_isolator import SUPPORTED_EXTS as _SE
        except ImportError:
            _SE = {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".mp4", ".mkv"}
        exts = " ".join(f"*{e}" for e in sorted(_SE))
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

        fmt = self._selected_format()
        preset = self._selected_preset()

        self._result_card.setVisible(False)
        self._set_busy(True, tr("dyn_vocal_processing"))

        def _progress_cb(pct: int) -> None:
            if self._worker:
                self._worker.signals.progress.emit(pct, 100, "")

        def _cancelled_cb() -> bool:
            return bool(self._worker and self._worker.is_cancelled)

        from core.vocal_isolator import separate_vocals
        self._worker = Worker(
            separate_vocals,
            input_path,
            output_dir,
            fmt,
            preset,
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
