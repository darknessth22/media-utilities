"""Presenter zoom and draw, like Microsoft's ZoomIt — with a real toolbar.

Freezes the desktop, then lets you zoom into it and draw on it while you talk
through something on screen. Same frozen-snapshot, all-monitors approach as
``RegionSelector``, and for the same reason: the overlay must never take a
system-wide input grab (see that module).

The view is STILL unless you move it. ZoomIt pans whenever the mouse moves,
which makes drawing on a zoomed view fight the pen — every stroke drags the
page with it. Here zoom is anchored where you scroll, and panning is a
deliberate act: the hand tool, the middle button, or Space + drag.

Strokes are stored in DESKTOP coordinates, not screen coordinates, so a circle
drawn around a button stays around that button when you zoom or pan.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QByteArray, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor, QCursor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton,
    QSlider, QWidget,
)

from core.i18n import tr

MIN_ZOOM = 1.0
MAX_ZOOM = 8.0
START_ZOOM = 2.0            # ZoomIt's default: opening zoomed is the point
# Per wheel "click" (120 units) this is ~1.2x. Scaled by the actual delta, so a
# touchpad's many small deltas zoom smoothly instead of in jarring steps.
_WHEEL_BASE = 1.0015
_KEY_ZOOM_STEP = 1.25

COLOURS: tuple[tuple[Qt.Key, str], ...] = (
    (Qt.Key.Key_R, "#EF4444"),
    (Qt.Key.Key_G, "#22C55E"),
    (Qt.Key.Key_B, "#3B82F6"),
    (Qt.Key.Key_O, "#F97316"),
    (Qt.Key.Key_Y, "#FACC15"),
    (Qt.Key.Key_P, "#EC4899"),
    (Qt.Key.Key_W, "#FFFFFF"),
    (Qt.Key.Key_K, "#111111"),
)
_MIN_WIDTH, _MAX_WIDTH = 1, 30
_ERASER_RADIUS = 14         # screen px
_HISTORY_LIMIT = 100

# Lucide icons (ISC licence), inlined so the overlay needs no asset files.
_ICONS = {
    "pen": '<path d="M17 3a2.85 2.85 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>',
    "pan": ('<polyline points="5 9 2 12 5 15"/><polyline points="9 5 12 2 15 5"/>'
            '<polyline points="15 19 12 22 9 19"/><polyline points="19 9 22 12 19 15"/>'
            '<line x1="2" x2="22" y1="12" y2="12"/><line x1="12" x2="12" y1="2" y2="22"/>'),
    "eraser": ('<path d="m7 21-4.3-4.3c-1-1-1-2.5 0-3.4l9.6-9.6c1-1 2.5-1 3.4 0l5.6 '
               '5.6c1 1 1 2.5 0 3.4L13 21"/><path d="M22 21H7"/><path d="m5 11 9 9"/>'),
    "undo": '<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>',
    "clear": ('<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>'
              '<path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>'),
    "zoom_out": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/><path d="M8 11h6"/>',
    "zoom_in": ('<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>'
                '<path d="M11 8v6"/><path d="M8 11h6"/>'),
    "close": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
}

_TOOLBAR_QSS = """
QFrame#ZoomToolbar {
    background-color: rgba(17, 24, 39, 235);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 12px;
}
QPushButton#ZoomTool {
    background: transparent; border: none; border-radius: 8px;
    min-width: 34px; min-height: 34px; max-width: 34px; max-height: 34px;
}
QPushButton#ZoomTool:hover { background-color: rgba(255, 255, 255, 25); }
QPushButton#ZoomTool:checked { background-color: rgba(59, 130, 246, 170); }
QPushButton#ZoomTool:disabled { background: transparent; }
QFrame#ZoomDivider { background-color: rgba(255, 255, 255, 35); }
QLabel#ZoomLevel { color: #E6EDF3; font-size: 12px; font-weight: bold; }
QSlider::groove:horizontal {
    height: 4px; background: rgba(255, 255, 255, 50); border-radius: 2px;
}
QSlider::sub-page:horizontal { background: #3B82F6; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 14px; height: 14px; margin: -5px 0;
    background: #FFFFFF; border-radius: 7px;
}
"""


def _icon(name: str, colour: str = "#E6EDF3", size: int = 18) -> QIcon:
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{colour}" stroke-width="2" stroke-linecap="round" '
           f'stroke-linejoin="round">{_ICONS[name]}</svg>')
    scale = 2                           # crisp on high-DPI screens
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return QIcon(pixmap)


def visible_origin(cursor: QPointF, origin: QPointF, zoom: float) -> QPointF:
    """Top-left of a view that keeps the desktop point under *cursor* put.

    With the view at the desktop origin, the point under the pointer is the
    pointer itself; this is the view that keeps it there at *zoom*.
    """
    return cursor - (cursor - origin) / zoom


def _segment_distance(p: QPointF, a: QPointF, b: QPointF) -> float:
    """Distance from *p* to the segment a–b."""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(p.x() - a.x(), p.y() - a.y())
    t = max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / length_sq))
    return math.hypot(p.x() - (a.x() + t * dx), p.y() - (a.y() + t * dy))


class _SizeDot(QWidget):
    """Live preview of the brush: its real size, in its real colour."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(34, 34)
        self.colour = QColor("#EF4444")
        self.width_px = 4

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = max(2.0, min(30.0, float(self.width_px)))
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1))
        painter.setBrush(self.colour)
        painter.drawEllipse(QRectF((34 - d) / 2, (34 - d) / 2, d, d))
        painter.end()


class ScreenZoom(QWidget):
    """Frozen, zoomable, drawable copy of every screen."""

    closed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setMouseTracking(True)

        region, self._scale, self._desktop = self._capture()
        self._region = region
        self.setGeometry(region)
        origin = QPointF(region.topLeft())

        self._cursor = QPointF(QCursor.pos())
        self._zoom = START_ZOOM
        self._view = self._clamp(visible_origin(self._cursor, origin, START_ZOOM),
                                 START_ZOOM)

        self._tool = "pen"
        self._space_pan = False
        self._pan_from: tuple[QPointF, QPointF] | None = None   # (cursor, view)
        self._erasing = False

        self._colour = QColor(COLOURS[0][1])
        self._width = 4
        self._strokes: list[tuple[QColor, float, list[QPointF]]] = []
        self._current: list[QPointF] | None = None
        self._history: list[list] = []

        self._build_toolbar()
        self._sync_cursor()

    # ── Capture ──────────────────────────────────────────────────────────────

    @staticmethod
    def _capture() -> tuple[QRect, float, QImage]:
        """One image of the whole desktop, at the sharpest screen's density.

        Screen geometry is in logical pixels but grabs are physical, so on a
        150 % display a logical-size composite would already be blurry before
        any zoom — and zoom is the whole point.
        """
        app = QApplication.instance()
        shots = []
        region = None
        scale = 1.0
        for screen in app.screens():
            geo = screen.geometry()
            shot = screen.grabWindow(0)
            if not shot.isNull():
                shots.append((geo, shot.toImage()))
                scale = max(scale, shot.devicePixelRatio())
            region = geo if region is None else region.united(geo)
        if region is None:
            region = QRect(0, 0, 1, 1)

        desktop = QImage(int(region.width() * scale), int(region.height() * scale),
                         QImage.Format.Format_RGB32)
        desktop.fill(QColor(0, 0, 0))
        painter = QPainter(desktop)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for geo, image in shots:
            local = geo.translated(-region.topLeft())
            painter.drawImage(QRectF(local.x() * scale, local.y() * scale,
                                     local.width() * scale, local.height() * scale),
                              image)
        painter.end()
        return region, scale, desktop

    # ── Toolbar ──────────────────────────────────────────────────────────────

    def _tool_button(self, icon: str, tip: str, checkable: bool = False) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("ZoomTool")
        btn.setIcon(_icon(icon))
        btn.setIconSize(QSize(18, 18))
        btn.setToolTip(tip)
        btn.setCheckable(checkable)
        # Keys must keep reaching the overlay, or R/G/B and Esc stop working
        # the moment a toolbar button is clicked.
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setObjectName("ZoomDivider")
        line.setFixedSize(1, 24)
        return line

    def _build_toolbar(self) -> None:
        bar = QFrame(self)
        bar.setObjectName("ZoomToolbar")
        bar.setStyleSheet(_TOOLBAR_QSS)
        bar.setCursor(Qt.CursorShape.ArrowCursor)
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(4)

        # Tools — exclusive, like any paint program.
        self._tool_group = QButtonGroup(bar)
        self._tool_buttons: dict[str, QPushButton] = {}
        for name, tip in (("pen", tr("zoom_tool_pen")),
                          ("pan", tr("zoom_tool_pan")),
                          ("eraser", tr("zoom_tool_eraser"))):
            btn = self._tool_button(name, tip, checkable=True)
            btn.clicked.connect(lambda _c=False, n=name: self.set_tool(n))
            self._tool_group.addButton(btn)
            self._tool_buttons[name] = btn
            row.addWidget(btn)
        self._tool_buttons["pen"].setChecked(True)
        row.addWidget(self._divider())

        # Colours — each swatch IS its colour; the chosen one gets a ring.
        self._swatches: dict[str, QPushButton] = {}
        swatch_group = QButtonGroup(bar)
        for key, hex_code in COLOURS:
            sw = QPushButton()
            sw.setCheckable(True)
            sw.setFixedSize(24, 24)
            sw.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            sw.setCursor(Qt.CursorShape.PointingHandCursor)
            sw.setToolTip(f"{tr('zoom_colour')}  ({_key_name(key)})")
            sw.setStyleSheet(
                f"QPushButton {{ background-color: {hex_code}; border-radius: 12px;"
                f" border: 2px solid rgba(255,255,255,40); }}"
                f"QPushButton:checked {{ border: 3px solid #FFFFFF; }}")
            sw.clicked.connect(lambda _c=False, h=hex_code: self.set_colour(QColor(h)))
            swatch_group.addButton(sw)
            self._swatches[hex_code.upper()] = sw
            row.addWidget(sw)
        self._swatches[COLOURS[0][1].upper()].setChecked(True)
        row.addWidget(self._divider())

        # Brush size — a slider with a dot that shows the actual stroke.
        self._size_dot = _SizeDot()
        self._size_dot.setToolTip(tr("zoom_size"))
        row.addWidget(self._size_dot)
        self._size_slider = QSlider(Qt.Orientation.Horizontal)
        self._size_slider.setRange(_MIN_WIDTH, _MAX_WIDTH)
        self._size_slider.setValue(self._width)
        self._size_slider.setFixedWidth(96)
        self._size_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._size_slider.setToolTip(tr("zoom_size"))
        self._size_slider.valueChanged.connect(self.set_width)
        row.addWidget(self._size_slider)
        row.addWidget(self._divider())

        undo = self._tool_button("undo", tr("zoom_undo"))
        undo.clicked.connect(self.undo)
        row.addWidget(undo)
        clear = self._tool_button("clear", tr("zoom_clear"))
        clear.clicked.connect(self.clear)
        row.addWidget(clear)
        row.addWidget(self._divider())

        out_btn = self._tool_button("zoom_out", tr("zoom_out"))
        out_btn.clicked.connect(lambda: self.zoom_by(1 / _KEY_ZOOM_STEP, self._screen_centre()))
        row.addWidget(out_btn)
        self._zoom_label = QLabel()
        self._zoom_label.setObjectName("ZoomLevel")
        self._zoom_label.setFixedWidth(44)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self._zoom_label)
        in_btn = self._tool_button("zoom_in", tr("zoom_in"))
        in_btn.clicked.connect(lambda: self.zoom_by(_KEY_ZOOM_STEP, self._screen_centre()))
        row.addWidget(in_btn)
        row.addWidget(self._divider())

        close = self._tool_button("close", tr("zoom_close"))
        close.clicked.connect(self.close)
        row.addWidget(close)

        self._toolbar = bar
        self._update_zoom_label()
        self._undo_btn = undo
        self._sync_undo()
        bar.adjustSize()

        # Top-centre of the screen the pointer is on — where the presenter is.
        screen = (QApplication.screenAt(self._cursor.toPoint())
                  or QApplication.primaryScreen())
        geo = screen.geometry().translated(-self._region.topLeft())
        bar.move(geo.center().x() - bar.width() // 2, geo.top() + 16)

    def _screen_centre(self) -> QPointF:
        """Zoom anchor for the toolbar buttons: the middle of this screen."""
        screen = (QApplication.screenAt(self._toolbar.mapToGlobal(
            self._toolbar.rect().center())) or QApplication.primaryScreen())
        return QPointF(screen.geometry().center())

    # ── Public controls ──────────────────────────────────────────────────────

    def set_tool(self, name: str) -> None:
        self._tool = name
        btn = self._tool_buttons.get(name)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
        self._sync_cursor()
        self.update()

    def set_colour(self, colour: QColor) -> None:
        self._colour = QColor(colour)
        sw = self._swatches.get(colour.name().upper())
        if sw is not None and not sw.isChecked():
            sw.setChecked(True)
        self._size_dot.colour = self._colour
        self._size_dot.update()
        if self._tool != "pen":
            self.set_tool("pen")        # picking a colour means you want to draw
        self.update()

    def set_width(self, width: int) -> None:
        self._width = max(_MIN_WIDTH, min(_MAX_WIDTH, int(width)))
        if self._size_slider.value() != self._width:
            self._size_slider.blockSignals(True)
            self._size_slider.setValue(self._width)
            self._size_slider.blockSignals(False)
        self._size_dot.width_px = self._width
        self._size_dot.update()
        self.update()

    def undo(self) -> None:
        if self._history:
            self._strokes = self._history.pop()
            self._sync_undo()
            self.update()

    def clear(self) -> None:
        if self._strokes:
            self._remember()            # so a mis-click on Clear is undoable
            self._strokes = []
            self.update()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        # show() + explicit geometry, not showFullScreen(), which means ONE
        # screen. And NO grabMouse()/grabKeyboard(): see RegionSelector.
        self.show()
        self.setGeometry(self._region)
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.update()

    def closeEvent(self, event) -> None:
        try:
            self.releaseMouse()
            self.releaseKeyboard()
        except Exception:
            pass
        super().closeEvent(event)
        self.closed.emit()

    # ── View transform ───────────────────────────────────────────────────────

    def _clamp(self, view: QPointF, zoom: float) -> QPointF:
        """Keep the visible slice inside the desktop — no panning into black."""
        o = QPointF(self._region.topLeft())
        max_x = o.x() + self._region.width() * (1 - 1 / zoom)
        max_y = o.y() + self._region.height() * (1 - 1 / zoom)
        return QPointF(min(max(view.x(), o.x()), max_x),
                       min(max(view.y(), o.y()), max_y))

    def to_desktop(self, screen_pt: QPointF) -> QPointF:
        """Screen (global) point -> the desktop point drawn there."""
        return self._view + (screen_pt - QPointF(self._region.topLeft())) / self._zoom

    def zoom_by(self, factor: float, anchor: QPointF | None = None) -> None:
        """Zoom keeping the desktop point under *anchor* exactly where it is."""
        self.set_zoom(self._zoom * factor, anchor)

    def set_zoom(self, zoom: float, anchor: QPointF | None = None) -> None:
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        anchor = self._cursor if anchor is None else anchor
        fixed = self.to_desktop(anchor)
        o = QPointF(self._region.topLeft())
        self._zoom = zoom
        self._view = self._clamp(fixed - (anchor - o) / zoom, zoom)
        self._update_zoom_label()
        self.update()

    def pan_by(self, screen_delta: QPointF) -> None:
        """Move the view by a screen-space drag (content follows the hand)."""
        self._view = self._clamp(self._view - screen_delta / self._zoom, self._zoom)
        self.update()

    def _update_zoom_label(self) -> None:
        self._zoom_label.setText(f"{self._zoom:.1f}×")

    # ── Strokes ──────────────────────────────────────────────────────────────

    def _remember(self) -> None:
        self._history.append(list(self._strokes))
        del self._history[:-_HISTORY_LIMIT]
        self._sync_undo()

    def _sync_undo(self) -> None:
        if hasattr(self, "_undo_btn"):
            self._undo_btn.setEnabled(bool(self._history))

    def _erase_at(self, screen_pt: QPointF) -> None:
        """Remove every stroke the eraser touches. Whole strokes, not pixels."""
        centre = self.to_desktop(screen_pt)
        radius = _ERASER_RADIUS / self._zoom
        keep = []
        for stroke in self._strokes:
            _colour, width, points = stroke
            reach = radius + width / 2
            hit = any(_segment_distance(centre, a, b) <= reach
                      for a, b in zip(points, points[1:]))
            if not hit:
                keep.append(stroke)
        if len(keep) != len(self._strokes):
            if not self._erasing:
                self._remember()        # one undo step per eraser drag
                self._erasing = True
            self._strokes = keep

    # ── Events ───────────────────────────────────────────────────────────────

    def _panning_tool(self) -> bool:
        return self._tool == "pan" or self._space_pan

    def _sync_cursor(self) -> None:
        if self._pan_from is not None:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif self._panning_tool():
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif self._tool == "eraser":
            self.setCursor(Qt.CursorShape.BlankCursor)     # the ring is drawn
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def wheelEvent(self, event) -> None:
        if self._current is not None:
            return                      # no zooming mid-stroke
        delta = event.angleDelta().y()
        if delta:
            self.zoom_by(_WHEEL_BASE ** delta, event.globalPosition())

    def mousePressEvent(self, event) -> None:
        pos = event.globalPosition()
        self._cursor = pos
        button = event.button()
        if button == Qt.MouseButton.RightButton:
            self.close()
            return
        if button == Qt.MouseButton.MiddleButton or (
                button == Qt.MouseButton.LeftButton and self._panning_tool()):
            self._pan_from = (pos, QPointF(self._view))
            self._sync_cursor()
            return
        if button != Qt.MouseButton.LeftButton:
            return
        if self._tool == "eraser":
            self._erasing = False
            self._erase_at(pos)
        else:
            self._current = [self.to_desktop(pos)]
        self.update()

    def mouseMoveEvent(self, event) -> None:
        pos = event.globalPosition()
        self._cursor = pos
        if self._pan_from is not None:
            start, view = self._pan_from
            self._view = self._clamp(view - (pos - start) / self._zoom, self._zoom)
        elif self._current is not None:
            self._current.append(self.to_desktop(pos))
        elif self._tool == "eraser" and event.buttons() & Qt.MouseButton.LeftButton:
            self._erase_at(pos)
        # Nothing else moves the view — that is the whole point.
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._pan_from is not None and event.button() in (
                Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._pan_from = None
            self._sync_cursor()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._current is not None:
            if len(self._current) > 1:
                self._remember()
                self._strokes.append((QColor(self._colour), float(self._width),
                                      self._current))
            self._current = None
        self._erasing = False
        self.update()

    def leaveEvent(self, event) -> None:
        self.update()                   # hide the brush ring over the toolbar
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if key == Qt.Key.Key_Space:
            if not event.isAutoRepeat():
                self._space_pan = True
                self._sync_cursor()
            return
        if key == Qt.Key.Key_Escape:
            self.close()
            return
        if ctrl and key == Qt.Key.Key_Z:
            self.undo()
            return
        colour = dict(COLOURS).get(key)
        if colour is not None and not ctrl:
            self.set_colour(QColor(colour))
        elif key == Qt.Key.Key_D:
            self.set_tool("pen")
        elif key == Qt.Key.Key_H:
            self.set_tool("pan")
        elif key == Qt.Key.Key_E:
            self.set_tool("eraser")
        elif key == Qt.Key.Key_C:
            self.clear()
        elif key == Qt.Key.Key_BracketRight:
            self.set_width(self._width + 2)
        elif key == Qt.Key.Key_BracketLeft:
            self.set_width(self._width - 2)
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom_by(_KEY_ZOOM_STEP)
        elif key == Qt.Key.Key_Minus:
            self.zoom_by(1 / _KEY_ZOOM_STEP)
        elif key == Qt.Key.Key_0:
            self.set_zoom(MIN_ZOOM)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pan = False
            self._sync_cursor()
            return
        super().keyReleaseEvent(event)

    # ── Painting ─────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        o = QPointF(self._region.topLeft())
        view = self._view - o
        s = self._scale
        source = QRectF(view.x() * s, view.y() * s,
                        self._region.width() / self._zoom * s,
                        self._region.height() / self._zoom * s)
        painter.drawImage(QRectF(self.rect()), self._desktop, source)

        # Strokes live in desktop coordinates; map them with the same transform
        # as the image so they stay pinned to what they mark.
        painter.save()
        painter.scale(self._zoom, self._zoom)
        painter.translate(-view)
        for colour, width, points in self._strokes:
            self._draw_stroke(painter, colour, width, points, o)
        if self._current:
            self._draw_stroke(painter, self._colour, self._width, self._current, o)
        painter.restore()

        self._draw_brush_preview(painter)
        painter.end()

    @staticmethod
    def _draw_stroke(painter, colour, width, points, origin) -> None:
        pen = QPen(colour, width, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        path = QPainterPath(points[0] - origin)
        for pt in points[1:]:
            path.lineTo(pt - origin)
        painter.drawPath(path)

    def _draw_brush_preview(self, painter) -> None:
        """Ring at the pointer showing exactly what a stroke or erase covers."""
        if self._panning_tool() or self._pan_from is not None:
            return
        local = self._cursor - QPointF(self._region.topLeft())
        if self._toolbar.geometry().contains(local.toPoint()):
            return
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self._tool == "eraser":
            r = _ERASER_RADIUS
            painter.setPen(QPen(QColor(0, 0, 0, 160), 3))
            painter.drawEllipse(local, r, r)
            painter.setPen(QPen(QColor(255, 255, 255), 1.5))
            painter.drawEllipse(local, r, r)
            return
        # The stroke scales with the zoom, so the preview does too.
        r = max(2.0, self._width * self._zoom / 2)
        painter.setPen(QPen(QColor(0, 0, 0, 140), 1))
        painter.drawEllipse(local, r + 1, r + 1)
        painter.setPen(QPen(self._colour, 1.5))
        painter.drawEllipse(local, r, r)


def _key_name(key: Qt.Key) -> str:
    """The letter to press for a swatch, e.g. "R" for Qt.Key.Key_R."""
    from PySide6.QtGui import QKeySequence

    return QKeySequence(key).toString()
