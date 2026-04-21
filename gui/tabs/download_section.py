"""Media Download tab — PySide6 UI bound to core.downloader.download_media.

T012: Reimplement Download tab UI layout and bind to core downloader via
      worker thread.

Supports:
  - YouTube, Facebook, Instagram, TikTok, Twitter/X, Spotify, and generic URLs
  - Video (quality chip selection via "Check Formats") or audio-only download
  - Audio format selection (MP3 / FLAC / OGG / OPUS / M4A)
  - Optional time-range trimming (start / end timestamps)
  - Output folder override
  - Cancellable background worker with progress feedback
"""
from __future__ import annotations

import os

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
    """Convert milliseconds to HH:MM:SS string (US2)."""
    total_s = max(0, ms // 1000)
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class DownloadSection(QScrollArea):
    """Media Download tab — URL-based downloader."""

    status_message = Signal(str, bool)   # (text, is_error)
    busy_changed   = Signal(bool)        # True=task started, False=task ended

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._download_token: int = 0
        self._active_output_dir: str | None = None
        self._formats: list[dict] = []          # from get_available_formats()
        self._selected_format_id: str | None = None
        self._last_result_path: str | None = None
        self._duration_ms: int = 0
        self._updating = False                  # guard for slider/input sync

        # Initialize multimedia (US2)
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
        layout.addWidget(self._build_progress_card())

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

        # Audio format chips (hidden when video is selected)
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
        self._load_preview_btn.clicked.connect(lambda: self._load_preview(self._url_input.text().strip()))
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

        # Controls row
        ctrl_row = QHBoxLayout()
        self._play_btn = QPushButton("Play")
        self._play_btn.setObjectName("ChipBtn")
        self._play_btn.setFixedWidth(70)
        self._play_btn.clicked.connect(self._toggle_playback)
        ctrl_row.addWidget(self._play_btn)

        self._scrubber = QSlider(Qt.Orientation.Horizontal)
        self._scrubber.setObjectName("PreviewSlider")
        self._scrubber.sliderMoved.connect(self._on_scrubber_moved)
        ctrl_row.addWidget(self._scrubber)

        self._time_label = QLabel("00:00:00 / 00:00:00")
        self._time_label.setObjectName("TextMuted")
        ctrl_row.addWidget(self._time_label)
        layout.addLayout(ctrl_row)

        # Range sliders (US2 markers)
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

        # Fallback/Status message
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

        # Speed and ETA row
        info_row = QHBoxLayout()
        self._speed_label = QLabel()
        self._speed_label.setObjectName("TextSecondary")
        self._speed_label.setVisible(False)
        info_row.addWidget(self._speed_label)

        info_row.addStretch()

        self._eta_label = QLabel()
        self._eta_label.setObjectName("TextSecondary")
        self._eta_label.setVisible(False)
        info_row.addWidget(self._eta_label)
        layout.addLayout(info_row)

        self._progress_label = QLabel()
        self._progress_label.setObjectName("TextSecondary")
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)
        return card

    # ── Control handlers ───────────────────────────────────────────────────────

    def _on_url_changed(self, url: str) -> None:
        url = url.strip()
        if url:
            platform = get_platform(url)
            platform_names = {
                "youtube": "YouTube", "facebook": "Facebook",
                "instagram": "Instagram", "tiktok": "TikTok",
                "twitter": "Twitter / X", "spotify": "Spotify",
                "generic": "Generic URL",
            }
            label = platform_names.get(platform, platform.capitalize())
            if platform == "generic":
                self._platform_label.setText("Detected: Generic URL — download will be attempted")
            else:
                self._platform_label.setText(f"Detected: {label}")
            # Spotify is audio-only
            if platform == "spotify":
                self._audio_radio.setChecked(True)
        else:
            self._platform_label.setText("")
        
        # US2: Reset preview on URL change
        if _MULTIMEDIA_AVAILABLE:
            self._player.stop()
            self._preview_card.setVisible(False)
            self._duration_ms = 0
            self._start_input.clear()
            self._end_input.clear()

    def _on_type_toggled(self, is_video: bool) -> None:
        self._audio_fmt_container.setVisible(not is_video)
        # Quality selection only makes sense for video
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

    # ── Preview logic (US2) ───────────────────────────────────────────────────

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
        
        # Reset markers
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
        """Update durations from player if it differs from extractor (US2)."""
        if duration <= 0:
            return
        self._duration_ms = duration
        self._updating = True
        self._scrubber.setRange(0, duration)
        self._start_slider.setRange(0, duration)
        self._end_slider.setRange(0, duration)
        # Only update end slider if it was at the previous "end" or unset
        if self._end_slider.value() >= duration or self._end_slider.value() == 0:
            self._end_slider.setValue(duration)
        self._time_label.setText(f"{_ms_to_str(self._player.position())} / {_ms_to_str(duration)}")
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
        """Sync text inputs back to sliders (T015)."""
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

        def fetch():
            return get_available_formats(_url)

        worker = Worker(fetch)
        worker.signals.result.connect(self._on_formats_fetched)
        worker.signals.error.connect(self._on_formats_error)
        worker.start()
        self._fmt_worker = worker   # keep alive

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

    # ── Primary action (Download) ─────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._download_token += 1
            _w = self._worker
            _out = self._active_output_dir
            def _on_cancel_done(_w=_w, _out=_out):
                if self._worker is _w:
                    self._worker = None
                self._do_cleanup_partial_files(_out)
            _w.signals.finished.connect(_on_cancel_done)
            self._reset_ui()
            self._active_output_dir = None
            self.status_message.emit("Download cancelled.", False)
            return

        url = self._url_input.text().strip()
        if not url:
            self.status_message.emit("Please enter a URL.", True)
            return

        is_audio = self._audio_radio.isChecked()
        platform = get_platform(url)
        audio_fmt = getattr(self, "_selected_audio_fmt", "mp3").lower()
        out_dir = self._out_input.text().strip() or None
        codec = self._settings.default_codec or "original"

        # Map settings codec to yt-dlp / ffmpeg codec strings
        codec_map = {"original": "original", "h264": "libx264", "hevc": "libx265", "vp9": "libvpx-vp9"}
        video_codec = codec_map.get(codec, "original")

        # Quality
        quality: str | None = None
        if not is_audio:
            idx = self._quality_combo.currentIndex()
            if idx > 0:
                quality = self._quality_combo.itemData(idx)

        start_time = self._start_input.text().strip() or None
        end_time = self._end_input.text().strip() or None
        
        # US2: Validation
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

        self._download_token += 1
        token = self._download_token
        self._active_output_dir = out_dir
        self._set_busy(True)
        self.status_message.emit("Downloading…", False)

        _url, _platform = url, platform
        _media_type = "audio" if is_audio else "video"
        _quality, _audio_fmt = quality, audio_fmt
        _start, _end = start_time, end_time
        _out_dir, _video_codec = out_dir, video_codec

        def do_download():
            # Create a localized reference for this thread to check
            # Note: self._worker is replaced below before thread starts
            def cancel_fn():
                w = getattr(self, "_worker", None)
                return w is None or w.is_cancelled
            
            # Use local token to identify this download's progress signals
            def p_cb(p, e, s):
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
                status_cb=lambda msg: self._worker.signals.intercept_status.emit(msg),
                progress_cb=p_cb,
            )

        self._worker = Worker(do_download)
        self._worker.signals.result.connect(
            lambda r: self._on_result(r) if token == self._download_token else None
        )
        self._worker.signals.error.connect(
            lambda e: self._on_error(e) if token == self._download_token else None
        )
        self._worker.signals.intercept_status.connect(
            lambda m: self._on_intercept_status(m) if token == self._download_token else None
        )
        self._worker.signals.progress.connect(
            lambda p, e, s: self._on_progress(p, e, s) if token == self._download_token else None
        )
        self._worker.start()

    def _on_progress(self, percent: int, eta: int, speed_str: str) -> None:
        """Update progress bar, speed, and ETA labels."""
        if percent != -1:
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(percent)
        else:
            self._progress_bar.setRange(0, 0)

        if speed_str:
            self._speed_label.setText(speed_str)
            self._speed_label.setVisible(True)
        else:
            self._speed_label.setVisible(False)

        if eta != -1:
            if eta >= 60:
                m, s = divmod(eta, 60)
                eta_text = f"~{m}:{s:02d} left"
            else:
                eta_text = f"~{eta}s left"
            self._eta_label.setText(eta_text)
            self._eta_label.setVisible(True)
        else:
            self._eta_label.setVisible(False)

    def _on_intercept_status(self, msg: str) -> None:
        self._progress_label.setText(msg)
        self._progress_label.setVisible(True)

    def _set_busy(self, busy: bool) -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if busy:
            self._progress_label.setText("Downloading…")
        else:
            self._speed_label.setVisible(False)
            self._eta_label.setVisible(False)
        self.busy_changed.emit(busy)

    def _reset_ui(self) -> None:
        """Reset all download-related UI elements to idle state."""
        self._set_busy(False)
        self._progress_label.setVisible(False)
        self._speed_label.setVisible(False)
        self._eta_label.setVisible(False)
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setValue(0)

    def _cleanup_partial_files(self) -> None:
        self._do_cleanup_partial_files(self._active_output_dir)

    def _do_cleanup_partial_files(self, out_dir: str | None) -> None:
        """Remove yt-dlp .part files after the download thread has stopped."""
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

    def _on_result(self, result: dict) -> None:
        self._reset_ui()
        self._worker = None
        if result.get("success"):
            warn = result.get("warning")
            if warn:
                self.status_message.emit(warn, False)
            fp = result.get("file_path") or ""
            self._last_result_path = fp
            fn = os.path.basename(fp) if fp else "downloaded file"
            size = result.get("file_size")
            size_str = f"  ({size / (1024*1024):.1f} MB)" if size else ""
            _source = "browser_intercept" if result.get("error_code") == "browser_intercept_ok" else "direct"
            get_history_manager().add_item(
                HistoryItem(task_type="download", file_name=fn, file_path=fp, status="success", source=_source)
            )
            msg = f"Download complete → {fn}{size_str}"
            if result.get("error_code") == "http_fallback_ok":
                msg += "\nDownloaded via direct URL (yt-dlp unavailable for this link)."
            elif result.get("error_code") == "html_scrape_ok":
                msg += "\nDownloaded via embedded video found in page HTML."
            elif result.get("error_code") == "browser_intercept_ok":
                msg += "\nDownloaded via browser stream intercept."
            self.status_message.emit(msg, False)
        else:
            url = self._url_input.text()
            get_history_manager().add_item(
                HistoryItem(task_type="download", file_name=url, file_path=url, status="error")
            )
            code = result.get("error_code")
            err_text = _GENERIC_ERROR_MESSAGES.get(code) or "Download failed. Check the URL or network."
            self.status_message.emit(err_text, True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._reset_ui()
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
