"""Hex Palette Extractor + Color Wheel — palette analysis and interactive color picker."""
from __future__ import annotations

import math
import os
import tempfile

from PySide6.QtCore import Qt, QPoint, QTimer, QRectF, Signal
from PySide6.QtGui import (
    QColor, QConicalGradient, QLinearGradient,
    QPainter, QPainterPath, QPen, QBrush, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox,
    QStackedWidget, QSlider, QVBoxLayout, QWidget,
)

from core.i18n import tr
from core.palette_extractor import extract_palette, ALL_EXTS, IMAGE_EXTS, VIDEO_EXTS
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker

try:
    from PySide6.QtCore import QUrl
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    _MM = True
except ImportError:
    _MM = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ms_to_ts(ms: int) -> str:
    total_s, frac = divmod(max(0, ms), 1000)
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{frac:03d}"


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


# ── Clickable color swatch ────────────────────────────────────────────────────

class _Swatch(QFrame):
    """Color swatch — click copies hex to clipboard, tooltip shows hex."""

    def __init__(self, hex_color: str, parent=None) -> None:
        super().__init__(parent)
        self._hex = hex_color
        self.setFixedSize(76, 92)
        self.setObjectName("Card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Click to copy {hex_color}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        block = QFrame()
        block.setFixedHeight(52)
        block.setStyleSheet(
            f"background-color: {hex_color}; border-radius: 5px; border: none;"
        )
        layout.addWidget(block)

        label = QLabel(hex_color)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 10px; font-family: monospace;")
        layout.addWidget(label)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            QApplication.clipboard().setText(self._hex)
            self.setToolTip(f"Copied!")
            QTimer.singleShot(1500, lambda: self.setToolTip(f"Click to copy {self._hex}"))
        super().mousePressEvent(event)


# ── Custom HSV color wheel ────────────────────────────────────────────────────

class ColorWheelWidget(QWidget):
    """Interactive HSV color wheel — hue ring + saturation/value square."""

    color_changed = Signal(QColor)

    _RING_W = 24          # ring thickness in px
    _INDICATOR_R = 7      # radius of the selection indicator circles

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(260, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._hue: float = 0.0      # 0 – 359
        self._sat: float = 1.0      # 0 – 1
        self._val: float = 1.0      # 0 – 1
        self._dragging: str | None = None   # "ring" | "square"

    # ── Geometry helpers ──────────────────────────────────────────────────────

    def _geom(self):
        side = min(self.width(), self.height())
        cx, cy = self.width() // 2, self.height() // 2
        outer_r = side // 2 - 8
        inner_r = outer_r - self._RING_W
        sq_half = int(inner_r * 0.68)   # inscribed square half-side
        sq_x = cx - sq_half
        sq_y = cy - sq_half
        sq_size = sq_half * 2
        return cx, cy, outer_r, inner_r, sq_x, sq_y, sq_size

    def _in_ring(self, px: int, py: int) -> bool:
        cx, cy, outer_r, inner_r, *_ = self._geom()
        d = math.hypot(px - cx, py - cy)
        return inner_r - 4 <= d <= outer_r + 4

    def _in_square(self, px: int, py: int) -> bool:
        _, _, _, _, sq_x, sq_y, sq_size = self._geom()
        return sq_x <= px <= sq_x + sq_size and sq_y <= py <= sq_y + sq_size

    def _hue_from_pos(self, px: int, py: int) -> float:
        cx, cy = self.width() // 2, self.height() // 2
        return math.degrees(math.atan2(py - cy, px - cx)) % 360

    def _sv_from_pos(self, px: int, py: int):
        _, _, _, _, sq_x, sq_y, sq_size = self._geom()
        s = max(0.0, min(1.0, (px - sq_x) / sq_size))
        v = max(0.0, min(1.0, 1.0 - (py - sq_y) / sq_size))
        return s, v

    # ── Public API ────────────────────────────────────────────────────────────

    def color(self) -> QColor:
        return QColor.fromHsvF(self._hue / 360.0, self._sat, self._val)

    def hex_color(self) -> str:
        c = self.color()
        return f"#{c.red():02X}{c.green():02X}{c.blue():02X}"

    def set_color(self, color: QColor) -> None:
        h, s, v, _ = color.getHsvF()
        self._hue = max(0.0, h * 360.0)
        self._sat = max(0.0, s)
        self._val = max(0.0, v)
        self.update()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        cx, cy, outer_r, inner_r, sq_x, sq_y, sq_size = self._geom()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── Hue ring via conical gradient ─────────────────────────────────
        grad = QConicalGradient(cx, cy, 0)
        for i in range(37):
            t = i / 36.0
            # gradient sweeps counterclockwise; flip hue to match atan2 clockwise
            hue = int((1.0 - t) * 360) % 360
            grad.setColorAt(t, QColor.fromHsv(hue, 255, 255))

        ring_path = QPainterPath()
        ring_path.addEllipse(QRectF(cx - outer_r, cy - outer_r, outer_r * 2, outer_r * 2))
        cut = QPainterPath()
        cut.addEllipse(QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2))
        ring_path -= cut

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPath(ring_path)

        # ── SV square ────────────────────────────────────────────────────
        hue_color = QColor.fromHsv(int(self._hue), 255, 255)

        # Pass 1: white → hue (left to right = saturation)
        sg = QLinearGradient(sq_x, sq_y, sq_x + sq_size, sq_y)
        sg.setColorAt(0.0, QColor(255, 255, 255))
        sg.setColorAt(1.0, hue_color)
        p.fillRect(sq_x, sq_y, sq_size, sq_size, sg)

        # Pass 2: transparent → black (top to bottom = value)
        vg = QLinearGradient(sq_x, sq_y, sq_x, sq_y + sq_size)
        vg.setColorAt(0.0, QColor(0, 0, 0, 0))
        vg.setColorAt(1.0, QColor(0, 0, 0, 255))
        p.fillRect(sq_x, sq_y, sq_size, sq_size, vg)

        # ── Hue ring indicator ────────────────────────────────────────────
        angle_rad = math.radians(self._hue)
        ind_r = outer_r - self._RING_W // 2
        ix = int(cx + ind_r * math.cos(angle_rad))
        iy = int(cy + ind_r * math.sin(angle_rad))
        p.setBrush(QColor.fromHsv(int(self._hue), 255, 255))
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawEllipse(QPoint(ix, iy), self._INDICATOR_R, self._INDICATOR_R)

        # ── SV square indicator ───────────────────────────────────────────
        svx = sq_x + int(self._sat * sq_size)
        svy = sq_y + int((1.0 - self._val) * sq_size)
        indicator_color = QColor(255, 255, 255) if self._val < 0.5 else QColor(0, 0, 0)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(indicator_color, 2))
        p.drawEllipse(QPoint(svx, svy), self._INDICATOR_R - 1, self._INDICATOR_R - 1)
        p.setPen(QPen(QColor(255, 255, 255) if self._val >= 0.5 else QColor(0, 0, 0), 1))
        p.drawEllipse(QPoint(svx, svy), self._INDICATOR_R + 1, self._INDICATOR_R + 1)

        p.end()

    # ── Mouse interaction ─────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        px, py = event.position().x(), event.position().y()
        if self._in_ring(int(px), int(py)):
            self._dragging = "ring"
            self._hue = self._hue_from_pos(int(px), int(py))
        elif self._in_square(int(px), int(py)):
            self._dragging = "square"
            self._sat, self._val = self._sv_from_pos(int(px), int(py))
        else:
            return
        self.update()
        self.color_changed.emit(self.color())

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            return
        px, py = int(event.position().x()), int(event.position().y())
        if self._dragging == "ring":
            self._hue = self._hue_from_pos(px, py)
        elif self._dragging == "square":
            self._sat, self._val = self._sv_from_pos(px, py)
        self.update()
        self.color_changed.emit(self.color())

    def mouseReleaseEvent(self, _event) -> None:
        self._dragging = None


# ── Main section ──────────────────────────────────────────────────────────────

class PaletteSection(QScrollArea):
    """Hex Palette Extractor with media preview + interactive Color Wheel tab."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._thumb_worker: Worker | None = None
        self._last_result_path: str | None = None
        self._current_tab: int = 0
        self._thumb_tmp: str | None = None
        self._hex_updating: bool = False
        self._duration_ms: int = 0
        self._scrubbing: bool = False
        self._frame_timestamp: str | None = None   # set by "Use this frame"; None = full video
        self._preview_placeholder_key: str | None = None

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_extract_page())
        self._stack.addWidget(self._build_wheel_page())

        # Outer wrapper so QScrollArea has a single child widget
        wrapper = QWidget()
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(self._stack)
        self.setWidget(wrapper)

        # Debounce timer for thumbnail preview (images only)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(400)
        self._preview_timer.timeout.connect(self._load_preview)

        if _MM:
            self._pos_timer = QTimer(self)
            self._pos_timer.setInterval(150)
            self._pos_timer.timeout.connect(self._update_position)

    # ── Tab routing ───────────────────────────────────────────────────────────

    def on_sub_tab_changed(self, tab_index: int) -> None:
        self._current_tab = tab_index
        self._stack.setCurrentIndex(tab_index)

    # ── Extract palette page ──────────────────────────────────────────────────

    def _build_extract_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_source_card())

        if _MM:
            self._player_card = self._build_player_card()
            self._player_card.setVisible(False)   # shown only when a video is loaded
            layout.addWidget(self._player_card)

        layout.addWidget(self._build_options_card())
        layout.addWidget(self._build_progress_card())

        self._swatches_card = self._build_swatches_card()
        layout.addWidget(self._swatches_card)
        return page

    # ── Source + preview card ─────────────────────────────────────────────────

    def _build_source_card(self) -> QFrame:
        card = _card()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)
        self._hdr_src = _section_header(tr("hdr_source_file"))
        outer.addWidget(self._hdr_src)

        self._hint_accepts = QLabel(tr("hint_accepts_img_vid"))
        self._hint_accepts.setObjectName("TextMuted")
        self._hint_accepts.setStyleSheet("font-size: 12px;")
        outer.addWidget(self._hint_accepts)

        body = QHBoxLayout()
        body.setSpacing(16)

        # Left: file input + browse
        left = QVBoxLayout()
        left.setSpacing(8)

        file_row = QHBoxLayout()
        self._file_input = QLineEdit()
        self._file_input.setObjectName("PillInput")
        self._file_input.setPlaceholderText(tr("ph_img_or_vid"))
        self._file_input.textChanged.connect(self._on_source_changed)
        file_row.addWidget(self._file_input)

        self._browse_src_btn = QPushButton(tr("btn_browse"))
        self._browse_src_btn.setObjectName("BrowseBtn")
        self._browse_src_btn.setFixedWidth(90)
        self._browse_src_btn.clicked.connect(self._browse_source)
        file_row.addWidget(self._browse_src_btn)
        left.addLayout(file_row)
        left.addStretch()
        body.addLayout(left, stretch=1)

        # Right: preview thumbnail
        self._preview_label = QLabel()
        self._preview_label.setFixedSize(200, 130)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setObjectName("Card")
        self._preview_label.setStyleSheet(
            "QLabel#Card { border-radius: 6px; background: #1C2128; color: #8B949E;"
            " font-size: 12px; }"
        )
        self._set_preview_placeholder("hint_palette_no_preview")
        body.addWidget(self._preview_label)

        outer.addLayout(body)
        return card

    # ── Video player card ─────────────────────────────────────────────────────

    def _build_player_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_player = _section_header(tr("hdr_palette_preview"))
        layout.addWidget(self._hdr_player)

        self._pal_video = QVideoWidget()
        self._pal_video.setObjectName("VideoWidget")
        self._pal_video.setMinimumHeight(240)
        self._pal_video.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self._pal_video)

        self._pal_audio = QAudioOutput()
        self._pal_audio.setVolume(0.0)

        self._pal_player = QMediaPlayer()
        self._pal_player.setVideoOutput(self._pal_video)
        self._pal_player.setAudioOutput(self._pal_audio)
        self._pal_player.durationChanged.connect(self._pal_on_duration)
        self._pal_player.playbackStateChanged.connect(self._pal_on_playback_state)
        self._pal_player.mediaStatusChanged.connect(self._pal_on_media_status)

        self._pal_scrubber = QSlider(Qt.Orientation.Horizontal)
        self._pal_scrubber.setObjectName("Scrubber")
        self._pal_scrubber.setRange(0, 1000)
        self._pal_scrubber.sliderPressed.connect(self._pal_scrub_press)
        self._pal_scrubber.sliderReleased.connect(self._pal_scrub_release)
        self._pal_scrubber.sliderMoved.connect(self._pal_scrub_moved)
        layout.addWidget(self._pal_scrubber)

        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        self._pal_play_btn = QPushButton("▶")
        self._pal_play_btn.setObjectName("SecondaryBtn")
        self._pal_play_btn.setFixedSize(42, 42)
        self._pal_play_btn.clicked.connect(self._pal_toggle_play)
        ctrl.addWidget(self._pal_play_btn)

        self._pal_time_lbl = QLabel("00:00:00.000 / 00:00:00.000")
        self._pal_time_lbl.setObjectName("TextSecondary")
        self._pal_time_lbl.setStyleSheet("font-family: monospace; font-size: 13px;")
        ctrl.addWidget(self._pal_time_lbl)

        ctrl.addStretch()

        self._pal_use_btn = QPushButton(tr("btn_use_this_frame"))
        self._pal_use_btn.setObjectName("BrowseBtn")
        self._pal_use_btn.setFixedHeight(42)
        self._pal_use_btn.setToolTip(tr("hint_palette_use_frame_tooltip"))
        self._pal_use_btn.clicked.connect(self._pal_stamp_frame)
        self._pal_use_btn.setEnabled(False)
        ctrl.addWidget(self._pal_use_btn)

        self._pal_reset_btn = QPushButton(tr("btn_whole_video"))
        self._pal_reset_btn.setObjectName("BrowseBtn")
        self._pal_reset_btn.setFixedHeight(42)
        self._pal_reset_btn.setToolTip(tr("hint_palette_reset_tooltip"))
        self._pal_reset_btn.clicked.connect(self._pal_reset_frame)
        self._pal_reset_btn.setEnabled(False)
        ctrl.addWidget(self._pal_reset_btn)

        layout.addLayout(ctrl)

        self._pal_mode_lbl = QLabel(tr("hint_palette_mode_whole"))
        self._pal_mode_lbl.setObjectName("TextMuted")
        self._pal_mode_lbl.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._pal_mode_lbl)

        return card

    # ── Player event handlers ─────────────────────────────────────────────────

    def _pal_on_media_status(self, status) -> None:
        from PySide6.QtMultimedia import QMediaPlayer as _QMP
        if status == _QMP.MediaStatus.LoadedMedia:
            self._pal_player.play()
            QTimer.singleShot(80, self._pal_player.pause)

    def _pal_on_duration(self, ms: int) -> None:
        self._duration_ms = ms
        self._pal_scrubber.setRange(0, max(1, ms))
        self._pal_time_lbl.setText(f"00:00:00.000 / {_ms_to_ts(ms)}")
        self._pal_use_btn.setEnabled(True)
        self._pos_timer.start()

    def _pal_on_playback_state(self, state) -> None:
        from PySide6.QtMultimedia import QMediaPlayer as _QMP
        self._pal_play_btn.setText(
            "⏸" if state == _QMP.PlaybackState.PlayingState else "▶"
        )

    def _update_position(self) -> None:
        if self._scrubbing or not self._duration_ms:
            return
        pos = self._pal_player.position()
        self._pal_scrubber.setValue(pos)
        self._pal_time_lbl.setText(f"{_ms_to_ts(pos)} / {_ms_to_ts(self._duration_ms)}")

    def _pal_scrub_press(self) -> None:
        self._scrubbing = True

    def _pal_scrub_release(self) -> None:
        self._pal_player.setPosition(self._pal_scrubber.value())
        QTimer.singleShot(300, lambda: setattr(self, "_scrubbing", False))

    def _pal_scrub_moved(self, value: int) -> None:
        if self._duration_ms:
            self._pal_time_lbl.setText(f"{_ms_to_ts(value)} / {_ms_to_ts(self._duration_ms)}")

    def _pal_toggle_play(self) -> None:
        from PySide6.QtMultimedia import QMediaPlayer as _QMP
        if self._pal_player.playbackState() == _QMP.PlaybackState.PlayingState:
            self._pal_player.pause()
        else:
            self._pal_player.play()

    def _pal_stamp_frame(self) -> None:
        pos = self._pal_player.position()
        self._frame_timestamp = _ms_to_ts(pos)
        self._pal_reset_btn.setEnabled(True)
        self._pal_mode_lbl.setText(
            tr("hint_palette_mode_single").format(time=self._frame_timestamp)
        )

    def _pal_reset_frame(self) -> None:
        self._frame_timestamp = None
        self._pal_reset_btn.setEnabled(False)
        self._pal_mode_lbl.setText(tr("hint_palette_mode_whole"))

    # ── Options card ──────────────────────────────────────────────────────────

    def _build_options_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        self._hdr_opts = _section_header(tr("hdr_palette_opts"))
        layout.addWidget(self._hdr_opts)

        row = QHBoxLayout()
        col = QVBoxLayout()
        self._lbl_n_colors = QLabel(tr("lbl_n_colors"))
        col.addWidget(self._lbl_n_colors)
        self._num_colors = QSpinBox()
        self._num_colors.setRange(2, 128)
        self._num_colors.setValue(16)
        self._num_colors.setFixedWidth(90)
        col.addWidget(self._num_colors)
        row.addLayout(col)
        row.addStretch()
        layout.addLayout(row)

        self._palette_note = QLabel(tr("hint_palette_quantization"))
        self._palette_note.setObjectName("TextMuted")
        self._palette_note.setWordWrap(True)
        self._palette_note.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._palette_note)
        return card

    # ── Output card ───────────────────────────────────────────────────────────

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
        return card

    # ── Swatches card (grid, click to copy) ──────────────────────────────────

    def _build_swatches_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        self._hdr_palette = _section_header(tr("hdr_extracted_palette"))
        header_row.addWidget(self._hdr_palette)
        header_row.addStretch()
        self._copy_all_btn = QPushButton(tr("btn_copy_all"))
        self._copy_all_btn.setObjectName("BrowseBtn")
        self._copy_all_btn.setFixedWidth(80)
        self._copy_all_btn.clicked.connect(self._copy_all_hex)
        header_row.addWidget(self._copy_all_btn)
        layout.addLayout(header_row)

        # Grid container widget (rebuilt after each extraction)
        self._grid_widget = QWidget()
        self._swatches_grid = QGridLayout(self._grid_widget)
        self._swatches_grid.setSpacing(8)
        self._swatches_grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._grid_widget)

        card.setVisible(False)
        return card

    # ── Color wheel page ──────────────────────────────────────────────────────

    def _build_wheel_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        card = _card()
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(24)

        # Left: color wheel widget
        self._wheel = ColorWheelWidget()
        self._wheel.setFixedSize(280, 280)
        self._wheel.color_changed.connect(self._on_wheel_color_changed)
        card_layout.addWidget(self._wheel, alignment=Qt.AlignmentFlag.AlignTop)

        # Right: color info panel
        info = QVBoxLayout()
        info.setSpacing(12)
        info.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._hdr_sel = _section_header(tr("hdr_selected_color"))
        info.addWidget(self._hdr_sel)

        # Preview swatch
        self._wheel_preview = QFrame()
        self._wheel_preview.setFixedSize(150, 70)
        self._wheel_preview.setStyleSheet(
            "background: #FF0000; border-radius: 8px; border: none;"
        )
        info.addWidget(self._wheel_preview)

        # Hex input
        self._wheel_hex_lbl = QLabel(tr("lbl_hex_code"))
        self._wheel_hex_lbl.setObjectName("TextMuted")
        self._wheel_hex_lbl.setStyleSheet("font-size: 11px;")
        info.addWidget(self._wheel_hex_lbl)

        self._wheel_hex = QLineEdit("#FF0000")
        self._wheel_hex.setObjectName("PillInput")
        self._wheel_hex.setMaximumWidth(150)
        self._wheel_hex.setPlaceholderText(tr("ph_wheel_hex"))
        self._wheel_hex.textChanged.connect(self._on_hex_typed)
        info.addWidget(self._wheel_hex)

        self._wheel_copy_btn = QPushButton(tr("btn_copy_hex"))
        self._wheel_copy_btn.setObjectName("BrowseBtn")
        self._wheel_copy_btn.setFixedWidth(100)
        self._wheel_copy_btn.clicked.connect(self._copy_wheel_hex)
        info.addWidget(self._wheel_copy_btn)

        # HSV readout
        self._wheel_hsv_lbl = QLabel("H: 0°   S: 100%   V: 100%")
        self._wheel_hsv_lbl.setObjectName("TextMuted")
        self._wheel_hsv_lbl.setStyleSheet("font-size: 12px; font-family: monospace;")
        info.addWidget(self._wheel_hsv_lbl)

        # RGB readout
        self._wheel_rgb_lbl = QLabel("R: 255   G: 0   B: 0")
        self._wheel_rgb_lbl.setObjectName("TextMuted")
        self._wheel_rgb_lbl.setStyleSheet("font-size: 12px; font-family: monospace;")
        info.addWidget(self._wheel_rgb_lbl)

        info.addStretch()
        card_layout.addLayout(info)
        layout.addWidget(card)
        layout.addStretch()
        return page

    # ── Preview loading ───────────────────────────────────────────────────────

    def _set_preview_placeholder(self, key: str) -> None:
        self._preview_placeholder_key = key
        self._preview_label.setPixmap(QPixmap())
        self._preview_label.setText(tr(key))

    def retranslate_ui(self) -> None:
        self._hdr_src.setText(tr("hdr_source_file"))
        self._hint_accepts.setText(tr("hint_accepts_img_vid"))
        self._file_input.setPlaceholderText(tr("ph_img_or_vid"))
        self._browse_src_btn.setText(tr("btn_browse"))
        if self._preview_placeholder_key:
            self._preview_label.setText(tr(self._preview_placeholder_key))
        self._hdr_opts.setText(tr("hdr_palette_opts"))
        self._lbl_n_colors.setText(tr("lbl_n_colors"))
        self._palette_note.setText(tr("hint_palette_quantization"))
        self._hdr_palette.setText(tr("hdr_extracted_palette"))
        self._hdr_sel.setText(tr("hdr_selected_color"))
        self._copy_all_btn.setText(tr("btn_copy_all"))
        self._wheel_hex_lbl.setText(tr("lbl_hex_code"))
        self._wheel_hex.setPlaceholderText(tr("ph_wheel_hex"))
        self._wheel_copy_btn.setText(tr("btn_copy_hex"))
        if _MM and hasattr(self, "_hdr_player"):
            self._hdr_player.setText(tr("hdr_palette_preview"))
            self._pal_use_btn.setText(tr("btn_use_this_frame"))
            self._pal_use_btn.setToolTip(tr("hint_palette_use_frame_tooltip"))
            self._pal_reset_btn.setText(tr("btn_whole_video"))
            self._pal_reset_btn.setToolTip(tr("hint_palette_reset_tooltip"))
            if self._frame_timestamp:
                self._pal_mode_lbl.setText(
                    tr("hint_palette_mode_single").format(time=self._frame_timestamp)
                )
            else:
                self._pal_mode_lbl.setText(tr("hint_palette_mode_whole"))

    def _on_source_changed(self, path: str) -> None:
        path = path.strip()
        ext = os.path.splitext(path)[1].lower()
        is_video = ext in VIDEO_EXTS and os.path.isfile(path)

        if _MM and hasattr(self, "_player_card"):
            self._player_card.setVisible(is_video)
            if is_video:
                self._pal_player.stop()
                self._pal_player.setSource(QUrl.fromLocalFile(path))
                # Reset frame selection when a new file is loaded
                self._frame_timestamp = None
                self._pal_reset_btn.setEnabled(False)
                self._pal_mode_lbl.setText(tr("hint_palette_mode_whole"))
            else:
                self._pal_player.stop()
                self._pos_timer.stop()
                self._duration_ms = 0

        # Still trigger image thumbnail preview
        self._preview_timer.start()

    def _load_preview(self) -> None:
        path = self._file_input.text().strip()
        if not path or not os.path.isfile(path):
            self._set_preview_placeholder("hint_palette_no_preview")
            return

        ext = os.path.splitext(path)[1].lower()
        if ext in IMAGE_EXTS:
            px = QPixmap(path)
            if not px.isNull():
                self._preview_placeholder_key = None
                self._preview_label.setPixmap(
                    px.scaled(200, 130, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
                )
                self._preview_label.setText("")
            else:
                self._set_preview_placeholder("err_palette_bad_image")
        elif ext in VIDEO_EXTS:
            self._set_preview_placeholder("dyn_loading")
            self._start_thumb_grab(path)

    def _start_thumb_grab(self, video_path: str) -> None:
        if self._thumb_worker and self._thumb_worker.isRunning():
            self._thumb_worker.cancel()

        tmp_dir = tempfile.mkdtemp(prefix="videl_thumb_")
        self._thumb_tmp = tmp_dir

        from core.frame_grabber import grab_frame
        self._thumb_worker = Worker(grab_frame, video_path, "00:00:01", "png", tmp_dir)
        self._thumb_worker.signals.result.connect(self._on_thumb_done)
        self._thumb_worker.signals.error.connect(
            lambda _: self._set_preview_placeholder("hint_palette_no_preview")
        )
        self._thumb_worker.start()

    def _on_thumb_done(self, result: dict) -> None:
        if result.get("success") and os.path.isfile(result["file_path"]):
            px = QPixmap(result["file_path"])
            if not px.isNull():
                self._preview_placeholder_key = None
                self._preview_label.setPixmap(
                    px.scaled(200, 130, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
                )
                self._preview_label.setText("")
                return
        self._set_preview_placeholder("hint_palette_no_preview")

    # ── Browse helpers ────────────────────────────────────────────────────────

    def _browse_source(self) -> None:
        ext_filter = "Media files (" + " ".join(f"*{e}" for e in sorted(ALL_EXTS)) + ")"
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image or Video", os.path.expanduser("~"), ext_filter
        )
        if path:
            self._file_input.setText(path)

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
        if self._current_tab == 1:
            self._copy_wheel_hex()
            return

        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        input_path = self._file_input.text().strip()
        if not input_path or not os.path.isfile(input_path):
            self.status_message.emit("Select a valid image or video file.", True)
            return

        num_colors = self._num_colors.value()

        self._swatches_card.setVisible(False)
        self._set_busy(True, "Analyzing colors with FFmpeg palettegen…")

        self._worker = Worker(extract_palette, input_path, num_colors, self._frame_timestamp)
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

        if not result["success"]:
            self.status_message.emit(f"Failed: {result['error']}", True)
            return

        hex_codes: list[str] = result["hex_codes"]
        self._current_hex_codes = hex_codes

        # Rebuild grid (8 columns)
        while self._swatches_grid.count():
            item = self._swatches_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cols = 8
        for i, hx in enumerate(hex_codes):
            self._swatches_grid.addWidget(_Swatch(hx), i // cols, i % cols)

        if not hex_codes:
            no_lbl = QLabel(
                "Pillow not installed — hex codes unavailable.\n"
                "pip install Pillow"
            )
            no_lbl.setObjectName("TextMuted")
            self._swatches_grid.addWidget(no_lbl, 0, 0)

        self._swatches_card.setVisible(True)

        get_history_manager().add_item(HistoryItem(
            task_type="palette_extract",
            file_name=os.path.basename(self._file_input.text()),
            file_path=self._file_input.text(),
            status="success",
        ))

        n = len(hex_codes)
        self.status_message.emit(f"Done → {n} color{'s' if n != 1 else ''} extracted.", False)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)

    # ── Copy helpers ──────────────────────────────────────────────────────────

    def _copy_all_hex(self) -> None:
        codes = getattr(self, "_current_hex_codes", [])
        if codes:
            QApplication.clipboard().setText("\n".join(codes))
            self.status_message.emit(f"Copied {len(codes)} hex codes.", False)

    def _copy_wheel_hex(self) -> None:
        hx = self._wheel.hex_color()
        QApplication.clipboard().setText(hx)
        self.status_message.emit(f"Copied {hx}", False)

    # ── Color wheel sync ──────────────────────────────────────────────────────

    def _on_wheel_color_changed(self, color: QColor) -> None:
        hx = f"#{color.red():02X}{color.green():02X}{color.blue():02X}"
        h, s, v, _ = color.getHsv()

        self._wheel_preview.setStyleSheet(
            f"background: {hx}; border-radius: 8px; border: none;"
        )
        self._wheel_hsv_lbl.setText(f"H: {h}°   S: {int(s/255*100)}%   V: {int(v/255*100)}%")
        self._wheel_rgb_lbl.setText(f"R: {color.red()}   G: {color.green()}   B: {color.blue()}")

        # Update hex input without triggering _on_hex_typed → loop
        if not self._hex_updating:
            self._hex_updating = True
            self._wheel_hex.setText(hx)
            self._hex_updating = False

    def _on_hex_typed(self, text: str) -> None:
        if self._hex_updating:
            return
        text = text.strip()
        if not text.startswith("#"):
            text = "#" + text
        color = QColor(text)
        if not color.isValid():
            return
        self._hex_updating = True
        self._wheel.set_color(color)
        self._hex_updating = False
        self._on_wheel_color_changed(color)
