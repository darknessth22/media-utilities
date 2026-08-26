"""Image canvas the user can paint a selection on, with zoom / pan / rotate.

Selections are stored in *image* coordinates, never widget pixels, so zooming,
panning or rotating the view never moves or distorts what was already painted —
the view transform is presentation only.

Strokes accumulate: releasing the mouse commits a stroke and the next press
starts another, so a selection can be built up over many passes. Each committed
stroke keeps the brush width it was drawn with, so widening the brush mid-
selection doesn't retroactively fatten earlier strokes. Undo removes the last
stroke; Clear removes all.

Navigation while drawing:
  wheel                 zoom about the cursor
  middle-drag / space   pan
  Ctrl+wheel            rotate
  right-click           undo last stroke
A loupe (magnifier) can be enabled to show the area under the cursor enlarged,
which makes it possible to brush precisely along an edge.

Tools: brush (freehand polyline, or a dab on click), lasso (filled polygon),
rect and ellipse (drag a bounding box).

The overlay is painted from a FOLD of every stroke (`_fold_selection`), not by
drawing each stroke in turn, and the fold includes the in-progress stroke. That
is what makes a negative stroke visibly remove the highlight as it is dragged —
drawing strokes independently could only lay a red mark on top of the blue one
it was meant to be erasing. The fold mirrors
`core.bg_eraser._mask_from_strokes`, so the shading is what will be erased.

Modifiers that change what a stroke MEANS rather than where it is:
  set_subtract   the stroke cuts out of the selection instead of adding to it.
                 Lets an over-eager smart selection be trimmed by hand instead
                 of undone and redrawn.
  set_invert     shade the complement — everything except the selection is what
                 gets removed. Presentation only; the core does the flip.

Any stroke can also be tagged *smart* (`set_smart`). A smart stroke does not
mean "erase these pixels" — it points at an object, and the core resolves the
object's real outline with segmentation. That is what makes a rough circle over
someone remove the whole person, phone-style.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap,
    QPolygonF, QTransform,
)
from PySide6.QtWidgets import QLabel, QSizePolicy

TOOL_BRUSH = "brush"
TOOL_LASSO = "lasso"
TOOL_RECT = "rect"
TOOL_ELLIPSE = "ellipse"

_OVERLAY = QColor(59, 130, 246, 110)
_OUTLINE = QColor(59, 130, 246, 230)
_CURSOR_RING = QColor(59, 130, 246, 200)
_LOUPE_BORDER = QColor(59, 130, 246, 220)
# Detected-object overlay — deliberately a different hue from the drawn
# selection so "what I drew" and "what was detected" never look alike.
_DETECT_FILL = QColor(16, 185, 129, 95)
_DETECT_EDGE = QColor(52, 211, 153, 255)
_PENDING_EDGE = QColor(245, 158, 11, 230)
# Subtractive (negative) strokes — red, so "adding" and "cutting away" are never
# confused at a glance.
_ERASE_OVERLAY = QColor(239, 68, 68, 110)
_ERASE_OUTLINE = QColor(248, 113, 113, 235)
_ERASE_RING = QColor(248, 113, 113, 215)

_MIN_ZOOM = 0.1
_MAX_ZOOM = 16.0
_LOUPE_SIZE = 170
_LOUPE_FACTOR = 3.0


class DrawCanvas(QLabel):
    """Shows an image and captures a painted selection over it.

    A selection is a list of strokes, each
    ``{"tool": str, "points": [QPointF in image coords], "brush": float,
    "smart": bool}`` where `brush` is a width in image pixels.
    """

    selection_changed = Signal()
    view_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._source: QPixmap | None = None
        self._image_path: str | None = None
        self._tool = TOOL_BRUSH
        self._brush_img = 24.0        # brush width in IMAGE pixels
        # When set, a stroke marks an OBJECT to segment rather than the exact
        # pixels to erase; the core resolves it with SAM.
        self._smart = False
        # Negative brush: strokes CUT AWAY from the selection instead of adding
        # to it, so an over-eager smart selection can be trimmed by hand rather
        # than undone and redrawn from scratch.
        self._subtract = False
        # Presentation flag only — inversion happens in the core. The canvas
        # just shades the complement so it is obvious what will be removed.
        self._invert = False

        self._strokes: list[dict] = []
        self._live: list[QPointF] = []
        self._drawing = False

        # View state — presentation only.
        self._zoom = 1.0
        self._fit_zoom = 1.0
        self._angle = 0.0             # degrees
        self._pan = QPointF(0, 0)     # extra translation in widget px
        self._panning = False
        self._pan_from = QPoint()
        self._space_held = False

        self._cursor_pos: QPoint | None = None
        self._loupe = False
        # Detected object outlines, per stroke index: {idx: [[QPointF, ...]]}.
        # Filled in by the section after segmentation so the user can SEE what a
        # smart stroke actually selected.
        self._detected: dict[int, list[list[QPointF]]] = {}
        self._pending_smart = False

    # ── image ─────────────────────────────────────────────────────────────

    def set_image(self, path: str) -> bool:
        """Load *path*. Re-loading the same path is a no-op so callers can call
        this freely (preview refreshes, tab switches) without wiping strokes."""
        if path and path == self._image_path and self.has_image():
            return True
        px = QPixmap(path)
        if px.isNull():
            self._source = None
            self._image_path = None
            self.clear()
            return False
        self._source = px
        self._image_path = path
        self._strokes = []
        self._live = []
        self._detected.clear()
        self._pending_smart = False
        self.reset_view()
        self.selection_changed.emit()
        return True

    def has_image(self) -> bool:
        return self._source is not None and not self._source.isNull()

    # ── view ──────────────────────────────────────────────────────────────

    def _compute_fit(self) -> float:
        if not self.has_image():
            return 1.0
        sw, sh = self._source.width(), self._source.height()
        if not sw or not sh:
            return 1.0
        # Account for rotation so a rotated image still fits the viewport.
        rad = math.radians(self._angle)
        c, s = abs(math.cos(rad)), abs(math.sin(rad))
        bw = sw * c + sh * s
        bh = sw * s + sh * c
        return min(self.width() / bw, self.height() / bh) if bw and bh else 1.0

    def reset_view(self) -> None:
        self._angle = 0.0
        self._pan = QPointF(0, 0)
        self._fit_zoom = self._compute_fit()
        self._zoom = self._fit_zoom
        self.update()
        self.view_changed.emit()

    def fit_to_window(self) -> None:
        self._fit_zoom = self._compute_fit()
        self._zoom = self._fit_zoom
        self._pan = QPointF(0, 0)
        self.update()
        self.view_changed.emit()

    def zoom_percent(self) -> int:
        return int(round(self._zoom * 100))

    def rotation(self) -> int:
        return int(round(self._angle)) % 360

    def set_loupe(self, on: bool) -> None:
        self._loupe = bool(on)
        self.update()

    def loupe_enabled(self) -> bool:
        return self._loupe

    def zoom_by(self, factor: float, about: QPoint | None = None) -> None:
        """Multiply zoom, keeping the image point under *about* stationary."""
        if not self.has_image():
            return
        new = max(_MIN_ZOOM, min(_MAX_ZOOM, self._zoom * factor))
        if abs(new - self._zoom) < 1e-9:
            return
        anchor = about or QPoint(self.width() // 2, self.height() // 2)
        before = self._widget_to_image(anchor)
        self._zoom = new
        after = self._widget_to_image(anchor)
        if before is not None and after is not None:
            # Shift the pan so the anchored image point lands back under the
            # cursor; delta is in image px, so scale it into widget px.
            d = QPointF(after.x() - before.x(), after.y() - before.y())
            t = QTransform().rotate(self._angle)
            dw = t.map(QPointF(d.x() * self._zoom, d.y() * self._zoom))
            self._pan += dw
        self.update()
        self.view_changed.emit()

    def rotate_by(self, degrees: float) -> None:
        if not self.has_image():
            return
        self._angle = (self._angle + degrees) % 360
        self.update()
        self.view_changed.emit()

    def set_rotation(self, degrees: float) -> None:
        if not self.has_image():
            return
        self._angle = float(degrees) % 360
        self.update()
        self.view_changed.emit()

    # ── coordinate mapping ────────────────────────────────────────────────

    def _transform(self) -> QTransform:
        """Image space -> widget space."""
        t = QTransform()
        t.translate(self.width() / 2 + self._pan.x(),
                    self.height() / 2 + self._pan.y())
        t.rotate(self._angle)
        t.scale(self._zoom, self._zoom)
        if self.has_image():
            t.translate(-self._source.width() / 2, -self._source.height() / 2)
        return t

    def _widget_to_image(self, p: QPoint) -> QPointF | None:
        t = self._transform()
        inv, ok = t.inverted()
        if not ok:
            return None
        return inv.map(QPointF(p))

    def _image_contains(self, p: QPointF) -> bool:
        if not self.has_image():
            return False
        return (0 <= p.x() <= self._source.width()
                and 0 <= p.y() <= self._source.height())

    def _clamp_to_image(self, p: QPointF) -> QPointF:
        if not self.has_image():
            return p
        return QPointF(min(max(p.x(), 0.0), float(self._source.width())),
                       min(max(p.y(), 0.0), float(self._source.height())))

    # ── selection API ─────────────────────────────────────────────────────

    def set_tool(self, tool: str) -> None:
        if tool == self._tool:
            return
        self._tool = tool
        self._live = []
        self._drawing = False
        self.update()

    def set_smart(self, on: bool) -> None:
        """Tag subsequent strokes as object-selection prompts."""
        self._smart = bool(on)

    def smart_enabled(self) -> bool:
        return self._smart

    def set_subtract(self, on: bool) -> None:
        """Tag subsequent strokes as subtractive (cut out of the selection)."""
        on = bool(on)
        if on == self._subtract:
            return
        self._subtract = on
        self._live = []
        self._drawing = False
        self.update()

    def subtract_enabled(self) -> bool:
        return self._subtract

    def set_invert(self, on: bool) -> None:
        """Shade the complement of the selection — everything except it goes."""
        on = bool(on)
        if on == self._invert:
            return
        self._invert = on
        self.update()

    def invert_enabled(self) -> bool:
        return self._invert

    def set_detected(self, index: int,
                     contours: list[list[tuple[float, float]]],
                     mask_key=None) -> None:
        """Attach a detected outline (image fractions) to stroke *index*.

        `mask_key` identifies the exact mask the core cached for this detection;
        it is passed back at erase time so the pixel-accurate mask is used rather
        than these simplified drawing polygons.
        """
        if not self.has_image():
            return
        w, h = self._source.width(), self._source.height()
        self._detected[index] = [
            [QPointF(fx * w, fy * h) for fx, fy in poly] for poly in contours
        ]
        if mask_key is not None:
            self._strokes[index]["mask_key"] = mask_key
        self._pending_smart = False
        self.update()

    def set_pending_smart(self, pending: bool) -> None:
        """Show a 'detecting…' state on the newest smart stroke."""
        self._pending_smart = bool(pending)
        self.update()

    def last_stroke_index(self) -> int:
        return len(self._strokes) - 1

    def last_stroke_shape(self) -> str | None:
        return self._strokes[-1]["tool"] if self._strokes else None

    def last_stroke_is_smart(self) -> bool:
        if not self._strokes:
            return False
        last = self._strokes[-1]
        # A negative stroke is always literal — it trims exactly what was drawn.
        return bool(last.get("smart")) and not last.get("subtract")

    def last_stroke_points(self) -> list[tuple[float, float]]:
        """Newest stroke as image fractions, for a segmentation prompt."""
        if not self._strokes or not self.has_image():
            return []
        w, h = self._source.width(), self._source.height()
        return [(p.x() / w, p.y() / h) for p in self._strokes[-1]["points"]]

    def set_brush_size(self, px: int) -> None:
        """Brush width in *screen* px — converted to image px so the painted
        width matches what the ring showed at the current zoom."""
        self._brush_img = max(1.0, float(px) / max(self._zoom, 1e-6))
        self.update()

    def clear_selection(self) -> None:
        self._strokes = []
        self._live = []
        self._detected.clear()
        self._pending_smart = False
        self._drawing = False
        self.update()
        self.selection_changed.emit()

    def undo_stroke(self) -> None:
        if self._strokes:
            self._detected.pop(len(self._strokes) - 1, None)
            self._strokes.pop()
            if not self._strokes:
                self._detected.clear()
            self._pending_smart = False
            self.update()
            self.selection_changed.emit()

    def stroke_count(self) -> int:
        return len(self._strokes)

    def has_selection(self) -> bool:
        return bool(self._strokes)

    def strokes(self) -> list[dict]:
        """Committed selection as [{"shape", "points": [(fx, fy)...], "brush"}].

        Coordinates are fractions of the image; `brush` is a fraction of the
        image's smaller edge, matching what `core.bg_eraser` expects.
        """
        if not self.has_image():
            return []
        w, h = self._source.width(), self._source.height()
        small = min(w, h) or 1
        out: list[dict] = []
        for i, s in enumerate(self._strokes):
            pts = [(min(max(p.x() / w, 0.0), 1.0),
                    min(max(p.y() / h, 0.0), 1.0)) for p in s["points"]]
            item = {"shape": s["tool"], "points": pts,
                    "brush": s["brush"] / small,
                    "smart": bool(s.get("smart")),
                    "subtract": bool(s.get("subtract"))}
            # Pass the previewed outline through so the erase matches exactly
            # what was shown on screen.
            if i in self._detected:
                item["detected"] = [
                    [(p.x() / w, p.y() / h) for p in poly]
                    for poly in self._detected[i]
                ]
            if s.get("mask_key") is not None:
                item["mask_key"] = s["mask_key"]
            out.append(item)
        return out

    # ── events ────────────────────────────────────────────────────────────

    def resizeEvent(self, ev) -> None:  # type: ignore[override]
        super().resizeEvent(ev)
        was_fit = abs(self._zoom - self._fit_zoom) < 1e-6
        self._fit_zoom = self._compute_fit()
        if was_fit:
            self._zoom = self._fit_zoom     # keep "fit" behaviour on resize
        self.update()
        self.view_changed.emit()

    def wheelEvent(self, ev) -> None:  # type: ignore[override]
        if not self.has_image():
            super().wheelEvent(ev)
            return
        delta = ev.angleDelta().y()
        if delta == 0:
            return
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.rotate_by(5.0 if delta > 0 else -5.0)
        else:
            self.zoom_by(1.15 if delta > 0 else 1 / 1.15,
                         ev.position().toPoint())
        ev.accept()

    def keyPressEvent(self, ev) -> None:  # type: ignore[override]
        if ev.key() == Qt.Key.Key_Space:
            self._space_held = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            ev.accept()
            return
        super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev) -> None:  # type: ignore[override]
        if ev.key() == Qt.Key.Key_Space:
            self._space_held = False
            self.setCursor(Qt.CursorShape.CrossCursor)
            ev.accept()
            return
        super().keyReleaseEvent(ev)

    def mousePressEvent(self, ev) -> None:  # type: ignore[override]
        pos = ev.position().toPoint()
        btn = ev.button()

        if btn == Qt.MouseButton.RightButton and self._strokes:
            self.undo_stroke()
            return

        # Pan with the middle button, or left button while space is held.
        if btn == Qt.MouseButton.MiddleButton or (
                self._space_held and btn == Qt.MouseButton.LeftButton):
            self._panning = True
            self._pan_from = pos
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        img_pt = self._widget_to_image(pos)
        if (btn != Qt.MouseButton.LeftButton or not self.has_image()
                or img_pt is None or not self._image_contains(img_pt)):
            super().mousePressEvent(ev)
            return
        self._drawing = True
        self._live = [img_pt]
        self.update()

    def mouseMoveEvent(self, ev) -> None:  # type: ignore[override]
        pos = ev.position().toPoint()
        self._cursor_pos = pos

        if self._panning:
            d = pos - self._pan_from
            self._pan += QPointF(d.x(), d.y())
            self._pan_from = pos
            self.update()
            self.view_changed.emit()
            return

        if not self._drawing:
            self.update()          # keep the ring / loupe following the pointer
            super().mouseMoveEvent(ev)
            return

        img_pt = self._widget_to_image(pos)
        if img_pt is None:
            return
        img_pt = self._clamp_to_image(img_pt)
        if self._tool in (TOOL_RECT, TOOL_ELLIPSE):
            self._live = [self._live[0], img_pt]
        else:
            self._live.append(img_pt)
        self.update()

    def mouseReleaseEvent(self, ev) -> None:  # type: ignore[override]
        if self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.OpenHandCursor if self._space_held
                           else Qt.CursorShape.CrossCursor)
            return
        if not self._drawing:
            super().mouseReleaseEvent(ev)
            return
        self._drawing = False
        self._commit_live()

    def leaveEvent(self, ev) -> None:  # type: ignore[override]
        self._cursor_pos = None
        self.update()
        super().leaveEvent(ev)

    def _commit_live(self) -> None:
        pts = self._live
        self._live = []
        usable = (
            (self._tool in (TOOL_RECT, TOOL_ELLIPSE) and len(pts) >= 2)
            or (self._tool == TOOL_LASSO and len(pts) >= 3)
            or (self._tool == TOOL_BRUSH and len(pts) >= 1)
        )
        if usable:
            self._strokes.append({"tool": self._tool, "points": pts,
                                  "brush": self._brush_img,
                                  "smart": self._smart and not self._subtract,
                                  "subtract": self._subtract})
            self.selection_changed.emit()
        self.update()

    # ── painting ──────────────────────────────────────────────────────────

    def _paint_stroke(self, painter: QPainter, tool: str,
                      pts: list[QPointF], brush_img: float) -> None:
        """Dashed guide for an in-progress shape drag. Image coordinates.

        Committed strokes are NOT drawn this way — they go through the fold in
        `_paint_selection`, which is what lets a negative stroke visibly cut the
        overlay instead of covering it.
        """
        if not pts:
            return
        fill = _OVERLAY
        edge = _OUTLINE
        if tool == TOOL_RECT and len(pts) >= 2:
            painter.setPen(QPen(edge, max(1.0, 1.5 / self._zoom),
                                Qt.PenStyle.DashLine))
            painter.setBrush(fill)
            painter.drawRect(QRectF(pts[0], pts[-1]).normalized())
        elif tool == TOOL_ELLIPSE and len(pts) >= 2:
            painter.setPen(QPen(edge, max(1.0, 1.5 / self._zoom),
                                Qt.PenStyle.DashLine))
            painter.setBrush(fill)
            painter.drawEllipse(QRectF(pts[0], pts[-1]).normalized())
        elif tool == TOOL_LASSO and len(pts) >= 2:
            painter.setPen(QPen(edge, max(1.0, 1.5 / self._zoom),
                                Qt.PenStyle.DashLine))
            painter.setBrush(fill)
            painter.drawPolygon(QPolygonF(pts))
        else:
            pen = QPen(fill, brush_img)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if len(pts) == 1:
                painter.drawPoint(pts[0])
            else:
                painter.drawPolyline(QPolygonF(pts))

    def _stroke_path(self, tool: str, pts: list[QPointF],
                     brush_img: float) -> QPainterPath | None:
        """One stroke as a filled region, matching how the core rasterises it."""
        if not pts:
            return None
        path = QPainterPath()
        if tool == TOOL_RECT and len(pts) >= 2:
            path.addRect(QRectF(pts[0], pts[-1]).normalized())
        elif tool == TOOL_ELLIPSE and len(pts) >= 2:
            path.addEllipse(QRectF(pts[0], pts[-1]).normalized())
        elif tool == TOOL_LASSO and len(pts) >= 3:
            path.addPolygon(QPolygonF(pts))
            path.closeSubpath()
        else:
            if len(pts) == 1:
                r = max(0.5, brush_img / 2.0)
                path.addEllipse(pts[0], r, r)
            else:
                line = QPainterPath(pts[0])
                for p in pts[1:]:
                    line.lineTo(p)
                stroker = QPainterPathStroker()
                stroker.setWidth(max(0.5, brush_img))
                stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
                stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                path = stroker.createStroke(line)
        return path

    def _detected_path(self, index: int) -> QPainterPath:
        """A detected object's outline as one region."""
        part = QPainterPath()
        for poly in self._detected.get(index, ()):
            if len(poly) >= 3:
                sub = QPainterPath()
                sub.addPolygon(QPolygonF(poly))
                sub.closeSubpath()
                part = part.united(sub)
        return part

    def _fold_selection(self, include_live: bool = True
                        ) -> tuple[QPainterPath, QPainterPath]:
        """Fold every stroke into (painted, detected) regions.

        Positive strokes union in, negative strokes subtract — the same
        sequential fold `core.bg_eraser._mask_from_strokes` performs, so what is
        shaded on screen is exactly what will be erased.

        Painted and detected areas are kept apart only so each keeps its own
        colour (blue for hand-painted, green for a segmented object). A negative
        stroke cuts BOTH, since the erase mask makes no such distinction.

        include_live folds the in-progress stroke too, so a negative stroke
        visibly eats into the selection as it is dragged rather than only once
        the mouse is released.
        """
        painted = QPainterPath()
        detected = QPainterPath()
        items: list[tuple[dict, int]] = [(s, i) for i, s in enumerate(self._strokes)]
        if include_live and self._live:
            items.append(({"tool": self._tool, "points": self._live,
                           "brush": self._brush_img,
                           "subtract": self._subtract}, -1))
        for s, i in items:
            if i >= 0 and i in self._detected:
                part = self._detected_path(i)
                target = "detected"
            else:
                part = self._stroke_path(s["tool"], s["points"], s["brush"])
                target = "painted"
            if part is None or part.isEmpty():
                continue
            if s.get("subtract"):
                # Cuts through everything already selected, whatever drew it.
                painted = painted.subtracted(part)
                detected = detected.subtracted(part)
            elif target == "detected":
                detected = detected.united(part)
            else:
                painted = painted.united(part)
        return painted, detected

    def _selection_path(self, include_live: bool = True) -> QPainterPath:
        """The whole selection as one region — painted and detected combined."""
        painted, detected = self._fold_selection(include_live)
        return painted.united(detected)

    def _paint_selection(self, painter: QPainter,
                         zoom: float | None = None) -> None:
        """Shade the folded selection — negatives already cut out of it.

        Drawn from the fold rather than stroke-by-stroke so a negative stroke
        removes the overlay ON SCREEN as it is drawn. Painting each stroke
        independently could not do this: a later red stroke merely sat on top of
        the blue one it was supposed to be erasing.
        """
        z = self._zoom if zoom is None else zoom
        painted, detected = self._fold_selection()
        hair = max(1.0, 1.5 / z)
        if not detected.isEmpty():
            painter.setPen(QPen(_DETECT_EDGE, max(1.0, 2.0 / z)))
            painter.setBrush(_DETECT_FILL)
            painter.drawPath(detected)
        if not painted.isEmpty():
            # Subtract the detected region so the two overlays don't stack into
            # a muddier colour where a brush stroke overlaps a detected object.
            painter.setPen(QPen(_OUTLINE, hair))
            painter.setBrush(_OVERLAY)
            painter.drawPath(painted.subtracted(detected))

    def _paint_live_cut(self, painter: QPainter,
                        zoom: float | None = None) -> None:
        """Outline of an in-progress negative stroke.

        The fold has already removed its area from the overlay, so without this
        there would be no indication of where the cut is landing while dragging.
        """
        z = self._zoom if zoom is None else zoom
        part = self._stroke_path(self._tool, self._live, self._brush_img)
        if part is None or part.isEmpty():
            return
        painter.setPen(QPen(_ERASE_OUTLINE, max(1.0, 1.5 / z),
                            Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(part)

    def _paint_scene(self, painter: QPainter) -> None:
        """Image plus the folded selection, in image coordinates."""
        painter.save()
        painter.setTransform(self._transform(), True)
        painter.drawPixmap(0, 0, self._source)

        if self._invert and (self._strokes or self._live):
            # Shade the COMPLEMENT: what is tinted is what disappears. Drawn as
            # the image rect minus the selection so the kept subject stays clear.
            frame = QPainterPath()
            frame.addRect(QRectF(0, 0, self._source.width(),
                                 self._source.height()))
            painter.setPen(QPen(_ERASE_OUTLINE, max(1.0, 1.5 / self._zoom)))
            painter.setBrush(_ERASE_OVERLAY)
            painter.drawPath(frame.subtracted(self._selection_path()))
        else:
            self._paint_selection(painter)

        if self._live and self._subtract:
            self._paint_live_cut(painter)
        elif self._live:
            # A positive stroke is already inside the fold; only a rect/ellipse
            # needs its dashed guide so the drag extent is visible.
            if self._tool in (TOOL_RECT, TOOL_ELLIPSE, TOOL_LASSO):
                self._paint_stroke(painter, self._tool, self._live,
                                   self._brush_img)

        # "Detecting…" marker on the newest smart stroke, whose real outline has
        # not arrived yet, so the fold has only the rough mark to show.
        if self._pending_smart and self._strokes:
            last = self._strokes[-1]
            if last.get("smart") and (len(self._strokes) - 1) not in self._detected:
                painter.setPen(QPen(_PENDING_EDGE, max(1.0, 2.0 / self._zoom),
                                    Qt.PenStyle.DotLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolyline(QPolygonF(last["points"]))
        painter.restore()

    def paintEvent(self, ev) -> None:  # type: ignore[override]
        painter = QPainter(self)
        if not self.has_image():
            painter.end()
            super().paintEvent(ev)
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self._paint_scene(painter)

        # Brush-width ring, in widget space so it tracks the pointer exactly.
        if (self._tool == TOOL_BRUSH and not self._drawing and not self._panning
                and self._cursor_pos):
            ip = self._widget_to_image(self._cursor_pos)
            if ip is not None and self._image_contains(ip):
                painter.setPen(QPen(
                    _ERASE_RING if self._subtract else _CURSOR_RING, 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                r = max(1.0, self._brush_img * self._zoom / 2.0)
                painter.drawEllipse(QPointF(self._cursor_pos), r, r)

        if self._loupe and self._cursor_pos:
            self._paint_loupe(painter)
        painter.end()

    def _paint_loupe(self, painter: QPainter) -> None:
        """Magnified inset of the area under the cursor, with the strokes.

        Rendered by re-drawing the scene at a higher zoom into a clipped
        circle, so what the loupe shows always matches the canvas.
        """
        ip = self._widget_to_image(self._cursor_pos)
        if ip is None or not self._image_contains(ip):
            return

        size = _LOUPE_SIZE
        margin = 12
        # Keep the loupe away from the cursor: opposite corner of the widget.
        left = self._cursor_pos.x() > self.width() // 2
        top = self._cursor_pos.y() > self.height() // 2
        x = margin if left else self.width() - size - margin
        y = margin if top else self.height() - size - margin
        rect = QRect(x, y, size, size)

        painter.save()
        painter.setClipRect(rect)
        painter.fillRect(rect, QColor(20, 24, 32))

        # Centre the magnified image point in the loupe.
        zoom = self._zoom * _LOUPE_FACTOR
        t = QTransform()
        t.translate(rect.center().x(), rect.center().y())
        t.rotate(self._angle)
        t.scale(zoom, zoom)
        t.translate(-ip.x(), -ip.y())

        painter.setTransform(t, False)
        painter.drawPixmap(0, 0, self._source)
        # Same fold as the canvas — the loupe must never disagree with it.
        if self._invert and (self._strokes or self._live):
            frame = QPainterPath()
            frame.addRect(QRectF(0, 0, self._source.width(),
                                 self._source.height()))
            painter.setPen(QPen(_ERASE_OUTLINE, max(1.0, 1.5 / zoom)))
            painter.setBrush(_ERASE_OVERLAY)
            painter.drawPath(frame.subtracted(self._selection_path()))
        else:
            self._paint_selection(painter, zoom)
        if self._live and self._subtract:
            self._paint_live_cut(painter, zoom)
        painter.restore()

        painter.save()
        painter.setPen(QPen(_LOUPE_BORDER, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)
        # Crosshair marking the exact cursor point inside the loupe.
        c = rect.center()
        painter.setPen(QPen(_CURSOR_RING, 1))
        painter.drawLine(c.x() - 8, c.y(), c.x() + 8, c.y())
        painter.drawLine(c.x(), c.y() - 8, c.x(), c.y() + 8)
        painter.restore()
