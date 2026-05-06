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

from core.i18n import tr
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
        self._hdr_files = _section_header(tr("hdr_video_image_files"))
        layout.addWidget(self._hdr_files)

        self._file_list = QListWidget()
        self._file_list.setObjectName("FileList")
        self._file_list.setFixedHeight(180)
        self._file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self._file_list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._wm_add_files_btn = QPushButton(tr("btn_add_files"))
        self._wm_add_files_btn.setObjectName("BrowseBtn")
        self._wm_add_files_btn.clicked.connect(self._browse_add_files)
        btn_row.addWidget(self._wm_add_files_btn)

        self._wm_add_dir_btn = QPushButton(tr("btn_add_folder"))
        self._wm_add_dir_btn.setObjectName("BrowseBtn")
        self._wm_add_dir_btn.clicked.connect(self._browse_add_folder)
        btn_row.addWidget(self._wm_add_dir_btn)

        self._wm_remove_btn = QPushButton(tr("btn_remove_selected"))
        self._wm_remove_btn.setObjectName("BrowseBtn")
        self._wm_remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(self._wm_remove_btn)

        self._wm_clear_btn = QPushButton(tr("btn_clear_all"))
        self._wm_clear_btn.setObjectName("BrowseBtn")
        self._wm_clear_btn.clicked.connect(self._file_list.clear)
        btn_row.addWidget(self._wm_clear_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._count_label = QLabel(tr("lbl_queue_files_many").format(n=0))
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
        self._hdr_wm_type = _section_header(tr("hdr_watermark_type"))
        layout.addWidget(self._hdr_wm_type)

        self._mode_group = QButtonGroup(self)
        self._radio_logo = QRadioButton(tr("lbl_wm_logo"))
        self._radio_text = QRadioButton(tr("lbl_wm_text"))
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
        self._hdr_logo = _section_header(tr("hdr_logo_opts"))
        layout.addWidget(self._hdr_logo)

        # Logo file
        self._lbl_logo_image = QLabel(tr("lbl_logo_image"))
        layout.addWidget(self._lbl_logo_image)
        logo_row = QHBoxLayout()
        self._logo_input = QLineEdit()
        self._logo_input.setObjectName("PillInput")
        self._logo_input.setPlaceholderText(tr("ph_logo_file"))
        logo_row.addWidget(self._logo_input)
        self._logo_browse_btn = QPushButton(tr("btn_browse"))
        self._logo_browse_btn.setObjectName("BrowseBtn")
        self._logo_browse_btn.setFixedWidth(90)
        self._logo_browse_btn.clicked.connect(self._browse_logo)
        logo_row.addWidget(self._logo_browse_btn)
        layout.addLayout(logo_row)

        # Position + scale + opacity row
        opts_row = QHBoxLayout()
        opts_row.setSpacing(16)

        pos_col = QVBoxLayout()
        self._wm_logo_lbl_pos = QLabel(tr("lbl_position"))
        pos_col.addWidget(self._wm_logo_lbl_pos)
        self._logo_pos = QComboBox()
        for key in _POSITIONS:
            self._logo_pos.addItem(tr(f"pos_{key.replace('-', '_')}"), key)
        self._logo_pos.setCurrentIndex(_POSITIONS.index("bottom-right"))
        self._logo_pos.setFixedWidth(150)
        pos_col.addWidget(self._logo_pos)
        opts_row.addLayout(pos_col)

        scale_col = QVBoxLayout()
        self._wm_logo_lbl_scale = QLabel(tr("lbl_scale_pct"))
        scale_col.addWidget(self._wm_logo_lbl_scale)
        self._logo_scale = QSpinBox()
        self._logo_scale.setRange(1, 100)
        self._logo_scale.setValue(15)
        self._logo_scale.setSuffix("%")
        self._logo_scale.setFixedWidth(90)
        scale_col.addWidget(self._logo_scale)
        opts_row.addLayout(scale_col)

        alpha_col = QVBoxLayout()
        self._wm_logo_lbl_opacity = QLabel(tr("lbl_opacity_pct"))
        alpha_col.addWidget(self._wm_logo_lbl_opacity)
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
        self._hdr_text = _section_header(tr("hdr_text_opts"))
        layout.addWidget(self._hdr_text)

        self._lbl_wm_text_content = QLabel(tr("lbl_wm_text_content"))
        layout.addWidget(self._lbl_wm_text_content)
        self._wm_text = QLineEdit()
        self._wm_text.setObjectName("PillInput")
        self._wm_text.setPlaceholderText(tr("ph_wm_text_example"))
        layout.addWidget(self._wm_text)

        opts_row = QHBoxLayout()
        opts_row.setSpacing(16)

        pos_col = QVBoxLayout()
        self._wm_text_lbl_pos = QLabel(tr("lbl_position"))
        pos_col.addWidget(self._wm_text_lbl_pos)
        self._text_pos = QComboBox()
        for key in _POSITIONS:
            self._text_pos.addItem(tr(f"pos_{key.replace('-', '_')}"), key)
        self._text_pos.setCurrentIndex(_POSITIONS.index("bottom-right"))
        self._text_pos.setFixedWidth(150)
        pos_col.addWidget(self._text_pos)
        opts_row.addLayout(pos_col)

        size_col = QVBoxLayout()
        self._wm_text_lbl_size = QLabel(tr("lbl_font_size"))
        size_col.addWidget(self._wm_text_lbl_size)
        self._font_size = QSpinBox()
        self._font_size.setRange(8, 256)
        self._font_size.setValue(36)
        self._font_size.setFixedWidth(90)
        size_col.addWidget(self._font_size)
        opts_row.addLayout(size_col)

        color_col = QVBoxLayout()
        self._wm_text_lbl_color = QLabel(tr("lbl_font_color"))
        color_col.addWidget(self._wm_text_lbl_color)
        self._font_color = QComboBox()
        for c in _COLORS:
            self._font_color.addItem(tr(f"color_{c}"), c)
        self._font_color.setCurrentIndex(_COLORS.index("white"))
        self._font_color.setFixedWidth(100)
        color_col.addWidget(self._font_color)
        opts_row.addLayout(color_col)

        alpha_col = QVBoxLayout()
        self._wm_text_lbl_opacity = QLabel(tr("lbl_opacity_pct"))
        alpha_col.addWidget(self._wm_text_lbl_opacity)
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
        self._hdr_encode = _section_header(tr("hdr_encode_settings"))
        layout.addWidget(self._hdr_encode)

        row = QHBoxLayout()
        row.setSpacing(16)

        crf_col = QVBoxLayout()
        self._wm_lbl_crf = QLabel(tr("lbl_crf_quality"))
        crf_col.addWidget(self._wm_lbl_crf)
        self._enc_crf = QSpinBox()
        self._enc_crf.setRange(1, 51)
        self._enc_crf.setValue(18)
        self._enc_crf.setFixedWidth(70)
        crf_col.addWidget(self._enc_crf)
        row.addLayout(crf_col)

        preset_col = QVBoxLayout()
        self._enc_preset_hint = QLabel(tr("hint_preset_smaller"))
        self._enc_preset_hint.setObjectName("TextMuted")
        self._enc_preset_hint.setStyleSheet("font-size: 11px;")
        preset_col.addWidget(self._enc_preset_hint)
        self._enc_preset = QComboBox()
        self._enc_preset.setFixedWidth(130)
        preset_col.addWidget(self._enc_preset)
        row.addLayout(preset_col)

        hw_col = QVBoxLayout()
        self._wm_lbl_hw = QLabel(tr("lbl_hw_accel"))
        hw_col.addWidget(self._wm_lbl_hw)
        self._enc_hw = QComboBox()
        self._enc_hw.setFixedWidth(160)
        self._enc_hw.addItem(tr("enc_hw_cpu"), "none")
        if "nvidia" in self._available_hw:
            self._enc_hw.addItem(tr("enc_hw_nvidia"), "nvidia")
        if "amd" in self._available_hw:
            self._enc_hw.addItem(tr("enc_hw_amd"), "amd")
        if "intel" in self._available_hw:
            self._enc_hw.addItem(tr("enc_hw_intel"), "intel")
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
        hint_keys = {
            "none": "hint_enc_preset_hw_none",
            "nvidia": "hint_enc_preset_hw_nvidia",
            "amd": "hint_enc_preset_hw_amd",
            "intel": "hint_enc_preset_hw_intel",
        }
        self._enc_preset.blockSignals(True)
        self._enc_preset.clear()
        self._enc_preset.addItems(presets)
        self._enc_preset.setCurrentText(default)
        self._enc_preset.blockSignals(False)
        self._enc_preset_hint.setText(tr(hint_keys.get(hw, "hint_enc_preset_hw_none")))

    # ── Output card ───────────────────────────────────────────────────────────

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_out = _section_header(tr("hdr_output_folder"))
        layout.addWidget(self._hdr_out)

        self._hint_wm_out = QLabel(tr("hint_watermark_output"))
        self._hint_wm_out.setObjectName("TextMuted")
        self._hint_wm_out.setWordWrap(True)
        self._hint_wm_out.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint_wm_out)

        row = QHBoxLayout()
        self._out_input = QLineEdit()
        self._out_input.setObjectName("PillInput")
        self._out_input.setPlaceholderText(tr("ph_each_source"))
        if self._settings.output_folder:
            self._out_input.setText(self._settings.output_folder)
        row.addWidget(self._out_input)

        self._wm_browse_out_btn = QPushButton(tr("btn_browse"))
        self._wm_browse_out_btn.setObjectName("BrowseBtn")
        self._wm_browse_out_btn.setFixedWidth(90)
        self._wm_browse_out_btn.clicked.connect(self._browse_output)
        row.addWidget(self._wm_browse_out_btn)
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
        self._count_label.setText(
            tr("lbl_queue_files_one") if n == 1 else tr("lbl_queue_files_many").format(n=n)
        )

    def _browse_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Logo Image", os.path.expanduser("~"),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if path:
            self._logo_input.setText(path)


    def _retranslate_wm_combos(self) -> None:
        for combo in (self._logo_pos, self._text_pos):
            for i in range(combo.count()):
                data = combo.itemData(i)
                if data is not None:
                    combo.setItemText(i, tr(f"pos_{str(data).replace('-', '_')}"))
        for i in range(self._font_color.count()):
            data = self._font_color.itemData(i)
            if data is not None:
                self._font_color.setItemText(i, tr(f"color_{data}"))
        cur_hw = self._enc_hw.currentData()
        self._enc_hw.blockSignals(True)
        self._enc_hw.clear()
        self._enc_hw.addItem(tr("enc_hw_cpu"), "none")
        if "nvidia" in self._available_hw:
            self._enc_hw.addItem(tr("enc_hw_nvidia"), "nvidia")
        if "amd" in self._available_hw:
            self._enc_hw.addItem(tr("enc_hw_amd"), "amd")
        if "intel" in self._available_hw:
            self._enc_hw.addItem(tr("enc_hw_intel"), "intel")
        restored = False
        for i in range(self._enc_hw.count()):
            if self._enc_hw.itemData(i) == cur_hw:
                self._enc_hw.setCurrentIndex(i)
                restored = True
                break
        if not restored:
            self._enc_hw.setCurrentIndex(0)
        self._enc_hw.blockSignals(False)
        self._on_enc_hw_changed(self._enc_hw.currentIndex())

    def retranslate_ui(self) -> None:
        self._hdr_files.setText(tr("hdr_video_image_files"))
        self._wm_add_files_btn.setText(tr("btn_add_files"))
        self._wm_add_dir_btn.setText(tr("btn_add_folder"))
        self._wm_remove_btn.setText(tr("btn_remove_selected"))
        self._wm_clear_btn.setText(tr("btn_clear_all"))
        self._update_count()
        self._hdr_wm_type.setText(tr("hdr_watermark_type"))
        self._radio_logo.setText(tr("lbl_wm_logo"))
        self._radio_text.setText(tr("lbl_wm_text"))
        self._hdr_logo.setText(tr("hdr_logo_opts"))
        self._lbl_logo_image.setText(tr("lbl_logo_image"))
        self._logo_input.setPlaceholderText(tr("ph_logo_file"))
        self._logo_browse_btn.setText(tr("btn_browse"))
        self._wm_logo_lbl_pos.setText(tr("lbl_position"))
        self._wm_logo_lbl_scale.setText(tr("lbl_scale_pct"))
        self._wm_logo_lbl_opacity.setText(tr("lbl_opacity_pct"))
        self._hdr_text.setText(tr("hdr_text_opts"))
        self._lbl_wm_text_content.setText(tr("lbl_wm_text_content"))
        self._wm_text.setPlaceholderText(tr("ph_wm_text_example"))
        self._wm_text_lbl_pos.setText(tr("lbl_position"))
        self._wm_text_lbl_size.setText(tr("lbl_font_size"))
        self._wm_text_lbl_color.setText(tr("lbl_font_color"))
        self._wm_text_lbl_opacity.setText(tr("lbl_opacity_pct"))
        self._hdr_encode.setText(tr("hdr_encode_settings"))
        self._wm_lbl_crf.setText(tr("lbl_crf_quality"))
        self._wm_lbl_hw.setText(tr("lbl_hw_accel"))
        self._retranslate_wm_combos()
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._hint_wm_out.setText(tr("hint_watermark_output"))
        self._out_input.setPlaceholderText(tr("ph_each_source"))
        self._wm_browse_out_btn.setText(tr("btn_browse"))

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
                "position": self._logo_pos.currentData(),
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
                "position": self._text_pos.currentData(),
                "font_size": self._font_size.value(),
                "font_color": self._font_color.currentData(),
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
