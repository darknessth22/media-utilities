"""AI Background Eraser — offline rembg-powered background removal."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QProgressBar, QPushButton, QRadioButton,
    QScrollArea, QSlider, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)

from core.i18n import tr
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.widgets.draw_canvas import (
    DrawCanvas, TOOL_BRUSH, TOOL_ELLIPSE, TOOL_LASSO, TOOL_RECT,
)
from gui.worker import Worker
from utils import model_manager
from utils.install_errors import classify as classify_install_error
from utils.model_manager import InsufficientDiskError


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


class BgEraserSection(QScrollArea):
    """Single-image background remover powered by rembg (fully offline)."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_result_path: str | None = None
        self._install_proc = None
        self._install_tail: list[str] = []
        self._component_id = "bg_eraser"
        self._current_sub_tab = 0
        self._detect_worker: Worker | None = None
        self._detect_index = -1

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._install_banner = self._build_install_banner()
        layout.addWidget(self._install_banner)

        self._tools_container = QWidget()
        tools_layout = QVBoxLayout(self._tools_container)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(16)
        tools_layout.addWidget(self._build_source_card())
        # Per-sub-tab options. The sidebar tab bar drives `_current_sub_tab`,
        # which selects both the options page and what the action button runs.
        tools_layout.addWidget(self._build_options_stack())
        tools_layout.addWidget(self._build_output_card())
        tools_layout.addWidget(self._build_progress_card())
        tools_layout.addWidget(self._build_preview_card())
        layout.addWidget(self._tools_container)

        self.setWidget(content)
        self._refresh_install_state()

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._load_input_preview)

    # ── Install banner ────────────────────────────────────────────────────────

    def _build_install_banner(self) -> QFrame:
        card = _card()
        card.setStyleSheet(
            "QFrame#Card { border: 1px solid rgba(245,158,11,0.4);"
            " background: rgba(245,158,11,0.06); border-radius: 10px; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        self._install_title = QLabel(f"⚠  {tr('lbl_model_not_installed')}")
        self._install_title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #F59E0B;"
        )
        title_row.addWidget(self._install_title)
        title_row.addStretch()
        layout.addLayout(title_row)

        self._install_desc = QLabel(tr("lbl_model_rembg_desc"))
        self._install_desc.setObjectName("TextMuted")
        self._install_desc.setWordWrap(True)
        self._install_desc.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._install_desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._install_btn = QPushButton(tr("btn_install_model"))
        self._install_btn.setObjectName("PrimaryBtn")
        self._install_btn.setFixedWidth(160)
        self._install_btn.clicked.connect(self._show_pre_install_panel)
        btn_row.addWidget(self._install_btn)

        self._retry_btn = QPushButton(tr("install_retry_button"))
        self._retry_btn.setObjectName("PrimaryBtn")
        self._retry_btn.setFixedWidth(140)
        self._retry_btn.clicked.connect(self._retry_install)
        self._retry_btn.setVisible(False)
        btn_row.addWidget(self._retry_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._preinstall_panel = QFrame()
        self._preinstall_panel.setObjectName("Card")
        self._preinstall_panel.setStyleSheet(
            "QFrame#Card { border: 1px solid rgba(59,130,246,0.4);"
            " background: rgba(59,130,246,0.06); border-radius: 8px; }"
        )
        pi_layout = QVBoxLayout(self._preinstall_panel)
        pi_layout.setContentsMargins(14, 10, 14, 10)
        pi_layout.setSpacing(6)
        self._variant_label = QLabel(tr("install_variant_choose"))
        self._variant_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        pi_layout.addWidget(self._variant_label)
        self._variant_group = QButtonGroup(self)
        self._variant_radios: list[QRadioButton] = []
        self._variant_radio_box = QVBoxLayout()
        self._variant_radio_box.setSpacing(2)
        pi_layout.addLayout(self._variant_radio_box)
        self._target_label = QLabel("")
        self._target_label.setObjectName("TextMuted")
        self._target_label.setWordWrap(True)
        self._target_label.setStyleSheet("font-size: 11px;")
        pi_layout.addWidget(self._target_label)
        pi_btn_row = QHBoxLayout()
        pi_btn_row.setSpacing(8)
        self._confirm_btn = QPushButton(tr("install_confirm_button"))
        self._confirm_btn.setObjectName("PrimaryBtn")
        self._confirm_btn.setFixedWidth(120)
        self._confirm_btn.clicked.connect(self._confirm_install)
        self._cancel_btn = QPushButton(tr("install_cancel_button"))
        self._cancel_btn.setObjectName("BrowseBtn")
        self._cancel_btn.setFixedWidth(100)
        self._cancel_btn.clicked.connect(self._cancel_pre_install)
        pi_btn_row.addWidget(self._confirm_btn)
        pi_btn_row.addWidget(self._cancel_btn)
        pi_btn_row.addStretch()
        pi_layout.addLayout(pi_btn_row)
        self._preinstall_panel.setVisible(False)
        layout.addWidget(self._preinstall_panel)

        self._install_status = QLabel("")
        self._install_status.setObjectName("TextMuted")
        self._install_status.setStyleSheet("font-size: 12px; color: #3B82F6;")
        self._install_status.setVisible(False)
        layout.addWidget(self._install_status)

        self._install_log = QTextEdit()
        self._install_log.setReadOnly(True)
        self._install_log.setFixedHeight(100)
        self._install_log.setObjectName("PillInput")
        self._install_log.setStyleSheet("font-size: 10px; font-family: monospace;")
        self._install_log.setVisible(False)
        layout.addWidget(self._install_log)

        return card

    def _refresh_install_state(self) -> None:
        installed = model_manager.is_installed(self._component_id)
        self._install_banner.setVisible(not installed)
        self._tools_container.setVisible(installed)

    def _show_pre_install_panel(self) -> None:
        try:
            variants = model_manager.available_variants(self._component_id)
            recommended = model_manager.detected_variant(self._component_id)
            target_dir = model_manager.pre_install_info(self._component_id).target_dir
        except Exception as exc:
            self._render_install_error(
                tr("install_error_generic").format(error=str(exc))
            )
            return

        for rb in self._variant_radios:
            self._variant_group.removeButton(rb)
            rb.setParent(None)
            rb.deleteLater()
        self._variant_radios = []

        for variant, size_mb in variants:
            base = (tr("install_variant_cuda") if variant == "cuda"
                    else tr("install_variant_cpu"))
            text = tr("install_variant_option").format(label=base, size_mb=size_mb)
            if variant == recommended and len(variants) > 1:
                text += "  " + tr("install_variant_recommended")
            rb = QRadioButton(text)
            rb.setStyleSheet("font-size: 12px;")
            rb.setProperty("variant", variant)
            if variant == recommended:
                rb.setChecked(True)
            self._variant_group.addButton(rb)
            self._variant_radio_box.addWidget(rb)
            self._variant_radios.append(rb)

        self._variant_label.setVisible(len(variants) > 1)
        self._target_label.setText(
            tr("install_target_label").format(target=target_dir)
        )
        self._install_btn.setVisible(False)
        self._preinstall_panel.setVisible(True)

    def _selected_variant(self) -> str:
        for rb in self._variant_radios:
            if rb.isChecked():
                return rb.property("variant") or "cpu"
        return "cpu"

    def _cancel_pre_install(self) -> None:
        self._preinstall_panel.setVisible(False)
        self._install_btn.setVisible(True)
        self._install_btn.setEnabled(True)

    def _confirm_install(self) -> None:
        self._chosen_variant = self._selected_variant()
        self._preinstall_panel.setVisible(False)
        self._install_btn.setVisible(True)
        self._start_install()

    def _start_install(self) -> None:
        self._install_btn.setEnabled(False)
        self._retry_btn.setVisible(False)
        self._install_status.setStyleSheet("font-size: 12px; color: #3B82F6;")
        self._install_status.setText(tr("lbl_model_installing"))
        self._install_status.setVisible(True)
        self._install_log.setVisible(True)
        self._install_log.clear()
        self._install_tail = []

        variant = getattr(self, "_chosen_variant", None)
        try:
            self._install_proc = model_manager.start_install(
                self._component_id, on_line=self._on_install_line, variant=variant,
            )
        except InsufficientDiskError as exc:
            info = model_manager.pre_install_info(self._component_id, variant)
            self._render_install_error(
                tr("install_error_disk").format(
                    required_mb=int(info.approx_size_mb * 1.5),
                    target=info.target_dir,
                )
            )
            return
        except Exception as exc:
            self._render_install_error(
                tr("install_error_generic").format(error=str(exc))
            )
            return

        self._install_proc.finished.connect(self._on_install_finished)

    def _on_install_line(self, line: str) -> None:
        import re as _re
        if _re.match(r"^\s*\d+%\|", line) or _re.search(r"\d+\.\d+\s*[KMG]?B/", line):
            self._install_status.setStyleSheet("font-size: 12px; color: #3B82F6;")
            self._install_status.setText(line)
            return
        self._install_log.append(line)
        self._install_tail.append(line)
        if len(self._install_tail) > 200:
            self._install_tail = self._install_tail[-200:]

    def _on_install_finished(self, exit_code: int, _status) -> None:
        proc = self._install_proc
        self._install_proc = None
        tail = "\n".join(self._install_tail)
        if proc is not None:
            try:
                tail += bytes(proc.readAllStandardOutput()).decode(
                    "utf-8", errors="replace"
                )
            except Exception:
                pass
        model_manager.finalize_install(self._component_id, exit_code, tail)

        if exit_code == 0:
            self._install_status.setStyleSheet("font-size: 12px; color: #22C55E;")
            self._install_status.setText(tr("lbl_model_install_done"))
            self._install_btn.setEnabled(True)
            import importlib
            importlib.invalidate_caches()
            model_manager.ensure_ai_packages_on_path()
            self._refresh_install_state()
            return

        state = model_manager.read_state(self._component_id)
        info = model_manager.pre_install_info(self._component_id, state.variant)
        msg = classify_install_error(
            state.last_error or tail,
            target=info.target_dir,
            required_mb=int(info.approx_size_mb * 1.5),
        )
        self._render_install_error(msg)

    def _render_install_error(self, msg: str) -> None:
        self._install_status.setStyleSheet("font-size: 12px; color: #EF4444;")
        self._install_status.setText(msg)
        self._install_status.setVisible(True)
        self._install_btn.setEnabled(False)
        self._retry_btn.setVisible(True)

    def _retry_install(self) -> None:
        model_manager.uninstall(self._component_id)
        self._start_install()

    # ── Source card ───────────────────────────────────────────────────────────

    def _build_source_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_src = _section_header(tr("hdr_source_img"))
        layout.addWidget(self._hdr_src)

        self._hint_src = QLabel(tr("hint_bg_source_formats"))
        self._hint_src.setObjectName("TextMuted")
        self._hint_src.setWordWrap(True)
        self._hint_src.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint_src)

        row = QHBoxLayout()
        self._input_edit = QLineEdit()
        self._input_edit.setObjectName("PillInput")
        self._input_edit.setPlaceholderText(tr("ph_img"))
        self._input_edit.textChanged.connect(self._on_input_changed)
        row.addWidget(self._input_edit)

        self._browse_in_btn = QPushButton(tr("btn_browse"))
        self._browse_in_btn.setObjectName("BrowseBtn")
        self._browse_in_btn.setFixedWidth(90)
        self._browse_in_btn.clicked.connect(self._browse_input)
        row.addWidget(self._browse_in_btn)
        layout.addLayout(row)

        # Input preview thumbnail — shown for the automatic sub-tab, where the
        # user only picks a file.
        self._preview_placeholder_key: str | None = "hint_bg_no_preview"
        self._input_preview = QLabel(tr("hint_bg_no_preview"))
        self._input_preview.setFixedSize(220, 140)
        self._input_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._input_preview.setObjectName("Card")
        self._input_preview.setStyleSheet(
            "QLabel#Card { border-radius: 6px; background: #1C2128;"
            " color: #8B949E; font-size: 12px; }"
        )
        layout.addWidget(self._input_preview)

        # Drawing surface — replaces the thumbnail on the erase sub-tab.
        self._canvas_wrap = QWidget()
        canvas_layout = QVBoxLayout(self._canvas_wrap)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(8)

        self._canvas = DrawCanvas()
        self._canvas.setObjectName("Card")
        self._canvas.setStyleSheet(
            "QLabel#Card { border-radius: 6px; background: #1C2128;"
            " color: #8B949E; font-size: 12px; }"
        )
        self._canvas.selection_changed.connect(self._on_selection_changed)
        canvas_layout.addWidget(self._canvas)

        # View controls — zoom / rotate / loupe, so fine brushwork is possible.
        view_row = QHBoxLayout()
        view_row.setSpacing(6)
        self._canvas.view_changed.connect(self._on_view_changed)

        self._zoom_out_btn = QPushButton("−")
        self._zoom_out_btn.setObjectName("BrowseBtn")
        self._zoom_out_btn.setFixedWidth(34)
        self._zoom_out_btn.clicked.connect(lambda: self._canvas.zoom_by(1 / 1.25))
        view_row.addWidget(self._zoom_out_btn)

        self._zoom_lbl = QLabel("100%")
        self._zoom_lbl.setObjectName("TextMuted")
        self._zoom_lbl.setStyleSheet("font-size: 11px;")
        self._zoom_lbl.setFixedWidth(46)
        self._zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        view_row.addWidget(self._zoom_lbl)

        self._zoom_in_btn = QPushButton("+")
        self._zoom_in_btn.setObjectName("BrowseBtn")
        self._zoom_in_btn.setFixedWidth(34)
        self._zoom_in_btn.clicked.connect(lambda: self._canvas.zoom_by(1.25))
        view_row.addWidget(self._zoom_in_btn)

        self._fit_btn = QPushButton(tr("btn_bg_fit"))
        self._fit_btn.setObjectName("BrowseBtn")
        self._fit_btn.clicked.connect(self._canvas.fit_to_window)
        view_row.addWidget(self._fit_btn)

        self._rot_ccw_btn = QPushButton("⟲")
        self._rot_ccw_btn.setObjectName("BrowseBtn")
        self._rot_ccw_btn.setFixedWidth(34)
        self._rot_ccw_btn.clicked.connect(lambda: self._canvas.rotate_by(-15))
        view_row.addWidget(self._rot_ccw_btn)

        self._rot_lbl = QLabel("0°")
        self._rot_lbl.setObjectName("TextMuted")
        self._rot_lbl.setStyleSheet("font-size: 11px;")
        self._rot_lbl.setFixedWidth(38)
        self._rot_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        view_row.addWidget(self._rot_lbl)

        self._rot_cw_btn = QPushButton("⟳")
        self._rot_cw_btn.setObjectName("BrowseBtn")
        self._rot_cw_btn.setFixedWidth(34)
        self._rot_cw_btn.clicked.connect(lambda: self._canvas.rotate_by(15))
        view_row.addWidget(self._rot_cw_btn)

        self._loupe_check = QCheckBox(tr("chk_bg_loupe"))
        self._loupe_check.setStyleSheet("font-size: 11px;")
        self._loupe_check.toggled.connect(self._canvas.set_loupe)
        view_row.addWidget(self._loupe_check)
        view_row.addStretch()
        canvas_layout.addLayout(view_row)

        self._nav_hint = QLabel(tr("hint_bg_navigation"))
        self._nav_hint.setObjectName("TextMuted")
        self._nav_hint.setWordWrap(True)
        self._nav_hint.setStyleSheet("font-size: 10px;")
        canvas_layout.addWidget(self._nav_hint)

        brush_row = QHBoxLayout()
        brush_row.setSpacing(8)
        self._brush_lbl = QLabel(tr("lbl_bg_brush_size"))
        self._brush_lbl.setObjectName("TextMuted")
        self._brush_lbl.setStyleSheet("font-size: 11px;")
        brush_row.addWidget(self._brush_lbl)

        self._brush_slider = QSlider(Qt.Orientation.Horizontal)
        self._brush_slider.setRange(4, 200)
        self._brush_slider.setValue(28)
        self._brush_slider.valueChanged.connect(self._canvas.set_brush_size)
        self._brush_slider.valueChanged.connect(self._update_brush_label)
        brush_row.addWidget(self._brush_slider, 1)

        # Negative brush — same tools, but strokes cut OUT of the selection.
        # Unlike Undo (which drops a whole stroke) this shaves a selection down
        # pixel by pixel, which is what trimming an over-eager smart pick needs.
        self._subtract_check = QCheckBox(tr("chk_bg_subtract"))
        self._subtract_check.setStyleSheet("font-size: 11px;")
        self._subtract_check.toggled.connect(self._on_subtract_toggled)
        brush_row.addWidget(self._subtract_check)

        self._undo_btn = QPushButton(tr("btn_bg_undo_stroke"))
        self._undo_btn.setObjectName("BrowseBtn")
        self._undo_btn.clicked.connect(self._canvas.undo_stroke)
        brush_row.addWidget(self._undo_btn)

        self._clear_sel_btn = QPushButton(tr("btn_bg_clear_selection"))
        self._clear_sel_btn.setObjectName("BrowseBtn")
        self._clear_sel_btn.clicked.connect(self._canvas.clear_selection)
        brush_row.addWidget(self._clear_sel_btn)
        canvas_layout.addLayout(brush_row)

        # Tells the user strokes add up, and how many are stored so far.
        self._stroke_lbl = QLabel(tr("hint_bg_strokes_none"))
        self._stroke_lbl.setObjectName("TextMuted")
        self._stroke_lbl.setWordWrap(True)
        self._stroke_lbl.setStyleSheet("font-size: 11px;")
        canvas_layout.addWidget(self._stroke_lbl)

        # Undo/Clear are meaningless until something has been painted.
        self._undo_btn.setEnabled(False)
        self._clear_sel_btn.setEnabled(False)
        self._update_brush_label(self._brush_slider.value())

        self._canvas_wrap.setVisible(False)
        layout.addWidget(self._canvas_wrap)
        return card

    # ── Options (one page per sub-tab) ────────────────────────────────────────

    def _build_options_stack(self) -> QWidget:
        self._options_stack = QStackedWidget()
        self._options_stack.addWidget(self._build_autobg_card())
        self._options_stack.addWidget(self._build_erase_card())
        self._options_stack.setCurrentIndex(0)
        return self._options_stack

    def _build_autobg_card(self) -> QFrame:
        """Sub-tab 0 — automatic background removal, with model choice."""
        from core.bg_eraser import DEFAULT_MODEL, MODELS

        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._hdr_model = _section_header(tr("hdr_bg_model"))
        layout.addWidget(self._hdr_model)

        self._model_combo = QComboBox()
        self._model_combo.setObjectName("PillInput")
        # Label keys follow the MODELS ordering so the dropdown stays in sync.
        for key in MODELS:
            self._model_combo.addItem(tr(f"bg_model_{key}"), key)
        self._model_combo.setCurrentIndex(list(MODELS).index(DEFAULT_MODEL))
        layout.addWidget(self._model_combo)

        self._model_hint = QLabel(tr("hint_bg_model"))
        self._model_hint.setObjectName("TextMuted")
        self._model_hint.setWordWrap(True)
        self._model_hint.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._model_hint)

        self._matting_check = QCheckBox(tr("chk_bg_alpha_matting"))
        self._matting_check.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._matting_check)
        return card

    def _build_tool_row(self) -> tuple[QWidget, QButtonGroup]:
        """Brush / lasso / rectangle selector for the erase sub-tab."""
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)
        group = QButtonGroup(row)
        for tool, key in ((TOOL_BRUSH, "bg_tool_brush"),
                          (TOOL_LASSO, "bg_tool_lasso"),
                          (TOOL_RECT, "bg_tool_rect"),
                          (TOOL_ELLIPSE, "bg_tool_ellipse")):
            rb = QRadioButton(tr(key))
            rb.setStyleSheet("font-size: 12px;")
            rb.setProperty("tool", tool)
            rb.setProperty("label_key", key)
            group.addButton(rb)
            h.addWidget(rb)
            setattr(self, f"_erase_rb_{tool}", rb)
        self._erase_rb_brush.setChecked(True)
        h.addStretch()
        return row, group

    def _build_erase_card(self) -> QFrame:
        """Sub-tab 1 — paint over an object to delete it and heal the gap."""
        import core.bg_eraser as _be
        _sens = _be
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._hdr_erase = _section_header(tr("hdr_bg_erase"))
        layout.addWidget(self._hdr_erase)
        self._hint_erase = QLabel(tr("hint_bg_erase"))
        self._hint_erase.setObjectName("TextMuted")
        self._hint_erase.setWordWrap(True)
        self._hint_erase.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._hint_erase)

        row, self._erase_tool_group = self._build_tool_row()
        self._erase_tool_group.buttonClicked.connect(self._on_tool_changed)
        layout.addWidget(row)

        # Smart select — the drawn shape points at an object and the object's
        # own outline is erased, rather than exactly the pixels drawn.
        self._smart_check = QCheckBox(tr("chk_bg_smart"))
        self._smart_check.setStyleSheet("font-size: 12px;")
        self._smart_check.toggled.connect(self._on_smart_toggled)
        layout.addWidget(self._smart_check)

        self._smart_hint = QLabel("")
        self._smart_hint.setObjectName("TextMuted")
        self._smart_hint.setWordWrap(True)
        self._smart_hint.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._smart_hint)

        # Sensitivity — how far a smart selection may grow past the exact spot
        # that was pointed at. This is what makes "one of three people" work.
        self._sens_row = QWidget()
        sens_h = QHBoxLayout(self._sens_row)
        sens_h.setContentsMargins(0, 0, 0, 0)
        sens_h.setSpacing(8)
        self._sens_lbl = QLabel(tr("lbl_bg_sensitivity"))
        self._sens_lbl.setObjectName("TextMuted")
        self._sens_lbl.setStyleSheet("font-size: 11px;")
        sens_h.addWidget(self._sens_lbl)
        self._sens_combo = QComboBox()
        self._sens_combo.setObjectName("PillInput")
        self._sens_combo.addItem(tr("bg_sens_tight"), _sens.SENS_TIGHT)
        self._sens_combo.addItem(tr("bg_sens_balanced"), _sens.SENS_BALANCED)
        self._sens_combo.addItem(tr("bg_sens_loose"), _sens.SENS_LOOSE)
        self._sens_combo.setCurrentIndex(1)
        self._sens_combo.currentIndexChanged.connect(self._on_sensitivity_changed)
        sens_h.addWidget(self._sens_combo, 1)
        layout.addWidget(self._sens_row)

        self._sens_hint = QLabel("")
        self._sens_hint.setObjectName("TextMuted")
        self._sens_hint.setWordWrap(True)
        self._sens_hint.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._sens_hint)
        self._on_smart_toggled(False)

        # Invert — keep what was selected, remove everything else.
        self._invert_check = QCheckBox(tr("chk_bg_invert"))
        self._invert_check.setStyleSheet("font-size: 12px;")
        self._invert_check.toggled.connect(self._on_invert_toggled)
        layout.addWidget(self._invert_check)

        self._invert_hint = QLabel(tr("hint_bg_invert_off"))
        self._invert_hint.setObjectName("TextMuted")
        self._invert_hint.setWordWrap(True)
        self._invert_hint.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._invert_hint)

        self._hdr_heal = _section_header(tr("hdr_bg_heal"))
        layout.addWidget(self._hdr_heal)

        self._heal_combo = QComboBox()
        self._heal_combo.setObjectName("PillInput")
        self._heal_combo.addItem(tr("bg_heal_lama"), _be.HEAL_LAMA)
        self._heal_combo.addItem(tr("bg_heal_fast"), _be.HEAL_FAST)
        self._heal_combo.addItem(tr("bg_heal_none"), _be.HEAL_NONE)
        self._heal_combo.setCurrentIndex(0)
        self._heal_combo.currentIndexChanged.connect(self._on_heal_changed)
        layout.addWidget(self._heal_combo)

        self._heal_warn = QLabel("")
        self._heal_warn.setObjectName("TextMuted")
        self._heal_warn.setWordWrap(True)
        self._heal_warn.setStyleSheet("font-size: 11px; color: #F59E0B;")
        layout.addWidget(self._heal_warn)
        self._on_heal_changed()
        return card

    # ── Output card ───────────────────────────────────────────────────────────

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_out = _section_header(tr("hdr_output_file"))
        layout.addWidget(self._hdr_out)

        row = QHBoxLayout()
        self._output_edit = QLineEdit()
        self._output_edit.setObjectName("PillInput")
        self._output_edit.setPlaceholderText(tr("ph_nobg_auto"))
        row.addWidget(self._output_edit)

        self._browse_out_btn = QPushButton(tr("btn_browse"))
        self._browse_out_btn.setObjectName("BrowseBtn")
        self._browse_out_btn.setFixedWidth(90)
        self._browse_out_btn.clicked.connect(self._browse_output)
        row.addWidget(self._browse_out_btn)
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
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)
        return card

    # ── Result preview card ───────────────────────────────────────────────────

    def _build_preview_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_result = _section_header(tr("hdr_result_preview"))
        layout.addWidget(self._hdr_result)

        self._result_placeholder_key: str | None = "hint_bg_result_placeholder"
        self._result_preview = QLabel(tr("hint_bg_result_placeholder"))
        self._result_preview.setMinimumSize(400, 200)
        self._result_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._result_preview.setObjectName("Card")
        self._result_preview.setWordWrap(True)
        self._result_preview.setStyleSheet(
            "QLabel#Card { border-radius: 6px; background: repeating-conic-gradient("
            "#2A2A3A 0% 25%, #1C1C2A 0% 50%) 0 0 / 20px 20px;"
            " color: #8B949E; font-size: 12px; }"
        )
        layout.addWidget(self._result_preview)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self._open_btn = QPushButton(tr("btn_open_explorer"))
        self._open_btn.setObjectName("BrowseBtn")
        self._open_btn.setVisible(False)
        self._open_btn.clicked.connect(self._open_result_folder)
        btn_row.addWidget(self._open_btn)
        layout.addLayout(btn_row)

        card.setVisible(False)
        self._result_card = card
        return card

    # ── Helpers ───────────────────────────────────────────────────────────────


    def on_sub_tab_changed(self, index: int) -> None:
        """Sub-tab switch from the section tab bar (0=auto background, 1=erase)."""
        self._current_sub_tab = max(0, min(1, index))
        self._options_stack.setCurrentIndex(self._current_sub_tab)

        drawing = self._current_sub_tab > 0
        self._canvas_wrap.setVisible(drawing)
        self._input_preview.setVisible(not drawing)
        # Brush width only applies to the freehand tool.
        self._sync_brush_row()

        if drawing:
            self._canvas.set_tool(self._active_tool())
            path = self._input_edit.text().strip()
            if path and os.path.isfile(path):
                self._canvas.set_image(path)
        self._update_output_placeholder()

    def _active_tool(self) -> str:
        btn = self._erase_tool_group.checkedButton()
        return btn.property("tool") if btn else TOOL_BRUSH

    def _sync_brush_row(self) -> None:
        show = self._current_sub_tab > 0 and self._active_tool() == TOOL_BRUSH
        self._brush_lbl.setVisible(show)
        self._brush_slider.setVisible(show)
        # Subtracting works with every shape, so it stays visible on the whole
        # erase sub-tab rather than only for the freehand brush.
        self._subtract_check.setVisible(self._current_sub_tab > 0)

    def _on_tool_changed(self, _btn=None) -> None:
        self._canvas.set_tool(self._active_tool())
        self._sync_brush_row()

    def _on_selection_changed(self) -> None:
        """Reflect the stroke count, and resolve a new smart stroke's object.

        Detection runs here rather than at Apply time so the user can SEE the
        detected outline on the canvas and undo it if it grabbed the wrong
        thing.
        """
        n = self._canvas.stroke_count()
        if n and self._canvas.last_stroke_is_smart():
            self._detect_last_stroke()
        self._stroke_lbl.setText(
            tr("hint_bg_strokes_none") if n == 0
            else tr("hint_bg_strokes").format(n=n)
        )
        self._undo_btn.setEnabled(n > 0)
        self._clear_sel_btn.setEnabled(n > 0)

    def _detect_last_stroke(self) -> None:
        """Segment the object the newest smart stroke points at."""
        import core.bg_eraser as be
        path = self._input_edit.text().strip()
        pts = self._canvas.last_stroke_points()
        if not path or not os.path.isfile(path) or not pts:
            return
        if not be.sam_available():
            # Nothing to preview until the model is fetched; Apply will get it.
            return
        if self._detect_worker and self._detect_worker.isRunning():
            return

        idx = self._canvas.last_stroke_index()
        self._canvas.set_pending_smart(True)
        self._detect_index = idx

        w = Worker(be.detect_object_mask, path, pts,
                   self._canvas.last_stroke_shape(), True,
                   self._model_combo.currentData() or be.DEFAULT_MODEL,
                   self._selected_sensitivity())
        w.signals.result.connect(self._on_detected)
        w.signals.error.connect(self._on_detect_error)
        self._detect_worker = w
        w.start()

    def _on_detected(self, result: dict) -> None:
        self._detect_worker = None
        self._canvas.set_pending_smart(False)
        if not result.get("success"):
            self.status_message.emit(
                result.get("error") or tr("err_bg_no_object"), True)
            return
        self._canvas.set_detected(self._detect_index, result["contours"],
                                  result.get("mask_key"))
        self._stroke_lbl.setText(tr("hint_bg_detected").format(
            pct=round(result["coverage"] * 100, 1)))

    def _on_detect_error(self, err_tuple: tuple) -> None:
        self._detect_worker = None
        self._canvas.set_pending_smart(False)
        _, msg, _ = err_tuple
        self.status_message.emit(f"{tr('err_bg_no_object')} ({msg})", True)

    def _update_brush_label(self, value: int) -> None:
        self._brush_lbl.setText(f"{tr('lbl_bg_brush_size')}  {value}px")

    @staticmethod
    def _erase_with_model(input_path: str, strokes: list, output_path,
                          heal: str, invert: bool = False,
                          sensitivity: str | None = None) -> dict:
        """Fetch any missing models, then erase. Runs in the worker.

        A failed download is not fatal — erase_region falls back (fast fill for
        healing, the drawn shape for smart select) and reports what actually ran
        via `heal_used` / `smart_used`.
        """
        import core.bg_eraser as be
        if any(st.get("smart") for st in strokes) and not be.sam_available():
            be.download_sam()
        if heal == be.HEAL_LAMA and not be.lama_available():
            be.download_lama()
        return be.erase_region(input_path, strokes, output_path, heal,
                               -1, invert,
                               sensitivity or be.DEFAULT_SENSITIVITY)

    def _on_smart_toggled(self, on: bool) -> None:
        """Explain smart mode, and whether its model still needs downloading."""
        import core.bg_eraser as be
        self._canvas.set_smart(on)
        # Sensitivity only affects smart selections; hide it otherwise so the
        # panel doesn't imply it does something for a literal brush stroke.
        self._sens_row.setVisible(bool(on))
        self._sens_hint.setVisible(bool(on))
        if on:
            self._on_sensitivity_changed()
        if not on:
            self._smart_hint.setText(tr("hint_bg_smart_off"))
            self._smart_hint.setStyleSheet("font-size: 11px;")
        elif be.sam_available():
            self._smart_hint.setText(tr("hint_bg_smart_on"))
            self._smart_hint.setStyleSheet("font-size: 11px;")
        else:
            self._smart_hint.setText(
                tr("hint_bg_smart_download").format(mb=be._SAM_SIZE_MB))
            self._smart_hint.setStyleSheet("font-size: 11px; color: #F59E0B;")

    def _on_subtract_toggled(self, on: bool) -> None:
        """Switch the brush between adding to and cutting out of the selection.

        Smart select is meaningless while subtracting — a negative stroke trims
        exactly what was drawn — so the checkbox is greyed out rather than
        silently ignored.
        """
        self._canvas.set_subtract(on)
        self._smart_check.setEnabled(not on)
        if on:
            self._stroke_lbl.setText(tr("hint_bg_subtract_on"))

    def _on_invert_toggled(self, on: bool) -> None:
        """Flip which side of the selection is removed."""
        self._canvas.set_invert(on)
        self._invert_hint.setText(
            tr("hint_bg_invert_on") if on else tr("hint_bg_invert_off"))
        self._invert_hint.setStyleSheet(
            "font-size: 11px; color: #F59E0B;" if on else "font-size: 11px;")

    def _selected_sensitivity(self) -> str:
        import core.bg_eraser as be
        return self._sens_combo.currentData() or be.DEFAULT_SENSITIVITY

    def _on_sensitivity_changed(self, _idx: int = 0) -> None:
        """Explain the chosen sensitivity, then re-detect with it.

        Re-running immediately matters: the user changes this precisely BECAUSE
        the last selection was wrong, so the preview must update without them
        having to redraw the stroke.
        """
        import core.bg_eraser as be
        mode = self._selected_sensitivity()
        self._sens_hint.setText(tr({
            be.SENS_TIGHT: "hint_bg_sens_tight",
            be.SENS_LOOSE: "hint_bg_sens_loose",
        }.get(mode, "hint_bg_sens_balanced")))
        if (self._smart_check.isChecked() and self._canvas.stroke_count()
                and self._canvas.last_stroke_is_smart()):
            self._detect_last_stroke()

    def _selected_heal(self) -> str:
        import core.bg_eraser as be
        return self._heal_combo.currentData() or be.HEAL_LAMA

    def _on_heal_changed(self, _idx: int = 0) -> None:
        """Explain the trade-off, and whether LaMa still needs downloading."""
        import core.bg_eraser as be
        mode = self._selected_heal()
        if mode == be.HEAL_LAMA:
            if be.lama_available():
                self._heal_warn.setText(tr("hint_bg_heal_lama_ready"))
                self._heal_warn.setStyleSheet("font-size: 11px;")
            else:
                self._heal_warn.setText(
                    tr("hint_bg_heal_lama_download").format(mb=be._LAMA_SIZE_MB))
                self._heal_warn.setStyleSheet(
                    "font-size: 11px; color: #F59E0B;")
        elif mode == be.HEAL_FAST:
            self._heal_warn.setText(tr("hint_bg_heal_limits"))
            self._heal_warn.setStyleSheet("font-size: 11px; color: #F59E0B;")
        else:
            self._heal_warn.setText(tr("hint_bg_heal_none"))
            self._heal_warn.setStyleSheet("font-size: 11px;")

    def _on_view_changed(self) -> None:
        self._zoom_lbl.setText(f"{self._canvas.zoom_percent()}%")
        self._rot_lbl.setText(f"{self._canvas.rotation()}°")
        # Screen-px brush width means the image-space width must be recomputed
        # whenever the zoom changes, or the ring and the stroke disagree.
        self._canvas.set_brush_size(self._brush_slider.value())

    def _update_output_placeholder(self) -> None:
        keys = ("ph_nobg_auto", "ph_bg_erase_auto")
        self._output_edit.setPlaceholderText(tr(keys[self._current_sub_tab]))

    def _set_input_preview_placeholder(self, key: str) -> None:
        self._preview_placeholder_key = key
        self._input_preview.setPixmap(QPixmap())
        self._input_preview.setText(tr(key))

    def retranslate_ui(self) -> None:
        self._install_title.setText(f"⚠  {tr('lbl_model_not_installed')}")
        self._install_desc.setText(tr("lbl_model_rembg_desc"))
        self._install_btn.setText(tr("btn_install_model"))
        self._retry_btn.setText(tr("install_retry_button"))
        self._confirm_btn.setText(tr("install_confirm_button"))
        self._cancel_btn.setText(tr("install_cancel_button"))
        self._variant_label.setText(tr("install_variant_choose"))
        self._hdr_src.setText(tr("hdr_source_img"))
        self._hint_src.setText(tr("hint_bg_source_formats"))
        self._input_edit.setPlaceholderText(tr("ph_img"))
        self._browse_in_btn.setText(tr("btn_browse"))
        if self._preview_placeholder_key:
            self._input_preview.setText(tr(self._preview_placeholder_key))
        self._hdr_out.setText(tr("hdr_output_file"))
        self._update_output_placeholder()
        self._browse_out_btn.setText(tr("btn_browse"))

        # Automatic sub-tab
        self._hdr_model.setText(tr("hdr_bg_model"))
        from core.bg_eraser import MODELS
        for i, key in enumerate(MODELS):
            self._model_combo.setItemText(i, tr(f"bg_model_{key}"))
        self._model_hint.setText(tr("hint_bg_model"))
        self._matting_check.setText(tr("chk_bg_alpha_matting"))

        # Drawing sub-tabs
        self._hdr_erase.setText(tr("hdr_bg_erase"))
        self._hint_erase.setText(tr("hint_bg_erase"))
        self._hdr_heal.setText(tr("hdr_bg_heal"))
        import core.bg_eraser as _be
        for i, key in enumerate(("bg_heal_lama", "bg_heal_fast", "bg_heal_none")):
            self._heal_combo.setItemText(i, tr(key))
        self._on_heal_changed()
        self._smart_check.setText(tr("chk_bg_smart"))
        self._sens_lbl.setText(tr("lbl_bg_sensitivity"))
        for i, key in enumerate(("bg_sens_tight", "bg_sens_balanced",
                                 "bg_sens_loose")):
            self._sens_combo.setItemText(i, tr(key))
        self._on_smart_toggled(self._smart_check.isChecked())
        self._invert_check.setText(tr("chk_bg_invert"))
        self._on_invert_toggled(self._invert_check.isChecked())
        self._subtract_check.setText(tr("chk_bg_subtract"))
        self._fit_btn.setText(tr("btn_bg_fit"))
        self._loupe_check.setText(tr("chk_bg_loupe"))
        self._nav_hint.setText(tr("hint_bg_navigation"))
        for btn in self._erase_tool_group.buttons():
            btn.setText(tr(btn.property("label_key")))
        self._update_brush_label(self._brush_slider.value())
        self._undo_btn.setText(tr("btn_bg_undo_stroke"))
        self._clear_sel_btn.setText(tr("btn_bg_clear_selection"))
        self._on_selection_changed()
        self._hdr_result.setText(tr("hdr_result_preview"))
        if self._result_placeholder_key:
            self._result_preview.setText(tr(self._result_placeholder_key))
        self._open_btn.setText(tr("btn_open_explorer"))

    def _browse_input(self) -> None:
        try:
            from core.bg_eraser import IMAGE_EXTS as _IMAGE_EXTS
        except ImportError:
            _IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
        ext_filter = "Images (" + " ".join(f"*{e}" for e in sorted(_IMAGE_EXTS)) + ")"
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", os.path.expanduser("~"), ext_filter
        )
        if path:
            self._input_edit.setText(path)

    def _browse_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Output PNG", os.path.expanduser("~"), "PNG image (*.png)"
        )
        if path:
            if not path.lower().endswith(".png"):
                path += ".png"
            self._output_edit.setText(path)

    def _on_input_changed(self, path: str) -> None:
        self._preview_timer.start()
        # Auto-fill output path
        path = path.strip()
        if path and os.path.isfile(path) and not self._output_edit.text().strip():
            stem = os.path.splitext(path)[0]
            suffix = ("nobg", "erased")[self._current_sub_tab]
            self._output_edit.setPlaceholderText(f"{stem}_{suffix}.png")

    def _load_input_preview(self) -> None:
        path = self._input_edit.text().strip()
        if not path or not os.path.isfile(path):
            self._set_input_preview_placeholder("hint_bg_no_preview")
            return
        if self._current_sub_tab > 0:
            self._canvas.set_image(path)
        px = QPixmap(path)
        if not px.isNull():
            self._preview_placeholder_key = None
            self._input_preview.setPixmap(
                px.scaled(220, 140, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
            self._input_preview.setText("")
        else:
            self._set_input_preview_placeholder("err_palette_bad_image")

    def populate_file(self, path: str) -> None:
        self._input_edit.setText(path)

    def _set_busy(self, busy: bool, msg: str = "") -> None:
        self._progress_bar.setVisible(busy)
        if busy and msg:
            self.status_message.emit(msg, False)
        self.busy_changed.emit(busy)

    def _open_result_folder(self) -> None:
        if self._last_result_path and os.path.isfile(self._last_result_path):
            import subprocess, sys
            if sys.platform == "win32":
                subprocess.Popen(
                    ["explorer", "/select,", os.path.normpath(self._last_result_path)]
                )
            else:
                from PySide6.QtGui import QDesktopServices
                from PySide6.QtCore import QUrl
                QDesktopServices.openUrl(
                    QUrl.fromLocalFile(os.path.dirname(self._last_result_path))
                )

    # ── Primary action ────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        input_path = self._input_edit.text().strip()
        if not input_path or not os.path.isfile(input_path):
            self.status_message.emit("Select a valid image file.", True)
            return

        output_path = self._output_edit.text().strip() or None
        # A typed name without an extension gives PIL no format to save as.
        if output_path and not os.path.splitext(output_path)[1]:
            output_path += ".png"
        if output_path and not os.path.isabs(output_path):
            output_path = os.path.join(os.path.dirname(input_path), output_path)

        import core.bg_eraser as be

        if self._current_sub_tab == 0:
            model = self._model_combo.currentData() or be.DEFAULT_MODEL
            size_mb = be.MODELS.get(model, (None, 0))[1]
            self._result_card.setVisible(False)
            self._set_busy(True, tr("dyn_bg_removing").format(mb=size_mb))
            self._worker = Worker(
                be.remove_background, input_path, output_path,
                model, self._matting_check.isChecked(),
            )
        else:
            if not self._canvas.has_selection():
                self.status_message.emit(tr("err_bg_no_selection"), True)
                return
            heal = self._selected_heal()
            self._result_card.setVisible(False)
            strokes = self._canvas.strokes()
            # A selection made only of negative strokes cuts from nothing, so it
            # would reach the core as an empty mask. Say so here instead.
            if not any(not st.get("subtract") for st in strokes):
                self.status_message.emit(tr("err_bg_only_subtract"), True)
                return
            wants_smart = any(st.get("smart") for st in strokes)
            if wants_smart and not be.sam_available():
                # One-off fetch; done inside the worker so the UI keeps a single
                # busy state and stays responsive.
                self._set_busy(True, tr("dyn_bg_smart_downloading").format(
                    mb=be._SAM_SIZE_MB))
            elif heal == be.HEAL_LAMA and not be.lama_available():
                self._set_busy(True, tr("dyn_bg_heal_downloading").format(
                    mb=be._LAMA_SIZE_MB))
            elif wants_smart:
                self._set_busy(True, tr("dyn_bg_smart_erasing"))
            else:
                self._set_busy(True, tr("dyn_bg_erasing"))
            self._worker = Worker(
                self._erase_with_model, input_path, strokes, output_path, heal,
                self._invert_check.isChecked(), self._selected_sensitivity(),
            )

        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _on_result(self, result: dict) -> None:
        self._set_busy(False)
        self._worker = None

        if not result["success"]:
            self.status_message.emit(f"Failed: {result['error']}", True)
            return

        out_path = result["file_path"]
        self._last_result_path = out_path

        px = QPixmap(out_path)
        if not px.isNull():
            self._result_placeholder_key = None
            self._result_preview.setPixmap(
                px.scaled(600, 400, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
            self._result_preview.setText("")
        else:
            self._result_placeholder_key = None
            self._result_preview.setText(out_path)

        self._open_btn.setVisible(True)
        self._result_card.setVisible(True)

        get_history_manager().add_item(HistoryItem(
            task_type=("bg_erase", "bg_object_erase")[self._current_sub_tab],
            file_name=os.path.basename(self._input_edit.text()),
            file_path=out_path,
            status="success",
        ))

        # If LaMa was asked for but the fast fill ran instead, say so — the
        # difference is visible and the user should know why.
        note = ""
        if self._current_sub_tab == 1:
            import core.bg_eraser as be
            notes = []
            if (self._selected_heal() == be.HEAL_LAMA
                    and result.get("heal_used") == be.HEAL_FAST):
                notes.append(tr("warn_bg_heal_fell_back"))
            if self._smart_check.isChecked() and not result.get("smart_used"):
                notes.append(tr("warn_bg_smart_fell_back"))
            if (result.get("hole_fraction") or 0) > 0.25:
                notes.append(tr("warn_bg_large_hole"))
            if notes:
                note = "  (" + "; ".join(notes) + ")"
        self.status_message.emit(
            f"Done → {os.path.basename(out_path)}{note}", False)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
