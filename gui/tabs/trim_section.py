"""Trim Media tab — Trim / Ripple Delete / Insert Clip sub-tabs."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl, Signal, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QDialog,
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    _MULTIMEDIA_AVAILABLE = True
except Exception as _mm_exc:  # ImportError or DLL load failure (OSError)
    from utils.app_logger import get_logger
    get_logger().warning("QtMultimedia unavailable in trim_section: %s", _mm_exc)
    _MULTIMEDIA_AVAILABLE = False

from core.i18n import tr
from core.trimmer import trim_media, ripple_delete_multi, insert_clip
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker

_AUDIO_EXTS = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"}
_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}

_TAB_TRIM   = 0
_TAB_RIPPLE = 1
_TAB_INSERT = 2


def _ms_to_str(ms: int) -> str:
    total_s = max(0, ms // 1000)
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _str_to_ms(text: str) -> int | None:
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


def _time_input(default: str = "00:00:00") -> QLineEdit:
    w = QLineEdit(default)
    w.setObjectName("PillInput")
    w.setFixedWidth(120)
    w.setPlaceholderText("00:00:00")
    return w


# ── Segment timeline widget ────────────────────────────────────────────────────

class _SegmentTimeline(QWidget):
    """Thin bar showing delete segments as red bands over the full video duration."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(18)
        self.setMinimumWidth(100)
        self._duration_ms: int = 0
        self._segments: list[tuple[int, int]] = []

    def set_duration(self, ms: int) -> None:
        self._duration_ms = ms
        self.update()

    def set_segments(self, segments: list[tuple[str, str]]) -> None:
        self._segments = []
        for s, e in segments:
            s_ms = _str_to_ms(s)
            e_ms = _str_to_ms(e)
            if s_ms is not None and e_ms is not None and e_ms > s_ms:
                self._segments.append((s_ms, e_ms))
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(55, 55, 55))
        if self._duration_ms > 0:
            for s_ms, e_ms in self._segments:
                x1 = int(s_ms / self._duration_ms * w)
                x2 = int(e_ms / self._duration_ms * w)
                p.fillRect(x1, 0, max(2, x2 - x1), h, QColor(210, 60, 60, 220))
        p.end()


# ── Fullscreen preview dialog ──────────────────────────────────────────────────

class _FullscreenPreview(QDialog):
    """Fullscreen video preview. buttons = list of (label, callback) shown in the bar."""

    def __init__(
        self,
        source_url: QUrl,
        position_ms: int,
        volume: float,
        buttons: list[tuple[str, callable]],
        parent=None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("background: black;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._fs_video = QVideoWidget()
        root.addWidget(self._fs_video, stretch=1)

        self._fs_audio = QAudioOutput()
        self._fs_audio.setVolume(volume)

        self._fs_player = QMediaPlayer()
        self._fs_player.setVideoOutput(self._fs_video)
        self._fs_player.setAudioOutput(self._fs_audio)
        self._fs_player.durationChanged.connect(self._on_duration)
        self._fs_player.mediaStatusChanged.connect(self._on_status)
        self._fs_player.playbackStateChanged.connect(self._on_playback)

        self._fs_duration = 0
        self._seek_target = position_ms
        self._initial_seek_done = False
        self._fs_scrubbing = False

        # Controls bar
        bar = QWidget()
        bar.setStyleSheet(
            "background: rgba(0,0,0,210); border-top: 1px solid rgba(255,255,255,25);"
        )
        bar_layout = QVBoxLayout(bar)
        bar_layout.setContentsMargins(16, 8, 16, 10)
        bar_layout.setSpacing(6)

        self._fs_scrubber = QSlider(Qt.Orientation.Horizontal)
        self._fs_scrubber.setRange(0, 1000)
        self._fs_scrubber.sliderPressed.connect(self._on_scrub_press)
        self._fs_scrubber.sliderReleased.connect(self._on_scrub_release)
        self._fs_scrubber.sliderMoved.connect(self._on_scrub_move)
        bar_layout.addWidget(self._fs_scrubber)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._fs_play_btn = QPushButton("▶")
        self._fs_play_btn.setFixedSize(38, 38)
        self._fs_play_btn.setStyleSheet(
            "QPushButton{color:white;background:rgba(255,255,255,20);"
            "border:1px solid rgba(255,255,255,40);border-radius:4px;font-size:14px;}"
            "QPushButton:hover{background:rgba(255,255,255,40);}"
        )
        self._fs_play_btn.clicked.connect(self._toggle_play)
        btn_row.addWidget(self._fs_play_btn)

        self._fs_time_lbl = QLabel("00:00:00 / 00:00:00")
        self._fs_time_lbl.setStyleSheet(
            "color:white;font-size:14px;font-family:monospace;min-width:180px;"
        )
        btn_row.addWidget(self._fs_time_lbl)
        btn_row.addStretch()

        _btn_style = (
            "QPushButton{color:white;background:rgba(255,255,255,15);"
            "border:1px solid rgba(255,255,255,40);border-radius:4px;"
            "padding:0 14px;font-size:13px;}"
            "QPushButton:hover{background:rgba(255,255,255,35);}"
        )
        for label, cb in buttons:
            btn = QPushButton(label)
            btn.setFixedHeight(38)
            btn.setStyleSheet(_btn_style)
            btn.clicked.connect(cb)
            btn_row.addWidget(btn)

        close_btn = QPushButton(tr("btn_trim_fs_close"))
        close_btn.setFixedHeight(38)
        close_btn.setStyleSheet(
            "QPushButton{color:white;background:rgba(200,60,60,160);"
            "border:1px solid rgba(255,100,100,60);border-radius:4px;"
            "padding:0 14px;font-size:13px;}"
            "QPushButton:hover{background:rgba(220,80,80,200);}"
        )
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)

        bar_layout.addLayout(btn_row)
        root.addWidget(bar)

        self._fs_timer = QTimer(self)
        self._fs_timer.setInterval(200)
        self._fs_timer.timeout.connect(self._update_pos)
        self._fs_timer.start()

        self._fs_player.setSource(source_url)
        self.showFullScreen()

    def _on_duration(self, ms: int) -> None:
        self._fs_duration = ms
        self._fs_scrubber.setRange(0, ms)

    def _on_status(self, status) -> None:
        from PySide6.QtMultimedia import QMediaPlayer as _QMP
        if status == _QMP.MediaStatus.LoadedMedia and not self._initial_seek_done:
            self._initial_seek_done = True
            self._fs_player.setPosition(self._seek_target)
            self._fs_player.play()
            QTimer.singleShot(80, self._fs_player.pause)

    def _on_playback(self, state) -> None:
        from PySide6.QtMultimedia import QMediaPlayer as _QMP
        self._fs_play_btn.setText(
            "⏸" if state == _QMP.PlaybackState.PlayingState else "▶"
        )

    def _toggle_play(self) -> None:
        from PySide6.QtMultimedia import QMediaPlayer as _QMP
        if self._fs_player.playbackState() == _QMP.PlaybackState.PlayingState:
            self._fs_player.pause()
        else:
            self._fs_player.play()

    def _on_scrub_press(self) -> None:
        self._fs_scrubbing = True

    def _on_scrub_release(self) -> None:
        self._fs_player.setPosition(self._fs_scrubber.value())
        QTimer.singleShot(300, lambda: setattr(self, "_fs_scrubbing", False))

    def _on_scrub_move(self, value: int) -> None:
        if self._fs_duration:
            self._fs_time_lbl.setText(
                f"{_ms_to_str(value)} / {_ms_to_str(self._fs_duration)}"
            )

    def _update_pos(self) -> None:
        if not self._fs_scrubbing and self._fs_duration:
            pos = self._fs_player.position()
            self._fs_scrubber.setValue(pos)
            self._fs_time_lbl.setText(
                f"{_ms_to_str(pos)} / {_ms_to_str(self._fs_duration)}"
            )

    def get_position(self) -> int:
        return self._fs_player.position()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self._fs_timer.stop()
        self._fs_player.stop()
        super().closeEvent(event)


# ── Main section ───────────────────────────────────────────────────────────────

class TrimSection(QScrollArea):
    """Trim Media tab — Trim / Ripple Delete / Insert Clip."""

    status_message = Signal(str, bool)
    busy_changed   = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._duration_ms: int = 0
        self._is_audio_only = False
        self._last_result_path: str | None = None

        # Ripple rows: (start, end, row_widget, remove_btn, set_start_btn|None, set_end_btn|None)
        self._rd_rows: list[
            tuple[QLineEdit, QLineEdit, QWidget, QPushButton, QPushButton | None, QPushButton | None]
        ] = []

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(20, 20, 20, 20)
        self._content_layout.setSpacing(16)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._content_layout.addWidget(self._build_source_card())

        if _MULTIMEDIA_AVAILABLE:
            self._content_layout.addWidget(self._build_player_card())
        else:
            self._trim_mm_warn = QLabel(tr("warn_trim_no_mm"))
            self._trim_mm_warn.setObjectName("TextMuted")
            self._trim_mm_warn.setWordWrap(True)
            self._trim_mm_warn.setStyleSheet("padding: 8px;")
            self._content_layout.addWidget(self._trim_mm_warn)

        self._content_layout.addWidget(self._build_tabs_card())
        self._content_layout.addWidget(self._build_output_card())
        self._content_layout.addWidget(self._build_progress_card())

        self.setWidget(content)

        if _MULTIMEDIA_AVAILABLE:
            self._pos_timer = QTimer(self)
            self._pos_timer.setInterval(200)
            self._pos_timer.timeout.connect(self._update_position)

    # ── Source card ────────────────────────────────────────────────────────────

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
        self._file_input.setPlaceholderText(tr("ph_vid_aud"))
        self._file_input.textChanged.connect(self._on_source_changed)
        row.addWidget(self._file_input)

        self._browse_src_btn = QPushButton(tr("btn_browse"))
        self._browse_src_btn.setObjectName("BrowseBtn")
        self._browse_src_btn.setFixedWidth(90)
        self._browse_src_btn.clicked.connect(self._browse_file)
        row.addWidget(self._browse_src_btn)
        layout.addLayout(row)

        self._large_file_warn = QLabel(tr("warn_trim_large_file"))
        self._large_file_warn.setObjectName("TextMuted")
        self._large_file_warn.setStyleSheet("color: #D29922; font-size: 12px;")
        self._large_file_warn.setVisible(False)
        layout.addWidget(self._large_file_warn)
        return card

    # ── Player card ────────────────────────────────────────────────────────────

    def _build_player_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_preview = _section_header(tr("hdr_preview"))
        layout.addWidget(self._hdr_preview)

        self._video_widget = QVideoWidget()
        self._video_widget.setObjectName("VideoWidget")
        self._video_widget.setMinimumHeight(240)
        self._video_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self._video_widget)

        self._audio_output = QAudioOutput()
        self._audio_output.setVolume(1.0)

        self._player = QMediaPlayer()
        self._player.setVideoOutput(self._video_widget)
        self._player.setAudioOutput(self._audio_output)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)

        self._scrubber = QSlider(Qt.Orientation.Horizontal)
        self._scrubber.setObjectName("Scrubber")
        self._scrubber.setRange(0, 1000)
        self._scrubber.sliderPressed.connect(self._on_scrub_pressed)
        self._scrubber.sliderReleased.connect(self._on_scrub_released)
        self._scrubber.sliderMoved.connect(self._on_scrub_moved)
        self._scrubbing = False
        layout.addWidget(self._scrubber)

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
        self._vol_slider.setToolTip(tr("tip_trim_volume"))
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        ctrl.addWidget(self._vol_slider)

        self._time_label = QLabel("00:00:00 / 00:00:00")
        self._time_label.setObjectName("TextSecondary")
        ctrl.addWidget(self._time_label)
        ctrl.addStretch()

        self._trim_fs_btn = QPushButton("⛶")
        self._trim_fs_btn.setObjectName("SecondaryBtn")
        self._trim_fs_btn.setFixedSize(42, 42)
        self._trim_fs_btn.setToolTip(tr("tip_trim_fullscreen"))
        self._trim_fs_btn.clicked.connect(self._open_fullscreen)
        ctrl.addWidget(self._trim_fs_btn)

        layout.addLayout(ctrl)
        self._video_widget.setVisible(False)
        return card

    # ── Sub-tabs card ──────────────────────────────────────────────────────────

    def _build_tabs_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_trim_tab(), tr("tab_trim_sub_trim"))
        self._tabs.addTab(self._build_ripple_tab(), tr("tab_trim_sub_ripple"))
        self._tabs.addTab(self._build_insert_tab(), tr("tab_trim_sub_insert"))
        layout.addWidget(self._tabs)
        return card

    # ── Trim tab ───────────────────────────────────────────────────────────────

    def _build_trim_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_trim = _section_header(tr("hdr_trim_range"))
        layout.addWidget(self._hdr_trim)

        row = QHBoxLayout()
        row.setSpacing(16)

        start_col = QVBoxLayout()
        self._lbl_trim_start = QLabel(tr("lbl_start_time"))
        start_col.addWidget(self._lbl_trim_start)
        self._trim_start = _time_input("00:00:00")
        start_col.addWidget(self._trim_start)

        end_col = QVBoxLayout()
        self._lbl_trim_end = QLabel(tr("lbl_end_time"))
        end_col.addWidget(self._lbl_trim_end)
        self._trim_end = _time_input("00:00:00")
        end_col.addWidget(self._trim_end)

        if _MULTIMEDIA_AVAILABLE:
            self._trim_set_start_btn = QPushButton(tr("btn_set_to_current"))
            self._trim_set_start_btn.setObjectName("BrowseBtn")
            self._trim_set_start_btn.clicked.connect(
                lambda: self._trim_start.setText(_ms_to_str(self._player.position()))
            )
            start_col.addWidget(self._trim_set_start_btn)

            self._trim_set_end_btn = QPushButton(tr("btn_set_to_current"))
            self._trim_set_end_btn.setObjectName("BrowseBtn")
            self._trim_set_end_btn.clicked.connect(
                lambda: self._trim_end.setText(_ms_to_str(self._player.position()))
            )
            end_col.addWidget(self._trim_set_end_btn)

        row.addLayout(start_col)
        row.addLayout(end_col)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()
        return w

    # ── Ripple Delete tab ──────────────────────────────────────────────────────

    def _build_ripple_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_del_segs = _section_header(tr("hdr_delete_segs"))
        layout.addWidget(self._hdr_del_segs)

        self._ripple_hint = QLabel(tr("hint_trim_ripple"))
        self._ripple_hint.setObjectName("TextMuted")
        self._ripple_hint.setWordWrap(True)
        layout.addWidget(self._ripple_hint)

        # Timeline visualiser
        self._rd_timeline = _SegmentTimeline()
        layout.addWidget(self._rd_timeline)

        # Scrollable segment rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedHeight(180)

        self._rd_rows_container = QWidget()
        self._rd_rows_layout = QVBoxLayout(self._rd_rows_container)
        self._rd_rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rd_rows_layout.setSpacing(6)
        self._rd_rows_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._rd_rows_container)
        layout.addWidget(scroll)

        add_btn = QPushButton(tr("btn_add_segment"))
        add_btn.setObjectName("BrowseBtn")
        add_btn.setFixedWidth(140)
        add_btn.clicked.connect(self._rd_add_segment)
        layout.addWidget(add_btn)

        layout.addStretch()

        # Start with one empty row
        self._rd_add_segment()
        return w

    def _rd_add_segment(self) -> None:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        idx_lbl = QLabel(f"{len(self._rd_rows) + 1}.")
        idx_lbl.setFixedWidth(20)
        idx_lbl.setObjectName("TextSecondary")
        row_layout.addWidget(idx_lbl)

        start_in = _time_input("00:00:00")
        end_in   = _time_input("00:00:00")
        start_in.textChanged.connect(self._rd_refresh_timeline)
        end_in.textChanged.connect(self._rd_refresh_timeline)
        row_layout.addWidget(QLabel(tr("lbl_from")))
        row_layout.addWidget(start_in)
        row_layout.addWidget(QLabel(tr("lbl_to")))
        row_layout.addWidget(end_in)

        set_s_btn: QPushButton | None = None
        set_e_btn: QPushButton | None = None
        if _MULTIMEDIA_AVAILABLE:
            set_s_btn = QPushButton(tr("btn_set_start_seg"))
            set_s_btn.setObjectName("BrowseBtn")
            set_s_btn.clicked.connect(
                lambda _=False, si=start_in: si.setText(_ms_to_str(self._player.position()))
            )
            set_e_btn = QPushButton(tr("btn_set_end_seg"))
            set_e_btn.setObjectName("BrowseBtn")
            set_e_btn.clicked.connect(
                lambda _=False, ei=end_in: ei.setText(_ms_to_str(self._player.position()))
            )
            row_layout.addWidget(set_s_btn)
            row_layout.addWidget(set_e_btn)

        remove_btn = QPushButton("✕")
        remove_btn.setObjectName("SecondaryBtn")
        remove_btn.setFixedSize(32, 32)
        remove_btn.setToolTip(tr("tip_trim_remove_segment"))
        entry = (start_in, end_in, row_widget, remove_btn, set_s_btn, set_e_btn)
        remove_btn.clicked.connect(lambda _=False, e=entry: self._rd_remove_segment(e))
        row_layout.addWidget(remove_btn)
        row_layout.addStretch()

        self._rd_rows.append(entry)
        self._rd_rows_layout.addWidget(row_widget)
        self._rd_renumber()

    def _rd_remove_segment(self, entry: tuple) -> None:
        if len(self._rd_rows) <= 1:
            return  # keep at least one row
        self._rd_rows.remove(entry)
        entry[2].setParent(None)
        entry[2].deleteLater()
        self._rd_renumber()
        self._rd_refresh_timeline()

    def _rd_renumber(self) -> None:
        for i, (_, _, row_w, _, _, _) in enumerate(self._rd_rows):
            lbl = row_w.findChild(QLabel)
            if lbl:
                lbl.setText(f"{i + 1}.")

    def _rd_get_segments(self) -> list[tuple[str, str]]:
        return [(s.text().strip(), e.text().strip()) for s, e, *_ in self._rd_rows]

    def _rd_refresh_timeline(self) -> None:
        self._rd_timeline.set_segments(self._rd_get_segments())

    # ── Insert Clip tab ────────────────────────────────────────────────────────

    def _build_insert_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_insert = _section_header(tr("hdr_insert_clip"))
        layout.addWidget(self._hdr_insert)

        self._insert_hint = QLabel(tr("hint_trim_insert"))
        self._insert_hint.setObjectName("TextMuted")
        self._insert_hint.setWordWrap(True)
        layout.addWidget(self._insert_hint)

        # Clip file
        clip_row = QHBoxLayout()
        self._ins_clip_input = QLineEdit()
        self._ins_clip_input.setObjectName("PillInput")
        self._ins_clip_input.setPlaceholderText(tr("ph_clip"))
        clip_row.addWidget(self._ins_clip_input)
        self._browse_clip_btn = QPushButton(tr("btn_browse"))
        self._browse_clip_btn.setObjectName("BrowseBtn")
        self._browse_clip_btn.setFixedWidth(90)
        self._browse_clip_btn.clicked.connect(self._browse_clip)
        clip_row.addWidget(self._browse_clip_btn)

        clip_lbl_row = QVBoxLayout()
        clip_lbl_row.addWidget(QLabel(tr("lbl_clip_file")))
        clip_lbl_row.addLayout(clip_row)
        layout.addLayout(clip_lbl_row)

        # Insert position
        at_col = QVBoxLayout()
        at_col.addWidget(QLabel(tr("lbl_insert_at")))
        at_row = QHBoxLayout()
        at_row.setSpacing(8)
        self._ins_at_input = _time_input("00:00:00")
        at_row.addWidget(self._ins_at_input)
        if _MULTIMEDIA_AVAILABLE:
            self._ins_set_at_btn = QPushButton(tr("btn_set_to_current"))
            self._ins_set_at_btn.setObjectName("BrowseBtn")
            self._ins_set_at_btn.clicked.connect(
                lambda: self._ins_at_input.setText(_ms_to_str(self._player.position()))
            )
            at_row.addWidget(self._ins_set_at_btn)
        at_row.addStretch()
        at_col.addLayout(at_row)
        layout.addLayout(at_col)

        layout.addStretch()
        return w

    # ── Output + progress cards ────────────────────────────────────────────────

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

    # ── Source file handling ───────────────────────────────────────────────────

    def _on_source_changed(self, path: str) -> None:
        path = path.strip()
        if not os.path.isfile(path):
            return
        ext = os.path.splitext(path)[1].lower()
        self._is_audio_only = ext in _AUDIO_EXTS
        self._large_file_warn.setVisible(os.path.getsize(path) > 4 * 1024 * 1024 * 1024)
        if _MULTIMEDIA_AVAILABLE:
            self._load_media(path)


    def retranslate_ui(self) -> None:
        if hasattr(self, "_trim_mm_warn"):
            self._trim_mm_warn.setText(tr("warn_trim_no_mm"))
        self._hdr_src.setText(tr("hdr_source_file"))
        self._file_input.setPlaceholderText(tr("ph_vid_aud"))
        self._browse_src_btn.setText(tr("btn_browse"))
        self._large_file_warn.setText(tr("warn_trim_large_file"))
        if hasattr(self, "_hdr_preview"):
            self._hdr_preview.setText(tr("hdr_preview"))
            self._vol_slider.setToolTip(tr("tip_trim_volume"))
            self._trim_fs_btn.setToolTip(tr("tip_trim_fullscreen"))
        if hasattr(self, "_hdr_trim"):
            self._hdr_trim.setText(tr("hdr_trim_range"))
        self._lbl_trim_start.setText(tr("lbl_start_time"))
        self._lbl_trim_end.setText(tr("lbl_end_time"))
        if _MULTIMEDIA_AVAILABLE and hasattr(self, "_trim_set_start_btn"):
            self._trim_set_start_btn.setText(tr("btn_set_to_current"))
            self._trim_set_end_btn.setText(tr("btn_set_to_current"))
        if hasattr(self, "_hdr_del_segs"):
            self._hdr_del_segs.setText(tr("hdr_delete_segs"))
        if hasattr(self, "_ripple_hint"):
            self._ripple_hint.setText(tr("hint_trim_ripple"))
        for _s, _e, _rw, rm_btn, ss_btn, se_btn in self._rd_rows:
            rm_btn.setToolTip(tr("tip_trim_remove_segment"))
            if ss_btn is not None:
                ss_btn.setText(tr("btn_set_start_seg"))
            if se_btn is not None:
                se_btn.setText(tr("btn_set_end_seg"))
        if hasattr(self, "_hdr_insert"):
            self._hdr_insert.setText(tr("hdr_insert_clip"))
        if hasattr(self, "_insert_hint"):
            self._insert_hint.setText(tr("hint_trim_insert"))
        self._browse_clip_btn.setText(tr("btn_browse"))
        if _MULTIMEDIA_AVAILABLE and hasattr(self, "_ins_set_at_btn"):
            self._ins_set_at_btn.setText(tr("btn_set_to_current"))
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._out_input.setPlaceholderText(tr("ph_same_dir"))
        self._browse_out_btn.setText(tr("btn_browse"))
        if hasattr(self, "_tabs") and self._tabs.count() >= 3:
            self._tabs.setTabText(_TAB_TRIM, tr("tab_trim_sub_trim"))
            self._tabs.setTabText(_TAB_RIPPLE, tr("tab_trim_sub_ripple"))
            self._tabs.setTabText(_TAB_INSERT, tr("tab_trim_sub_insert"))

    def _browse_file(self) -> None:
        start = os.path.dirname(self._file_input.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Media File", start,
            "Media (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.mp3 *.wav *.aac *.flac *.ogg *.m4a)",
        )
        if path:
            self._file_input.setText(path)

    def _browse_clip(self) -> None:
        start = os.path.dirname(self._ins_clip_input.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Clip to Insert", start,
            "Video (*.mp4 *.mkv *.avi *.mov *.webm *.flv)",
        )
        if path:
            self._ins_clip_input.setText(path)

    def _browse_output(self) -> None:
        start = self._out_input.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if d:
            self._out_input.setText(d)

    def populate_file(self, path: str) -> None:
        self._file_input.setText(path)

    # ── Media player ───────────────────────────────────────────────────────────

    def _load_media(self, path: str) -> None:
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(path))
        self._video_widget.setVisible(not self._is_audio_only)

    def _on_media_status_changed(self, status) -> None:
        from PySide6.QtMultimedia import QMediaPlayer as _QMP
        if status == _QMP.MediaStatus.LoadedMedia and not self._is_audio_only:
            self._player.play()
            QTimer.singleShot(80, self._player.pause)

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._duration_ms = duration_ms
        self._scrubber.setRange(0, max(1, duration_ms))
        end_str = _ms_to_str(duration_ms)
        self._trim_end.setText(end_str)
        self._time_label.setText(f"00:00:00 / {end_str}")
        self._rd_timeline.set_duration(duration_ms)
        self._pos_timer.start()

    def _on_playback_state_changed(self, state) -> None:
        from PySide6.QtMultimedia import QMediaPlayer as _QMP
        self._play_btn.setText(
            "⏸" if state == _QMP.PlaybackState.PlayingState else "▶"
        )

    def _update_position(self) -> None:
        if not self._scrubbing and self._duration_ms:
            pos = self._player.position()
            self._scrubber.setValue(pos)
            self._time_label.setText(
                f"{_ms_to_str(pos)} / {_ms_to_str(self._duration_ms)}"
            )

    def _on_scrub_pressed(self) -> None:
        self._scrubbing = True

    def _on_scrub_released(self) -> None:
        self._player.setPosition(self._scrubber.value())
        QTimer.singleShot(300, lambda: setattr(self, "_scrubbing", False))

    def _on_scrub_moved(self, value: int) -> None:
        if self._duration_ms:
            self._time_label.setText(
                f"{_ms_to_str(value)} / {_ms_to_str(self._duration_ms)}"
            )

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
        if value > 0 and self._mute_btn.isChecked():
            self._mute_btn.setChecked(False)
            self._toggle_mute(False)

    def _open_fullscreen(self) -> None:
        if not _MULTIMEDIA_AVAILABLE or not hasattr(self, "_player"):
            return
        src = self._file_input.text().strip()
        if not src or not os.path.exists(src):
            self.status_message.emit("Load a file first.", True)
            return
        self._player.pause()

        tab = self._tabs.currentIndex()
        if tab == _TAB_TRIM:
            buttons = [
                (tr("btn_set_start"), lambda: self._trim_start.setText(_ms_to_str(dlg.get_position()))),
                (tr("btn_set_end"),   lambda: self._trim_end.setText(_ms_to_str(dlg.get_position()))),
            ]
        elif tab == _TAB_RIPPLE:
            # Set start/end on the last segment row
            last_s, last_e = self._rd_rows[-1][0], self._rd_rows[-1][1]
            buttons = [
                (tr("btn_set_start"), lambda: last_s.setText(_ms_to_str(dlg.get_position()))),
                (tr("btn_set_end"),   lambda: last_e.setText(_ms_to_str(dlg.get_position()))),
            ]
        else:  # INSERT
            buttons = [
                (tr("btn_set_insert"), lambda: self._ins_at_input.setText(_ms_to_str(dlg.get_position()))),
            ]

        dlg = _FullscreenPreview(
            source_url=self._player.source(),
            position_ms=self._player.position(),
            volume=self._audio_output.volume(),
            buttons=buttons,
            parent=self,
        )
        dlg.exec()
        self._player.setPosition(dlg.get_position())

    # ── Visibility ─────────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        if _MULTIMEDIA_AVAILABLE and hasattr(self, "_pos_timer") and self._duration_ms:
            self._pos_timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        if _MULTIMEDIA_AVAILABLE and hasattr(self, "_pos_timer"):
            self._pos_timer.stop()
        super().hideEvent(event)

    # ── Primary action ─────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        tab = self._tabs.currentIndex()

        src = self._file_input.text().strip()
        if not src or not os.path.exists(src):
            self.status_message.emit("Please select a valid media file.", True)
            return

        out_dir = self._out_input.text().strip() or None

        if _MULTIMEDIA_AVAILABLE and hasattr(self, "_player"):
            self._player.stop()

        if tab == _TAB_TRIM:
            self._run_trim(src, out_dir)
        elif tab == _TAB_RIPPLE:
            self._run_ripple(src, out_dir)
        else:
            self._run_insert(src, out_dir)

    def _run_trim(self, src: str, out_dir: str | None) -> None:
        start_str = self._trim_start.text().strip() or "0"
        end_str   = self._trim_end.text().strip()
        if not end_str or end_str == "00:00:00":
            self.status_message.emit("Please set a valid end time.", True)
            return

        self._set_busy(True, "Trimming…", "Trimming media…")

        def _do():
            return trim_media(src, start_str, end_str, out_dir)

        self._start_worker(_do, src, "_trimmed", out_dir, "trim")

    def _run_ripple(self, src: str, out_dir: str | None) -> None:
        segments = self._rd_get_segments()
        if not any(s and e for s, e in segments):
            self.status_message.emit("Please enter at least one delete segment.", True)
            return

        self._set_busy(True, "Deleting segments…", "Deleting segments…")

        def _do():
            return ripple_delete_multi(src, segments, out_dir)

        self._start_worker(_do, src, "_trimmed", out_dir, "trim")

    def _run_insert(self, src: str, out_dir: str | None) -> None:
        clip = self._ins_clip_input.text().strip()
        if not clip or not os.path.exists(clip):
            self.status_message.emit("Please select a valid clip file.", True)
            return
        at_str = self._ins_at_input.text().strip() or "0"

        self._set_busy(True, "Inserting clip…", "Re-encoding and inserting clip…")

        def _do():
            return insert_clip(src, clip, at_str, out_dir)

        self._start_worker(_do, src, "_inserted", out_dir, "trim")

    def _start_worker(self, fn, src, suffix, out_dir, task_type) -> None:
        self._pending_src     = src
        self._pending_suffix  = suffix
        self._pending_out_dir = out_dir
        self._pending_task    = task_type

        self._worker = Worker(fn)
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

        src     = self._pending_src
        suffix  = self._pending_suffix
        out_dir = self._pending_out_dir or os.path.dirname(src)
        base    = os.path.splitext(os.path.basename(src))[0]
        ext     = os.path.splitext(src)[1]
        out_path = os.path.join(out_dir, f"{base}{suffix}{ext}")

        if success:
            self._last_result_path = out_path
            get_history_manager().add_item(
                HistoryItem(
                    task_type=self._pending_task,
                    file_name=os.path.basename(out_path),
                    file_path=out_path,
                    status="success",
                )
            )
            self.status_message.emit(f"Done → {os.path.basename(out_path)}", False)
        else:
            get_history_manager().add_item(
                HistoryItem(
                    task_type=self._pending_task,
                    file_name=os.path.basename(src),
                    file_path=src,
                    status="error",
                )
            )
            self.status_message.emit("Operation failed. Check inputs.", True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
