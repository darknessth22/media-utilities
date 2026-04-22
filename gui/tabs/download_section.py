"""Media Download tab — PySide6 UI with sequential download queue."""
from __future__ import annotations

import os
import re
import uuid

from PySide6.QtCore import Qt, Signal, QUrl, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
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
    _MULTIMEDIA_AVAILABLE = True
except ImportError:
    _MULTIMEDIA_AVAILABLE = False

from core.downloader import download_media, get_available_formats, get_platform, get_preview_stream_url
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker

_AUDIO_FORMATS = ["MP3", "FLAC", "OGG", "OPUS", "M4A"]

_GENERIC_ERROR_MESSAGES: dict[str, str] = {
    "timeout": "Connection timed out. Check your network and try again.",
    "auth_required": "This video requires login — not supported for generic URLs.",
    "unsupported": "This site is not supported. Try a direct video file link instead.",
    "no_video": "No downloadable video found at this URL.",
    "download_failed": "Download failed. Check the URL or your network.",
    "cancelled": "Download cancelled.",
}


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


def _ms_to_str(ms: int) -> str:
    total_s = max(0, ms // 1000)
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class _JobRow(QFrame):
    """Single row in the download queue — name, progress, status, cancel."""

    cancel_requested = Signal(str)  # job_id

    def __init__(self, job_id: str, display_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("JobRow")
        self._job_id = job_id

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)

        self._dot = QLabel("●")
        self._dot.setFixedWidth(14)
        self._dot.setStyleSheet("color: #8B949E; font-size: 10px;")
        top.addWidget(self._dot)

        self._name_lbl = QLabel(display_name)
        self._name_lbl.setObjectName("TextSecondary")
        self._name_lbl.setStyleSheet("font-size: 12px;")
        top.addWidget(self._name_lbl, 1)

        self._status_lbl = QLabel("Pending")
        self._status_lbl.setObjectName("TextMuted")
        self._status_lbl.setStyleSheet("font-size: 11px; margin-right: 4px;")
        top.addWidget(self._status_lbl)

        self._cancel_btn = QPushButton("✕")
        self._cancel_btn.setObjectName("ChipBtn")
        self._cancel_btn.setFixedSize(22, 22)
        self._cancel_btn.setStyleSheet("font-size: 10px; padding: 0;")
        self._cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self._job_id))
        top.addWidget(self._cancel_btn)
        outer.addLayout(top)

        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("TaskProgressBar")
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setVisible(False)
        outer.addWidget(self._progress_bar)

        self._info_lbl = QLabel()
        self._info_lbl.setObjectName("TextMuted")
        self._info_lbl.setStyleSheet("font-size: 11px;")
        self._info_lbl.setVisible(False)
        outer.addWidget(self._info_lbl)

    def update_name(self, name: str) -> None:
        self._name_lbl.setText(name)

    def set_downloading(self) -> None:
        self._dot.setStyleSheet("color: #3B82F6; font-size: 10px;")
        self._status_lbl.setText("Downloading")
        self._progress_bar.setVisible(True)
        self._info_lbl.setVisible(True)

    def update_progress(self, percent: int, speed: str, eta: int) -> None:
        if percent != -1:
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(percent)
        else:
            self._progress_bar.setRange(0, 0)
        parts = []
        if speed:
            parts.append(speed)
        if eta != -1:
            m, s = divmod(eta, 60) if eta >= 60 else (0, eta)
            parts.append(f"~{m}:{s:02d} left" if m else f"~{s}s left")
        if parts:
            self._info_lbl.setText("  ".join(parts))

    def set_done(self) -> None:
        self._dot.setStyleSheet("color: #3FB950; font-size: 10px;")
        self._status_lbl.setText("Done ✓")
        self._progress_bar.setVisible(False)
        self._info_lbl.setVisible(False)
        self._cancel_btn.setEnabled(False)

    def set_error(self, msg: str = "") -> None:
        self._dot.setStyleSheet("color: #F85149; font-size: 10px;")
        self._status_lbl.setText("Error")
        self._progress_bar.setVisible(False)
        if msg:
            self._info_lbl.setText(msg[:80])
            self._info_lbl.setVisible(True)
        self._cancel_btn.setEnabled(False)

    def set_cancelled(self) -> None:
        self._dot.setStyleSheet("color: #8B949E; font-size: 10px;")
        self._status_lbl.setText("Cancelled")
        self._progress_bar.setVisible(False)
        self._info_lbl.setVisible(False)
        self._cancel_btn.setEnabled(False)


class DownloadSection(QScrollArea):
    """Media Download tab — URL-based downloader with sequential queue."""

    status_message = Signal(str, bool)   # (text, is_error)
    busy_changed   = Signal(bool)        # kept for API compat
    queue_changed  = Signal(int)         # count of pending + downloading jobs

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_result_path: str | None = None
        self._formats: list[dict] = []
        self._selected_format_id: str | None = None
        self._duration_ms: int = 0
        self._updating = False

        # Queue state
        self._queue: list[dict] = []
        self._job_rows: dict[str, _JobRow] = {}
        self._active_job: dict | None = None

        if _MULTIMEDIA_AVAILABLE:
            self._player = QMediaPlayer()
            self._audio_output = QAudioOutput()
            self._player.setAudioOutput(self._audio_output)
            self._pos_timer = QTimer(self)
            self._pos_timer.setInterval(200)
            self._pos_timer.timeout.connect(self._on_player_pos_changed)

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_url_card())
        layout.addWidget(self._build_type_card())
        layout.addWidget(self._build_quality_card())
        layout.addWidget(self._build_trim_card())
        if _MULTIMEDIA_AVAILABLE:
            layout.addWidget(self._build_preview_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_queue_card())

        self.setWidget(content)

    # ── Card builders ──────────────────────────────────────────────────────────

    def _build_url_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("SOURCE URL"))

        row = QHBoxLayout()
        self._url_input = QLineEdit()
        self._url_input.setObjectName("PillInput")
        self._url_input.setPlaceholderText(
            "YouTube, Facebook, Instagram, TikTok, Twitter/X, Spotify…"
        )
        self._url_input.textChanged.connect(self._on_url_changed)
        row.addWidget(self._url_input)
        layout.addLayout(row)

        self._platform_label = QLabel()
        self._platform_label.setObjectName("TextMuted")
        self._platform_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._platform_label)
        return card

    def _build_type_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("MEDIA TYPE"))

        row = QHBoxLayout()
        row.setSpacing(16)
        self._type_group = QButtonGroup(self)
        self._video_radio = QRadioButton("Video")
        self._audio_radio = QRadioButton("Audio only")
        self._video_radio.setChecked(True)
        self._type_group.addButton(self._video_radio, 0)
        self._type_group.addButton(self._audio_radio, 1)
        self._video_radio.toggled.connect(self._on_type_toggled)
        row.addWidget(self._video_radio)
        row.addWidget(self._audio_radio)
        row.addStretch()
        layout.addLayout(row)

        self._audio_fmt_container = QWidget()
        af_row = QHBoxLayout(self._audio_fmt_container)
        af_row.setContentsMargins(0, 0, 0, 0)
        af_row.setSpacing(8)
        self._audio_fmt_btns: dict[str, QPushButton] = {}
        for fmt in _AUDIO_FORMATS:
            btn = QPushButton(fmt)
            btn.setObjectName("ChipBtn")
            btn.setCheckable(True)
            btn.setFixedWidth(64)
            btn.clicked.connect(lambda _c, f=fmt: self._select_audio_fmt(f))
            self._audio_fmt_btns[fmt] = btn
            af_row.addWidget(btn)
        af_row.addStretch()
        layout.addWidget(self._audio_fmt_container)
        self._audio_fmt_container.setVisible(False)
        self._select_audio_fmt("MP3")
        return card

    def _build_quality_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("VIDEO QUALITY"))

        row = QHBoxLayout()
        self._quality_combo = QComboBox()
        self._quality_combo.setObjectName("QualityCombo")
        self._quality_combo.addItem("Best available (default)")
        self._quality_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(self._quality_combo)

        self._check_fmt_btn = QPushButton("Check Formats")
        self._check_fmt_btn.setObjectName("BrowseBtn")
        self._check_fmt_btn.setFixedWidth(120)
        self._check_fmt_btn.clicked.connect(self._check_formats)
        row.addWidget(self._check_fmt_btn)
        layout.addLayout(row)

        self._quality_hint = QLabel(
            'Click "Check Formats" to see available resolutions for the URL.'
        )
        self._quality_hint.setObjectName("TextMuted")
        self._quality_hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._quality_hint)
        return card

    def _build_trim_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.addWidget(_section_header("TIME RANGE  (optional — HH:MM:SS or MM:SS)"))
        header_row.addStretch()

        self._load_preview_btn = QPushButton("Load Preview")
        self._load_preview_btn.setObjectName("BrowseBtn")
        self._load_preview_btn.setFixedWidth(110)
        self._load_preview_btn.setVisible(_MULTIMEDIA_AVAILABLE)
        self._load_preview_btn.clicked.connect(
            lambda: self._load_preview(self._url_input.text().strip())
        )
        header_row.addWidget(self._load_preview_btn)
        layout.addLayout(header_row)

        row = QHBoxLayout()
        row.setSpacing(16)

        start_col = QVBoxLayout()
        start_col.addWidget(QLabel("Start"))
        self._start_input = QLineEdit()
        self._start_input.setObjectName("PillInput")
        self._start_input.setFixedWidth(110)
        self._start_input.setPlaceholderText("0:00")
        self._start_input.textChanged.connect(self._on_time_input_changed)
        start_col.addWidget(self._start_input)
        row.addLayout(start_col)

        end_col = QVBoxLayout()
        end_col.addWidget(QLabel("End"))
        self._end_input = QLineEdit()
        self._end_input.setObjectName("PillInput")
        self._end_input.setFixedWidth(110)
        self._end_input.setPlaceholderText("end of video")
        self._end_input.textChanged.connect(self._on_time_input_changed)
        end_col.addWidget(self._end_input)
        row.addLayout(end_col)

        row.addStretch()
        layout.addLayout(row)
        return card

    def _build_preview_card(self) -> QFrame:
        self._preview_card = _card()
        self._preview_card.setVisible(False)
        layout = QVBoxLayout(self._preview_card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        self._video_widget = QVideoWidget()
        self._video_widget.setMinimumHeight(200)
        self._video_widget.setStyleSheet("background: #000; border-radius: 4px;")
        self._player.setVideoOutput(self._video_widget)
        layout.addWidget(self._video_widget)

        ctrl_row = QHBoxLayout()
        self._play_btn = QPushButton("Play")
        self._play_btn.setObjectName("ChipBtn")
        self._play_btn.setFixedWidth(70)
        self._play_btn.clicked.connect(self._toggle_playback)
        ctrl_row.addWidget(self._play_btn)

        self._reload_preview_btn = QPushButton("Reload")
        self._reload_preview_btn.setObjectName("ChipBtn")
        self._reload_preview_btn.setFixedWidth(70)
        self._reload_preview_btn.setToolTip(
            "CDN preview links expire — click to re-fetch a fresh URL."
        )
        self._reload_preview_btn.clicked.connect(
            lambda: self._load_preview(self._url_input.text().strip())
        )
        ctrl_row.addWidget(self._reload_preview_btn)

        self._scrubber = QSlider(Qt.Orientation.Horizontal)
        self._scrubber.setObjectName("PreviewSlider")
        self._scrubber.sliderMoved.connect(self._on_scrubber_moved)
        ctrl_row.addWidget(self._scrubber)

        self._time_label = QLabel("00:00:00 / 00:00:00")
        self._time_label.setObjectName("TextMuted")
        ctrl_row.addWidget(self._time_label)
        layout.addLayout(ctrl_row)

        range_layout = QVBoxLayout()
        range_layout.setSpacing(4)

        lbl_s = QLabel("Start Marker")
        lbl_s.setObjectName("TextMuted")
        lbl_s.setStyleSheet("font-size: 10px;")
        range_layout.addWidget(lbl_s)
        self._start_slider = QSlider(Qt.Orientation.Horizontal)
        self._start_slider.setObjectName("StartSlider")
        self._start_slider.sliderMoved.connect(self._on_start_slider_moved)
        range_layout.addWidget(self._start_slider)

        lbl_e = QLabel("End Marker")
        lbl_e.setObjectName("TextMuted")
        lbl_e.setStyleSheet("font-size: 10px;")
        range_layout.addWidget(lbl_e)
        self._end_slider = QSlider(Qt.Orientation.Horizontal)
        self._end_slider.setObjectName("EndSlider")
        self._end_slider.sliderMoved.connect(self._on_end_slider_moved)
        range_layout.addWidget(self._end_slider)

        layout.addLayout(range_layout)

        expiry_note = QLabel(
            "Preview links from Facebook / Instagram / LinkedIn expire quickly"
            " — use Reload if playback stalls."
        )
        expiry_note.setObjectName("TextMuted")
        expiry_note.setWordWrap(True)
        expiry_note.setStyleSheet("font-size: 11px;")
        layout.addWidget(expiry_note)

        self._preview_status = QLabel()
        self._preview_status.setObjectName("TextSecondary")
        self._preview_status.setWordWrap(True)
        self._preview_status.setVisible(False)
        layout.addWidget(self._preview_status)

        return self._preview_card

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("OUTPUT FOLDER"))

        row = QHBoxLayout()
        self._out_input = QLineEdit()
        self._out_input.setObjectName("PillInput")
        self._out_input.setPlaceholderText("Current working directory")
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

    def _build_queue_card(self) -> QFrame:
        self._queue_card = _card()
        self._queue_card.setVisible(False)
        outer = QVBoxLayout(self._queue_card)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        header_row = QHBoxLayout()
        header_lbl = _section_header("DOWNLOAD QUEUE")
        header_lbl.setStyleSheet(
            "font-size: 11px; font-weight: bold; letter-spacing: 1px;"
        )
        header_row.addWidget(header_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        header_row.addStretch()
        clear_btn = QPushButton("Clear done")
        clear_btn.setObjectName("BrowseBtn")
        clear_btn.setFixedHeight(26)
        clear_btn.setFixedWidth(80)
        clear_btn.clicked.connect(self._clear_done_jobs)
        header_row.addWidget(clear_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addLayout(header_row)

        self._queue_layout = QVBoxLayout()
        self._queue_layout.setSpacing(4)
        outer.addLayout(self._queue_layout)

        return self._queue_card

    # ── Control handlers ───────────────────────────────────────────────────────

    def _on_url_changed(self, url: str) -> None:
        url = url.strip()
        if url:
            platform = get_platform(url)
            platform_names = {
                "youtube": "YouTube", "facebook": "Facebook",
                "instagram": "Instagram", "tiktok": "TikTok",
                "twitter": "Twitter / X", "linkedin": "LinkedIn",
                "spotify": "Spotify", "generic": "Generic URL",
            }
            label = platform_names.get(platform, platform.capitalize())
            if platform == "generic":
                self._platform_label.setText("Detected: Generic URL — download will be attempted")
            else:
                self._platform_label.setText(f"Detected: {label}")
            if platform == "spotify":
                self._audio_radio.setChecked(True)
        else:
            self._platform_label.setText("")

        if _MULTIMEDIA_AVAILABLE:
            self._player.stop()
            self._preview_card.setVisible(False)
            self._duration_ms = 0
            self._start_input.clear()
            self._end_input.clear()

    def _on_type_toggled(self, is_video: bool) -> None:
        self._audio_fmt_container.setVisible(not is_video)
        self._quality_combo.setEnabled(is_video)
        self._check_fmt_btn.setEnabled(is_video)
        if _MULTIMEDIA_AVAILABLE:
            self._load_preview_btn.setVisible(is_video)
            if not is_video:
                self._player.stop()
                self._preview_card.setVisible(False)

    def _select_audio_fmt(self, fmt: str) -> None:
        self._selected_audio_fmt = fmt
        for name, btn in self._audio_fmt_btns.items():
            active = name == fmt
            btn.setChecked(active)
            btn.setProperty("selected", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _browse_output(self) -> None:
        start = self._out_input.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if d:
            self._out_input.setText(d)

    # ── Preview logic ──────────────────────────────────────────────────────────

    def _load_preview(self, url: str) -> None:
        if not url:
            return
        self._load_preview_btn.setEnabled(False)
        self._load_preview_btn.setText("Loading…")
        self.status_message.emit("Fetching preview stream…", False)
        worker = Worker(lambda: get_preview_stream_url(url))
        worker.signals.result.connect(self._on_preview_loaded)
        worker.signals.error.connect(self._on_preview_error)
        worker.start()
        self._preview_worker = worker

    def _on_preview_loaded(self, result: dict) -> None:
        self._load_preview_btn.setEnabled(True)
        self._load_preview_btn.setText("Load Preview")
        if "error" in result:
            self.status_message.emit(f"Preview unavailable: {result['error']}", True)
            self._preview_card.setVisible(False)
            return
        self._duration_ms = result["duration_ms"]
        self._player.setSource(QUrl(result["stream_url"]))
        self._updating = True
        self._scrubber.setRange(0, self._duration_ms)
        self._start_slider.setRange(0, self._duration_ms)
        self._end_slider.setRange(0, self._duration_ms)
        self._start_slider.setValue(0)
        self._end_slider.setValue(self._duration_ms)
        self._updating = False
        self._preview_card.setVisible(True)
        self._preview_status.setVisible(False)
        self._time_label.setText(f"00:00:00 / {_ms_to_str(self._duration_ms)}")
        self.status_message.emit(f"Preview loaded: {result['title']}", False)

    def _on_preview_error(self, err_tuple: tuple) -> None:
        self._load_preview_btn.setEnabled(True)
        self._load_preview_btn.setText("Load Preview")
        _, msg, _ = err_tuple
        self.status_message.emit(f"Preview error: {msg}", True)

    def _on_duration_changed(self, duration: int) -> None:
        if duration <= 0:
            return
        self._duration_ms = duration
        self._updating = True
        self._scrubber.setRange(0, duration)
        self._start_slider.setRange(0, duration)
        self._end_slider.setRange(0, duration)
        if self._end_slider.value() >= duration or self._end_slider.value() == 0:
            self._end_slider.setValue(duration)
        self._time_label.setText(
            f"{_ms_to_str(self._player.position())} / {_ms_to_str(duration)}"
        )
        self._updating = False

    def _toggle_playback(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self._play_btn.setText("Play")
            self._pos_timer.stop()
        else:
            self._player.play()
            self._play_btn.setText("Pause")
            self._pos_timer.start()

    def _on_player_pos_changed(self) -> None:
        if not self._updating:
            pos = self._player.position()
            self._updating = True
            self._scrubber.setValue(pos)
            self._time_label.setText(f"{_ms_to_str(pos)} / {_ms_to_str(self._duration_ms)}")
            self._updating = False

    def _on_scrubber_moved(self, value: int) -> None:
        self._updating = True
        self._player.setPosition(value)
        self._time_label.setText(f"{_ms_to_str(value)} / {_ms_to_str(self._duration_ms)}")
        self._updating = False

    def _on_start_slider_moved(self, value: int) -> None:
        if not self._updating:
            self._updating = True
            self._start_input.setText(_ms_to_str(value))
            self._updating = False

    def _on_end_slider_moved(self, value: int) -> None:
        if not self._updating:
            self._updating = True
            self._end_input.setText(_ms_to_str(value))
            self._updating = False

    def _on_time_input_changed(self) -> None:
        if self._updating or not _MULTIMEDIA_AVAILABLE or self._duration_ms == 0:
            return

        def _str_to_ms(text: str) -> int | None:
            try:
                parts = list(map(int, text.split(":")))
                if len(parts) == 1:
                    return parts[0] * 1000
                if len(parts) == 2:
                    return (parts[0] * 60 + parts[1]) * 1000
                if len(parts) == 3:
                    return (parts[0] * 3600 + parts[1] * 60 + parts[2]) * 1000
            except Exception:
                pass
            return None

        self._updating = True
        s_ms = _str_to_ms(self._start_input.text())
        if s_ms is not None:
            self._start_slider.setValue(min(s_ms, self._duration_ms))
        e_ms = _str_to_ms(self._end_input.text())
        if e_ms is not None:
            self._end_slider.setValue(min(e_ms, self._duration_ms))
        self._updating = False

    # ── "Check Formats" ───────────────────────────────────────────────────────

    def _check_formats(self) -> None:
        url = self._url_input.text().strip()
        if not url:
            self.status_message.emit("Enter a URL first.", True)
            return
        self._check_fmt_btn.setEnabled(False)
        self._check_fmt_btn.setText("Checking…")
        self.status_message.emit("Fetching available formats…", False)
        _url = url
        worker = Worker(lambda: get_available_formats(_url))
        worker.signals.result.connect(self._on_formats_fetched)
        worker.signals.error.connect(self._on_formats_error)
        worker.start()
        self._fmt_worker = worker

    def _on_formats_fetched(self, formats: list) -> None:
        self._check_fmt_btn.setEnabled(True)
        self._check_fmt_btn.setText("Check Formats")
        self._formats = formats
        self._quality_combo.clear()
        self._quality_combo.addItem("Best available (default)", None)
        for fmt in formats:
            self._quality_combo.addItem(fmt["display"], fmt["format_id"])
        if formats:
            self.status_message.emit(f"{len(formats)} format(s) loaded.", False)
        else:
            self.status_message.emit("No formats found — URL may be unsupported.", True)

    def _on_formats_error(self, err_tuple: tuple) -> None:
        self._check_fmt_btn.setEnabled(True)
        self._check_fmt_btn.setText("Check Formats")
        _, msg, _ = err_tuple
        self.status_message.emit(f"Format check failed: {msg}", True)

    # ── Queue management ───────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        """Add current form state as a new download job to the queue."""
        url = self._url_input.text().strip()
        if not url:
            self.status_message.emit("Please enter a URL.", True)
            return

        is_audio = self._audio_radio.isChecked()
        platform = get_platform(url)
        audio_fmt = getattr(self, "_selected_audio_fmt", "mp3").lower()
        out_dir = self._out_input.text().strip() or None
        codec = self._settings.default_codec or "original"
        codec_map = {
            "original": "original", "h264": "libx264",
            "hevc": "libx265", "vp9": "libvpx-vp9",
        }
        video_codec = codec_map.get(codec, "original")

        quality: str | None = None
        if not is_audio:
            idx = self._quality_combo.currentIndex()
            if idx > 0:
                quality = self._quality_combo.itemData(idx)

        start_time = self._start_input.text().strip() or None
        end_time = self._end_input.text().strip() or None

        def _str_to_ms(text: str) -> int | None:
            try:
                parts = list(map(int, text.split(":")))
                if len(parts) == 1:
                    return parts[0] * 1000
                if len(parts) == 2:
                    return (parts[0] * 60 + parts[1]) * 1000
                if len(parts) == 3:
                    return (parts[0] * 3600 + parts[1] * 60 + parts[2]) * 1000
            except Exception:
                pass
            return None

        if start_time and end_time:
            s_ms = _str_to_ms(start_time)
            e_ms = _str_to_ms(end_time)
            if s_ms is not None and e_ms is not None and s_ms >= e_ms:
                self.status_message.emit("Start time must be less than end time.", True)
                return

        if start_time and not end_time:
            self.status_message.emit("Please set an end time when specifying a start time.", True)
            return

        job_id = uuid.uuid4().hex[:8]
        display_name = url if len(url) <= 60 else url[:57] + "…"
        job = {
            "job_id": job_id,
            "url": url,
            "display_name": display_name,
            "platform": platform,
            "media_type": "audio" if is_audio else "video",
            "quality": quality,
            "audio_fmt": audio_fmt,
            "start_time": start_time,
            "end_time": end_time,
            "out_dir": out_dir,
            "video_codec": video_codec,
            "status": "pending",
        }

        self._queue.append(job)
        self._add_job_row(job)
        self._queue_card.setVisible(True)
        self._clear_form()

        self._emit_queue_count()

        if self._worker is None or not self._worker.isRunning():
            self._run_next()

    def _add_job_row(self, job: dict) -> None:
        row = _JobRow(job["job_id"], job["display_name"])
        row.cancel_requested.connect(self._cancel_job)
        self._job_rows[job["job_id"]] = row
        self._queue_layout.addWidget(row)

    def _clear_form(self) -> None:
        self._url_input.clear()
        self._platform_label.setText("")
        self._quality_combo.clear()
        self._quality_combo.addItem("Best available (default)")
        self._start_input.clear()
        self._end_input.clear()
        self._video_radio.setChecked(True)

    def _emit_queue_count(self) -> None:
        count = sum(1 for j in self._queue if j["status"] in ("pending", "downloading"))
        self.queue_changed.emit(count)
        self.busy_changed.emit(count > 0)

    def _run_next(self) -> None:
        pending = next((j for j in self._queue if j["status"] == "pending"), None)
        if pending is None:
            return

        pending["status"] = "downloading"
        self._active_job = pending
        row = self._job_rows.get(pending["job_id"])
        if row:
            row.set_downloading()

        job_id = pending["job_id"]
        _url = pending["url"]
        _platform = pending["platform"]
        _media_type = pending["media_type"]
        _quality = pending["quality"]
        _audio_fmt = pending["audio_fmt"]
        _start = pending["start_time"]
        _end = pending["end_time"]
        _out_dir = pending["out_dir"]
        _video_codec = pending["video_codec"]

        def do_download():
            def cancel_fn():
                w = getattr(self, "_worker", None)
                return w is None or w.is_cancelled

            def p_cb(p, e, s):
                if self._worker:
                    self._worker.signals.progress.emit(p, e, s)

            return download_media(
                url=_url,
                platform=_platform,
                media_type=_media_type,
                quality=_quality,
                start_time=_start,
                end_time=_end,
                audio_format=_audio_fmt,
                output_dir=_out_dir,
                video_codec=_video_codec,
                cancel_check=cancel_fn,
                status_cb=lambda msg: (
                    self._worker.signals.intercept_status.emit(msg) if self._worker else None
                ),
                progress_cb=p_cb,
            )

        self._worker = Worker(do_download)
        self._worker.signals.result.connect(lambda r: self._on_job_result(job_id, r))
        self._worker.signals.error.connect(lambda e: self._on_job_error(job_id, e))
        self._worker.signals.progress.connect(
            lambda p, e, s: self._on_job_progress(job_id, p, e, s)
        )
        self._worker.signals.intercept_status.connect(
            lambda m: self._on_intercept_status(job_id, m)
        )
        # finished fires even when cancelled (result/error do not)
        self._worker.signals.finished.connect(lambda: self._on_worker_finished(job_id))
        self._worker.start()
        self.status_message.emit(f"Downloading: {pending['display_name']}", False)

    def _on_intercept_status(self, job_id: str, msg: str) -> None:
        self.status_message.emit(msg, False)
        # Parse yt-dlp destination messages to update the job display name
        for pattern in (
            r'\[download\] Destination: (.+)',
            r'\[Merger\] Merging formats into "(.+)"',
            r'\[download\] (.+) has already been downloaded',
        ):
            m = re.search(pattern, msg)
            if m:
                title = os.path.splitext(os.path.basename(m.group(1).strip()))[0]
                if title:
                    display = title if len(title) <= 60 else title[:57] + "…"
                    job = next((j for j in self._queue if j["job_id"] == job_id), None)
                    if job:
                        job["display_name"] = display
                    row = self._job_rows.get(job_id)
                    if row:
                        row.update_name(display)
                break

    def _on_job_progress(self, job_id: str, percent: int, eta: int, speed: str) -> None:
        row = self._job_rows.get(job_id)
        if row:
            row.update_progress(percent, speed, eta)

    def _on_job_result(self, job_id: str, result: dict) -> None:
        job = next((j for j in self._queue if j["job_id"] == job_id), None)
        self._worker = None
        self._active_job = None

        row = self._job_rows.get(job_id)

        if result.get("success"):
            if job:
                job["status"] = "done"
            fp = result.get("file_path") or ""
            if fp:
                title = os.path.splitext(os.path.basename(fp))[0]
                display = title if len(title) <= 60 else title[:57] + "…"
                if job:
                    job["display_name"] = display
                if row:
                    row.update_name(display)
            if row:
                row.set_done()
            self._last_result_path = fp
            fn = os.path.basename(fp) if fp else "downloaded file"
            size = result.get("file_size")
            size_str = f"  ({size / (1024*1024):.1f} MB)" if size else ""
            _source = (
                "browser_intercept"
                if result.get("error_code") == "browser_intercept_ok"
                else "direct"
            )
            get_history_manager().add_item(
                HistoryItem(
                    task_type="download", file_name=fn, file_path=fp,
                    status="success", source=_source,
                )
            )
            msg = f"Download complete → {fn}{size_str}"
            if result.get("error_code") == "http_fallback_ok":
                msg += "\nDownloaded via direct URL."
            elif result.get("error_code") == "html_scrape_ok":
                msg += "\nDownloaded via embedded video."
            elif result.get("error_code") == "browser_intercept_ok":
                msg += "\nDownloaded via browser stream intercept."
            self.status_message.emit(msg, False)
        else:
            if job:
                job["status"] = "error"
            code = result.get("error_code")
            err_text = _GENERIC_ERROR_MESSAGES.get(code) or "Download failed."
            if job:
                get_history_manager().add_item(
                    HistoryItem(
                        task_type="download", file_name=job["url"],
                        file_path=job["url"], status="error",
                    )
                )
            if row:
                row.set_error(err_text)
            self.status_message.emit(err_text, True)

        QTimer.singleShot(2000, lambda: self._remove_job(job_id))

    def _on_job_error(self, job_id: str, err_tuple: tuple) -> None:
        job = next((j for j in self._queue if j["job_id"] == job_id), None)
        self._worker = None
        self._active_job = None

        row = self._job_rows.get(job_id)
        _, msg, _ = err_tuple
        if job:
            job["status"] = "error"
        if row:
            row.set_error(msg[:80])
        self.status_message.emit(f"Error: {msg}", True)
        QTimer.singleShot(2000, lambda: self._remove_job(job_id))

    def _on_worker_finished(self, job_id: str) -> None:
        """Called after every worker run — handles the cancelled case where result/error don't fire."""
        job = next((j for j in self._queue if j["job_id"] == job_id), None)
        if job and job["status"] == "cancelled":
            self._worker = None
            self._active_job = None
            self._do_cleanup_partial_files(job.get("out_dir"))
            QTimer.singleShot(1000, lambda: self._remove_job(job_id))
            self._run_next()

    def _cancel_job(self, job_id: str) -> None:
        job = next((j for j in self._queue if j["job_id"] == job_id), None)
        if job is None:
            return

        row = self._job_rows.get(job_id)
        if job["status"] == "downloading" and self._worker:
            job["status"] = "cancelled"
            if row:
                row.set_cancelled()
            self._worker.cancel()
            # _on_worker_finished handles cleanup when worker stops
        elif job["status"] == "pending":
            job["status"] = "cancelled"
            if row:
                row.set_cancelled()
            QTimer.singleShot(500, lambda: self._remove_job(job_id))

        self._emit_queue_count()

    def _remove_job(self, job_id: str) -> None:
        self._queue = [j for j in self._queue if j["job_id"] != job_id]
        row = self._job_rows.pop(job_id, None)
        if row:
            self._queue_layout.removeWidget(row)
            row.deleteLater()
        if not self._queue:
            self._queue_card.setVisible(False)
        self._emit_queue_count()
        # Start next if queue has pending and nothing running
        if self._worker is None or not self._worker.isRunning():
            self._run_next()

    def _clear_done_jobs(self) -> None:
        done_ids = [
            j["job_id"] for j in self._queue
            if j["status"] in ("done", "error", "cancelled")
        ]
        for job_id in done_ids:
            self._remove_job(job_id)

    def _do_cleanup_partial_files(self, out_dir: str | None) -> None:
        out = out_dir or "."
        try:
            if os.path.isdir(out):
                for f in os.scandir(out):
                    if f.name.endswith(".part") and f.is_file():
                        try:
                            os.remove(f.path)
                        except OSError:
                            pass
        except OSError:
            pass
