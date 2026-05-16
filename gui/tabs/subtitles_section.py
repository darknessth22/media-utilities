"""Subtitles tab — burn-in SRT/VTT/ASS into a video via FFmpeg libass."""
from __future__ import annotations

import os
import time

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import (
    QBrush, QColor, QDesktopServices, QDragEnterEvent, QDropEvent,
    QFont, QFontDatabase, QFontMetrics, QPainter, QPainterPath, QPen,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.subtitles import (
    burn_subtitles,
    extract_embedded_sub,
    probe_duration,
    probe_embedded_subs,
    probe_resolution,
    read_sub_preview,
    _VIDEO_EXTS,
    _SUB_EXTS,
)
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker
from utils.ffmpeg import detect_hw_encoders


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


def _fmt_hms(sec: float) -> str:
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


_HW_LABELS = [
    ("none", "None (CPU)"),
    ("nvidia", "NVIDIA NVENC"),
    ("amd", "AMD AMF"),
    ("intel", "Intel QuickSync"),
]

_PRESETS = [
    ("balanced", "Balanced", 18, "medium"),
    ("fast", "Fast", 23, "veryfast"),
    ("hq", "High Quality", 16, "slow"),
]

_ENCODINGS = [
    ("auto", "Auto-detect"),
    ("utf-8", "UTF-8"),
    ("utf-8-sig", "UTF-8 BOM"),
    ("windows-1256", "Windows-1256 (Arabic)"),
    ("cp1252", "Windows-1252 (Latin)"),
    ("latin-1", "Latin-1"),
]


class _ColorButton(QPushButton):
    """Small swatch button — click opens QColorDialog."""

    color_changed = Signal(str)

    def __init__(self, initial: str = "#FFFFFF", parent=None, *, allow_alpha: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("ColorSwatch")
        self.setFixedSize(36, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._allow_alpha = allow_alpha
        self._color = initial
        self._apply()
        self.clicked.connect(self._pick)

    def color(self) -> str:
        return self._color

    def set_color(self, hex_str: str) -> None:
        if not hex_str:
            return
        self._color = hex_str if hex_str.startswith("#") else f"#{hex_str}"
        self._apply()

    def _apply(self) -> None:
        # Scope by objectName — otherwise the dialog opened with this widget
        # as parent inherits the swatch's QPushButton background rule and
        # its OK/Cancel become invisible.
        # Show a checker pattern peek through transparency.
        col = QColor(self._color)
        rgb = col.name().upper()  # solid base for the swatch fill
        self.setStyleSheet(
            f"QPushButton#ColorSwatch {{ background: {rgb};"
            f" border: 1px solid #444; border-radius: 4px; }}"
            f"QPushButton#ColorSwatch:hover {{ border: 1px solid #888; }}"
        )
        if self._allow_alpha and col.alpha() < 255:
            self.setText("∅" if col.alpha() == 0 else f"α{col.alpha()}")
        else:
            self.setText("")

    def _pick(self) -> None:
        parent = self.window() or self
        opts = QColorDialog.ColorDialogOption.ShowAlphaChannel if self._allow_alpha \
            else QColorDialog.ColorDialogOption(0)
        c = QColorDialog.getColor(QColor(self._color), parent, "Pick color", opts)
        if c.isValid():
            fmt = QColor.NameFormat.HexArgb if self._allow_alpha and c.alpha() < 255 \
                else QColor.NameFormat.HexRgb
            self._color = c.name(fmt).upper()
            self._apply()
            self.color_changed.emit(self._color)


class _SubtitlePreview(QWidget):
    """WYSIWYG preview — draws sample text with the chosen libass styling.

    Renders font + size + bold/italic, primary fill, outline (stroked path),
    optional shadow (offset stroke), and optional background box.
    Uses a dark backdrop to mimic a video frame.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(80)
        self._text = "The quick brown fox  •  أبجد هوز حطي"
        self._family = "Arial"
        self._size_pt = 16
        self._bold = False
        self._italic = False
        self._color = "#FFFFFF"
        self._outline_color = "#000000"
        self._outline_w = 2
        self._shadow_w = 0
        self._back_color: str | None = None

    def setText(self, t: str) -> None:
        self._text = t
        self.update()

    def set_state(
        self, *, family: str, size_pt: int, bold: bool, italic: bool,
        color: str, outline_color: str, outline_w: int,
        shadow_w: int, back_color: str | None,
    ) -> None:
        self._family = family
        self._size_pt = max(8, int(size_pt))
        self._bold = bold
        self._italic = italic
        self._color = color
        self._outline_color = outline_color
        self._outline_w = max(0, int(outline_w))
        self._shadow_w = max(0, int(shadow_w))
        self._back_color = back_color
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Backdrop — fake video frame
        p.fillRect(self.rect(), QColor("#0D1117"))

        font = QFont(self._family)
        # Scale: ASS FontSize ≈ pixels at 720p. Preview uses point size as-is
        # but clamps so big values don't overflow the card.
        max_px = max(14, int(self.height() * 0.55))
        font.setPixelSize(min(max_px, self._size_pt))
        font.setBold(self._bold)
        font.setItalic(self._italic)

        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(self._text)
        text_h = fm.height()
        x = (self.width() - text_w) / 2
        y = (self.height() + fm.ascent() - fm.descent()) / 2

        # Background box
        if self._back_color:
            pad_x, pad_y = 8, 4
            p.fillRect(
                int(x - pad_x), int(y - fm.ascent() - pad_y),
                int(text_w + 2 * pad_x), int(text_h + 2 * pad_y),
                QColor(self._back_color),
            )

        path = QPainterPath()
        path.addText(x, y, font, self._text)

        # Shadow — offset filled copy
        if self._shadow_w > 0:
            shadow = QPainterPath()
            shadow.addText(x + self._shadow_w, y + self._shadow_w, font, self._text)
            p.fillPath(shadow, QBrush(QColor(0, 0, 0, 180)))

        # Outline
        if self._outline_w > 0:
            pen = QPen(QColor(self._outline_color))
            pen.setWidthF(self._outline_w * 1.5)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPath(path)

        # Fill
        p.fillPath(path, QBrush(QColor(self._color)))


class SubtitlesSection(QScrollArea):
    """Burn subtitles into a video. Audio stream-copied, video re-encoded."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._video_duration: float = 0.0
        self._burn_start_ts: float = 0.0
        self._extracted_sub_tmp: str | None = None

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAcceptDrops(True)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_video_card())
        layout.addWidget(self._build_sub_card())
        layout.addWidget(self._build_style_card())
        layout.addWidget(self._build_encode_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

        self.setWidget(content)
        self._refresh_style_preview()

    # ── Drag & drop ──────────────────────────────────────────────────────────
    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent) -> None:
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if p:
                self.populate_file(p)
        e.acceptProposedAction()

    # ── Video card ───────────────────────────────────────────────────────────
    def _build_video_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_video = _section_header(tr("hdr_source_video"))
        layout.addWidget(self._hdr_video)
        row = QHBoxLayout()
        self._video_input = QLineEdit()
        self._video_input.setObjectName("PillInput")
        self._video_input.setPlaceholderText(tr("ph_vid"))
        self._video_input.editingFinished.connect(self._on_video_path_changed)
        row.addWidget(self._video_input)
        self._browse_video_btn = QPushButton(tr("btn_browse"))
        self._browse_video_btn.setObjectName("BrowseBtn")
        self._browse_video_btn.setFixedWidth(90)
        self._browse_video_btn.clicked.connect(self._browse_video)
        row.addWidget(self._browse_video_btn)
        layout.addLayout(row)

        self._video_info = QLabel("")
        self._video_info.setObjectName("TextMuted")
        self._video_info.setStyleSheet("font-size: 12px;")
        self._video_info.setVisible(False)
        layout.addWidget(self._video_info)

        track_row = QHBoxLayout()
        track_row.setSpacing(8)
        self._lbl_embedded = QLabel(tr("lbl_embedded_track"))
        track_row.addWidget(self._lbl_embedded)
        self._embedded_combo = QComboBox()
        self._embedded_combo.setMinimumWidth(280)
        track_row.addWidget(self._embedded_combo, 1)
        self._extract_btn = QPushButton(tr("btn_use_embedded"))
        self._extract_btn.clicked.connect(self._use_embedded_sub)
        track_row.addWidget(self._extract_btn)
        self._embedded_row_widget = QWidget()
        self._embedded_row_widget.setLayout(track_row)
        self._embedded_row_widget.setVisible(False)
        layout.addWidget(self._embedded_row_widget)
        return card

    # ── Sub card ─────────────────────────────────────────────────────────────
    def _build_sub_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_sub = _section_header(tr("hdr_subtitle_file"))
        layout.addWidget(self._hdr_sub)
        row = QHBoxLayout()
        self._sub_input = QLineEdit()
        self._sub_input.setObjectName("PillInput")
        self._sub_input.setPlaceholderText(tr("ph_subtitle_file"))
        self._sub_input.editingFinished.connect(self._refresh_sub_preview)
        row.addWidget(self._sub_input)
        self._browse_sub_btn = QPushButton(tr("btn_browse"))
        self._browse_sub_btn.setObjectName("BrowseBtn")
        self._browse_sub_btn.setFixedWidth(90)
        self._browse_sub_btn.clicked.connect(self._browse_sub)
        row.addWidget(self._browse_sub_btn)
        layout.addLayout(row)

        opts = QHBoxLayout()
        opts.setSpacing(12)
        self._lbl_encoding = QLabel(tr("lbl_encoding"))
        opts.addWidget(self._lbl_encoding)
        self._encoding_combo = QComboBox()
        for k, lbl in _ENCODINGS:
            self._encoding_combo.addItem(lbl, k)
        self._encoding_combo.currentIndexChanged.connect(self._refresh_sub_preview)
        opts.addWidget(self._encoding_combo)

        self._lbl_offset = QLabel(tr("lbl_time_offset"))
        opts.addWidget(self._lbl_offset)
        self._offset_spin = QDoubleSpinBox()
        self._offset_spin.setRange(-600.0, 600.0)
        self._offset_spin.setSingleStep(0.1)
        self._offset_spin.setDecimals(2)
        self._offset_spin.setSuffix(" s")
        self._offset_spin.setFixedWidth(100)
        opts.addWidget(self._offset_spin)

        self._trim_overlaps_cb = QCheckBox(tr("lbl_trim_overlaps"))
        self._trim_overlaps_cb.setToolTip(tr("hint_trim_overlaps"))
        opts.addWidget(self._trim_overlaps_cb)
        opts.addStretch()
        layout.addLayout(opts)

        self._sub_preview = QLabel("")
        self._sub_preview.setObjectName("Card")
        self._sub_preview.setWordWrap(True)
        self._sub_preview.setMinimumHeight(60)
        self._sub_preview.setStyleSheet(
            "QLabel#Card { border-radius: 6px; background: #1C2128;"
            " color: #C9D1D9; padding: 8px; font-size: 12px; }"
        )
        self._sub_preview.setVisible(False)
        layout.addWidget(self._sub_preview)
        return card

    # ── Style card ───────────────────────────────────────────────────────────
    def _build_style_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_style = _section_header(tr("hdr_subtitle_style"))
        layout.addWidget(self._hdr_style)

        font_row = QHBoxLayout()
        font_row.setSpacing(12)
        self._lbl_font = QLabel(tr("lbl_font"))
        font_row.addWidget(self._lbl_font)
        self._font_combo = QFontComboBox()
        self._font_combo.setEditable(False)
        self._font_combo.setWritingSystem(QFontDatabase.WritingSystem.Any)
        self._font_combo.setCurrentFont(QFont("Arial"))
        self._font_combo.setMinimumWidth(280)
        self._font_combo.setMaxVisibleItems(15)
        self._font_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._font_combo.setStyleSheet(
            "QFontComboBox::drop-down { border: none; width: 24px; }"
            "QFontComboBox::down-arrow {"
            " image: none; width: 0; height: 0;"
            " border-left: 5px solid transparent;"
            " border-right: 5px solid transparent;"
            " border-top: 6px solid #8B949E;"
            " margin-right: 8px; margin-top: 2px;"
            "}"
        )
        font_row.addWidget(self._font_combo, 1)

        self._bold_cb = QCheckBox(tr("lbl_bold"))
        self._italic_cb = QCheckBox(tr("lbl_italic"))
        font_row.addWidget(self._bold_cb)
        font_row.addWidget(self._italic_cb)
        layout.addLayout(font_row)

        # Live WYSIWYG preview
        self._font_preview = _SubtitlePreview()
        self._font_preview.setText(tr("font_preview_sample"))
        self._font_combo.currentFontChanged.connect(lambda _f: self._refresh_style_preview())
        self._bold_cb.toggled.connect(self._refresh_style_preview)
        self._italic_cb.toggled.connect(self._refresh_style_preview)
        layout.addWidget(self._font_preview)

        # Size, colors, outline
        row = QHBoxLayout()
        row.setSpacing(10)
        self._lbl_font_size = QLabel(tr("lbl_font_size"))
        row.addWidget(self._lbl_font_size)
        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(8, 120)
        self._font_size_spin.setValue(28)
        self._font_size_spin.setFixedWidth(70)
        self._font_size_spin.valueChanged.connect(self._refresh_style_preview)
        row.addWidget(self._font_size_spin)

        self._lbl_color = QLabel(tr("lbl_font_color"))
        row.addWidget(self._lbl_color)
        self._color_btn = _ColorButton("#FFFFFF")
        self._color_btn.color_changed.connect(lambda _c: self._refresh_style_preview())
        row.addWidget(self._color_btn)

        self._lbl_outline_color = QLabel(tr("lbl_outline_color"))
        row.addWidget(self._lbl_outline_color)
        self._outline_color_btn = _ColorButton("#000000", allow_alpha=True)
        self._outline_color_btn.color_changed.connect(lambda _c: self._refresh_style_preview())
        row.addWidget(self._outline_color_btn)

        self._lbl_back_color = QLabel(tr("lbl_back_color"))
        row.addWidget(self._lbl_back_color)
        self._back_color_btn = _ColorButton("#000000", allow_alpha=True)
        self._back_color_btn.color_changed.connect(lambda _c: self._refresh_style_preview())
        row.addWidget(self._back_color_btn)
        row.addStretch()
        layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self._lbl_outline = QLabel(tr("lbl_outline"))
        row2.addWidget(self._lbl_outline)
        self._outline_spin = QSpinBox()
        self._outline_spin.setRange(0, 8)
        self._outline_spin.setValue(2)
        self._outline_spin.setFixedWidth(60)
        self._outline_spin.valueChanged.connect(self._refresh_style_preview)
        row2.addWidget(self._outline_spin)

        self._lbl_shadow = QLabel(tr("lbl_shadow"))
        row2.addWidget(self._lbl_shadow)
        self._shadow_spin = QSpinBox()
        self._shadow_spin.setRange(0, 8)
        self._shadow_spin.setValue(0)
        self._shadow_spin.setFixedWidth(60)
        self._shadow_spin.valueChanged.connect(self._refresh_style_preview)
        row2.addWidget(self._shadow_spin)

        self._lbl_bg_box = QLabel(tr("lbl_bg_box"))
        row2.addWidget(self._lbl_bg_box)
        self._bg_box_cb = QCheckBox()
        self._bg_box_cb.toggled.connect(self._refresh_style_preview)
        row2.addWidget(self._bg_box_cb)

        self._lbl_margin_v = QLabel(tr("lbl_margin_v"))
        row2.addWidget(self._lbl_margin_v)
        self._margin_v_spin = QSpinBox()
        self._margin_v_spin.setRange(0, 400)
        self._margin_v_spin.setValue(20)
        self._margin_v_spin.setFixedWidth(70)
        row2.addWidget(self._margin_v_spin)
        row2.addStretch()
        layout.addLayout(row2)

        return card

    # ── Encode card ──────────────────────────────────────────────────────────
    def _build_encode_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_encode = _section_header(tr("hdr_encode_settings"))
        layout.addWidget(self._hdr_encode)

        row = QHBoxLayout()
        row.setSpacing(12)
        self._lbl_preset = QLabel(tr("lbl_preset"))
        row.addWidget(self._lbl_preset)
        self._preset_combo = QComboBox()
        for k, lbl, _crf, _libx in _PRESETS:
            self._preset_combo.addItem(lbl, k)
        self._preset_combo.currentIndexChanged.connect(self._apply_preset)
        row.addWidget(self._preset_combo)

        self._lbl_crf = QLabel(tr("lbl_crf"))
        row.addWidget(self._lbl_crf)
        self._crf_spin = QSpinBox()
        self._crf_spin.setRange(14, 32)
        self._crf_spin.setValue(18)
        self._crf_spin.setFixedWidth(70)
        row.addWidget(self._crf_spin)

        self._lbl_hw = QLabel(tr("lbl_hw_accel"))
        row.addWidget(self._lbl_hw)
        self._hw_combo = QComboBox()
        encoders = detect_hw_encoders()
        model: QStandardItemModel = self._hw_combo.model()  # type: ignore[assignment]
        default_idx = 0
        for i, (key, label) in enumerate(_HW_LABELS):
            display = label
            supported = key == "none" or key in encoders
            if not supported:
                display = f"{label}  —  " + tr("hw_unavailable")
            self._hw_combo.addItem(display, key)
            if not supported:
                item = model.item(i)
                if item is not None:
                    item.setEnabled(False)
            elif key != "none" and default_idx == 0:
                default_idx = i
        self._hw_combo.setCurrentIndex(default_idx)
        row.addWidget(self._hw_combo)
        row.addStretch()
        layout.addLayout(row)
        return card

    # ── Output card ──────────────────────────────────────────────────────────
    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_out = _section_header(tr("hdr_output_folder"))
        layout.addWidget(self._hdr_out)
        self._hint_out = QLabel(tr("hint_save_alongside"))
        self._hint_out.setObjectName("TextMuted")
        self._hint_out.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint_out)
        row = QHBoxLayout()
        self._out_input = QLineEdit()
        self._out_input.setObjectName("PillInput")
        self._out_input.setPlaceholderText(tr("ph_same_dir_src"))
        if self._settings.output_folder:
            self._out_input.setText(self._settings.output_folder)
        row.addWidget(self._out_input)
        self._browse_out_btn = QPushButton(tr("btn_browse"))
        self._browse_out_btn.setObjectName("BrowseBtn")
        self._browse_out_btn.setFixedWidth(90)
        self._browse_out_btn.clicked.connect(self._browse_out)
        row.addWidget(self._browse_out_btn)
        layout.addLayout(row)

        tmpl_row = QHBoxLayout()
        tmpl_row.setSpacing(8)
        self._lbl_filename = QLabel(tr("lbl_filename_template"))
        tmpl_row.addWidget(self._lbl_filename)
        self._filename_input = QLineEdit("{name}_subbed")
        self._filename_input.setPlaceholderText("{name}_subbed")
        tmpl_row.addWidget(self._filename_input, 1)
        layout.addLayout(tmpl_row)
        self._tmpl_hint = QLabel(tr("hint_filename_template"))
        self._tmpl_hint.setObjectName("TextMuted")
        self._tmpl_hint.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._tmpl_hint)
        return card

    # ── Progress card ────────────────────────────────────────────────────────
    def _build_progress_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("TaskProgressBar")
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._eta_label = QLabel("")
        self._eta_label.setObjectName("TextMuted")
        self._eta_label.setStyleSheet("font-size: 12px;")
        self._eta_label.setVisible(False)
        layout.addWidget(self._eta_label)

        self._cancel_btn = QPushButton(tr("btn_cancel"))
        self._cancel_btn.setFixedWidth(120)
        self._cancel_btn.clicked.connect(self._cancel_burn)
        self._cancel_btn.setVisible(False)
        layout.addWidget(self._cancel_btn)

        self._result_label = QLabel()
        self._result_label.setObjectName("TextSecondary")
        self._result_label.setWordWrap(True)
        self._result_label.setVisible(False)
        layout.addWidget(self._result_label)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._open_folder_btn = QPushButton(tr("btn_open_folder"))
        self._open_folder_btn.setVisible(False)
        self._open_folder_btn.clicked.connect(self._open_folder)
        actions.addWidget(self._open_folder_btn)
        self._play_btn = QPushButton(tr("btn_play"))
        self._play_btn.setVisible(False)
        self._play_btn.clicked.connect(self._play_output)
        actions.addWidget(self._play_btn)
        actions.addStretch()
        layout.addLayout(actions)
        self._last_output: str | None = None
        return card

    def retranslate_ui(self) -> None:
        self._hdr_video.setText(tr("hdr_source_video"))
        self._video_input.setPlaceholderText(tr("ph_vid"))
        self._browse_video_btn.setText(tr("btn_browse"))
        self._lbl_embedded.setText(tr("lbl_embedded_track"))
        self._extract_btn.setText(tr("btn_use_embedded"))
        self._hdr_sub.setText(tr("hdr_subtitle_file"))
        self._sub_input.setPlaceholderText(tr("ph_subtitle_file"))
        self._browse_sub_btn.setText(tr("btn_browse"))
        self._lbl_encoding.setText(tr("lbl_encoding"))
        self._lbl_offset.setText(tr("lbl_time_offset"))
        self._trim_overlaps_cb.setText(tr("lbl_trim_overlaps"))
        self._trim_overlaps_cb.setToolTip(tr("hint_trim_overlaps"))
        self._hdr_style.setText(tr("hdr_subtitle_style"))
        self._lbl_font.setText(tr("lbl_font"))
        self._bold_cb.setText(tr("lbl_bold"))
        self._italic_cb.setText(tr("lbl_italic"))
        self._font_preview.setText(tr("font_preview_sample"))
        self._refresh_style_preview()
        self._lbl_font_size.setText(tr("lbl_font_size"))
        self._lbl_color.setText(tr("lbl_font_color"))
        self._lbl_outline_color.setText(tr("lbl_outline_color"))
        self._lbl_back_color.setText(tr("lbl_back_color"))
        self._lbl_outline.setText(tr("lbl_outline"))
        self._lbl_shadow.setText(tr("lbl_shadow"))
        self._lbl_bg_box.setText(tr("lbl_bg_box"))
        self._lbl_margin_v.setText(tr("lbl_margin_v"))
        self._hdr_encode.setText(tr("hdr_encode_settings"))
        self._lbl_preset.setText(tr("lbl_preset"))
        self._lbl_crf.setText(tr("lbl_crf"))
        self._lbl_hw.setText(tr("lbl_hw_accel"))
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._hint_out.setText(tr("hint_save_alongside"))
        self._out_input.setPlaceholderText(tr("ph_same_dir_src"))
        self._browse_out_btn.setText(tr("btn_browse"))
        self._lbl_filename.setText(tr("lbl_filename_template"))
        self._tmpl_hint.setText(tr("hint_filename_template"))
        self._cancel_btn.setText(tr("btn_cancel"))
        self._open_folder_btn.setText(tr("btn_open_folder"))
        self._play_btn.setText(tr("btn_play"))

    def _refresh_style_preview(self) -> None:
        self._font_preview.set_state(
            family=self._font_combo.currentFont().family() or "Arial",
            size_pt=self._font_size_spin.value(),
            bold=self._bold_cb.isChecked(),
            italic=self._italic_cb.isChecked(),
            color=self._color_btn.color(),
            outline_color=self._outline_color_btn.color(),
            outline_w=self._outline_spin.value(),
            shadow_w=self._shadow_spin.value(),
            back_color=self._back_color_btn.color() if self._bg_box_cb.isChecked() else None,
        )

    def _apply_preset(self) -> None:
        key = self._preset_combo.currentData()
        for k, _lbl, crf, _libx in _PRESETS:
            if k == key:
                self._crf_spin.setValue(crf)
                return

    # ── Browse helpers ───────────────────────────────────────────────────────
    def _browse_video(self) -> None:
        ext_filter = "Video files (" + " ".join(f"*{e}" for e in sorted(_VIDEO_EXTS)) + ")"
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", os.path.expanduser("~"), ext_filter
        )
        if path:
            self._video_input.setText(path)
            self._on_video_path_changed()

    def _browse_sub(self) -> None:
        ext_filter = "Subtitle files (" + " ".join(f"*{e}" for e in sorted(_SUB_EXTS)) + ")"
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Subtitle File", os.path.expanduser("~"), ext_filter
        )
        if path:
            self._sub_input.setText(path)
            self._refresh_sub_preview()

    def _browse_out(self) -> None:
        start = self._out_input.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if d:
            self._out_input.setText(d)

    def populate_file(self, path: str) -> None:
        ext = os.path.splitext(path)[1].lower()
        if ext in _SUB_EXTS:
            self._sub_input.setText(path)
            self._refresh_sub_preview()
        else:
            self._video_input.setText(path)
            self._on_video_path_changed()

    # ── Video-change reactions ───────────────────────────────────────────────
    def _on_video_path_changed(self) -> None:
        path = self._video_input.text().strip()
        if not path or not os.path.isfile(path):
            self._video_info.setVisible(False)
            self._embedded_row_widget.setVisible(False)
            return

        self._video_duration = probe_duration(path)
        w, h = probe_resolution(path)
        bits: list[str] = []
        if w and h:
            bits.append(f"{w}×{h}")
        if self._video_duration > 0:
            bits.append(_fmt_hms(self._video_duration))
        try:
            size_mb = os.path.getsize(path) / (1024 * 1024)
            bits.append(f"{size_mb:.1f} MB")
        except Exception:
            pass
        self._video_info.setText(" · ".join(bits))
        self._video_info.setVisible(bool(bits))

        # Embedded subs
        tracks = probe_embedded_subs(path)
        self._embedded_combo.clear()
        if tracks:
            for t in tracks:
                lang = t.get("lang", "?")
                title = t.get("title", "")
                codec = t.get("codec", "")
                lbl = f"#{t.get('index', '?')}  {lang}"
                if title:
                    lbl += f"  — {title}"
                if codec:
                    lbl += f"  ({codec})"
                self._embedded_combo.addItem(lbl, t.get("index"))
            self._embedded_row_widget.setVisible(True)
        else:
            self._embedded_row_widget.setVisible(False)

        # Auto-detect sibling subtitle file
        if not self._sub_input.text().strip():
            base = os.path.splitext(path)[0]
            for ext in (".srt", ".ass", ".ssa", ".vtt"):
                cand = base + ext
                if os.path.isfile(cand):
                    self._sub_input.setText(cand)
                    self.status_message.emit(
                        tr("status_sibling_sub_found").format(name=os.path.basename(cand)),
                        False,
                    )
                    self._refresh_sub_preview()
                    break

    def _use_embedded_sub(self) -> None:
        video = self._video_input.text().strip()
        idx = self._embedded_combo.currentData()
        if not video or idx is None:
            return
        out = os.path.join(
            os.path.dirname(video),
            f"{os.path.splitext(os.path.basename(video))[0]}_track{idx}.srt",
        )
        try:
            extract_embedded_sub(video, int(idx), out)
        except Exception as exc:
            self.status_message.emit(f"Extract failed: {exc}", True)
            return
        self._extracted_sub_tmp = out
        self._sub_input.setText(out)
        self.status_message.emit(tr("status_embedded_extracted"), False)
        self._refresh_sub_preview()

    def _refresh_sub_preview(self) -> None:
        path = self._sub_input.text().strip()
        if not path or not os.path.isfile(path):
            self._sub_preview.setVisible(False)
            return
        enc = self._encoding_combo.currentData() or "auto"
        text = read_sub_preview(path, max_lines=4, encoding=enc)
        if text:
            self._sub_preview.setText(text)
            self._sub_preview.setVisible(True)
        else:
            self._sub_preview.setText(tr("warn_sub_unreadable"))
            self._sub_preview.setVisible(True)

    # ── Output naming ────────────────────────────────────────────────────────
    def _resolve_output_path(self, video: str) -> str:
        out_dir = self._out_input.text().strip() or os.path.dirname(video)
        base, ext = os.path.splitext(os.path.basename(video))
        tmpl = self._filename_input.text().strip() or "{name}_subbed"
        try:
            name = tmpl.format(name=base, ext=ext.lstrip("."))
        except Exception:
            name = f"{base}_subbed"
        if not name.endswith(ext):
            name = f"{name}{ext}"
        return os.path.join(out_dir, name)

    # ── Action ───────────────────────────────────────────────────────────────
    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._cancel_burn()
            return

        video = self._video_input.text().strip()
        sub = self._sub_input.text().strip()
        if not video or not os.path.isfile(video):
            self.status_message.emit("Select a valid video file.", True)
            return
        if not sub or not os.path.isfile(sub):
            self.status_message.emit("Select a valid subtitle file (.srt/.vtt/.ass).", True)
            return

        out_path = self._resolve_output_path(video)
        if os.path.abspath(out_path) == os.path.abspath(video):
            self.status_message.emit(tr("warn_output_equals_input"), True)
            return
        if os.path.isfile(out_path):
            r = QMessageBox.question(
                self, tr("title_overwrite"),
                tr("warn_overwrite").format(name=os.path.basename(out_path)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                return

        kwargs = dict(
            font=self._font_combo.currentFont().family() or None,
            font_size=self._font_size_spin.value(),
            font_color=self._color_btn.color(),
            outline=self._outline_spin.value(),
            outline_color=self._outline_color_btn.color(),
            back_color=self._back_color_btn.color() if self._bg_box_cb.isChecked() else None,
            bold=self._bold_cb.isChecked(),
            italic=self._italic_cb.isChecked(),
            alignment=2,  # bottom-center (libass numpad)
            margin_v=self._margin_v_spin.value(),
            border_style=3 if self._bg_box_cb.isChecked() else 1,
            shadow=self._shadow_spin.value(),
            encoding=self._encoding_combo.currentData() or "auto",
            time_offset=self._offset_spin.value(),
            trim_overlaps=self._trim_overlaps_cb.isChecked(),
            crf=self._crf_spin.value(),
            hw_accel=self._hw_combo.currentData() or "none",
        )
        # libx264 preset from preset combo
        for k, _lbl, _crf, libx in _PRESETS:
            if k == self._preset_combo.currentData():
                kwargs["preset"] = libx
                break

        self._result_label.setVisible(False)
        self._open_folder_btn.setVisible(False)
        self._play_btn.setVisible(False)
        self._progress_bar.setValue(0)
        self._burn_start_ts = time.time()
        self._set_busy(True, f"Burning subtitles into {os.path.basename(video)}…")

        self._worker = Worker(
            burn_subtitles, video, sub, out_path,
            cancel_check=self._is_cancelled,
            progress_cb=self._on_progress,
            info_cb=self._on_burn_info,
            **kwargs,
        )
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        # finished fires even when cancelled (result/error suppressed by Worker).
        self._worker.signals.finished.connect(self._on_finished)
        self._worker.start()

    def _is_cancelled(self) -> bool:
        return self._worker is not None and self._worker.check_cancelled()

    def _on_burn_info(self, msg: str) -> None:
        # Called from ffmpeg reader thread — marshal to GUI thread.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self.status_message.emit(msg, False))

    def _on_progress(self, done: float, total: float) -> None:
        if total <= 0:
            return
        pct = int(min(100, max(0, done * 100 / total)))
        elapsed = time.time() - self._burn_start_ts
        eta = (elapsed / done * (total - done)) if done > 0.5 else 0
        # Direct setValue is safe enough — Worker emits on QThread; setValue
        # is queued via Qt when called from non-GUI thread. progress_cb is
        # called from reader thread; route via singleShot to GUI thread.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self._apply_progress(pct, elapsed, eta))

    def _apply_progress(self, pct: int, elapsed: float, eta: float) -> None:
        self._progress_bar.setValue(pct)
        self._eta_label.setText(
            tr("lbl_progress_eta").format(
                pct=pct, elapsed=_fmt_hms(elapsed), eta=_fmt_hms(eta)
            )
        )

    def _cancel_burn(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.status_message.emit("Cancelling…", False)

    def _set_busy(self, busy: bool, status_msg: str = "") -> None:
        self._progress_bar.setVisible(busy)
        self._eta_label.setVisible(busy)
        self._cancel_btn.setVisible(busy)
        if busy and status_msg:
            self.status_message.emit(status_msg, False)
        self.busy_changed.emit(busy)

    def _on_result(self, out_path: str) -> None:
        self._set_busy(False)
        _old = self._worker
        self._worker = None
        if _old is not None:
            _old.wait(5000)
        self._last_output = out_path
        self._result_label.setText(f"Saved → {out_path}")
        self._result_label.setVisible(True)
        self._open_folder_btn.setVisible(True)
        self._play_btn.setVisible(True)
        self.status_message.emit(f"Done → {os.path.basename(out_path)}", False)
        get_history_manager().add_item(HistoryItem(
            task_type="subtitles_burn",
            file_name=os.path.basename(out_path),
            file_path=out_path,
            status="success",
        ))

    def _on_finished(self) -> None:
        # Worker.run() suppresses result/error when cancelled — handle UI reset here.
        w = self._worker
        if w is None:
            return
        if w.check_cancelled():
            self._set_busy(False)
            self._worker = None
            w.wait(2000)
            self.status_message.emit("Cancelled.", False)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        _old = self._worker
        self._worker = None
        if _old is not None:
            _old.wait(5000)
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)

    def _open_folder(self) -> None:
        if self._last_output and os.path.isfile(self._last_output):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self._last_output)))

    def _play_output(self) -> None:
        if self._last_output and os.path.isfile(self._last_output):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_output))
