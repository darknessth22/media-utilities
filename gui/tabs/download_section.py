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

from PySide6.QtCore import Qt, Signal
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
    QVBoxLayout,
    QWidget,
)

from core.downloader import download_media, get_available_formats, get_platform
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker

_AUDIO_FORMATS = ["MP3", "FLAC", "OGG", "OPUS", "M4A"]


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


class DownloadSection(QScrollArea):
    """Media Download tab — URL-based downloader."""

    status_message = Signal(str, bool)   # (text, is_error)
    busy_changed   = Signal(bool)        # True=task started, False=task ended

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._formats: list[dict] = []          # from get_available_formats()
        self._selected_format_id: str | None = None

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
        layout.addWidget(_section_header("TIME RANGE  (optional — HH:MM:SS or MM:SS)"))

        row = QHBoxLayout()
        row.setSpacing(16)

        start_col = QVBoxLayout()
        start_col.addWidget(QLabel("Start"))
        self._start_input = QLineEdit()
        self._start_input.setObjectName("PillInput")
        self._start_input.setFixedWidth(110)
        self._start_input.setPlaceholderText("0:00")
        start_col.addWidget(self._start_input)
        row.addLayout(start_col)

        end_col = QVBoxLayout()
        end_col.addWidget(QLabel("End"))
        self._end_input = QLineEdit()
        self._end_input.setObjectName("PillInput")
        self._end_input.setFixedWidth(110)
        self._end_input.setPlaceholderText("end of video")
        end_col.addWidget(self._end_input)
        row.addLayout(end_col)

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
            self._platform_label.setText(f"Detected: {label}")
            # Spotify is audio-only
            if platform == "spotify":
                self._audio_radio.setChecked(True)
        else:
            self._platform_label.setText("")

    def _on_type_toggled(self, is_video: bool) -> None:
        self._audio_fmt_container.setVisible(not is_video)
        # Quality selection only makes sense for video
        self._quality_combo.setEnabled(is_video)
        self._check_fmt_btn.setEnabled(is_video)

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
            self._set_busy(False)
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
        if start_time and not end_time:
            self.status_message.emit("Please set an end time when specifying a start time.", True)
            return

        self._set_busy(True)
        self.status_message.emit("Downloading…", False)

        _url, _platform = url, platform
        _media_type = "audio" if is_audio else "video"
        _quality, _audio_fmt = quality, audio_fmt
        _start, _end = start_time, end_time
        _out_dir, _video_codec = out_dir, video_codec
        _cancel_check = None

        def do_download():
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
                cancel_check=_cancel_check,
            )

        self._worker = Worker(do_download)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if busy:
            self._progress_label.setText("Downloading…")
        self.busy_changed.emit(busy)

    def _on_result(self, result: dict) -> None:
        self._set_busy(False)
        self._worker = None
        if result.get("success"):
            fp = result.get("file_path") or ""
            fn = os.path.basename(fp) if fp else "downloaded file"
            size = result.get("file_size")
            size_str = f"  ({size / (1024*1024):.1f} MB)" if size else ""
            get_history_manager().add_item(
                HistoryItem(task_type="download", file_name=fn, file_path=fp, status="success")
            )
            self.status_message.emit(f"Download complete → {fn}{size_str}", False)
        else:
            url = self._url_input.text()
            get_history_manager().add_item(
                HistoryItem(task_type="download", file_name=url, file_path=url, status="error")
            )
            self.status_message.emit("Download failed. Check the URL or network.", True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
