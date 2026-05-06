"""Jump-Cutter tab — auto-remove silence with protected ranges + media preview."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QPainter
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
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    _MULTIMEDIA_AVAILABLE = True
except Exception as _mm_exc:
    from utils.app_logger import get_logger
    get_logger().warning("QtMultimedia unavailable in jumpcut_section: %s", _mm_exc)
    _MULTIMEDIA_AVAILABLE = False

from core.i18n import tr
from core.jumpcutter import _AUDIO_EXTS, _VIDEO_EXTS, remove_silence
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


def _time_input(default: str = "00:00:00") -> QLineEdit:
    w = QLineEdit(default)
    w.setObjectName("PillInput")
    w.setFixedWidth(120)
    w.setPlaceholderText("00:00:00")
    return w


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


class _ProtectedTimeline(QWidget):
    """Thin bar showing protected ranges as green bands over full duration."""

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
                p.fillRect(x1, 0, max(2, x2 - x1), h, QColor(70, 190, 110, 220))
        p.end()


class JumpcutSection(QScrollArea):
    """Auto-silence removal with media preview + protected ranges."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_result_path: str | None = None
        self._duration_ms: int = 0
        self._is_audio_only = False

        # Protected rows: (start_in, end_in, row_widget, remove_btn, set_s_btn|None, set_e_btn|None)
        self._pr_rows: list[
            tuple[QLineEdit, QLineEdit, QWidget, QPushButton, QPushButton | None, QPushButton | None]
        ] = []

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAcceptDrops(True)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_source_card())
        if _MULTIMEDIA_AVAILABLE:
            layout.addWidget(self._build_player_card())
        else:
            self._mm_warn = QLabel(tr("warn_trim_no_mm"))
            self._mm_warn.setObjectName("TextMuted")
            self._mm_warn.setWordWrap(True)
            self._mm_warn.setStyleSheet("padding: 8px;")
            layout.addWidget(self._mm_warn)

        layout.addWidget(self._build_params_card())
        layout.addWidget(self._build_protected_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())
        self.setWidget(content)

        if _MULTIMEDIA_AVAILABLE:
            self._pos_timer = QTimer(self)
            self._pos_timer.setInterval(200)
            self._pos_timer.timeout.connect(self._update_position)

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
        self._file_input.textChanged.connect(self._on_source_changed)
        row.addWidget(self._file_input)

        self._browse_src_btn = QPushButton(tr("btn_browse"))
        self._browse_src_btn.setObjectName("BrowseBtn")
        self._browse_src_btn.setFixedWidth(90)
        self._browse_src_btn.clicked.connect(self._browse_file)
        row.addWidget(self._browse_src_btn)
        layout.addLayout(row)
        return card

    # ── Player ────────────────────────────────────────────────────────────────

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
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        ctrl.addWidget(self._vol_slider)

        self._time_label = QLabel("00:00:00 / 00:00:00")
        self._time_label.setObjectName("TextSecondary")
        ctrl.addWidget(self._time_label)
        ctrl.addStretch()

        # Quick mark buttons — add a new protected range from current position
        self._mark_in_btn = QPushButton(tr("btn_jumpcut_mark_in"))
        self._mark_in_btn.setObjectName("BrowseBtn")
        self._mark_in_btn.setToolTip(tr("tip_jumpcut_mark_in"))
        self._mark_in_btn.clicked.connect(self._mark_in_at_current)
        ctrl.addWidget(self._mark_in_btn)

        self._mark_out_btn = QPushButton(tr("btn_jumpcut_mark_out"))
        self._mark_out_btn.setObjectName("BrowseBtn")
        self._mark_out_btn.setToolTip(tr("tip_jumpcut_mark_out"))
        self._mark_out_btn.clicked.connect(self._mark_out_at_current)
        ctrl.addWidget(self._mark_out_btn)

        layout.addLayout(ctrl)
        self._video_widget.setVisible(False)
        return card

    # ── Params ────────────────────────────────────────────────────────────────

    def _build_params_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)
        self._hdr_params = _section_header(tr("hdr_jumpcut_params"))
        layout.addWidget(self._hdr_params)

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

        self._lbl_dur = QLabel(tr("lbl_jumpcut_minsil").format(s=0.5))
        layout.addWidget(self._lbl_dur)
        self._dur_slider = QSlider(Qt.Orientation.Horizontal)
        self._dur_slider.setRange(1, 30)
        self._dur_slider.setValue(5)
        self._dur_slider.setTickInterval(5)
        self._dur_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._dur_slider.valueChanged.connect(
            lambda v: self._lbl_dur.setText(tr("lbl_jumpcut_minsil").format(s=v / 10.0))
        )
        layout.addWidget(self._dur_slider)

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

        self._pr_timeline = _ProtectedTimeline()
        layout.addWidget(self._pr_timeline)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedHeight(180)
        self._pr_rows_container = QWidget()
        self._pr_rows_layout = QVBoxLayout(self._pr_rows_container)
        self._pr_rows_layout.setContentsMargins(0, 0, 0, 0)
        self._pr_rows_layout.setSpacing(6)
        self._pr_rows_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._pr_rows_container)
        layout.addWidget(scroll)

        self._pr_add_btn = QPushButton(tr("btn_add_protected_range"))
        self._pr_add_btn.setObjectName("BrowseBtn")
        self._pr_add_btn.setFixedWidth(180)
        self._pr_add_btn.clicked.connect(lambda: self._pr_add_row())
        layout.addWidget(self._pr_add_btn)

        self._pr_add_row()  # start with one empty row
        return card

    def _pr_add_row(self, start: str = "00:00:00", end: str = "00:00:00") -> tuple:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        idx_lbl = QLabel(f"{len(self._pr_rows) + 1}.")
        idx_lbl.setFixedWidth(20)
        idx_lbl.setObjectName("TextSecondary")
        row_layout.addWidget(idx_lbl)

        start_in = _time_input(start)
        end_in = _time_input(end)
        start_in.textChanged.connect(self._pr_refresh_timeline)
        end_in.textChanged.connect(self._pr_refresh_timeline)
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
        remove_btn.clicked.connect(lambda _=False, e=entry: self._pr_remove_row(e))
        row_layout.addWidget(remove_btn)
        row_layout.addStretch()

        self._pr_rows.append(entry)
        self._pr_rows_layout.addWidget(row_widget)
        self._pr_renumber()
        self._pr_refresh_timeline()
        return entry

    def _pr_remove_row(self, entry: tuple) -> None:
        if len(self._pr_rows) <= 1:
            entry[0].setText("00:00:00")
            entry[1].setText("00:00:00")
            return
        self._pr_rows.remove(entry)
        entry[2].setParent(None)
        entry[2].deleteLater()
        self._pr_renumber()
        self._pr_refresh_timeline()

    def _pr_renumber(self) -> None:
        for i, (_, _, row_w, *_rest) in enumerate(self._pr_rows):
            lbl = row_w.findChild(QLabel)
            if lbl:
                lbl.setText(f"{i + 1}.")

    def _pr_get_segments(self) -> list[tuple[str, str]]:
        return [(s.text().strip(), e.text().strip()) for s, e, *_ in self._pr_rows]

    def _pr_refresh_timeline(self) -> None:
        self._pr_timeline.set_segments(self._pr_get_segments())

    def _pr_collect_ranges(self) -> tuple[list[tuple[float, float]], list[str]]:
        """Convert rows to (ranges_in_seconds, errors). Skips empty rows."""
        ranges: list[tuple[float, float]] = []
        errors: list[str] = []
        for s_str, e_str in self._pr_get_segments():
            s_ms = _str_to_ms(s_str)
            e_ms = _str_to_ms(e_str)
            if s_ms is None or e_ms is None:
                errors.append(f"{s_str} - {e_str}")
                continue
            if s_ms == 0 and e_ms == 0:
                continue  # empty placeholder row
            if e_ms <= s_ms:
                errors.append(f"{s_str} - {e_str}")
                continue
            ranges.append((s_ms / 1000.0, e_ms / 1000.0))
        return ranges, errors

    # Mark in/out from current playback position
    def _mark_in_at_current(self) -> None:
        if not _MULTIMEDIA_AVAILABLE:
            return
        ts = _ms_to_str(self._player.position())
        last = self._pr_rows[-1] if self._pr_rows else None
        if last is not None and last[0].text().strip() == "00:00:00" and last[1].text().strip() == "00:00:00":
            last[0].setText(ts)
            return
        self._pr_add_row(start=ts, end=ts)

    def _mark_out_at_current(self) -> None:
        if not _MULTIMEDIA_AVAILABLE or not self._pr_rows:
            return
        self._pr_rows[-1][1].setText(_ms_to_str(self._player.position()))

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

    # ── Media player ──────────────────────────────────────────────────────────

    def _on_source_changed(self, path: str) -> None:
        path = path.strip()
        if not os.path.isfile(path):
            return
        ext = os.path.splitext(path)[1].lower()
        self._is_audio_only = ext in _AUDIO_EXTS
        if _MULTIMEDIA_AVAILABLE:
            self._load_media(path)

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
        self._time_label.setText(f"00:00:00 / {_ms_to_str(duration_ms)}")
        self._pr_timeline.set_duration(duration_ms)
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

    def showEvent(self, event) -> None:
        if _MULTIMEDIA_AVAILABLE and hasattr(self, "_pos_timer") and self._duration_ms:
            self._pos_timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        if _MULTIMEDIA_AVAILABLE and hasattr(self, "_pos_timer"):
            self._pos_timer.stop()
        super().hideEvent(event)

    # ── i18n ──────────────────────────────────────────────────────────────────

    def retranslate_ui(self) -> None:
        self._hdr_src.setText(tr("hdr_source_file"))
        self._hint.setText(tr("hint_jumpcut_intro"))
        self._file_input.setPlaceholderText(tr("ph_vid_aud"))
        self._browse_src_btn.setText(tr("btn_browse"))
        if hasattr(self, "_hdr_preview"):
            self._hdr_preview.setText(tr("hdr_preview"))
            self._mark_in_btn.setText(tr("btn_jumpcut_mark_in"))
            self._mark_in_btn.setToolTip(tr("tip_jumpcut_mark_in"))
            self._mark_out_btn.setText(tr("btn_jumpcut_mark_out"))
            self._mark_out_btn.setToolTip(tr("tip_jumpcut_mark_out"))
        if hasattr(self, "_mm_warn"):
            self._mm_warn.setText(tr("warn_trim_no_mm"))
        self._hdr_params.setText(tr("hdr_jumpcut_params"))
        self._lbl_noise.setText(tr("lbl_jumpcut_noise").format(db=self._noise_slider.value()))
        self._lbl_dur.setText(tr("lbl_jumpcut_minsil").format(s=self._dur_slider.value() / 10.0))
        self._lbl_pad.setText(tr("lbl_jumpcut_padding").format(ms=self._pad_slider.value() * 10))
        self._hdr_protected.setText(tr("hdr_jumpcut_protected"))
        self._lbl_protected_hint.setText(tr("hint_jumpcut_protected"))
        self._pr_add_btn.setText(tr("btn_add_protected_range"))
        for _s, _e, _rw, rm_btn, ss_btn, se_btn in self._pr_rows:
            rm_btn.setToolTip(tr("tip_trim_remove_segment"))
            if ss_btn is not None:
                ss_btn.setText(tr("btn_set_start_seg"))
            if se_btn is not None:
                se_btn.setText(tr("btn_set_end_seg"))
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

        protected, errors = self._pr_collect_ranges()
        if errors:
            self.status_message.emit(
                tr("err_jumpcut_protected").format(line=errors[0][:60]), True
            )
            return

        if _MULTIMEDIA_AVAILABLE and hasattr(self, "_player"):
            self._player.pause()

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
