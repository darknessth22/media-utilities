"""Pixel Art — turn a photo, GIF or video into pixel art.

Every slider updates a before/after preview straight away. The preview runs
on a reduced copy of one frame with the pixel size scaled to match, so it
looks like the final result while staying fast enough to follow a dragged
slider. The real export runs in the background.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSlider, QVBoxLayout,
    QWidget,
)

from core import pixel_art
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from core.i18n import tr
from gui.worker import Worker

_PREVIEW_MAX = 720          # longest side of the preview copy, px
_PALETTE_KEYS = [pixel_art.AUTO] + list(pixel_art.PALETTES)
_DITHER_KEYS = [pixel_art.DITHER_NONE, pixel_art.DITHER_ORDERED, pixel_art.DITHER_FLOYD]


def _card() -> QFrame:
    f = QFrame()
    f.setObjectName("Card")
    return f


def _section_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("TextSecondary")
    lbl.setStyleSheet("font-size: 11px; font-weight: bold; letter-spacing: 1px; margin-bottom: 2px;")
    return lbl


def _to_qpixmap(img) -> QPixmap:
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, img.width * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())      # copy: `data` dies with this frame


class _Preview(QLabel):
    """Shows one image scaled to fit, keeping hard pixel edges when asked."""

    def __init__(self, crisp: bool, parent=None) -> None:
        super().__init__(parent)
        self._crisp = crisp
        self._pixmap: QPixmap | None = None
        self.setMinimumSize(240, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setObjectName("TextMuted")

    def set_image(self, pixmap: QPixmap | None) -> None:
        self._pixmap = pixmap
        self.setText("" if pixmap else tr("pa_preview_empty"))
        self.update()

    def paintEvent(self, event) -> None:
        if self._pixmap is None:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        # Checkerboard under the image so transparent sprites read as such.
        size = 10
        for y in range(0, self.height(), size):
            for x in range(0, self.width(), size):
                dark = (x // size + y // size) % 2
                painter.fillRect(x, y, size, size, QColor(60, 60, 66) if dark else QColor(80, 80, 88))
        # Scaling the "after" image smoothly would blur the very pixels the
        # tool exists to make, so that side uses nearest-neighbour.
        mode = (Qt.TransformationMode.FastTransformation if self._crisp
                else Qt.TransformationMode.SmoothTransformation)
        scaled = self._pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, mode)
        painter.drawPixmap((self.width() - scaled.width()) // 2,
                           (self.height() - scaled.height()) // 2, scaled)
        painter.end()


class _Swatches(QWidget):
    """The palette in use, as a row of colour chips."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._colours: list[str] = []
        self.setFixedHeight(22)

    def set_colours(self, colours: list[str]) -> None:
        self._colours = colours
        self.setToolTip("  ".join(colours))
        self.update()

    def paintEvent(self, _event) -> None:
        if not self._colours:
            return
        painter = QPainter(self)
        chip = max(6, min(22, self.width() // max(1, len(self._colours))))
        for i, code in enumerate(self._colours):
            painter.fillRect(i * chip, 0, chip - 2, 20, QColor(code))
        painter.end()


class PixelArtSection(QScrollArea):
    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._path: str | None = None
        self._source = None             # PIL image of the preview frame
        self._preview_scale = 1.0
        self._worker: Worker | None = None
        self._cancelled = False

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAcceptDrops(True)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._build_source_card())
        layout.addWidget(self._build_preview_card())
        layout.addWidget(self._build_controls_card())
        layout.addWidget(self._build_progress_card())
        self.setWidget(content)

        # Debounce: dragging a slider fires dozens of changes a second.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(90)
        self._refresh_timer.timeout.connect(self._render_preview)
        self._sync_enabled()

    # ── Cards ────────────────────────────────────────────────────────────────

    def _build_source_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_source = _section_header(tr("pa_hdr_source"))
        layout.addWidget(self._hdr_source)
        self._hint_source = QLabel(tr("pa_hint_source"))
        self._hint_source.setObjectName("TextMuted")
        self._hint_source.setWordWrap(True)
        self._hint_source.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint_source)
        row = QHBoxLayout()
        self._file_label = QLabel(tr("pa_no_file"))
        self._file_label.setObjectName("TextSecondary")
        row.addWidget(self._file_label, 1)
        self._browse_btn = QPushButton(tr("btn_browse"))
        self._browse_btn.setObjectName("BrowseBtn")
        self._browse_btn.clicked.connect(self._browse)
        row.addWidget(self._browse_btn)
        layout.addLayout(row)
        return card

    def _build_preview_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        self._hdr_preview = _section_header(tr("pa_hdr_preview"))
        layout.addWidget(self._hdr_preview)
        grid = QGridLayout()
        grid.setSpacing(10)
        self._lbl_before = QLabel(tr("pa_before"))
        self._lbl_after = QLabel(tr("pa_after"))
        for lbl in (self._lbl_before, self._lbl_after):
            lbl.setObjectName("TextMuted")
            lbl.setStyleSheet("font-size: 11px;")
        self._before = _Preview(crisp=False)
        self._after = _Preview(crisp=True)
        self._before.set_image(None)
        self._after.set_image(None)
        grid.addWidget(self._lbl_before, 0, 0)
        grid.addWidget(self._lbl_after, 0, 1)
        grid.addWidget(self._before, 1, 0)
        grid.addWidget(self._after, 1, 1)
        grid.setRowMinimumHeight(1, 300)
        layout.addLayout(grid)
        self._swatches = _Swatches()
        layout.addWidget(self._swatches)
        return card

    def _slider(self, lo: int, hi: int, value: int) -> QSlider:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(value)
        s.valueChanged.connect(self._schedule_preview)
        return s

    def _build_controls_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_style = _section_header(tr("pa_hdr_style"))
        layout.addWidget(self._hdr_style)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        defaults = pixel_art.PixelSettings()

        self._lbl_pixel = QLabel()
        self._pixel = self._slider(2, 32, defaults.pixel_size)
        self._lbl_palette = QLabel()
        self._palette = QComboBox()
        self._palette.currentIndexChanged.connect(self._on_palette_changed)
        self._lbl_colours = QLabel()
        self._colours = self._slider(2, 64, defaults.colors)
        self._lbl_dither = QLabel()
        self._dither = QComboBox()
        self._dither.currentIndexChanged.connect(self._schedule_preview)
        self._lbl_contrast = QLabel()
        self._contrast = self._slider(50, 200, int(defaults.contrast * 100))
        self._lbl_saturation = QLabel()
        self._saturation = self._slider(0, 200, int(defaults.saturation * 100))
        self._upscale = QCheckBox()
        self._upscale.setChecked(defaults.upscale)
        self._upscale.toggled.connect(self._schedule_preview)

        rows = [(self._lbl_pixel, self._pixel), (self._lbl_palette, self._palette),
                (self._lbl_colours, self._colours), (self._lbl_dither, self._dither),
                (self._lbl_contrast, self._contrast), (self._lbl_saturation, self._saturation)]
        for r, (lbl, widget) in enumerate(rows):
            grid.addWidget(lbl, r, 0)
            grid.addWidget(widget, r, 1)
        grid.addWidget(self._upscale, len(rows), 0, 1, 2)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        self._reset_btn = QPushButton(tr("pa_reset"))
        self._reset_btn.setObjectName("BrowseBtn")
        self._reset_btn.clicked.connect(self._reset)
        layout.addWidget(self._reset_btn, 0, Qt.AlignmentFlag.AlignLeft)

        self._fill_combos()
        self._update_value_labels()
        return card

    def _build_progress_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)
        self._result = QLabel("")
        self._result.setObjectName("TextMuted")
        self._result.setWordWrap(True)
        self._result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._result)
        self._open_btn = QPushButton(tr("pa_open_folder"))
        self._open_btn.setObjectName("BrowseBtn")
        self._open_btn.setVisible(False)
        self._open_btn.clicked.connect(self._open_folder)
        layout.addWidget(self._open_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self._last_output: str | None = None
        return card

    def _fill_combos(self) -> None:
        for combo, keys, prefix in ((self._palette, _PALETTE_KEYS, "pa_palette_"),
                                    (self._dither, _DITHER_KEYS, "pa_dither_")):
            current = combo.currentIndex()
            combo.blockSignals(True)
            combo.clear()
            for key in keys:
                combo.addItem(tr(prefix + key), key)
            combo.setCurrentIndex(max(0, current))
            combo.blockSignals(False)

    # ── Settings ─────────────────────────────────────────────────────────────

    def _settings_from_ui(self, scale: float = 1.0) -> pixel_art.PixelSettings:
        return pixel_art.PixelSettings(
            pixel_size=max(1, round(self._pixel.value() * scale)),
            palette=self._palette.currentData() or pixel_art.AUTO,
            colors=self._colours.value(),
            dither=self._dither.currentData() or pixel_art.DITHER_NONE,
            contrast=self._contrast.value() / 100,
            saturation=self._saturation.value() / 100,
            upscale=self._upscale.isChecked(),
        )

    def _update_value_labels(self) -> None:
        self._lbl_pixel.setText(tr("pa_pixel_size").format(n=self._pixel.value()))
        self._lbl_palette.setText(tr("pa_palette"))
        self._lbl_colours.setText(tr("pa_colours").format(n=self._colours.value()))
        self._lbl_dither.setText(tr("pa_dither"))
        self._lbl_contrast.setText(tr("pa_contrast").format(n=self._contrast.value()))
        self._lbl_saturation.setText(tr("pa_saturation").format(n=self._saturation.value()))
        self._upscale.setText(tr("pa_upscale"))

    def _on_palette_changed(self) -> None:
        self._sync_enabled()
        self._schedule_preview()

    def _sync_enabled(self) -> None:
        # The colour count only means something for the automatic palette;
        # a preset has a fixed number of colours.
        auto = (self._palette.currentData() or pixel_art.AUTO) == pixel_art.AUTO
        self._colours.setEnabled(auto)
        self._lbl_colours.setEnabled(auto)

    def _reset(self) -> None:
        d = pixel_art.PixelSettings()
        for widget, value in ((self._pixel, d.pixel_size), (self._colours, d.colors),
                              (self._contrast, int(d.contrast * 100)),
                              (self._saturation, int(d.saturation * 100))):
            widget.setValue(value)
        self._palette.setCurrentIndex(0)
        self._dither.setCurrentIndex(0)
        self._upscale.setChecked(d.upscale)

    # ── Source ───────────────────────────────────────────────────────────────

    def _browse(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(pixel_art.ALL_EXTS))
        path, _ = QFileDialog.getOpenFileName(self, tr("pa_hdr_source"), "",
                                              f"{tr('pa_filter')} ({exts})")
        if path:
            self.load(path)

    def load(self, path: str) -> None:
        if os.path.splitext(path)[1].lower() not in pixel_art.ALL_EXTS:
            self.status_message.emit(tr("pa_unsupported"), True)
            return
        try:
            frame = pixel_art.preview_frame(path)
        except Exception as exc:                # noqa: BLE001 - shown to user
            self.status_message.emit(tr("pa_cannot_open").format(error=exc), True)
            return
        self._path = path
        self._file_label.setText(os.path.basename(path))
        self._file_label.setToolTip(path)
        # Work on a reduced copy: the preview must keep up with a dragged
        # slider, and a 4K frame cannot.
        scale = min(1.0, _PREVIEW_MAX / max(frame.width, frame.height))
        if scale < 1.0:
            frame = frame.resize((max(1, int(frame.width * scale)),
                                  max(1, int(frame.height * scale))))
        self._source = frame
        self._preview_scale = scale
        self._before.set_image(_to_qpixmap(frame))
        self._result.setText("")
        self._open_btn.setVisible(False)
        self._render_preview()

    def populate_files(self, paths: list[str]) -> None:
        if paths:
            self.load(paths[0])

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.load(paths[0])
            event.acceptProposedAction()

    # ── Preview ──────────────────────────────────────────────────────────────

    def _schedule_preview(self, *_args) -> None:
        self._update_value_labels()
        self._refresh_timer.start()

    def _render_preview(self) -> None:
        if self._source is None:
            return
        # Same look as the export: the pixel size shrinks with the preview copy.
        settings = self._settings_from_ui(self._preview_scale)
        palette = pixel_art.build_palette([self._source], settings)
        art = pixel_art.pixelate(self._source, settings, palette)
        self._after.set_image(_to_qpixmap(art))
        self._swatches.set_colours(palette)

    # ── Export ───────────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._cancelled = True
            return
        if not self._path:
            self.status_message.emit(tr("pa_pick_first"), True)
            return
        path, settings = self._path, self._settings_from_ui()
        self._cancelled = False
        self._progress.setRange(0, 0)
        self._progress.setVisible(True)
        self._result.setText(tr("pa_working"))
        self._open_btn.setVisible(False)
        self.busy_changed.emit(True)

        def run(worker=None):
            def progress(done, total):
                self._worker.signals.progress.emit(done, total, "")
            return pixel_art.convert(path, settings, progress=progress,
                                     cancel=lambda: self._cancelled)

        self._worker = Worker(run)
        self._worker.signals.progress.connect(self._on_progress)
        self._worker.signals.result.connect(self._on_done)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, done: int, total: int, _msg: str) -> None:
        self._progress.setRange(0, max(1, total))
        self._progress.setValue(done)

    def _finish(self) -> None:
        self._progress.setVisible(False)
        self._worker = None
        self.busy_changed.emit(False)

    def _on_done(self, output: str) -> None:
        self._finish()
        self._last_output = output
        self._result.setText(tr("pa_saved").format(path=output))
        self._open_btn.setVisible(True)
        self.status_message.emit(tr("pa_saved").format(path=os.path.basename(output)), False)
        get_history_manager().add_item(HistoryItem(
            task_type="pixel_art", file_name=os.path.basename(output),
            file_path=output, status="success"))

    def _on_error(self, err: tuple) -> None:
        self._finish()
        _cls, msg, _tb = err
        if self._cancelled:
            self._result.setText(tr("pa_cancelled"))
            self.status_message.emit(tr("pa_cancelled"), False)
            return
        self._result.setText(tr("pa_failed").format(error=msg))
        self.status_message.emit(tr("pa_failed").format(error=msg), True)

    def _open_folder(self) -> None:
        if not self._last_output:
            return
        import subprocess
        import sys
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(self._last_output)])
        else:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self._last_output)))

    # ── Localisation ─────────────────────────────────────────────────────────

    def retranslate_ui(self) -> None:
        self._hdr_source.setText(tr("pa_hdr_source"))
        self._hint_source.setText(tr("pa_hint_source"))
        if not self._path:
            self._file_label.setText(tr("pa_no_file"))
        self._browse_btn.setText(tr("btn_browse"))
        self._hdr_preview.setText(tr("pa_hdr_preview"))
        self._lbl_before.setText(tr("pa_before"))
        self._lbl_after.setText(tr("pa_after"))
        self._hdr_style.setText(tr("pa_hdr_style"))
        self._reset_btn.setText(tr("pa_reset"))
        self._open_btn.setText(tr("pa_open_folder"))
        self._fill_combos()
        self._update_value_labels()
        if self._source is None:
            self._before.set_image(None)
            self._after.set_image(None)
