"""AI Background Eraser — offline rembg-powered background removal."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QProgressBar, QPushButton,
    QScrollArea, QTextEdit, QVBoxLayout, QWidget,
)

from core.i18n import tr
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker
from utils.model_manager import is_rembg_installed, install_rembg


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
        self._install_worker: Worker | None = None

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

        self._install_btn = QPushButton(tr("btn_install_model"))
        self._install_btn.setObjectName("PrimaryBtn")
        self._install_btn.setFixedWidth(160)
        self._install_btn.clicked.connect(self._start_install)
        layout.addWidget(self._install_btn)

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
        installed = is_rembg_installed()
        self._install_banner.setVisible(not installed)
        self._tools_container.setVisible(installed)

    def _start_install(self) -> None:
        self._install_btn.setEnabled(False)
        self._install_status.setText(tr("lbl_model_installing"))
        self._install_status.setVisible(True)
        self._install_log.setVisible(True)
        self._install_log.clear()

        def _log_cb(line: str) -> None:
            if self._install_worker:
                self._install_worker.signals.progress.emit(0, 100, line)

        self._install_worker = Worker(install_rembg, _log_cb)
        self._install_worker.signals.progress.connect(self._on_install_log)
        self._install_worker.signals.result.connect(self._on_install_done)
        self._install_worker.signals.error.connect(self._on_install_error)
        self._install_worker.start()

    def _on_install_log(self, _v: int, _t: int, line: str) -> None:
        if line:
            self._install_log.append(line)

    def _on_install_done(self, _result) -> None:
        self._install_worker = None
        self._install_status.setStyleSheet("font-size: 12px; color: #22C55E;")
        self._install_status.setText(tr("lbl_model_install_done"))
        self._install_btn.setEnabled(True)
        # Reload the module so imports work without restart
        try:
            from core import bg_eraser as _be
            import importlib
            importlib.reload(_be)
        except Exception:
            pass
        self._refresh_install_state()

    def _on_install_error(self, err_tuple: tuple) -> None:
        self._install_worker = None
        _, msg, _ = err_tuple
        self._install_status.setStyleSheet("font-size: 12px; color: #EF4444;")
        self._install_status.setText(tr("lbl_model_install_failed").format(error=msg))
        self._install_btn.setEnabled(True)

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

        # Input preview thumbnail
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


    def _set_input_preview_placeholder(self, key: str) -> None:
        self._preview_placeholder_key = key
        self._input_preview.setPixmap(QPixmap())
        self._input_preview.setText(tr(key))

    def retranslate_ui(self) -> None:
        self._install_title.setText(f"⚠  {tr('lbl_model_not_installed')}")
        self._install_desc.setText(tr("lbl_model_rembg_desc"))
        self._install_btn.setText(tr("btn_install_model"))
        self._hdr_src.setText(tr("hdr_source_img"))
        self._hint_src.setText(tr("hint_bg_source_formats"))
        self._input_edit.setPlaceholderText(tr("ph_img"))
        self._browse_in_btn.setText(tr("btn_browse"))
        if self._preview_placeholder_key:
            self._input_preview.setText(tr(self._preview_placeholder_key))
        self._hdr_out.setText(tr("hdr_output_file"))
        self._output_edit.setPlaceholderText(tr("ph_nobg_auto"))
        self._browse_out_btn.setText(tr("btn_browse"))
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
            self._output_edit.setPlaceholderText(f"{stem}_nobg.png")

    def _load_input_preview(self) -> None:
        path = self._input_edit.text().strip()
        if not path or not os.path.isfile(path):
            self._set_input_preview_placeholder("hint_bg_no_preview")
            return
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

        self._result_card.setVisible(False)
        self._set_busy(True, "Removing background (first run downloads ~170 MB model)…")

        from core.bg_eraser import remove_background
        self._worker = Worker(remove_background, input_path, output_path)
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
            task_type="bg_erase",
            file_name=os.path.basename(self._input_edit.text()),
            file_path=out_path,
            status="success",
        ))

        self.status_message.emit(f"Done → {os.path.basename(out_path)}", False)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
