"""AI Transcript — offline whisper.cpp (CPU + NVIDIA CUDA), EN/AR + translate.

Two-stage install, both managed in this tab (no pip dependency):
  1. Backend = whisper.cpp prebuilt binary (CPU ~80 MB or CUDA ~600 MB)
     downloaded from the upstream GitHub release.
  2. One or more GGUF model files (~32 MB → 3 GB each) from HuggingFace.

Both live under %LOCALAPPDATA%/Videl/{whisper_bin,whisper_models}/.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from core.i18n import tr
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker


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


def _bg_download_backend(backend_id: str) -> str:
    from core.transcript import download_backend
    return download_backend(backend_id)


def _bg_download_model(model_id: str) -> str:
    from core.transcript import download_model
    return download_model(model_id)


class TranscriptSection(QScrollArea):
    """Local Whisper transcription -> SRT. Backend (CPU/CUDA) + model catalog."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._dl_worker: Worker | None = None

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_disclaimer_card())
        layout.addWidget(self._build_backend_card())
        layout.addWidget(self._build_model_card())
        layout.addWidget(self._build_source_card())
        layout.addWidget(self._build_options_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

        self.setWidget(content)
        self._refresh_backend_status()
        self._refresh_model_status()

    # ── Disclaimer banner ────────────────────────────────────────────────────
    def _build_disclaimer_card(self) -> QFrame:
        card = _card()
        card.setStyleSheet(
            "QFrame#Card { border: 1px solid rgba(245,158,11,0.4);"
            " background: rgba(245,158,11,0.06); border-radius: 10px; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        self._disclaimer_title = QLabel(tr("transcript_disclaimer_title"))
        self._disclaimer_title.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #F59E0B;"
        )
        layout.addWidget(self._disclaimer_title)

        self._disclaimer_body = QLabel(tr("transcript_disclaimer_body"))
        self._disclaimer_body.setObjectName("TextMuted")
        self._disclaimer_body.setWordWrap(True)
        self._disclaimer_body.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._disclaimer_body)
        return card

    # ── Backend card ─────────────────────────────────────────────────────────
    def _build_backend_card(self) -> QFrame:
        from core.transcript import BACKENDS, recommended_backend

        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._hdr_backend = _section_header(tr("hdr_whisper_backend"))
        layout.addWidget(self._hdr_backend)

        self._hint_backend = QLabel(tr("hint_whisper_backend"))
        self._hint_backend.setObjectName("TextMuted")
        self._hint_backend.setWordWrap(True)
        self._hint_backend.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint_backend)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._backend_combo = QComboBox()
        self._backend_combo.setMinimumWidth(360)
        rec = recommended_backend()
        for b in BACKENDS:
            label = b.label
            if b.id == rec:
                label += "  " + tr("install_variant_recommended")
            self._backend_combo.addItem(label, b.id)
            if b.id == rec:
                self._backend_combo.setCurrentIndex(self._backend_combo.count() - 1)
        self._backend_combo.currentIndexChanged.connect(self._refresh_backend_status)
        row.addWidget(self._backend_combo)

        self._backend_status_lbl = QLabel("")
        self._backend_status_lbl.setStyleSheet("font-size: 12px;")
        row.addWidget(self._backend_status_lbl)
        row.addStretch()

        self._backend_install_btn = QPushButton(tr("btn_install_backend"))
        self._backend_install_btn.setObjectName("PrimaryBtn")
        self._backend_install_btn.setFixedWidth(180)
        self._backend_install_btn.clicked.connect(self._download_selected_backend)
        row.addWidget(self._backend_install_btn)

        self._backend_delete_btn = QPushButton(tr("btn_delete"))
        self._backend_delete_btn.setObjectName("BrowseBtn")
        self._backend_delete_btn.setFixedWidth(100)
        self._backend_delete_btn.clicked.connect(self._delete_selected_backend)
        row.addWidget(self._backend_delete_btn)
        layout.addLayout(row)
        return card

    def _selected_backend_id(self) -> str:
        return self._backend_combo.currentData() or "cpu"

    def _refresh_backend_status(self) -> None:
        from core.transcript import is_backend_installed, BACKEND_BY_ID
        from utils.gpu_detect import detect as _gpu_detect
        bid = self._selected_backend_id()
        b = BACKEND_BY_ID[bid]
        installed = is_backend_installed(bid)
        if installed:
            self._backend_status_lbl.setText(tr("lbl_installed"))
            self._backend_status_lbl.setStyleSheet("font-size: 12px; color: #22C55E;")
            self._backend_install_btn.setEnabled(False)
            self._backend_install_btn.setText(tr("btn_installed"))
            self._backend_delete_btn.setEnabled(True)
        else:
            if b.requires_nvidia and _gpu_detect() != "cuda":
                self._backend_status_lbl.setText(tr("lbl_backend_no_nvidia"))
                self._backend_status_lbl.setStyleSheet("font-size: 12px; color: #EF4444;")
                self._backend_install_btn.setEnabled(False)
            else:
                self._backend_status_lbl.setText(tr("lbl_backend_not_installed"))
                self._backend_status_lbl.setStyleSheet("font-size: 12px; color: #F59E0B;")
                self._backend_install_btn.setEnabled(True)
            self._backend_install_btn.setText(tr("btn_install_backend"))
            self._backend_delete_btn.setEnabled(False)

    def _download_selected_backend(self) -> None:
        if self._dl_worker and self._dl_worker.isRunning():
            return
        bid = self._selected_backend_id()
        self._backend_install_btn.setEnabled(False)
        self._set_busy(True, tr("status_downloading_backend").format(backend=bid))
        self._dl_worker = Worker(_bg_download_backend, bid)
        self._dl_worker.signals.result.connect(self._on_backend_done)
        self._dl_worker.signals.error.connect(self._on_dl_error)
        self._dl_worker.start()

    def _on_backend_done(self, _path: str) -> None:
        self._set_busy(False)
        self._dl_worker = None
        self.status_message.emit(tr("status_backend_installed"), False)
        self._refresh_backend_status()

    def _delete_selected_backend(self) -> None:
        from core.transcript import delete_backend, BACKEND_BY_ID
        bid = self._selected_backend_id()
        confirm = QMessageBox.question(
            self,
            tr("confirm_delete_backend_title"),
            tr("confirm_delete_backend_body").format(name=BACKEND_BY_ID[bid].label),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        delete_backend(bid)
        self.status_message.emit(tr("status_backend_deleted"), False)
        self._refresh_backend_status()

    # ── Model card ───────────────────────────────────────────────────────────
    def _build_model_card(self) -> QFrame:
        from core.transcript import MODELS, DEFAULT_MODEL_ID

        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_model = _section_header(tr("hdr_whisper_model"))
        layout.addWidget(self._hdr_model)

        self._hint_model = QLabel(tr("hint_whisper_model"))
        self._hint_model.setObjectName("TextMuted")
        self._hint_model.setWordWrap(True)
        self._hint_model.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint_model)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._model_combo = QComboBox()
        self._model_combo.setMinimumWidth(320)
        default_idx = 0
        for i, m in enumerate(MODELS):
            self._model_combo.addItem(m.label, m.id)
            if m.id == DEFAULT_MODEL_ID:
                default_idx = i
        self._model_combo.setCurrentIndex(default_idx)
        self._model_combo.currentIndexChanged.connect(self._refresh_model_status)
        row.addWidget(self._model_combo)

        self._model_status_lbl = QLabel("")
        self._model_status_lbl.setStyleSheet("font-size: 12px;")
        row.addWidget(self._model_status_lbl)
        row.addStretch()

        self._model_install_btn = QPushButton(tr("btn_install_selected_model"))
        self._model_install_btn.setObjectName("PrimaryBtn")
        self._model_install_btn.setFixedWidth(180)
        self._model_install_btn.clicked.connect(self._download_selected_model)
        row.addWidget(self._model_install_btn)

        self._model_delete_btn = QPushButton(tr("btn_delete"))
        self._model_delete_btn.setObjectName("BrowseBtn")
        self._model_delete_btn.setFixedWidth(100)
        self._model_delete_btn.clicked.connect(self._delete_selected_model)
        row.addWidget(self._model_delete_btn)
        layout.addLayout(row)
        return card

    def _selected_model_id(self) -> str:
        return self._model_combo.currentData() or "medium-q5_0"

    def _refresh_model_status(self) -> None:
        from core.transcript import is_model_downloaded
        mid = self._selected_model_id()
        installed = is_model_downloaded(mid)
        if installed:
            self._model_status_lbl.setText(tr("lbl_installed"))
            self._model_status_lbl.setStyleSheet("font-size: 12px; color: #22C55E;")
            self._model_install_btn.setEnabled(False)
            self._model_install_btn.setText(tr("btn_installed"))
            self._model_delete_btn.setEnabled(True)
        else:
            self._model_status_lbl.setText(tr("lbl_model_not_downloaded"))
            self._model_status_lbl.setStyleSheet("font-size: 12px; color: #F59E0B;")
            self._model_install_btn.setEnabled(True)
            self._model_install_btn.setText(tr("btn_install_selected_model"))
            self._model_delete_btn.setEnabled(False)

    def _download_selected_model(self) -> None:
        if self._dl_worker and self._dl_worker.isRunning():
            return
        mid = self._selected_model_id()
        self._model_install_btn.setEnabled(False)
        self._set_busy(True, tr("status_downloading_model").format(model=mid))
        self._dl_worker = Worker(_bg_download_model, mid)
        self._dl_worker.signals.result.connect(self._on_model_done)
        self._dl_worker.signals.error.connect(self._on_dl_error)
        self._dl_worker.start()

    def _on_model_done(self, _path: str) -> None:
        self._set_busy(False)
        self._dl_worker = None
        self.status_message.emit(tr("status_model_downloaded"), False)
        self._refresh_model_status()

    def _on_dl_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._dl_worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Download failed: {msg}", True)
        self._refresh_backend_status()
        self._refresh_model_status()

    def _delete_selected_model(self) -> None:
        from core.transcript import delete_model, MODEL_BY_ID
        mid = self._selected_model_id()
        m = MODEL_BY_ID[mid]
        confirm = QMessageBox.question(
            self,
            tr("confirm_delete_model_title"),
            tr("confirm_delete_model_body").format(name=m.label, size_mb=m.size_mb),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        delete_model(mid)
        self.status_message.emit(tr("status_model_deleted").format(name=m.label), False)
        self._refresh_model_status()

    # ── Source card ──────────────────────────────────────────────────────────
    def _build_source_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_src = _section_header(tr("hdr_source_media"))
        layout.addWidget(self._hdr_src)

        row = QHBoxLayout()
        self._input_edit = QLineEdit()
        self._input_edit.setObjectName("PillInput")
        self._input_edit.setPlaceholderText(tr("ph_audio_or_video"))
        row.addWidget(self._input_edit)

        self._browse_btn = QPushButton(tr("btn_browse"))
        self._browse_btn.setObjectName("BrowseBtn")
        self._browse_btn.setFixedWidth(90)
        self._browse_btn.clicked.connect(self._browse_input)
        row.addWidget(self._browse_btn)
        layout.addLayout(row)
        return card

    # ── Options card ─────────────────────────────────────────────────────────
    def _build_options_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_opts = _section_header(tr("hdr_transcript_options"))
        layout.addWidget(self._hdr_opts)

        row = QHBoxLayout()
        row.setSpacing(12)
        self._lbl_lang = QLabel(tr("lbl_language"))
        row.addWidget(self._lbl_lang)
        self._lang_combo = QComboBox()
        self._lang_combo.addItem(tr("lang_auto_detect"), "auto")
        self._lang_combo.addItem("English", "en")
        self._lang_combo.setFixedWidth(160)
        row.addWidget(self._lang_combo)
        row.addStretch()
        layout.addLayout(row)
        return card

    # ── Output card ──────────────────────────────────────────────────────────
    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_out = _section_header(tr("hdr_output_file"))
        layout.addWidget(self._hdr_out)
        self._hint_out = QLabel(tr("hint_save_alongside"))
        self._hint_out.setObjectName("TextMuted")
        self._hint_out.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint_out)

        row = QHBoxLayout()
        self._output_edit = QLineEdit()
        self._output_edit.setObjectName("PillInput")
        self._output_edit.setPlaceholderText(tr("ph_srt_auto"))
        row.addWidget(self._output_edit)

        self._browse_out_btn = QPushButton(tr("btn_browse"))
        self._browse_out_btn.setObjectName("BrowseBtn")
        self._browse_out_btn.setFixedWidth(90)
        self._browse_out_btn.clicked.connect(self._browse_output)
        row.addWidget(self._browse_out_btn)
        layout.addLayout(row)
        return card

    # ── Progress ────────────────────────────────────────────────────────────
    def _build_progress_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("TaskProgressBar")
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setVisible(False)
        self._progress_bar.setTextVisible(True)
        layout.addWidget(self._progress_bar)
        self._result_label = QLabel()
        self._result_label.setObjectName("TextSecondary")
        self._result_label.setWordWrap(True)
        self._result_label.setVisible(False)
        layout.addWidget(self._result_label)
        return card

    # ── Browse / retranslate ────────────────────────────────────────────────
    def _browse_input(self) -> None:
        from core.transcript import INPUT_EXTS
        ext_filter = "Audio/Video (" + " ".join(f"*{e}" for e in sorted(INPUT_EXTS)) + ")"
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Audio or Video", os.path.expanduser("~"), ext_filter
        )
        if path:
            self._input_edit.setText(path)

    def _browse_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save SRT", os.path.expanduser("~"), "SubRip subtitle (*.srt)"
        )
        if path:
            if not path.lower().endswith(".srt"):
                path += ".srt"
            self._output_edit.setText(path)

    def populate_file(self, path: str) -> None:
        self._input_edit.setText(path)

    def retranslate_ui(self) -> None:
        self._disclaimer_title.setText(tr("transcript_disclaimer_title"))
        self._disclaimer_body.setText(tr("transcript_disclaimer_body"))
        self._hdr_backend.setText(tr("hdr_whisper_backend"))
        self._hint_backend.setText(tr("hint_whisper_backend"))
        self._backend_delete_btn.setText(tr("btn_delete"))
        self._refresh_backend_status()
        self._hdr_model.setText(tr("hdr_whisper_model"))
        self._hint_model.setText(tr("hint_whisper_model"))
        self._model_delete_btn.setText(tr("btn_delete"))
        self._refresh_model_status()
        self._hdr_src.setText(tr("hdr_source_media"))
        self._input_edit.setPlaceholderText(tr("ph_audio_or_video"))
        self._browse_btn.setText(tr("btn_browse"))
        self._hdr_opts.setText(tr("hdr_transcript_options"))
        self._lbl_lang.setText(tr("lbl_language"))
        self._lang_combo.setItemText(0, tr("lang_auto_detect"))
        self._hdr_out.setText(tr("hdr_output_file"))
        self._hint_out.setText(tr("hint_save_alongside"))
        self._output_edit.setPlaceholderText(tr("ph_srt_auto"))
        self._browse_out_btn.setText(tr("btn_browse"))

    def _set_busy(self, busy: bool, msg: str = "") -> None:
        self._progress_bar.setVisible(busy)
        if busy and msg:
            self.status_message.emit(msg, False)
        self.busy_changed.emit(busy)

    # ── Primary action ──────────────────────────────────────────────────────
    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        from core.transcript import (
            is_backend_installed, is_model_downloaded, BACKEND_BY_ID, MODEL_BY_ID,
        )
        input_path = self._input_edit.text().strip()
        if not input_path or not os.path.isfile(input_path):
            self.status_message.emit("Select a valid audio/video file.", True)
            return

        backend_id = self._selected_backend_id()
        model_id = self._selected_model_id()
        if not is_backend_installed(backend_id):
            self.status_message.emit(
                f"Install the {BACKEND_BY_ID[backend_id].label} backend first.", True
            )
            return
        if not is_model_downloaded(model_id):
            self.status_message.emit(
                f"Install the {MODEL_BY_ID[model_id].label} model first.", True
            )
            return

        language = self._lang_combo.currentData() or "auto"
        translate = False
        output_path = self._output_edit.text().strip() or None

        self._result_label.setVisible(False)
        self._set_busy(True, "Transcribing…")

        from core.transcript import transcribe
        worker = Worker(
            transcribe, input_path,
            backend_id=backend_id, model_id=model_id,
            language=language, translate=translate,
            output_path=output_path,
        )

        # Thread-safe progress relay: the worker thread calls _progress_cb,
        # which emits a Qt signal — auto-queued onto the GUI thread.
        def _progress_cb(done: int, total: int) -> None:
            worker.signals.progress.emit(done, total, "")
        worker.kwargs["progress_cb"] = _progress_cb

        worker.signals.progress.connect(self._on_progress)
        worker.signals.result.connect(self._on_result)
        worker.signals.error.connect(self._on_error)

        # Reset progress bar to indeterminate until first % arrives.
        self._progress_bar.setRange(0, 0)

        self._worker = worker
        worker.start()

    def _on_progress(self, done: int, total: int, _msg: str) -> None:
        if total <= 0:
            self._progress_bar.setRange(0, 0)
            return
        if self._progress_bar.maximum() != total:
            self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(done)

    def _on_result(self, result) -> None:
        self._set_busy(False)
        _old = self._worker
        self._worker = None
        if _old is not None:
            _old.wait(5000)
        out = result.output_path
        self._result_label.setText(
            f"Saved → {out}   ({result.segment_count} segments, "
            f"lang={result.language}, model={result.model_id}, backend={result.backend_id})"
        )
        self._result_label.setVisible(True)
        self.status_message.emit(f"Done → {os.path.basename(out)}", False)
        get_history_manager().add_item(HistoryItem(
            task_type="transcript",
            file_name=os.path.basename(out),
            file_path=out,
            status="success",
        ))
        self._refresh_model_status()

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        _old = self._worker
        self._worker = None
        if _old is not None:
            _old.wait(5000)
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
