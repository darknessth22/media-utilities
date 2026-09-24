"""Drag-a-rectangle overlay for grabbing part of the screen.

A sibling of ``ScreenColorPicker``: same frozen-snapshot approach and the same
multi-screen union, but the user drags a region instead of clicking a pixel.
Used by the screen OCR tool and the screen ruler.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget


class RegionSelector(QWidget):
    """Select a screen rectangle. Emits ``selected(QRect, QImage)``.

    The QRect is in GLOBAL screen coordinates; the QImage is that region of the
    desktop as it looked *before* the overlay appeared, so the dimming and the
    selection chrome are never captured.
    """

    selected = Signal(QRect, object)     # (global rect, QImage of that region)
    cancelled = Signal()

    _MIN_SIDE = 4        # px; smaller is a stray click, not a drag

    def __init__(self, hint: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self._hint = hint

        app = QApplication.instance()
        self._shots: list[tuple] = []
        region = None
        for screen in app.screens():
            geo = screen.geometry()
            shot = screen.grabWindow(0)
            if not shot.isNull():
                self._shots.append((geo, shot.toImage()))
            region = geo if region is None else region.united(geo)
        if region is None:
            region = QRect(0, 0, 1, 1)
        self._region = region
        self._origin = region.topLeft()
        self.setGeometry(region)

        self._start: QPoint | None = None
        self._cursor = QCursor.pos()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        # show() + explicit geometry, NOT showFullScreen(): "full screen" means
        # ONE screen, which crops the overlay on a multi-monitor desktop and
        # leaves no widget under the cursor elsewhere.
        self.show()
        self.setGeometry(self._region)
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        # NO grabMouse()/grabKeyboard(). An input grab is system-wide, and if
        # anything throws between the grab and the release — or the window is
        # closed by another route — the whole desktop stops responding to the
        # mouse and keyboard. The overlay is frameless, always-on-top and
        # covers every screen, so it already receives the events it needs
        # without taking input away from the rest of the system.
        self._cursor = QCursor.pos()
        self.update()

    def _finish(self) -> None:
        # Defensive: release any grab that an older build (or a subclass) may
        # have taken, so a stale grab can never outlive the overlay.
        try:
            self.releaseMouse()
            self.releaseKeyboard()
        except Exception:
            pass
        self.close()

    def closeEvent(self, event) -> None:
        """Last line of defence — closed by ANY route, input is released."""
        try:
            self.releaseMouse()
            self.releaseKeyboard()
        except Exception:
            pass
        super().closeEvent(event)

    def hideEvent(self, event) -> None:
        try:
            self.releaseMouse()
            self.releaseKeyboard()
        except Exception:
            pass
        super().hideEvent(event)

    # ── Capture ──────────────────────────────────────────────────────────────

    def _image_of(self, rect: QRect):
        """The frozen desktop within *rect* (global coords), stitched if needed."""
        from PySide6.QtGui import QImage

        out = QImage(rect.size(), QImage.Format.Format_RGB32)
        out.fill(QColor(0, 0, 0))
        painter = QPainter(out)
        for geo, image in self._shots:
            overlap = geo.intersected(rect)
            if overlap.isEmpty():
                continue
            src = QRect(overlap.topLeft() - geo.topLeft(), overlap.size())
            painter.drawImage(overlap.topLeft() - rect.topLeft(), image, src)
        painter.end()
        return out

    # ── Events ───────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._finish()
            self.cancelled.emit()
            return
        self._start = event.globalPosition().toPoint()
        self._cursor = self._start
        self.update()

    def mouseMoveEvent(self, event) -> None:
        self._cursor = event.globalPosition().toPoint()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._start is None:
            return
        rect = QRect(self._start, event.globalPosition().toPoint()).normalized()
        self._start = None
        if rect.width() < self._MIN_SIDE or rect.height() < self._MIN_SIDE:
            self.update()           # treat as a mis-click, keep selecting
            return
        image = self._image_of(rect)
        self._finish()
        self.selected.emit(rect, image)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._finish()
            self.cancelled.emit()

    # ── Paint ────────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        for geo, image in self._shots:
            painter.drawImage(geo.topLeft() - self._origin, image)

        selection = None
        if self._start is not None:
            selection = QRect(self._start, self._cursor).normalized()

        # Dim everything except the live selection, so the region stands out.
        shade = QColor(0, 0, 0, 110)
        if selection is None:
            painter.fillRect(self.rect(), shade)
        else:
            local = QRect(selection.topLeft() - self._origin, selection.size())
            for band in (
                QRect(0, 0, self.width(), local.top()),
                QRect(0, local.bottom() + 1, self.width(), self.height() - local.bottom()),
                QRect(0, local.top(), local.left(), local.height()),
                QRect(local.right() + 1, local.top(),
                      self.width() - local.right(), local.height()),
            ):
                if band.isValid():
                    painter.fillRect(band, shade)

            painter.setPen(QPen(QColor(255, 255, 255), 1))
            painter.drawRect(local.adjusted(0, 0, -1, -1))

            label = f"{selection.width()} x {selection.height()}"
            painter.setPen(QColor(255, 255, 255))
            font = painter.font()
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            # Above the selection, or inside it when there is no room.
            ty = local.top() - 8
            if ty < 14:
                ty = local.top() + 18
            painter.fillRect(QRect(local.left(), ty - 14, 96, 18), QColor(0, 0, 0, 170))
            painter.drawText(local.left() + 5, ty, label)

        if self._hint and selection is None:
            painter.setPen(QColor(255, 255, 255))
            font = painter.font()
            font.setPointSize(12)
            painter.setFont(font)
            pos = self._cursor - self._origin
            painter.fillRect(QRect(pos.x() + 14, pos.y() + 10,
                                   9 * len(self._hint) + 16, 26), QColor(0, 0, 0, 180))
            painter.drawText(pos.x() + 22, pos.y() + 28, self._hint)
