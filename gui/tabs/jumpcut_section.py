"""Jump-Cutter tab — auto-remove silence from audio/video via FFmpeg silencedetect."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.jumpcutter import (
    _AUDIO_EXTS,
    _VIDEO_EXTS,
    parse_protected_ranges,
    remove_silence,
)
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker

_ALL_EXTS = _AUDIO_EXTS | _VIDEO_EXTS


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


class JumpcutSection(QScrollArea):
    """Auto-silence removal tab."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_result_path: str | None = None

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAcceptDrops(True)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_source_card())
        layout.addWidget(self._build_params_card())
        layout.addWidget(self._build_protected_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())
        self.setWidget(content)

    # ── Source ────────────────────────────────────────────────────────────────

    def _build_source_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_src = _section_header(tr("hdr_source_file"))
        layout.addWidget(self._hdr_src)

        self._hint = QLabel(tr("hint_jumpcut_intro"))
        self._hint.setObjectName("TextMuted")
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint)

        row = QHBoxLayout()
        self._file_input = QLineEdit()
        self._file_input.setObjectName("PillInput")
        self._file_input.setPlaceholderText(tr("ph_vid_aud"))
        row.addWidget(self._file_input)

        self._browse_src_btn = QPushButton(tr("btn_browse"))
        self._browse_src_btn.setObjectName("BrowseBtn")
        self._browse_src_btn.setFixedWidth(90)
        self._browse_src_btn.clicked.connect(self._browse_file)
        row.addWidget(self._browse_src_btn)
        layout.addLayout(row)
        return card

    # ── Params ────────────────────────────────────────────────────────────────

    def _build_params_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)
        self._hdr_params = _section_header(tr("hdr_jumpcut_params"))
        layout.addWidget(self._hdr_params)

        # Noise floor (dB): -20 to -40, default -30
        self._lbl_noise = QLabel(tr("lbl_jumpcut_noise").format(db=-30))
        layout.addWidget(self._lbl_noise)
        self._noise_slider = QSlider(Qt.Orientation.Horizontal)
        self._noise_slider.setRange(-40, -20)
        self._noise_slider.setValue(-30)
        self._noise_slider.setTickInterval(5)
        self._noise_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._noise_slider.valueChanged.connect(
            lambda v: self._lbl_noise.setText(tr("lbl_jumpcut_noise").format(db=v))
        )
        layout.addWidget(self._noise_slider)

        # Min silence duration (seconds): 0.1 to 3.0, step 0.1, default 0.5
        self._lbl_dur = QLabel(tr("lbl_jumpcut_minsil").format(s=0.5))
        layout.addWidget(self._lbl_dur)
        self._dur_slider = QSlider(Qt.Orientation.Horizontal)
        self._dur_slider.setRange(1, 30)  # tenths of a second
        self._dur_slider.setValue(5)
        self._dur_slider.setTickInterval(5)
        self._dur_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._dur_slider.valueChanged.connect(
            lambda v: self._lbl_dur.setText(tr("lbl_jumpcut_minsil").format(s=v / 10.0))
        )
        layout.addWidget(self._dur_slider)

        # Padding: 0 to 50 (hundredths of a second), default 5 (50 ms)
        self._lbl_pad = QLabel(tr("lbl_jumpcut_padding").format(ms=50))
        layout.addWidget(self._lbl_pad)
        self._pad_slider = QSlider(Qt.Orientation.Horizontal)
        self._pad_slider.setRange(0, 50)
        self._pad_slider.setValue(5)
        self._pad_slider.setTickInterval(10)
        self._pad_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._pad_slider.valueChanged.connect(
            lambda v: self._lbl_pad.setText(tr("lbl_jumpcut_padding").format(ms=v * 10))
        )
        layout.addWidget(self._pad_slider)
        return card

    # ── Protected ranges ──────────────────────────────────────────────────────

    def _build_protected_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        self._hdr_protected = _section_header(tr("hdr_jumpcut_protected"))
        layout.addWidget(self._hdr_protected)

        self._lbl_protected_hint = QLabel(tr("hint_jumpcut_protected"))
        self._lbl_protected_hint.setObjectName("TextMuted")
        self._lbl_protected_hint.setWordWrap(True)
        self._lbl_protected_hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._lbl_protected_hint)

        self._protected_edit = QPlainTextEdit()
        self._protected_edit.setObjectName("PillInput")
        self._protected_edit.setPlaceholderText(tr("ph_jumpcut_protected"))
        self._protected_edit.setFixedHeight(110)
        self._protected_edit.textChanged.connect(self._update_protected_status)
        layout.addWidget(self._protected_edit)

        self._lbl_protected_status = QLabel("")
        self._lbl_protected_status.setObjectName("TextSecondary")
        self._lbl_protected_status.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._lbl_protected_status)
        return card

    def _update_protected_status(self) -> None:
        text = self._protected_edit.toPlainText()
        ranges, errors = parse_protected_ranges(text)
        if errors:
            self._lbl_protected_status.setText(
                tr("lbl_jumpcut_protected_err").format(n=len(errors), line=errors[0][:60])
            )
            self._lbl_protected_status.setStyleSheet("color:#e06c75; font-size: 11px;")
        else:
            self._lbl_protected_status.setText(
                tr("lbl_jumpcut_protected_ok").format(n=len(ranges))
            )
            self._lbl_protected_status.setStyleSheet("font-size: 11px;")

    # ── Output / progress ─────────────────────────────────────────────────────

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_out = _section_header(tr("hdr_output_folder"))
        layout.addWidget(self._hdr_out)

        row = QHBoxLayout()
        self._out_input = QLineEdit()
        self._out_input.setObjectName("PillInput")
        self._out_input.setPlaceholderText(tr("ph_same_dir"))
        if self._settings.output_folder:
            self._out_input.setText(self._settings.output_folder)
        row.addWidget(self._out_input)

        self._browse_out_btn = QPushButton(tr("btn_browse"))
        self._browse_out_btn.setObjectName("BrowseBtn")
        self._browse_out_btn.setFixedWidth(90)
        self._browse_out_btn.clicked.connect(self._browse_output)
        row.addWidget(self._browse_out_btn)
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

    # ── Browse / DnD ──────────────────────────────────────────────────────────

    def _browse_file(self) -> None:
        start = os.path.dirname(self._file_input.text()) or os.path.expanduser("~")
        ext_filter = "Media (" + " ".join(f"*{e}" for e in sorted(_ALL_EXTS)) + ")"
        path, _ = QFileDialog.getOpenFileName(self, "Select Media File", start, ext_filter)
        if path:
            self._file_input.setText(path)

    def _browse_output(self) -> None:
        start = self._out_input.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if d:
            self._out_input.setText(d)

    def populate_file(self, path: str) -> None:
        self._file_input.setText(path)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p and os.path.splitext(p)[1].lower() in _ALL_EXTS:
                self._file_input.setText(p)
                event.acceptProposedAction()
                return
        event.ignore()

    # ── i18n ──────────────────────────────────────────────────────────────────

    def retranslate_ui(self) -> None:
        self._hdr_src.setText(tr("hdr_source_file"))
        self._hint.setText(tr("hint_jumpcut_intro"))
        self._file_input.setPlaceholderText(tr("ph_vid_aud"))
        self._browse_src_btn.setText(tr("btn_browse"))
        self._hdr_params.setText(tr("hdr_jumpcut_params"))
        self._lbl_noise.setText(tr("lbl_jumpcut_noise").format(db=self._noise_slider.value()))
        self._lbl_dur.setText(tr("lbl_jumpcut_minsil").format(s=self._dur_slider.value() / 10.0))
        self._lbl_pad.setText(tr("lbl_jumpcut_padding").format(ms=self._pad_slider.value() * 10))
        self._hdr_protected.setText(tr("hdr_jumpcut_protected"))
        self._lbl_protected_hint.setText(tr("hint_jumpcut_protected"))
        self._protected_edit.setPlaceholderText(tr("ph_jumpcut_protected"))
        self._update_protected_status()
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._out_input.setPlaceholderText(tr("ph_same_dir"))
        self._browse_out_btn.setText(tr("btn_browse"))

    # ── Primary action ────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        src = self._file_input.text().strip()
        if not src or not os.path.exists(src):
            self.status_message.emit("Please select a valid media file.", True)
            return
        if os.path.splitext(src)[1].lower() not in _ALL_EXTS:
            self.status_message.emit("Unsupported file type.", True)
            return

        out_dir = self._out_input.text().strip() or None
        noise_db = float(self._noise_slider.value())
        min_dur = self._dur_slider.value() / 10.0
        padding = self._pad_slider.value() / 100.0

        protected, errors = parse_protected_ranges(self._protected_edit.toPlainText())
        if errors:
            self.status_message.emit(
                tr("err_jumpcut_protected").format(line=errors[0][:60]), True
            )
            return

        self._set_busy(True, "Removing silence…", "Detecting and cutting silences…")

        def _do():
            return remove_silence(src, noise_db, min_dur, padding, out_dir, protected)

        self._pending_src = src
        self._worker = Worker(_do)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool, status_msg: str = "", progress_msg: str = "") -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if busy:
            self._progress_label.setText(progress_msg)
            self.status_message.emit(status_msg, False)
        self.busy_changed.emit(busy)

    def _on_result(self, result: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        success, out_path, stats = result
        src = self._pending_src

        if success and out_path:
            self._last_result_path = out_path
            saved = max(0.0, stats.get("orig_duration", 0) - stats.get("new_duration", 0))
            n = stats.get("silences_removed", 0)
            get_history_manager().add_item(HistoryItem(
                task_type="jumpcut",
                file_name=os.path.basename(out_path),
                file_path=out_path,
                status="success",
            ))
            self.status_message.emit(
                f"Done → {os.path.basename(out_path)} ({n} silence(s) cut, {saved:.1f}s saved)",
                False,
            )
        else:
            get_history_manager().add_item(HistoryItem(
                task_type="jumpcut",
                file_name=os.path.basename(src),
                file_path=src,
                status="error",
            ))
            self.status_message.emit("No silences found or operation failed.", True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
