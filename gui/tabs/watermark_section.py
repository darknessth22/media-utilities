"""Batch Watermarking tab — logo overlay or text burn across entire directories."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.watermarker import watermark_batch, _VIDEO_EXTS, _IMAGE_EXTS, _ALL_EXTS, PRESET_OPTIONS
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


_POSITIONS = ["top-left", "top-right", "bottom-left", "bottom-right", "center"]
_COLORS = ["white", "black", "yellow", "red", "cyan", "lime"]


class WatermarkSection(QScrollArea):
    """Stamp a logo or text watermark onto a batch of video files."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_result_path: str | None = None
        self._available_hw = detect_hw_encoders()

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_files_card())
        layout.addWidget(self._build_mode_card())
        layout.addWidget(self._build_logo_card())
        layout.addWidget(self._build_text_card())
        layout.addWidget(self._build_encode_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

        self.setWidget(content)

        # Show correct options panel on init
        self._on_mode_changed(True)

    # ── Files card ────────────────────────────────────────────────────────────

    def _build_files_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("VIDEO / IMAGE FILES"))

        self._file_list = QListWidget()
        self._file_list.setObjectName("FileList")
        self._file_list.setFixedHeight(180)
        self._file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self._file_list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        add_btn = QPushButton("Add Files…")
        add_btn.setObjectName("BrowseBtn")
        add_btn.clicked.connect(self._browse_add_files)
        btn_row.addWidget(add_btn)

        add_dir_btn = QPushButton("Add Folder…")
        add_dir_btn.setObjectName("BrowseBtn")
        add_dir_btn.clicked.connect(self._browse_add_folder)
        btn_row.addWidget(add_dir_btn)

        remove_btn = QPushButton("Remove Selected")
        remove_btn.setObjectName("BrowseBtn")
        remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(remove_btn)

        clear_btn = QPushButton("Clear All")
        clear_btn.setObjectName("BrowseBtn")
        clear_btn.clicked.connect(self._file_list.clear)
        btn_row.addWidget(clear_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._count_label = QLabel("0 files queued")
        self._count_label.setObjectName("TextMuted")
        self._count_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._count_label)

        self._file_list.model().rowsInserted.connect(self._update_count)
        self._file_list.model().rowsRemoved.connect(self._update_count)
        return card

    # ── Mode card ─────────────────────────────────────────────────────────────

    def _build_mode_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("WATERMARK TYPE"))

        self._mode_group = QButtonGroup(self)
        self._radio_logo = QRadioButton("Logo / image overlay")
        self._radio_text = QRadioButton("Text watermark")
        self._radio_logo.setChecked(True)
        self._mode_group.addButton(self._radio_logo, 0)
        self._mode_group.addButton(self._radio_text, 1)
        self._radio_logo.toggled.connect(self._on_mode_changed)

        row = QHBoxLayout()
        row.setSpacing(24)
        row.addWidget(self._radio_logo)
        row.addWidget(self._radio_text)
        row.addStretch()
        layout.addLayout(row)
        return card

    def _on_mode_changed(self, logo_checked: bool) -> None:
        if hasattr(self, "_logo_card"):
            self._logo_card.setVisible(logo_checked)
        if hasattr(self, "_text_card"):
            self._text_card.setVisible(not logo_checked)

    # ── Logo options card ─────────────────────────────────────────────────────

    def _build_logo_card(self) -> QFrame:
        self._logo_card = _card()
        layout = QVBoxLayout(self._logo_card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(_section_header("LOGO OPTIONS"))

        # Logo file
        layout.addWidget(QLabel("Logo image (PNG with transparency recommended)"))
        logo_row = QHBoxLayout()
        self._logo_input = QLineEdit()
        self._logo_input.setObjectName("PillInput")
        self._logo_input.setPlaceholderText("Path to logo file…")
        logo_row.addWidget(self._logo_input)
        logo_browse = QPushButton("Browse…")
        logo_browse.setObjectName("BrowseBtn")
        logo_browse.setFixedWidth(90)
        logo_browse.clicked.connect(self._browse_logo)
        logo_row.addWidget(logo_browse)
        layout.addLayout(logo_row)

        # Position + scale + opacity row
        opts_row = QHBoxLayout()
        opts_row.setSpacing(16)

        pos_col = QVBoxLayout()
        pos_col.addWidget(QLabel("Position"))
        self._logo_pos = QComboBox()
        self._logo_pos.addItems(_POSITIONS)
        self._logo_pos.setCurrentText("bottom-right")
        self._logo_pos.setFixedWidth(150)
        pos_col.addWidget(self._logo_pos)
        opts_row.addLayout(pos_col)

        scale_col = QVBoxLayout()
        scale_col.addWidget(QLabel("Scale (% of video width)"))
        self._logo_scale = QSpinBox()
        self._logo_scale.setRange(1, 100)
        self._logo_scale.setValue(15)
        self._logo_scale.setSuffix("%")
        self._logo_scale.setFixedWidth(90)
        scale_col.addWidget(self._logo_scale)
        opts_row.addLayout(scale_col)

        alpha_col = QVBoxLayout()
        alpha_col.addWidget(QLabel("Opacity (%)"))
        self._logo_opacity = QSpinBox()
        self._logo_opacity.setRange(1, 100)
        self._logo_opacity.setValue(80)
        self._logo_opacity.setSuffix("%")
        self._logo_opacity.setFixedWidth(90)
        alpha_col.addWidget(self._logo_opacity)
        opts_row.addLayout(alpha_col)

        opts_row.addStretch()
        layout.addLayout(opts_row)
        return self._logo_card

    # ── Text options card ─────────────────────────────────────────────────────

    def _build_text_card(self) -> QFrame:
        self._text_card = _card()
        layout = QVBoxLayout(self._text_card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(_section_header("TEXT OPTIONS"))

        layout.addWidget(QLabel("Watermark text"))
        self._wm_text = QLineEdit()
        self._wm_text.setObjectName("PillInput")
        self._wm_text.setPlaceholderText("© Your Name 2025")
        layout.addWidget(self._wm_text)

        opts_row = QHBoxLayout()
        opts_row.setSpacing(16)

        pos_col = QVBoxLayout()
        pos_col.addWidget(QLabel("Position"))
        self._text_pos = QComboBox()
        self._text_pos.addItems(_POSITIONS)
        self._text_pos.setCurrentText("bottom-right")
        self._text_pos.setFixedWidth(150)
        pos_col.addWidget(self._text_pos)
        opts_row.addLayout(pos_col)

        size_col = QVBoxLayout()
        size_col.addWidget(QLabel("Font size"))
        self._font_size = QSpinBox()
        self._font_size.setRange(8, 256)
        self._font_size.setValue(36)
        self._font_size.setFixedWidth(90)
        size_col.addWidget(self._font_size)
        opts_row.addLayout(size_col)

        color_col = QVBoxLayout()
        color_col.addWidget(QLabel("Font color"))
        self._font_color = QComboBox()
        self._font_color.addItems(_COLORS)
        self._font_color.setCurrentText("white")
        self._font_color.setFixedWidth(100)
        color_col.addWidget(self._font_color)
        opts_row.addLayout(color_col)

        alpha_col = QVBoxLayout()
        alpha_col.addWidget(QLabel("Opacity (%)"))
        self._text_opacity = QSpinBox()
        self._text_opacity.setRange(1, 100)
        self._text_opacity.setValue(80)
        self._text_opacity.setSuffix("%")
        self._text_opacity.setFixedWidth(90)
        alpha_col.addWidget(self._text_opacity)
        opts_row.addLayout(alpha_col)

        opts_row.addStretch()
        layout.addLayout(opts_row)
        return self._text_card

    # ── Encode settings card ──────────────────────────────────────────────────

    _PRESET_OPTIONS = PRESET_OPTIONS

    def _build_encode_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(_section_header("VIDEO ENCODE SETTINGS"))

        row = QHBoxLayout()
        row.setSpacing(16)

        crf_col = QVBoxLayout()
        crf_col.addWidget(QLabel("Quality (CRF / QP)"))
        self._enc_crf = QSpinBox()
        self._enc_crf.setRange(1, 51)
        self._enc_crf.setValue(18)
        self._enc_crf.setFixedWidth(70)
        crf_col.addWidget(self._enc_crf)
        row.addLayout(crf_col)

        preset_col = QVBoxLayout()
        self._enc_preset_hint = QLabel("Slower = smaller file at same quality")
        self._enc_preset_hint.setObjectName("TextMuted")
        self._enc_preset_hint.setStyleSheet("font-size: 11px;")
        preset_col.addWidget(self._enc_preset_hint)
        self._enc_preset = QComboBox()
        self._enc_preset.setFixedWidth(130)
        preset_col.addWidget(self._enc_preset)
        row.addLayout(preset_col)

        hw_col = QVBoxLayout()
        hw_col.addWidget(QLabel("Hardware Acceleration"))
        self._enc_hw = QComboBox()
        self._enc_hw.setFixedWidth(160)
        self._enc_hw.addItem("CPU (libx264)", "none")
        if "nvidia" in self._available_hw:
            self._enc_hw.addItem("NVIDIA (NVENC)", "nvidia")
        if "amd" in self._available_hw:
            self._enc_hw.addItem("AMD (AMF)", "amd")
        if "intel" in self._available_hw:
            self._enc_hw.addItem("Intel (QuickSync)", "intel")
        self._enc_hw.currentIndexChanged.connect(self._on_enc_hw_changed)
        hw_col.addWidget(self._enc_hw)
        row.addLayout(hw_col)

        row.addStretch()
        layout.addLayout(row)

        self._on_enc_hw_changed(0)
        return card

    def _on_enc_hw_changed(self, _idx: int) -> None:
        hw = self._enc_hw.currentData()
        presets, default = self._PRESET_OPTIONS.get(hw, self._PRESET_OPTIONS["none"])
        hints = {
            "none":   "Slower = smaller file at same quality",
            "nvidia": "p1 = fastest · p7 = best quality",
            "amd":    "Tradeoff between encode speed and compression",
            "intel":  "Slower = smaller file at same quality",
        }
        self._enc_preset.blockSignals(True)
        self._enc_preset.clear()
        self._enc_preset.addItems(presets)
        self._enc_preset.setCurrentText(default)
        self._enc_preset.blockSignals(False)
        self._enc_preset_hint.setText(hints.get(hw, ""))

    # ── Output card ───────────────────────────────────────────────────────────

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("OUTPUT FOLDER"))

        hint = QLabel("Watermarked files saved with _watermarked suffix. Leave blank to save alongside originals.")
        hint.setObjectName("TextMuted")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(hint)

        row = QHBoxLayout()
        self._out_input = QLineEdit()
        self._out_input.setObjectName("PillInput")
        self._out_input.setPlaceholderText("Same directory as each source file")
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

    # ── Progress card ─────────────────────────────────────────────────────────

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

    # ── File management ───────────────────────────────────────────────────────

    def _browse_add_files(self) -> None:
        ext_filter = "Media files (" + " ".join(f"*{e}" for e in sorted(_ALL_EXTS)) + ")"
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Video / Image Files", os.path.expanduser("~"), ext_filter
        )
        self._add_paths(paths)

    def _browse_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder", os.path.expanduser("~")
        )
        if not folder:
            return
        paths = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if os.path.splitext(f)[1].lower() in _ALL_EXTS
        ]
        self._add_paths(sorted(paths))

    def _add_paths(self, paths: list[str]) -> None:
        existing = {self._file_list.item(i).text() for i in range(self._file_list.count())}
        for p in paths:
            if p not in existing:
                self._file_list.addItem(QListWidgetItem(p))

    def _remove_selected(self) -> None:
        for item in self._file_list.selectedItems():
            self._file_list.takeItem(self._file_list.row(item))

    def _update_count(self) -> None:
        n = self._file_list.count()
        self._count_label.setText(f"{n} file{'s' if n != 1 else ''} queued")

    def _browse_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Logo Image", os.path.expanduser("~"),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if path:
            self._logo_input.setText(path)

    def _browse_output(self) -> None:
        start = self._out_input.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if d:
            self._out_input.setText(d)

    def populate_files(self, paths: list[str]) -> None:
        self._add_paths(paths)

    # ── Primary action ────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        paths = [self._file_list.item(i).text() for i in range(self._file_list.count())]
        if not paths:
            self.status_message.emit("Add at least one video file.", True)
            return

        out_dir = self._out_input.text().strip() or None
        use_logo = self._radio_logo.isChecked()

        if use_logo:
            logo = self._logo_input.text().strip()
            if not logo or not os.path.isfile(logo):
                self.status_message.emit("Select a valid logo image file.", True)
                return
            kwargs = {
                "logo_path": logo,
                "position": self._logo_pos.currentText(),
                "opacity": self._logo_opacity.value() / 100.0,
                "scale": self._logo_scale.value() / 100.0,
                "crf": self._enc_crf.value(),
                "preset": self._enc_preset.currentText(),
                "hw_accel": self._enc_hw.currentData(),
            }
            mode = "logo"
        else:
            text = self._wm_text.text().strip()
            if not text:
                self.status_message.emit("Enter watermark text.", True)
                return
            kwargs = {
                "text": text,
                "position": self._text_pos.currentText(),
                "font_size": self._font_size.value(),
                "font_color": self._font_color.currentText(),
                "opacity": self._text_opacity.value() / 100.0,
                "crf": self._enc_crf.value(),
                "preset": self._enc_preset.currentText(),
                "hw_accel": self._enc_hw.currentData(),
            }
            mode = "text"

        self._pending_out_dir = out_dir
        total = len(paths)
        # Indeterminate (pulsing) — per-file progress isn't visible inside a single ffmpeg run
        self._progress_bar.setRange(0, 0)
        self._set_busy(True, f"Watermarking {total} file(s)…", f"0 / {total}")

        _mode = mode
        _kwargs = kwargs

        def _do():
            def _progress(done: int, t: int) -> None:
                self._worker.signals.progress.emit(done, t, f"{done} / {t}")
            return watermark_batch(paths, _mode, out_dir, progress_cb=_progress, **_kwargs)

        self._worker = Worker(_do)
        self._worker.signals.progress.connect(self._on_progress)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, done: int, total: int, msg: str) -> None:
        self._progress_label.setText(msg)

    def _set_busy(self, busy: bool, status_msg: str = "", progress_msg: str = "") -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if busy:
            self._progress_label.setText(progress_msg)
            self.status_message.emit(status_msg, False)
        self.busy_changed.emit(busy)

    def _on_result(self, results: dict) -> None:
        self._set_busy(False)
        self._worker = None
        ok = sum(1 for v in results.values() if v)
        fail = len(results) - ok
        out_dir = getattr(self, "_pending_out_dir", None)
        self._last_result_path = None
        for path, success in results.items():
            base = os.path.splitext(os.path.basename(path))[0]
            ext = os.path.splitext(path)[1]
            out_filename = f"{base}_watermarked{ext}"
            actual_out_dir = out_dir or os.path.dirname(path) or "."
            output_path = os.path.join(actual_out_dir, out_filename)
            if success:
                self._last_result_path = output_path
            get_history_manager().add_item(HistoryItem(
                task_type="watermark",
                file_name=out_filename,
                file_path=output_path,
                status="success" if success else "error",
            ))
        if fail == 0:
            self.status_message.emit(f"Done → {ok} file(s) watermarked.", False)
        else:
            self.status_message.emit(
                f"Complete — {ok} succeeded, {fail} failed.", fail == len(results)
            )

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
