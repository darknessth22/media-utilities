"""Trim Media tab — PySide6 QMediaPlayer + QVideoWidget.

T014: Replace VLC video trimmer with PySide6 QMediaPlayer + QVideoWidget.
      Preserves the fallback behaviour (text-only time inputs) when the
      multimedia backend is unavailable or the file is audio-only.

FR-011: The existing VLC-based visual trimmer MUST be replaced with a
        QWidget using PySide6.QtMultimedia (QMediaPlayer + QVideoWidget).
        Fallback (text-only) is preserved.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl, Signal, QTimer
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
    QSlider,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    _MULTIMEDIA_AVAILABLE = True
except ImportError:
    _MULTIMEDIA_AVAILABLE = False

from core.trimmer import trim_media
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker

_AUDIO_EXTS = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"}
_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}


def _ms_to_str(ms: int) -> str:
    """Convert milliseconds to HH:MM:SS string."""
    total_s = max(0, ms // 1000)
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _str_to_ms(text: str) -> int | None:
    """Parse HH:MM:SS / MM:SS / SS to milliseconds, or None on error."""
    try:
        parts = list(map(int, text.strip().split(":")))
        if len(parts) == 1:
            return parts[0] * 1000
        if len(parts) == 2:
            return (parts[0] * 60 + parts[1]) * 1000
        if len(parts) == 3:
            return (parts[0] * 3600 + parts[1] * 60 + parts[2]) * 1000
    except (ValueError, AttributeError):
        pass
    return None


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


class TrimSection(QScrollArea):
    """Trim Media tab — video/audio trimmer powered by QMediaPlayer."""

    status_message = Signal(str, bool)
    busy_changed   = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._duration_ms: int = 0
        self._is_audio_only = False
        self._last_result_path: str | None = None

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(20, 20, 20, 20)
        self._content_layout.setSpacing(16)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._content_layout.addWidget(self._build_source_card())

        # Video preview (only when multimedia is available)
        if _MULTIMEDIA_AVAILABLE:
            self._content_layout.addWidget(self._build_player_card())
        else:
            self._no_player_label = QLabel(
                "ℹ  PySide6.QtMultimedia is not installed — "
                "video preview unavailable.\n"
                "You can still trim by entering start/end times manually."
            )
            self._no_player_label.setObjectName("TextMuted")
            self._no_player_label.setWordWrap(True)
            self._no_player_label.setStyleSheet("padding: 8px;")
            self._content_layout.addWidget(self._no_player_label)

        self._content_layout.addWidget(self._build_time_card())
        self._content_layout.addWidget(self._build_output_card())
        self._content_layout.addWidget(self._build_progress_card())

        self.setWidget(content)

        # Position polling timer
        if _MULTIMEDIA_AVAILABLE:
            self._pos_timer = QTimer(self)
            self._pos_timer.setInterval(200)
            self._pos_timer.timeout.connect(self._update_position)

    # ── Card builders ──────────────────────────────────────────────────────────

    def _build_source_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("SOURCE FILE"))

        row = QHBoxLayout()
        self._file_input = QLineEdit()
        self._file_input.setObjectName("PillInput")
        self._file_input.setPlaceholderText("Video or audio file…")
        self._file_input.textChanged.connect(self._on_source_changed)
        row.addWidget(self._file_input)

        browse_btn = QPushButton("Browse…")
        browse_btn.setObjectName("BrowseBtn")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_file)
        row.addWidget(browse_btn)
        layout.addLayout(row)

        self._large_file_warn = QLabel("⚠  Large file (>4 GB) — trimming may be slow.")
        self._large_file_warn.setObjectName("TextMuted")
        self._large_file_warn.setStyleSheet("color: #D29922; font-size: 12px;")
        self._large_file_warn.setVisible(False)
        layout.addWidget(self._large_file_warn)
        return card

    def _build_player_card(self) -> QFrame:
        """QMediaPlayer + QVideoWidget player card."""
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("PREVIEW"))

        # Video widget
        self._video_widget = QVideoWidget()
        self._video_widget.setObjectName("VideoWidget")
        self._video_widget.setMinimumHeight(240)
        self._video_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self._video_widget)

        # Audio output
        self._audio_output = QAudioOutput()
        self._audio_output.setVolume(1.0)

        # Media player
        self._player = QMediaPlayer()
        self._player.setVideoOutput(self._video_widget)
        self._player.setAudioOutput(self._audio_output)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)

        # Scrubber
        self._scrubber = QSlider(Qt.Orientation.Horizontal)
        self._scrubber.setObjectName("Scrubber")
        self._scrubber.setRange(0, 1000)
        self._scrubber.sliderPressed.connect(self._on_scrub_pressed)
        self._scrubber.sliderReleased.connect(self._on_scrub_released)
        self._scrubber.sliderMoved.connect(self._on_scrub_moved)
        self._scrubbing = False
        layout.addWidget(self._scrubber)

        # Controls row
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        self._play_btn = QPushButton("▶")
        self._play_btn.setObjectName("SecondaryBtn")
        self._play_btn.setFixedSize(42, 42)
        self._play_btn.clicked.connect(self._toggle_play)
        ctrl.addWidget(self._play_btn)

        self._mute_btn = QPushButton("🔊")
        self._mute_btn.setObjectName("SecondaryBtn")
        self._mute_btn.setFixedSize(42, 42)
        self._mute_btn.setCheckable(True)
        self._mute_btn.clicked.connect(self._toggle_mute)
        ctrl.addWidget(self._mute_btn)

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setObjectName("VolumeSlider")
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(100)
        self._vol_slider.setFixedWidth(90)
        self._vol_slider.setToolTip("Volume")
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        ctrl.addWidget(self._vol_slider)

        self._time_label = QLabel("00:00:00 / 00:00:00")
        self._time_label.setObjectName("TextSecondary")
        ctrl.addWidget(self._time_label)
        ctrl.addStretch()

        layout.addLayout(ctrl)

        # Hide video widget initially (shown once a file is loaded)
        self._video_widget.setVisible(False)
        return card

    def _build_time_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("TRIM RANGE  (HH:MM:SS)"))

        row = QHBoxLayout()
        row.setSpacing(16)

        start_col = QVBoxLayout()
        start_col.addWidget(QLabel("Start time"))
        self._start_input = QLineEdit("00:00:00")
        self._start_input.setObjectName("PillInput")
        self._start_input.setFixedWidth(120)
        self._start_input.setPlaceholderText("00:00:00")
        start_col.addWidget(self._start_input)
        row.addLayout(start_col)

        end_col = QVBoxLayout()
        end_col.addWidget(QLabel("End time"))
        self._end_input = QLineEdit("00:00:00")
        self._end_input.setObjectName("PillInput")
        self._end_input.setFixedWidth(120)
        self._end_input.setPlaceholderText("00:00:00")
        end_col.addWidget(self._end_input)
        row.addLayout(end_col)

        if _MULTIMEDIA_AVAILABLE:
            set_start_btn = QPushButton("Set to current")
            set_start_btn.setObjectName("BrowseBtn")
            set_start_btn.clicked.connect(self._set_start_to_current)
            start_col.addWidget(set_start_btn)

            set_end_btn = QPushButton("Set to current")
            set_end_btn.setObjectName("BrowseBtn")
            set_end_btn.clicked.connect(self._set_end_to_current)
            end_col.addWidget(set_end_btn)

        row.addStretch()
        layout.addLayout(row)
        return card

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("OUTPUT FOLDER"))

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

    # ── Source file handling ───────────────────────────────────────────────────

    def _on_source_changed(self, path: str) -> None:
        path = path.strip()
        if not os.path.isfile(path):
            return

        ext = os.path.splitext(path)[1].lower()
        self._is_audio_only = ext in _AUDIO_EXTS
        is_large = os.path.getsize(path) > 4 * 1024 * 1024 * 1024

        if hasattr(self, "_large_file_warn"):
            self._large_file_warn.setVisible(is_large)

        if _MULTIMEDIA_AVAILABLE:
            self._load_media(path)

    def _browse_file(self) -> None:
        start = os.path.dirname(self._file_input.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Media File",
            start,
            "Media (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.mp3 *.wav *.aac *.flac *.ogg *.m4a)",
        )
        if path:
            self._file_input.setText(path)

    def _browse_output(self) -> None:
        start = self._out_input.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if d:
            self._out_input.setText(d)

    def populate_file(self, path: str) -> None:
        """Pre-populate from DnD handler."""
        self._file_input.setText(path)

    # ── Media player ───────────────────────────────────────────────────────────

    def _load_media(self, path: str) -> None:
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(path))
        self._video_widget.setVisible(not self._is_audio_only)

    def _on_media_status_changed(self, status) -> None:
        from PySide6.QtMultimedia import QMediaPlayer as _QMP
        if status == _QMP.MediaStatus.LoadedMedia and not self._is_audio_only:
            # Play then immediately pause to render the first frame (avoids black screen)
            self._player.play()
            QTimer.singleShot(80, self._player.pause)

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._duration_ms = duration_ms
        self._scrubber.setRange(0, max(1, duration_ms))
        end_str = _ms_to_str(duration_ms)
        self._end_input.setText(end_str)
        self._time_label.setText(f"00:00:00 / {end_str}")
        self._pos_timer.start()

    def _on_playback_state_changed(self, state) -> None:
        from PySide6.QtMultimedia import QMediaPlayer as _QMP
        if state == _QMP.PlaybackState.PlayingState:
            self._play_btn.setText("⏸")
        else:
            self._play_btn.setText("▶")

    def _update_position(self) -> None:
        if not self._scrubbing and self._duration_ms:
            pos = self._player.position()
            self._scrubber.setValue(pos)
            total = _ms_to_str(self._duration_ms)
            self._time_label.setText(f"{_ms_to_str(pos)} / {total}")

    def _on_scrub_pressed(self) -> None:
        self._scrubbing = True

    def _on_scrub_released(self) -> None:
        self._scrubbing = False
        self._player.setPosition(self._scrubber.value())

    def _on_scrub_moved(self, value: int) -> None:
        if self._duration_ms:
            total = _ms_to_str(self._duration_ms)
            self._time_label.setText(f"{_ms_to_str(value)} / {total}")

    def _toggle_play(self) -> None:
        from PySide6.QtMultimedia import QMediaPlayer as _QMP
        if self._player.playbackState() == _QMP.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _toggle_mute(self, checked: bool) -> None:
        self._audio_output.setMuted(checked)
        self._mute_btn.setText("🔇" if checked else "🔊")
        self._vol_slider.setEnabled(not checked)

    def _on_volume_changed(self, value: int) -> None:
        self._audio_output.setVolume(value / 100.0)
        # Auto-unmute if user drags the slider up from 0
        if value > 0 and self._mute_btn.isChecked():
            self._mute_btn.setChecked(False)
            self._toggle_mute(False)

    def _set_start_to_current(self) -> None:
        pos = self._player.position() if _MULTIMEDIA_AVAILABLE else 0
        self._start_input.setText(_ms_to_str(pos))

    def _set_end_to_current(self) -> None:
        pos = self._player.position() if _MULTIMEDIA_AVAILABLE else self._duration_ms
        self._end_input.setText(_ms_to_str(pos))

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

        start_str = self._start_input.text().strip() or "0"
        end_str = self._end_input.text().strip()
        if not end_str or end_str == "00:00:00":
            self.status_message.emit("Please set a valid end time.", True)
            return

        out_dir = self._out_input.text().strip() or None

        if _MULTIMEDIA_AVAILABLE and hasattr(self, "_player"):
            self._player.stop()

        self._set_busy(True)
        self.status_message.emit("Trimming…", False)

        _src = src
        _start = start_str
        _end = end_str
        _out_dir = out_dir

        def do_trim():
            return trim_media(_src, _start, _end, _out_dir)

        self._worker = Worker(do_trim)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if busy:
            self._progress_label.setText("Trimming media…")
        self.busy_changed.emit(busy)

    def _on_result(self, success: bool) -> None:
        self._set_busy(False)
        self._worker = None
        src = self._file_input.text()
        base = os.path.splitext(os.path.basename(src))[0]
        ext = os.path.splitext(src)[1]
        out_dir = self._out_input.text().strip() or os.path.dirname(src)
        out_path = os.path.join(out_dir, f"{base}_trimmed{ext}")

        if success:
            self._last_result_path = out_path
            get_history_manager().add_item(
                HistoryItem(
                    task_type="trim",
                    file_name=os.path.basename(out_path),
                    file_path=out_path,
                    status="success",
                )
            )
            self.status_message.emit(f"Done → {os.path.basename(out_path)}", False)
        else:
            get_history_manager().add_item(
                HistoryItem(task_type="trim", file_name=os.path.basename(src), file_path=src, status="error")
            )
            self.status_message.emit("Trim failed. Check start/end times.", True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
