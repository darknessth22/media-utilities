"""Home Dashboard and Tools Grid pages — Phase 3 UX overhaul.

Notable Phase-3 additions:
- HeroBanner accepts drag-and-drop; dropped media files are routed to a tool
  via the ``file_dropped`` signal on HomePage.
- The old Quick Access duplicate row is replaced by a Recent strip backed by
  ``core.recent_jobs``.
- ToolCard renders an IconTile (rounded square tinted with the tool's accent)
  and gains a hover-lift drop shadow.
- ToolsPage adds a category filter chip row.
"""
from __future__ import annotations

import os
from typing import Callable

from core.i18n import tr
from core.paths import resource_path
from core import recent_jobs

from PySide6.QtCore import Qt, QPoint, QRectF, Signal
from PySide6.QtGui import (
    QColor, QLinearGradient, QRadialGradient,
    QPainter, QPainterPath, QPen, QBrush, QPixmap, QFont,
    QDragEnterEvent, QDropEvent,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QSizePolicy, QGraphicsDropShadowEffect,
)

# resource_path → sys._MEIPASS in frozen builds; __file__ arithmetic is unreliable
# there and made every tool-card icon vanish on the Linux AppImage.
_ICONS_DIR = resource_path("assets", "icons")
_APP_LOGO  = resource_path("assets", "videl_logo.png")

_TOOL_COLOR: dict[str, str] = {
    "download":  "#3B82F6",
    "convert":   "#22D3EE",
    "compress":  "#22C55E",
    "merge":     "#A855F7",
    "trim":      "#F97316",
    "mux":       "#EC4899",
    "gif":       "#FACC15",
    "spatial":   "#FB923C",
    "document":  "#38BDF8",
    "scrub":     "#7C3AED",
    "chunk":     "#06B6D4",
    "watermark":     "#0E7490",
    "frame_grabber": "#8B5CF6",
    "palette":       "#F43F5E",
    "bg_eraser":        "#10B981",
    "vocal_isolator":   "#A855F7",
    "upscaler":         "#0EA5E9",
    "video_upscaler":   "#6366F1",
    "pdf_toolkit":      "#EF4444",
    "jumpcut":          "#F59E0B",
    "subtitles":        "#14B8A6",
    "transcript":       "#0891B2",
    "image_editor":     "#D946EF",
    "photo_restore":    "#FB7185",
    "history":          "#6B7280",
}

# Category for filter chips. Keep keys aligned with locale `filter_*` strings.
_TOOL_CATEGORY: dict[str, str] = {
    "download": "video",
    "convert": "video",
    "compress": "video",
    "merge": "video",
    "trim": "video",
    "mux": "audio",
    "gif": "video",
    "spatial": "video",
    "document": "document",
    "scrub": "video",
    "chunk": "video",
    "watermark": "video",
    "frame_grabber": "image",
    "palette": "image",
    "bg_eraser": "image",
    "vocal_isolator": "audio",
    "upscaler": "image",
    "video_upscaler": "video",
    "pdf_toolkit": "document",
    "jumpcut": "video",
    "subtitles": "video",
    "transcript": "audio",
    "image_editor": "image",
    "photo_restore": "image",
}

# File-extension → tool routing for the home drop-zone. Picked so the most
# common creator workflow lands in the right tool: drop a video → Convert,
# drop a PDF → PDF toolkit, drop an image → Convert (still a media op).
_DROP_EXT_TO_TOOL: dict[str, str] = {
    ".mp4": "convert", ".mov": "convert", ".mkv": "convert", ".webm": "convert",
    ".avi": "convert", ".m4v": "convert",
    ".mp3": "convert", ".wav": "convert", ".flac": "convert", ".m4a": "convert",
    ".aac": "convert", ".ogg": "convert",
    ".png": "convert", ".jpg": "convert", ".jpeg": "convert", ".webp": "convert",
    ".gif": "gif", ".heic": "convert", ".bmp": "convert", ".tif": "convert",
    ".pdf": "pdf_toolkit",
    ".srt": "subtitles", ".vtt": "subtitles", ".ass": "subtitles", ".ssa": "subtitles",
    ".docx": "document", ".doc": "document", ".pptx": "document",
    ".xlsx": "document", ".txt": "document",
}

# Static icon/id/index data — labels come from i18n at runtime.
_ALL_TOOLS_META: list[tuple[str, str, str, str, int]] = [
    ("download",     "download.svg",   "tool_download_name",     "tool_download_desc",     0),
    ("convert",      "convert.svg",    "tool_convert_name",      "tool_convert_desc",      1),
    ("compress",     "compress.svg",   "tool_compress_name",     "tool_compress_desc",     5),
    ("merge",        "merge.svg",      "tool_merge_name",        "tool_merge_desc",        6),
    ("trim",         "trim.svg",       "tool_trim_name",         "tool_trim_desc",         2),
    ("mux",          "mux.svg",        "tool_mux_name",          "tool_mux_desc",          8),
    ("gif",          "gif.svg",        "tool_gif_name",          "tool_gif_desc",          4),
    ("spatial",      "spatial.svg",    "tool_spatial_name",      "tool_spatial_desc",      7),
    ("document",     "document.svg",   "tool_document_name",     "tool_document_desc",     3),
    ("scrub",        "scrub.svg",      "tool_scrub_name",        "tool_scrub_desc",        9),
    ("chunk",        "chunk.svg",      "tool_chunk_name",        "tool_chunk_desc",       10),
    ("watermark",    "watermark.svg",  "tool_watermark_name",    "tool_watermark_desc",   11),
    ("frame_grabber","frame.svg",      "tool_frame_grabber_name","tool_frame_grabber_desc",12),
    ("palette",      "palette.svg",    "tool_palette_name",      "tool_palette_desc",     13),
    ("bg_eraser",       "bg_eraser.svg",       "tool_bg_eraser_name",       "tool_bg_eraser_desc",      14),
    ("vocal_isolator",  "vocal_isolator.svg",  "tool_vocal_isolator_name",  "tool_vocal_isolator_desc", 15),
    ("upscaler",        "upscaler.svg",        "tool_upscaler_name",        "tool_upscaler_desc",       16),
    ("video_upscaler",  "video_upscaler.svg",  "tool_video_upscaler_name",  "tool_video_upscaler_desc", 17),
    ("pdf_toolkit",     "document.svg",        "tool_pdf_toolkit_name",     "tool_pdf_toolkit_desc",    18),
    ("jumpcut",         "jumpcut.svg",         "tool_jumpcut_name",         "tool_jumpcut_desc",        19),
    ("subtitles",       "subtitles.svg",       "tool_subtitles_name",       "tool_subtitles_desc",      20),
    ("transcript",      "transcript.svg",      "tool_transcript_name",      "tool_transcript_desc",     21),
    ("image_editor",    "image_editor.svg",    "tool_image_editor_name",    "tool_image_editor_desc",   22),
    ("photo_restore",   "photo_restore.svg",   "tool_photo_restore_name",   "tool_photo_restore_desc",  23),
    ("history",         "history.svg",         "tool_history_name",         "tool_history_desc",        24),
]


def _resolved_tools(meta: list) -> list[tuple[str, str, str, str, int]]:
    """Resolve translation keys in tool metadata to current-language strings."""
    return [(tid, icon, tr(nk), tr(dk), idx) for tid, icon, nk, dk, idx in meta]


def _all_tools() -> list[tuple[str, str, str, str, int]]:
    return _resolved_tools(_ALL_TOOLS_META)


def _home_tools() -> list[tuple[str, str, str, str, int]]:
    return _resolved_tools(_ALL_TOOLS_META[:7])


def _meta_for_tool(tool_id: str) -> tuple[str, str, str, str, int] | None:
    for entry in _ALL_TOOLS_META:
        if entry[0] == tool_id:
            return entry
    return None


# ── Icon loader ───────────────────────────────────────────────────────────────

def _load_icon(filename: str, size: int = 32, color: str = "#8B949E") -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    path = os.path.join(_ICONS_DIR, filename)
    if not os.path.exists(path):
        return pixmap
    try:
        with open(path, "rb") as fh:
            svg_text = fh.read().decode("utf-8", errors="replace")
        svg_text = svg_text.replace("currentColor", color)
        if "fill=" not in svg_text and "stroke=" not in svg_text:
            svg_text = svg_text.replace("<svg", f'<svg fill="{color}"', 1)
        renderer = QSvgRenderer(svg_text.encode("utf-8"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
    except Exception:
        pass
    return pixmap


# ── Icon tile (tinted accent square behind icon) ──────────────────────────────

class IconTile(QWidget):
    """Rounded square tinted with the tool accent (~14% alpha) hosting the icon.

    Replaces the previous flat icon-only treatment so the tool color reads at
    a glance, without changing the global card background.
    """

    def __init__(
        self,
        icon_file: str,
        accent_hex: str,
        tile_size: int = 48,
        icon_size: int = 26,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._tile = tile_size
        self._icon_size = icon_size
        self._accent = QColor(accent_hex)
        self._pixmap = _load_icon(icon_file, icon_size, accent_hex)
        self.setFixedSize(tile_size, tile_size)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(self._accent)
        bg.setAlpha(36)  # ~14%
        p.setBrush(QBrush(bg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, self._tile, self._tile, 12, 12)
        if not self._pixmap.isNull():
            ix = (self._tile - self._pixmap.width()) // 2
            iy = (self._tile - self._pixmap.height()) // 2
            p.drawPixmap(ix, iy, self._pixmap)
        p.end()


# ── Clickable base with hover-lift drop shadow ────────────────────────────────

class _ClickableFrame(QFrame):
    def __init__(self, callback: Callable[[], None], parent=None) -> None:
        super().__init__(parent)
        self._cb = callback
        # Hover-lift effect — disabled until enterEvent fires so idle cards
        # don't all carry shadow children (cheaper on long grids).
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(0)
        self._shadow.setOffset(0, 0)
        self._shadow.setColor(QColor(0, 0, 0, 0))
        self.setGraphicsEffect(self._shadow)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._cb()
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:  # type: ignore[override]
        self._shadow.setBlurRadius(24)
        self._shadow.setOffset(0, 6)
        self._shadow.setColor(QColor(59, 130, 246, 110))
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._shadow.setBlurRadius(0)
        self._shadow.setOffset(0, 0)
        self._shadow.setColor(QColor(0, 0, 0, 0))
        super().leaveEvent(event)


# ── Gradient title label ──────────────────────────────────────────────────────

class _GradientTitleLabel(QWidget):
    """Renders title text with a left→right gradient fill."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self._text = text
        font = QFont()
        font.setPointSize(20)
        font.setBold(True)
        self._font = font
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(36)

    def set_text(self, text: str) -> None:
        self._text = text
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self._font)

        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, QColor("#E5E7EB"))
        grad.setColorAt(1.0, QColor("#9CA3AF"))

        painter.setPen(QPen(QBrush(grad), 0))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)
        painter.end()


# ── Hero Banner with drop-zone ───────────────────────────────────────────────

class HeroBanner(QFrame):
    """Painted welcome banner that doubles as a drop target.

    Emits ``file_dropped(path, tool_id, section_idx)`` so the parent page can
    forward it to the main window for routing.
    """

    file_dropped = Signal(str, str, int)

    _LOGO_W = 200
    _LOGO_H = 150

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("HeroBanner")
        self.setMinimumHeight(170)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAcceptDrops(True)
        self._drag_active = False

        raw = QPixmap(_APP_LOGO)
        self._logo_px = (
            raw.scaled(
                self._LOGO_W, self._LOGO_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if not raw.isNull() else QPixmap()
        )

        outer = QHBoxLayout(self)
        outer.setContentsMargins(44, 28, self._LOGO_W + 32, 28)
        outer.setSpacing(0)

        left = QVBoxLayout()
        left.setSpacing(8)

        self._title_lbl = _GradientTitleLabel(tr("welcome_title"))
        self._sub_lbl = QLabel(tr("hero_subtitle"))
        self._sub_lbl.setObjectName("HeroSubtitle")
        self._drop_hint = QLabel(tr("hero_drop_hint"))
        self._drop_hint.setObjectName("HeroDropHint")

        left.addWidget(self._title_lbl)
        left.addWidget(self._sub_lbl)
        left.addSpacing(4)
        left.addWidget(self._drop_hint)
        left.addStretch()

        outer.addLayout(left)

    # ── Drag & drop ────────────────────────────────────────────────────────
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            self._drag_active = True
            self.update()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        self._drag_active = False
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]
        self._drag_active = False
        self.update()
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        tool_id = _DROP_EXT_TO_TOOL.get(ext, "convert")
        meta = _meta_for_tool(tool_id)
        if meta is None:
            return
        self.file_dropped.emit(path, tool_id, meta[4])
        event.acceptProposedAction()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        base = QLinearGradient(0, 0, w, h)
        base.setColorAt(0.00, QColor("#0D1530"))
        base.setColorAt(0.40, QColor("#0A1020"))
        base.setColorAt(1.00, QColor("#060C1A"))
        painter.setBrush(QBrush(base))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, w, h, 16, 16)

        glow_cx = w * 0.75
        glow_cy = h * 0.40
        glow_r  = max(w, h) * 0.70
        glow = QRadialGradient(glow_cx, glow_cy, glow_r)
        glow.setColorAt(0.00, QColor(59, 130, 246, 80))
        glow.setColorAt(0.30, QColor(37,  99, 235, 40))
        glow.setColorAt(1.00, QColor(0,   0,   0,  0))
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 0, w, h)

        wave = QPainterPath()
        wave.moveTo(0, h * 0.65)
        wave.cubicTo(
            w * 0.28, h * 0.50,
            w * 0.58, h * 0.75,
            w,        h * 0.60,
        )
        pen = QPen(QColor(59, 130, 246, 35), 2.5)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(wave)

        logo_cx = w - self._LOGO_W // 2 - 20
        logo_cy = h // 2
        halo = QRadialGradient(logo_cx, logo_cy, 130)
        halo.setColorAt(0.00, QColor(96, 165, 250, 55))
        halo.setColorAt(1.00, QColor(0,   0,   0,  0))
        painter.setBrush(QBrush(halo))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(logo_cx - 130), int(logo_cy - 130), 260, 260)

        # Border — emphasised when a drag is hovering over the banner.
        if self._drag_active:
            border_pen = QPen(QColor(96, 165, 250, 220), 2)
        else:
            border_pen = QPen(QColor(30, 58, 138, 120), 1)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(0, 0, w - 1, h - 1, 16, 16)

        painter.end()

        if not self._logo_px.isNull():
            lx = w - self._logo_px.width() - 20
            ly = (h - self._logo_px.height()) // 2
            p2 = QPainter(self)
            p2.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p2.drawPixmap(lx, ly, self._logo_px)
            p2.end()


# ── Tool cards ────────────────────────────────────────────────────────────────

class ToolCard(_ClickableFrame):
    def __init__(
        self,
        tool_id: str,
        icon_file: str,
        title: str,
        desc: str,
        section_idx: int,
        navigate_cb: Callable[[int], None],
        parent=None,
    ) -> None:
        # Wrap nav so opening a tool also records into recents.
        def _navigate() -> None:
            recent_jobs.record_open(tool_id, section_idx)
            navigate_cb(section_idx)

        super().__init__(_navigate, parent)
        self.setObjectName("ToolCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        color = _TOOL_COLOR.get(tool_id, "#6B7280")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(IconTile(icon_file, color, tile_size=48, icon_size=26))

        self._title_lbl = QLabel(title)
        self._title_lbl.setObjectName("ToolCardTitle")
        layout.addWidget(self._title_lbl)

        self._desc_lbl = QLabel(desc)
        self._desc_lbl.setObjectName("ToolCardDesc")
        self._desc_lbl.setWordWrap(True)
        layout.addWidget(self._desc_lbl)
        layout.addStretch()

    def update_text(self, title: str, desc: str) -> None:
        self._title_lbl.setText(title)
        self._desc_lbl.setText(desc)


class MoreToolsCard(_ClickableFrame):
    """The 8th card — 'More Tools' — opens the Tools page."""

    def update_text(self) -> None:
        self._title_lbl.setText(tr("home_more_tools"))
        self._desc_lbl.setText(tr("home_more_tools_desc"))

    def __init__(self, show_tools_cb: Callable[[], None], parent=None) -> None:
        super().__init__(show_tools_cb, parent)
        self.setObjectName("MoreToolsCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setPixmap(_load_icon("dashboard.svg", 40, "#6B7280"))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        self._title_lbl = QLabel(tr("home_more_tools"))
        self._title_lbl.setObjectName("ToolCardTitle")
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title_lbl)

        self._desc_lbl = QLabel(tr("home_more_tools_desc"))
        self._desc_lbl.setObjectName("ToolCardDesc")
        self._desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._desc_lbl.setWordWrap(True)
        layout.addWidget(self._desc_lbl)
        layout.addStretch()


# ── Recent strip card ────────────────────────────────────────────────────────

class RecentJobCard(_ClickableFrame):
    """Compact card used in the home Recent strip."""

    def __init__(
        self,
        tool_id: str,
        icon_file: str,
        title: str,
        section_idx: int,
        navigate_cb: Callable[[int], None],
        parent=None,
    ) -> None:
        super().__init__(lambda: navigate_cb(section_idx), parent)
        self.setObjectName("RecentJobCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        color = _TOOL_COLOR.get(tool_id, "#6B7280")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 14, 10)
        layout.setSpacing(10)

        layout.addWidget(IconTile(icon_file, color, tile_size=34, icon_size=18))

        self._title_lbl = QLabel(title)
        self._title_lbl.setObjectName("RecentJobTitle")
        layout.addWidget(self._title_lbl)
        layout.addStretch()


# ── Filter chips ──────────────────────────────────────────────────────────────

class FilterChipBar(QWidget):
    """Pill buttons for filtering the Tools grid by category.

    Emits ``filter_changed(category_id)`` where ``category_id`` is one of
    ``all|video|audio|image|document``.
    """

    filter_changed = Signal(str)

    _CATEGORIES: list[tuple[str, str]] = [
        ("all", "filter_all"),
        ("video", "filter_video"),
        ("audio", "filter_audio"),
        ("image", "filter_image"),
        ("document", "filter_document"),
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._active = "all"
        self._buttons: list[tuple[str, QPushButton]] = []

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        for cat_id, key in self._CATEGORIES:
            btn = QPushButton(tr(key))
            btn.setObjectName("FilterChipActive" if cat_id == self._active else "FilterChip")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(cat_id == self._active)
            btn.clicked.connect(lambda _checked=False, c=cat_id: self._select(c))
            self._buttons.append((cat_id, btn))
            row.addWidget(btn)
        row.addStretch()

    def _select(self, cat_id: str) -> None:
        if cat_id == self._active:
            # Re-affirm checked state since QPushButton toggles on click.
            for c, b in self._buttons:
                b.setChecked(c == self._active)
            return
        self._active = cat_id
        for c, b in self._buttons:
            b.setChecked(c == cat_id)
            b.setObjectName("FilterChipActive" if c == cat_id else "FilterChip")
            # Force re-style after objectName change.
            b.style().unpolish(b)
            b.style().polish(b)
        self.filter_changed.emit(cat_id)

    def retranslate_ui(self) -> None:
        for (cat_id, key), (_c, btn) in zip(self._CATEGORIES, self._buttons):
            btn.setText(tr(key))


# ── Grid builder ──────────────────────────────────────────────────────────────

def _build_tools_grid(
    tools: list[tuple[str, str, str, str, int]],
    navigate_cb: Callable[[int], None],
    cols: int = 4,
    more_tools_cb: Callable[[], None] | None = None,
) -> QWidget:
    grid_widget = QWidget()
    grid = QGridLayout(grid_widget)
    grid.setSpacing(16)
    grid.setContentsMargins(0, 0, 0, 0)

    for i, (tool_id, icon_file, title, desc, idx) in enumerate(tools):
        card = ToolCard(tool_id, icon_file, title, desc, idx, navigate_cb)
        grid.addWidget(card, i // cols, i % cols)

    if more_tools_cb is not None:
        i = len(tools)
        grid.addWidget(MoreToolsCard(more_tools_cb), i // cols, i % cols)

    return grid_widget


# ── Pages ─────────────────────────────────────────────────────────────────────

class HomePage(QScrollArea):
    """Landing screen: hero (drop target) + Recent strip + 7-tool grid."""

    file_dropped = Signal(str, str, int)

    def __init__(
        self,
        navigate_cb: Callable[[int], None],
        show_tools_cb: Callable[[], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._navigate_cb = navigate_cb
        self._show_tools_cb = show_tools_cb

        content = QWidget()
        self._root = QVBoxLayout(content)
        self._root.setContentsMargins(32, 32, 32, 32)
        self._root.setSpacing(24)

        # Hero
        self._hero = HeroBanner()
        self._hero.file_dropped.connect(self.file_dropped)
        self._root.addWidget(self._hero)

        # Recent strip header
        recent_hdr = QHBoxLayout()
        self._recent_lbl = QLabel(tr("recent_jobs_title"))
        self._recent_lbl.setObjectName("SectionLabel")
        recent_hdr.addWidget(self._recent_lbl)
        recent_hdr.addStretch()
        self._root.addLayout(recent_hdr)

        # Recent strip body — populated/refreshed in _populate_recent.
        self._recent_row = QHBoxLayout()
        self._recent_row.setSpacing(12)
        self._recent_empty_lbl = QLabel(tr("recent_jobs_empty"))
        self._recent_empty_lbl.setObjectName("RecentEmptyLabel")
        self._recent_empty_lbl.setWordWrap(True)
        self._recent_cards: list[RecentJobCard] = []
        self._populate_recent()
        self._root.addLayout(self._recent_row)

        # Tools section header
        self._tools_lbl = QLabel(tr("home_tools_section"))
        self._tools_lbl.setObjectName("SectionLabel")
        self._root.addWidget(self._tools_lbl)

        # Tool cards grid
        self._tool_cards: list[ToolCard] = []
        self._more_tools_card: MoreToolsCard | None = None
        grid_w = self._build_grid(cols=4)
        self._root.addWidget(grid_w)
        self._root.addStretch()

        self.setWidget(content)

    def _clear_recent_row(self) -> None:
        while self._recent_row.count():
            item = self._recent_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._recent_cards.clear()

    def _populate_recent(self) -> None:
        self._clear_recent_row()
        recents = recent_jobs.list_recent(limit=5)
        if not recents:
            self._recent_row.addWidget(self._recent_empty_lbl)
            return
        for tool_id, idx in recents:
            meta = _meta_for_tool(tool_id)
            if meta is None:
                continue
            _tid, icon_file, name_key, _desc_key, _idx = meta
            card = RecentJobCard(
                tool_id, icon_file, tr(name_key), idx, self._navigate_cb,
            )
            self._recent_cards.append(card)
            self._recent_row.addWidget(card)
        self._recent_row.addStretch()

    def refresh_recent(self) -> None:
        """Public hook so MainWindow can refresh the strip after navigation."""
        self._populate_recent()

    def _build_grid(self, cols: int = 4) -> QWidget:
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(16)
        grid.setContentsMargins(0, 0, 0, 0)

        self._tool_cards.clear()
        for i, (tool_id, icon_file, title, desc, idx) in enumerate(_home_tools()):
            card = ToolCard(tool_id, icon_file, title, desc, idx, self._navigate_cb)
            self._tool_cards.append(card)
            grid.addWidget(card, i // cols, i % cols)

        i = len(self._tool_cards)
        self._more_tools_card = MoreToolsCard(self._show_tools_cb)
        grid.addWidget(self._more_tools_card, i // cols, i % cols)
        return grid_widget

    def retranslate_ui(self) -> None:
        self._hero._title_lbl.set_text(tr("welcome_title"))
        self._hero._sub_lbl.setText(tr("hero_subtitle"))
        self._hero._drop_hint.setText(tr("hero_drop_hint"))
        self._recent_lbl.setText(tr("recent_jobs_title"))
        self._recent_empty_lbl.setText(tr("recent_jobs_empty"))
        self._tools_lbl.setText(tr("home_tools_section"))
        if self._more_tools_card:
            self._more_tools_card.update_text()
        for card, (_, _, title, desc, _idx) in zip(self._tool_cards, _home_tools()):
            card.update_text(title, desc)
        # Re-render recent labels (titles are tool names from i18n).
        self._populate_recent()


class ToolsPage(QScrollArea):
    """Full tools grid page — all tools, with category filter chips."""

    def __init__(self, navigate_cb: Callable[[int], None], parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._navigate_cb = navigate_cb
        self._active_filter = "all"

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(16)

        self._header = QLabel(tr("nav_tools"))
        self._header.setObjectName("PageHeader")
        root.addWidget(self._header)

        self._sub = QLabel(tr("tools_page_subtitle"))
        self._sub.setObjectName("TextSecondary")
        root.addWidget(self._sub)

        # Filter chips
        self._chip_bar = FilterChipBar()
        self._chip_bar.filter_changed.connect(self._on_filter_changed)
        root.addWidget(self._chip_bar)

        self._tool_cards: list[tuple[str, ToolCard]] = []
        grid_widget = QWidget()
        self._grid = QGridLayout(grid_widget)
        self._grid.setSpacing(16)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._populate_grid()
        root.addWidget(grid_widget)
        root.addStretch()

        self.setWidget(content)

    def _matches_filter(self, tool_id: str) -> bool:
        if self._active_filter == "all":
            return True
        return _TOOL_CATEGORY.get(tool_id) == self._active_filter

    def _clear_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._tool_cards.clear()

    def _populate_grid(self) -> None:
        cols = 4
        self._clear_grid()
        visible = [
            entry for entry in _all_tools()
            if self._matches_filter(entry[0])
        ]
        # Reset all column stretches so a previous filter's setup doesn't leak
        # in. The branch below picks the right policy for full vs partial rows.
        for c in range(cols + 1):
            self._grid.setColumnStretch(c, 0)

        # Partial: any row with < cols cards. Cap card width and let a phantom
        # trailing column eat leftover so the few cards don't blow up.
        # Full: at least one row of `cols` cards. Let columns share width
        # evenly so the grid spans the page instead of leaving a big right
        # gap from the phantom column.
        partial = len(visible) < cols
        for i, (tool_id, icon_file, title, desc, idx) in enumerate(visible):
            card = ToolCard(tool_id, icon_file, title, desc, idx, self._navigate_cb)
            if partial:
                card.setMinimumWidth(220)
                card.setMaximumWidth(280)
                card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            self._tool_cards.append((tool_id, card))
            if partial:
                self._grid.addWidget(
                    card, i // cols, i % cols,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                )
            else:
                self._grid.addWidget(card, i // cols, i % cols)

        if partial:
            self._grid.setColumnStretch(cols, 1)
        else:
            for c in range(cols):
                self._grid.setColumnStretch(c, 1)

    def _on_filter_changed(self, cat_id: str) -> None:
        self._active_filter = cat_id
        self._populate_grid()

    def retranslate_ui(self) -> None:
        self._header.setText(tr("nav_tools"))
        self._sub.setText(tr("tools_page_subtitle"))
        self._chip_bar.retranslate_ui()
        # Rebuild grid so card text updates with new locale.
        self._populate_grid()
