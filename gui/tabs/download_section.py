"""Media Download tab — PySide6 UI with sequential download queue."""
from __future__ import annotations

import os
import re
import uuid

from PySide6.QtCore import Qt, Signal, QUrl, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    _MULTIMEDIA_AVAILABLE = True
except Exception as _mm_exc:  # ImportError or DLL load failure (OSError)
    from utils.app_logger import get_logger
    get_logger().warning("QtMultimedia unavailable in download_section: %s", _mm_exc)
    _MULTIMEDIA_AVAILABLE = False

from core.i18n import tr
from core.downloader import download_media, fetch_playlist_entries, fetch_spotify_entries, get_available_formats, get_available_subtitles, get_platform, get_preview_stream_url
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.presets_bar import PresetsBar
from gui.worker import Worker

_AUDIO_FORMATS = ["MP3", "WAV", "AAC", "FLAC", "OGG", "M4A"]
_VIDEO_AUDIO_FORMATS = ["Original", "AAC", "MP3", "OPUS"]

_GENERIC_ERROR_MESSAGES: dict[str, str] = {
    "timeout": "Connection timed out. Check your network and try again.",
    "auth_required": "This video requires login or authentication.",
    "no_video": "No downloadable video found at this URL.",
    "download_failed": "Download failed. Check the URL or your network.",
    "cancelled": "Download cancelled.",
    "unsupported_platform": "This site is not supported. Supported: YouTube, YouTube Music, Spotify, Facebook, Instagram, TikTok, Twitter/X, LinkedIn, Twitch.",
    "unsupported_url": "yt-dlp couldn't recognize this link. For Facebook groups, open the specific video or post and copy its direct link (a profile or group page has no single video). Updating yt-dlp in Settings may also help.",
    # Codes emitted by core.downloader._classify_download_error
    "geo_blocked": "This video is not available in your region. Try a VPN or different cookies.",
    "paywall": "This video requires login, subscription, or age confirmation. Set cookies in Settings.",
    "unavailable": "This video has been removed or is no longer available.",
    "rate_limited": "The site is rate-limiting downloads. Wait a few minutes and try again.",
    "ffmpeg": "Post-processing failed. The downloaded file may be corrupt or in an unsupported format.",
    "empty_media": "Instagram sent an empty response for this post — usually means yt-dlp's extractor is outdated. Go to Settings and click \"Update yt-dlp\", then try again.",
    "network": "Network error. Check your connection and try again.",
    "generic": "Download failed. Check the URL or try again later.",
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

        self._status_lbl = QLabel(tr("dyn_pending"))
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
        self._status_lbl.setText(tr("dyn_downloading"))
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
        self._status_lbl.setText(tr("dyn_done"))
        self._progress_bar.setVisible(False)
        self._info_lbl.setVisible(False)
        self._cancel_btn.setEnabled(False)

    def set_error(self, msg: str = "") -> None:
        self._dot.setStyleSheet("color: #F85149; font-size: 10px;")
        self._status_lbl.setText(tr("dyn_error"))
        self._progress_bar.setVisible(False)
        if msg:
            self._info_lbl.setText(msg[:80])
            self._info_lbl.setVisible(True)
        self._cancel_btn.setEnabled(False)

    def set_cancelled(self) -> None:
        self._dot.setStyleSheet("color: #8B949E; font-size: 10px;")
        self._status_lbl.setText(tr("dyn_cancelled"))
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

        layout.addWidget(self._build_presets_card())
        layout.addWidget(self._build_url_card())
        layout.addWidget(self._build_playlist_card())
        layout.addWidget(self._build_type_card())
        layout.addWidget(self._build_quality_card())
        layout.addWidget(self._build_trim_card())
        if _MULTIMEDIA_AVAILABLE:
            layout.addWidget(self._build_preview_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_queue_card())

        self.setWidget(content)

    # ── Preset support ─────────────────────────────────────────────────────────

    def get_preset_data(self) -> dict:
        return {
            "media_type": "audio" if self._audio_radio.isChecked() else "video",
            "audio_fmt": next(
                (f for f, b in self._audio_fmt_btns.items() if b.isChecked()), "MP3"
            ),
            "video_audio_fmt": next(
                (f for f, b in self._video_audio_fmt_btns.items() if b.isChecked()),
                "Original",
            ),
            "quality": self._quality_combo.currentText(),
            "output_dir": self._out_input.text().strip(),
        }

    def load_preset_data(self, data: dict) -> None:
        if data.get("media_type") == "audio":
            self._audio_radio.setChecked(True)
        else:
            self._video_radio.setChecked(True)
        if af := data.get("audio_fmt"):
            self._select_audio_fmt(af)
        if vaf := data.get("video_audio_fmt"):
            self._select_video_audio_fmt(vaf)
        if out := data.get("output_dir"):
            self._out_input.setText(out)

    def _build_presets_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(0)
        layout.addWidget(
            PresetsBar(
                "download",
                self._settings,
                self.get_preset_data,
                self.load_preset_data,
            )
        )
        return card

    def paste_url(self, url: str) -> None:
        """Set the URL input and trigger format check."""
        self._url_input.setText(url)

    # ── Card builders ──────────────────────────────────────────────────────────

    def _build_url_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_url = _section_header(tr("hdr_source_url"))
        layout.addWidget(self._hdr_url)

        row = QHBoxLayout()
        self._url_input = QLineEdit()
        self._url_input.setObjectName("PillInput")
        self._url_input.setPlaceholderText(tr("ph_url_services"))
        self._url_input.textChanged.connect(self._on_url_changed)
        row.addWidget(self._url_input)
        layout.addLayout(row)

        self._platform_label = QLabel()
        self._platform_label.setObjectName("TextMuted")
        self._platform_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._platform_label)
        return card

    def _is_playlist_url(self, url: str) -> bool:
        if re.search(r'[?&]list=', url) and ('youtube.com' in url or 'youtu.be' in url):
            return True
        # Spotify albums and playlists are multi-track collections.
        return bool(re.search(r'open\.spotify\.com/(?:intl-[a-z]{2}/)?(?:album|playlist)/', url))

    def _is_spotify_collection_url(self, url: str) -> bool:
        return bool(re.search(r'open\.spotify\.com/(?:intl-[a-z]{2}/)?(?:album|playlist)/', url))

    def _build_playlist_card(self) -> QFrame:
        self._playlist_card = _card()
        self._playlist_card.setVisible(False)
        layout = QVBoxLayout(self._playlist_card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_playlist = _section_header(tr("hdr_playlist"))
        layout.addWidget(self._hdr_playlist)

        load_row = QHBoxLayout()
        self._load_playlist_btn = QPushButton(tr("btn_load_playlist"))
        self._load_playlist_btn.setObjectName("BrowseBtn")
        self._load_playlist_btn.setFixedWidth(120)
        self._load_playlist_btn.clicked.connect(self._load_playlist)
        load_row.addWidget(self._load_playlist_btn)
        self._playlist_status_lbl = QLabel()
        self._playlist_status_lbl.setObjectName("TextMuted")
        self._playlist_status_lbl.setStyleSheet("font-size: 12px;")
        load_row.addWidget(self._playlist_status_lbl)
        self._playlist_status_key: str | None = None
        load_row.addStretch()
        layout.addLayout(load_row)

        self._playlist_table = QTableWidget(0, 3)
        self._playlist_table.setHorizontalHeaderLabels(["", tr("lbl_title"), tr("lbl_duration")])
        hdr = self._playlist_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._playlist_table.setColumnWidth(0, 32)
        self._playlist_table.setColumnWidth(2, 80)
        self._playlist_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._playlist_table.verticalHeader().setVisible(False)
        self._playlist_table.setMinimumHeight(180)
        self._playlist_table.setMaximumHeight(360)
        self._playlist_table.setVisible(False)
        layout.addWidget(self._playlist_table)

        action_row = QHBoxLayout()
        self._select_all_btn = QPushButton(tr("btn_select_all"))
        self._select_all_btn.setObjectName("ChipBtn")
        self._select_all_btn.setFixedWidth(80)
        self._select_all_btn.setVisible(False)
        self._select_all_btn.clicked.connect(lambda: self._set_all_playlist_checked(True))
        action_row.addWidget(self._select_all_btn)
        self._deselect_all_btn = QPushButton(tr("btn_deselect_all"))
        self._deselect_all_btn.setObjectName("ChipBtn")
        self._deselect_all_btn.setFixedWidth(90)
        self._deselect_all_btn.setVisible(False)
        self._deselect_all_btn.clicked.connect(lambda: self._set_all_playlist_checked(False))
        action_row.addWidget(self._deselect_all_btn)
        action_row.addStretch()
        self._download_selected_btn = QPushButton(tr("btn_download_selected"))
        self._download_selected_btn.setObjectName("BrowseBtn")
        self._download_selected_btn.setFixedWidth(150)
        self._download_selected_btn.setVisible(False)
        self._download_selected_btn.clicked.connect(self._download_selected_playlist_items)
        action_row.addWidget(self._download_selected_btn)
        layout.addLayout(action_row)

        self._playlist_quality_hint = QLabel(tr("hint_playlist_quality"))
        self._playlist_quality_hint.setObjectName("TextMuted")
        self._playlist_quality_hint.setWordWrap(True)
        self._playlist_quality_hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._playlist_quality_hint)
        return self._playlist_card

    def _build_type_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_media_type = _section_header(tr("hdr_media_type"))
        layout.addWidget(self._hdr_media_type)

        row = QHBoxLayout()
        row.setSpacing(16)
        self._type_group = QButtonGroup(self)
        self._video_radio = QRadioButton(tr("lbl_video"))
        self._audio_radio = QRadioButton(tr("lbl_audio_only"))
        self._video_radio.setChecked(True)
        self._type_group.addButton(self._video_radio, 0)
        self._type_group.addButton(self._audio_radio, 1)
        self._video_radio.toggled.connect(self._on_type_toggled)
        row.addWidget(self._video_radio)
        row.addWidget(self._audio_radio)
        row.addStretch()
        layout.addLayout(row)

        self._audio_fmt_container = QWidget()
        self._audio_fmt_container.setStyleSheet("background: transparent;")

        af_row = QHBoxLayout(self._audio_fmt_container)
        af_row.setContentsMargins(0, 0, 0, 0)
        af_row.setSpacing(8)
        self._audio_fmt_btns: dict[str, QPushButton] = {}
        for fmt in _AUDIO_FORMATS:
            btn = QPushButton(fmt)
            btn.setObjectName("ChipBtn")
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setFixedWidth(64)
            btn.clicked.connect(lambda _c, f=fmt: self._select_audio_fmt(f))
            self._audio_fmt_btns[fmt] = btn
            af_row.addWidget(btn)
        af_row.addStretch()
        layout.addWidget(self._audio_fmt_container)
        self._audio_fmt_container.setVisible(False)
        self._select_audio_fmt("MP3")

        self._video_audio_fmt_container = QWidget()
        self._video_audio_fmt_container.setStyleSheet("background: transparent;")
        vaf_layout = QVBoxLayout(self._video_audio_fmt_container)
        vaf_layout.setContentsMargins(0, 4, 0, 0)
        vaf_layout.setSpacing(4)
        self._lbl_audio_in_video = QLabel(tr("lbl_audio_fmt_in_video"))
        self._lbl_audio_in_video.setObjectName("TextMuted")
        self._lbl_audio_in_video.setStyleSheet("font-size: 11px;")
        vaf_layout.addWidget(self._lbl_audio_in_video)
        vaf_row = QHBoxLayout()
        vaf_row.setContentsMargins(0, 0, 0, 0)
        vaf_row.setSpacing(8)
        self._video_audio_fmt_btns: dict[str, QPushButton] = {}
        for fmt in _VIDEO_AUDIO_FORMATS:
            btn = QPushButton(fmt)
            btn.setObjectName("ChipBtn")
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setFixedWidth(70)
            btn.clicked.connect(lambda _c, f=fmt: self._select_video_audio_fmt(f))
            self._video_audio_fmt_btns[fmt] = btn
            vaf_row.addWidget(btn)
        vaf_row.addStretch()
        vaf_layout.addLayout(vaf_row)
        layout.addWidget(self._video_audio_fmt_container)
        self._video_audio_fmt_container.setVisible(True)
        self._select_video_audio_fmt("Original")

        self._subs_container = QWidget()
        self._subs_container.setStyleSheet("background: transparent;")
        sub_layout = QVBoxLayout(self._subs_container)
        sub_layout.setContentsMargins(0, 6, 0, 0)
        sub_layout.setSpacing(4)
        self._subs_check = QCheckBox(tr("lbl_dl_subtitles"))
        self._subs_check.toggled.connect(self._on_subs_toggled)
        sub_layout.addWidget(self._subs_check)
        sub_row = QHBoxLayout()
        sub_row.setContentsMargins(16, 0, 0, 0)
        sub_row.setSpacing(8)
        self._lbl_subs_lang = QLabel(tr("lbl_dl_sub_track"))
        self._lbl_subs_lang.setObjectName("TextMuted")
        self._lbl_subs_lang.setStyleSheet("font-size: 11px;")
        sub_row.addWidget(self._lbl_subs_lang)
        self._subs_combo = QComboBox()
        self._subs_combo.setMinimumWidth(220)
        self._subs_combo.addItem(tr("lbl_dl_sub_load_first"), None)
        self._subs_combo.setEnabled(False)
        sub_row.addWidget(self._subs_combo)
        self._subs_check_btn = QPushButton(tr("btn_dl_check_subs"))
        self._subs_check_btn.setObjectName("BrowseBtn")
        self._subs_check_btn.setFixedWidth(110)
        self._subs_check_btn.setEnabled(False)
        self._subs_check_btn.clicked.connect(self._check_subs)
        sub_row.addWidget(self._subs_check_btn)
        sub_row.addStretch()
        sub_layout.addLayout(sub_row)
        layout.addWidget(self._subs_container)
        return card

    def _build_quality_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_quality = _section_header(tr("hdr_video_quality"))
        layout.addWidget(self._hdr_quality)

        row = QHBoxLayout()
        self._quality_combo = QComboBox()
        self._quality_combo.setObjectName("QualityCombo")
        self._quality_combo.addItem(tr("lbl_best_available"))
        self._quality_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(self._quality_combo)

        self._check_fmt_btn = QPushButton(tr("btn_check_formats"))
        self._check_fmt_btn.setObjectName("BrowseBtn")
        self._check_fmt_btn.setFixedWidth(120)
        self._check_fmt_btn.clicked.connect(self._check_formats)
        row.addWidget(self._check_fmt_btn)
        layout.addLayout(row)

        self._quality_hint = QLabel(tr("hint_check_formats_download"))
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
        self._hdr_time_range = _section_header(tr("hdr_time_range"))
        header_row.addWidget(self._hdr_time_range)
        header_row.addStretch()

        self._load_preview_btn = QPushButton(tr("btn_load_preview"))
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
        self._lbl_trim_start = QLabel(tr("lbl_start"))
        start_col.addWidget(self._lbl_trim_start)
        self._start_input = QLineEdit()
        self._start_input.setObjectName("PillInput")
        self._start_input.setFixedWidth(110)
        self._start_input.setPlaceholderText(tr("ph_trim_start_short"))
        self._start_input.textChanged.connect(self._on_time_input_changed)
        start_col.addWidget(self._start_input)
        row.addLayout(start_col)

        end_col = QVBoxLayout()
        self._lbl_trim_end = QLabel(tr("lbl_end"))
        end_col.addWidget(self._lbl_trim_end)
        self._end_input = QLineEdit()
        self._end_input.setObjectName("PillInput")
        self._end_input.setFixedWidth(110)
        self._end_input.setPlaceholderText(tr("ph_trim_end"))
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
        self._play_btn = QPushButton(tr("btn_play"))
        self._play_btn.setObjectName("ChipBtn")
        self._play_btn.setFixedWidth(70)
        self._play_btn.clicked.connect(self._toggle_playback)
        ctrl_row.addWidget(self._play_btn)

        self._reload_preview_btn = QPushButton(tr("btn_reload"))
        self._reload_preview_btn.setObjectName("ChipBtn")
        self._reload_preview_btn.setFixedWidth(70)
        self._reload_preview_btn.setToolTip(tr("tooltip_reload_preview"))
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

        self._lbl_start_marker = QLabel(tr("lbl_start_marker"))
        self._lbl_start_marker.setObjectName("TextMuted")
        self._lbl_start_marker.setStyleSheet("font-size: 10px;")
        range_layout.addWidget(self._lbl_start_marker)
        self._start_slider = QSlider(Qt.Orientation.Horizontal)
        self._start_slider.setObjectName("StartSlider")
        self._start_slider.sliderMoved.connect(self._on_start_slider_moved)
        range_layout.addWidget(self._start_slider)

        self._lbl_end_marker = QLabel(tr("lbl_end_marker"))
        self._lbl_end_marker.setObjectName("TextMuted")
        self._lbl_end_marker.setStyleSheet("font-size: 10px;")
        range_layout.addWidget(self._lbl_end_marker)
        self._end_slider = QSlider(Qt.Orientation.Horizontal)
        self._end_slider.setObjectName("EndSlider")
        self._end_slider.sliderMoved.connect(self._on_end_slider_moved)
        range_layout.addWidget(self._end_slider)

        layout.addLayout(range_layout)

        self._preview_expiry_note = QLabel(tr("hint_preview_cdn_expire"))
        self._preview_expiry_note.setObjectName("TextMuted")
        self._preview_expiry_note.setWordWrap(True)
        self._preview_expiry_note.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._preview_expiry_note)

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
        self._hdr_output = _section_header(tr("hdr_output_folder"))
        layout.addWidget(self._hdr_output)

        row = QHBoxLayout()
        self._out_input = QLineEdit()
        self._out_input.setObjectName("PillInput")
        self._out_input.setPlaceholderText(tr("ph_cwd"))
        if self._settings.output_folder:
            self._out_input.setText(self._settings.output_folder)
        row.addWidget(self._out_input)

        self._out_browse_btn = QPushButton(tr("btn_browse"))
        self._out_browse_btn.setObjectName("BrowseBtn")
        self._out_browse_btn.setFixedWidth(90)
        self._out_browse_btn.clicked.connect(self._browse_output)
        row.addWidget(self._out_browse_btn)
        layout.addLayout(row)
        return card

    def _build_queue_card(self) -> QFrame:
        self._queue_card = _card()
        self._queue_card.setVisible(False)
        outer = QVBoxLayout(self._queue_card)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        header_row = QHBoxLayout()
        self._hdr_queue = _section_header(tr("hdr_download_queue"))
        header_lbl = self._hdr_queue
        header_lbl.setStyleSheet(
            "font-size: 11px; font-weight: bold; letter-spacing: 1px;"
        )
        header_row.addWidget(header_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        header_row.addStretch()
        self._clear_done_btn = QPushButton(tr("btn_clear_done"))
        clear_btn = self._clear_done_btn
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


    def retranslate_ui(self) -> None:
        self._hdr_url.setText(tr("hdr_source_url"))
        self._url_input.setPlaceholderText(tr("ph_url_services"))
        self._hdr_playlist.setText(tr("hdr_playlist"))
        self._load_playlist_btn.setText(tr("btn_load_playlist"))
        self._select_all_btn.setText(tr("btn_select_all"))
        self._deselect_all_btn.setText(tr("btn_deselect_all"))
        self._download_selected_btn.setText(tr("btn_download_selected"))
        self._playlist_quality_hint.setText(tr("hint_playlist_quality"))
        self._hdr_media_type.setText(tr("hdr_media_type"))
        self._video_radio.setText(tr("lbl_video"))
        self._audio_radio.setText(tr("lbl_audio_only"))
        self._lbl_audio_in_video.setText(tr("lbl_audio_fmt_in_video"))
        self._subs_check.setText(tr("lbl_dl_subtitles"))
        self._lbl_subs_lang.setText(tr("lbl_dl_sub_track"))
        self._subs_check_btn.setText(tr("btn_dl_check_subs"))
        self._hdr_quality.setText(tr("hdr_video_quality"))
        self._check_fmt_btn.setText(tr("btn_check_formats"))
        if self._quality_combo.count():
            self._quality_combo.setItemText(0, tr("lbl_best_available"))
        self._quality_hint.setText(tr("hint_check_formats_download"))
        self._hdr_time_range.setText(tr("hdr_time_range"))
        self._load_preview_btn.setText(tr("btn_load_preview"))
        if _MULTIMEDIA_AVAILABLE:
            self._play_btn.setText(tr("btn_play"))
            self._reload_preview_btn.setText(tr("btn_reload"))
            self._reload_preview_btn.setToolTip(tr("tooltip_reload_preview"))
            self._lbl_start_marker.setText(tr("lbl_start_marker"))
            self._lbl_end_marker.setText(tr("lbl_end_marker"))
            self._preview_expiry_note.setText(tr("hint_preview_cdn_expire"))
        self._lbl_trim_start.setText(tr("lbl_start"))
        self._lbl_trim_end.setText(tr("lbl_end"))
        self._start_input.setPlaceholderText(tr("ph_trim_start_short"))
        self._end_input.setPlaceholderText(tr("ph_trim_end"))
        self._hdr_output.setText(tr("hdr_output_folder"))
        self._out_input.setPlaceholderText(tr("ph_cwd"))
        self._out_browse_btn.setText(tr("btn_browse"))
        self._hdr_queue.setText(tr("hdr_download_queue"))
        self._clear_done_btn.setText(tr("btn_clear_done"))
        self._playlist_table.setHorizontalHeaderLabels(
            ["", tr("lbl_title"), tr("lbl_duration")]
        )
        self._refresh_playlist_status_lbl()

    def _refresh_playlist_status_lbl(self) -> None:
        key = getattr(self, "_playlist_status_key", None)
        if not key:
            return
        if key == "count":
            n = getattr(self, "_playlist_loaded_count", 0)
            self._playlist_status_lbl.setText(tr("lbl_playlist_video_count").format(n=n))
        elif key == "error":
            msg = getattr(self, "_playlist_err_msg", "") or ""
            self._playlist_status_lbl.setText(tr("err_download_playlist").format(msg=msg[:60]))
        else:
            self._playlist_status_lbl.setText(tr(key))

    def _on_url_changed(self, url: str) -> None:
        url = url.strip()
        if url:
            platform = get_platform(url)
            platform_names = {
                "youtube": "YouTube", "facebook": "Facebook",
                "instagram": "Instagram", "tiktok": "TikTok",
                "twitter": "Twitter / X", "linkedin": "LinkedIn",
                "spotify": "Spotify", "twitch": "Twitch",
            }
            if platform == "unsupported":
                self._platform_label.setText(
                    "⚠ Unsupported site — only YouTube, YouTube Music, Spotify, Facebook, Instagram, TikTok, Twitter/X, LinkedIn, and Twitch are supported."
                )
                self._platform_label.setStyleSheet("font-size: 12px; color: #F85149;")
            else:
                label = platform_names.get(platform, platform.capitalize())
                self._platform_label.setText(f"Detected: {label}")
                self._platform_label.setStyleSheet("font-size: 12px;")
            if platform == "spotify":
                self._audio_radio.setChecked(True)
            self._playlist_card.setVisible(self._is_playlist_url(url))
        else:
            self._platform_label.setText("")
            self._platform_label.setStyleSheet("font-size: 12px;")
            self._playlist_card.setVisible(False)
        self._reset_playlist_table()

        if _MULTIMEDIA_AVAILABLE:
            self._player.stop()
            self._preview_card.setVisible(False)
            self._duration_ms = 0
            self._start_input.clear()
            self._end_input.clear()

    def _on_subs_toggled(self, checked: bool) -> None:
        self._subs_combo.setEnabled(checked and self._subs_combo.count() > 1)
        self._subs_check_btn.setEnabled(checked)

    def _check_subs(self) -> None:
        url = self._url_input.text().strip()
        if not url:
            self.status_message.emit("Enter a URL first.", True)
            return
        self._subs_check_btn.setEnabled(False)
        self._subs_check_btn.setText(tr("dyn_checking"))
        self.status_message.emit("Fetching available subtitles…", False)
        worker = Worker(lambda: get_available_subtitles(url))
        worker.signals.result.connect(self._on_subs_fetched)
        worker.signals.error.connect(self._on_subs_error)
        worker.start()
        self._subs_worker = worker

    def _on_subs_fetched(self, subs: list) -> None:
        self._subs_check_btn.setEnabled(True)
        self._subs_check_btn.setText(tr("btn_dl_check_subs"))
        self._subs_combo.clear()
        if not subs:
            self._subs_combo.addItem(tr("lbl_dl_sub_none"), None)
            self._subs_combo.setEnabled(False)
            self.status_message.emit("No subtitles available for this URL.", True)
            return
        for s in subs:
            label = f"{s['name']} [{s['lang']}]"
            self._subs_combo.addItem(label, {"lang": s["lang"], "auto": s["auto"]})
        self._subs_combo.setEnabled(True)
        self.status_message.emit(f"{len(subs)} subtitle track(s) loaded.", False)

    def _on_subs_error(self, err_tuple: tuple) -> None:
        self._subs_check_btn.setEnabled(True)
        self._subs_check_btn.setText(tr("btn_dl_check_subs"))
        _, msg, _ = err_tuple
        self.status_message.emit(f"Subtitle check failed: {msg}", True)

    def _on_type_toggled(self, is_video: bool) -> None:
        self._audio_fmt_container.setVisible(not is_video)
        self._video_audio_fmt_container.setVisible(is_video)
        self._subs_container.setVisible(is_video)
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

    def _select_video_audio_fmt(self, fmt: str) -> None:
        self._selected_video_audio_fmt = fmt
        for name, btn in self._video_audio_fmt_btns.items():
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
        self._load_preview_btn.setText(tr("dyn_loading"))
        self.status_message.emit("Fetching preview stream…", False)
        worker = Worker(lambda: get_preview_stream_url(url))
        worker.signals.result.connect(self._on_preview_loaded)
        worker.signals.error.connect(self._on_preview_error)
        worker.start()
        self._preview_worker = worker

    def _on_preview_loaded(self, result: dict) -> None:
        self._load_preview_btn.setEnabled(True)
        self._load_preview_btn.setText(tr("btn_load_preview"))
        if "error" in result:
            from core.downloader import _classify_download_error
            code = _classify_download_error(result["error"])
            friendly = _GENERIC_ERROR_MESSAGES.get(code)
            msg = friendly if friendly else result["error"]
            self.status_message.emit(f"Preview unavailable: {msg}", True)
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
        self._load_preview_btn.setText(tr("btn_load_preview"))
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
            self._play_btn.setText(tr("btn_play"))
            self._pos_timer.stop()
        else:
            self._player.play()
            self._play_btn.setText(tr("btn_pause"))
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

    # ── Playlist manager ───────────────────────────────────────────────────────

    def _reset_playlist_table(self) -> None:
        self._playlist_table.setRowCount(0)
        self._playlist_table.setVisible(False)
        self._select_all_btn.setVisible(False)
        self._deselect_all_btn.setVisible(False)
        self._download_selected_btn.setVisible(False)
        self._playlist_status_key = None
        self._playlist_status_lbl.setText("")
        self._load_playlist_btn.setEnabled(True)
        self._load_playlist_btn.setText(tr("btn_load_playlist"))

    def _load_playlist(self) -> None:
        url = self._url_input.text().strip()
        if not url:
            return
        self._load_playlist_btn.setEnabled(False)
        self._load_playlist_btn.setText(tr("dyn_loading"))
        self._playlist_status_key = "dyn_fetching_playlist"
        self._playlist_status_lbl.setText(tr("dyn_fetching_playlist"))
        self._playlist_table.setVisible(False)
        self._select_all_btn.setVisible(False)
        self._deselect_all_btn.setVisible(False)
        self._download_selected_btn.setVisible(False)
        _url = url
        _fetch = fetch_spotify_entries if self._is_spotify_collection_url(_url) else fetch_playlist_entries
        worker = Worker(lambda: _fetch(_url))
        worker.signals.result.connect(self._on_playlist_loaded)
        worker.signals.error.connect(self._on_playlist_error)
        worker.start()
        self._playlist_fetch_worker = worker

    def _on_playlist_loaded(self, entries: list) -> None:
        self._load_playlist_btn.setEnabled(True)
        self._load_playlist_btn.setText(tr("btn_reload"))
        if not entries:
            self._playlist_status_key = "err_playlist_empty"
            self._playlist_status_lbl.setText(tr("err_playlist_empty"))
            return
        self._playlist_table.setRowCount(0)
        for entry in entries:
            row = self._playlist_table.rowCount()
            self._playlist_table.insertRow(row)

            chk = QCheckBox()
            chk.setChecked(True)
            chk_container = QWidget()
            chk_container.setStyleSheet("background: transparent;")
            chk_layout = QHBoxLayout(chk_container)
            chk_layout.addWidget(chk)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            self._playlist_table.setCellWidget(row, 0, chk_container)

            title_item = QTableWidgetItem(entry["title"])
            title_item.setFlags(title_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            title_item.setData(Qt.ItemDataRole.UserRole, entry["url"])
            self._playlist_table.setItem(row, 1, title_item)

            dur_item = QTableWidgetItem(entry["duration"])
            dur_item.setFlags(dur_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            dur_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._playlist_table.setItem(row, 2, dur_item)

        self._playlist_status_key = "count"
        self._playlist_loaded_count = len(entries)
        self._playlist_status_lbl.setText(
            tr("lbl_playlist_video_count").format(n=len(entries))
        )
        self._playlist_table.setVisible(True)
        self._select_all_btn.setVisible(True)
        self._deselect_all_btn.setVisible(True)
        self._download_selected_btn.setVisible(True)

    def _on_playlist_error(self, err_tuple: tuple) -> None:
        self._load_playlist_btn.setEnabled(True)
        self._load_playlist_btn.setText(tr("btn_load_playlist"))
        _, msg, _ = err_tuple
        self._playlist_status_key = "error"
        self._playlist_err_msg = str(msg)
        self._playlist_status_lbl.setText(
            tr("err_download_playlist").format(msg=str(msg)[:60])
        )

    def _set_all_playlist_checked(self, checked: bool) -> None:
        for row in range(self._playlist_table.rowCount()):
            container = self._playlist_table.cellWidget(row, 0)
            if container:
                chk = container.findChild(QCheckBox)
                if chk:
                    chk.setChecked(checked)

    def _download_selected_playlist_items(self) -> None:
        is_audio = self._audio_radio.isChecked()
        audio_fmt = getattr(self, "_selected_audio_fmt", "mp3").lower()
        video_audio_fmt = getattr(self, "_selected_video_audio_fmt", "Original")
        out_dir = self._out_input.text().strip() or None
        codec = self._settings.default_codec or "original"
        codec_map = {
            "original": "original", "h264": "libx264",
            "hevc": "libx265", "vp9": "libvpx-vp9",
        }
        video_codec = codec_map.get(codec, "original")

        # Use height-based quality matching (from first-video formats) — not format_id,
        # since format IDs differ between videos.
        quality_height: int | None = None
        if not is_audio:
            idx = self._quality_combo.currentIndex()
            if idx > 0:
                data = self._quality_combo.itemData(idx)
                if isinstance(data, dict):
                    quality_height = data.get("height") or None

        _sub_data = self._subs_combo.currentData() if self._subs_combo.isEnabled() else None
        queued = 0
        for row in range(self._playlist_table.rowCount()):
            container = self._playlist_table.cellWidget(row, 0)
            if not container:
                continue
            chk = container.findChild(QCheckBox)
            if not chk or not chk.isChecked():
                continue
            title_item = self._playlist_table.item(row, 1)
            if not title_item:
                continue
            video_url = title_item.data(Qt.ItemDataRole.UserRole)
            title = title_item.text()
            if not video_url:
                continue

            job_id = uuid.uuid4().hex[:8]
            display_name = title if len(title) <= 60 else title[:57] + "…"
            job = {
                "job_id": job_id,
                "url": video_url,
                "display_name": display_name,
                "platform": get_platform(video_url),
                "media_type": "audio" if is_audio else "video",
                "quality": None,
                "quality_height": quality_height,
                "playlist_mode": "single",
                "audio_fmt": audio_fmt,
                "video_audio_fmt": video_audio_fmt,
                "start_time": None,
                "end_time": None,
                "out_dir": out_dir,
                "video_codec": video_codec,
                "subtitles": (not is_audio) and self._subs_check.isChecked() and bool(_sub_data),
                "subtitle_lang": (_sub_data or {}).get("lang", ""),
                "subtitle_auto": (_sub_data or {}).get("auto", False),
                "status": "pending",
            }
            self._queue.append(job)
            self._add_job_row(job)
            queued += 1

        if queued == 0:
            self.status_message.emit("No items selected.", True)
            return

        self._queue_card.setVisible(True)
        self._emit_queue_count()
        if self._worker is None or not self._worker.isRunning():
            self._run_next()
        self.status_message.emit(f"Queued {queued} playlist item(s).", False)

    # ── "Check Formats" ───────────────────────────────────────────────────────

    def _check_formats(self) -> None:
        url = self._url_input.text().strip()
        if not url:
            self.status_message.emit("Enter a URL first.", True)
            return
        self._check_fmt_btn.setEnabled(False)
        self._check_fmt_btn.setText(tr("dyn_checking"))
        self.status_message.emit("Fetching available formats…", False)
        _url = url
        worker = Worker(lambda: get_available_formats(_url))
        worker.signals.result.connect(self._on_formats_fetched)
        worker.signals.error.connect(self._on_formats_error)
        worker.start()
        self._fmt_worker = worker

    def _on_formats_fetched(self, formats: list) -> None:
        self._check_fmt_btn.setEnabled(True)
        self._check_fmt_btn.setText(tr("btn_check_formats"))
        self._formats = formats
        self._quality_combo.clear()
        self._quality_combo.addItem(tr("lbl_best_available"), None)
        for fmt in formats:
            self._quality_combo.addItem(
                fmt["display"],
                {"format_id": fmt["format_id"], "height": fmt.get("height", 0)},
            )
        if formats:
            self.status_message.emit(f"{len(formats)} format(s) loaded.", False)
        else:
            self.status_message.emit("No formats found — URL may be unsupported.", True)

    def _on_formats_error(self, err_tuple: tuple) -> None:
        self._check_fmt_btn.setEnabled(True)
        self._check_fmt_btn.setText(tr("btn_check_formats"))
        _, msg, _ = err_tuple
        self.status_message.emit(f"Format check failed: {msg}", True)

    # ── Visibility ─────────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        if _MULTIMEDIA_AVAILABLE and hasattr(self, "_pos_timer") and hasattr(self, "_player"):
            if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self._pos_timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        if _MULTIMEDIA_AVAILABLE and hasattr(self, "_pos_timer"):
            self._pos_timer.stop()
        super().hideEvent(event)

    # ── Queue management ───────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        """Add current form state as a new download job to the queue."""
        url = self._url_input.text().strip()
        if not url:
            self.status_message.emit("Please enter a URL.", True)
            return

        is_audio = self._audio_radio.isChecked()
        platform = get_platform(url)
        if platform == "unsupported":
            self.status_message.emit(
                "Unsupported site. Supported: YouTube, YouTube Music, Spotify, Facebook, Instagram, TikTok, Twitter/X, LinkedIn.",
                True,
            )
            return
        audio_fmt = getattr(self, "_selected_audio_fmt", "mp3").lower()
        video_audio_fmt = getattr(self, "_selected_video_audio_fmt", "Original")
        out_dir = self._out_input.text().strip() or None
        codec = self._settings.default_codec or "original"
        codec_map = {
            "original": "original", "h264": "libx264",
            "hevc": "libx265", "vp9": "libvpx-vp9",
        }
        video_codec = codec_map.get(codec, "original")

        quality: str | None = None
        quality_height: int | None = None
        playlist_mode = "single"
        if not is_audio:
            idx = self._quality_combo.currentIndex()
            if idx > 0:
                data = self._quality_combo.itemData(idx)
                if isinstance(data, dict):
                    quality = data.get("format_id")
                    quality_height = data.get("height") or None
                else:
                    quality = data

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
        _sub_data = self._subs_combo.currentData() if self._subs_combo.isEnabled() else None
        job = {
            "job_id": job_id,
            "url": url,
            "display_name": display_name,
            "platform": platform,
            "media_type": "audio" if is_audio else "video",
            "quality": quality,
            "quality_height": quality_height,
            "playlist_mode": playlist_mode,
            "audio_fmt": audio_fmt,
            "video_audio_fmt": video_audio_fmt,
            "start_time": start_time,
            "end_time": end_time,
            "out_dir": out_dir,
            "video_codec": video_codec,
            "subtitles": (not is_audio) and self._subs_check.isChecked() and bool(_sub_data),
            "subtitle_lang": (_sub_data or {}).get("lang", ""),
            "subtitle_auto": (_sub_data or {}).get("auto", False),
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
        self._playlist_card.setVisible(False)
        self._quality_combo.clear()
        self._quality_combo.addItem(tr("lbl_best_available"))
        self._start_input.clear()
        self._end_input.clear()
        self._video_radio.setChecked(True)

    def _emit_queue_count(self) -> None:
        count = sum(1 for j in self._queue if j["status"] in ("pending", "downloading"))
        self.queue_changed.emit(count)
        # Don't flip primary button to "Cancel" — Download tab uses a queue:
        # the primary button always means "Add to queue". Per-row × cancels.
        self.busy_changed.emit(False)

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
        _quality_height = pending.get("quality_height")
        _playlist_mode = pending.get("playlist_mode", "single")
        _audio_fmt = pending["audio_fmt"]
        _video_audio_fmt = pending.get("video_audio_fmt", "Original")
        _start = pending["start_time"]
        _end = pending["end_time"]
        _out_dir = pending["out_dir"]
        _video_codec = pending["video_codec"]
        _subs = pending.get("subtitles", False)
        _sub_lang = pending.get("subtitle_lang", "")
        _sub_auto = pending.get("subtitle_auto", False)

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
                quality_height=_quality_height,
                playlist_mode=_playlist_mode,
                start_time=_start,
                end_time=_end,
                audio_format=_audio_fmt,
                video_audio_format=_video_audio_fmt,
                output_dir=_out_dir,
                video_codec=_video_codec,
                cancel_check=cancel_fn,
                status_cb=lambda msg: (
                    self._worker.signals.intercept_status.emit(msg) if self._worker else None
                ),
                progress_cb=p_cb,
                subtitles=_subs,
                subtitle_lang=_sub_lang,
                subtitle_auto=_sub_auto,
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
        if self._active_job is None or self._active_job["job_id"] != job_id:
            return
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
        if self._active_job is None or self._active_job["job_id"] != job_id:
            return
        row = self._job_rows.get(job_id)
        if row:
            row.update_progress(percent, speed, eta)

    def _on_job_result(self, job_id: str, result: dict) -> None:
        if self._active_job is None or self._active_job["job_id"] != job_id:
            return
        job = next((j for j in self._queue if j["job_id"] == job_id), None)
        _old = self._worker
        self._worker = None
        self._active_job = None
        if _old is not None:
            _old.wait(5000)

        row = self._job_rows.get(job_id)

        if result.get("success"):
            if job:
                job["status"] = "done"
            fp = result.get("file_path") or ""
            if result.get("is_playlist"):
                count = result.get("playlist_count", 0)
                playlist_files = result.get("playlist_files", [])
                display = f"Playlist — {count} video(s) downloaded"
                if job:
                    job["display_name"] = display
                if row:
                    row.update_name(display)
                    row.set_done()
                self._last_result_path = fp
                if playlist_files:
                    for pf in playlist_files:
                        fn = os.path.basename(pf)
                        get_history_manager().add_item(
                            HistoryItem(
                                task_type="download", file_name=fn, file_path=pf,
                                status="success", source="direct",
                            )
                        )
                        self.status_message.emit(f"Download complete → {fn}", False)
                else:
                    if job:
                        get_history_manager().add_item(
                            HistoryItem(
                                task_type="download", file_name=display,
                                file_path=fp, status="success", source="direct",
                            )
                        )
                    self.status_message.emit(f"Playlist complete: {count} video(s) downloaded", False)
                QTimer.singleShot(2000, lambda: self._remove_job(job_id))
                self._emit_queue_count()
                return
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
            err_text = _GENERIC_ERROR_MESSAGES.get(code) or result.get("warning") or "Download failed."
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
        if self._active_job is None or self._active_job["job_id"] != job_id:
            return
        job = next((j for j in self._queue if j["job_id"] == job_id), None)
        _old = self._worker
        self._worker = None
        self._active_job = None
        if _old is not None:
            _old.wait(5000)

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
        if self._active_job is None or self._active_job["job_id"] != job_id:
            return
        job = next((j for j in self._queue if j["job_id"] == job_id), None)
        if job and job["status"] == "cancelled":
            _old = self._worker
            self._worker = None
            self._active_job = None
            if _old is not None:
                _old.wait(5000)
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
            # Watchdog — if worker stuck in ffmpeg postproc and doesn't honor
            # the cancel flag within 5s, force-remove the row and reclaim the
            # worker slot so the queue can advance.
            QTimer.singleShot(5000, lambda: self._force_finalize_cancel(job_id))
        elif job["status"] == "pending":
            job["status"] = "cancelled"
            if row:
                row.set_cancelled()
            QTimer.singleShot(500, lambda: self._remove_job(job_id))

        self._emit_queue_count()

    def _force_finalize_cancel(self, job_id: str) -> None:
        """Kill stuck worker after cancel grace period."""
        job = next((j for j in self._queue if j["job_id"] == job_id), None)
        if job is None or job["status"] != "cancelled":
            return
        # Worker still running → terminate it. QThread.terminate is unsafe
        # but here it's the only way to release a yt-dlp post-process that
        # ignored cancel_check (e.g. mid-ffmpeg merge).
        if self._worker and self._worker.isRunning():
            try:
                self._worker.terminate()
                self._worker.wait(2000)
            except Exception:
                pass
            self._worker = None
        self._active_job = None
        self._remove_job(job_id)
        if self._worker is None:
            self._run_next()

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
