"""High-Res Frame Grabber — video preview + precision extraction to PNG or 16-bit TIFF."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    _MM = True
except ImportError:
    _MM = False

from core.i18n import tr
from core.frame_grabber import grab_frame, VIDEO_EXTS
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


def _ms_to_ts(ms: int) -> str:
    """Convert milliseconds to HH:MM:SS.mmm string."""
    total_s, frac_ms = divmod(max(0, ms), 1000)
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{frac_ms:03d}"


class FrameGrabberSection(QScrollArea):
    """Precision frame extraction — video preview, scrub to frame, grab as PNG or 16-bit TIFF."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_result_path: str | None = None
        self._duration_ms: int = 0
        self._scrubbing: bool = False

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_source_card())

        if _MM:
            layout.addWidget(self._build_player_card())
        else:
            self._fg_mm_warn = QLabel(tr("warn_fg_no_multimedia"))
            self._fg_mm_warn.setObjectName("TextMuted")
            self._fg_mm_warn.setWordWrap(True)
            self._fg_mm_warn.setStyleSheet("padding: 8px;")
            layout.addWidget(self._fg_mm_warn)

        layout.addWidget(self._build_timestamp_card())
        layout.addWidget(self._build_format_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

        self.setWidget(content)

        if _MM:
            self._pos_timer = QTimer(self)
            self._pos_timer.setInterval(150)
            self._pos_timer.timeout.connect(self._update_position)

    # ── Source card ───────────────────────────────────────────────────────────

    def _build_source_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_src = _section_header(tr("hdr_source_video"))
        layout.addWidget(self._hdr_src)

        row = QHBoxLayout()
        self._file_input = QLineEdit()
        self._file_input.setObjectName("PillInput")
        self._file_input.setPlaceholderText(tr("ph_vid"))
        self._file_input.textChanged.connect(self._on_source_changed)
        row.addWidget(self._file_input)

        self._fg_browse_src = QPushButton(tr("btn_browse"))
        self._fg_browse_src.setObjectName("BrowseBtn")
        self._fg_browse_src.setFixedWidth(90)
        self._fg_browse_src.clicked.connect(self._browse_source)
        row.addWidget(self._fg_browse_src)
        layout.addLayout(row)
        return card

    # ── Video player card (mirrors trim section) ──────────────────────────────

    def _build_player_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_preview = _section_header(tr("hdr_frame_preview"))
        layout.addWidget(self._hdr_preview)

        self._video_widget = QVideoWidget()
        self._video_widget.setObjectName("VideoWidget")
        self._video_widget.setMinimumHeight(260)
        self._video_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._video_widget.setVisible(False)
        layout.addWidget(self._video_widget)

        self._audio_output = QAudioOutput()
        self._audio_output.setVolume(0.0)   # muted by default — frame grabber doesn't need audio

        self._player = QMediaPlayer()
        self._player.setVideoOutput(self._video_widget)
        self._player.setAudioOutput(self._audio_output)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)

        # Scrub slider
        self._scrubber = QSlider(Qt.Orientation.Horizontal)
        self._scrubber.setObjectName("Scrubber")
        self._scrubber.setRange(0, 1000)
        self._scrubber.sliderPressed.connect(self._on_scrub_pressed)
        self._scrubber.sliderReleased.connect(self._on_scrub_released)
        self._scrubber.sliderMoved.connect(self._on_scrub_moved)
        layout.addWidget(self._scrubber)

        # Controls row
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        self._play_btn = QPushButton("▶")
        self._play_btn.setObjectName("SecondaryBtn")
        self._play_btn.setFixedSize(42, 42)
        self._play_btn.clicked.connect(self._toggle_play)
        ctrl.addWidget(self._play_btn)

        self._time_label = QLabel("00:00:00.000 / 00:00:00.000")
        self._time_label.setObjectName("TextSecondary")
        self._time_label.setStyleSheet("font-family: monospace; font-size: 13px;")
        ctrl.addWidget(self._time_label)

        ctrl.addStretch()

        # "Use this frame" button — stamps current position into the timestamp input
        self._use_frame_btn = QPushButton(tr("btn_use_this_frame"))
        self._use_frame_btn.setObjectName("BrowseBtn")
        self._use_frame_btn.setFixedHeight(42)
        self._use_frame_btn.setToolTip(tr("tooltip_fg_stamp_frame"))
        self._use_frame_btn.clicked.connect(self._stamp_current_frame)
        self._use_frame_btn.setEnabled(False)
        ctrl.addWidget(self._use_frame_btn)

        layout.addLayout(ctrl)
        return card

    # ── Timestamp card ────────────────────────────────────────────────────────

    def _build_timestamp_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_ts = _section_header(tr("hdr_frame_ts"))
        layout.addWidget(self._hdr_ts)

        self._fg_hint_ts = QLabel(tr("hint_fg_scrub_use_frame"))
        self._fg_hint_ts.setObjectName("TextMuted")
        self._fg_hint_ts.setWordWrap(True)
        self._fg_hint_ts.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._fg_hint_ts)

        row = QHBoxLayout()
        row.setSpacing(12)
        self._timestamp_input = QLineEdit()
        self._timestamp_input.setObjectName("PillInput")
        self._timestamp_input.setPlaceholderText(tr("ph_fg_timestamp"))
        self._timestamp_input.setText("00:00:00")
        self._timestamp_input.setFixedWidth(240)
        row.addWidget(self._timestamp_input)
        row.addStretch()
        layout.addLayout(row)
        return card

    # ── Format card ───────────────────────────────────────────────────────────

    def _build_format_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_fmt = _section_header(tr("hdr_output_format"))
        layout.addWidget(self._hdr_fmt)

        self._fmt_group = QButtonGroup(self)
        self._radio_png = QRadioButton(tr("fmt_fg_png"))
        self._radio_tiff = QRadioButton(tr("fmt_fg_tiff"))
        self._radio_png.setChecked(True)
        self._fmt_group.addButton(self._radio_png, 0)
        self._fmt_group.addButton(self._radio_tiff, 1)

        layout.addWidget(self._radio_png)
        layout.addWidget(self._radio_tiff)

        self._fg_fmt_note = QLabel(tr("note_fg_tiff_precision"))
        self._fg_fmt_note.setObjectName("TextMuted")
        self._fg_fmt_note.setWordWrap(True)
        self._fg_fmt_note.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._fg_fmt_note)
        return card

    # ── Output card ───────────────────────────────────────────────────────────

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_out = _section_header(tr("hdr_output_folder"))
        layout.addWidget(self._hdr_out)

        self._fg_hint_out = QLabel(tr("hint_save_alongside"))
        self._fg_hint_out.setObjectName("TextMuted")
        self._fg_hint_out.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._fg_hint_out)

        row = QHBoxLayout()
        self._out_input = QLineEdit()
        self._out_input.setObjectName("PillInput")
        self._out_input.setPlaceholderText(tr("ph_same_dir_src"))
        if self._settings.output_folder:
            self._out_input.setText(self._settings.output_folder)
        row.addWidget(self._out_input)

        self._fg_browse_out = QPushButton(tr("btn_browse"))
        self._fg_browse_out.setObjectName("BrowseBtn")
        self._fg_browse_out.setFixedWidth(90)
        self._fg_browse_out.clicked.connect(self._browse_output)
        row.addWidget(self._fg_browse_out)
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

        self._result_label = QLabel()
        self._result_label.setObjectName("TextSecondary")
        self._result_label.setWordWrap(True)
        self._result_label.setVisible(False)
        layout.addWidget(self._result_label)
        return card

    # ── Source / player wiring ────────────────────────────────────────────────


    def retranslate_ui(self) -> None:
        if hasattr(self, "_fg_mm_warn"):
            self._fg_mm_warn.setText(tr("warn_fg_no_multimedia"))
        self._hdr_src.setText(tr("hdr_source_video"))
        self._file_input.setPlaceholderText(tr("ph_vid"))
        self._fg_browse_src.setText(tr("btn_browse"))
        if _MM and hasattr(self, "_hdr_preview"):
            self._hdr_preview.setText(tr("hdr_frame_preview"))
            self._use_frame_btn.setText(tr("btn_use_this_frame"))
            self._use_frame_btn.setToolTip(tr("tooltip_fg_stamp_frame"))
        self._hdr_ts.setText(tr("hdr_frame_ts"))
        self._fg_hint_ts.setText(tr("hint_fg_scrub_use_frame"))
        self._timestamp_input.setPlaceholderText(tr("ph_fg_timestamp"))
        self._hdr_fmt.setText(tr("hdr_output_format"))
        self._radio_png.setText(tr("fmt_fg_png"))
        self._radio_tiff.setText(tr("fmt_fg_tiff"))
        self._fg_fmt_note.setText(tr("note_fg_tiff_precision"))
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._out_input.setPlaceholderText(tr("ph_same_dir_src"))
        self._fg_browse_out.setText(tr("btn_browse"))
        self._fg_hint_out.setText(tr("hint_save_alongside"))

    def _on_source_changed(self, path: str) -> None:
        path = path.strip()
        if not _MM or not os.path.isfile(path):
            return
        ext = os.path.splitext(path)[1].lower()
        if ext in VIDEO_EXTS:
            self._load_media(path)

    def _load_media(self, path: str) -> None:
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(path))

    def _on_media_status_changed(self, status) -> None:
        from PySide6.QtMultimedia import QMediaPlayer as _QMP
        if status == _QMP.MediaStatus.LoadedMedia:
            self._video_widget.setVisible(True)
            self._player.play()
            QTimer.singleShot(80, self._player.pause)

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._duration_ms = duration_ms
        self._scrubber.setRange(0, max(1, duration_ms))
        self._time_label.setText(
            f"00:00:00.000 / {_ms_to_ts(duration_ms)}"
        )
        self._use_frame_btn.setEnabled(True)
        self._pos_timer.start()

    def _on_playback_state_changed(self, state) -> None:
        from PySide6.QtMultimedia import QMediaPlayer as _QMP
        self._play_btn.setText(
            "⏸" if state == _QMP.PlaybackState.PlayingState else "▶"
        )

    def _update_position(self) -> None:
        if self._scrubbing or not self._duration_ms:
            return
        pos = self._player.position()
        self._scrubber.setValue(pos)
        self._time_label.setText(f"{_ms_to_ts(pos)} / {_ms_to_ts(self._duration_ms)}")

    def _on_scrub_pressed(self) -> None:
        self._scrubbing = True

    def _on_scrub_released(self) -> None:
        self._player.setPosition(self._scrubber.value())
        QTimer.singleShot(300, lambda: setattr(self, "_scrubbing", False))

    def _on_scrub_moved(self, value: int) -> None:
        if self._duration_ms:
            self._time_label.setText(f"{_ms_to_ts(value)} / {_ms_to_ts(self._duration_ms)}")

    def _toggle_play(self) -> None:
        if not _MM or not hasattr(self, "_player"):
            return
        from PySide6.QtMultimedia import QMediaPlayer as _QMP
        if self._player.playbackState() == _QMP.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _stamp_current_frame(self) -> None:
        """Copy current playback position into the timestamp input."""
        if not _MM or not hasattr(self, "_player"):
            return
        pos = self._player.position()
        self._timestamp_input.setText(_ms_to_ts(pos))

    # ── Browse helpers ────────────────────────────────────────────────────────

    def _browse_source(self) -> None:
        ext_filter = "Video files (" + " ".join(f"*{e}" for e in sorted(VIDEO_EXTS)) + ")"
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", os.path.expanduser("~"), ext_filter
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

    # ── Visibility — pause timer when tab is not visible ──────────────────────

    def showEvent(self, event) -> None:
        if _MM and hasattr(self, "_pos_timer") and self._duration_ms:
            self._pos_timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        if _MM and hasattr(self, "_pos_timer"):
            self._pos_timer.stop()
        super().hideEvent(event)

    # ── Primary action ────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        video_path = self._file_input.text().strip()
        if not video_path or not os.path.isfile(video_path):
            self.status_message.emit("Select a valid video file.", True)
            return

        timestamp = self._timestamp_input.text().strip() or "00:00:00"
        fmt = "tiff" if self._radio_tiff.isChecked() else "png"
        out_dir = self._out_input.text().strip() or None

        if _MM and hasattr(self, "_player"):
            self._player.pause()

        self._result_label.setVisible(False)
        self._set_busy(True, f"Extracting frame at {timestamp}…")

        self._worker = Worker(grab_frame, video_path, timestamp, fmt, out_dir)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool, status_msg: str = "") -> None:
        self._progress_bar.setVisible(busy)
        if busy and status_msg:
            self.status_message.emit(status_msg, False)
        self.busy_changed.emit(busy)

    def _on_result(self, result: dict) -> None:
        self._set_busy(False)
        self._worker = None

        if result["success"]:
            out_path = result["file_path"]
            self._last_result_path = out_path
            self._result_label.setText(f"Saved → {out_path}")
            self._result_label.setVisible(True)
            self.status_message.emit(f"Done → {os.path.basename(out_path)}", False)
            get_history_manager().add_item(HistoryItem(
                task_type="frame_grab",
                file_name=os.path.basename(out_path),
                file_path=out_path,
                status="success",
            ))
        else:
            self.status_message.emit(f"Failed: {result['error']}", True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
