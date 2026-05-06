"""Home Dashboard and Tools Grid pages — Phase 2 UI overhaul."""
from __future__ import annotations

import os
from typing import Callable

from core.i18n import tr

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
    "watermark":     "#0E7490",  # cyan-700 — deep teal
    "frame_grabber": "#8B5CF6",  # violet-500
    "palette":       "#F43F5E",  # rose-500
    "bg_eraser":        "#10B981",  # emerald-500
    "vocal_isolator":   "#A855F7",  # purple-500
    "upscaler":         "#0EA5E9",  # sky-500
    "pdf_toolkit":      "#EF4444",  # red-500
    "jumpcut":          "#F59E0B",  # amber-500
    "history":          "#6B7280",  # gray
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
    ("pdf_toolkit",     "document.svg",        "tool_pdf_toolkit_name",     "tool_pdf_toolkit_desc",    17),
    ("jumpcut",         "jumpcut.svg",         "tool_jumpcut_name",         "tool_jumpcut_desc",        18),
    ("history",         "history.svg",         "tool_history_name",         "tool_history_desc",        19),
]

_QUICK_TOOLS_META: list[tuple[str, str, str, str, int]] = [
    ("download", "download.svg", "quick_download_name", "quick_download_desc", 0),
    ("compress", "compress.svg", "quick_compress_name", "quick_compress_desc", 5),
    ("convert",  "convert.svg",  "quick_convert_name",  "quick_convert_desc",  1),
    ("merge",    "merge.svg",    "quick_merge_name",    "quick_merge_desc",    6),
]


def _resolved_tools(meta: list) -> list[tuple[str, str, str, str, int]]:
    """Resolve translation keys in tool metadata to current-language strings."""
    return [(tid, icon, tr(nk), tr(dk), idx) for tid, icon, nk, dk, idx in meta]


def _all_tools() -> list[tuple[str, str, str, str, int]]:
    return _resolved_tools(_ALL_TOOLS_META)


def _home_tools() -> list[tuple[str, str, str, str, int]]:
    return _resolved_tools(_ALL_TOOLS_META[:7])


def _quick_tools() -> list[tuple[str, str, str, str, int]]:
    return _resolved_tools(_QUICK_TOOLS_META)


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

    def set_text(self, text: str) -> None:
        self._text = text
        self.update()
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

        self._title_lbl = _GradientTitleLabel(tr("welcome_title"))
        self._sub_lbl = QLabel(tr("hero_subtitle"))
        self._sub_lbl.setObjectName("HeroSubtitle")
        sub = self._sub_lbl
        left.addWidget(self._title_lbl)
        left.addWidget(self._sub_lbl)
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
        layout.addWidget(icon_lbl)

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
        self._title_lbl = QLabel(title)
        self._title_lbl.setObjectName("QuickCardTitle")
        self._sub_lbl = QLabel(subtitle)
        self._sub_lbl.setObjectName("QuickCardSub")
        text_col.addWidget(self._title_lbl)
        text_col.addWidget(self._sub_lbl)
        layout.addLayout(text_col)
        layout.addStretch()

    def update_text(self, title: str, subtitle: str) -> None:
        self._title_lbl.setText(title)
        self._sub_lbl.setText(subtitle)


class ViewAllCard(_ClickableFrame):
    def update_text(self) -> None:
        self._lbl.setText(tr("home_view_all"))

    def __init__(self, show_tools_cb: Callable[[], None], parent=None) -> None:
        super().__init__(show_tools_cb, parent)
        self.setObjectName("ViewAllCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._lbl = QLabel(tr("home_view_all"))
        self._lbl.setObjectName("ViewAllLabel")
        layout.addWidget(self._lbl)


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
        self._navigate_cb = navigate_cb
        self._show_tools_cb = show_tools_cb

        content = QWidget()
        self._root = QVBoxLayout(content)
        self._root.setContentsMargins(32, 32, 32, 32)
        self._root.setSpacing(28)

        # Hero
        self._hero = HeroBanner()
        self._root.addWidget(self._hero)

        # Quick Access header
        qa_hdr = QHBoxLayout()
        self._qa_lbl = QLabel(tr("home_quick_access"))
        self._qa_lbl.setObjectName("SectionLabel")
        qa_hdr.addWidget(self._qa_lbl)
        qa_hdr.addStretch()
        self._root.addLayout(qa_hdr)

        # Quick Access cards
        self._quick_row = QHBoxLayout()
        self._quick_row.setSpacing(12)
        self._quick_cards: list[QuickAccessCard] = []
        self._view_all_card = ViewAllCard(show_tools_cb)
        for tool_id, icon_file, title, sub, idx in _quick_tools():
            card = QuickAccessCard(tool_id, icon_file, title, sub, idx, navigate_cb)
            self._quick_cards.append(card)
            self._quick_row.addWidget(card)
        self._quick_row.addWidget(self._view_all_card)
        self._root.addLayout(self._quick_row)

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
        self._qa_lbl.setText(tr("home_quick_access"))
        self._tools_lbl.setText(tr("home_tools_section"))
        self._view_all_card.update_text()
        if self._more_tools_card:
            self._more_tools_card.update_text()
        for card, (_, _, title, sub, _idx) in zip(self._quick_cards, _quick_tools()):
            card.update_text(title, sub)
        for card, (_, _, title, desc, _idx) in zip(self._tool_cards, _home_tools()):
            card.update_text(title, desc)


class ToolsPage(QScrollArea):
    """Full tools grid page — all tools."""

    def __init__(self, navigate_cb: Callable[[int], None], parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._navigate_cb = navigate_cb

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

        self._tool_cards: list[ToolCard] = []
        grid_widget = QWidget()
        self._grid = QGridLayout(grid_widget)
        self._grid.setSpacing(16)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._populate_grid()
        root.addWidget(grid_widget)
        root.addStretch()

        self.setWidget(content)

    def _populate_grid(self) -> None:
        cols = 4
        self._tool_cards.clear()
        for i, (tool_id, icon_file, title, desc, idx) in enumerate(_all_tools()):
            card = ToolCard(tool_id, icon_file, title, desc, idx, self._navigate_cb)
            self._tool_cards.append(card)
            self._grid.addWidget(card, i // cols, i % cols)

    def retranslate_ui(self) -> None:
        self._header.setText(tr("nav_tools"))
        self._sub.setText(tr("tools_page_subtitle"))
        for card, (_, _, title, desc, _idx) in zip(self._tool_cards, _all_tools()):
            card.update_text(title, desc)
