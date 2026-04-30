"""Auto-Chunker tab — split media by exact duration or MB size (stream copy)."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.chunker import split_by_duration, split_by_size
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


class ChunkSection(QScrollArea):
    """Slice a media file into parts by duration or target size (stream copy, no re-encode)."""

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
        layout.addWidget(self._build_mode_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())
        self.setWidget(content)

    # ── Source card ───────────────────────────────────────────────────────────

    def _build_source_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_src = _section_header(tr("hdr_source_file"))
        layout.addWidget(self._hdr_src)

        row = QHBoxLayout()
        self._file_input = QLineEdit()
        self._file_input.setObjectName("PillInput")
        self._file_input.setPlaceholderText(tr("ph_vid_to_split"))
        row.addWidget(self._file_input)

        self._browse_src_btn = QPushButton(tr("btn_browse"))
        self._browse_src_btn.setObjectName("BrowseBtn")
        self._browse_src_btn.setFixedWidth(90)
        self._browse_src_btn.clicked.connect(self._browse_file)
        row.addWidget(self._browse_src_btn)
        layout.addLayout(row)
        return card

    # ── Mode card ─────────────────────────────────────────────────────────────

    def _build_mode_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)
        self._hdr_split = _section_header(tr("hdr_split_mode"))
        layout.addWidget(self._hdr_split)

        self._hint_mode = QLabel(tr("hint_chunk_stream_copy"))
        self._hint_mode.setObjectName("TextMuted")
        self._hint_mode.setWordWrap(True)
        self._hint_mode.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint_mode)

        self._mode_group = QButtonGroup(self)
        self._radio_duration = QRadioButton(tr("lbl_by_duration"))
        self._radio_size = QRadioButton(tr("lbl_by_size"))
        self._radio_duration.setChecked(True)
        self._mode_group.addButton(self._radio_duration, 0)
        self._mode_group.addButton(self._radio_size, 1)
        self._radio_duration.toggled.connect(self._on_mode_changed)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(24)
        mode_row.addWidget(self._radio_duration)
        mode_row.addWidget(self._radio_size)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # Duration row
        self._dur_row = QWidget()
        dur_layout = QHBoxLayout(self._dur_row)
        dur_layout.setContentsMargins(0, 0, 0, 0)
        dur_layout.setSpacing(10)
        self._lbl_segment_len = QLabel(tr("lbl_segment_len"))
        dur_layout.addWidget(self._lbl_segment_len)
        self._dur_spin = QDoubleSpinBox()
        self._dur_spin.setRange(1, 86400)
        self._dur_spin.setValue(60)
        self._dur_spin.setDecimals(0)
        self._dur_spin.setSuffix(" s")
        self._dur_spin.setFixedWidth(110)
        dur_layout.addWidget(self._dur_spin)
        dur_layout.addStretch()
        layout.addWidget(self._dur_row)

        # Size row
        self._size_row = QWidget()
        size_layout = QHBoxLayout(self._size_row)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.setSpacing(10)
        self._lbl_max_chunk_mb = QLabel(tr("lbl_max_chunk_mb"))
        size_layout.addWidget(self._lbl_max_chunk_mb)
        self._size_spin = QDoubleSpinBox()
        self._size_spin.setRange(0.1, 100000)
        self._size_spin.setValue(50)
        self._size_spin.setDecimals(1)
        self._size_spin.setSuffix(" MB")
        self._size_spin.setFixedWidth(130)
        size_layout.addWidget(self._size_spin)
        size_layout.addStretch()
        self._size_row.setVisible(False)
        layout.addWidget(self._size_row)

        return card

    def _on_mode_changed(self, dur_checked: bool) -> None:
        self._dur_row.setVisible(dur_checked)
        self._size_row.setVisible(not dur_checked)

    # ── Output card ───────────────────────────────────────────────────────────

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_out = _section_header(tr("hdr_output_folder"))
        layout.addWidget(self._hdr_out)

        self._hint_parts = QLabel(tr("hint_parts_named"))
        self._hint_parts.setObjectName("TextMuted")
        self._hint_parts.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint_parts)

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

        self._progress_label = QLabel()
        self._progress_label.setObjectName("TextSecondary")
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)
        return card

    # ── Browsing ──────────────────────────────────────────────────────────────


    def retranslate_ui(self) -> None:
        self._hdr_src.setText(tr("hdr_source_file"))
        self._file_input.setPlaceholderText(tr("ph_vid_to_split"))
        self._browse_src_btn.setText(tr("btn_browse"))
        self._hdr_split.setText(tr("hdr_split_mode"))
        self._hint_mode.setText(tr("hint_chunk_stream_copy"))
        self._radio_duration.setText(tr("lbl_by_duration"))
        self._radio_size.setText(tr("lbl_by_size"))
        self._lbl_segment_len.setText(tr("lbl_segment_len"))
        self._lbl_max_chunk_mb.setText(tr("lbl_max_chunk_mb"))
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._out_input.setPlaceholderText(tr("ph_same_dir"))
        self._browse_out_btn.setText(tr("btn_browse"))
        self._hint_parts.setText(tr("hint_parts_named"))

    def _browse_file(self) -> None:
        start = os.path.dirname(self._file_input.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Media File", start,
            "Media (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.mp3 *.wav *.aac *.flac *.ogg *.m4a)"
        )
        if path:
            self._file_input.setText(path)

    def _browse_output(self) -> None:
        start = self._out_input.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if d:
            self._out_input.setText(d)

    def populate_file(self, path: str) -> None:
        self._file_input.setText(path)

    # ── Primary action ────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        src = self._file_input.text().strip()
        if not src or not os.path.isfile(src):
            self.status_message.emit("Select a valid media file first.", True)
            return

        out_dir = self._out_input.text().strip() or None
        use_duration = self._radio_duration.isChecked()

        if use_duration:
            secs = self._dur_spin.value()
            label = f"{int(secs)}s segments"

            def _do():
                return split_by_duration(src, secs, out_dir)
        else:
            mb = self._size_spin.value()
            label = f"~{mb:.1f} MB chunks"

            def _do():
                return split_by_size(src, mb, out_dir)

        self._pending_src = src
        self._pending_label = label
        self._set_busy(True, f"Splitting into {label}…", f"Running FFmpeg…")

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

    def _on_result(self, success: bool) -> None:
        self._set_busy(False)
        self._worker = None
        src = self._pending_src
        base = os.path.splitext(os.path.basename(src))[0]
        ext = os.path.splitext(src)[1]

        if success:
            get_history_manager().add_item(HistoryItem(
                task_type="chunk",
                file_name=f"{base}_part000{ext}",
                file_path=src,
                status="success",
            ))
            self.status_message.emit(f"Done → {self._pending_label} saved.", False)
        else:
            self.status_message.emit("Split failed — check file and settings.", True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
