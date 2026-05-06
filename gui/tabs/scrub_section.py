"""Metadata Scrubber tab — batch strip GPS, timestamps, and EXIF via FFmpeg stream copy."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.scrubber import scrub_batch, _SUPPORTED_EXTS
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


class ScrubSection(QScrollArea):
    """Strip all metadata from a batch of media files (stream copy, no re-encode)."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_result_path: str | None = None

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAcceptDrops(True)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_files_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())
        self.setWidget(content)

    # ── File list card ────────────────────────────────────────────────────────

    def _build_files_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_files = _section_header(tr("hdr_files_queue"))
        layout.addWidget(self._hdr_files)

        self._hint_intro = QLabel(tr("hint_scrub_intro"))
        self._hint_intro.setObjectName("TextMuted")
        self._hint_intro.setWordWrap(True)
        self._hint_intro.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint_intro)

        self._file_list = QListWidget()
        self._file_list.setObjectName("FileList")
        self._file_list.setFixedHeight(200)
        self._file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._file_list.setAcceptDrops(False)
        layout.addWidget(self._file_list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._add_files_btn = QPushButton(tr("btn_add_files"))
        self._add_files_btn.setObjectName("BrowseBtn")
        self._add_files_btn.clicked.connect(self._browse_add_files)
        btn_row.addWidget(self._add_files_btn)

        self._add_dir_btn = QPushButton(tr("btn_add_folder"))
        self._add_dir_btn.setObjectName("BrowseBtn")
        self._add_dir_btn.clicked.connect(self._browse_add_folder)
        btn_row.addWidget(self._add_dir_btn)

        self._remove_btn = QPushButton(tr("btn_remove_selected"))
        self._remove_btn.setObjectName("BrowseBtn")
        self._remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(self._remove_btn)

        self._clear_btn = QPushButton(tr("btn_clear_all"))
        self._clear_btn.setObjectName("BrowseBtn")
        self._clear_btn.clicked.connect(self._file_list.clear)
        btn_row.addWidget(self._clear_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._count_label = QLabel("0 files queued")
        self._count_label.setObjectName("TextMuted")
        self._count_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._count_label)

        self._file_list.model().rowsInserted.connect(self._update_count)
        self._file_list.model().rowsRemoved.connect(self._update_count)

        return card

    # ── Output card ───────────────────────────────────────────────────────────

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_out = _section_header(tr("hdr_output_folder"))
        layout.addWidget(self._hdr_out)

        self._hint_out = QLabel(tr("hint_scrub_output"))
        self._hint_out.setObjectName("TextMuted")
        self._hint_out.setWordWrap(True)
        self._hint_out.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._hint_out)

        row = QHBoxLayout()
        self._out_input = QLineEdit()
        self._out_input.setObjectName("PillInput")
        self._out_input.setPlaceholderText(tr("ph_each_source"))
        if self._settings.output_folder:
            self._out_input.setText(self._settings.output_folder)
        row.addWidget(self._out_input)

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
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._progress_label = QLabel()
        self._progress_label.setObjectName("TextSecondary")
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)
        return card

    # ── File management ───────────────────────────────────────────────────────

    def _browse_add_files(self) -> None:
        ext_filter = "Media files (" + " ".join(f"*{e}" for e in sorted(_SUPPORTED_EXTS)) + ")"
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Media Files", os.path.expanduser("~"), ext_filter
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
            if os.path.splitext(f)[1].lower() in _SUPPORTED_EXTS
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


    def retranslate_ui(self) -> None:
        self._hdr_files.setText(tr("hdr_files_queue"))
        self._hint_intro.setText(tr("hint_scrub_intro"))
        self._add_files_btn.setText(tr("btn_add_files"))
        self._add_dir_btn.setText(tr("btn_add_folder"))
        self._remove_btn.setText(tr("btn_remove_selected"))
        self._clear_btn.setText(tr("btn_clear_all"))
        self._update_count()
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._hint_out.setText(tr("hint_scrub_output"))
        self._out_input.setPlaceholderText(tr("ph_each_source"))
        self._browse_out_btn.setText(tr("btn_browse"))

    def _browse_output(self) -> None:
        start = self._out_input.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if d:
            self._out_input.setText(d)

    # ── Drag and drop ─────────────────────────────────────────────────────────

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile()
            and os.path.splitext(url.toLocalFile())[1].lower() in _SUPPORTED_EXTS
        ]
        if paths:
            self._add_paths(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def populate_files(self, paths: list[str]) -> None:
        """Called by DnD handler in MainWindow."""
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
            self.status_message.emit("Add at least one file to scrub.", True)
            return

        out_dir = self._out_input.text().strip() or None

        self._progress_bar.setRange(0, len(paths))
        self._progress_bar.setValue(0)
        self._set_busy(True, f"Scrubbing {len(paths)} file(s)…", f"Processing…")

        def _do():
            def _prog(done, _total):
                pass
            return scrub_batch(paths, out_dir, progress_cb=_prog)

        self._pending_paths = paths
        self._worker = Worker(_do)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

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
        if fail == 0:
            self.status_message.emit(f"Done → {ok} file(s) scrubbed.", False)
            for path, success in results.items():
                if success:
                    base = os.path.splitext(os.path.basename(path))[0]
                    ext = os.path.splitext(path)[1]
                    out_path = path  # approximate; exact dir depends on settings
                    get_history_manager().add_item(HistoryItem(
                        task_type="scrub",
                        file_name=f"{base}_clean{ext}",
                        file_path=out_path,
                        status="success",
                    ))
        else:
            self.status_message.emit(
                f"Complete — {ok} succeeded, {fail} failed.", fail == len(results)
            )

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
