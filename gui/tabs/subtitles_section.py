"""Subtitles tab — burn-in SRT/VTT/ASS into a video via FFmpeg libass."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.subtitles import burn_subtitles, _VIDEO_EXTS, _SUB_EXTS
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker
from utils.ffmpeg import detect_hw_encoders


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


_HW_LABELS = [
    ("none", "None (CPU)"),
    ("nvidia", "NVIDIA NVENC"),
    ("amd", "AMD AMF"),
    ("intel", "Intel QuickSync"),
]


class SubtitlesSection(QScrollArea):
    """Burn subtitles into a video. Audio stream-copied, video re-encoded."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_video_card())
        layout.addWidget(self._build_sub_card())
        layout.addWidget(self._build_style_card())
        layout.addWidget(self._build_encode_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

        self.setWidget(content)

    def _build_video_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_video = _section_header(tr("hdr_source_video"))
        layout.addWidget(self._hdr_video)
        row = QHBoxLayout()
        self._video_input = QLineEdit()
        self._video_input.setObjectName("PillInput")
        self._video_input.setPlaceholderText(tr("ph_vid"))
        row.addWidget(self._video_input)
        self._browse_video_btn = QPushButton(tr("btn_browse"))
        self._browse_video_btn.setObjectName("BrowseBtn")
        self._browse_video_btn.setFixedWidth(90)
        self._browse_video_btn.clicked.connect(self._browse_video)
        row.addWidget(self._browse_video_btn)
        layout.addLayout(row)
        return card

    def _build_sub_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_sub = _section_header(tr("hdr_subtitle_file"))
        layout.addWidget(self._hdr_sub)
        row = QHBoxLayout()
        self._sub_input = QLineEdit()
        self._sub_input.setObjectName("PillInput")
        self._sub_input.setPlaceholderText(tr("ph_subtitle_file"))
        row.addWidget(self._sub_input)
        self._browse_sub_btn = QPushButton(tr("btn_browse"))
        self._browse_sub_btn.setObjectName("BrowseBtn")
        self._browse_sub_btn.setFixedWidth(90)
        self._browse_sub_btn.clicked.connect(self._browse_sub)
        row.addWidget(self._browse_sub_btn)
        layout.addLayout(row)
        return card

    def _build_style_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_style = _section_header(tr("hdr_subtitle_style"))
        layout.addWidget(self._hdr_style)

        row = QHBoxLayout()
        row.setSpacing(12)
        self._lbl_font_size = QLabel(tr("lbl_font_size"))
        row.addWidget(self._lbl_font_size)
        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(8, 120)
        self._font_size_spin.setValue(28)
        self._font_size_spin.setFixedWidth(80)
        row.addWidget(self._font_size_spin)

        self._lbl_color = QLabel(tr("lbl_font_color"))
        row.addWidget(self._lbl_color)
        self._color_input = QLineEdit("#FFFFFF")
        self._color_input.setFixedWidth(100)
        row.addWidget(self._color_input)

        self._lbl_outline = QLabel(tr("lbl_outline"))
        row.addWidget(self._lbl_outline)
        self._outline_spin = QSpinBox()
        self._outline_spin.setRange(0, 8)
        self._outline_spin.setValue(2)
        self._outline_spin.setFixedWidth(60)
        row.addWidget(self._outline_spin)
        row.addStretch()
        layout.addLayout(row)
        return card

    def _build_encode_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_encode = _section_header(tr("hdr_encode_settings"))
        layout.addWidget(self._hdr_encode)

        row = QHBoxLayout()
        row.setSpacing(12)
        self._lbl_crf = QLabel(tr("lbl_crf"))
        row.addWidget(self._lbl_crf)
        self._crf_spin = QSpinBox()
        self._crf_spin.setRange(14, 32)
        self._crf_spin.setValue(18)
        self._crf_spin.setFixedWidth(70)
        row.addWidget(self._crf_spin)

        self._lbl_hw = QLabel(tr("lbl_hw_accel"))
        row.addWidget(self._lbl_hw)
        self._hw_combo = QComboBox()
        encoders = detect_hw_encoders()
        for key, label in _HW_LABELS:
            if key == "none":
                self._hw_combo.addItem(label, "none")
                continue
            enc_name = {"nvidia": "h264_nvenc", "amd": "h264_amf", "intel": "h264_qsv"}[key]
            if enc_name in encoders:
                self._hw_combo.addItem(label, key)
        row.addWidget(self._hw_combo)
        row.addStretch()
        layout.addLayout(row)
        return card

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_out = _section_header(tr("hdr_output_folder"))
        layout.addWidget(self._hdr_out)
        self._hint_out = QLabel(tr("hint_save_alongside"))
        self._hint_out.setObjectName("TextMuted")
        self._hint_out.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint_out)
        row = QHBoxLayout()
        self._out_input = QLineEdit()
        self._out_input.setObjectName("PillInput")
        self._out_input.setPlaceholderText(tr("ph_same_dir_src"))
        if self._settings.output_folder:
            self._out_input.setText(self._settings.output_folder)
        row.addWidget(self._out_input)
        self._browse_out_btn = QPushButton(tr("btn_browse"))
        self._browse_out_btn.setObjectName("BrowseBtn")
        self._browse_out_btn.setFixedWidth(90)
        self._browse_out_btn.clicked.connect(self._browse_out)
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
        self._result_label = QLabel()
        self._result_label.setObjectName("TextSecondary")
        self._result_label.setWordWrap(True)
        self._result_label.setVisible(False)
        layout.addWidget(self._result_label)
        return card

    def retranslate_ui(self) -> None:
        self._hdr_video.setText(tr("hdr_source_video"))
        self._video_input.setPlaceholderText(tr("ph_vid"))
        self._browse_video_btn.setText(tr("btn_browse"))
        self._hdr_sub.setText(tr("hdr_subtitle_file"))
        self._sub_input.setPlaceholderText(tr("ph_subtitle_file"))
        self._browse_sub_btn.setText(tr("btn_browse"))
        self._hdr_style.setText(tr("hdr_subtitle_style"))
        self._lbl_font_size.setText(tr("lbl_font_size"))
        self._lbl_color.setText(tr("lbl_font_color"))
        self._lbl_outline.setText(tr("lbl_outline"))
        self._hdr_encode.setText(tr("hdr_encode_settings"))
        self._lbl_crf.setText(tr("lbl_crf"))
        self._lbl_hw.setText(tr("lbl_hw_accel"))
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._hint_out.setText(tr("hint_save_alongside"))
        self._out_input.setPlaceholderText(tr("ph_same_dir_src"))
        self._browse_out_btn.setText(tr("btn_browse"))

    # ── Browse helpers ───────────────────────────────────────────────────────
    def _browse_video(self) -> None:
        ext_filter = "Video files (" + " ".join(f"*{e}" for e in sorted(_VIDEO_EXTS)) + ")"
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", os.path.expanduser("~"), ext_filter
        )
        if path:
            self._video_input.setText(path)

    def _browse_sub(self) -> None:
        ext_filter = "Subtitle files (" + " ".join(f"*{e}" for e in sorted(_SUB_EXTS)) + ")"
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Subtitle File", os.path.expanduser("~"), ext_filter
        )
        if path:
            self._sub_input.setText(path)

    def _browse_out(self) -> None:
        start = self._out_input.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if d:
            self._out_input.setText(d)

    def populate_file(self, path: str) -> None:
        ext = os.path.splitext(path)[1].lower()
        if ext in _SUB_EXTS:
            self._sub_input.setText(path)
        else:
            self._video_input.setText(path)

    # ── Action ───────────────────────────────────────────────────────────────
    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        video = self._video_input.text().strip()
        sub = self._sub_input.text().strip()
        if not video or not os.path.isfile(video):
            self.status_message.emit("Select a valid video file.", True)
            return
        if not sub or not os.path.isfile(sub):
            self.status_message.emit("Select a valid subtitle file (.srt/.vtt/.ass).", True)
            return

        out_dir = self._out_input.text().strip() or None
        out_path = None
        if out_dir:
            base, ext = os.path.splitext(os.path.basename(video))
            out_path = os.path.join(out_dir, f"{base}_subbed{ext}")

        font_size = self._font_size_spin.value()
        color = self._color_input.text().strip() or None
        outline = self._outline_spin.value()
        crf = self._crf_spin.value()
        hw = self._hw_combo.currentData() or "none"

        self._result_label.setVisible(False)
        self._set_busy(True, f"Burning subtitles into {os.path.basename(video)}…")

        self._worker = Worker(
            burn_subtitles, video, sub, out_path,
            font_size=font_size, font_color=color, outline=outline,
            crf=crf, hw_accel=hw,
        )
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool, status_msg: str = "") -> None:
        self._progress_bar.setVisible(busy)
        if busy and status_msg:
            self.status_message.emit(status_msg, False)
        self.busy_changed.emit(busy)

    def _on_result(self, out_path: str) -> None:
        self._set_busy(False)
        _old = self._worker
        self._worker = None
        if _old is not None:
            _old.wait(5000)
        self._result_label.setText(f"Saved → {out_path}")
        self._result_label.setVisible(True)
        self.status_message.emit(f"Done → {os.path.basename(out_path)}", False)
        get_history_manager().add_item(HistoryItem(
            task_type="subtitles_burn",
            file_name=os.path.basename(out_path),
            file_path=out_path,
            status="success",
        ))

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        _old = self._worker
        self._worker = None
        if _old is not None:
            _old.wait(5000)
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
