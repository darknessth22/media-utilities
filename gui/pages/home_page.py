"""Home Dashboard and Tools Grid pages — Phase 2 UI overhaul."""
from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import Qt, QPoint, QRectF
from PySide6.QtGui import (
    QColor, QLinearGradient, QRadialGradient,
    QPainter, QPainterPath, QPen, QBrush, QPixmap, QFont,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel,
    QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QSizePolicy,
)

_ICONS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "icons")
_APP_LOGO  = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "videl_logo.png")

_TOOL_COLOR: dict[str, str] = {
    "download":  "#3B82F6",  # blue
    "convert":   "#22D3EE",  # cyan
    "compress":  "#22C55E",  # green
    "merge":     "#A855F7",  # purple
    "trim":      "#F97316",  # orange
    "mux":       "#EC4899",  # pink
    "gif":       "#FACC15",  # yellow
    "spatial":   "#FB923C",  # orange-400 — warm, distinct from trim
    "document":  "#38BDF8",  # sky-400 — light cyan-blue
    "scrub":     "#7C3AED",  # violet-600 — deep purple, distinct from merge
    "chunk":     "#06B6D4",  # cyan-500 — pure cyan
    "watermark": "#0E7490",  # cyan-700 — deep teal
    "history":   "#6B7280",  # gray
}

# All tools (for ToolsPage)
_ALL_TOOLS: list[tuple[str, str, str, str, int]] = [
    ("download", "download.svg", "Media Download",   "Download videos, audio, playlists\nfrom 1000+ websites.", 0),
    ("convert",  "convert.svg",  "Convert Media",    "Convert videos and audios\nto any format.",              1),
    ("compress", "compress.svg", "Compress Media",   "Compress videos and images\nwithout quality loss.",      5),
    ("merge",    "merge.svg",    "Merge Videos",     "Merge multiple videos into\none seamless output.",       6),
    ("trim",     "trim.svg",     "Trim Media",       "Trim and cut videos to your\ndesired length.",           2),
    ("mux",      "mux.svg",      "Audio Mixing",     "Mix multiple audio tracks\nlike a pro.",                 8),
    ("gif",      "gif.svg",      "GIF Creator",      "Create high-quality GIFs\nfrom videos.",                 4),
    ("spatial",  "spatial.svg",  "Transform Media",  "Resize, crop, and rotate\nvideo files.",                 7),
    ("document",  "document.svg", "Document Convert",  "Convert documents between\nformats.",                    3),
    ("scrub",     "scrub.svg",     "Metadata Scrubber", "Strip GPS, timestamps and\nEXIF data from media.",  9),
    ("chunk",     "chunk.svg",     "Auto-Chunker",      "Split files by duration\nor size (stream copy).", 10),
    ("watermark", "watermark.svg", "Batch Watermark",   "Stamp logos or text across\nan entire directory.", 11),
    ("history",   "history.svg", "History",           "View past operations\nand results.",                    12),
]

# 7 tools shown on Home, then "+ More Tools" card
_HOME_TOOLS: list[tuple[str, str, str, str, int]] = _ALL_TOOLS[:7]

_QUICK_TOOLS: list[tuple[str, str, str, str, int]] = [
    ("download", "download.svg", "Media Download", "Download from 1000+ sites", 0),
    ("compress", "compress.svg", "Compress Media", "Reduce file size",           5),
    ("convert",  "convert.svg",  "Convert Media",  "Convert to any format",      1),
    ("merge",    "merge.svg",    "Merge Videos",   "Combine multiple videos",    6),
]


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


# ── Clickable base ────────────────────────────────────────────────────────────

class _ClickableFrame(QFrame):
    def __init__(self, callback: Callable[[], None], parent=None) -> None:
        super().__init__(parent)
        self._cb = callback

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._cb()
        super().mousePressEvent(event)


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


# ── Hero Banner (fully custom painted) ───────────────────────────────────────

class HeroBanner(QFrame):
    """
    Layered hero widget:
      1. Deep navy base gradient (135° linear)
      2. Right-side radial blue glow
      3. Subtle wave / flow line
      4. Logo with soft halo (right side, vertically centred)
      5. Text content on left (gradient title + subtitle)
    """

    _LOGO_W = 200
    _LOGO_H = 150

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("HeroBanner")
        self.setMinimumHeight(200)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        # Load logo once
        raw = QPixmap(_APP_LOGO)
        self._logo_px = (
            raw.scaled(
                self._LOGO_W, self._LOGO_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if not raw.isNull() else QPixmap()
        )

        # Content layout (painted bg, children on top)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(44, 36, self._LOGO_W + 32, 36)
        outer.setSpacing(0)

        left = QVBoxLayout()
        left.setSpacing(12)

        self._title_lbl = _GradientTitleLabel("Welcome to Videl")
        sub = QLabel("All-in-one media toolkit for creators.\nFast. Simple. Powerful.")
        sub.setObjectName("HeroSubtitle")
        left.addWidget(self._title_lbl)
        left.addWidget(sub)
        left.addStretch()

        outer.addLayout(left)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # 1. Base gradient — deep navy 135°
        base = QLinearGradient(0, 0, w, h)
        base.setColorAt(0.00, QColor("#0D1530"))
        base.setColorAt(0.40, QColor("#0A1020"))
        base.setColorAt(1.00, QColor("#060C1A"))
        painter.setBrush(QBrush(base))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, w, h, 16, 16)

        # 2. Right-side radial blue glow
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

        # 3. Subtle wave / flow line
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

        # 4. Logo halo (soft radial behind logo position)
        logo_cx = w - self._LOGO_W // 2 - 20
        logo_cy = h // 2
        halo = QRadialGradient(logo_cx, logo_cy, 130)
        halo.setColorAt(0.00, QColor(96, 165, 250, 55))
        halo.setColorAt(1.00, QColor(0,   0,   0,  0))
        painter.setBrush(QBrush(halo))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            int(logo_cx - 130), int(logo_cy - 130), 260, 260
        )

        # 5. Rounded border
        border_pen = QPen(QColor(30, 58, 138, 120), 1)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(0, 0, w - 1, h - 1, 16, 16)

        painter.end()

        # 6. Draw logo centred in right zone, on top of glow
        if not self._logo_px.isNull():
            lx = w - self._logo_px.width() - 20
            ly = (h - self._logo_px.height()) // 2
            # Use a fresh painter scoped to logo draw
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
        super().__init__(lambda: navigate_cb(section_idx), parent)
        self.setObjectName("ToolCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        color = _TOOL_COLOR.get(tool_id, "#6B7280")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setPixmap(_load_icon(icon_file, 40, color))
        layout.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("ToolCardTitle")
        layout.addWidget(title_lbl)

        desc_lbl = QLabel(desc)
        desc_lbl.setObjectName("ToolCardDesc")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)
        layout.addStretch()


class MoreToolsCard(_ClickableFrame):
    """The 8th card — 'More Tools' — opens the Tools page."""

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
        layout.addWidget(icon_lbl)

        title_lbl = QLabel("More Tools")
        title_lbl.setObjectName("ToolCardTitle")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)

        desc_lbl = QLabel("Explore more\npowerful utilities.")
        desc_lbl.setObjectName("ToolCardDesc")
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)
        layout.addStretch()


# ── Quick Access cards ────────────────────────────────────────────────────────

class QuickAccessCard(_ClickableFrame):
    def __init__(
        self,
        tool_id: str,
        icon_file: str,
        title: str,
        subtitle: str,
        section_idx: int,
        navigate_cb: Callable[[int], None],
        parent=None,
    ) -> None:
        super().__init__(lambda: navigate_cb(section_idx), parent)
        self.setObjectName("QuickCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        color = _TOOL_COLOR.get(tool_id, "#6B7280")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(28, 28)
        icon_lbl.setPixmap(_load_icon(icon_file, 28, color))
        layout.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("QuickCardTitle")
        s = QLabel(subtitle)
        s.setObjectName("QuickCardSub")
        text_col.addWidget(t)
        text_col.addWidget(s)
        layout.addLayout(text_col)
        layout.addStretch()


class ViewAllCard(_ClickableFrame):
    def __init__(self, show_tools_cb: Callable[[], None], parent=None) -> None:
        super().__init__(show_tools_cb, parent)
        self.setObjectName("ViewAllCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl = QLabel("View All Tools  →")
        lbl.setObjectName("ViewAllLabel")
        layout.addWidget(lbl)


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
    """Landing screen: painted hero + quick access + 7-tool grid + More Tools."""

    def __init__(
        self,
        navigate_cb: Callable[[int], None],
        show_tools_cb: Callable[[], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(28)

        # Hero
        root.addWidget(HeroBanner())

        # Quick Access
        qa_hdr = QHBoxLayout()
        qa_lbl = QLabel("QUICK ACCESS")
        qa_lbl.setObjectName("SectionLabel")
        qa_hdr.addWidget(qa_lbl)
        qa_hdr.addStretch()
        root.addLayout(qa_hdr)

        quick_row = QHBoxLayout()
        quick_row.setSpacing(12)
        for tool_id, icon_file, title, sub, idx in _QUICK_TOOLS:
            quick_row.addWidget(
                QuickAccessCard(tool_id, icon_file, title, sub, idx, navigate_cb)
            )
        quick_row.addWidget(ViewAllCard(show_tools_cb))
        root.addLayout(quick_row)

        # Tools (7 items + More Tools card)
        tools_lbl = QLabel("TOOLS")
        tools_lbl.setObjectName("SectionLabel")
        root.addWidget(tools_lbl)

        root.addWidget(
            _build_tools_grid(
                _HOME_TOOLS,
                navigate_cb,
                cols=4,
                more_tools_cb=show_tools_cb,
            )
        )
        root.addStretch()

        self.setWidget(content)


class ToolsPage(QScrollArea):
    """Full tools grid page — all tools."""

    def __init__(self, navigate_cb: Callable[[int], None], parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(16)

        header = QLabel("Tools")
        header.setObjectName("PageHeader")
        root.addWidget(header)

        sub = QLabel("Select a tool to get started.")
        sub.setObjectName("TextSecondary")
        root.addWidget(sub)

        root.addWidget(_build_tools_grid(_ALL_TOOLS, navigate_cb, cols=4))
        root.addStretch()

        self.setWidget(content)
