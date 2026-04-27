"""Spatial Manipulation tab — Resize, Crop, Rotate, Flip."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPixmap, QTransform
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.spatial import crop_media, extract_frame, resize_media, rotate_flip_chain
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.presets_bar import PresetsBar
from gui.worker import Worker

_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif"}

_ASPECT_RATIOS: dict[str, tuple[int, int] | None] = {
    "Custom":  None,
    "1:1":     (1, 1),
    "16:9":    (16, 9),
    "9:16":    (9, 16),
    "4:3":     (4, 3),
    "3:4":     (3, 4),
    "21:9":    (21, 9),
    "2:1":     (2, 1),
}

_COMMON_RESOLUTIONS: dict[str, tuple[int, int] | None] = {
    "Custom":                        None,
    "4K (3840×2160)":                (3840, 2160),
    "2K (2560×1440)":                (2560, 1440),
    "1080p (1920×1080)":             (1920, 1080),
    "720p (1280×720)":               (1280, 720),
    "480p (854×480)":                (854, 480),
    "360p (640×360)":                (640, 360),
    "Instagram Square (1080×1080)":  (1080, 1080),
    "TikTok / Reels (1080×1920)":    (1080, 1920),
}

_OP_LABELS = {
    "cw90":   "90° CW",
    "ccw90":  "90° CCW",
    "rot180": "180°",
    "fliph":  "Flip H",
    "flipv":  "Flip V",
}


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


class SpatialSection(QScrollArea):
    """Spatial manipulation — Resize, Crop, Rotate, Flip."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._frame_worker: Worker | None = None
        self._last_result_path: str | None = None
        self._original_pixmap: QPixmap | None = None
        self._current_sub_tab: int = 0  # 0=resize, 1=crop, 2=rotate_flip

        # Rotate/flip: accumulate operations across button clicks
        self._accumulated_ops: list[str] = []
        self._accumulated_transform = QTransform()  # identity

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_source_card())
        layout.addWidget(self._build_preview_card())

        self._ops_stack = QStackedWidget()
        self._ops_stack.addWidget(self._build_resize_widget())
        self._ops_stack.addWidget(self._build_crop_widget())
        self._ops_stack.addWidget(self._build_rotate_flip_widget())
        layout.addWidget(self._ops_stack)

        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

        self.setWidget(content)

    # ── Preset support ─────────────────────────────────────────────────────────

    def get_resize_preset_data(self) -> dict:
        return {
            "preset": self._resize_preset_combo.currentText(),
            "width": self._resize_w_spin.value(),
            "height": self._resize_h_spin.value(),
            "output_dir": self._out_input.text().strip(),
        }

    def load_resize_preset_data(self, data: dict) -> None:
        if p := data.get("preset"):
            self._resize_preset_combo.blockSignals(True)
            idx = self._resize_preset_combo.findText(p)
            if idx >= 0:
                self._resize_preset_combo.setCurrentIndex(idx)
            self._resize_preset_combo.blockSignals(False)
        if (w := data.get("width")) is not None:
            self._resize_w_spin.setValue(w)
        if (h := data.get("height")) is not None:
            self._resize_h_spin.setValue(h)
        if out := data.get("output_dir"):
            self._out_input.setText(out)
        self._refresh_preview()

    def get_crop_preset_data(self) -> dict:
        return {
            "aspect_ratio": self._crop_ar_combo.currentText(),
            "width": self._crop_w_spin.value(),
            "height": self._crop_h_spin.value(),
            "x": self._crop_x_spin.value(),
            "y": self._crop_y_spin.value(),
            "output_dir": self._out_input.text().strip(),
        }

    def load_crop_preset_data(self, data: dict) -> None:
        if ar := data.get("aspect_ratio"):
            self._crop_ar_combo.blockSignals(True)
            idx = self._crop_ar_combo.findText(ar)
            if idx >= 0:
                self._crop_ar_combo.setCurrentIndex(idx)
            self._crop_ar_combo.blockSignals(False)
        if (w := data.get("width")) is not None:
            self._crop_w_spin.setValue(w)
        if (h := data.get("height")) is not None:
            self._crop_h_spin.setValue(h)
        if (x := data.get("x")) is not None:
            self._crop_x_spin.setValue(x)
        if (y := data.get("y")) is not None:
            self._crop_y_spin.setValue(y)
        if out := data.get("output_dir"):
            self._out_input.setText(out)
        self._refresh_preview()

    # ── Card builders ──────────────────────────────────────────────────────────

    def _build_source_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("SOURCE FILE"))

        row = QHBoxLayout()
        self._file_input = QLineEdit()
        self._file_input.setObjectName("PillInput")
        self._file_input.setPlaceholderText("Video or image file…")
        self._file_input.textChanged.connect(self._on_source_changed)
        row.addWidget(self._file_input)

        browse_btn = QPushButton("Browse…")
        browse_btn.setObjectName("BrowseBtn")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_file)
        row.addWidget(browse_btn)
        layout.addLayout(row)

        self._source_info = QLabel()
        self._source_info.setObjectName("TextMuted")
        self._source_info.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._source_info)
        return card

    def _build_preview_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("PREVIEW"))

        self._preview_label = QLabel("No file loaded — browse a video or image above.")
        self._preview_label.setObjectName("TextMuted")
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumHeight(220)
        self._preview_label.setStyleSheet(
            "background-color: #0D1117; border-radius: 6px;"
            " color: #8B949E; font-size: 13px;"
        )
        layout.addWidget(self._preview_label)
        return card

    def _build_resize_widget(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        card = _card()
        inner = QVBoxLayout(card)
        inner.setContentsMargins(20, 16, 20, 16)
        inner.setSpacing(12)
        inner.addWidget(_section_header("RESIZE OPTIONS"))

        inner.addWidget(
            PresetsBar(
                "transform_resize",
                self._settings,
                self.get_resize_preset_data,
                self.load_resize_preset_data,
            )
        )

        # Preset resolutions
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset resolution"))
        preset_row.addStretch()
        self._resize_preset_combo = QComboBox()
        self._resize_preset_combo.addItems(list(_COMMON_RESOLUTIONS.keys()))
        self._resize_preset_combo.setCurrentText("1080p (1920×1080)")
        self._resize_preset_combo.setFixedWidth(240)
        self._resize_preset_combo.currentTextChanged.connect(self._on_resize_preset_changed)
        preset_row.addWidget(self._resize_preset_combo)
        inner.addLayout(preset_row)

        # Aspect ratio
        ar_row = QHBoxLayout()
        ar_row.addWidget(QLabel("Aspect ratio"))
        ar_row.addStretch()
        self._resize_ar_combo = QComboBox()
        self._resize_ar_combo.addItems(list(_ASPECT_RATIOS.keys()))
        self._resize_ar_combo.setCurrentText("16:9")
        self._resize_ar_combo.setFixedWidth(120)
        self._resize_ar_combo.currentTextChanged.connect(self._on_resize_ar_changed)
        inner.addLayout(ar_row)
        ar_row.addWidget(self._resize_ar_combo)

        # Width / Height / Lock AR
        dims_row = QHBoxLayout()
        dims_row.setSpacing(16)

        w_col = QVBoxLayout()
        w_col.addWidget(QLabel("Target Width (px)"))
        self._resize_w_spin = QSpinBox()
        self._resize_w_spin.setRange(1, 7680)
        self._resize_w_spin.setValue(1920)
        self._resize_w_spin.setFixedWidth(110)
        self._resize_w_spin.valueChanged.connect(self._on_resize_w_changed)
        self._resize_w_spin.valueChanged.connect(self._refresh_preview)
        w_col.addWidget(self._resize_w_spin)
        dims_row.addLayout(w_col)

        h_col = QVBoxLayout()
        h_col.addWidget(QLabel("Target Height (px)"))
        self._resize_h_spin = QSpinBox()
        self._resize_h_spin.setRange(1, 7680)
        self._resize_h_spin.setValue(1080)
        self._resize_h_spin.setFixedWidth(110)
        self._resize_h_spin.valueChanged.connect(self._on_resize_h_changed)
        self._resize_h_spin.valueChanged.connect(self._refresh_preview)
        h_col.addWidget(self._resize_h_spin)
        dims_row.addLayout(h_col)

        self._resize_lock_ar = QPushButton("🔓 Lock AR")
        self._resize_lock_ar.setObjectName("BrowseBtn")
        self._resize_lock_ar.setCheckable(True)
        self._resize_lock_ar.setFixedSize(100, 36)
        self._resize_lock_ar.toggled.connect(self._on_lock_ar_toggled)
        dims_row.addWidget(self._resize_lock_ar, alignment=Qt.AlignmentFlag.AlignBottom)
        dims_row.addStretch()
        inner.addLayout(dims_row)

        layout.addWidget(card)
        layout.addStretch()
        return w

    def _build_crop_widget(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        card = _card()
        inner = QVBoxLayout(card)
        inner.setContentsMargins(20, 16, 20, 16)
        inner.setSpacing(12)
        inner.addWidget(_section_header("CROP OPTIONS"))

        inner.addWidget(
            PresetsBar(
                "transform_crop",
                self._settings,
                self.get_crop_preset_data,
                self.load_crop_preset_data,
            )
        )

        # Aspect ratio preset
        ar_row = QHBoxLayout()
        ar_row.addWidget(QLabel("Aspect ratio preset"))
        ar_row.addStretch()
        self._crop_ar_combo = QComboBox()
        self._crop_ar_combo.addItems(list(_ASPECT_RATIOS.keys()))
        self._crop_ar_combo.setFixedWidth(120)
        self._crop_ar_combo.currentTextChanged.connect(self._on_crop_ar_changed)
        ar_row.addWidget(self._crop_ar_combo)
        inner.addLayout(ar_row)

        # Crop W / H
        dims_row = QHBoxLayout()
        dims_row.setSpacing(16)

        cw_col = QVBoxLayout()
        cw_col.addWidget(QLabel("Crop Width (px)"))
        self._crop_w_spin = QSpinBox()
        self._crop_w_spin.setRange(1, 7680)
        self._crop_w_spin.setValue(1280)
        self._crop_w_spin.setFixedWidth(110)
        self._crop_w_spin.valueChanged.connect(self._refresh_preview)
        cw_col.addWidget(self._crop_w_spin)
        dims_row.addLayout(cw_col)

        ch_col = QVBoxLayout()
        ch_col.addWidget(QLabel("Crop Height (px)"))
        self._crop_h_spin = QSpinBox()
        self._crop_h_spin.setRange(1, 7680)
        self._crop_h_spin.setValue(720)
        self._crop_h_spin.setFixedWidth(110)
        self._crop_h_spin.valueChanged.connect(self._refresh_preview)
        ch_col.addWidget(self._crop_h_spin)
        dims_row.addLayout(ch_col)
        dims_row.addStretch()
        inner.addLayout(dims_row)

        # X / Y offset
        offset_row = QHBoxLayout()
        offset_row.setSpacing(16)

        x_col = QVBoxLayout()
        x_col.addWidget(QLabel("X offset (px)"))
        self._crop_x_spin = QSpinBox()
        self._crop_x_spin.setRange(0, 7680)
        self._crop_x_spin.setValue(0)
        self._crop_x_spin.setFixedWidth(110)
        self._crop_x_spin.valueChanged.connect(self._refresh_preview)
        x_col.addWidget(self._crop_x_spin)
        offset_row.addLayout(x_col)

        y_col = QVBoxLayout()
        y_col.addWidget(QLabel("Y offset (px)"))
        self._crop_y_spin = QSpinBox()
        self._crop_y_spin.setRange(0, 7680)
        self._crop_y_spin.setValue(0)
        self._crop_y_spin.setFixedWidth(110)
        self._crop_y_spin.valueChanged.connect(self._refresh_preview)
        y_col.addWidget(self._crop_y_spin)
        offset_row.addLayout(y_col)
        offset_row.addStretch()
        inner.addLayout(offset_row)

        hint = QLabel(
            "X=0, Y=0 starts from top-left corner. "
            "Use the aspect ratio preset to auto-fill crop dimensions."
        )
        hint.setObjectName("TextMuted")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 11px;")
        inner.addWidget(hint)

        layout.addWidget(card)
        layout.addStretch()
        return w

    def _build_rotate_flip_widget(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        card = _card()
        inner = QVBoxLayout(card)
        inner.setContentsMargins(20, 16, 20, 16)
        inner.setSpacing(12)
        inner.addWidget(_section_header("ROTATE & FLIP"))

        hint = QLabel(
            "Each click adds to the sequence — preview updates live. "
            "Click Reset to start over."
        )
        hint.setObjectName("TextMuted")
        hint.setStyleSheet("font-size: 12px;")
        inner.addWidget(hint)

        btns_row = QHBoxLayout()
        btns_row.setSpacing(8)

        ops = [
            ("↻  90° CW",   "cw90"),
            ("↺  90° CCW",  "ccw90"),
            ("↕  180°",     "rot180"),
            ("⇔  Flip H",   "fliph"),
            ("↕  Flip V",   "flipv"),
        ]
        self._op_buttons: dict[str, QPushButton] = {}
        for label, op in ops:
            btn = QPushButton(label)
            btn.setObjectName("BrowseBtn")
            btn.setFixedHeight(38)
            btn.clicked.connect(lambda _checked, o=op: self._apply_rotate_op(o))
            btns_row.addWidget(btn)
            self._op_buttons[op] = btn

        reset_btn = QPushButton("Reset")
        reset_btn.setObjectName("BrowseBtn")
        reset_btn.setFixedHeight(38)
        reset_btn.clicked.connect(self._reset_rotate_ops)
        btns_row.addWidget(reset_btn)
        btns_row.addStretch()
        inner.addLayout(btns_row)

        # Shows current accumulated chain e.g. "90° CW → Flip H"
        self._ops_chain_label = QLabel("No operations — click a button above.")
        self._ops_chain_label.setObjectName("TextMuted")
        self._ops_chain_label.setStyleSheet("font-size: 12px; color: #3B82F6;")
        self._ops_chain_label.setWordWrap(True)
        inner.addWidget(self._ops_chain_label)

        layout.addWidget(card)
        layout.addStretch()
        return w

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("OUTPUT FOLDER"))

        row = QHBoxLayout()
        self._out_input = QLineEdit()
        self._out_input.setObjectName("PillInput")
        self._out_input.setPlaceholderText("Same directory as source file")
        if self._settings.output_folder:
            self._out_input.setText(self._settings.output_folder)
        row.addWidget(self._out_input)

        browse_btn = QPushButton("Browse…")
        browse_btn.setObjectName("BrowseBtn")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_output)
        row.addWidget(browse_btn)
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

    # ── Source handling ────────────────────────────────────────────────────────

    def _on_source_changed(self, path: str) -> None:
        path = path.strip()
        if not os.path.isfile(path):
            self._source_info.setText("")
            return
        ext = os.path.splitext(path)[1].lower()
        size_mb = os.path.getsize(path) / (1024 * 1024)
        ftype = (
            "Video" if ext in _VIDEO_EXTS
            else ("Image" if ext in _IMAGE_EXTS else "File")
        )
        self._source_info.setText(f"{ftype}  ·  {size_mb:.1f} MB")
        self._reset_rotate_ops()
        self._load_preview_frame(path)

    def _browse_file(self) -> None:
        start = os.path.dirname(self._file_input.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video or Image", start,
            "Media (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.m4v "
            "*.jpg *.jpeg *.png *.webp *.bmp)",
        )
        if path:
            self._file_input.setText(path)

    def _browse_output(self) -> None:
        start = self._out_input.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if d:
            self._out_input.setText(d)

    def populate_file(self, path: str) -> None:
        self._file_input.setText(path)

    # ── Preview ────────────────────────────────────────────────────────────────

    def _load_preview_frame(self, path: str) -> None:
        self._preview_label.setPixmap(QPixmap())
        self._preview_label.setText("Loading preview…")
        self._original_pixmap = None

        ext = os.path.splitext(path)[1].lower()
        if ext in _IMAGE_EXTS:
            px = QPixmap(path)
            if not px.isNull():
                self._original_pixmap = px
                self._refresh_preview()
            else:
                self._preview_label.setText("Preview unavailable.")
            return

        def do_extract():
            return extract_frame(path, time_sec=1.0)

        self._frame_worker = Worker(do_extract)
        self._frame_worker.signals.result.connect(self._on_frame_extracted)
        self._frame_worker.start()

    def _on_frame_extracted(self, tmp_path: str | None) -> None:
        if tmp_path and os.path.exists(tmp_path):
            px = QPixmap(tmp_path)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            if not px.isNull():
                self._original_pixmap = px
                self._refresh_preview()
                return
        self._preview_label.setText("Preview unavailable for this file.")

    def _refresh_preview(self, *_args) -> None:
        """Route to the correct preview renderer for the active sub-tab."""
        if not self._original_pixmap:
            return
        if self._current_sub_tab == 0:
            self._resize_preview()
        elif self._current_sub_tab == 1:
            self._crop_preview()
        else:
            self._rotate_flip_preview()

    def _resize_preview(self) -> None:
        """Show the source content letterboxed into the target W×H aspect ratio."""
        target_w = self._resize_w_spin.value()
        target_h = self._resize_h_spin.value()
        # Compute preview canvas size at target AR, capped to the label area
        max_pw = max(400, self._preview_label.width() - 20) if self._preview_label.width() > 40 else 400
        max_ph = 320
        ar = target_w / target_h
        if ar >= max_pw / max_ph:
            pw, ph = max_pw, max(1, round(max_pw / ar))
        else:
            ph, pw = max_ph, max(1, round(max_ph * ar))

        canvas = QPixmap(pw, ph)
        canvas.fill(Qt.GlobalColor.black)

        scaled = self._original_pixmap.scaled(
            pw, ph,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter = QPainter(canvas)
        painter.drawPixmap(
            (pw - scaled.width()) // 2,
            (ph - scaled.height()) // 2,
            scaled,
        )
        painter.end()

        self._preview_label.setPixmap(canvas)
        self._preview_label.setText("")

    def _crop_preview(self) -> None:
        """Show the cropped rectangle from the source frame."""
        src_w = self._original_pixmap.width()
        src_h = self._original_pixmap.height()
        cx = min(self._crop_x_spin.value(), max(0, src_w - 1))
        cy = min(self._crop_y_spin.value(), max(0, src_h - 1))
        cw = max(1, min(self._crop_w_spin.value(), src_w - cx))
        ch = max(1, min(self._crop_h_spin.value(), src_h - cy))

        cropped = self._original_pixmap.copy(cx, cy, cw, ch)
        if cropped.isNull():
            return

        max_pw = max(400, self._preview_label.width() - 20) if self._preview_label.width() > 40 else 400
        scaled = cropped.scaled(
            max_pw, 320,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_label.setPixmap(scaled)
        self._preview_label.setText("")

    def _rotate_flip_preview(self) -> None:
        if self._accumulated_transform.isIdentity():
            # Show original frame if no ops yet
            max_pw = max(400, self._preview_label.width() - 20) if self._preview_label.width() > 40 else 400
            scaled = self._original_pixmap.scaled(
                max_pw, 320,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._preview_label.setPixmap(scaled)
            self._preview_label.setText("")
            return

        transformed = self._original_pixmap.transformed(
            self._accumulated_transform,
            Qt.TransformationMode.SmoothTransformation,
        )
        max_pw = max(400, self._preview_label.width() - 20) if self._preview_label.width() > 40 else 400
        scaled = transformed.scaled(
            max_pw, 320,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_label.setPixmap(scaled)
        self._preview_label.setText("")

    # ── Sub-tab switching (called by MainWindow) ───────────────────────────────

    def on_sub_tab_changed(self, index: int) -> None:
        self._current_sub_tab = index
        self._ops_stack.setCurrentIndex(index)
        self._refresh_preview()

    # ── Resize controls ────────────────────────────────────────────────────────

    def _on_lock_ar_toggled(self, locked: bool) -> None:
        if locked:
            self._resize_lock_ar.setText("🔒 Lock AR")
            self._resize_lock_ar.setStyleSheet(
                "background-color: #1D4ED8; color: #FFFFFF;"
                " border: 1px solid #3B82F6; border-radius: 6px;"
            )
        else:
            self._resize_lock_ar.setText("🔓 Lock AR")
            self._resize_lock_ar.setStyleSheet("")

    def _on_resize_preset_changed(self, text: str) -> None:
        dims = _COMMON_RESOLUTIONS.get(text)
        if dims:
            self._resize_w_spin.blockSignals(True)
            self._resize_h_spin.blockSignals(True)
            self._resize_w_spin.setValue(dims[0])
            self._resize_h_spin.setValue(dims[1])
            self._resize_w_spin.blockSignals(False)
            self._resize_h_spin.blockSignals(False)
            self._refresh_preview()

    def _on_resize_ar_changed(self, text: str) -> None:
        ratio = _ASPECT_RATIOS.get(text)
        if ratio:
            w = self._resize_w_spin.value()
            h = round(w * ratio[1] / ratio[0])
            self._resize_h_spin.blockSignals(True)
            self._resize_h_spin.setValue(h)
            self._resize_h_spin.blockSignals(False)
            self._resize_preset_combo.blockSignals(True)
            self._resize_preset_combo.setCurrentText("Custom")
            self._resize_preset_combo.blockSignals(False)
            self._refresh_preview()

    def _on_resize_w_changed(self, w: int) -> None:
        if not self._resize_lock_ar.isChecked():
            return
        ar_text = self._resize_ar_combo.currentText()
        ratio = _ASPECT_RATIOS.get(ar_text)
        if ratio:
            self._resize_h_spin.blockSignals(True)
            self._resize_h_spin.setValue(round(w * ratio[1] / ratio[0]))
            self._resize_h_spin.blockSignals(False)
        # Preview refresh is triggered by w_spin.valueChanged → _refresh_preview

    def _on_resize_h_changed(self, h: int) -> None:
        if not self._resize_lock_ar.isChecked():
            return
        ar_text = self._resize_ar_combo.currentText()
        ratio = _ASPECT_RATIOS.get(ar_text)
        if ratio:
            self._resize_w_spin.blockSignals(True)
            self._resize_w_spin.setValue(round(h * ratio[0] / ratio[1]))
            self._resize_w_spin.blockSignals(False)
        # Preview refresh is triggered by h_spin.valueChanged → _refresh_preview

    # ── Crop controls ──────────────────────────────────────────────────────────

    def _on_crop_ar_changed(self, text: str) -> None:
        ratio = _ASPECT_RATIOS.get(text)
        if ratio:
            w = self._crop_w_spin.value()
            self._crop_h_spin.blockSignals(True)
            self._crop_h_spin.setValue(round(w * ratio[1] / ratio[0]))
            self._crop_h_spin.blockSignals(False)
            self._refresh_preview()

    # ── Rotate/Flip controls ───────────────────────────────────────────────────

    def _apply_rotate_op(self, op: str) -> None:
        """Accumulate op and update preview live."""
        self._accumulated_ops.append(op)

        delta = QTransform()
        if op == "cw90":
            delta.rotate(90)
        elif op == "ccw90":
            delta.rotate(-90)
        elif op == "rot180":
            delta.rotate(180)
        elif op == "fliph":
            delta.scale(-1, 1)
        elif op == "flipv":
            delta.scale(1, -1)

        # accumulated * delta = apply accumulated first, then delta
        self._accumulated_transform = self._accumulated_transform * delta

        # Update chain label
        chain = " → ".join(_OP_LABELS.get(o, o) for o in self._accumulated_ops)
        self._ops_chain_label.setText(chain)

        if self._original_pixmap:
            self._rotate_flip_preview()

    def _reset_rotate_ops(self) -> None:
        self._accumulated_ops.clear()
        self._accumulated_transform = QTransform()
        self._ops_chain_label.setText("No operations — click a button above.")
        self._refresh_preview()

    # ── Primary action ─────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        src = self._file_input.text().strip()
        if not src or not os.path.exists(src):
            self.status_message.emit("Please select a valid file.", True)
            return

        out_dir = self._out_input.text().strip() or os.path.dirname(src)
        self._set_busy(True)

        if self._current_sub_tab == 0:
            w = self._resize_w_spin.value()
            h = self._resize_h_spin.value()
            self.status_message.emit(f"Resizing to {w}×{h}…", False)
            self._progress_label.setText(f"Resizing to {w}×{h}…")

            def do_work():
                return resize_media(src, out_dir, w, h)

        elif self._current_sub_tab == 1:
            cw = self._crop_w_spin.value()
            ch = self._crop_h_spin.value()
            cx = self._crop_x_spin.value()
            cy = self._crop_y_spin.value()
            self.status_message.emit(f"Cropping to {cw}×{ch} at ({cx}, {cy})…", False)
            self._progress_label.setText(f"Cropping {cw}×{ch}…")

            def do_work():
                return crop_media(src, out_dir, cw, ch, cx, cy)

        else:
            if not self._accumulated_ops:
                self._set_busy(False)
                self.status_message.emit("No operations selected — click a transform button.", True)
                return
            ops = list(self._accumulated_ops)
            chain = " → ".join(_OP_LABELS.get(o, o) for o in ops)
            self.status_message.emit(f"Applying {chain}…", False)
            self._progress_label.setText(f"Applying {chain}…")

            def do_work():
                return rotate_flip_chain(src, out_dir, ops)

        self._worker = Worker(do_work)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if not busy:
            self._progress_label.setText("")
        self.busy_changed.emit(busy)

    def _on_result(self, result: dict) -> None:
        self._set_busy(False)
        self._worker = None
        src = self._file_input.text()
        if result.get("success"):
            fp = result["file_path"]
            self._last_result_path = fp
            fn = os.path.basename(fp)
            get_history_manager().add_item(
                HistoryItem(task_type="spatial", file_name=fn, file_path=fp, status="success")
            )
            self.status_message.emit(f"Done → {fn}", False)
        else:
            err = result.get("error") or "Processing failed."
            get_history_manager().add_item(
                HistoryItem(
                    task_type="spatial",
                    file_name=os.path.basename(src),
                    file_path=src,
                    status="error",
                )
            )
            self.status_message.emit(f"Error: {err}", True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
