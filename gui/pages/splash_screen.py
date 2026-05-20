"""Static splash screen — shown once on app launch."""
from __future__ import annotations

import os

from core.i18n import tr
from core.paths import resource_path

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import (
    QColor, QLinearGradient, QRadialGradient,
    QPainter, QPen, QBrush, QPixmap, QFont,
)
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton,
    QGraphicsOpacityEffect, QSizePolicy,
)

_APP_LOGO = resource_path("assets", "videl_logo.png")
_LOGO_CY_FRAC = 0.38


class _SplashBackground(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._logo_px: QPixmap | None = None
        self._logo_draw = 260

    def set_logo(self, px: QPixmap, draw_size: int) -> None:
        self._logo_px = px
        self._logo_draw = draw_size
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()

        # Base gradient
        base = QLinearGradient(0, 0, w, h)
        base.setColorAt(0.00, QColor("#0D1530"))
        base.setColorAt(0.55, QColor("#0A1020"))
        base.setColorAt(1.00, QColor("#060C1A"))
        painter.setBrush(QBrush(base))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 0, w, h)

        # Centre glow (static)
        cx, cy = w * 0.50, h * _LOGO_CY_FRAC
        glow = QRadialGradient(cx, cy, max(w, h) * 0.60)
        glow.setColorAt(0.00, QColor(59, 130, 246, 80))
        glow.setColorAt(0.40, QColor(37,  99, 235, 40))
        glow.setColorAt(1.00, QColor(0,   0,   0,  0))
        painter.setBrush(QBrush(glow))
        painter.drawRect(0, 0, w, h)

        # Upper-right orb (static)
        orb = QRadialGradient(w * 0.78, h * 0.28, max(w, h) * 0.38)
        orb.setColorAt(0.00, QColor(96, 165, 250, 38))
        orb.setColorAt(1.00, QColor(0,   0,   0,  0))
        painter.setBrush(QBrush(orb))
        painter.drawRect(0, 0, w, h)

        # Logo
        px = self._logo_px
        if px and not px.isNull():
            scaled = px.scaled(
                self._logo_draw, self._logo_draw,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(
                int(cx - scaled.width()  / 2),
                int(cy - scaled.height() / 2),
                scaled,
            )

        painter.end()


class _GradientLabel(QWidget):
    def __init__(self, text: str, font_size: int = 34, parent=None) -> None:
        super().__init__(parent)
        self._text = text
        self._font = QFont()
        self._font.setPointSize(font_size)
        self._font.setBold(True)
        self._font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(font_size * 2 + 4)

    def set_text(self, text: str) -> None:
        self._text = text
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self._font)
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.00, QColor("#93C5FD"))
        grad.setColorAt(0.45, QColor("#E5E7EB"))
        grad.setColorAt(1.00, QColor("#9CA3AF"))
        painter.setPen(QPen(QBrush(grad), 0))
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter,
            self._text,
        )
        painter.end()


class SplashScreen(QWidget):
    ready_to_start = Signal()

    _LOGO_DRAW = 260
    _PAD       = 60

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._setup_ui()

    def _setup_ui(self) -> None:
        self._drag_pos: QPoint | None = None

        self._bg = _SplashBackground(self)
        self._bg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._bg.set_logo(QPixmap(_APP_LOGO), self._LOGO_DRAW)

        # Window controls (top-right)
        _ctrl_style = """
            QPushButton { background: transparent; color: #60748C;
                          border: none; font-size: 15px; }
            QPushButton:hover { background: rgba(255,255,255,12); color: #E5E7EB; }
        """
        _close_style = """
            QPushButton { background: transparent; color: #60748C;
                          border: none; font-size: 15px; }
            QPushButton:hover { background: #C0392B; color: #FFFFFF; }
        """
        self._btn_min = QPushButton("—", parent=self._bg)
        self._btn_min.setFixedSize(38, 38)
        self._btn_min.setCursor(Qt.CursorShape.ArrowCursor)
        self._btn_min.setStyleSheet(_ctrl_style)
        self._btn_min.clicked.connect(self.showMinimized)

        self._btn_close = QPushButton("✕", parent=self._bg)
        self._btn_close.setFixedSize(38, 38)
        self._btn_close.setCursor(Qt.CursorShape.ArrowCursor)
        self._btn_close.setStyleSheet(_close_style)
        from PySide6.QtWidgets import QApplication
        self._btn_close.clicked.connect(QApplication.instance().quit)

        self._title_lbl = _GradientLabel(tr("welcome_title"), font_size=34, parent=self._bg)
        self._title_lbl.setAutoFillBackground(False)
        self._title_lbl.setFixedWidth(560)

        self._sub_lbl = QLabel(tr("hero_subtitle").replace("\n", "  ·  "), parent=self._bg)
        self._sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub_lbl.setAutoFillBackground(False)
        self._sub_lbl.setStyleSheet(
            "font-size: 14px; color: #60748C; letter-spacing: 1.2px; background: transparent;"
        )
        self._sub_lbl.adjustSize()

        self._start_btn = QPushButton(tr("splash_get_started"), parent=self._bg)
        self._start_btn.setFixedSize(224, 50)
        self._start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_btn.setAutoFillBackground(False)
        self._start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3B82F6, stop:1 #2563EB);
                color: #FFFFFF;
                border: none;
                border-radius: 25px;
                font-size: 14px;
                font-weight: 600;
                letter-spacing: 1.4px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #60A5FA, stop:1 #3B82F6);
            }
            QPushButton:pressed { background: #1D4ED8; }
        """)
        self._start_btn.clicked.connect(self.ready_to_start.emit)

        # Show everything immediately — no entrance animations
        for widget in (self._title_lbl, self._sub_lbl, self._start_btn):
            eff = QGraphicsOpacityEffect(widget)
            eff.setOpacity(1.0)
            widget.setGraphicsEffect(eff)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        w, h = self.width(), self.height()

        self._bg.setGeometry(0, 0, w, h)

        # Window control buttons top-right
        self._btn_close.move(w - 38, 0)
        self._btn_min.move(w - 76, 0)

        logo_cy   = int(h * _LOGO_CY_FRAC)
        logo_half = self._LOGO_DRAW // 2 + self._PAD // 2
        content_y = logo_cy + logo_half + 22

        tw = self._title_lbl.width()
        self._title_lbl.move(w // 2 - tw // 2, content_y)

        self._sub_lbl.adjustSize()
        sw = self._sub_lbl.width()
        sub_y = content_y + self._title_lbl.height() + 8
        self._sub_lbl.move(w // 2 - sw // 2, sub_y)

        btn_y = sub_y + self._sub_lbl.height() + 42
        self._start_btn.move(w // 2 - self._start_btn.width() // 2, btn_y)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_pos = None

    def retranslate_ui(self) -> None:
        self._title_lbl.set_text(tr("welcome_title"))
        self._sub_lbl.setText(tr("hero_subtitle").replace("\n", "  ·  "))
        self._start_btn.setText(tr("splash_get_started"))
