"""AI Vocal Isolator — HTDemucs 2-stem separation tab."""
from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QProgressBar,
    QPushButton, QRadioButton, QScrollArea,
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


# Preset → (model_name, extra_flags, label_key)
_PRESETS = {
    "fast":     ("htdemucs",    ["--no-split"],  "preset_fast"),
    "balanced": ("htdemucs",    [],              "preset_balanced"),
    "quality":  ("htdemucs_ft", [],              "preset_quality"),
}


class VocalIsolatorSection(QScrollArea):
    """2-stem AI vocal separator powered by HTDemucs (fully offline after first run)."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_output_dir: str | None = None
        self._install_proc = None
        self._install_tail: list[str] = []
        self._component_id = "vocal_isolator"

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
        tools_layout.addWidget(self._build_options_card())
        tools_layout.addWidget(self._build_device_card())
        tools_layout.addWidget(self._build_progress_card())
        tools_layout.addWidget(self._build_result_card())
        layout.addWidget(self._tools_container)

        self.setWidget(content)
        self._refresh_install_state()

        # Detect device lazily — avoids torch import blocking startup
        QTimer.singleShot(0, self._detect_device_async)

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

        self._install_desc = QLabel(tr("lbl_model_demucs_desc"))
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
            supported, reason_key = model_manager.variant_compatibility(
                self._component_id, variant
            )
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

        # If recommended was unavailable, fall back to first enabled radio.
        if not any(rb.isChecked() for rb in self._variant_radios):
            for rb in self._variant_radios:
                if rb.isEnabled():
                    rb.setChecked(True)
                    break

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
            self._render_install_error(
                tr("install_error_generic").format(error=str(exc))
            )
            return

        self._install_proc.finished.connect(self._on_install_finished)

    def _on_install_line(self, line: str) -> None:
        import re as _re
        # Detect pip's progress-bar refresh lines (e.g. "  35%|███| 1.2/3.5 GB ...")
        # and surface them as a live status label instead of flooding the log.
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
            # Re-probe device — initial probe ran before files existed.
            self._detect_device_async()
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

        self._hdr_src = _section_header(tr("hdr_source_file"))
        layout.addWidget(self._hdr_src)

        self._hint_src = QLabel(tr("hint_vocal_source_formats"))
        self._hint_src.setObjectName("TextMuted")
        self._hint_src.setWordWrap(True)
        self._hint_src.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint_src)

        row = QHBoxLayout()
        self._input_edit = QLineEdit()
        self._input_edit.setObjectName("PillInput")
        self._input_edit.setPlaceholderText(tr("ph_vid_aud"))
        row.addWidget(self._input_edit)

        self._browse_in_btn = QPushButton(tr("btn_browse"))
        self._browse_in_btn.setObjectName("BrowseBtn")
        self._browse_in_btn.setFixedWidth(90)
        self._browse_in_btn.clicked.connect(self._browse_input)
        row.addWidget(self._browse_in_btn)
        layout.addLayout(row)
        return card

    # ── Output folder card ────────────────────────────────────────────────────

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._hdr_out = _section_header(tr("hdr_output_folder"))
        layout.addWidget(self._hdr_out)

        row = QHBoxLayout()
        self._output_edit = QLineEdit()
        self._output_edit.setObjectName("PillInput")
        self._output_edit.setPlaceholderText(tr("ph_same_dir"))
        row.addWidget(self._output_edit)

        self._browse_out_btn = QPushButton(tr("btn_browse"))
        self._browse_out_btn.setObjectName("BrowseBtn")
        self._browse_out_btn.setFixedWidth(90)
        self._browse_out_btn.clicked.connect(self._browse_output)
        row.addWidget(self._browse_out_btn)
        layout.addLayout(row)
        return card

    # ── Options card (format + preset) ───────────────────────────────────────

    def _build_options_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        # Output format
        self._hdr_fmt = _section_header(tr("hdr_vocal_output_format"))
        layout.addWidget(self._hdr_fmt)

        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(12)
        self._fmt_group = QButtonGroup(self)
        for i, fmt in enumerate(("WAV", "MP3", "FLAC")):
            rb = QRadioButton(fmt)
            rb.setStyleSheet("font-size: 13px;")
            self._fmt_group.addButton(rb, i)
            fmt_row.addWidget(rb)
            if fmt == "WAV":
                rb.setChecked(True)
        fmt_row.addStretch()
        layout.addLayout(fmt_row)

        # Preset
        self._hdr_preset = _section_header(tr("hdr_vocal_preset"))
        layout.addWidget(self._hdr_preset)

        self._preset_combo = QComboBox()
        self._preset_combo.setObjectName("PillInput")
        self._preset_combo.addItem(tr("preset_fast"),     "fast")
        self._preset_combo.addItem(tr("preset_balanced"), "balanced")
        self._preset_combo.addItem(tr("preset_quality"),  "quality")
        self._preset_combo.setCurrentIndex(1)  # balanced default

        preset_hint = QLabel(tr("hint_vocal_preset"))
        preset_hint.setObjectName("TextMuted")
        preset_hint.setWordWrap(True)
        preset_hint.setStyleSheet("font-size: 11px;")
        self._preset_hint = preset_hint

        layout.addWidget(self._preset_combo)
        layout.addWidget(preset_hint)
        return card

    # ── Device / CPU warning card ─────────────────────────────────────────────

    def _build_device_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(6)

        # Placeholder while detection runs in background
        self._device_lbl = QLabel(f"⚡ {tr('lbl_vocal_device')}: …")
        self._device_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._device_lbl.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._device_lbl)

        # Device override radios — populated after detect/install state known.
        self._device_group = QButtonGroup(self)
        self._device_radio_row = QHBoxLayout()
        self._device_radio_row.setSpacing(12)
        self._device_rb_auto = QRadioButton("Auto")
        self._device_rb_cpu = QRadioButton("CPU")
        self._device_rb_cuda = QRadioButton("GPU (CUDA)")
        for rb in (self._device_rb_auto, self._device_rb_cpu, self._device_rb_cuda):
            rb.setStyleSheet("font-size: 12px;")
            self._device_group.addButton(rb)
            self._device_radio_row.addWidget(rb)
        self._device_radio_row.addStretch()
        self._device_rb_auto.setChecked(True)
        layout.addLayout(self._device_radio_row)

        self._warn_lbl = QLabel(f"⚠ {tr('warn_vocal_cpu_time')}")
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
        """Run torch device detection in a Worker so it never blocks the UI."""
        def _do_detect():
            try:
                from core.vocal_isolator import detect_device, last_detect_debug
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
        # If the user installed the CUDA variant but we still report CPU, surface
        # the probe diagnostic inline so it's not silently swallowed.
        if device == "cpu" and debug:
            try:
                from utils import model_manager as _mm
                if _mm.read_state("vocal_isolator").variant == "cuda":
                    self._warn_lbl.setText(f"⚠ CUDA variant installed but probe → CPU.\n{debug}")
                    self._warn_lbl.setVisible(True)
            except Exception:
                pass
        self._detected_device = device
        # CUDA radio enabled only when the installed variant is "cuda" AND probe
        # found a usable kernel — otherwise selecting it would just crash.
        cuda_usable = device == "cuda"
        try:
            from utils import model_manager as _mm
            cuda_installed = _mm.read_state("vocal_isolator").variant == "cuda"
        except Exception:
            cuda_installed = False
        self._device_rb_cuda.setEnabled(cuda_usable and cuda_installed)
        if not (cuda_usable and cuda_installed):
            self._device_rb_cuda.setToolTip(
                "CUDA variant not installed or your GPU is not supported by the bundled torch build."
            )

    # ── Progress card ─────────────────────────────────────────────────────────

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

    # ── Result card ───────────────────────────────────────────────────────────

    def _build_result_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        self._hdr_result = _section_header(tr("hdr_result"))
        layout.addWidget(self._hdr_result)

        self._vocals_lbl = QLabel("")
        self._vocals_lbl.setWordWrap(True)
        self._vocals_lbl.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._vocals_lbl)

        self._accomp_lbl = QLabel("")
        self._accomp_lbl.setWordWrap(True)
        self._accomp_lbl.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._accomp_lbl)

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

    # ── Helpers ───────────────────────────────────────────────────────────────

    def retranslate_ui(self) -> None:
        self._install_title.setText(f"⚠  {tr('lbl_model_not_installed')}")
        self._install_desc.setText(tr("lbl_model_demucs_desc"))
        self._install_btn.setText(tr("btn_install_model"))
        self._retry_btn.setText(tr("install_retry_button"))
        self._confirm_btn.setText(tr("install_confirm_button"))
        self._cancel_btn.setText(tr("install_cancel_button"))
        self._variant_label.setText(tr("install_variant_choose"))
        self._hdr_src.setText(tr("hdr_source_file"))
        self._hint_src.setText(tr("hint_vocal_source_formats"))
        self._input_edit.setPlaceholderText(tr("ph_vid_aud"))
        self._browse_in_btn.setText(tr("btn_browse"))
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._output_edit.setPlaceholderText(tr("ph_same_dir"))
        self._browse_out_btn.setText(tr("btn_browse"))
        self._hdr_fmt.setText(tr("hdr_vocal_output_format"))
        self._hdr_preset.setText(tr("hdr_vocal_preset"))
        self._preset_hint.setText(tr("hint_vocal_preset"))
        self._preset_combo.setItemText(0, tr("preset_fast"))
        self._preset_combo.setItemText(1, tr("preset_balanced"))
        self._preset_combo.setItemText(2, tr("preset_quality"))
        self._warn_lbl.setText(f"⚠ {tr('warn_vocal_cpu_time')}")
        self._hdr_result.setText(tr("hdr_result"))
        self._open_btn.setText(tr("btn_open_explorer"))

    def _selected_format(self) -> str:
        btn = self._fmt_group.checkedButton()
        return btn.text().lower() if btn else "wav"

    def _selected_preset(self) -> str:
        return self._preset_combo.currentData() or "balanced"

    def _browse_input(self) -> None:
        try:
            from core.vocal_isolator import SUPPORTED_EXTS as _SE
        except ImportError:
            _SE = {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".mp4", ".mkv"}
        exts = " ".join(f"*{e}" for e in sorted(_SE))
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Audio / Video File",
            os.path.expanduser("~"),
            f"Audio/Video ({exts})",
        )
        if path:
            self._input_edit.setText(path)

    def _browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", os.path.expanduser("~")
        )
        if folder:
            self._output_edit.setText(folder)

    def populate_file(self, path: str) -> None:
        self._input_edit.setText(path)

    def _set_busy(self, busy: bool, msg: str = "") -> None:
        self._progress_bar.setVisible(busy)
        self._progress_lbl.setVisible(busy)
        if busy:
            self._progress_bar.setValue(0)
            if msg:
                self.status_message.emit(msg, False)
        self.busy_changed.emit(busy)

    def _on_progress(self, value: int, _total: int, _label: str) -> None:
        self._progress_bar.setValue(value)
        self._progress_lbl.setText(f"{value}%")

    def _open_output_folder(self) -> None:
        if self._last_output_dir and os.path.isdir(self._last_output_dir):
            if sys.platform == "win32":
                subprocess.Popen(["explorer", os.path.normpath(self._last_output_dir)])
            else:
                from PySide6.QtGui import QDesktopServices
                from PySide6.QtCore import QUrl
                QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_output_dir))

    # ── Primary action ────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        input_path = self._input_edit.text().strip()
        if not input_path or not os.path.isfile(input_path):
            self.status_message.emit(tr("err_vocal_no_input"), True)
            return

        output_dir = self._output_edit.text().strip()
        if not output_dir:
            output_dir = os.path.dirname(input_path)

        fmt = self._selected_format()
        preset = self._selected_preset()

        self._result_card.setVisible(False)
        self._set_busy(True, tr("dyn_vocal_processing"))

        def _progress_cb(pct: int) -> None:
            if self._worker:
                self._worker.signals.progress.emit(pct, 100, "")

        def _cancelled_cb() -> bool:
            return bool(self._worker and self._worker.is_cancelled)

        from core.vocal_isolator import separate_vocals
        device_override: str | None
        if self._device_rb_cpu.isChecked():
            device_override = "cpu"
        elif self._device_rb_cuda.isChecked():
            device_override = "cuda"
        else:
            device_override = None  # auto-detect
        self._worker = Worker(
            separate_vocals,
            input_path,
            output_dir,
            fmt,
            preset,
            _progress_cb,
            _cancelled_cb,
            device_override,
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

        self._last_output_dir = result["output_dir"]
        vocals = result["vocals_path"]
        accomp = result["accompaniment_path"]

        self._vocals_lbl.setText(f"🎤 {tr('lbl_vocal_vocals')}: {os.path.basename(vocals)}")
        self._accomp_lbl.setText(f"🎵 {tr('lbl_vocal_accompaniment')}: {os.path.basename(accomp)}")
        self._open_btn.setVisible(True)
        self._result_card.setVisible(True)

        get_history_manager().add_item(HistoryItem(
            task_type="vocal_isolate",
            file_name=os.path.basename(self._input_edit.text()),
            file_path=vocals,
            status="success",
        ))

        self.status_message.emit(
            f"Done [{result['device'].upper()}] → {os.path.basename(vocals)}", False
        )

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
