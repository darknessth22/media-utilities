"""Image Editor tab — fit/alignment/rotate/crop, flip, filter presets, color grading,
post-effects, user presets, aspect-ratio presets.

Pipeline lives in core/image_editor.py.
"""
from __future__ import annotations

import io
import os
from dataclasses import asdict
from typing import Optional

from PIL import Image
from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QGuiApplication,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.image_editor import (
    ASPECT_PRESETS,
    BUILTIN_FILTERS,
    CurvesOptions,
    EditConfig,
    EffectsOptions,
    EnhanceOptions,
    FitOptions,
    FilterOptions,
    AdjustOptions,
    FIT_MODES,
    MASK_BLEND_MODES,
    MASK_TYPES,
    MaskAdjust,
    MaskLayer,
    MonitorSpec,
    _render_one_monitor,
    apply_edits,
    delete_user_preset,
    export_wallpapers,
    load_image,
    load_user_presets,
    mask_overlay_image,
    preset_to_config,
    process_batch,
    process_image,
    save_user_preset,
    _IMAGE_EXTS,
)
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker


def _card() -> QFrame:
    f = QFrame()
    f.setObjectName("Card")
    return f


def _hdr(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("TextSecondary")
    lbl.setStyleSheet(
        "font-size: 11px; font-weight: bold; letter-spacing: 1px; margin-bottom: 2px;"
    )
    return lbl


_PREVIEW_MAX = 480
# The preview pipeline runs at this max canvas size, NOT the real target W×H —
# rendering a 4K canvas on every slider drag is what made the editor feel slow.
_PREVIEW_RENDER_MAX = 640


def _pil_to_qpixmap(img: Image.Image) -> QPixmap:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    pm = QPixmap()
    pm.loadFromData(buf.getvalue(), "PNG")
    return pm


# ── Histogram widget ─────────────────────────────────────────────────────────

class HistogramWidget(QWidget):
    """Tiny RGB histogram. Call set_image(pil_img) to refresh."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(80)
        self.setMinimumWidth(256)
        self._buckets: list[tuple[list[int], list[int], list[int]]] = []
        self._r: list[int] = [0] * 256
        self._g: list[int] = [0] * 256
        self._b: list[int] = [0] * 256
        self._peak: int = 1

    def set_image(self, img: Image.Image) -> None:
        small = img.convert("RGB")
        small.thumbnail((256, 256), Image.Resampling.NEAREST)
        h = small.histogram()
        # PIL histogram for RGB = 768 ints: R[0..255], G[0..255], B[0..255]
        self._r = h[0:256]
        self._g = h[256:512]
        self._b = h[512:768]
        self._peak = max(1, max(max(self._r), max(self._g), max(self._b)))
        self.update()

    def clear(self) -> None:
        self._r = [0] * 256
        self._g = [0] * 256
        self._b = [0] * 256
        self._peak = 1
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        p.fillRect(self.rect(), QColor(20, 22, 28))
        # 256 bins → scale to widget width.
        for chan, color in (
            (self._r, QColor(239, 68, 68, 180)),
            (self._g, QColor(34, 197, 94, 180)),
            (self._b, QColor(59, 130, 246, 180)),
        ):
            p.setPen(QPen(color, 1))
            prev_x = 0
            prev_y = h
            for i in range(256):
                x = int(i * w / 255)
                y = h - int(chan[i] * h / self._peak)
                p.drawLine(prev_x, prev_y, x, y)
                prev_x, prev_y = x, y
        p.end()


# ── Multi-monitor layout preview ─────────────────────────────────────────────

class LayoutPreviewWidget(QWidget):
    """Schematic top-down view of every wallpaper row at scaled positions.

    Draws each monitor's pixmap inside a rectangle laid out at its (x, y, w, h)
    in desktop coords, scaled to fit the widget. Wallpaper-Engine-style layout
    view.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(160)
        self._entries: list[tuple[int, int, int, int, str, QPixmap]] = []

    def set_entries(self, entries: list[tuple[int, int, int, int, str, QPixmap]]) -> None:
        """Each tuple: (x, y, width, height, label, thumb_pixmap)."""
        self._entries = list(entries)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(20, 22, 28)
        p.fillRect(self.rect(), bg)
        if not self._entries:
            p.setPen(QColor("#6B7280"))
            p.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                tr("hint_ie_wp_layout_empty"),
            )
            p.end()
            return
        min_x = min(e[0] for e in self._entries)
        min_y = min(e[1] for e in self._entries)
        max_x = max(e[0] + e[2] for e in self._entries)
        max_y = max(e[1] + e[3] for e in self._entries)
        span_w = max(1, max_x - min_x)
        span_h = max(1, max_y - min_y)
        pad = 12
        avail_w = max(1, self.width() - 2 * pad)
        avail_h = max(1, self.height() - 2 * pad)
        scale = min(avail_w / span_w, avail_h / span_h)
        off_x = pad + (avail_w - span_w * scale) / 2
        off_y = pad + (avail_h - span_h * scale) / 2
        for (x, y, w, h, label, pm) in self._entries:
            rx = int(off_x + (x - min_x) * scale)
            ry = int(off_y + (y - min_y) * scale)
            rw = max(2, int(w * scale))
            rh = max(2, int(h * scale))
            p.fillRect(rx, ry, rw, rh, QColor(40, 44, 52))
            if pm is not None and not pm.isNull():
                p.drawPixmap(rx, ry, pm.scaled(
                    rw, rh,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
            p.setPen(QPen(QColor("#3B82F6"), 1))
            p.drawRect(rx, ry, rw - 1, rh - 1)
            p.setPen(QColor("#E5E7EB"))
            p.drawText(rx + 4, ry + 14, label or "")
        p.end()


# ── Monitor row widget ────────────────────────────────────────────────────────

class _MonitorRow(QFrame):
    """One row in the multi-monitor wallpaper list.

    Emits `changed` whenever any control is edited so the parent can persist the
    setup and refresh the per-row preview thumbnail.
    """

    removed = Signal(object)   # emits self
    changed = Signal()          # emits whenever any control is touched
    selected = Signal(object)   # emits self when user clicks "Edit ✎"
    move_up = Signal(object)    # emits self for reorder
    move_down = Signal(object)  # emits self for reorder

    def __init__(self, spec: MonitorSpec, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        # Persisted device-path id (Windows IDesktopWallpaper) — survives row reorder/deletion.
        self.monitor_id: Optional[str] = spec.monitor_id
        # Per-monitor edit override (filter/adjust/effects/crop). None = inherit
        # global editor state for this monitor; set = use this row's own grade.
        self.edit_cfg: Optional[EditConfig] = spec.edit_cfg
        # Accept dropped image files onto the row to set its source.
        self.setAcceptDrops(True)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(10)

        # ── Live thumbnail of what this monitor will render ───────────────────
        self.thumb_label = QLabel(tr("hint_ie_wp_thumb_empty"))
        self.thumb_label.setObjectName("TextMuted")
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setFixedSize(140, 84)
        self.thumb_label.setStyleSheet(
            "background:#1a1c22; border:1px solid #2a2d35; border-radius:4px; font-size:10px;"
        )
        outer.addWidget(self.thumb_label)

        controls = QWidget()
        layout = QVBoxLayout(controls)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        outer.addWidget(controls, 1)

        # Top row: label + W×H + remove
        top = QHBoxLayout()
        top.setSpacing(8)
        self.label_edit = QLineEdit(spec.label)
        self.label_edit.setObjectName("PillInput")
        self.label_edit.setFixedWidth(140)
        top.addWidget(self.label_edit)

        top.addWidget(QLabel("W"))
        self.w_spin = QSpinBox()
        self.w_spin.setRange(16, 16384)
        self.w_spin.setValue(spec.width)
        self.w_spin.setFixedWidth(80)
        top.addWidget(self.w_spin)

        top.addWidget(QLabel("H"))
        self.h_spin = QSpinBox()
        self.h_spin.setRange(16, 16384)
        self.h_spin.setValue(spec.height)
        self.h_spin.setFixedWidth(80)
        top.addWidget(self.h_spin)

        top.addWidget(QLabel("X"))
        self.x_spin = QSpinBox()
        self.x_spin.setRange(-32768, 32768)
        self.x_spin.setValue(spec.x)
        self.x_spin.setFixedWidth(70)
        top.addWidget(self.x_spin)

        top.addWidget(QLabel("Y"))
        self.y_spin = QSpinBox()
        self.y_spin.setRange(-32768, 32768)
        self.y_spin.setValue(spec.y)
        self.y_spin.setFixedWidth(70)
        top.addWidget(self.y_spin)

        top.addStretch()
        self.up_btn = QPushButton("▲")
        self.up_btn.setObjectName("BrowseBtn")
        self.up_btn.setFixedWidth(28)
        self.up_btn.setToolTip(tr("tip_ie_wp_row_up"))
        self.up_btn.clicked.connect(lambda: self.move_up.emit(self))
        top.addWidget(self.up_btn)
        self.down_btn = QPushButton("▼")
        self.down_btn.setObjectName("BrowseBtn")
        self.down_btn.setFixedWidth(28)
        self.down_btn.setToolTip(tr("tip_ie_wp_row_down"))
        self.down_btn.clicked.connect(lambda: self.move_down.emit(self))
        top.addWidget(self.down_btn)
        self.edit_btn = QPushButton(tr("btn_ie_wp_row_edit"))
        self.edit_btn.setObjectName("BrowseBtn")
        self.edit_btn.setToolTip(tr("tip_ie_wp_row_edit"))
        self.edit_btn.clicked.connect(lambda: self.selected.emit(self))
        top.addWidget(self.edit_btn)
        self.remove_btn = QPushButton("✕")
        self.remove_btn.setObjectName("BrowseBtn")
        self.remove_btn.setFixedWidth(32)
        self.remove_btn.clicked.connect(lambda: self.removed.emit(self))
        top.addWidget(self.remove_btn)
        layout.addLayout(top)

        # Bottom row: fit + flip + rotate + bg
        bot = QHBoxLayout()
        bot.setSpacing(8)
        bot.addWidget(QLabel(tr("lbl_ie_fit")))
        self.fit_combo = QComboBox()
        for m in FIT_MODES:
            self.fit_combo.addItem(tr(f"ie_fit_{m}"), m)
        idx = self.fit_combo.findData(spec.fit_mode)
        if idx >= 0:
            self.fit_combo.setCurrentIndex(idx)
        self.fit_combo.setFixedWidth(130)
        bot.addWidget(self.fit_combo)

        self.flip_h = QCheckBox(tr("lbl_ie_flip_h"))
        self.flip_h.setChecked(spec.flip_h)
        bot.addWidget(self.flip_h)
        self.flip_v = QCheckBox(tr("lbl_ie_flip_v"))
        self.flip_v.setChecked(spec.flip_v)
        bot.addWidget(self.flip_v)

        bot.addWidget(QLabel(tr("lbl_ie_rotate")))
        self.rotate_spin = QDoubleSpinBox()
        self.rotate_spin.setRange(-180.0, 180.0)
        self.rotate_spin.setDecimals(1)
        self.rotate_spin.setSingleStep(0.5)
        self.rotate_spin.setSuffix("°")
        self.rotate_spin.setFixedWidth(80)
        self.rotate_spin.setValue(spec.rotate_deg)
        bot.addWidget(self.rotate_spin)

        self._bg_color = spec.bg_color
        self.bg_btn = QPushButton("  ")
        self.bg_btn.setFixedSize(46, 24)
        self._apply_bg()
        self.bg_btn.clicked.connect(self._pick_bg)
        bot.addWidget(self.bg_btn)
        self.auto_bg_btn = QPushButton(tr("btn_ie_wp_auto_bg"))
        self.auto_bg_btn.setObjectName("BrowseBtn")
        self.auto_bg_btn.setToolTip(tr("tip_ie_wp_auto_bg"))
        self.auto_bg_btn.setFixedHeight(24)
        self.auto_bg_btn.clicked.connect(self._auto_bg)
        bot.addWidget(self.auto_bg_btn)
        self.palette_bg_btn = QPushButton(tr("btn_ie_wp_palette_bg"))
        self.palette_bg_btn.setObjectName("BrowseBtn")
        self.palette_bg_btn.setToolTip(tr("tip_ie_wp_palette_bg"))
        self.palette_bg_btn.setFixedHeight(24)
        self.palette_bg_btn.clicked.connect(self._palette_bg)
        bot.addWidget(self.palette_bg_btn)
        self.smart_fit_btn = QPushButton(tr("btn_ie_wp_smart_fit"))
        self.smart_fit_btn.setObjectName("BrowseBtn")
        self.smart_fit_btn.setToolTip(tr("tip_ie_wp_smart_fit"))
        self.smart_fit_btn.setFixedHeight(24)
        self.smart_fit_btn.clicked.connect(self._smart_fit)
        bot.addWidget(self.smart_fit_btn)
        bot.addStretch()
        layout.addLayout(bot)

        # Source row — per-monitor source image override (Wallpaper Engine style).
        src_row = QHBoxLayout()
        src_row.setSpacing(8)
        self._src_lbl = QLabel(tr("lbl_ie_wp_row_source"))
        src_row.addWidget(self._src_lbl)
        self.source_edit = QLineEdit(spec.source_path or "")
        self.source_edit.setObjectName("PillInput")
        self.source_edit.setPlaceholderText(tr("ph_ie_wp_row_source"))
        self.source_edit.setReadOnly(True)
        src_row.addWidget(self.source_edit)
        self._src_browse_btn = QPushButton(tr("btn_browse"))
        self._src_browse_btn.setObjectName("BrowseBtn")
        self._src_browse_btn.setFixedWidth(80)
        self._src_browse_btn.clicked.connect(self._pick_source)
        src_row.addWidget(self._src_browse_btn)
        self._src_clear_btn = QPushButton(tr("btn_ie_wp_row_use_main"))
        self._src_clear_btn.setObjectName("BrowseBtn")
        self._src_clear_btn.clicked.connect(lambda: self.source_edit.setText(""))
        src_row.addWidget(self._src_clear_btn)
        layout.addLayout(src_row)

        # Slideshow row (Windows-only at apply time, system-wide).
        sld = QHBoxLayout()
        sld.setSpacing(8)
        self.slideshow_chk = QCheckBox(tr("lbl_ie_wp_slideshow"))
        self.slideshow_chk.setChecked(spec.use_slideshow)
        self.slideshow_chk.setToolTip(tr("tip_ie_wp_slideshow"))
        sld.addWidget(self.slideshow_chk)
        self.slideshow_edit = QLineEdit(spec.slideshow_folder or "")
        self.slideshow_edit.setObjectName("PillInput")
        self.slideshow_edit.setPlaceholderText(tr("ph_ie_wp_slideshow_folder"))
        self.slideshow_edit.setReadOnly(True)
        sld.addWidget(self.slideshow_edit)
        self._sld_browse_btn = QPushButton(tr("btn_browse"))
        self._sld_browse_btn.setObjectName("BrowseBtn")
        self._sld_browse_btn.setFixedWidth(80)
        self._sld_browse_btn.clicked.connect(self._pick_slideshow_folder)
        sld.addWidget(self._sld_browse_btn)
        self._sld_min_lbl = QLabel(tr("lbl_ie_wp_slideshow_interval"))
        sld.addWidget(self._sld_min_lbl)
        self.slideshow_min_spin = QSpinBox()
        self.slideshow_min_spin.setRange(1, 1440)
        self.slideshow_min_spin.setValue(max(1, spec.slideshow_interval_minutes))
        self.slideshow_min_spin.setSuffix(" min")
        self.slideshow_min_spin.setFixedWidth(90)
        sld.addWidget(self.slideshow_min_spin)
        layout.addLayout(sld)


        # Forward every meaningful edit to `changed` so the parent re-renders
        # the thumbnail and persists the setup.
        self.label_edit.textChanged.connect(self.changed)
        self.w_spin.valueChanged.connect(self.changed)
        self.h_spin.valueChanged.connect(self.changed)
        self.x_spin.valueChanged.connect(self.changed)
        self.y_spin.valueChanged.connect(self.changed)
        self.fit_combo.currentIndexChanged.connect(self.changed)
        self.flip_h.toggled.connect(self.changed)
        self.flip_v.toggled.connect(self.changed)
        self.rotate_spin.valueChanged.connect(self.changed)
        self.source_edit.textChanged.connect(self.changed)
        self.slideshow_chk.toggled.connect(self.changed)
        self.slideshow_edit.textChanged.connect(self.changed)
        self.slideshow_min_spin.valueChanged.connect(self.changed)

    def _apply_bg(self) -> None:
        self.bg_btn.setStyleSheet(
            f"background:{self._bg_color}; border:1px solid #555; border-radius:4px;"
        )

    def _pick_bg(self) -> None:
        col = QColorDialog.getColor(QColor(self._bg_color), self, tr("lbl_ie_bg_color"))
        if col.isValid():
            self._bg_color = col.name()
            self._apply_bg()
            self.changed.emit()

    def _pick_source(self) -> None:
        from core.image_editor import _IMAGE_EXTS as _EXTS
        ext_filter = "Images (" + " ".join(f"*{e}" for e in sorted(_EXTS)) + ")"
        path, _ = QFileDialog.getOpenFileName(
            self, tr("lbl_ie_wp_row_source"),
            os.path.expanduser("~"), ext_filter,
        )
        if path:
            self.source_edit.setText(path)

    def _auto_bg(self) -> None:
        """Sample the source's edge median colour and set it as bg_color."""
        from core.image_editor import sample_edge_color
        # Prefer row source override; fall back to whatever the parent loaded.
        path = self.source_edit.text().strip()
        if not path or not os.path.isfile(path):
            # Find ancestor section for fallback source path.
            owner = self.parent()
            while owner is not None and not isinstance(owner, ImageEditorSection):
                owner = owner.parent()
            path = getattr(owner, "_src_path", None) if owner else None
        if not path or not os.path.isfile(path):
            return
        try:
            im = load_image(path)
            self._bg_color = sample_edge_color(im)
            self._apply_bg()
            self.changed.emit()
        except Exception:
            pass

    def _palette_bg(self) -> None:
        """Set bg_color from the source's dominant colour (Pillow quantise)."""
        from core.image_editor import dominant_color
        path = self.source_edit.text().strip()
        if not path or not os.path.isfile(path):
            owner = self.parent()
            while owner is not None and not isinstance(owner, ImageEditorSection):
                owner = owner.parent()
            path = getattr(owner, "_src_path", None) if owner else None
        if not path or not os.path.isfile(path):
            return
        try:
            im = load_image(path)
            self._bg_color = dominant_color(im)
            self._apply_bg()
            self.changed.emit()
        except Exception:
            pass

    def _smart_fit(self) -> None:
        """Pick cover (≈aspect) vs fill (otherwise) based on source vs target."""
        from core.image_editor import smart_fit_for
        path = self.source_edit.text().strip()
        if not path or not os.path.isfile(path):
            owner = self.parent()
            while owner is not None and not isinstance(owner, ImageEditorSection):
                owner = owner.parent()
            path = getattr(owner, "_src_path", None) if owner else None
        if not path or not os.path.isfile(path):
            return
        try:
            im = load_image(path)
            mode = smart_fit_for(im.size, (self.w_spin.value(), self.h_spin.value()))
            idx = self.fit_combo.findData(mode)
            if idx >= 0:
                self.fit_combo.setCurrentIndex(idx)
        except Exception:
            pass

    def _pick_slideshow_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, tr("lbl_ie_wp_slideshow"), os.path.expanduser("~"),
        )
        if folder:
            self.slideshow_edit.setText(folder)
            self.slideshow_chk.setChecked(True)

    def set_active(self, active: bool) -> None:
        """Highlight the row when it is the editor's current active row."""
        if active:
            self.setStyleSheet(
                "QFrame#Card { border: 2px solid #3B82F6; background-color: rgba(59,130,246,0.08); }"
            )
        else:
            self.setStyleSheet("")

    def set_thumbnail(self, pixmap: Optional[QPixmap]) -> None:
        if pixmap is None or pixmap.isNull():
            self.thumb_label.setPixmap(QPixmap())
            self.thumb_label.setText(tr("hint_ie_wp_thumb_empty"))
        else:
            self.thumb_label.setPixmap(pixmap.scaled(
                self.thumb_label.width(), self.thumb_label.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            self.thumb_label.setText("")

    # ── Drag-drop: dropping an image on the row sets its source ───────────────

    def dragEnterEvent(self, ev) -> None:  # type: ignore[override]
        if ev.mimeData().hasUrls():
            from core.image_editor import _IMAGE_EXTS as _EXTS
            for u in ev.mimeData().urls():
                p = u.toLocalFile()
                if p and os.path.splitext(p)[1].lower() in _EXTS:
                    ev.acceptProposedAction()
                    return
        ev.ignore()

    def dropEvent(self, ev) -> None:  # type: ignore[override]
        from core.image_editor import _IMAGE_EXTS as _EXTS
        for u in ev.mimeData().urls():
            p = u.toLocalFile()
            if p and os.path.splitext(p)[1].lower() in _EXTS:
                self.source_edit.setText(p)
                ev.acceptProposedAction()
                return
        ev.ignore()

    def to_spec(self) -> MonitorSpec:
        src = self.source_edit.text().strip()
        return MonitorSpec(
            label=self.label_edit.text().strip() or "Monitor",
            width=self.w_spin.value(),
            height=self.h_spin.value(),
            x=self.x_spin.value(),
            y=self.y_spin.value(),
            fit_mode=self.fit_combo.currentData() or "cover",
            flip_h=self.flip_h.isChecked(),
            flip_v=self.flip_v.isChecked(),
            rotate_deg=float(self.rotate_spin.value()),
            bg_color=self._bg_color,
            source_path=src or None,
            monitor_id=self.monitor_id,
            edit_cfg=self.edit_cfg,
            use_slideshow=self.slideshow_chk.isChecked(),
            slideshow_folder=self.slideshow_edit.text().strip() or None,
            slideshow_interval_minutes=int(self.slideshow_min_spin.value()),
        )

    def retranslate_ui(self) -> None:
        # Update labels created with tr() at construction.
        # Only the fit/flip/rotate texts are stable enough to rebuild safely.
        for i in range(self.fit_combo.count()):
            data = self.fit_combo.itemData(i)
            if data:
                self.fit_combo.setItemText(i, tr(f"ie_fit_{data}"))
        self.flip_h.setText(tr("lbl_ie_flip_h"))
        self.flip_v.setText(tr("lbl_ie_flip_v"))
        self._src_lbl.setText(tr("lbl_ie_wp_row_source"))
        self.source_edit.setPlaceholderText(tr("ph_ie_wp_row_source"))
        self._src_browse_btn.setText(tr("btn_browse"))
        self._src_clear_btn.setText(tr("btn_ie_wp_row_use_main"))
        self.edit_btn.setText(tr("btn_ie_wp_row_edit"))
        self.edit_btn.setToolTip(tr("tip_ie_wp_row_edit"))
        self.auto_bg_btn.setText(tr("btn_ie_wp_auto_bg"))
        self.auto_bg_btn.setToolTip(tr("tip_ie_wp_auto_bg"))


# ── Hold-to-compare preview label ─────────────────────────────────────────────

class _PreviewLabel(QLabel):
    """QLabel that emits hold/release for the Before/After button replacement.

    Also supports an opt-in crop-rectangle mode: when ``crop_mode_active`` is
    True, left-drag draws a rubber-band rect over the displayed pixmap. The
    final fractional crop (top/left/bottom/right) is emitted via `crop_set`.
    """

    hold_pressed = Signal()
    hold_released = Signal()
    crop_set = Signal(float, float, float, float)  # top, left, bottom, right (each 0..0.49)
    # Raw drag start/end fractions (0..1) of the displayed pixmap, for mask geometry.
    mask_geometry_set = Signal(float, float, float, float)
    # Sampled pixel colour for a color-range mask.
    mask_color_picked = Signal(int, int, int)
    # A finished freehand brush stroke — list of (fx, fy) fractions of the pixmap.
    brush_stroke = Signal(list)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.crop_mode_active = False
        self._drag_origin = None
        self._drag_rect = None
        # Mask placement mode: None | "radial" | "linear" | "brush".
        self.mask_mode: Optional[str] = None
        self._mask_origin = None
        self._mask_cur = None
        # Brush paint mode — accumulates label-space points during a drag.
        self._brush_points: list = []
        self.brush_size_frac: float = 0.06
        self.brush_erase: bool = False
        # Outlines of existing masks, drawn always: list of
        # ("radial", cx, cy, rx, ry) or ("linear", x0, y0, x1, y1) in 0..1 fractions.
        self._mask_overlays: list = []

    def set_mask_overlays(self, overlays: list) -> None:
        self._mask_overlays = list(overlays)
        self.update()

    def _frac_to_point(self, fx: float, fy: float) -> Optional[tuple[int, int]]:
        """Translate a 0..1 fraction of the shown pixmap into a label-space point."""
        pm = self.pixmap()
        if not pm or pm.isNull():
            return None
        pw, ph = pm.width(), pm.height()
        ox = max(0, (self.width() - pw) // 2)
        oy = max(0, (self.height() - ph) // 2)
        return (int(ox + fx * pw), int(oy + fy * ph))

    def _point_to_frac(self, pt) -> Optional[tuple[float, float]]:
        """Translate a label-space point into a 0..1 fraction of the shown pixmap."""
        pm = self.pixmap()
        if not pm or pm.isNull():
            return None
        pw, ph = pm.width(), pm.height()
        ox = max(0, (self.width() - pw) // 2)
        oy = max(0, (self.height() - ph) // 2)
        fx = (pt.x() - ox) / max(1, pw)
        fy = (pt.y() - oy) / max(1, ph)
        return (max(0.0, min(1.0, fx)), max(0.0, min(1.0, fy)))

    def _sample_color(self, pt) -> None:
        """Read the displayed pixel under *pt* and emit it for a color mask."""
        pm = self.pixmap()
        if not pm or pm.isNull():
            return
        pw, ph = pm.width(), pm.height()
        x = pt.x() - max(0, (self.width() - pw) // 2)
        y = pt.y() - max(0, (self.height() - ph) // 2)
        if 0 <= x < pw and 0 <= y < ph:
            c = pm.toImage().pixelColor(x, y)
            self.mask_color_picked.emit(c.red(), c.green(), c.blue())

    def mousePressEvent(self, ev) -> None:  # type: ignore[override]
        if ev.button() == Qt.MouseButton.LeftButton:
            if self.crop_mode_active:
                self._drag_origin = ev.position().toPoint()
                self._drag_rect = None
            elif self.mask_mode == "color":
                self._sample_color(ev.position().toPoint())
            elif self.mask_mode == "brush":
                self._brush_points = [ev.position().toPoint()]
                self.update()
            elif self.mask_mode:
                self._mask_origin = ev.position().toPoint()
                self._mask_cur = None
            else:
                self.hold_pressed.emit()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:  # type: ignore[override]
        if self.crop_mode_active and self._drag_origin is not None:
            from PySide6.QtCore import QRect
            self._drag_rect = QRect(self._drag_origin, ev.position().toPoint()).normalized()
            self.update()
        elif self.mask_mode == "brush" and self._brush_points:
            self._brush_points.append(ev.position().toPoint())
            self.update()
        elif self.mask_mode and self._mask_origin is not None:
            self._mask_cur = ev.position().toPoint()
            self.update()
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:  # type: ignore[override]
        if ev.button() == Qt.MouseButton.LeftButton:
            if self.crop_mode_active and self._drag_origin is not None and self._drag_rect is not None:
                pm = self.pixmap()
                if pm and not pm.isNull():
                    # Compute the actual pixmap rect inside the label (centered, scaled).
                    pw, ph = pm.width(), pm.height()
                    lw, lh = self.width(), self.height()
                    ox = max(0, (lw - pw) // 2)
                    oy = max(0, (lh - ph) // 2)
                    r = self._drag_rect.intersected(self.rect())
                    # Translate into pixmap coords + clamp.
                    x0 = max(0, r.left() - ox) / pw
                    y0 = max(0, r.top() - oy) / ph
                    x1 = min(pw, r.right() - ox) / pw
                    y1 = min(ph, r.bottom() - oy) / ph
                    if x1 > x0 and y1 > y0:
                        crop_top    = max(0.0, min(0.49, y0))
                        crop_left   = max(0.0, min(0.49, x0))
                        crop_bottom = max(0.0, min(0.49, 1.0 - y1))
                        crop_right  = max(0.0, min(0.49, 1.0 - x1))
                        self.crop_set.emit(crop_top, crop_left, crop_bottom, crop_right)
                self._drag_origin = None
                self._drag_rect = None
                self.update()
            elif self.mask_mode == "brush" and self._brush_points:
                fracs = []
                for pt in self._brush_points:
                    f = self._point_to_frac(pt)
                    if f is not None:
                        fracs.append(f)
                self._brush_points = []
                if fracs:
                    self.brush_stroke.emit(fracs)
                self.update()
            elif self.mask_mode and self._mask_origin is not None and self._mask_cur is not None:
                f0 = self._point_to_frac(self._mask_origin)
                f1 = self._point_to_frac(self._mask_cur)
                if f0 is not None and f1 is not None:
                    self.mask_geometry_set.emit(f0[0], f0[1], f1[0], f1[1])
                self._mask_origin = None
                self._mask_cur = None
                self.update()
            elif not self.crop_mode_active and not self.mask_mode:
                self.hold_released.emit()
        super().mouseReleaseEvent(ev)

    def paintEvent(self, ev) -> None:  # type: ignore[override]
        super().paintEvent(ev)
        from PySide6.QtGui import QPainter, QPen, QColor
        if self.crop_mode_active and self._drag_rect is not None:
            p = QPainter(self)
            p.setPen(QPen(QColor(59, 130, 246, 220), 2))
            p.setBrush(QColor(59, 130, 246, 40))
            p.drawRect(self._drag_rect)
            p.end()
        elif self.mask_mode and self._mask_origin is not None and self._mask_cur is not None:
            from PySide6.QtCore import QRect
            p = QPainter(self)
            p.setPen(QPen(QColor(34, 197, 94, 230), 2))
            p.setBrush(QColor(34, 197, 94, 45))
            if self.mask_mode == "radial":
                p.drawEllipse(QRect(self._mask_origin, self._mask_cur).normalized())
            else:
                p.drawLine(self._mask_origin, self._mask_cur)
            p.end()
        # In-progress freehand brush stroke.
        if self.mask_mode == "brush" and self._brush_points:
            p = QPainter(self)
            pm = self.pixmap()
            wpx = 8.0
            if pm and not pm.isNull():
                wpx = max(2.0, self.brush_size_frac * min(pm.width(), pm.height()))
            col = QColor(239, 68, 68, 170) if self.brush_erase else QColor(34, 197, 94, 170)
            pen = QPen(col, wpx)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            if len(self._brush_points) == 1:
                p.drawPoint(self._brush_points[0])
            else:
                for i in range(1, len(self._brush_points)):
                    p.drawLine(self._brush_points[i - 1], self._brush_points[i])
            p.end()
        # Outlines of every existing mask — drawn whenever overlays are set.
        if self._mask_overlays:
            from PySide6.QtCore import QRect
            p = QPainter(self)
            pen = QPen(QColor(34, 197, 94, 210), 1.5)
            pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for ov in self._mask_overlays:
                if ov[0] == "radial":
                    _, cx, cy, rx, ry, rot = ov
                    c = self._frac_to_point(cx, cy)
                    e = self._frac_to_point(cx + rx, cy + ry)
                    if c and e:
                        hw = max(1, abs(e[0] - c[0]))
                        hh = max(1, abs(e[1] - c[1]))
                        p.save()
                        p.translate(c[0], c[1])
                        p.rotate(rot)
                        p.drawEllipse(QRect(-hw, -hh, 2 * hw, 2 * hh))
                        p.restore()
                else:
                    _, x0, y0, x1, y1 = ov
                    a = self._frac_to_point(x0, y0)
                    b = self._frac_to_point(x1, y1)
                    if a and b:
                        p.drawLine(a[0], a[1], b[0], b[1])
                        for pt in (a, b):
                            p.drawEllipse(pt[0] - 3, pt[1] - 3, 6, 6)
            p.end()


# ── Tone-curve widget ─────────────────────────────────────────────────────────

class CurveWidget(QWidget):
    """Interactive master tone curve. Drag handles, click empty space to add a
    point, double-click a middle point to remove it. Emits `changed` on edit.
    """

    changed = Signal()
    _MARGIN = 10

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(252, 200)
        self._points: list[list[int]] = [[0, 0], [255, 255]]
        self._drag: Optional[int] = None
        self.setCursor(Qt.CursorShape.CrossCursor)

    def points(self) -> list:
        return [list(p) for p in self._points]

    def set_points(self, pts) -> None:
        cleaned = [
            [max(0, min(255, int(p[0]))), max(0, min(255, int(p[1])))]
            for p in (pts or []) if len(p) >= 2
        ]
        if len(cleaned) < 2:
            cleaned = [[0, 0], [255, 255]]
        cleaned.sort()
        cleaned[0][0] = 0
        cleaned[-1][0] = 255
        self._points = cleaned
        self.update()

    def reset(self) -> None:
        self._points = [[0, 0], [255, 255]]
        self.update()
        self.changed.emit()

    def _plot(self) -> tuple[int, int, int, int]:
        m = self._MARGIN
        return (m, m, self.width() - 2 * m, self.height() - 2 * m)

    def _to_widget(self, x: float, y: float) -> tuple[float, float]:
        px0, py0, pw, ph = self._plot()
        return (px0 + x / 255.0 * pw, py0 + (1.0 - y / 255.0) * ph)

    def _from_widget(self, wx: float, wy: float) -> tuple[int, int]:
        px0, py0, pw, ph = self._plot()
        x = (wx - px0) / max(1, pw) * 255.0
        y = (1.0 - (wy - py0) / max(1, ph)) * 255.0
        return (max(0, min(255, int(round(x)))), max(0, min(255, int(round(y)))))

    def _hit(self, wx: float, wy: float) -> Optional[int]:
        for i, (x, y) in enumerate(self._points):
            hx, hy = self._to_widget(x, y)
            if (hx - wx) ** 2 + (hy - wy) ** 2 <= 100:
                return i
        return None

    def paintEvent(self, _ev) -> None:  # type: ignore[override]
        from core.image_editor import _build_curve_lut
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(20, 22, 28))
        px0, py0, pw, ph = self._plot()
        p.setPen(QPen(QColor(55, 58, 66), 1))
        for i in range(1, 4):
            gx = int(px0 + pw * i / 4)
            gy = int(py0 + ph * i / 4)
            p.drawLine(gx, py0, gx, py0 + ph)
            p.drawLine(px0, gy, px0 + pw, gy)
        p.setPen(QPen(QColor(70, 74, 82), 1, Qt.PenStyle.DashLine))
        p.drawLine(px0, py0 + ph, px0 + pw, py0)
        lut = _build_curve_lut(self._points)
        p.setPen(QPen(QColor(59, 130, 246), 2))
        prev = None
        for i in range(256):
            wx, wy = self._to_widget(i, lut[i])
            if prev is not None:
                p.drawLine(int(prev[0]), int(prev[1]), int(wx), int(wy))
            prev = (wx, wy)
        p.setPen(QPen(QColor(59, 130, 246), 2))
        p.setBrush(QColor(255, 255, 255))
        for x, y in self._points:
            wx, wy = self._to_widget(x, y)
            p.drawEllipse(int(wx) - 4, int(wy) - 4, 8, 8)
        p.end()

    def mousePressEvent(self, ev) -> None:  # type: ignore[override]
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        pos = ev.position()
        i = self._hit(pos.x(), pos.y())
        if i is None:
            x, y = self._from_widget(pos.x(), pos.y())
            x = max(1, min(254, x))  # new points never collide with the locked ends
            self._points.append([x, y])
            self._points.sort()
            self._points[0][0], self._points[-1][0] = 0, 255
            self._drag = self._hit(pos.x(), pos.y())
            self.update()
            self.changed.emit()
        else:
            self._drag = i

    def mouseMoveEvent(self, ev) -> None:  # type: ignore[override]
        if self._drag is None:
            return
        x, y = self._from_widget(ev.position().x(), ev.position().y())
        i = self._drag
        last = len(self._points) - 1
        if i == 0:
            x = 0
        elif i == last:
            x = 255
        else:
            x = max(self._points[i - 1][0] + 1, min(self._points[i + 1][0] - 1, x))
        self._points[i] = [x, y]
        self.update()
        self.changed.emit()

    def mouseReleaseEvent(self, _ev) -> None:  # type: ignore[override]
        self._drag = None

    def mouseDoubleClickEvent(self, ev) -> None:  # type: ignore[override]
        i = self._hit(ev.position().x(), ev.position().y())
        if i is not None and 0 < i < len(self._points) - 1:
            del self._points[i]
            self._drag = None
            self.update()
            self.changed.emit()


# ── Local-adjustment mask row ─────────────────────────────────────────────────

class _MaskRow(QFrame):
    """One stacked local-adjustment mask: type + geometry + 9 adjustment sliders.

    Geometry is set by dragging on the preview (see `request_region`); the row
    only stores the resulting fractional coords.
    """

    removed = Signal(object)         # emits self
    changed = Signal()               # emits on any control edit
    request_region = Signal(object)  # emits self when "Set region" is clicked
    move_up = Signal(object)         # emits self — reorder up
    move_down = Signal(object)       # emits self — reorder down
    duplicate = Signal(object)       # emits self — clone this mask

    # (key, lo, hi, default, label_key, scale)  — scale: slider value ÷ scale.
    _ADJ_DEFS = [
        ("brightness",  0,   200, 100, "lbl_ie_brightness",  100.0),
        ("contrast",    0,   200, 100, "lbl_ie_contrast",    100.0),
        ("saturation",  0,   200, 100, "lbl_ie_saturation",  100.0),
        ("hue",      -180,   180,   0, "lbl_ie_hue",           1.0),
        ("temperature",-100, 100,   0, "lbl_ie_temperature",   1.0),
        ("tint",      -100,  100,   0, "lbl_ie_tint",          1.0),
        ("exposure",  -200,  200,   0, "lbl_ie_exposure",    100.0),
        ("shadows",   -100,  100,   0, "lbl_ie_shadows",     100.0),
        ("highlights",-100,  100,   0, "lbl_ie_highlights",  100.0),
        ("clarity",      0,  100,   0, "lbl_ie_clarity",     100.0),
        ("dehaze",       0,  100,   0, "lbl_ie_dehaze",      100.0),
        ("vibrance",  -100,  100,   0, "lbl_ie_vibrance",    100.0),
        ("gamma",       20,  300, 100, "lbl_ie_gamma",       100.0),
        ("sharpen",      0,  300,   0, "lbl_ie_sharpen",     100.0),
        ("blur",         0,  100,   0, "lbl_ie_blur",         10.0),
    ]

    def __init__(self, layer: MaskLayer, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        # Geometry kept as plain attributes; written by set_geometry().
        self._cx, self._cy, self._rx, self._ry = layer.cx, layer.cy, layer.rx, layer.ry
        self._x0, self._y0 = layer.x0, layer.y0
        self._x1, self._y1 = layer.x1, layer.y1
        self._pick_color = layer.pick_color
        # Freehand brush strokes — painted on the preview, stored as fractions.
        self._brush_strokes = [dict(s) for s in (layer.brush_strokes or [])]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        # ── Header: title + type + invert + feather + set-region + remove ─────
        head = QHBoxLayout()
        head.setSpacing(8)
        self._title = QLabel("Mask")
        self._title.setStyleSheet("font-weight: bold; color: #22C55E;")
        head.addWidget(self._title)

        self._lbl_type = QLabel(tr("lbl_ie_mask_type"))
        head.addWidget(self._lbl_type)
        self.type_combo = QComboBox()
        for t in MASK_TYPES:
            self.type_combo.addItem(tr(f"ie_mask_{t}"), t)
        idx = self.type_combo.findData(layer.mask_type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.type_combo.setFixedWidth(150)
        head.addWidget(self.type_combo)

        self._lbl_blend = QLabel(tr("lbl_ie_mask_blend"))
        head.addWidget(self._lbl_blend)
        self.blend_combo = QComboBox()
        for m in MASK_BLEND_MODES:
            self.blend_combo.addItem(tr(f"ie_mask_blend_{m}"), m)
        bidx = self.blend_combo.findData(layer.blend_mode)
        if bidx >= 0:
            self.blend_combo.setCurrentIndex(bidx)
        self.blend_combo.setFixedWidth(130)
        self.blend_combo.setToolTip(tr("tip_ie_mask_blend"))
        head.addWidget(self.blend_combo)

        self.invert_chk = QCheckBox(tr("lbl_ie_mask_invert"))
        self.invert_chk.setChecked(layer.invert)
        head.addWidget(self.invert_chk)

        head.addStretch()
        self.region_btn = QPushButton(tr("btn_ie_mask_set_region"))
        self.region_btn.setObjectName("BrowseBtn")
        self.region_btn.setToolTip(tr("tip_ie_mask_set_region"))
        self.region_btn.clicked.connect(lambda: self.request_region.emit(self))
        head.addWidget(self.region_btn)
        self.up_btn = QPushButton("▲")
        self.up_btn.setObjectName("BrowseBtn")
        self.up_btn.setFixedWidth(30)
        self.up_btn.setToolTip(tr("tip_ie_mask_up"))
        self.up_btn.clicked.connect(lambda: self.move_up.emit(self))
        head.addWidget(self.up_btn)
        self.down_btn = QPushButton("▼")
        self.down_btn.setObjectName("BrowseBtn")
        self.down_btn.setFixedWidth(30)
        self.down_btn.setToolTip(tr("tip_ie_mask_down"))
        self.down_btn.clicked.connect(lambda: self.move_down.emit(self))
        head.addWidget(self.down_btn)
        self.dup_btn = QPushButton("⧉")
        self.dup_btn.setObjectName("BrowseBtn")
        self.dup_btn.setFixedWidth(30)
        self.dup_btn.setToolTip(tr("tip_ie_mask_duplicate"))
        self.dup_btn.clicked.connect(lambda: self.duplicate.emit(self))
        head.addWidget(self.dup_btn)
        self.remove_btn = QPushButton("✕")
        self.remove_btn.setObjectName("BrowseBtn")
        self.remove_btn.setFixedWidth(32)
        self.remove_btn.clicked.connect(lambda: self.removed.emit(self))
        head.addWidget(self.remove_btn)
        outer.addLayout(head)

        # ── Feather slider ────────────────────────────────────────────────────
        feat = QHBoxLayout()
        self._lbl_feather = QLabel(tr("lbl_ie_mask_feather"))
        self._lbl_feather.setFixedWidth(120)
        feat.addWidget(self._lbl_feather)
        self.feather_slider = QSlider(Qt.Orientation.Horizontal)
        self.feather_slider.setRange(0, 100)
        self.feather_slider.setValue(int(round(layer.feather * 100)))
        feat.addWidget(self.feather_slider)
        self._feather_val = QLabel(str(self.feather_slider.value()))
        self._feather_val.setFixedWidth(48)
        self._feather_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        feat.addWidget(self._feather_val)
        outer.addLayout(feat)

        # ── Opacity slider — overall mask-effect strength ─────────────────────
        op = QHBoxLayout()
        self._lbl_opacity = QLabel(tr("lbl_ie_mask_opacity"))
        self._lbl_opacity.setFixedWidth(120)
        op.addWidget(self._lbl_opacity)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(int(round(layer.opacity * 100)))
        self.opacity_slider.setToolTip(tr("tip_ie_mask_opacity"))
        op.addWidget(self.opacity_slider)
        self._opacity_val = QLabel(str(self.opacity_slider.value()))
        self._opacity_val.setFixedWidth(48)
        self._opacity_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        op.addWidget(self._opacity_val)
        outer.addLayout(op)

        # ── Rotation row (radial type only) ───────────────────────────────────
        self._rotation_row = QWidget()
        rotl = QHBoxLayout(self._rotation_row)
        rotl.setContentsMargins(0, 0, 0, 0)
        rotl.setSpacing(8)
        self._lbl_rotation = QLabel(tr("lbl_ie_mask_rotation"))
        self._lbl_rotation.setFixedWidth(120)
        rotl.addWidget(self._lbl_rotation)
        self.rotation_spin = QDoubleSpinBox()
        self.rotation_spin.setRange(-180.0, 180.0)
        self.rotation_spin.setDecimals(1)
        self.rotation_spin.setSingleStep(1.0)
        self.rotation_spin.setSuffix("°")
        self.rotation_spin.setFixedWidth(90)
        self.rotation_spin.setValue(float(layer.rotation))
        rotl.addWidget(self.rotation_spin)
        rotl.addStretch()
        outer.addWidget(self._rotation_row)

        # ── Luminance-range row (luminance type only) ─────────────────────────
        self._lum_row = QWidget()
        lrow = QHBoxLayout(self._lum_row)
        lrow.setContentsMargins(0, 0, 0, 0)
        lrow.setSpacing(8)
        self._lbl_lum_min = QLabel(tr("lbl_ie_mask_lum_min"))
        self._lbl_lum_min.setFixedWidth(120)
        lrow.addWidget(self._lbl_lum_min)
        self.lum_min_slider = QSlider(Qt.Orientation.Horizontal)
        self.lum_min_slider.setRange(0, 100)
        self.lum_min_slider.setValue(int(round(layer.lum_min * 100)))
        lrow.addWidget(self.lum_min_slider)
        self._lbl_lum_max = QLabel(tr("lbl_ie_mask_lum_max"))
        lrow.addWidget(self._lbl_lum_max)
        self.lum_max_slider = QSlider(Qt.Orientation.Horizontal)
        self.lum_max_slider.setRange(0, 100)
        self.lum_max_slider.setValue(int(round(layer.lum_max * 100)))
        lrow.addWidget(self.lum_max_slider)
        outer.addWidget(self._lum_row)

        # ── Brush row (brush type only) ───────────────────────────────────────
        self._brush_row = QWidget()
        brow = QHBoxLayout(self._brush_row)
        brow.setContentsMargins(0, 0, 0, 0)
        brow.setSpacing(8)
        self._lbl_brush_size = QLabel(tr("lbl_ie_mask_brush_size"))
        self._lbl_brush_size.setFixedWidth(120)
        brow.addWidget(self._lbl_brush_size)
        self.brush_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.brush_size_slider.setRange(1, 40)
        self.brush_size_slider.setValue(12)
        brow.addWidget(self.brush_size_slider)
        self.erase_chk = QCheckBox(tr("lbl_ie_mask_erase"))
        brow.addWidget(self.erase_chk)
        self.clear_strokes_btn = QPushButton(tr("btn_ie_mask_clear_strokes"))
        self.clear_strokes_btn.setObjectName("BrowseBtn")
        self.clear_strokes_btn.clicked.connect(self.clear_brush_strokes)
        brow.addWidget(self.clear_strokes_btn)
        outer.addWidget(self._brush_row)

        # ── Color-range row (visible only for the "color" mask type) ──────────
        self._color_row = QWidget()
        crow = QHBoxLayout(self._color_row)
        crow.setContentsMargins(0, 0, 0, 0)
        crow.setSpacing(8)
        self._lbl_color = QLabel(tr("lbl_ie_mask_color"))
        self._lbl_color.setFixedWidth(120)
        crow.addWidget(self._lbl_color)
        self.color_btn = QPushButton("  ")
        self.color_btn.setFixedSize(46, 22)
        self._apply_color_btn()
        self.color_btn.clicked.connect(self._pick_color_dialog)
        crow.addWidget(self.color_btn)
        self._lbl_tol = QLabel(tr("lbl_ie_mask_tolerance"))
        crow.addWidget(self._lbl_tol)
        self.tol_slider = QSlider(Qt.Orientation.Horizontal)
        self.tol_slider.setRange(1, 100)
        self.tol_slider.setValue(int(round(layer.tolerance * 100)))
        crow.addWidget(self.tol_slider)
        self._tol_val = QLabel(str(self.tol_slider.value()))
        self._tol_val.setFixedWidth(40)
        self._tol_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        crow.addWidget(self._tol_val)
        outer.addWidget(self._color_row)

        # ── Adjustment sliders ────────────────────────────────────────────────
        self._sl: dict[str, QSlider] = {}
        self._adj_labels: dict[str, QLabel] = {}
        for key, lo, hi, default, lkey, scale in self._ADJ_DEFS:
            row = QHBoxLayout()
            lbl = QLabel(tr(lkey))
            lbl.setFixedWidth(120)
            self._adj_labels[key] = lbl
            row.addWidget(lbl)
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(lo, hi)
            sl.setValue(self._slider_value_for(layer.adjust, key, default, scale))
            row.addWidget(sl)
            v = QLabel(str(sl.value()))
            v.setFixedWidth(48)
            v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            sl.valueChanged.connect(lambda val, lab=v: lab.setText(str(val)))
            row.addWidget(v)
            outer.addLayout(row)
            self._sl[key] = sl

        # Wire signals AFTER all widgets carry their initial values, so building
        # the row from a saved layer never fires `changed`.
        self.type_combo.currentIndexChanged.connect(self.changed)
        self.type_combo.currentIndexChanged.connect(self._sync_type_ui)
        self.blend_combo.currentIndexChanged.connect(self.changed)
        self.blend_combo.currentIndexChanged.connect(self._sync_blend_ui)
        self.invert_chk.toggled.connect(self.changed)
        self.feather_slider.valueChanged.connect(self.changed)
        self.feather_slider.valueChanged.connect(
            lambda v: self._feather_val.setText(str(v))
        )
        self.opacity_slider.valueChanged.connect(self.changed)
        self.opacity_slider.valueChanged.connect(
            lambda v: self._opacity_val.setText(str(v))
        )
        self.rotation_spin.valueChanged.connect(self.changed)
        self.lum_min_slider.valueChanged.connect(self.changed)
        self.lum_max_slider.valueChanged.connect(self.changed)
        self.brush_size_slider.valueChanged.connect(self.changed)
        self.erase_chk.toggled.connect(self.changed)
        self.tol_slider.valueChanged.connect(self.changed)
        self.tol_slider.valueChanged.connect(lambda v: self._tol_val.setText(str(v)))
        for sl in self._sl.values():
            sl.valueChanged.connect(self.changed)

        self._sync_type_ui()
        self._sync_blend_ui()

    @staticmethod
    def _slider_value_for(adj: MaskAdjust, key: str, default: int, scale: float) -> int:
        return int(round(getattr(adj, key, default / scale) * scale))

    def mask_type(self) -> str:
        return self.type_combo.currentData() or "radial"

    def blend_mode(self) -> str:
        return self.blend_combo.currentData() or "add"

    def brush_size_frac(self) -> float:
        """Brush diameter as a fraction of the smaller canvas side."""
        return self.brush_size_slider.value() / 200.0

    def brush_erase(self) -> bool:
        return self.erase_chk.isChecked()

    def add_brush_stroke(self, points: list) -> None:
        """Append a finished freehand stroke — `points` are (fx, fy) fractions."""
        self._brush_strokes.append({
            "points": [[float(x), float(y)] for x, y in points],
            "size": self.brush_size_frac(),
            "erase": self.brush_erase(),
        })
        self.changed.emit()

    def clear_brush_strokes(self) -> None:
        self._brush_strokes = []
        self.changed.emit()

    def overlay(self) -> Optional[tuple]:
        """Geometry tuple for drawing this mask's outline on the preview.

        Color / luminance / brush masks have no simple outline — returns None.
        """
        t = self.mask_type()
        if t == "radial":
            return ("radial", self._cx, self._cy, self._rx, self._ry,
                    float(self.rotation_spin.value()))
        if t == "linear":
            return ("linear", self._x0, self._y0, self._x1, self._y1)
        return None

    def _apply_color_btn(self) -> None:
        self.color_btn.setStyleSheet(
            f"background:{self._pick_color}; border:1px solid #555; border-radius:3px;"
        )

    def _pick_color_dialog(self) -> None:
        col = QColorDialog.getColor(QColor(self._pick_color), self, tr("lbl_ie_mask_color"))
        if col.isValid():
            self._pick_color = col.name()
            self._apply_color_btn()
            self.changed.emit()

    def set_pick_color(self, hex_color: str) -> None:
        """Set the color-range target (called after an eyedropper pick)."""
        self._pick_color = hex_color
        self._apply_color_btn()
        self.changed.emit()

    def _sync_type_ui(self) -> None:
        """Show type-specific rows and relabel the region button per mask type."""
        t = self.mask_type()
        self._color_row.setVisible(t == "color")
        self._lum_row.setVisible(t == "luminance")
        self._brush_row.setVisible(t == "brush")
        self._rotation_row.setVisible(t == "radial")
        # Luminance masks need no preview drag — hide the region button.
        self.region_btn.setVisible(t != "luminance")
        self.region_btn.setCheckable(t == "brush")
        if t != "brush":
            self.region_btn.setChecked(False)
        if t == "color":
            self.region_btn.setText(tr("btn_ie_mask_pick_color"))
            self.region_btn.setToolTip(tr("tip_ie_mask_pick_color"))
        elif t == "brush":
            self.region_btn.setText(tr("btn_ie_mask_paint"))
            self.region_btn.setToolTip(tr("tip_ie_mask_paint"))
        else:
            self.region_btn.setText(tr("btn_ie_mask_set_region"))
            self.region_btn.setToolTip(tr("tip_ie_mask_set_region"))

    def _sync_blend_ui(self) -> None:
        """Subtract / intersect masks contribute geometry only — grey out their
        adjustment + opacity controls so it's clear they carry no colour grade."""
        is_add = self.blend_mode() == "add"
        self.opacity_slider.setEnabled(is_add)
        for sl in self._sl.values():
            sl.setEnabled(is_add)

    def set_index(self, n: int) -> None:
        self._title.setText(tr("ie_mask_label").format(n=n))

    def set_geometry(self, x0: float, y0: float, x1: float, y1: float) -> None:
        """Store a drag's start/end fractions, interpreted by the mask type."""
        if self.mask_type() == "radial":
            self._cx = (x0 + x1) / 2.0
            self._cy = (y0 + y1) / 2.0
            self._rx = max(0.02, abs(x1 - x0) / 2.0)
            self._ry = max(0.02, abs(y1 - y0) / 2.0)
        else:
            self._x0, self._y0, self._x1, self._y1 = x0, y0, x1, y1
        self.changed.emit()

    def to_layer(self) -> MaskLayer:
        adj = MaskAdjust(
            brightness  = self._sl["brightness"].value() / 100.0,
            contrast    = self._sl["contrast"].value() / 100.0,
            saturation  = self._sl["saturation"].value() / 100.0,
            hue         = self._sl["hue"].value(),
            temperature = self._sl["temperature"].value(),
            tint        = self._sl["tint"].value(),
            exposure    = self._sl["exposure"].value() / 100.0,
            shadows     = self._sl["shadows"].value() / 100.0,
            highlights  = self._sl["highlights"].value() / 100.0,
            clarity     = self._sl["clarity"].value() / 100.0,
            dehaze      = self._sl["dehaze"].value() / 100.0,
            vibrance    = self._sl["vibrance"].value() / 100.0,
            gamma       = self._sl["gamma"].value() / 100.0,
            sharpen     = self._sl["sharpen"].value() / 100.0,
            blur        = self._sl["blur"].value() / 10.0,
        )
        return MaskLayer(
            mask_type=self.mask_type(),
            invert=self.invert_chk.isChecked(),
            feather=self.feather_slider.value() / 100.0,
            opacity=self.opacity_slider.value() / 100.0,
            blend_mode=self.blend_mode(),
            cx=self._cx, cy=self._cy, rx=self._rx, ry=self._ry,
            rotation=float(self.rotation_spin.value()),
            x0=self._x0, y0=self._y0, x1=self._x1, y1=self._y1,
            pick_color=self._pick_color,
            tolerance=self.tol_slider.value() / 100.0,
            lum_min=self.lum_min_slider.value() / 100.0,
            lum_max=self.lum_max_slider.value() / 100.0,
            brush_strokes=[
                {"points": [list(p) for p in s.get("points", [])],
                 "size": s.get("size", 0.06), "erase": bool(s.get("erase", False))}
                for s in self._brush_strokes
            ],
            adjust=adj,
        )

    def retranslate_ui(self) -> None:
        self._lbl_type.setText(tr("lbl_ie_mask_type"))
        for i in range(self.type_combo.count()):
            data = self.type_combo.itemData(i)
            if data:
                self.type_combo.setItemText(i, tr(f"ie_mask_{data}"))
        self.invert_chk.setText(tr("lbl_ie_mask_invert"))
        self.up_btn.setToolTip(tr("tip_ie_mask_up"))
        self.down_btn.setToolTip(tr("tip_ie_mask_down"))
        self.dup_btn.setToolTip(tr("tip_ie_mask_duplicate"))
        self._lbl_blend.setText(tr("lbl_ie_mask_blend"))
        for i in range(self.blend_combo.count()):
            data = self.blend_combo.itemData(i)
            if data:
                self.blend_combo.setItemText(i, tr(f"ie_mask_blend_{data}"))
        self.blend_combo.setToolTip(tr("tip_ie_mask_blend"))
        self._lbl_feather.setText(tr("lbl_ie_mask_feather"))
        self._lbl_opacity.setText(tr("lbl_ie_mask_opacity"))
        self.opacity_slider.setToolTip(tr("tip_ie_mask_opacity"))
        self._lbl_rotation.setText(tr("lbl_ie_mask_rotation"))
        self._lbl_lum_min.setText(tr("lbl_ie_mask_lum_min"))
        self._lbl_lum_max.setText(tr("lbl_ie_mask_lum_max"))
        self._lbl_brush_size.setText(tr("lbl_ie_mask_brush_size"))
        self.erase_chk.setText(tr("lbl_ie_mask_erase"))
        self.clear_strokes_btn.setText(tr("btn_ie_mask_clear_strokes"))
        self._lbl_color.setText(tr("lbl_ie_mask_color"))
        self._lbl_tol.setText(tr("lbl_ie_mask_tolerance"))
        self._sync_type_ui()  # relabels the region button per mask type
        for key, lbl in self._adj_labels.items():
            lbl.setText(tr(f"lbl_ie_{key}"))


class ImageEditorSection(QScrollArea):
    """Image edit — alignment/rotate/crop/flip + filters + adjustments + effects + presets."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Optional[Worker] = None
        self._src_image: Optional[Image.Image] = None
        self._src_path: Optional[str] = None
        self._last_result_path: Optional[str] = None
        self._show_original = False
        # Tracks the last per-monitor export, in row order, so "Apply to monitors" knows what to set.
        self._last_per_monitor_paths: list[str] = []
        # Per-monitor edit mode: when set, editor controls drive this row's
        # edit_cfg and the preview renders the row's source. Else controls
        # drive the global edit state (self._global_cfg).
        self._active_row: Optional["_MonitorRow"] = None
        self._global_cfg: EditConfig = EditConfig()
        # Cached source image for the active row, keyed by path.
        self._active_row_src_path: Optional[str] = None
        self._active_row_src_image: Optional[Image.Image] = None
        # Stacked local-adjustment masks.
        self._mask_rows: list["_MaskRow"] = []
        # Mask row currently waiting for a region drag on the preview.
        self._active_mask_row: Optional["_MaskRow"] = None
        # Undo / redo — snapshots of EditConfig, debounced via the preview timer.
        self._undo_stack: list[EditConfig] = []
        self._redo_stack: list[EditConfig] = []
        self._restoring = False

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(120)
        self._preview_timer.timeout.connect(self._refresh_preview)

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Input + preview + active-row banner stay pinned above the sub-tabs.
        root.addWidget(self._build_input_card())
        root.addWidget(self._build_preview_card())
        root.addWidget(self._build_active_row_banner())

        # The editing cards are grouped into 6 sub-tab pages, driven by the app
        # header tab bar via on_sub_tab_changed(). Page order MUST match the
        # tab_keys list for "image_editor" in app.py's _SECTIONS_META.
        self._ie_stack = QStackedWidget()
        self._ie_stack.addWidget(self._make_page([          # 0 — Transform
            self._build_canvas_card(), self._build_crop_rotate_card(),
        ]))
        self._ie_stack.addWidget(self._make_page([          # 1 — Color
            self._build_filter_card(), self._build_adjust_card(),
            self._build_curves_card(),
        ]))
        self._ie_stack.addWidget(self._make_page([          # 2 — Enhance
            self._build_enhance_card(), self._build_effects_card(),
        ]))
        self._ie_stack.addWidget(self._make_page([          # 3 — Masks
            self._build_masks_card(),
        ]))
        self._ie_stack.addWidget(self._make_page([          # 4 — Presets
            self._build_preset_card(),
        ]))
        self._ie_stack.addWidget(self._make_page([          # 5 — Wallpaper
            self._build_wallpaper_card(), self._build_setup_presets_card(),
            self._build_schedule_card(),
        ]))
        root.addWidget(self._ie_stack)

        # Output + progress stay pinned below the sub-tabs.
        root.addWidget(self._build_output_card())
        root.addWidget(self._build_progress_card())

        self.setWidget(content)

        # Undo / redo keyboard shortcuts.
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self._undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, activated=self._redo)

        self._reload_user_presets()
        self._wallpaper_first_open_done = False
        self._load_wallpaper_setup()

        # Start the wallpaper auto-apply scheduler. Polls every minute and
        # fires matching entries (Windows only — apply step is a no-op on others).
        try:
            from core.wallpaper_scheduler import WallpaperScheduler
            self._wallpaper_scheduler = WallpaperScheduler(self._on_scheduled_fire, self)
            self._wallpaper_scheduler.start()
        except Exception:
            self._wallpaper_scheduler = None

    def _on_scheduled_fire(self, setup_name: str) -> None:
        """Schedule trigger — load the setup and apply per-monitor wallpapers."""
        from core import wallpaper_setups
        specs = wallpaper_setups.load(setup_name)
        if not specs:
            return
        self._clear_monitor_rows()
        for s in specs:
            self._add_monitor_row(s)
        # Delay slightly so widget construction settles before the export step.
        QTimer.singleShot(150, self._apply_per_monitor_now)

    def showEvent(self, ev) -> None:  # type: ignore[override]
        super().showEvent(ev)
        # The app shell rebuilds its sub-tab bar (resetting to tab 0) on section
        # entry without signalling us — keep the stacked page in sync.
        self._ie_stack.setCurrentIndex(0)
        if not self._wallpaper_first_open_done:
            self._wallpaper_first_open_done = True
            # If neither a saved setup nor any manual rows exist, auto-detect.
            if not self._wp_rows:
                try:
                    self._detect_monitors()
                except Exception:
                    pass

    # ── Sub-tab plumbing ──────────────────────────────────────────────────────

    def _make_page(self, cards: list[QWidget]) -> QWidget:
        """Wrap a list of cards in a sub-tab page widget."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        for c in cards:
            lay.addWidget(c)
        return page

    def on_sub_tab_changed(self, index: int) -> None:
        """App header sub-tab changed — show the matching page."""
        if 0 <= index < self._ie_stack.count():
            self._ie_stack.setCurrentIndex(index)
            # Refresh so mask outlines appear/disappear with the Masks tab.
            self._schedule_preview()

    # ── Input card ────────────────────────────────────────────────────────────

    def _build_input_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_input = _hdr(tr("hdr_ie_input"))
        layout.addWidget(self._hdr_input)

        self._mode_batch = QCheckBox(tr("lbl_ie_batch_mode"))
        self._mode_batch.toggled.connect(self._on_mode_toggled)
        layout.addWidget(self._mode_batch)

        self._single_row = QHBoxLayout()
        self._single_input = QLineEdit()
        self._single_input.setObjectName("PillInput")
        self._single_input.setPlaceholderText(tr("ph_ie_select_image"))
        self._single_input.setReadOnly(True)
        self._single_row.addWidget(self._single_input)
        self._single_browse_btn = QPushButton(tr("btn_browse"))
        self._single_browse_btn.setObjectName("BrowseBtn")
        self._single_browse_btn.setFixedWidth(90)
        self._single_browse_btn.clicked.connect(self._browse_single)
        self._single_row.addWidget(self._single_browse_btn)
        layout.addLayout(self._single_row)

        self._batch_list = QListWidget()
        self._batch_list.setObjectName("FileList")
        self._batch_list.setFixedHeight(140)
        self._batch_list.setVisible(False)
        layout.addWidget(self._batch_list)

        batch_btns = QHBoxLayout()
        self._batch_add_btn = QPushButton(tr("btn_add_files"))
        self._batch_add_btn.setObjectName("BrowseBtn")
        self._batch_add_btn.clicked.connect(self._batch_add_files)
        self._batch_dir_btn = QPushButton(tr("btn_add_folder"))
        self._batch_dir_btn.setObjectName("BrowseBtn")
        self._batch_dir_btn.clicked.connect(self._batch_add_folder)
        self._batch_clear_btn = QPushButton(tr("btn_clear_all"))
        self._batch_clear_btn.setObjectName("BrowseBtn")
        self._batch_clear_btn.clicked.connect(self._batch_list.clear)
        for b in (self._batch_add_btn, self._batch_dir_btn, self._batch_clear_btn):
            b.setVisible(False)
            batch_btns.addWidget(b)
        batch_btns.addStretch()
        layout.addLayout(batch_btns)
        return card

    def _on_mode_toggled(self, checked: bool) -> None:
        for w in (self._batch_list, self._batch_add_btn, self._batch_dir_btn, self._batch_clear_btn):
            w.setVisible(checked)
        self._single_input.setVisible(not checked)
        self._single_browse_btn.setVisible(not checked)

    def _browse_single(self) -> None:
        ext_filter = "Images (" + " ".join(f"*{e}" for e in sorted(_IMAGE_EXTS)) + ")"
        path, _ = QFileDialog.getOpenFileName(self, "Select Image", os.path.expanduser("~"), ext_filter)
        if not path:
            return
        self._single_input.setText(path)
        self._load_source(path)

    def _batch_add_files(self) -> None:
        ext_filter = "Images (" + " ".join(f"*{e}" for e in sorted(_IMAGE_EXTS)) + ")"
        paths, _ = QFileDialog.getOpenFileNames(self, "Select Images", os.path.expanduser("~"), ext_filter)
        self._batch_add(paths)

    def _batch_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", os.path.expanduser("~"))
        if not folder:
            return
        paths = [
            os.path.join(folder, f) for f in os.listdir(folder)
            if os.path.splitext(f)[1].lower() in _IMAGE_EXTS
        ]
        self._batch_add(sorted(paths))

    def _batch_add(self, paths: list[str]) -> None:
        existing = {self._batch_list.item(i).text() for i in range(self._batch_list.count())}
        for p in paths:
            if p not in existing:
                self._batch_list.addItem(QListWidgetItem(p))
        if not self._src_image and self._batch_list.count() > 0:
            self._load_source(self._batch_list.item(0).text())

    def _load_source(self, path: str) -> None:
        try:
            self._src_image = load_image(path)
            self._src_path = path
            self._schedule_preview()
        except Exception as exc:
            self.status_message.emit(f"Cannot open image: {exc}", True)

    # ── Preview card (preview label + before/after + reset + histogram) ──────

    def _build_preview_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        hdr_row = QHBoxLayout()
        self._hdr_preview = _hdr(tr("hdr_ie_preview"))
        hdr_row.addWidget(self._hdr_preview)
        hdr_row.addStretch()
        self._undo_btn = QPushButton("↶")
        self._undo_btn.setObjectName("BrowseBtn")
        self._undo_btn.setFixedWidth(34)
        self._undo_btn.setToolTip(tr("tip_ie_undo"))
        self._undo_btn.setEnabled(False)
        self._undo_btn.clicked.connect(self._undo)
        hdr_row.addWidget(self._undo_btn)
        self._redo_btn = QPushButton("↷")
        self._redo_btn.setObjectName("BrowseBtn")
        self._redo_btn.setFixedWidth(34)
        self._redo_btn.setToolTip(tr("tip_ie_redo"))
        self._redo_btn.setEnabled(False)
        self._redo_btn.clicked.connect(self._redo)
        hdr_row.addWidget(self._redo_btn)
        self._compare_btn = QPushButton(tr("btn_ie_compare"))
        self._compare_btn.setObjectName("BrowseBtn")
        self._compare_btn.setToolTip(tr("tip_ie_compare"))
        # Use pressed/released so it acts as hold-to-compare.
        self._compare_btn.pressed.connect(self._on_compare_pressed)
        self._compare_btn.released.connect(self._on_compare_released)
        hdr_row.addWidget(self._compare_btn)
        self._reset_btn = QPushButton(tr("btn_ie_reset"))
        self._reset_btn.setObjectName("BrowseBtn")
        self._reset_btn.clicked.connect(self._reset_all)
        hdr_row.addWidget(self._reset_btn)
        self._crop_mode_btn = QPushButton(tr("btn_ie_crop_mode"))
        self._crop_mode_btn.setObjectName("BrowseBtn")
        self._crop_mode_btn.setCheckable(True)
        self._crop_mode_btn.setToolTip(tr("tip_ie_crop_mode"))
        self._crop_mode_btn.toggled.connect(self._on_crop_mode_toggled)
        hdr_row.addWidget(self._crop_mode_btn)
        layout.addLayout(hdr_row)

        self._preview_label = _PreviewLabel(tr("hint_ie_no_preview"))
        self._preview_label.setObjectName("TextMuted")
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumHeight(280)
        self._preview_label.setToolTip(tr("tip_ie_compare"))
        self._preview_label.hold_pressed.connect(self._on_compare_pressed)
        self._preview_label.hold_released.connect(self._on_compare_released)
        self._preview_label.crop_set.connect(self._on_crop_set)
        self._preview_label.mask_geometry_set.connect(self._on_mask_geometry_set)
        self._preview_label.mask_color_picked.connect(self._on_mask_color_picked)
        self._preview_label.brush_stroke.connect(self._on_brush_stroke)
        self._preview_label.setMouseTracking(True)
        layout.addWidget(self._preview_label)

        self._histogram = HistogramWidget()
        layout.addWidget(self._histogram)
        return card

    def _on_crop_mode_toggled(self, checked: bool) -> None:
        # Crop drag and mask drag are mutually exclusive.
        if checked and self._active_mask_row is not None:
            self._active_mask_row = None
            self._preview_label.mask_mode = None
        self._preview_label.crop_mode_active = checked
        self._preview_label.setCursor(
            Qt.CursorShape.CrossCursor if checked else Qt.CursorShape.ArrowCursor
        )

    def _on_crop_set(self, top: float, left: float, bottom: float, right: float) -> None:
        """Translate a dragged rect on the preview into the 4 crop sliders."""
        for key, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
            sl = self._crop_sliders[key][0]
            sl.setValue(int(round(val * 100)))
        # Exit crop mode automatically after a successful set.
        self._crop_mode_btn.setChecked(False)

    def _on_compare_pressed(self) -> None:
        self._show_original = True
        self._refresh_preview()

    def _on_compare_released(self) -> None:
        self._show_original = False
        self._refresh_preview()

    def _schedule_preview(self) -> None:
        self._preview_timer.start()

    def _preview_source(self, src: Optional[Image.Image]) -> Optional[Image.Image]:
        """A downscaled copy of *src* for fast preview rendering, cached by identity.

        Rotating / cropping a full-resolution photo on every keystroke is wasteful
        — the preview only needs ~1280px of detail. Recomputed when the source
        image changes (keyed by identity + size).
        """
        if src is None:
            return None
        key = (id(src), src.size)
        if getattr(self, "_prev_src_key", None) != key:
            small = src.copy()
            small.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
            self._prev_src_img = small
            self._prev_src_key = key
        return self._prev_src_img

    def _scaled_preview_cfg(self, cfg: EditConfig) -> EditConfig:
        """Clone *cfg* with the canvas scaled down so the preview pipeline runs
        on a small image. Absolute-pixel radii shrink with it so effects keep
        roughly the same look. The real export still uses the full *cfg*.
        """
        tw = max(1, cfg.fit.target_w)
        th = max(1, cfg.fit.target_h)
        scale = min(1.0, _PREVIEW_RENDER_MAX / max(tw, th))
        if scale >= 0.999:
            return cfg
        import copy
        pc = copy.deepcopy(cfg)
        pc.fit.target_w = max(1, int(round(tw * scale)))
        pc.fit.target_h = max(1, int(round(th * scale)))
        pc.effects.blur *= scale
        pc.effects.glass_blur_radius *= scale
        pc.enhance.sharpen_radius = max(0.1, pc.enhance.sharpen_radius * scale)
        return pc

    def _refresh_preview(self) -> None:
        # Stash the latest editor state into either the active row's override
        # or the global cfg, so the rest of the UI / Apply step has the truth.
        try:
            cur = self._collect_config()
        except Exception:
            cur = None
        if cur is not None:
            if self._active_row is not None:
                self._active_row.edit_cfg = cur
            else:
                self._global_cfg = cur

        # Debounced undo snapshot — one entry per settled edit, global mode only.
        if (cur is not None and not self._restoring and self._active_row is None
                and (not self._undo_stack or self._undo_stack[-1] != cur)):
            self._undo_stack.append(cur)
            if len(self._undo_stack) > 60:
                self._undo_stack.pop(0)
            self._redo_stack.clear()
            self._update_undo_buttons()

        src = self._active_source_image()
        if src is None:
            self._schedule_row_thumbs()
            return
        try:
            psrc = self._preview_source(src)
            if self._show_original:
                preview = psrc.convert("RGB")
            else:
                preview = apply_edits(psrc, self._scaled_preview_cfg(cur or self._global_cfg))
            if max(preview.size) > _PREVIEW_MAX:
                preview = preview.copy()
                preview.thumbnail((_PREVIEW_MAX, _PREVIEW_MAX), Image.Resampling.LANCZOS)
            # Show-mask overlay — tint every masked region red on the preview.
            shown = preview
            if (not self._show_original and self._show_masks_chk.isChecked()
                    and cur is not None and cur.masks):
                try:
                    ov = mask_overlay_image(preview, cur.masks)
                    red = Image.new("RGB", preview.size, (255, 45, 45))
                    shown = Image.composite(Image.blend(preview, red, 0.5), preview, ov)
                except Exception:
                    shown = preview
            self._preview_label.setPixmap(_pil_to_qpixmap(shown))
            self._preview_label.setText("")
            self._histogram.set_image(preview)
        except Exception as exc:
            self._preview_label.setText(f"Preview error: {exc}")
        # Mask outlines — shown only while the Masks sub-tab is open.
        if self._ie_stack.currentIndex() == 3 and self._mask_rows:
            ovs = [r.overlay() for r in self._mask_rows]
            self._preview_label.set_mask_overlays([o for o in ovs if o is not None])
        else:
            self._preview_label.set_mask_overlays([])
        self._schedule_row_thumbs()

    # ── Canvas card (aspect, fit, W×H, swap, bg, flip) ───────────────────────

    def _build_canvas_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_canvas = _hdr(tr("hdr_ie_canvas"))
        layout.addWidget(self._hdr_canvas)

        # Row 0 — aspect preset + swap
        row0 = QHBoxLayout()
        row0.setSpacing(12)
        ap_col = QVBoxLayout()
        self._lbl_aspect = QLabel(tr("lbl_ie_aspect"))
        ap_col.addWidget(self._lbl_aspect)
        self._aspect_combo = QComboBox()
        for key, w, h in ASPECT_PRESETS:
            self._aspect_combo.addItem(tr(f"ie_aspect_{key}"), (key, w, h))
        self._aspect_combo.setFixedWidth(220)
        self._aspect_combo.currentIndexChanged.connect(self._on_aspect_changed)
        ap_col.addWidget(self._aspect_combo)
        row0.addLayout(ap_col)

        sw_col = QVBoxLayout()
        sw_col.addWidget(QLabel(" "))
        self._swap_btn = QPushButton(tr("btn_ie_swap_wh"))
        self._swap_btn.setObjectName("BrowseBtn")
        self._swap_btn.setToolTip(tr("tip_ie_swap_wh"))
        self._swap_btn.clicked.connect(self._swap_wh)
        sw_col.addWidget(self._swap_btn)
        row0.addLayout(sw_col)
        row0.addStretch()
        layout.addLayout(row0)

        # Row 1 — fit + W + H + bg
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        fit_col = QVBoxLayout()
        self._lbl_fit = QLabel(tr("lbl_ie_fit"))
        fit_col.addWidget(self._lbl_fit)
        self._fit_combo = QComboBox()
        for m in FIT_MODES:
            self._fit_combo.addItem(tr(f"ie_fit_{m}"), m)
        self._fit_combo.setFixedWidth(140)
        self._fit_combo.currentIndexChanged.connect(self._schedule_preview)
        fit_col.addWidget(self._fit_combo)
        row1.addLayout(fit_col)

        w_col = QVBoxLayout()
        self._lbl_w = QLabel(tr("lbl_ie_width"))
        w_col.addWidget(self._lbl_w)
        self._w_spin = QSpinBox()
        self._w_spin.setRange(16, 16384)
        self._w_spin.setValue(1080)
        self._w_spin.setFixedWidth(100)
        self._w_spin.valueChanged.connect(self._on_wh_changed)
        w_col.addWidget(self._w_spin)
        row1.addLayout(w_col)

        h_col = QVBoxLayout()
        self._lbl_h = QLabel(tr("lbl_ie_height"))
        h_col.addWidget(self._lbl_h)
        self._h_spin = QSpinBox()
        self._h_spin.setRange(16, 16384)
        self._h_spin.setValue(1080)
        self._h_spin.setFixedWidth(100)
        self._h_spin.valueChanged.connect(self._on_wh_changed)
        h_col.addWidget(self._h_spin)
        row1.addLayout(h_col)

        bg_col = QVBoxLayout()
        self._lbl_bg = QLabel(tr("lbl_ie_bg_color"))
        bg_col.addWidget(self._lbl_bg)
        self._bg_btn = QPushButton("  ")
        self._bg_btn.setFixedSize(60, 28)
        self._bg_color = "#000000"
        self._apply_bg_btn_color()
        self._bg_btn.clicked.connect(self._pick_bg)
        bg_col.addWidget(self._bg_btn)
        row1.addLayout(bg_col)

        row1.addStretch()
        layout.addLayout(row1)

        # Row 2 — flip
        row2 = QHBoxLayout()
        self._flip_h_chk = QCheckBox(tr("lbl_ie_flip_h"))
        self._flip_v_chk = QCheckBox(tr("lbl_ie_flip_v"))
        self._flip_h_chk.toggled.connect(self._schedule_preview)
        self._flip_v_chk.toggled.connect(self._schedule_preview)
        row2.addWidget(self._flip_h_chk)
        row2.addWidget(self._flip_v_chk)
        row2.addStretch()
        layout.addLayout(row2)
        return card

    def _on_aspect_changed(self, _idx: int) -> None:
        data = self._aspect_combo.currentData()
        if not data:
            self._schedule_preview()
            return
        key, w, h = data
        if key == "custom" or (w == 0 and h == 0):
            self._schedule_preview()
            return
        self._w_spin.blockSignals(True)
        self._h_spin.blockSignals(True)
        self._w_spin.setValue(w)
        self._h_spin.setValue(h)
        self._w_spin.blockSignals(False)
        self._h_spin.blockSignals(False)
        self._schedule_preview()

    def _on_wh_changed(self, _v: int) -> None:
        # Manual W/H edit means the aspect combo is no longer "selecting" a preset.
        if self._aspect_combo.currentIndex() != 0:
            self._aspect_combo.blockSignals(True)
            self._aspect_combo.setCurrentIndex(0)  # custom
            self._aspect_combo.blockSignals(False)
        self._schedule_preview()

    def _swap_wh(self) -> None:
        w, h = self._w_spin.value(), self._h_spin.value()
        self._w_spin.blockSignals(True)
        self._h_spin.blockSignals(True)
        self._w_spin.setValue(h)
        self._h_spin.setValue(w)
        self._w_spin.blockSignals(False)
        self._h_spin.blockSignals(False)
        self._aspect_combo.blockSignals(True)
        self._aspect_combo.setCurrentIndex(0)
        self._aspect_combo.blockSignals(False)
        self._schedule_preview()

    def _apply_bg_btn_color(self) -> None:
        self._bg_btn.setStyleSheet(
            f"background:{self._bg_color}; border:1px solid #555; border-radius:4px;"
        )

    def _pick_bg(self) -> None:
        col = QColorDialog.getColor(QColor(self._bg_color), self, tr("lbl_ie_bg_color"))
        if col.isValid():
            self._bg_color = col.name()
            self._apply_bg_btn_color()
            self._schedule_preview()

    # ── Crop & rotate card ───────────────────────────────────────────────────

    def _build_crop_rotate_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_crop = _hdr(tr("hdr_ie_crop_rotate"))
        layout.addWidget(self._hdr_crop)

        # Rotation row
        rot_row = QHBoxLayout()
        self._lbl_rotate = QLabel(tr("lbl_ie_rotate"))
        rot_row.addWidget(self._lbl_rotate)
        self._rotate_spin = QDoubleSpinBox()
        self._rotate_spin.setRange(-180.0, 180.0)
        self._rotate_spin.setDecimals(1)
        self._rotate_spin.setSingleStep(0.5)
        self._rotate_spin.setSuffix("°")
        self._rotate_spin.setFixedWidth(100)
        self._rotate_spin.valueChanged.connect(self._schedule_preview)
        rot_row.addWidget(self._rotate_spin)
        self._rot_ccw_btn = QPushButton("⟲ 90°")
        self._rot_ccw_btn.setObjectName("BrowseBtn")
        self._rot_ccw_btn.clicked.connect(lambda: self._nudge_rotate(-90))
        rot_row.addWidget(self._rot_ccw_btn)
        self._rot_cw_btn = QPushButton("⟳ 90°")
        self._rot_cw_btn.setObjectName("BrowseBtn")
        self._rot_cw_btn.clicked.connect(lambda: self._nudge_rotate(90))
        rot_row.addWidget(self._rot_cw_btn)
        self._rot_180_btn = QPushButton("180°")
        self._rot_180_btn.setObjectName("BrowseBtn")
        self._rot_180_btn.clicked.connect(lambda: self._nudge_rotate(180))
        rot_row.addWidget(self._rot_180_btn)
        rot_row.addStretch()
        layout.addLayout(rot_row)

        # Crop sliders (top/left/bottom/right %)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        self._crop_sliders: dict[str, tuple[QSlider, QLabel]] = {}
        for r, (key, lkey) in enumerate([
            ("top",    "lbl_ie_crop_top"),
            ("left",   "lbl_ie_crop_left"),
            ("bottom", "lbl_ie_crop_bottom"),
            ("right",  "lbl_ie_crop_right"),
        ]):
            lbl = QLabel(tr(lkey))
            lbl.setFixedWidth(90)
            grid.addWidget(lbl, r, 0)
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(0, 49)
            sl.setValue(0)
            sl.valueChanged.connect(self._schedule_preview)
            grid.addWidget(sl, r, 1)
            v = QLabel("0%")
            v.setFixedWidth(48)
            v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            sl.valueChanged.connect(lambda val, lab=v: lab.setText(f"{val}%"))
            grid.addWidget(v, r, 2)
            self._crop_sliders[key] = (sl, lbl)
        layout.addLayout(grid)
        return card

    def _nudge_rotate(self, delta: int) -> None:
        cur = self._rotate_spin.value() + delta
        # Wrap to [-180, 180].
        while cur > 180.0:
            cur -= 360.0
        while cur < -180.0:
            cur += 360.0
        self._rotate_spin.setValue(cur)

    # ── Filter card ───────────────────────────────────────────────────────────

    def _build_filter_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_filter = _hdr(tr("hdr_ie_filter"))
        layout.addWidget(self._hdr_filter)

        row = QHBoxLayout()
        f_col = QVBoxLayout()
        self._lbl_filter = QLabel(tr("lbl_ie_filter"))
        f_col.addWidget(self._lbl_filter)
        self._filter_combo = QComboBox()
        for key in BUILTIN_FILTERS.keys():
            self._filter_combo.addItem(tr(f"ie_filter_{key}"), key)
        self._filter_combo.setFixedWidth(220)
        self._filter_combo.currentIndexChanged.connect(self._schedule_preview)
        f_col.addWidget(self._filter_combo)
        row.addLayout(f_col)

        s_col = QVBoxLayout()
        self._lbl_strength = QLabel(tr("lbl_ie_strength"))
        s_col.addWidget(self._lbl_strength)
        s_row = QHBoxLayout()
        self._strength_slider = QSlider(Qt.Orientation.Horizontal)
        self._strength_slider.setRange(0, 100)
        self._strength_slider.setValue(100)
        self._strength_slider.setFixedWidth(220)
        self._strength_slider.valueChanged.connect(self._on_strength_changed)
        s_row.addWidget(self._strength_slider)
        self._strength_val = QLabel("100%")
        self._strength_val.setFixedWidth(48)
        s_row.addWidget(self._strength_val)
        s_col.addLayout(s_row)
        row.addLayout(s_col)
        row.addStretch()
        layout.addLayout(row)
        return card

    def _on_strength_changed(self, v: int) -> None:
        self._strength_val.setText(f"{v}%")
        self._schedule_preview()

    # ── Adjust card ───────────────────────────────────────────────────────────

    def _build_adjust_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_adjust = _hdr(tr("hdr_ie_adjust"))
        layout.addWidget(self._hdr_adjust)

        self._adjust_chk = QCheckBox(tr("lbl_ie_enable_adjust"))
        self._adjust_chk.toggled.connect(self._schedule_preview)
        layout.addWidget(self._adjust_chk)

        self._adj_sliders: dict[str, tuple[QSlider, QLabel, int, int]] = {}
        # (key, lo, hi, default, label_key)
        defs = [
            ("brightness",   0,   200, 100, "lbl_ie_brightness"),
            ("contrast",     0,   200, 100, "lbl_ie_contrast"),
            ("saturation",   0,   200, 100, "lbl_ie_saturation"),
            ("hue",       -180,   180,   0, "lbl_ie_hue"),
            ("shadows",   -100,   100,   0, "lbl_ie_shadows"),
            ("highlights",-100,   100,   0, "lbl_ie_highlights"),
            ("temperature",-100,  100,   0, "lbl_ie_temperature"),
            ("tint",      -100,   100,   0, "lbl_ie_tint"),
            ("black_point",  0,    50,   0, "lbl_ie_black_point"),
            ("white_point", 50,   100, 100, "lbl_ie_white_point"),
        ]
        self._adj_labels: dict[str, QLabel] = {}
        for key, lo, hi, default, lkey in defs:
            row = QHBoxLayout()
            lbl = QLabel(tr(lkey))
            lbl.setFixedWidth(120)
            self._adj_labels[key] = lbl
            row.addWidget(lbl)
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(lo, hi)
            sl.setValue(default)
            sl.valueChanged.connect(self._schedule_preview)
            row.addWidget(sl)
            val_lbl = QLabel(str(default))
            val_lbl.setFixedWidth(48)
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            sl.valueChanged.connect(lambda v, lab=val_lbl: lab.setText(str(v)))
            row.addWidget(val_lbl)
            layout.addLayout(row)
            self._adj_sliders[key] = (sl, val_lbl, lo, hi)
        return card

    # ── Curves card (master tone curve) ──────────────────────────────────────

    def _build_curves_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_curves = _hdr(tr("hdr_ie_curves"))
        layout.addWidget(self._hdr_curves)

        self._curves_chk = QCheckBox(tr("lbl_ie_enable_curves"))
        self._curves_chk.toggled.connect(self._schedule_preview)
        layout.addWidget(self._curves_chk)

        curve_row = QHBoxLayout()
        self._curve_widget = CurveWidget()
        self._curve_widget.changed.connect(self._on_curve_changed)
        curve_row.addWidget(self._curve_widget)
        curve_row.addStretch()
        layout.addLayout(curve_row)

        btn_row = QHBoxLayout()
        self._curve_reset_btn = QPushButton(tr("btn_ie_curve_reset"))
        self._curve_reset_btn.setObjectName("BrowseBtn")
        self._curve_reset_btn.clicked.connect(self._curve_widget.reset)
        btn_row.addWidget(self._curve_reset_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        return card

    def _on_curve_changed(self) -> None:
        # Touching the curve implies you want it on.
        if not self._curves_chk.isChecked():
            self._curves_chk.blockSignals(True)
            self._curves_chk.setChecked(True)
            self._curves_chk.blockSignals(False)
        self._schedule_preview()

    # ── Enhance card (Photoshop-style enhancing tools) ───────────────────────

    def _build_enhance_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_enhance = _hdr(tr("hdr_ie_enhance"))
        layout.addWidget(self._hdr_enhance)

        self._enh_hint = QLabel(tr("hint_ie_enhance"))
        self._enh_hint.setObjectName("TextMuted")
        self._enh_hint.setWordWrap(True)
        self._enh_hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._enh_hint)

        self._auto_enhance_chk = QCheckBox(tr("lbl_ie_auto_enhance"))
        self._auto_enhance_chk.setToolTip(tr("tip_ie_auto_enhance"))
        self._auto_enhance_chk.toggled.connect(self._schedule_preview)
        layout.addWidget(self._auto_enhance_chk)

        self._enh_sliders: dict[str, tuple[QSlider, QLabel]] = {}
        self._enh_labels: dict[str, QLabel] = {}
        # (key, lo, hi, default, label_key)
        defs = [
            ("exposure",         -200, 200,   0, "lbl_ie_exposure"),          # /100 → stops
            ("gamma",              20, 300, 100, "lbl_ie_gamma"),             # /100 → 0.2..3.0
            ("dehaze",              0, 100,   0, "lbl_ie_dehaze"),            # /100 → 0..1
            ("vibrance",         -100, 100,   0, "lbl_ie_vibrance"),          # /100 → -1..1
            ("clarity",             0, 100,   0, "lbl_ie_clarity"),           # /100 → 0..1
            ("denoise",             0, 100,   0, "lbl_ie_denoise"),           # /100 → 0..1
            ("sharpen_amount",      0, 300,   0, "lbl_ie_sharpen_amount"),    # /100 → 0..3
            ("sharpen_radius",      1,  20,   2, "lbl_ie_sharpen_radius"),    # px (direct)
            ("sharpen_threshold",   0,  20,   3, "lbl_ie_sharpen_threshold"), # direct
        ]
        for key, lo, hi, default, lkey in defs:
            row = QHBoxLayout()
            lbl = QLabel(tr(lkey))
            lbl.setFixedWidth(120)
            self._enh_labels[key] = lbl
            row.addWidget(lbl)
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(lo, hi)
            sl.setValue(default)
            sl.valueChanged.connect(self._schedule_preview)
            row.addWidget(sl)
            v = QLabel(str(default))
            v.setFixedWidth(48)
            v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            sl.valueChanged.connect(lambda val, lab=v: lab.setText(str(val)))
            row.addWidget(v)
            layout.addLayout(row)
            self._enh_sliders[key] = (sl, v)
        return card

    # ── Effects card ──────────────────────────────────────────────────────────

    def _build_effects_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_effects = _hdr(tr("hdr_ie_effects"))
        layout.addWidget(self._hdr_effects)

        self._eff_sliders: dict[str, tuple[QSlider, QLabel]] = {}
        self._eff_labels: dict[str, QLabel] = {}
        defs = [
            ("sharpen",       0, 200, 0, "lbl_ie_sharpen"),    # slider/100 → 0..2.0
            ("blur",          0, 100, 0, "lbl_ie_blur"),       # slider/10  → 0..10 px
            ("grain",         0, 100, 0, "lbl_ie_grain"),      # slider/100 → 0..1
            ("vignette",      0, 100, 0, "lbl_ie_vignette"),   # slider/100 → 0..1
            ("glass_blur",    0, 100, 0, "lbl_ie_glass_blur"), # slider/100 → 0..1
            ("duotone",       0, 100, 0, "lbl_ie_duotone"),    # slider/100 → 0..1
            ("gradient",      0, 100, 0, "lbl_ie_gradient"),   # slider/100 → 0..1
        ]
        for key, lo, hi, default, lkey in defs:
            row = QHBoxLayout()
            lbl = QLabel(tr(lkey))
            lbl.setFixedWidth(120)
            self._eff_labels[key] = lbl
            row.addWidget(lbl)
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(lo, hi)
            sl.setValue(default)
            sl.valueChanged.connect(self._schedule_preview)
            row.addWidget(sl)
            v = QLabel(str(default))
            v.setFixedWidth(48)
            v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            sl.valueChanged.connect(lambda val, lab=v: lab.setText(str(val)))
            row.addWidget(v)
            layout.addLayout(row)
            self._eff_sliders[key] = (sl, v)

        # Colour pickers for duotone + gradient.
        self._eff_colors: dict[str, str] = {
            "duotone_dark":   "#1E3A8A",
            "duotone_light":  "#FCD34D",
            "gradient_c1":    "#000000",
            "gradient_c2":    "#FFFFFF",
        }
        self._eff_color_buttons: dict[str, QPushButton] = {}
        def _make_color_btn(key: str) -> QPushButton:
            btn = QPushButton("  ")
            btn.setFixedSize(36, 22)
            btn.setStyleSheet(f"background:{self._eff_colors[key]}; border:1px solid #555; border-radius:3px;")
            def _pick():
                col = QColorDialog.getColor(QColor(self._eff_colors[key]), self, key)
                if col.isValid():
                    self._eff_colors[key] = col.name()
                    btn.setStyleSheet(f"background:{col.name()}; border:1px solid #555; border-radius:3px;")
                    self._schedule_preview()
            btn.clicked.connect(_pick)
            self._eff_color_buttons[key] = btn
            return btn

        duo_row = QHBoxLayout()
        self._lbl_eff_duo_dark = QLabel(tr("lbl_ie_duotone_dark"))
        duo_row.addWidget(self._lbl_eff_duo_dark)
        duo_row.addWidget(_make_color_btn("duotone_dark"))
        self._lbl_eff_duo_light = QLabel(tr("lbl_ie_duotone_light"))
        duo_row.addWidget(self._lbl_eff_duo_light)
        duo_row.addWidget(_make_color_btn("duotone_light"))
        duo_row.addStretch()
        layout.addLayout(duo_row)

        grad_row = QHBoxLayout()
        self._lbl_eff_grad_c1 = QLabel(tr("lbl_ie_gradient_c1"))
        grad_row.addWidget(self._lbl_eff_grad_c1)
        grad_row.addWidget(_make_color_btn("gradient_c1"))
        self._lbl_eff_grad_c2 = QLabel(tr("lbl_ie_gradient_c2"))
        grad_row.addWidget(self._lbl_eff_grad_c2)
        grad_row.addWidget(_make_color_btn("gradient_c2"))
        self._lbl_eff_grad_angle = QLabel(tr("lbl_ie_gradient_angle"))
        grad_row.addWidget(self._lbl_eff_grad_angle)
        self._grad_angle_spin = QSpinBox()
        self._grad_angle_spin.setRange(0, 359)
        self._grad_angle_spin.setSuffix("°")
        self._grad_angle_spin.setFixedWidth(70)
        self._grad_angle_spin.valueChanged.connect(self._schedule_preview)
        grad_row.addWidget(self._grad_angle_spin)
        grad_row.addStretch()
        layout.addLayout(grad_row)
        return card

    # ── Masks card (stacked local adjustments) ───────────────────────────────

    def _build_masks_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_masks = _hdr(tr("hdr_ie_masks"))
        layout.addWidget(self._hdr_masks)

        self._masks_hint = QLabel(tr("hint_ie_masks"))
        self._masks_hint.setObjectName("TextMuted")
        self._masks_hint.setWordWrap(True)
        self._masks_hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._masks_hint)

        add_row = QHBoxLayout()
        self._mask_add_btn = QPushButton(tr("btn_ie_mask_add"))
        self._mask_add_btn.setObjectName("BrowseBtn")
        self._mask_add_btn.clicked.connect(lambda: self._add_mask_row())
        add_row.addWidget(self._mask_add_btn)
        self._show_masks_chk = QCheckBox(tr("lbl_ie_show_masks"))
        self._show_masks_chk.setToolTip(tr("tip_ie_show_masks"))
        self._show_masks_chk.toggled.connect(self._schedule_preview)
        add_row.addWidget(self._show_masks_chk)
        add_row.addStretch()
        layout.addLayout(add_row)

        self._mask_rows_layout = QVBoxLayout()
        self._mask_rows_layout.setSpacing(6)
        layout.addLayout(self._mask_rows_layout)
        return card

    def _add_mask_row(self, layer: Optional[MaskLayer] = None, index: Optional[int] = None) -> None:
        row = _MaskRow(layer if layer is not None else MaskLayer())
        row.removed.connect(self._remove_mask_row)
        row.changed.connect(self._schedule_preview)
        row.request_region.connect(self._begin_mask_region)
        row.move_up.connect(self._move_mask_up)
        row.move_down.connect(self._move_mask_down)
        row.duplicate.connect(self._duplicate_mask_row)
        row.type_combo.currentIndexChanged.connect(
            lambda _i, r=row: self._on_mask_type_changed(r))
        if index is None or index >= len(self._mask_rows):
            self._mask_rows.append(row)
            self._mask_rows_layout.addWidget(row)
        else:
            self._mask_rows.insert(index, row)
            self._mask_rows_layout.insertWidget(index, row)
        self._renumber_masks()
        self._schedule_preview()

    def _move_mask_up(self, row: "_MaskRow") -> None:
        if row not in self._mask_rows:
            return
        i = self._mask_rows.index(row)
        if i <= 0:
            return
        self._mask_rows[i - 1], self._mask_rows[i] = self._mask_rows[i], self._mask_rows[i - 1]
        self._mask_rows_layout.removeWidget(row)
        self._mask_rows_layout.insertWidget(i - 1, row)
        self._renumber_masks()
        self._schedule_preview()

    def _move_mask_down(self, row: "_MaskRow") -> None:
        if row not in self._mask_rows:
            return
        i = self._mask_rows.index(row)
        if i >= len(self._mask_rows) - 1:
            return
        self._mask_rows[i + 1], self._mask_rows[i] = self._mask_rows[i], self._mask_rows[i + 1]
        self._mask_rows_layout.removeWidget(row)
        self._mask_rows_layout.insertWidget(i + 1, row)
        self._renumber_masks()
        self._schedule_preview()

    def _duplicate_mask_row(self, row: "_MaskRow") -> None:
        i = self._mask_rows.index(row) if row in self._mask_rows else len(self._mask_rows) - 1
        self._add_mask_row(row.to_layer(), index=i + 1)

    def _remove_mask_row(self, row: "_MaskRow") -> None:
        if self._active_mask_row is row:
            self._active_mask_row = None
            self._preview_label.mask_mode = None
            self._preview_label.setCursor(Qt.CursorShape.ArrowCursor)
        if row in self._mask_rows:
            self._mask_rows.remove(row)
        self._mask_rows_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self._renumber_masks()
        self._schedule_preview()

    def _clear_mask_rows(self) -> None:
        self._active_mask_row = None
        self._preview_label.mask_mode = None
        for row in list(self._mask_rows):
            self._mask_rows.remove(row)
            self._mask_rows_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()

    def _renumber_masks(self) -> None:
        for i, row in enumerate(self._mask_rows, 1):
            row.set_index(i)

    def _begin_mask_region(self, row: "_MaskRow") -> None:
        """Arm the preview so the next drag / click / paint stroke sets this mask."""
        t = row.mask_type()
        if t == "brush":
            # The paint button is checkable for brush — toggle paint mode.
            if not row.region_btn.isChecked():
                self._end_mask_region()
                return
            self._active_mask_row = row
            self._preview_label.mask_mode = "brush"
            self._preview_label.brush_size_frac = row.brush_size_frac()
            self._preview_label.brush_erase = row.brush_erase()
            self._preview_label.setCursor(Qt.CursorShape.CrossCursor)
            if self._crop_mode_btn.isChecked():
                self._crop_mode_btn.setChecked(False)
            self.status_message.emit(tr("ie_mask_brush_hint"), False)
            return
        self._active_mask_row = row
        self._preview_label.mask_mode = t
        self._preview_label.setCursor(Qt.CursorShape.CrossCursor)
        if self._crop_mode_btn.isChecked():
            self._crop_mode_btn.setChecked(False)
        hint = "ie_mask_color_hint" if t == "color" else "ie_mask_region_hint"
        self.status_message.emit(tr(hint), False)

    def _on_mask_type_changed(self, row: "_MaskRow") -> None:
        """If the armed brush row switched away from brush, disarm painting."""
        if (self._active_mask_row is row and row.mask_type() != "brush"
                and self._preview_label.mask_mode == "brush"):
            self._end_mask_region()

    def _end_mask_region(self) -> None:
        self._active_mask_row = None
        self._preview_label.mask_mode = None
        self._preview_label.setCursor(Qt.CursorShape.ArrowCursor)

    def _on_mask_geometry_set(self, x0: float, y0: float, x1: float, y1: float) -> None:
        if self._active_mask_row is None:
            return
        self._active_mask_row.set_geometry(x0, y0, x1, y1)  # emits changed → preview
        self._end_mask_region()

    def _on_mask_color_picked(self, r: int, g: int, b: int) -> None:
        if self._active_mask_row is None:
            return
        self._active_mask_row.set_pick_color(f"#{r:02X}{g:02X}{b:02X}")  # emits changed
        self._end_mask_region()

    def _on_brush_stroke(self, points: list) -> None:
        """A finished freehand stroke — append it to the armed brush mask.

        Brush mode stays armed afterwards so the user can paint stroke after
        stroke; they click the Paint button again (or switch tools) to stop.
        """
        row = self._active_mask_row
        if row is None or row.mask_type() != "brush":
            return
        row.add_brush_stroke(points)  # emits changed → preview refresh
        # Keep the live brush params in sync for the next stroke.
        self._preview_label.brush_size_frac = row.brush_size_frac()
        self._preview_label.brush_erase = row.brush_erase()

    # ── Preset card ───────────────────────────────────────────────────────────

    def _build_preset_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_preset = _hdr(tr("hdr_ie_presets"))
        layout.addWidget(self._hdr_preset)

        row = QHBoxLayout()
        self._preset_combo = QComboBox()
        self._preset_combo.setFixedWidth(220)
        row.addWidget(self._preset_combo)
        self._load_preset_btn = QPushButton(tr("btn_ie_load_preset"))
        self._load_preset_btn.setObjectName("BrowseBtn")
        self._load_preset_btn.clicked.connect(self._on_load_preset)
        row.addWidget(self._load_preset_btn)
        self._save_preset_btn = QPushButton(tr("btn_ie_save_preset"))
        self._save_preset_btn.setObjectName("BrowseBtn")
        self._save_preset_btn.clicked.connect(self._on_save_preset)
        row.addWidget(self._save_preset_btn)
        self._del_preset_btn = QPushButton(tr("btn_ie_delete_preset"))
        self._del_preset_btn.setObjectName("BrowseBtn")
        self._del_preset_btn.clicked.connect(self._on_delete_preset)
        row.addWidget(self._del_preset_btn)
        row.addStretch()
        layout.addLayout(row)
        return card

    def _reload_user_presets(self) -> None:
        self._preset_combo.clear()
        presets = load_user_presets()
        if not presets:
            self._preset_combo.addItem(tr("ie_preset_none"), None)
        else:
            for name in sorted(presets.keys()):
                self._preset_combo.addItem(name, name)

    def _on_save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, tr("btn_ie_save_preset"), tr("ph_ie_preset_name"))
        if not ok or not name.strip():
            return
        try:
            save_user_preset(name.strip(), self._collect_config())
            self._reload_user_presets()
            idx = self._preset_combo.findData(name.strip())
            if idx >= 0:
                self._preset_combo.setCurrentIndex(idx)
            self.status_message.emit(tr("ie_preset_saved").format(name=name.strip()), False)
        except Exception as exc:
            self.status_message.emit(f"Save preset failed: {exc}", True)

    def _on_load_preset(self) -> None:
        name = self._preset_combo.currentData()
        if not name:
            return
        presets = load_user_presets()
        if name not in presets:
            return
        cfg = preset_to_config(presets[name])
        self._apply_config(cfg)
        self._schedule_preview()
        self.status_message.emit(tr("ie_preset_loaded").format(name=name), False)

    def _on_delete_preset(self) -> None:
        name = self._preset_combo.currentData()
        if not name:
            return
        reply = QMessageBox.question(
            self, tr("btn_ie_delete_preset"),
            tr("ie_preset_delete_confirm").format(name=name),
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_user_preset(name)
            self._reload_user_presets()

    # ── Row reorder ───────────────────────────────────────────────────────────

    def _move_row_up(self, row: "_MonitorRow") -> None:
        if row not in self._wp_rows:
            return
        idx = self._wp_rows.index(row)
        if idx <= 0:
            return
        self._wp_rows[idx - 1], self._wp_rows[idx] = self._wp_rows[idx], self._wp_rows[idx - 1]
        self._wp_rows_layout.removeWidget(row)
        self._wp_rows_layout.insertWidget(idx - 1, row)
        self._save_wallpaper_setup()
        self._schedule_row_thumbs()

    def _move_row_down(self, row: "_MonitorRow") -> None:
        if row not in self._wp_rows:
            return
        idx = self._wp_rows.index(row)
        if idx >= len(self._wp_rows) - 1:
            return
        self._wp_rows[idx + 1], self._wp_rows[idx] = self._wp_rows[idx], self._wp_rows[idx + 1]
        self._wp_rows_layout.removeWidget(row)
        self._wp_rows_layout.insertWidget(idx + 1, row)
        self._save_wallpaper_setup()
        self._schedule_row_thumbs()

    # ── Active-row banner (shown only while editing a wallpaper row) ─────────

    def _build_active_row_banner(self) -> QFrame:
        self._active_banner = QFrame()
        self._active_banner.setObjectName("Card")
        self._active_banner.setStyleSheet(
            "QFrame#Card { border: 1px solid #3B82F6; background-color: rgba(59,130,246,0.10); }"
        )
        row = QHBoxLayout(self._active_banner)
        row.setContentsMargins(16, 8, 16, 8)
        self._active_banner_lbl = QLabel("")
        self._active_banner_lbl.setStyleSheet("color: #93C5FD; font-weight: bold;")
        row.addWidget(self._active_banner_lbl)
        row.addStretch()
        self._stop_edit_btn = QPushButton(tr("btn_ie_wp_stop_editing"))
        self._stop_edit_btn.setObjectName("BrowseBtn")
        self._stop_edit_btn.clicked.connect(self._stop_editing_row)
        row.addWidget(self._stop_edit_btn)
        self._active_banner.setVisible(False)
        return self._active_banner

    def _on_row_selected(self, row: "_MonitorRow") -> None:
        """Enter per-row edit mode: editor controls now drive THIS row's edit_cfg."""
        if self._active_row is row:
            return
        # Leaving global mode? Stash current controls as the global config.
        if self._active_row is None:
            self._global_cfg = self._collect_config()
        for r in self._wp_rows:
            r.set_active(r is row)
        self._active_row = row
        # Seed row edit_cfg from the current global edit state if it has no override yet.
        if row.edit_cfg is None:
            row.edit_cfg = EditConfig(
                fit=FitOptions(**asdict(self._global_cfg.fit)),
                enhance=EnhanceOptions(**asdict(self._global_cfg.enhance)),
                filter=FilterOptions(**asdict(self._global_cfg.filter)),
                adjust=AdjustOptions(**asdict(self._global_cfg.adjust)),
                effects=EffectsOptions(**asdict(self._global_cfg.effects)),
            )
        self._apply_config(row.edit_cfg)
        # Invalidate cached source so the next preview reloads from the row.
        self._active_row_src_path = None
        self._active_row_src_image = None
        self._active_banner_lbl.setText(
            tr("ie_wp_editing_row").format(label=row.label_edit.text() or "Monitor")
        )
        self._active_banner.setVisible(True)
        self._schedule_preview()

    def _stop_editing_row(self) -> None:
        if self._active_row is None:
            return
        # Persist current controls into the row's override before exiting.
        self._active_row.edit_cfg = self._collect_config()
        self._active_row.set_active(False)
        self._active_row = None
        self._active_banner.setVisible(False)
        # Restore global edit state into the controls.
        self._apply_config(self._global_cfg)
        self._save_wallpaper_setup()
        self._schedule_preview()

    def _active_source_image(self) -> Optional[Image.Image]:
        """Return the source image the preview should show, given active-row mode."""
        if self._active_row is None:
            return self._src_image
        path = self._active_row.source_edit.text().strip()
        if path and os.path.isfile(path):
            if path != self._active_row_src_path:
                try:
                    self._active_row_src_image = load_image(path)
                    self._active_row_src_path = path
                except Exception:
                    return self._src_image
            return self._active_row_src_image
        return self._src_image

    # ── Wallpaper / multi-monitor card ───────────────────────────────────────

    def _build_wallpaper_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_wp = _hdr(tr("hdr_ie_wallpaper"))
        layout.addWidget(self._hdr_wp)

        self._wp_hint = QLabel(tr("hint_ie_wallpaper"))
        self._wp_hint.setObjectName("TextMuted")
        self._wp_hint.setWordWrap(True)
        self._wp_hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._wp_hint)

        # Action row: Detect / Add
        action_row = QHBoxLayout()
        self._wp_detect_btn = QPushButton(tr("btn_ie_wp_detect"))
        self._wp_detect_btn.setObjectName("BrowseBtn")
        self._wp_detect_btn.clicked.connect(self._detect_monitors)
        action_row.addWidget(self._wp_detect_btn)
        self._wp_add_btn = QPushButton(tr("btn_ie_wp_add_monitor"))
        self._wp_add_btn.setObjectName("BrowseBtn")
        self._wp_add_btn.clicked.connect(self._add_monitor_row)
        action_row.addWidget(self._wp_add_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        # Live layout preview (Wallpaper-Engine style)
        self._layout_preview = LayoutPreviewWidget()
        layout.addWidget(self._layout_preview)

        # Rows container
        self._wp_rows_layout = QVBoxLayout()
        self._wp_rows_layout.setSpacing(6)
        layout.addLayout(self._wp_rows_layout)
        self._wp_rows: list[_MonitorRow] = []

        # Base name + export controls
        name_row = QHBoxLayout()
        self._wp_lbl_name = QLabel(tr("lbl_ie_wp_base_name"))
        name_row.addWidget(self._wp_lbl_name)
        self._wp_name_edit = QLineEdit()
        self._wp_name_edit.setObjectName("PillInput")
        self._wp_name_edit.setPlaceholderText(tr("ph_ie_wp_base_name"))
        name_row.addWidget(self._wp_name_edit)
        layout.addLayout(name_row)

        export_row = QHBoxLayout()
        self._wp_export_per_btn = QPushButton(tr("btn_ie_wp_export_per_monitor"))
        self._wp_export_per_btn.setObjectName("BrowseBtn")
        self._wp_export_per_btn.clicked.connect(self._export_per_monitor)
        export_row.addWidget(self._wp_export_per_btn)
        self._wp_export_span_btn = QPushButton(tr("btn_ie_wp_export_spanned"))
        self._wp_export_span_btn.setObjectName("BrowseBtn")
        self._wp_export_span_btn.clicked.connect(self._export_spanned)
        export_row.addWidget(self._wp_export_span_btn)
        self._wp_apply_btn = QPushButton(tr("btn_ie_wp_apply_now"))
        self._wp_apply_btn.setObjectName("BrowseBtn")
        self._wp_apply_btn.setToolTip(tr("tip_ie_wp_apply_now"))
        self._wp_apply_btn.clicked.connect(self._apply_per_monitor_now)
        export_row.addWidget(self._wp_apply_btn)
        self._wp_open_settings_btn = QPushButton(tr("btn_ie_wp_open_settings"))
        self._wp_open_settings_btn.setObjectName("BrowseBtn")
        self._wp_open_settings_btn.clicked.connect(self._open_wp_settings)
        export_row.addWidget(self._wp_open_settings_btn)
        export_row.addStretch()
        layout.addLayout(export_row)
        return card

    def _add_monitor_row(self, spec: Optional[MonitorSpec] = None) -> None:
        if spec is None:
            n = len(self._wp_rows) + 1
            # New rows default to 1920×1080 stacked horizontally next to existing.
            # fit_mode="fill" = no crop (Wallpaper-Engine "Scale and Fit").
            x_off = sum(r.to_spec().width for r in self._wp_rows)
            spec = MonitorSpec(
                label=f"Monitor {n}", width=1920, height=1080,
                x=x_off, y=0, fit_mode="fill",
            )
        row = _MonitorRow(spec)
        row.removed.connect(self._remove_monitor_row)
        row.changed.connect(self._on_row_changed)
        row.selected.connect(self._on_row_selected)
        row.move_up.connect(self._move_row_up)
        row.move_down.connect(self._move_row_down)
        self._wp_rows.append(row)
        self._wp_rows_layout.addWidget(row)
        self._schedule_row_thumbs()
        self._save_wallpaper_setup()

    def _on_row_changed(self) -> None:
        self._schedule_row_thumbs()
        self._save_wallpaper_setup()

    def _remove_monitor_row(self, row: _MonitorRow) -> None:
        if self._active_row is row:
            # Leaving active row via delete — restore global cfg into controls.
            self._active_row = None
            self._active_banner.setVisible(False)
            self._apply_config(self._global_cfg)
        if row in self._wp_rows:
            self._wp_rows.remove(row)
        self._wp_rows_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self._save_wallpaper_setup()

    def _clear_monitor_rows(self) -> None:
        for row in list(self._wp_rows):
            self._remove_monitor_row(row)

    # ── Persistence ──────────────────────────────────────────────────────────

    def _wallpaper_setup_file(self) -> str:
        from utils.paths import user_config_dir
        return os.path.join(str(user_config_dir()), "wallpaper_setup.json")

    def _save_wallpaper_setup(self) -> None:
        try:
            import json
            from dataclasses import asdict
            data = {"rows": [asdict(r.to_spec()) for r in self._wp_rows]}
            path = self._wallpaper_setup_file()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _load_wallpaper_setup(self) -> bool:
        """Restore saved monitor rows. Returns True if any were loaded."""
        try:
            import json
            path = self._wallpaper_setup_file()
            if not os.path.isfile(path):
                return False
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            rows = data.get("rows") or []
            if not rows:
                return False
            for blob in rows:
                spec = MonitorSpec()
                for k in spec.__dataclass_fields__:
                    if k not in blob:
                        continue
                    if k == "edit_cfg" and isinstance(blob[k], dict):
                        spec.edit_cfg = preset_to_config(blob[k])
                    else:
                        setattr(spec, k, blob[k])
                self._add_monitor_row(spec)
            return True
        except Exception:
            return False

    # ── Row thumbnails ───────────────────────────────────────────────────────

    def _schedule_row_thumbs(self) -> None:
        if not hasattr(self, "_row_thumb_timer"):
            self._row_thumb_timer = QTimer(self)
            self._row_thumb_timer.setSingleShot(True)
            self._row_thumb_timer.setInterval(150)
            self._row_thumb_timer.timeout.connect(self._refresh_row_thumbnails)
        self._row_thumb_timer.start()

    def _refresh_row_thumbnails(self) -> None:
        if not self._wp_rows:
            if hasattr(self, "_layout_preview"):
                self._layout_preview.set_entries([])
            return
        # Use the global cfg as fallback — _render_one_monitor picks the row's
        # own edit_cfg when present, falls back to base_cfg otherwise.
        cfg = self._global_cfg
        # Downscaled source — row thumbnails are tiny, full-res input is wasted work.
        fallback = self._preview_source(self._src_image)
        layout_entries: list[tuple[int, int, int, int, str, QPixmap]] = []
        source_cache: dict[str, Image.Image] = {}
        for row in self._wp_rows:
            spec = row.to_spec()
            src = fallback
            if spec.source_path and os.path.isfile(spec.source_path):
                if spec.source_path not in source_cache:
                    try:
                        im = load_image(spec.source_path)
                        im.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
                        source_cache[spec.source_path] = im
                    except Exception:
                        row.set_thumbnail(None)
                        continue
                src = source_cache[spec.source_path]
            if src is None:
                row.set_thumbnail(None)
                continue
            try:
                # Render a tiny version: replace target W×H with thumb-sized values
                # scaled to the same aspect to keep the pipeline fast.
                tw, th = 140, 84
                ratio = min(tw / max(1, spec.width), th / max(1, spec.height))
                scaled_w = max(16, int(spec.width * ratio))
                scaled_h = max(16, int(spec.height * ratio))
                blob = asdict(spec)
                # Drop nested objects asdict can't round-trip cleanly; we only need geometry+grade for the preview.
                blob.pop("edit_cfg", None)
                preview_spec = MonitorSpec(**{**blob, "width": scaled_w, "height": scaled_h})
                preview_spec.edit_cfg = spec.edit_cfg
                rendered = _render_one_monitor(src, preview_spec, cfg)
                pm = _pil_to_qpixmap(rendered)
                row.set_thumbnail(pm)
                layout_entries.append((spec.x, spec.y, spec.width, spec.height, spec.label, pm))
            except Exception:
                row.set_thumbnail(None)
                layout_entries.append((spec.x, spec.y, spec.width, spec.height, spec.label, QPixmap()))
        if hasattr(self, "_layout_preview"):
            self._layout_preview.set_entries(layout_entries)

    def _detect_monitors(self) -> None:
        """Populate one row per physical monitor.

        On Windows uses `IDesktopWallpaper` enumeration so each row carries the
        exact device path it should target on Apply — this immunises the apply
        step against rows being reordered or deleted. Off-Windows falls back to
        Qt's `QGuiApplication.screens()` (no device id, apply uses index order).
        """
        win_monitors: list[dict] = []
        try:
            from core.wallpaper_setter import list_monitors as _list_monitors, is_supported
            if is_supported():
                win_monitors = _list_monitors()
        except Exception:
            win_monitors = []

        screens = QGuiApplication.screens()
        if not win_monitors and not screens:
            self.status_message.emit(tr("ie_wp_err_no_monitors"), True)
            return
        self._clear_monitor_rows()

        if win_monitors:
            # Pair Windows monitor records to Qt screens (by geometry origin) so we get a nicer label.
            def _qt_label_for(x: int, y: int) -> str:
                for s in screens:
                    g = s.geometry()
                    dpr = s.devicePixelRatio() or 1.0
                    sx = int(round(g.x() * dpr))
                    sy = int(round(g.y() * dpr))
                    if sx == x and sy == y:
                        return s.name() or ""
                return ""
            for i, m in enumerate(win_monitors, 1):
                w = max(1, m.get("width") or 1920)
                h = max(1, m.get("height") or 1080)
                label = _qt_label_for(m.get("x", 0), m.get("y", 0)) or f"Monitor {i}"
                self._add_monitor_row(MonitorSpec(
                    label=label, width=w, height=h,
                    x=m.get("x", 0), y=m.get("y", 0),
                    fit_mode="fill",
                    monitor_id=m.get("id"),
                ))
            self.status_message.emit(tr("ie_wp_detected").format(n=len(win_monitors)), False)
            return

        # Non-Windows fallback.
        for i, screen in enumerate(screens, 1):
            geo = screen.geometry()
            dpr = screen.devicePixelRatio() or 1.0
            px_w = int(round(geo.width() * dpr))
            px_h = int(round(geo.height() * dpr))
            px_x = int(round(geo.x() * dpr))
            px_y = int(round(geo.y() * dpr))
            name = screen.name() or f"Monitor {i}"
            self._add_monitor_row(MonitorSpec(
                label=name, width=px_w, height=px_h, x=px_x, y=px_y,
                fit_mode="fill",
            ))
        self.status_message.emit(tr("ie_wp_detected").format(n=len(screens)), False)

    def _wp_specs(self) -> list[MonitorSpec]:
        return [r.to_spec() for r in self._wp_rows]

    def _wp_out_dir(self) -> str:
        return self._out_input.text().strip() or os.path.dirname(self._src_path or "") or os.path.expanduser("~")

    def _wp_base_name(self) -> str:
        name = self._wp_name_edit.text().strip()
        if name:
            return name
        if self._src_path:
            return os.path.splitext(os.path.basename(self._src_path))[0] + "_wallpaper"
        # Fall back to first per-row source if no main image is loaded.
        for row in self._wp_rows:
            sp = row.source_edit.text().strip()
            if sp:
                return os.path.splitext(os.path.basename(sp))[0] + "_wallpaper"
        return "wallpaper"

    def _export_per_monitor(self) -> None:
        specs = self._wp_specs()
        if not specs:
            self.status_message.emit(tr("ie_wp_err_no_monitors"), True)
            return
        main_src = self._src_path if (self._src_path and os.path.isfile(self._src_path)) else None
        if main_src is None and any(not s.source_path for s in specs):
            self.status_message.emit(tr("ie_wp_err_missing_source"), True)
            return
        try:
            paths = export_wallpapers(
                main_src, specs, self._global_cfg,
                self._wp_out_dir(), self._wp_base_name(),
                do_per_monitor=True, do_spanned=False,
            )
            self._log_wallpaper_history(paths)
            # Remember per-monitor outputs in row order for "Apply now".
            self._last_per_monitor_paths = [
                paths.get(spec.label, "") for spec in specs
            ]
            self.status_message.emit(
                tr("ie_wp_done_per_monitor").format(n=len(paths), dir=self._wp_out_dir()), False,
            )
        except Exception as exc:
            self.status_message.emit(f"Wallpaper export failed: {exc}", True)

    def _export_spanned(self) -> None:
        specs = self._wp_specs()
        if not specs:
            self.status_message.emit(tr("ie_wp_err_no_monitors"), True)
            return
        main_src = self._src_path if (self._src_path and os.path.isfile(self._src_path)) else None
        if main_src is None and any(not s.source_path for s in specs):
            self.status_message.emit(tr("ie_wp_err_missing_source"), True)
            return
        try:
            paths = export_wallpapers(
                main_src, specs, self._global_cfg,
                self._wp_out_dir(), self._wp_base_name(),
                do_per_monitor=False, do_spanned=True,
            )
            self._log_wallpaper_history(paths)
            spanned = paths.get("__spanned__", "")
            self.status_message.emit(tr("ie_wp_done_spanned").format(path=spanned), False)
        except Exception as exc:
            self.status_message.emit(f"Wallpaper export failed: {exc}", True)

    def _log_wallpaper_history(self, paths: dict) -> None:
        for label, path in paths.items():
            name = os.path.basename(path)
            get_history_manager().add_item(HistoryItem(
                task_type="image_editor",
                file_name=name,
                file_path=path,
                status="success",
            ))
        # Track most recent for "open output folder" affordances.
        if paths:
            self._last_result_path = next(iter(paths.values()))

    def _apply_per_monitor_now(self) -> None:
        """Always re-export with current edits to a private cache dir, then push to monitors.

        Uses a dedicated `wallpaper_cache/` dir with timestamp-suffixed filenames
        so Windows reads a fresh file every time (the wallpaper cache keys on
        path; same path + Windows cache = stale image, so we always vary the name).
        """
        import time
        from core.wallpaper_setter import apply_assignments, apply_slideshow, is_supported
        if not is_supported():
            self.status_message.emit(tr("ie_wp_apply_unsupported"), True)
            return
        specs = self._wp_specs()
        if not specs:
            self.status_message.emit(tr("ie_wp_err_no_monitors"), True)
            return
        main_src = self._src_path if (self._src_path and os.path.isfile(self._src_path)) else None
        if main_src is None and any(not s.source_path for s in specs):
            self.status_message.emit(tr("ie_wp_err_missing_source"), True)
            return
        try:
            from utils.paths import user_data_dir
            cache_dir = os.path.join(str(user_data_dir()), "wallpaper_cache")
            os.makedirs(cache_dir, exist_ok=True)
            self._prune_wallpaper_cache(cache_dir, keep=20)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            # Ensure the latest editor controls are captured into either the
            # active row's override or the global cfg before we export.
            cur = self._collect_config()
            if self._active_row is not None:
                self._active_row.edit_cfg = cur
            else:
                self._global_cfg = cur
            paths_dict = export_wallpapers(
                main_src, specs, self._global_cfg,
                cache_dir, f"wallpaper_{stamp}",
                do_per_monitor=True, do_spanned=False,
            )
            self._last_per_monitor_paths = [paths_dict.get(s.label, "") for s in specs]
            # Slideshow rows: system-wide. Use the first enabled one if any.
            sld_row = next(
                (s for s in specs if s.use_slideshow and s.slideshow_folder), None,
            )
            slideshow_done = False
            if sld_row is not None:
                try:
                    apply_slideshow(
                        sld_row.slideshow_folder,
                        interval_minutes=int(sld_row.slideshow_interval_minutes),
                    )
                    slideshow_done = True
                except Exception as exc:
                    self.status_message.emit(f"Slideshow failed: {exc}", True)

            # Still-image assignments — skip slideshow rows.
            assignments: list[tuple[Optional[str], str]] = []
            for spec in specs:
                if spec.use_slideshow:
                    continue
                path = paths_dict.get(spec.label, "")
                if not path:
                    continue
                assignments.append((spec.monitor_id, path))
            n = 0
            if assignments:
                n = apply_assignments(assignments)
            total = n + (1 if slideshow_done else 0)
            if total == 0:
                self.status_message.emit(tr("ie_wp_err_no_monitors"), True)
                return
            self.status_message.emit(tr("ie_wp_applied").format(n=total), False)
        except NotImplementedError:
            self.status_message.emit(tr("ie_wp_apply_unsupported"), True)
        except Exception as exc:
            self.status_message.emit(f"Apply wallpapers failed: {exc}", True)

    def _prune_wallpaper_cache(self, cache_dir: str, keep: int = 20) -> None:
        """Keep only the newest `keep` files in the wallpaper cache to avoid disk creep."""
        try:
            entries = []
            for name in os.listdir(cache_dir):
                p = os.path.join(cache_dir, name)
                if os.path.isfile(p):
                    entries.append((os.path.getmtime(p), p))
            entries.sort(reverse=True)
            for _mtime, p in entries[keep:]:
                try:
                    os.remove(p)
                except OSError:
                    pass
        except OSError:
            pass

    def _open_wp_settings(self) -> None:
        # Windows: ms-settings:personalization-background. Mac/Linux: open desktop settings best-effort.
        import sys as _sys
        if _sys.platform == "win32":
            QDesktopServices.openUrl(QUrl("ms-settings:personalization-background"))
        elif _sys.platform == "darwin":
            QDesktopServices.openUrl(QUrl("x-apple.systempreferences:com.apple.preference.desktopscreeneffect"))
        else:
            # Best effort on Linux — opens the output folder so user can drag-set.
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._wp_out_dir()))

    # ── Setup presets card (named multi-monitor setups) ──────────────────────

    def _build_setup_presets_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_setup_presets = _hdr(tr("hdr_ie_wp_setup_presets"))
        layout.addWidget(self._hdr_setup_presets)
        self._hint_setup_presets = QLabel(tr("hint_ie_wp_setup_presets"))
        self._hint_setup_presets.setObjectName("TextMuted")
        self._hint_setup_presets.setWordWrap(True)
        self._hint_setup_presets.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint_setup_presets)
        row = QHBoxLayout()
        self._setup_combo = QComboBox()
        self._setup_combo.setFixedWidth(220)
        row.addWidget(self._setup_combo)
        self._setup_load_btn = QPushButton(tr("btn_ie_wp_setup_load"))
        self._setup_load_btn.setObjectName("BrowseBtn")
        self._setup_load_btn.clicked.connect(self._on_setup_load)
        row.addWidget(self._setup_load_btn)
        self._setup_save_btn = QPushButton(tr("btn_ie_wp_setup_save"))
        self._setup_save_btn.setObjectName("BrowseBtn")
        self._setup_save_btn.clicked.connect(self._on_setup_save)
        row.addWidget(self._setup_save_btn)
        self._setup_del_btn = QPushButton(tr("btn_ie_wp_setup_delete"))
        self._setup_del_btn.setObjectName("BrowseBtn")
        self._setup_del_btn.clicked.connect(self._on_setup_delete)
        row.addWidget(self._setup_del_btn)
        row.addStretch()
        layout.addLayout(row)
        self._reload_setup_presets()
        return card

    def _reload_setup_presets(self) -> None:
        from core import wallpaper_setups
        self._setup_combo.clear()
        names = wallpaper_setups.list_names()
        if not names:
            self._setup_combo.addItem(tr("ie_wp_setup_none"), None)
        else:
            for n in names:
                self._setup_combo.addItem(n, n)

    def _on_setup_save(self) -> None:
        from core import wallpaper_setups
        name, ok = QInputDialog.getText(
            self, tr("btn_ie_wp_setup_save"), tr("ph_ie_wp_setup_name"),
        )
        if not ok or not name.strip():
            return
        try:
            wallpaper_setups.save(name.strip(), [r.to_spec() for r in self._wp_rows])
            self._reload_setup_presets()
            idx = self._setup_combo.findData(name.strip())
            if idx >= 0:
                self._setup_combo.setCurrentIndex(idx)
            self.status_message.emit(tr("ie_wp_setup_saved").format(name=name.strip()), False)
        except Exception as exc:
            self.status_message.emit(f"Save setup failed: {exc}", True)

    def _on_setup_load(self) -> None:
        from core import wallpaper_setups
        name = self._setup_combo.currentData()
        if not name:
            return
        specs = wallpaper_setups.load(name)
        if not specs:
            self.status_message.emit(tr("ie_wp_setup_empty"), True)
            return
        self._clear_monitor_rows()
        for s in specs:
            self._add_monitor_row(s)
        self.status_message.emit(tr("ie_wp_setup_loaded").format(name=name), False)

    def _on_setup_delete(self) -> None:
        from core import wallpaper_setups
        name = self._setup_combo.currentData()
        if not name:
            return
        reply = QMessageBox.question(
            self, tr("btn_ie_wp_setup_delete"),
            tr("ie_wp_setup_delete_confirm").format(name=name),
        )
        if reply == QMessageBox.StandardButton.Yes:
            wallpaper_setups.delete(name)
            self._reload_setup_presets()

    # ── Schedule card ────────────────────────────────────────────────────────

    def _build_schedule_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_schedule = _hdr(tr("hdr_ie_wp_schedule"))
        layout.addWidget(self._hdr_schedule)
        self._hint_schedule = QLabel(tr("hint_ie_wp_schedule"))
        self._hint_schedule.setObjectName("TextMuted")
        self._hint_schedule.setWordWrap(True)
        self._hint_schedule.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint_schedule)

        self._schedule_rows_layout = QVBoxLayout()
        self._schedule_rows_layout.setSpacing(4)
        layout.addLayout(self._schedule_rows_layout)
        self._schedule_rows: list[QWidget] = []

        btn_row = QHBoxLayout()
        self._sched_add_btn = QPushButton(tr("btn_ie_wp_schedule_add"))
        self._sched_add_btn.setObjectName("BrowseBtn")
        self._sched_add_btn.clicked.connect(self._add_schedule_row)
        btn_row.addWidget(self._sched_add_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        self._load_schedule_rows()
        return card

    def _add_schedule_row(self, entry=None) -> None:
        from core.wallpaper_scheduler import ScheduleEntry
        import uuid
        from PySide6.QtWidgets import QTimeEdit
        from PySide6.QtCore import QTime
        if entry is None:
            entry = ScheduleEntry(id=uuid.uuid4().hex, setup_name="", time="08:00")
        row = QFrame()
        row.setObjectName("Card")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(10, 6, 10, 6)
        rl.setSpacing(8)
        chk = QCheckBox(tr("lbl_ie_wp_schedule_enabled"))
        chk.setChecked(entry.enabled)
        rl.addWidget(chk)
        setup_combo = QComboBox()
        from core import wallpaper_setups as _ws
        for n in _ws.list_names():
            setup_combo.addItem(n, n)
        if entry.setup_name:
            idx = setup_combo.findData(entry.setup_name)
            if idx >= 0:
                setup_combo.setCurrentIndex(idx)
            else:
                setup_combo.addItem(entry.setup_name, entry.setup_name)
                setup_combo.setCurrentIndex(setup_combo.count() - 1)
        setup_combo.setFixedWidth(180)
        rl.addWidget(setup_combo)
        time_edit = QTimeEdit()
        time_edit.setDisplayFormat("HH:mm")
        try:
            h, m = entry.time.split(":")
            time_edit.setTime(QTime(int(h), int(m)))
        except Exception:
            time_edit.setTime(QTime(8, 0))
        time_edit.setFixedWidth(80)
        rl.addWidget(time_edit)
        weekday_chks: list[QCheckBox] = []
        for i, lkey in enumerate(("wd_mon","wd_tue","wd_wed","wd_thu","wd_fri","wd_sat","wd_sun")):
            c = QCheckBox(tr(lkey))
            c.setChecked(i in (entry.weekdays or []))
            weekday_chks.append(c)
            rl.addWidget(c)
        rl.addStretch()
        rm_btn = QPushButton("✕")
        rm_btn.setObjectName("BrowseBtn")
        rm_btn.setFixedWidth(28)
        rl.addWidget(rm_btn)

        # Attach payload so saving knows what to read back.
        row._payload = (entry, chk, setup_combo, time_edit, weekday_chks)  # type: ignore[attr-defined]

        def _on_change(*_a):
            self._save_schedule_rows()
        chk.toggled.connect(_on_change)
        setup_combo.currentIndexChanged.connect(_on_change)
        time_edit.timeChanged.connect(_on_change)
        for c in weekday_chks:
            c.toggled.connect(_on_change)

        def _remove():
            self._schedule_rows.remove(row)
            self._schedule_rows_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
            self._save_schedule_rows()
        rm_btn.clicked.connect(_remove)

        self._schedule_rows.append(row)
        self._schedule_rows_layout.addWidget(row)
        self._save_schedule_rows()

    def _load_schedule_rows(self) -> None:
        from core import wallpaper_scheduler
        for e in wallpaper_scheduler.load_entries():
            self._add_schedule_row(e)

    def _save_schedule_rows(self) -> None:
        from core import wallpaper_scheduler
        from core.wallpaper_scheduler import ScheduleEntry
        entries: list[ScheduleEntry] = []
        for row in self._schedule_rows:
            entry, chk, combo, time_edit, weekday_chks = row._payload  # type: ignore[attr-defined]
            entry.enabled = chk.isChecked()
            entry.setup_name = combo.currentData() or combo.currentText()
            entry.time = time_edit.time().toString("HH:mm")
            entry.weekdays = [i for i, c in enumerate(weekday_chks) if c.isChecked()]
            entries.append(entry)
        wallpaper_scheduler.save_entries(entries)

    # ── Output / progress ────────────────────────────────────────────────────

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_out = _hdr(tr("hdr_output_folder"))
        layout.addWidget(self._hdr_out)
        row = QHBoxLayout()
        self._out_input = QLineEdit()
        self._out_input.setObjectName("PillInput")
        self._out_input.setPlaceholderText(tr("ph_each_source"))
        if getattr(self._settings, "output_folder", ""):
            self._out_input.setText(self._settings.output_folder)
        row.addWidget(self._out_input)
        self._out_browse_btn = QPushButton(tr("btn_browse"))
        self._out_browse_btn.setObjectName("BrowseBtn")
        self._out_browse_btn.setFixedWidth(90)
        self._out_browse_btn.clicked.connect(self._browse_out)
        row.addWidget(self._out_browse_btn)
        layout.addLayout(row)
        return card

    def _browse_out(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Select Output Folder",
            self._out_input.text() or os.path.expanduser("~"),
        )
        if d:
            self._out_input.setText(d)

    def _build_progress_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("TaskProgressBar")
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)
        self._progress_label = QLabel()
        self._progress_label.setObjectName("TextSecondary")
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)
        return card

    # ── Reset ────────────────────────────────────────────────────────────────

    # ── Undo / redo ──────────────────────────────────────────────────────────

    def _update_undo_buttons(self) -> None:
        self._undo_btn.setEnabled(len(self._undo_stack) > 1)
        self._redo_btn.setEnabled(bool(self._redo_stack))

    def _restore_config(self, cfg: EditConfig) -> None:
        """Push *cfg* into the controls without recording a new undo entry."""
        self._restoring = True
        try:
            self._apply_config(cfg)
            self._refresh_preview()
        finally:
            self._restoring = False
        self._update_undo_buttons()

    def _undo(self) -> None:
        # Undo applies to the global edit state, not per-monitor row overrides.
        if self._active_row is not None or len(self._undo_stack) <= 1:
            return
        self._redo_stack.append(self._undo_stack.pop())
        self._restore_config(self._undo_stack[-1])

    def _redo(self) -> None:
        if self._active_row is not None or not self._redo_stack:
            return
        cfg = self._redo_stack.pop()
        self._undo_stack.append(cfg)
        self._restore_config(cfg)

    def _reset_all(self) -> None:
        defaults = EditConfig()
        self._apply_config(defaults)
        self._aspect_combo.blockSignals(True)
        self._aspect_combo.setCurrentIndex(0)
        self._aspect_combo.blockSignals(False)
        self._schedule_preview()

    # ── Config gather / apply ────────────────────────────────────────────────

    def _collect_config(self) -> EditConfig:
        crop_top    = self._crop_sliders["top"][0].value() / 100.0
        crop_left   = self._crop_sliders["left"][0].value() / 100.0
        crop_bottom = self._crop_sliders["bottom"][0].value() / 100.0
        crop_right  = self._crop_sliders["right"][0].value() / 100.0

        fit = FitOptions(
            target_w=self._w_spin.value(),
            target_h=self._h_spin.value(),
            mode=self._fit_combo.currentData() or "cover",
            bg_color=self._bg_color,
            flip_h=self._flip_h_chk.isChecked(),
            flip_v=self._flip_v_chk.isChecked(),
            rotate_deg=float(self._rotate_spin.value()),
            crop_top=crop_top, crop_left=crop_left,
            crop_bottom=crop_bottom, crop_right=crop_right,
        )
        flt = FilterOptions(
            preset=self._filter_combo.currentData() or "none",
            strength=self._strength_slider.value() / 100.0,
        )
        adj = AdjustOptions(
            enabled=self._adjust_chk.isChecked(),
            brightness  = self._adj_sliders["brightness"][0].value() / 100.0,
            contrast    = self._adj_sliders["contrast"][0].value() / 100.0,
            saturation  = self._adj_sliders["saturation"][0].value() / 100.0,
            hue         = self._adj_sliders["hue"][0].value(),
            shadows     = self._adj_sliders["shadows"][0].value() / 100.0,
            highlights  = self._adj_sliders["highlights"][0].value() / 100.0,
            temperature = self._adj_sliders["temperature"][0].value(),
            tint        = self._adj_sliders["tint"][0].value(),
            black_point = self._adj_sliders["black_point"][0].value(),
            white_point = self._adj_sliders["white_point"][0].value(),
        )
        enh = EnhanceOptions(
            auto_enhance      = self._auto_enhance_chk.isChecked(),
            clarity           = self._enh_sliders["clarity"][0].value() / 100.0,
            dehaze            = self._enh_sliders["dehaze"][0].value() / 100.0,
            vibrance          = self._enh_sliders["vibrance"][0].value() / 100.0,
            exposure          = self._enh_sliders["exposure"][0].value() / 100.0,
            gamma             = self._enh_sliders["gamma"][0].value() / 100.0,
            denoise           = self._enh_sliders["denoise"][0].value() / 100.0,
            sharpen_amount    = self._enh_sliders["sharpen_amount"][0].value() / 100.0,
            sharpen_radius    = float(self._enh_sliders["sharpen_radius"][0].value()),
            sharpen_threshold = int(self._enh_sliders["sharpen_threshold"][0].value()),
        )
        eff = EffectsOptions(
            sharpen          = self._eff_sliders["sharpen"][0].value() / 100.0,
            blur             = self._eff_sliders["blur"][0].value() / 10.0,
            grain            = self._eff_sliders["grain"][0].value() / 100.0,
            vignette         = self._eff_sliders["vignette"][0].value() / 100.0,
            glass_blur       = self._eff_sliders["glass_blur"][0].value() / 100.0,
            duotone_amount   = self._eff_sliders["duotone"][0].value() / 100.0,
            duotone_dark     = self._eff_colors["duotone_dark"],
            duotone_light    = self._eff_colors["duotone_light"],
            gradient_amount  = self._eff_sliders["gradient"][0].value() / 100.0,
            gradient_color1  = self._eff_colors["gradient_c1"],
            gradient_color2  = self._eff_colors["gradient_c2"],
            gradient_angle   = int(self._grad_angle_spin.value()),
        )
        masks = [r.to_layer() for r in self._mask_rows]
        curves = CurvesOptions(
            enabled=self._curves_chk.isChecked(),
            points=self._curve_widget.points(),
        )
        return EditConfig(fit=fit, enhance=enh, filter=flt, adjust=adj,
                          curves=curves, effects=eff, masks=masks)

    def _apply_config(self, cfg: EditConfig) -> None:
        widgets = [
            self._fit_combo, self._w_spin, self._h_spin,
            self._flip_h_chk, self._flip_v_chk, self._rotate_spin,
            self._filter_combo, self._strength_slider, self._adjust_chk,
            self._grad_angle_spin, self._auto_enhance_chk, self._curves_chk,
        ] + [t[0] for t in self._adj_sliders.values()] \
          + [t[0] for t in self._eff_sliders.values()] \
          + [t[0] for t in self._enh_sliders.values()] \
          + [t[0] for t in self._crop_sliders.values()]
        for w in widgets:
            w.blockSignals(True)
        try:
            idx = self._fit_combo.findData(cfg.fit.mode)
            if idx >= 0:
                self._fit_combo.setCurrentIndex(idx)
            self._w_spin.setValue(cfg.fit.target_w)
            self._h_spin.setValue(cfg.fit.target_h)
            self._bg_color = cfg.fit.bg_color
            self._apply_bg_btn_color()
            self._flip_h_chk.setChecked(cfg.fit.flip_h)
            self._flip_v_chk.setChecked(cfg.fit.flip_v)
            self._rotate_spin.setValue(cfg.fit.rotate_deg)
            self._crop_sliders["top"][0].setValue(int(round(cfg.fit.crop_top * 100)))
            self._crop_sliders["left"][0].setValue(int(round(cfg.fit.crop_left * 100)))
            self._crop_sliders["bottom"][0].setValue(int(round(cfg.fit.crop_bottom * 100)))
            self._crop_sliders["right"][0].setValue(int(round(cfg.fit.crop_right * 100)))
            for key in ("top", "left", "bottom", "right"):
                sl = self._crop_sliders[key][0]
                # Force the visual label to refresh.
                sl.valueChanged.emit(sl.value())
            idx = self._filter_combo.findData(cfg.filter.preset)
            if idx >= 0:
                self._filter_combo.setCurrentIndex(idx)
            self._strength_slider.setValue(int(round(cfg.filter.strength * 100)))
            self._strength_val.setText(f"{self._strength_slider.value()}%")
            self._adjust_chk.setChecked(cfg.adjust.enabled)
            self._adj_sliders["brightness"][0].setValue(int(round(cfg.adjust.brightness * 100)))
            self._adj_sliders["contrast"][0].setValue(int(round(cfg.adjust.contrast * 100)))
            self._adj_sliders["saturation"][0].setValue(int(round(cfg.adjust.saturation * 100)))
            self._adj_sliders["hue"][0].setValue(int(cfg.adjust.hue))
            self._adj_sliders["shadows"][0].setValue(int(round(cfg.adjust.shadows * 100)))
            self._adj_sliders["highlights"][0].setValue(int(round(cfg.adjust.highlights * 100)))
            self._adj_sliders["temperature"][0].setValue(int(cfg.adjust.temperature))
            self._adj_sliders["tint"][0].setValue(int(cfg.adjust.tint))
            self._adj_sliders["black_point"][0].setValue(int(cfg.adjust.black_point))
            self._adj_sliders["white_point"][0].setValue(int(cfg.adjust.white_point))
            for key, (sl, lab, _lo, _hi) in self._adj_sliders.items():
                lab.setText(str(sl.value()))
            self._eff_sliders["sharpen"][0].setValue(int(round(cfg.effects.sharpen * 100)))
            self._eff_sliders["blur"][0].setValue(int(round(cfg.effects.blur * 10)))
            self._eff_sliders["grain"][0].setValue(int(round(cfg.effects.grain * 100)))
            self._eff_sliders["vignette"][0].setValue(int(round(cfg.effects.vignette * 100)))
            self._eff_sliders["glass_blur"][0].setValue(int(round(cfg.effects.glass_blur * 100)))
            self._eff_sliders["duotone"][0].setValue(int(round(cfg.effects.duotone_amount * 100)))
            self._eff_sliders["gradient"][0].setValue(int(round(cfg.effects.gradient_amount * 100)))
            self._grad_angle_spin.setValue(int(cfg.effects.gradient_angle))
            self._eff_colors["duotone_dark"]  = cfg.effects.duotone_dark
            self._eff_colors["duotone_light"] = cfg.effects.duotone_light
            self._eff_colors["gradient_c1"]   = cfg.effects.gradient_color1
            self._eff_colors["gradient_c2"]   = cfg.effects.gradient_color2
            for k, btn in self._eff_color_buttons.items():
                btn.setStyleSheet(f"background:{self._eff_colors[k]}; border:1px solid #555; border-radius:3px;")
            for key, (sl, lab) in self._eff_sliders.items():
                lab.setText(str(sl.value()))
            self._auto_enhance_chk.setChecked(cfg.enhance.auto_enhance)
            self._enh_sliders["clarity"][0].setValue(int(round(cfg.enhance.clarity * 100)))
            self._enh_sliders["dehaze"][0].setValue(int(round(cfg.enhance.dehaze * 100)))
            self._enh_sliders["vibrance"][0].setValue(int(round(cfg.enhance.vibrance * 100)))
            self._enh_sliders["exposure"][0].setValue(int(round(cfg.enhance.exposure * 100)))
            self._enh_sliders["gamma"][0].setValue(int(round(cfg.enhance.gamma * 100)))
            self._enh_sliders["denoise"][0].setValue(int(round(cfg.enhance.denoise * 100)))
            self._enh_sliders["sharpen_amount"][0].setValue(int(round(cfg.enhance.sharpen_amount * 100)))
            self._enh_sliders["sharpen_radius"][0].setValue(int(round(cfg.enhance.sharpen_radius)))
            self._enh_sliders["sharpen_threshold"][0].setValue(int(cfg.enhance.sharpen_threshold))
            for key, (sl, lab) in self._enh_sliders.items():
                lab.setText(str(sl.value()))
            self._curves_chk.setChecked(cfg.curves.enabled)
            self._curve_widget.set_points(cfg.curves.points)
            # Rebuild the stacked mask rows from the config.
            self._clear_mask_rows()
            for layer in cfg.masks:
                self._add_mask_row(layer)
        finally:
            for w in widgets:
                w.blockSignals(False)

    # ── Primary action ────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        batch_mode = self._mode_batch.isChecked()
        cfg = self._collect_config()
        out_dir = self._out_input.text().strip() or None

        if batch_mode:
            paths = [self._batch_list.item(i).text() for i in range(self._batch_list.count())]
            if not paths:
                self.status_message.emit(tr("ie_err_no_images"), True)
                return
            self._progress_bar.setRange(0, len(paths))
            self._progress_bar.setValue(0)
            self._set_busy(True, tr("ie_processing").format(n=len(paths)), f"0 / {len(paths)}")

            def _do():
                def _progress(done: int, total: int) -> None:
                    if self._worker is not None:
                        self._worker.signals.progress.emit(done, total, f"{done} / {total}")
                return process_batch(
                    paths, out_dir, cfg,
                    progress_cb=_progress,
                    cancel_cb=lambda: self._worker is not None and self._worker.is_cancelled,
                )
            self._worker = Worker(_do)
            self._worker.signals.progress.connect(self._on_progress)
            self._worker.signals.result.connect(self._on_batch_result)
            self._worker.signals.error.connect(self._on_error)
            self._worker.start()
            return

        if not self._src_path or not os.path.isfile(self._src_path):
            self.status_message.emit(tr("ie_err_no_image"), True)
            return
        in_path = self._src_path
        base = os.path.splitext(os.path.basename(in_path))[0]
        ext = os.path.splitext(in_path)[1] or ".png"
        tgt_dir = out_dir or os.path.dirname(in_path) or "."
        out_path = os.path.join(tgt_dir, f"{base}_edited{ext}")

        self._progress_bar.setRange(0, 0)
        self._set_busy(True, tr("ie_processing_one"), "")

        def _do_single():
            return process_image(in_path, out_path, cfg)
        self._worker = Worker(_do_single)
        self._worker.signals.result.connect(self._on_single_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, done: int, total: int, msg: str) -> None:
        if self._progress_bar.maximum() > 0:
            self._progress_bar.setValue(done)
        self._progress_label.setText(msg)

    def _set_busy(self, busy: bool, status_msg: str = "", progress_msg: str = "") -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if busy:
            self._progress_label.setText(progress_msg)
            if status_msg:
                self.status_message.emit(status_msg, False)
        self.busy_changed.emit(busy)

    def _on_single_result(self, out_path: str) -> None:
        self._set_busy(False)
        self._worker = None
        self._last_result_path = out_path
        get_history_manager().add_item(HistoryItem(
            task_type="image_editor",
            file_name=os.path.basename(out_path),
            file_path=out_path,
            status="success",
        ))
        self.status_message.emit(tr("ie_done_one").format(path=out_path), False)

    def _on_batch_result(self, results: dict) -> None:
        self._set_busy(False)
        self._worker = None
        ok = sum(1 for v in results.values() if v)
        fail = len(results) - ok
        for path, success in results.items():
            base = os.path.splitext(os.path.basename(path))[0]
            ext = os.path.splitext(path)[1]
            out_name = f"{base}_edited{ext}"
            out_dir = self._out_input.text().strip() or os.path.dirname(path) or "."
            full = os.path.join(out_dir, out_name)
            if success:
                self._last_result_path = full
            get_history_manager().add_item(HistoryItem(
                task_type="image_editor",
                file_name=out_name,
                file_path=full,
                status="success" if success else "error",
            ))
        if fail == 0:
            self.status_message.emit(tr("ie_done_batch").format(n=ok), False)
        else:
            self.status_message.emit(
                tr("ie_done_batch_partial").format(ok=ok, fail=fail),
                fail == len(results),
            )

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)

    def populate_files(self, paths: list[str]) -> None:
        if not paths:
            return
        if len(paths) == 1 and not self._mode_batch.isChecked():
            self._single_input.setText(paths[0])
            self._load_source(paths[0])
        else:
            self._mode_batch.setChecked(True)
            self._batch_add(paths)

    # ── i18n ──────────────────────────────────────────────────────────────────

    def retranslate_ui(self) -> None:
        self._hdr_input.setText(tr("hdr_ie_input"))
        self._mode_batch.setText(tr("lbl_ie_batch_mode"))
        self._single_input.setPlaceholderText(tr("ph_ie_select_image"))
        self._single_browse_btn.setText(tr("btn_browse"))
        self._batch_add_btn.setText(tr("btn_add_files"))
        self._batch_dir_btn.setText(tr("btn_add_folder"))
        self._batch_clear_btn.setText(tr("btn_clear_all"))
        self._hdr_preview.setText(tr("hdr_ie_preview"))
        self._compare_btn.setText(tr("btn_ie_compare"))
        self._compare_btn.setToolTip(tr("tip_ie_compare"))
        self._undo_btn.setToolTip(tr("tip_ie_undo"))
        self._redo_btn.setToolTip(tr("tip_ie_redo"))
        self._reset_btn.setText(tr("btn_ie_reset"))
        if not self._src_image:
            self._preview_label.setText(tr("hint_ie_no_preview"))
        self._hdr_canvas.setText(tr("hdr_ie_canvas"))
        self._lbl_aspect.setText(tr("lbl_ie_aspect"))
        for i in range(self._aspect_combo.count()):
            data = self._aspect_combo.itemData(i)
            if data:
                key = data[0]
                self._aspect_combo.setItemText(i, tr(f"ie_aspect_{key}"))
        self._swap_btn.setText(tr("btn_ie_swap_wh"))
        self._swap_btn.setToolTip(tr("tip_ie_swap_wh"))
        self._lbl_fit.setText(tr("lbl_ie_fit"))
        for i in range(self._fit_combo.count()):
            data = self._fit_combo.itemData(i)
            if data:
                self._fit_combo.setItemText(i, tr(f"ie_fit_{data}"))
        self._lbl_w.setText(tr("lbl_ie_width"))
        self._lbl_h.setText(tr("lbl_ie_height"))
        self._lbl_bg.setText(tr("lbl_ie_bg_color"))
        self._flip_h_chk.setText(tr("lbl_ie_flip_h"))
        self._flip_v_chk.setText(tr("lbl_ie_flip_v"))
        self._hdr_crop.setText(tr("hdr_ie_crop_rotate"))
        self._lbl_rotate.setText(tr("lbl_ie_rotate"))
        for key, (_sl, lbl) in self._crop_sliders.items():
            lbl.setText(tr(f"lbl_ie_crop_{key}"))
        self._hdr_filter.setText(tr("hdr_ie_filter"))
        self._lbl_filter.setText(tr("lbl_ie_filter"))
        for i in range(self._filter_combo.count()):
            data = self._filter_combo.itemData(i)
            if data:
                self._filter_combo.setItemText(i, tr(f"ie_filter_{data}"))
        self._lbl_strength.setText(tr("lbl_ie_strength"))
        self._hdr_adjust.setText(tr("hdr_ie_adjust"))
        self._adjust_chk.setText(tr("lbl_ie_enable_adjust"))
        for key, lbl in self._adj_labels.items():
            lbl.setText(tr(f"lbl_ie_{key}"))
        self._hdr_curves.setText(tr("hdr_ie_curves"))
        self._curves_chk.setText(tr("lbl_ie_enable_curves"))
        self._curve_reset_btn.setText(tr("btn_ie_curve_reset"))
        self._hdr_enhance.setText(tr("hdr_ie_enhance"))
        self._enh_hint.setText(tr("hint_ie_enhance"))
        self._auto_enhance_chk.setText(tr("lbl_ie_auto_enhance"))
        self._auto_enhance_chk.setToolTip(tr("tip_ie_auto_enhance"))
        for key, lbl in self._enh_labels.items():
            lbl.setText(tr(f"lbl_ie_{key}"))
        self._hdr_effects.setText(tr("hdr_ie_effects"))
        for key, lbl in self._eff_labels.items():
            lbl.setText(tr(f"lbl_ie_{key}"))
        self._hdr_masks.setText(tr("hdr_ie_masks"))
        self._masks_hint.setText(tr("hint_ie_masks"))
        self._mask_add_btn.setText(tr("btn_ie_mask_add"))
        self._show_masks_chk.setText(tr("lbl_ie_show_masks"))
        self._show_masks_chk.setToolTip(tr("tip_ie_show_masks"))
        for mrow in self._mask_rows:
            mrow.retranslate_ui()
        self._renumber_masks()
        self._hdr_preset.setText(tr("hdr_ie_presets"))
        self._load_preset_btn.setText(tr("btn_ie_load_preset"))
        self._save_preset_btn.setText(tr("btn_ie_save_preset"))
        self._del_preset_btn.setText(tr("btn_ie_delete_preset"))
        self._hdr_wp.setText(tr("hdr_ie_wallpaper"))
        self._wp_hint.setText(tr("hint_ie_wallpaper"))
        self._wp_detect_btn.setText(tr("btn_ie_wp_detect"))
        self._wp_add_btn.setText(tr("btn_ie_wp_add_monitor"))
        self._wp_lbl_name.setText(tr("lbl_ie_wp_base_name"))
        self._wp_name_edit.setPlaceholderText(tr("ph_ie_wp_base_name"))
        self._wp_export_per_btn.setText(tr("btn_ie_wp_export_per_monitor"))
        self._wp_export_span_btn.setText(tr("btn_ie_wp_export_spanned"))
        self._wp_apply_btn.setText(tr("btn_ie_wp_apply_now"))
        self._wp_apply_btn.setToolTip(tr("tip_ie_wp_apply_now"))
        self._wp_open_settings_btn.setText(tr("btn_ie_wp_open_settings"))
        for row in self._wp_rows:
            row.retranslate_ui()
        self._stop_edit_btn.setText(tr("btn_ie_wp_stop_editing"))
        if self._active_row is not None:
            self._active_banner_lbl.setText(
                tr("ie_wp_editing_row").format(
                    label=self._active_row.label_edit.text() or "Monitor"
                )
            )
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._out_input.setPlaceholderText(tr("ph_each_source"))
        self._out_browse_btn.setText(tr("btn_browse"))
