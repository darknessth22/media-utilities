"""AI Photo Restore — chained Colorize → Face Restore → Upscale pipeline.

Same install-banner / Worker pattern as upscaler_section. The actual heavy
lifting (torch, CodeFormer, DDColor, Real-ESRGAN) lives in core/restore.py's
child subprocess so this tab keeps the GUI snappy.
"""
from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QProgressBar,
    QPushButton, QRadioButton, QScrollArea, QSlider,
    QTextEdit, QVBoxLayout, QWidget,
)

from core.i18n import tr
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
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


class PhotoRestoreSection(QScrollArea):
    """AI Photo Restore — chained colorize + face restore + upscale."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_output_path: str | None = None
        self._install_proc = None
        self._install_tail: list[str] = []
        self._component_id = "photo_restore"

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
        tools_layout.addWidget(self._build_output_card())
        tools_layout.addWidget(self._build_stages_card())
        tools_layout.addWidget(self._build_device_card())
        tools_layout.addWidget(self._build_progress_card())
        tools_layout.addWidget(self._build_result_card())
        layout.addWidget(self._tools_container)

        self.setWidget(content)
        self._refresh_install_state()
        QTimer.singleShot(0, self._detect_device_async)

    def showEvent(self, event) -> None:  # noqa: N802 — Qt API
        super().showEvent(event)
        self._refresh_install_state()

    # ── Install banner (mirrors upscaler_section) ─────────────────────────────

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

        self._install_desc = QLabel(tr("lbl_model_photo_restore_desc"))
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
        self._install_desc.setText(tr("lbl_model_photo_restore_desc"))
        self._install_btn.setEnabled(True)
        self._install_btn.setToolTip("")

    def _show_pre_install_panel(self) -> None:
        try:
            variants = model_manager.available_variants(self._component_id)
            recommended = model_manager.detected_variant(self._component_id)
            target_dir = model_manager.pre_install_info(self._component_id).target_dir
        except Exception as exc:
            self._render_install_error(tr("install_error_generic").format(error=str(exc)))
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
            supported, reason_key = model_manager.variant_compatibility(self._component_id, variant)
            if not supported:
                text += "  " + tr("install_variant_unavailable")
            elif variant == recommended and len(variants) > 1:
                text += "  " + tr("install_variant_recommended")
            rb = QRadioButton(text)
            rb.setStyleSheet("font-size: 12px;")
            rb.setProperty("variant", variant)
            if not supported:
                rb.setEnabled(False)
                if reason_key:
                    rb.setToolTip(tr(reason_key))
            elif variant == recommended:
                rb.setChecked(True)
            self._variant_group.addButton(rb)
            self._variant_radio_box.addWidget(rb)
            self._variant_radios.append(rb)

        if not any(rb.isChecked() for rb in self._variant_radios):
            for rb in self._variant_radios:
                if rb.isEnabled():
                    rb.setChecked(True)
                    break

        self._variant_label.setVisible(len(variants) > 1)
        self._target_label.setText(tr("install_target_label").format(target=target_dir))
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
        except InsufficientDiskError:
            info = model_manager.pre_install_info(self._component_id, variant)
            self._render_install_error(
                tr("install_error_disk").format(
                    required_mb=int(info.approx_size_mb * 1.5),
                    target=info.target_dir,
                )
            )
            return
        except Exception as exc:
            self._render_install_error(tr("install_error_generic").format(error=str(exc)))
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
                tail += bytes(proc.readAllStandardOutput()).decode("utf-8", errors="replace")
            except Exception:
                pass
        actual_id = (proc.property("videl_component_id") if proc else None) or self._component_id
        target_id = (proc.property("videl_target_id") if proc else None) or self._component_id
        model_manager.finalize_install(actual_id, exit_code, tail)

        if exit_code == 0:
            import importlib
            importlib.invalidate_caches()
            model_manager.ensure_ai_packages_on_path()
            if actual_id != target_id and not model_manager.is_installed(target_id):
                self._on_install_line(f"[deps] Continuing with {target_id}…")
                variant = getattr(self, "_chosen_variant", None)
                try:
                    self._install_proc = model_manager.start_install(
                        target_id, on_line=self._on_install_line, variant=variant,
                    )
                    self._install_proc.finished.connect(self._on_install_finished)
                    return
                except Exception as exc:
                    self._render_install_error(tr("install_error_generic").format(error=str(exc)))
                    return
            self._install_status.setStyleSheet("font-size: 12px; color: #22C55E;")
            self._install_status.setText(tr("lbl_model_install_done"))
            self._install_btn.setEnabled(True)
            self._refresh_install_state()
            self._detect_device_async()
            return

        state = model_manager.read_state(actual_id)
        info = model_manager.pre_install_info(actual_id, state.variant)
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

    # ── Source / output cards ─────────────────────────────────────────────────

    def _build_source_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_src = _section_header(tr("hdr_source_image"))
        layout.addWidget(self._hdr_src)
        self._hint_src = QLabel(tr("hint_upscaler_source_formats"))
        self._hint_src.setObjectName("TextMuted")
        self._hint_src.setWordWrap(True)
        self._hint_src.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint_src)
        row = QHBoxLayout()
        self._input_edit = QLineEdit()
        self._input_edit.setObjectName("PillInput")
        self._input_edit.setPlaceholderText(tr("ph_image"))
        row.addWidget(self._input_edit)
        self._browse_in_btn = QPushButton(tr("btn_browse"))
        self._browse_in_btn.setObjectName("BrowseBtn")
        self._browse_in_btn.setFixedWidth(90)
        self._browse_in_btn.clicked.connect(self._browse_input)
        row.addWidget(self._browse_in_btn)
        layout.addLayout(row)
        return card

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
        self._output_edit.setPlaceholderText(tr("ph_photo_restore_output"))
        row.addWidget(self._output_edit)
        self._browse_out_btn = QPushButton(tr("btn_browse"))
        self._browse_out_btn.setObjectName("BrowseBtn")
        self._browse_out_btn.setFixedWidth(90)
        self._browse_out_btn.clicked.connect(self._browse_output)
        row.addWidget(self._browse_out_btn)
        layout.addLayout(row)
        return card

    # ── Stages card (3 toggles + CodeFormer fidelity) ─────────────────────────

    def _build_stages_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._hdr_stages = _section_header(tr("hdr_photo_restore_stages"))
        layout.addWidget(self._hdr_stages)

        self._cb_heal = QCheckBox(tr("photo_restore_stage_heal"))
        self._cb_colorize = QCheckBox(tr("photo_restore_stage_colorize"))
        self._cb_restore_faces = QCheckBox(tr("photo_restore_stage_faces"))
        for cb in (self._cb_heal, self._cb_colorize, self._cb_restore_faces):
            cb.setStyleSheet("font-size: 13px;")
            layout.addWidget(cb)
        self._cb_restore_faces.setChecked(True)

        # Heal strength — scratch detection sensitivity + light bilateral
        # at high values. Default low (5) since aggressive heal melts faces.
        self._heal_lbl = QLabel(tr("photo_restore_heal_strength").format(value=10))
        self._heal_lbl.setObjectName("TextMuted")
        self._heal_lbl.setStyleSheet("font-size: 11px; margin-top: 4px;")
        layout.addWidget(self._heal_lbl)
        self._heal_slider = QSlider(Qt.Orientation.Horizontal)
        self._heal_slider.setRange(3, 25)
        self._heal_slider.setValue(10)
        self._heal_slider.valueChanged.connect(
            lambda v: self._heal_lbl.setText(tr("photo_restore_heal_strength").format(value=v))
        )
        layout.addWidget(self._heal_slider)
        def _toggle_heal():
            on = self._cb_heal.isChecked()
            for w in (self._heal_lbl, self._heal_slider):
                w.setVisible(on)
        self._cb_heal.toggled.connect(_toggle_heal)
        _toggle_heal()
        self._upscale_hint = QLabel(tr("photo_restore_upscale_hint"))
        self._upscale_hint.setObjectName("TextMuted")
        self._upscale_hint.setWordWrap(True)
        self._upscale_hint.setStyleSheet("font-size: 11px; color: #6B7280; margin-top: 4px;")
        layout.addWidget(self._upscale_hint)

        # Colorize Style — DDColor variant. Natural (modelscope ONNX, photo-
        # realistic default) vs Vivid (artistic ONNX, bolder/cinematic).
        style_row = QHBoxLayout()
        style_row.setSpacing(8)
        self._style_lbl = QLabel(tr("photo_restore_colorize_style"))
        self._style_lbl.setObjectName("TextMuted")
        self._style_lbl.setStyleSheet("font-size: 11px; margin-top: 8px;")
        style_row.addWidget(self._style_lbl)
        self._style_combo = QComboBox()
        self._style_combo.setObjectName("PillInput")
        self._style_combo.addItem(tr("photo_restore_style_natural"), "natural")
        self._style_combo.addItem(tr("photo_restore_style_vivid"), "vivid")
        style_row.addWidget(self._style_combo, 1)
        layout.addLayout(style_row)

        # Colorize input size — bigger = sharper ab field but slower.
        size_row = QHBoxLayout()
        size_row.setSpacing(8)
        self._size_lbl = QLabel(tr("photo_restore_colorize_size"))
        self._size_lbl.setObjectName("TextMuted")
        self._size_lbl.setStyleSheet("font-size: 11px;")
        size_row.addWidget(self._size_lbl)
        self._size_combo = QComboBox()
        self._size_combo.setObjectName("PillInput")
        self._size_combo.addItem(tr("photo_restore_size_384"), 384)
        self._size_combo.addItem(tr("photo_restore_size_512"), 512)
        self._size_combo.addItem(tr("photo_restore_size_768"), 768)
        self._size_combo.setCurrentIndex(1)  # 512 default
        size_row.addWidget(self._size_combo, 1)
        layout.addLayout(size_row)

        # Saturation slider — gentle by default since gray-world WB already
        # adds perceived colour pop. Push higher only when you want vivid.
        self._sat_lbl = QLabel(tr("photo_restore_colorize_saturation").format(value=115))
        self._sat_lbl.setObjectName("TextMuted")
        self._sat_lbl.setStyleSheet("font-size: 11px; margin-top: 8px;")
        layout.addWidget(self._sat_lbl)
        self._sat_slider = QSlider(Qt.Orientation.Horizontal)
        self._sat_slider.setRange(80, 200)
        self._sat_slider.setValue(115)
        self._sat_slider.valueChanged.connect(
            lambda v: self._sat_lbl.setText(tr("photo_restore_colorize_saturation").format(value=v))
        )
        layout.addWidget(self._sat_slider)
        # Show saturation row only when colorize is on.
        def _toggle_sat():
            on = self._cb_colorize.isChecked()
            for w in (self._sat_lbl, self._sat_slider,
                      self._style_lbl, self._style_combo,
                      self._size_lbl, self._size_combo):
                w.setVisible(on)
        self._cb_colorize.toggled.connect(_toggle_sat)
        _toggle_sat()

        # CodeFormer fidelity slider — 0 = max identity, 1 = max quality.
        self._fidelity_lbl = QLabel(tr("photo_restore_fidelity").format(value=70))
        self._fidelity_lbl.setObjectName("TextMuted")
        self._fidelity_lbl.setStyleSheet("font-size: 11px; margin-top: 4px;")
        layout.addWidget(self._fidelity_lbl)
        self._fidelity_slider = QSlider(Qt.Orientation.Horizontal)
        self._fidelity_slider.setRange(0, 100)
        self._fidelity_slider.setValue(70)
        self._fidelity_slider.valueChanged.connect(
            lambda v: self._fidelity_lbl.setText(tr("photo_restore_fidelity").format(value=v))
        )
        layout.addWidget(self._fidelity_slider)
        return card

    # ── Device card ───────────────────────────────────────────────────────────

    def _build_device_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(6)
        self._device_lbl = QLabel(f"⚡ {tr('lbl_vocal_device')}: …")
        self._device_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._device_lbl.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._device_lbl)

        self._device_group = QButtonGroup(self)
        row = QHBoxLayout()
        row.setSpacing(12)
        self._device_rb_auto = QRadioButton("Auto")
        self._device_rb_cpu = QRadioButton("CPU")
        self._device_rb_cuda = QRadioButton("GPU (CUDA)")
        for rb in (self._device_rb_auto, self._device_rb_cpu, self._device_rb_cuda):
            rb.setStyleSheet("font-size: 12px;")
            self._device_group.addButton(rb)
            row.addWidget(rb)
        row.addStretch()
        self._device_rb_auto.setChecked(True)
        layout.addLayout(row)

        self._warn_lbl = QLabel(f"⚠ {tr('warn_photo_restore_cpu')}")
        self._warn_lbl.setObjectName("TextMuted")
        self._warn_lbl.setWordWrap(True)
        self._warn_lbl.setStyleSheet(
            "font-size: 12px; color: #F59E0B; "
            "background: rgba(245,158,11,0.08); "
            "border: 1px solid rgba(245,158,11,0.25); "
            "border-radius: 6px; padding: 6px 10px;"
        )
        self._warn_lbl.setVisible(False)
        layout.addWidget(self._warn_lbl)
        return card

    def _detect_device_async(self) -> None:
        def _do_detect():
            try:
                from core.upscaler import detect_device, last_detect_debug
                dev = detect_device()
                return (dev, last_detect_debug())
            except Exception as exc:
                return ("cpu", f"detect_device raised: {exc}")
        w = Worker(_do_detect)
        w.signals.result.connect(self._on_device_detected)
        w.start()
        self._device_worker = w

    def _on_device_detected(self, payload) -> None:
        if isinstance(payload, tuple):
            device, debug = payload
        else:
            device, debug = payload, ""
        device_label = "GPU (CUDA)" if device == "cuda" else "CPU"
        color = "#3B82F6" if device == "cuda" else "#F59E0B"
        self._device_lbl.setText(
            f"⚡ {tr('lbl_vocal_device')}: <b style='color:{color};'>{device_label}</b>"
        )
        if debug:
            self._device_lbl.setToolTip(debug)
        self._warn_lbl.setVisible(device == "cpu")
        self._detected_device = device
        cuda_usable = device == "cuda"
        try:
            cuda_installed = model_manager.read_state("torch_runtime").variant == "cuda"
        except Exception:
            cuda_installed = False
        self._device_rb_cuda.setEnabled(cuda_usable and cuda_installed)
        if not (cuda_usable and cuda_installed):
            self._device_rb_cuda.setToolTip(
                "CUDA variant not installed or your GPU is not supported."
            )

    # ── Progress + result cards ───────────────────────────────────────────────

    def _build_progress_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("TaskProgressBar")
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)
        self._progress_lbl = QLabel("")
        self._progress_lbl.setObjectName("TextMuted")
        self._progress_lbl.setStyleSheet("font-size: 11px;")
        self._progress_lbl.setVisible(False)
        layout.addWidget(self._progress_lbl)
        return card

    def _build_result_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        self._hdr_result = _section_header(tr("hdr_result"))
        layout.addWidget(self._hdr_result)
        self._result_lbl = QLabel("")
        self._result_lbl.setWordWrap(True)
        self._result_lbl.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._result_lbl)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._open_btn = QPushButton(tr("btn_open_explorer"))
        self._open_btn.setObjectName("BrowseBtn")
        self._open_btn.setVisible(False)
        self._open_btn.clicked.connect(self._open_output_folder)
        btn_row.addWidget(self._open_btn)
        layout.addLayout(btn_row)
        card.setVisible(False)
        self._result_card = card
        return card

    # ── Public API used by app.py ─────────────────────────────────────────────

    def retranslate_ui(self) -> None:
        self._install_title.setText(f"⚠  {tr('lbl_model_not_installed')}")
        self._install_desc.setText(tr("lbl_model_photo_restore_desc"))
        self._install_btn.setText(tr("btn_install_model"))
        self._retry_btn.setText(tr("install_retry_button"))
        self._confirm_btn.setText(tr("install_confirm_button"))
        self._cancel_btn.setText(tr("install_cancel_button"))
        self._variant_label.setText(tr("install_variant_choose"))
        self._hdr_src.setText(tr("hdr_source_image"))
        self._hint_src.setText(tr("hint_upscaler_source_formats"))
        self._input_edit.setPlaceholderText(tr("ph_image"))
        self._browse_in_btn.setText(tr("btn_browse"))
        self._hdr_out.setText(tr("hdr_output_file"))
        self._output_edit.setPlaceholderText(tr("ph_photo_restore_output"))
        self._browse_out_btn.setText(tr("btn_browse"))
        self._hdr_stages.setText(tr("hdr_photo_restore_stages"))
        self._cb_heal.setText(tr("photo_restore_stage_heal"))
        self._cb_colorize.setText(tr("photo_restore_stage_colorize"))
        self._cb_restore_faces.setText(tr("photo_restore_stage_faces"))
        self._heal_lbl.setText(tr("photo_restore_heal_strength").format(value=self._heal_slider.value()))
        self._upscale_hint.setText(tr("photo_restore_upscale_hint"))
        self._sat_lbl.setText(tr("photo_restore_colorize_saturation").format(value=self._sat_slider.value()))
        self._style_lbl.setText(tr("photo_restore_colorize_style"))
        self._style_combo.setItemText(0, tr("photo_restore_style_natural"))
        self._style_combo.setItemText(1, tr("photo_restore_style_vivid"))
        self._size_lbl.setText(tr("photo_restore_colorize_size"))
        self._size_combo.setItemText(0, tr("photo_restore_size_384"))
        self._size_combo.setItemText(1, tr("photo_restore_size_512"))
        self._size_combo.setItemText(2, tr("photo_restore_size_768"))
        self._fidelity_lbl.setText(tr("photo_restore_fidelity").format(value=self._fidelity_slider.value()))
        self._warn_lbl.setText(f"⚠ {tr('warn_photo_restore_cpu')}")
        self._hdr_result.setText(tr("hdr_result"))
        self._open_btn.setText(tr("btn_open_explorer"))

    def populate_file(self, path: str) -> None:
        self._input_edit.setText(path)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _browse_input(self) -> None:
        from core.upscaler import IMAGE_EXTS
        exts = " ".join(f"*{e}" for e in sorted(IMAGE_EXTS))
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", os.path.expanduser("~"),
            f"Images ({exts})",
        )
        if path:
            self._input_edit.setText(path)

    def _browse_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Restored Image As", os.path.expanduser("~"),
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;WebP (*.webp)",
        )
        if path:
            self._output_edit.setText(path)

    def _set_busy(self, busy: bool, msg: str = "") -> None:
        self._progress_bar.setVisible(busy)
        self._progress_lbl.setVisible(busy)
        if busy:
            self._progress_bar.setValue(0)
            if msg:
                self.status_message.emit(msg, False)
        self.busy_changed.emit(busy)

    def _on_progress(self, value: int, _total: int, label: str) -> None:
        self._progress_bar.setValue(value)
        self._progress_lbl.setText(f"{value}% — {label}" if label else f"{value}%")

    def _open_output_folder(self) -> None:
        if self._last_output_path and os.path.isfile(self._last_output_path):
            folder = os.path.dirname(self._last_output_path)
            if sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(self._last_output_path)])
            else:
                from PySide6.QtGui import QDesktopServices
                from PySide6.QtCore import QUrl
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # ── Primary action ────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        input_path = self._input_edit.text().strip()
        if not input_path or not os.path.isfile(input_path):
            self.status_message.emit(tr("err_photo_restore_no_input"), True)
            return

        options = {
            "colorize": self._cb_colorize.isChecked(),
            "restore_faces": self._cb_restore_faces.isChecked(),
            "heal": self._cb_heal.isChecked(),
        }
        if not any(options.values()):
            self.status_message.emit(tr("err_photo_restore_no_stages"), True)
            return

        output_path = self._output_edit.text().strip()
        if not output_path:
            stem, ext = os.path.splitext(input_path)
            ext = ext or ".png"
            output_path = f"{stem}_restored{ext}"

        self._result_card.setVisible(False)
        self._set_busy(True, tr("dyn_photo_restore_processing"))

        def _progress_cb(pct: int, label: str) -> None:
            if self._worker:
                self._worker.signals.progress.emit(pct, 100, label)

        def _cancelled_cb() -> bool:
            return bool(self._worker and self._worker.is_cancelled)

        from core.restore import run_restore
        device_override: str | None
        if self._device_rb_cpu.isChecked():
            device_override = "cpu"
        elif self._device_rb_cuda.isChecked():
            device_override = "cuda"
        else:
            device_override = None

        fidelity = self._fidelity_slider.value() / 100.0
        saturation = self._sat_slider.value() / 100.0
        style = self._style_combo.currentData() or "natural"
        size = int(self._size_combo.currentData() or 512)

        self._worker = Worker(
            run_restore,
            input_path,
            output_path,
            options,
            device=device_override,
            codeformer_weight=fidelity,
            colorize_saturation=saturation,
            colorize_style=style,
            colorize_size=size,
            heal_strength=self._heal_slider.value(),
            progress_cb=_progress_cb,
            cancelled_cb=_cancelled_cb,
        )
        self._worker.signals.progress.connect(self._on_progress)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _on_result(self, result: dict) -> None:
        self._set_busy(False)
        self._worker = None

        if not result.get("success"):
            self.status_message.emit(f"Failed: {result.get('error', 'unknown')}", True)
            return

        self._last_output_path = result["output_path"]
        stages_label = " + ".join(result.get("stages", []))
        self._result_lbl.setText(
            f"🖼 {tr('lbl_photo_restore_result')}: {os.path.basename(self._last_output_path)} "
            f"({stages_label})"
        )
        self._open_btn.setVisible(True)
        self._result_card.setVisible(True)

        get_history_manager().add_item(HistoryItem(
            task_type="photo_restore",
            file_name=os.path.basename(self._input_edit.text()),
            file_path=self._last_output_path,
            status="success",
        ))

        self.status_message.emit(
            f"Done [{result['device'].upper()}] → {os.path.basename(self._last_output_path)}", False
        )

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
