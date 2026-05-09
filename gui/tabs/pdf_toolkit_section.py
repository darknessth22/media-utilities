"""PDF Toolkit tab — Compress, Merge, Split, and Image Extraction."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
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
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker
from utils import model_manager
from utils.install_errors import classify as classify_install_error
from utils.model_manager import InsufficientDiskError


_PDF_FILTER = "PDF Files (*.pdf)"

_QUALITY_PRESETS = [
    ("pdf_quality_screen", 72),
    ("pdf_quality_web", 150),
    ("pdf_quality_print", 300),
]

_MODES = [
    "pdf_mode_compress",
    "pdf_mode_merge",
    "pdf_mode_split",
    "pdf_mode_extract",
    "pdf_mode_ocr",
]

# UI lang code -> display key. Keep in sync with core/ocr.py language maps.
_OCR_LANG_OPTIONS = [
    ("en", "ocr_lang_en"),
    ("ar", "ocr_lang_ar"),
    ("ch", "ocr_lang_ch"),
    ("ja", "ocr_lang_ja"),
    ("ko", "ocr_lang_ko"),
    ("en+ar", "ocr_lang_en_ar"),
    ("en+fr", "ocr_lang_en_fr"),
    ("en+es", "ocr_lang_en_es"),
]
# Per-engine subset (RapidOCR has fewer combinations).
_OCR_LANGS_RAPID = {"en", "ch", "ja", "ko"}


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


def _file_row(placeholder: str, parent: QWidget):
    row = QHBoxLayout()
    inp = QLineEdit()
    inp.setObjectName("PillInput")
    inp.setPlaceholderText(placeholder)
    row.addWidget(inp)
    btn = QPushButton(tr("btn_browse"))
    btn.setObjectName("BrowseBtn")
    btn.setFixedWidth(90)
    row.addWidget(btn)
    return inp, btn, row


class _CompressPane(QWidget):
    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._selected_dpi = 150

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._build_source_card())
        layout.addWidget(self._build_quality_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

    def _build_source_card(self):
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        self._hdr_src = _hdr(tr("hdr_source_pdf"))
        v.addWidget(self._hdr_src)
        self._src_inp, self._src_btn, row = _file_row(tr("ph_pdf_source"), self)
        self._src_btn.clicked.connect(self._browse_src)
        v.addLayout(row)
        return card

    def _build_quality_card(self):
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        self._hdr_q = _hdr(tr("hdr_pdf_quality"))
        v.addWidget(self._hdr_q)
        row = QHBoxLayout()
        row.setSpacing(8)
        self._quality_btns: dict[int, QPushButton] = {}
        for key, dpi in _QUALITY_PRESETS:
            btn = QPushButton(tr(key))
            btn.setObjectName("ChipBtn")
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setFixedWidth(90)
            btn.clicked.connect(lambda _c, d=dpi: self._select_quality(d))
            self._quality_btns[dpi] = btn
            row.addWidget(btn)
        row.addStretch()
        v.addLayout(row)
        self._select_quality(150)
        return card

    def _build_output_card(self):
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        self._hdr_out = _hdr(tr("hdr_output_folder"))
        v.addWidget(self._hdr_out)
        self._out_inp, self._out_btn, row = _file_row(tr("ph_same_dir"), self)
        if self._settings.output_folder:
            self._out_inp.setText(self._settings.output_folder)
        self._out_btn.clicked.connect(self._browse_out)
        v.addLayout(row)
        return card

    def _build_progress_card(self):
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(8)
        self._progress = QProgressBar()
        self._progress.setObjectName("TaskProgressBar")
        self._progress.setRange(0, 100)
        self._progress.setVisible(False)
        v.addWidget(self._progress)
        self._progress_lbl = QLabel()
        self._progress_lbl.setObjectName("TextSecondary")
        self._progress_lbl.setVisible(False)
        v.addWidget(self._progress_lbl)
        return card

    def _select_quality(self, dpi: int):
        self._selected_dpi = dpi
        for d, btn in self._quality_btns.items():
            active = d == dpi
            btn.setChecked(active)
            btn.setProperty("selected", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _browse_src(self):
        start = os.path.dirname(self._src_inp.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, tr("dlg_select_pdf"), start, _PDF_FILTER)
        if path:
            self._src_inp.setText(path)

    def _browse_out(self):
        start = self._out_inp.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, tr("dlg_select_output_folder"), start)
        if d:
            self._out_inp.setText(d)

    def populate_file(self, path: str):
        self._src_inp.setText(path)

    def retranslate_ui(self):
        self._hdr_src.setText(tr("hdr_source_pdf"))
        self._src_inp.setPlaceholderText(tr("ph_pdf_source"))
        self._src_btn.setText(tr("btn_browse"))
        self._hdr_q.setText(tr("hdr_pdf_quality"))
        for (key, dpi), btn in zip(_QUALITY_PRESETS, self._quality_btns.values()):
            btn.setText(tr(key))
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._out_inp.setPlaceholderText(tr("ph_same_dir"))
        self._out_btn.setText(tr("btn_browse"))

    def trigger_primary_action(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit(tr("status_cancelled"), False)
            return

        src = self._src_inp.text().strip()
        if not src:
            self.status_message.emit(tr("err_select_pdf"), True)
            return
        if not os.path.exists(src):
            self.status_message.emit(tr("err_file_not_found"), True)
            return

        dpi = self._selected_dpi
        out_dir = self._out_inp.text().strip() or os.path.dirname(src)
        base = os.path.splitext(os.path.basename(src))[0]
        out_path = os.path.join(out_dir, f"{base}_compressed.pdf")

        self._set_busy(True)
        self.status_message.emit(tr("status_pdf_compressing"), False)

        def _do():
            from core.pdf_toolkit import compress_pdf
            ok, result = compress_pdf(src, out_path, image_dpi=dpi)
            return {"success": ok, "path": result if ok else None, "error": result if not ok else None}

        self._worker = Worker(_do)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool):
        self._progress.setVisible(busy)
        self._progress_lbl.setVisible(busy)
        if busy:
            self._progress_lbl.setText(tr("status_pdf_compressing"))
        self.busy_changed.emit(busy)

    def _on_result(self, result: dict):
        self._set_busy(False)
        self._worker = None
        if result["success"]:
            fp = result["path"]
            fn = os.path.basename(fp)
            get_history_manager().add_item(
                HistoryItem(task_type="pdf_compress", file_name=fn, file_path=fp, status="success")
            )
            self.status_message.emit(f"Done → {fn}", False)
        else:
            self.status_message.emit(f"Error: {result['error']}", True)

    def _on_error(self, err_tuple: tuple):
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)


class _MergePane(QWidget):
    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._build_files_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

    def _build_files_card(self):
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        self._hdr_files = _hdr(tr("hdr_pdf_files_to_merge"))
        v.addWidget(self._hdr_files)

        self._file_list = QListWidget()
        self._file_list.setFixedHeight(140)
        self._file_list.setToolTip(tr("tip_pdf_drag_to_reorder"))
        self._file_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        v.addWidget(self._file_list)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton(tr("btn_add_files"))
        self._add_btn.setObjectName("BrowseBtn")
        self._add_btn.clicked.connect(self._add_files)
        btn_row.addWidget(self._add_btn)

        self._remove_btn = QPushButton(tr("btn_remove_selected"))
        self._remove_btn.setObjectName("BrowseBtn")
        self._remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(self._remove_btn)

        self._clear_btn = QPushButton(tr("btn_clear_list"))
        self._clear_btn.setObjectName("BrowseBtn")
        self._clear_btn.clicked.connect(self._file_list.clear)
        btn_row.addWidget(self._clear_btn)
        btn_row.addStretch()
        v.addLayout(btn_row)
        return card

    def _build_output_card(self):
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        self._hdr_out = _hdr(tr("hdr_output_file"))
        v.addWidget(self._hdr_out)
        row = QHBoxLayout()
        self._out_inp = QLineEdit()
        self._out_inp.setObjectName("PillInput")
        self._out_inp.setPlaceholderText(tr("ph_pdf_merged_output"))
        row.addWidget(self._out_inp)
        self._out_btn = QPushButton(tr("btn_browse"))
        self._out_btn.setObjectName("BrowseBtn")
        self._out_btn.setFixedWidth(90)
        self._out_btn.clicked.connect(self._browse_out)
        row.addWidget(self._out_btn)
        v.addLayout(row)
        return card

    def _build_progress_card(self):
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(8)
        self._progress = QProgressBar()
        self._progress.setObjectName("TaskProgressBar")
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        v.addWidget(self._progress)
        self._progress_lbl = QLabel()
        self._progress_lbl.setObjectName("TextSecondary")
        self._progress_lbl.setVisible(False)
        v.addWidget(self._progress_lbl)
        return card

    def _add_files(self):
        start = os.path.expanduser("~")
        paths, _ = QFileDialog.getOpenFileNames(self, tr("dlg_select_pdfs"), start, _PDF_FILTER)
        for p in paths:
            self._file_list.addItem(QListWidgetItem(p))

    def _remove_selected(self):
        for item in self._file_list.selectedItems():
            self._file_list.takeItem(self._file_list.row(item))

    def _browse_out(self):
        start = os.path.expanduser("~")
        path, _ = QFileDialog.getSaveFileName(self, tr("dlg_save_pdf"), start, _PDF_FILTER)
        if path:
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            self._out_inp.setText(path)

    def retranslate_ui(self):
        self._hdr_files.setText(tr("hdr_pdf_files_to_merge"))
        self._add_btn.setText(tr("btn_add_files"))
        self._remove_btn.setText(tr("btn_remove_selected"))
        self._clear_btn.setText(tr("btn_clear_list"))
        self._hdr_out.setText(tr("hdr_output_file"))
        self._out_inp.setPlaceholderText(tr("ph_pdf_merged_output"))
        self._out_btn.setText(tr("btn_browse"))

    def trigger_primary_action(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit(tr("status_cancelled"), False)
            return

        paths = [self._file_list.item(i).text() for i in range(self._file_list.count())]
        if len(paths) < 2:
            self.status_message.emit(tr("err_pdf_merge_min_files"), True)
            return

        out_path = self._out_inp.text().strip()
        if not out_path:
            first_dir = os.path.dirname(paths[0])
            out_path = os.path.join(first_dir, "merged.pdf")

        self._set_busy(True)
        self.status_message.emit(tr("status_pdf_merging"), False)

        def _do():
            from core.pdf_toolkit import merge_pdfs
            ok, result = merge_pdfs(paths, out_path)
            return {"success": ok, "path": result if ok else None, "error": result if not ok else None}

        self._worker = Worker(_do)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool):
        self._progress.setVisible(busy)
        self._progress_lbl.setVisible(busy)
        if busy:
            self._progress_lbl.setText(tr("status_pdf_merging"))
        self.busy_changed.emit(busy)

    def _on_result(self, result: dict):
        self._set_busy(False)
        self._worker = None
        if result["success"]:
            fp = result["path"]
            fn = os.path.basename(fp)
            get_history_manager().add_item(
                HistoryItem(task_type="pdf_merge", file_name=fn, file_path=fp, status="success")
            )
            self.status_message.emit(f"Done → {fn}", False)
        else:
            self.status_message.emit(f"Error: {result['error']}", True)

    def _on_error(self, err_tuple: tuple):
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)


class _SplitPane(QWidget):
    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._build_source_card())
        layout.addWidget(self._build_range_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

    def _build_source_card(self):
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        self._hdr_src = _hdr(tr("hdr_source_pdf"))
        v.addWidget(self._hdr_src)
        self._src_inp, self._src_btn, row = _file_row(tr("ph_pdf_source"), self)
        self._src_btn.clicked.connect(self._browse_src)
        v.addLayout(row)
        return card

    def _build_range_card(self):
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        self._hdr_range = _hdr(tr("hdr_pdf_split_range"))
        v.addWidget(self._hdr_range)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._all_pages_btn = QPushButton(tr("pdf_split_all_pages"))
        self._all_pages_btn.setObjectName("ChipBtn")
        self._all_pages_btn.setCheckable(True)
        self._all_pages_btn.setFlat(True)
        self._all_pages_btn.clicked.connect(lambda: self._select_split_mode("all"))
        row.addWidget(self._all_pages_btn)

        self._range_btn = QPushButton(tr("pdf_split_custom_range"))
        self._range_btn.setObjectName("ChipBtn")
        self._range_btn.setCheckable(True)
        self._range_btn.setFlat(True)
        self._range_btn.clicked.connect(lambda: self._select_split_mode("range"))
        row.addWidget(self._range_btn)
        row.addStretch()
        v.addLayout(row)

        range_row = QHBoxLayout()
        self._range_lbl = QLabel(tr("lbl_pdf_range_hint"))
        self._range_lbl.setObjectName("TextSecondary")
        range_row.addWidget(self._range_lbl)
        self._range_inp = QLineEdit()
        self._range_inp.setObjectName("PillInput")
        self._range_inp.setPlaceholderText(tr("ph_pdf_range"))
        range_row.addWidget(self._range_inp, 1)
        v.addLayout(range_row)

        self._split_mode = "all"
        self._select_split_mode("all")
        return card

    def _build_output_card(self):
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        self._hdr_out = _hdr(tr("hdr_output_folder"))
        v.addWidget(self._hdr_out)
        self._out_inp, self._out_btn, row = _file_row(tr("ph_same_dir"), self)
        if self._settings.output_folder:
            self._out_inp.setText(self._settings.output_folder)
        self._out_btn.clicked.connect(self._browse_out)
        v.addLayout(row)
        return card

    def _build_progress_card(self):
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(8)
        self._progress = QProgressBar()
        self._progress.setObjectName("TaskProgressBar")
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        v.addWidget(self._progress)
        self._progress_lbl = QLabel()
        self._progress_lbl.setObjectName("TextSecondary")
        self._progress_lbl.setVisible(False)
        v.addWidget(self._progress_lbl)
        return card

    def _select_split_mode(self, mode: str):
        self._split_mode = mode
        for btn, m in [(self._all_pages_btn, "all"), (self._range_btn, "range")]:
            active = m == mode
            btn.setChecked(active)
            btn.setProperty("selected", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._range_inp.setEnabled(mode == "range")
        self._range_lbl.setEnabled(mode == "range")

    def _browse_src(self):
        start = os.path.dirname(self._src_inp.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, tr("dlg_select_pdf"), start, _PDF_FILTER)
        if path:
            self._src_inp.setText(path)

    def _browse_out(self):
        start = self._out_inp.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, tr("dlg_select_output_folder"), start)
        if d:
            self._out_inp.setText(d)

    def populate_file(self, path: str):
        self._src_inp.setText(path)

    def retranslate_ui(self):
        self._hdr_src.setText(tr("hdr_source_pdf"))
        self._src_inp.setPlaceholderText(tr("ph_pdf_source"))
        self._src_btn.setText(tr("btn_browse"))
        self._hdr_range.setText(tr("hdr_pdf_split_range"))
        self._all_pages_btn.setText(tr("pdf_split_all_pages"))
        self._range_btn.setText(tr("pdf_split_custom_range"))
        self._range_lbl.setText(tr("lbl_pdf_range_hint"))
        self._range_inp.setPlaceholderText(tr("ph_pdf_range"))
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._out_inp.setPlaceholderText(tr("ph_same_dir"))
        self._out_btn.setText(tr("btn_browse"))

    def _parse_ranges(self, text: str) -> list[tuple[int, int]] | None:
        ranges = []
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                halves = part.split("-", 1)
                try:
                    start, end = int(halves[0].strip()), int(halves[1].strip())
                    ranges.append((start, end))
                except ValueError:
                    return None
            else:
                try:
                    n = int(part)
                    ranges.append((n, n))
                except ValueError:
                    return None
        return ranges if ranges else None

    def trigger_primary_action(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit(tr("status_cancelled"), False)
            return

        src = self._src_inp.text().strip()
        if not src:
            self.status_message.emit(tr("err_select_pdf"), True)
            return
        if not os.path.exists(src):
            self.status_message.emit(tr("err_file_not_found"), True)
            return

        out_dir = self._out_inp.text().strip() or os.path.dirname(src)
        page_ranges = None

        if self._split_mode == "range":
            raw = self._range_inp.text().strip()
            if not raw:
                self.status_message.emit(tr("err_pdf_range_empty"), True)
                return
            page_ranges = self._parse_ranges(raw)
            if page_ranges is None:
                self.status_message.emit(tr("err_pdf_range_invalid"), True)
                return

        self._set_busy(True)
        self.status_message.emit(tr("status_pdf_splitting"), False)

        def _do():
            from core.pdf_toolkit import split_pdf
            ok, out_paths, err = split_pdf(src, out_dir, page_ranges)
            return {"success": ok, "paths": out_paths, "count": len(out_paths), "error": err}

        self._worker = Worker(_do)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool):
        self._progress.setVisible(busy)
        self._progress_lbl.setVisible(busy)
        if busy:
            self._progress_lbl.setText(tr("status_pdf_splitting"))
        self.busy_changed.emit(busy)

    def _on_result(self, result: dict):
        self._set_busy(False)
        self._worker = None
        if result["success"]:
            count = result["count"]
            get_history_manager().add_item(
                HistoryItem(
                    task_type="pdf_split",
                    file_name=os.path.basename(self._src_inp.text()),
                    file_path=self._src_inp.text(),
                    status="success",
                )
            )
            self.status_message.emit(f"Done — {count} file(s) saved", False)
        else:
            self.status_message.emit(f"Error: {result['error']}", True)

    def _on_error(self, err_tuple: tuple):
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)


class _ExtractPane(QWidget):
    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._extract_mode = "embedded"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._build_source_card())
        layout.addWidget(self._build_mode_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

    def _build_source_card(self):
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        self._hdr_src = _hdr(tr("hdr_source_pdf"))
        v.addWidget(self._hdr_src)
        self._src_inp, self._src_btn, row = _file_row(tr("ph_pdf_source"), self)
        self._src_btn.clicked.connect(self._browse_src)
        v.addLayout(row)
        return card

    def _build_mode_card(self):
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        self._hdr_mode = _hdr(tr("hdr_pdf_extract_mode"))
        v.addWidget(self._hdr_mode)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._embedded_btn = QPushButton(tr("pdf_extract_embedded"))
        self._embedded_btn.setObjectName("ChipBtn")
        self._embedded_btn.setCheckable(True)
        self._embedded_btn.setFlat(True)
        self._embedded_btn.clicked.connect(lambda: self._select_mode("embedded"))
        row.addWidget(self._embedded_btn)

        self._pages_btn = QPushButton(tr("pdf_extract_pages"))
        self._pages_btn.setObjectName("ChipBtn")
        self._pages_btn.setCheckable(True)
        self._pages_btn.setFlat(True)
        self._pages_btn.clicked.connect(lambda: self._select_mode("pages"))
        row.addWidget(self._pages_btn)
        row.addStretch()
        v.addLayout(row)

        dpi_row = QHBoxLayout()
        self._dpi_lbl = QLabel(tr("lbl_pdf_jpeg_dpi"))
        self._dpi_lbl.setObjectName("TextSecondary")
        dpi_row.addWidget(self._dpi_lbl)
        self._dpi_spin = QSpinBox()
        self._dpi_spin.setRange(72, 600)
        self._dpi_spin.setSingleStep(25)
        self._dpi_spin.setValue(150)
        self._dpi_spin.setFixedWidth(80)
        dpi_row.addWidget(self._dpi_spin)
        dpi_row.addStretch()
        v.addLayout(dpi_row)

        self._select_mode("embedded")
        return card

    def _build_output_card(self):
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        self._hdr_out = _hdr(tr("hdr_output_folder"))
        v.addWidget(self._hdr_out)
        self._out_inp, self._out_btn, row = _file_row(tr("ph_same_dir"), self)
        if self._settings.output_folder:
            self._out_inp.setText(self._settings.output_folder)
        self._out_btn.clicked.connect(self._browse_out)
        v.addLayout(row)
        return card

    def _build_progress_card(self):
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(8)
        self._progress = QProgressBar()
        self._progress.setObjectName("TaskProgressBar")
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        v.addWidget(self._progress)
        self._progress_lbl = QLabel()
        self._progress_lbl.setObjectName("TextSecondary")
        self._progress_lbl.setVisible(False)
        v.addWidget(self._progress_lbl)
        return card

    def _select_mode(self, mode: str):
        self._extract_mode = mode
        for btn, m in [(self._embedded_btn, "embedded"), (self._pages_btn, "pages")]:
            active = m == mode
            btn.setChecked(active)
            btn.setProperty("selected", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        pages_mode = mode == "pages"
        self._dpi_lbl.setEnabled(pages_mode)
        self._dpi_spin.setEnabled(pages_mode)

    def _browse_src(self):
        start = os.path.dirname(self._src_inp.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, tr("dlg_select_pdf"), start, _PDF_FILTER)
        if path:
            self._src_inp.setText(path)

    def _browse_out(self):
        start = self._out_inp.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, tr("dlg_select_output_folder"), start)
        if d:
            self._out_inp.setText(d)

    def populate_file(self, path: str):
        self._src_inp.setText(path)

    def retranslate_ui(self):
        self._hdr_src.setText(tr("hdr_source_pdf"))
        self._src_inp.setPlaceholderText(tr("ph_pdf_source"))
        self._src_btn.setText(tr("btn_browse"))
        self._hdr_mode.setText(tr("hdr_pdf_extract_mode"))
        self._embedded_btn.setText(tr("pdf_extract_embedded"))
        self._pages_btn.setText(tr("pdf_extract_pages"))
        self._dpi_lbl.setText(tr("lbl_pdf_jpeg_dpi"))
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._out_inp.setPlaceholderText(tr("ph_same_dir"))
        self._out_btn.setText(tr("btn_browse"))

    def trigger_primary_action(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit(tr("status_cancelled"), False)
            return

        src = self._src_inp.text().strip()
        if not src:
            self.status_message.emit(tr("err_select_pdf"), True)
            return
        if not os.path.exists(src):
            self.status_message.emit(tr("err_file_not_found"), True)
            return

        out_dir = self._out_inp.text().strip() or os.path.dirname(src)
        mode = self._extract_mode
        dpi = self._dpi_spin.value()

        self._set_busy(True)
        self.status_message.emit(tr("status_pdf_extracting"), False)

        def _do():
            from core.pdf_toolkit import extract_images_from_pdf
            ok, out_paths, err = extract_images_from_pdf(
                src, out_dir,
                export_pages_as_jpeg=(mode == "pages"),
                jpeg_dpi=dpi,
            )
            return {"success": ok, "count": len(out_paths), "error": err}

        self._worker = Worker(_do)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool):
        self._progress.setVisible(busy)
        self._progress_lbl.setVisible(busy)
        if busy:
            self._progress_lbl.setText(tr("status_pdf_extracting"))
        self.busy_changed.emit(busy)

    def _on_result(self, result: dict):
        self._set_busy(False)
        self._worker = None
        if result["success"]:
            count = result["count"]
            if count == 0:
                self.status_message.emit(tr("status_pdf_no_images"), False)
            else:
                get_history_manager().add_item(
                    HistoryItem(
                        task_type="pdf_extract",
                        file_name=os.path.basename(self._src_inp.text()),
                        file_path=self._src_inp.text(),
                        status="success",
                    )
                )
                self.status_message.emit(f"Done — {count} image(s) saved", False)
        else:
            self.status_message.emit(f"Error: {result['error']}", True)

    def _on_error(self, err_tuple: tuple):
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)


class _OcrPane(QWidget):
    """OCR a PDF -> searchable PDF or text. Backed by RapidOCR or EasyOCR
    (each installable on demand via model_manager)."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._install_proc = None
        self._install_tail: list[str] = []
        self._installing_id: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._build_engine_card())
        layout.addWidget(self._build_source_card())
        layout.addWidget(self._build_options_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_install_card())
        layout.addWidget(self._build_progress_card())

        self._refresh_engine_state()

    # ── Engine selector ──────────────────────────────────────────────────────

    def _build_engine_card(self) -> QFrame:
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        self._hdr_engine = _hdr(tr("hdr_ocr_engine"))
        v.addWidget(self._hdr_engine)

        self._engine_hint = QLabel(tr("hint_ocr_engine"))
        self._engine_hint.setObjectName("TextMuted")
        self._engine_hint.setWordWrap(True)
        self._engine_hint.setStyleSheet("font-size: 12px;")
        v.addWidget(self._engine_hint)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._engine_combo = QComboBox()
        self._engine_combo.setObjectName("PillInput")
        self._engine_combo.addItem(tr("ocr_engine_rapid"), "rapid")
        self._engine_combo.addItem(tr("ocr_engine_easy"), "easy")
        self._engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        row.addWidget(self._engine_combo, 1)

        self._engine_status = QLabel("")
        self._engine_status.setObjectName("TextMuted")
        self._engine_status.setStyleSheet("font-size: 12px;")
        row.addWidget(self._engine_status)
        row.addStretch()
        v.addLayout(row)

        return card

    # ── Source ──────────────────────────────────────────────────────────────

    def _build_source_card(self) -> QFrame:
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        self._hdr_src = _hdr(tr("hdr_source_pdf"))
        v.addWidget(self._hdr_src)
        self._src_inp, self._src_btn, row = _file_row(tr("ph_pdf_source"), self)
        self._src_btn.clicked.connect(self._browse_src)
        v.addLayout(row)
        return card

    # ── Options ─────────────────────────────────────────────────────────────

    def _build_options_card(self) -> QFrame:
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        self._hdr_opts = _hdr(tr("hdr_ocr_options"))
        v.addWidget(self._hdr_opts)

        # Output mode chips
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        self._mode_searchable_btn = QPushButton(tr("ocr_mode_searchable"))
        self._mode_searchable_btn.setObjectName("ChipBtn")
        self._mode_searchable_btn.setCheckable(True)
        self._mode_searchable_btn.setFlat(True)
        self._mode_searchable_btn.clicked.connect(lambda: self._select_output_mode("searchable"))
        mode_row.addWidget(self._mode_searchable_btn)

        self._mode_text_btn = QPushButton(tr("ocr_mode_text"))
        self._mode_text_btn.setObjectName("ChipBtn")
        self._mode_text_btn.setCheckable(True)
        self._mode_text_btn.setFlat(True)
        self._mode_text_btn.clicked.connect(lambda: self._select_output_mode("text"))
        mode_row.addWidget(self._mode_text_btn)
        mode_row.addStretch()
        v.addLayout(mode_row)

        # Language
        lang_row = QHBoxLayout()
        self._lang_lbl = QLabel(tr("lbl_ocr_lang"))
        self._lang_lbl.setObjectName("TextSecondary")
        lang_row.addWidget(self._lang_lbl)
        self._lang_combo = QComboBox()
        self._lang_combo.setObjectName("PillInput")
        lang_row.addWidget(self._lang_combo, 1)
        v.addLayout(lang_row)

        # DPI
        dpi_row = QHBoxLayout()
        self._dpi_lbl = QLabel(tr("lbl_ocr_dpi"))
        self._dpi_lbl.setObjectName("TextSecondary")
        dpi_row.addWidget(self._dpi_lbl)
        self._dpi_spin = QSpinBox()
        self._dpi_spin.setRange(72, 600)
        self._dpi_spin.setSingleStep(50)
        self._dpi_spin.setValue(300)
        self._dpi_spin.setFixedWidth(80)
        dpi_row.addWidget(self._dpi_spin)
        dpi_row.addStretch()
        v.addLayout(dpi_row)

        self._output_mode = "searchable"
        self._select_output_mode("searchable")
        return card

    # ── Output ──────────────────────────────────────────────────────────────

    def _build_output_card(self) -> QFrame:
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        self._hdr_out = _hdr(tr("hdr_output_file"))
        v.addWidget(self._hdr_out)
        self._out_inp, self._out_btn, row = _file_row(tr("ph_ocr_output_auto"), self)
        self._out_btn.clicked.connect(self._browse_out)
        v.addLayout(row)
        return card

    # ── Install card (engine missing) ───────────────────────────────────────

    def _build_install_card(self) -> QFrame:
        card = _card()
        card.setStyleSheet(
            "QFrame#Card { border: 1px solid rgba(245,158,11,0.4);"
            " background: rgba(245,158,11,0.06); border-radius: 10px; }"
        )
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)

        self._install_title = QLabel(f"⚠  {tr('lbl_ocr_engine_not_installed')}")
        self._install_title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #F59E0B;"
        )
        v.addWidget(self._install_title)

        self._install_desc = QLabel("")
        self._install_desc.setObjectName("TextMuted")
        self._install_desc.setWordWrap(True)
        self._install_desc.setStyleSheet("font-size: 12px;")
        v.addWidget(self._install_desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._install_btn = QPushButton(tr("btn_install_engine"))
        self._install_btn.setObjectName("PrimaryBtn")
        self._install_btn.setFixedWidth(180)
        self._install_btn.clicked.connect(self._start_install)
        btn_row.addWidget(self._install_btn)
        btn_row.addStretch()
        v.addLayout(btn_row)

        self._install_status = QLabel("")
        self._install_status.setObjectName("TextMuted")
        self._install_status.setStyleSheet("font-size: 12px; color: #3B82F6;")
        self._install_status.setVisible(False)
        v.addWidget(self._install_status)

        self._install_log = QTextEdit()
        self._install_log.setReadOnly(True)
        self._install_log.setFixedHeight(100)
        self._install_log.setObjectName("PillInput")
        self._install_log.setStyleSheet("font-size: 10px; font-family: monospace;")
        self._install_log.setVisible(False)
        v.addWidget(self._install_log)

        card.setVisible(False)
        self._install_card = card
        return card

    # ── Progress ────────────────────────────────────────────────────────────

    def _build_progress_card(self) -> QFrame:
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(8)
        self._progress = QProgressBar()
        self._progress.setObjectName("TaskProgressBar")
        self._progress.setRange(0, 100)
        self._progress.setVisible(False)
        v.addWidget(self._progress)
        self._progress_lbl = QLabel()
        self._progress_lbl.setObjectName("TextSecondary")
        self._progress_lbl.setVisible(False)
        v.addWidget(self._progress_lbl)
        return card

    # ── State / behaviour ───────────────────────────────────────────────────

    def _current_engine(self) -> str:
        return self._engine_combo.currentData() or "rapid"

    def _engine_component_id(self, engine: str) -> str:
        return "ocr_rapid" if engine == "rapid" else "ocr_easy"

    def _refresh_engine_state(self) -> None:
        engine = self._current_engine()
        cid = self._engine_component_id(engine)
        installed = model_manager.is_installed(cid)

        # Status badge
        self._engine_status.setText(
            tr("ocr_engine_installed") if installed else tr("ocr_engine_not_installed")
        )
        self._engine_status.setStyleSheet(
            "font-size: 12px; color: #22C55E;" if installed
            else "font-size: 12px; color: #F59E0B;"
        )

        # Install card
        if not installed and self._install_proc is None:
            desc_key = ("lbl_ocr_rapid_desc" if engine == "rapid"
                        else "lbl_ocr_easy_desc")
            self._install_desc.setText(tr(desc_key))
            self._install_card.setVisible(True)
            self._install_btn.setEnabled(True)
            self._install_status.setVisible(False)
            self._install_log.setVisible(False)
        elif installed:
            self._install_card.setVisible(False)

        # Refresh language dropdown for engine
        self._populate_langs(engine)

    def _populate_langs(self, engine: str) -> None:
        prev = self._lang_combo.currentData()
        self._lang_combo.blockSignals(True)
        self._lang_combo.clear()
        for code, key in _OCR_LANG_OPTIONS:
            if engine == "rapid" and code not in _OCR_LANGS_RAPID:
                continue
            self._lang_combo.addItem(tr(key), code)
        # Try to restore previous selection
        if prev is not None:
            idx = self._lang_combo.findData(prev)
            if idx >= 0:
                self._lang_combo.setCurrentIndex(idx)
        self._lang_combo.blockSignals(False)

    def _on_engine_changed(self, _idx: int) -> None:
        self._refresh_engine_state()

    def _select_output_mode(self, mode: str) -> None:
        self._output_mode = mode
        for btn, m in [(self._mode_searchable_btn, "searchable"),
                       (self._mode_text_btn, "text")]:
            active = m == mode
            btn.setChecked(active)
            btn.setProperty("selected", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _browse_src(self) -> None:
        start = os.path.dirname(self._src_inp.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, tr("dlg_select_pdf"), start, _PDF_FILTER)
        if path:
            self._src_inp.setText(path)

    def _browse_out(self) -> None:
        start = self._out_inp.text() or os.path.expanduser("~")
        if self._output_mode == "text":
            flt = "Text files (*.txt)"
            path, _ = QFileDialog.getSaveFileName(self, tr("dlg_save_txt"), start, flt)
        else:
            path, _ = QFileDialog.getSaveFileName(self, tr("dlg_save_pdf"), start, _PDF_FILTER)
        if path:
            self._out_inp.setText(path)

    def populate_file(self, path: str) -> None:
        self._src_inp.setText(path)

    # ── Install flow ────────────────────────────────────────────────────────

    def _start_install(self) -> None:
        engine = self._current_engine()
        cid = self._engine_component_id(engine)
        # Auto-pick variant: CUDA when supported (only ocr_easy has CUDA).
        variant = model_manager.detected_variant(cid)

        self._installing_id = cid
        self._install_btn.setEnabled(False)
        self._install_status.setStyleSheet("font-size: 12px; color: #3B82F6;")
        self._install_status.setText(tr("lbl_ocr_installing"))
        self._install_status.setVisible(True)
        self._install_log.setVisible(True)
        self._install_log.clear()
        self._install_tail = []

        try:
            self._install_proc = model_manager.start_install(
                cid, on_line=self._on_install_line, variant=variant,
            )
        except InsufficientDiskError:
            info = model_manager.pre_install_info(cid, variant)
            self._render_install_error(
                tr("install_error_disk").format(
                    required_mb=int(info.approx_size_mb * 1.5),
                    target=info.target_dir,
                )
            )
            return
        except Exception as exc:  # noqa: BLE001
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
        cid = self._installing_id or self._engine_component_id(self._current_engine())
        self._installing_id = None

        tail = "\n".join(self._install_tail)
        if proc is not None:
            try:
                tail += bytes(proc.readAllStandardOutput()).decode("utf-8", errors="replace")
            except Exception:
                pass
        model_manager.finalize_install(cid, exit_code, tail)

        if exit_code == 0:
            self._install_status.setStyleSheet("font-size: 12px; color: #22C55E;")
            self._install_status.setText(tr("lbl_ocr_install_done"))
            import importlib
            importlib.invalidate_caches()
            model_manager.ensure_ai_packages_on_path()
            self._refresh_engine_state()
            return

        state = model_manager.read_state(cid)
        info = model_manager.pre_install_info(cid, state.variant)
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
        self._install_btn.setEnabled(True)

    # ── i18n ────────────────────────────────────────────────────────────────

    def retranslate_ui(self) -> None:
        self._hdr_engine.setText(tr("hdr_ocr_engine"))
        self._engine_hint.setText(tr("hint_ocr_engine"))
        self._engine_combo.setItemText(0, tr("ocr_engine_rapid"))
        self._engine_combo.setItemText(1, tr("ocr_engine_easy"))
        self._hdr_src.setText(tr("hdr_source_pdf"))
        self._src_inp.setPlaceholderText(tr("ph_pdf_source"))
        self._src_btn.setText(tr("btn_browse"))
        self._hdr_opts.setText(tr("hdr_ocr_options"))
        self._mode_searchable_btn.setText(tr("ocr_mode_searchable"))
        self._mode_text_btn.setText(tr("ocr_mode_text"))
        self._lang_lbl.setText(tr("lbl_ocr_lang"))
        self._dpi_lbl.setText(tr("lbl_ocr_dpi"))
        self._hdr_out.setText(tr("hdr_output_file"))
        self._out_inp.setPlaceholderText(tr("ph_ocr_output_auto"))
        self._out_btn.setText(tr("btn_browse"))
        self._install_title.setText(f"⚠  {tr('lbl_ocr_engine_not_installed')}")
        self._install_btn.setText(tr("btn_install_engine"))
        # Re-render engine state to refresh status colour text + lang labels.
        self._populate_langs(self._current_engine())
        self._refresh_engine_state()

    # ── Run ─────────────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit(tr("status_cancelled"), False)
            return

        engine = self._current_engine()
        cid = self._engine_component_id(engine)
        if not model_manager.is_installed(cid):
            self.status_message.emit(tr("err_ocr_engine_missing"), True)
            return

        src = self._src_inp.text().strip()
        if not src:
            self.status_message.emit(tr("err_select_pdf"), True)
            return
        if not os.path.exists(src):
            self.status_message.emit(tr("err_file_not_found"), True)
            return

        lang = self._lang_combo.currentData() or "en"
        searchable = (self._output_mode == "searchable")
        dpi = self._dpi_spin.value()

        out_path = self._out_inp.text().strip()
        if not out_path:
            base = os.path.splitext(src)[0]
            out_path = f"{base}_ocr.pdf" if searchable else f"{base}_ocr.txt"

        # Use GPU for EasyOCR iff the CUDA variant is the one installed.
        use_gpu = False
        if engine == "easy":
            state = model_manager.read_state(cid)
            use_gpu = (state.variant == "cuda")

        self._set_busy(True)
        self.status_message.emit(tr("status_pdf_ocr"), False)

        def _do():
            from core.ocr import ocr_pdf
            ok, result = ocr_pdf(
                src, out_path,
                engine=engine,
                lang=lang,
                searchable=searchable,
                dpi=dpi,
                use_gpu=use_gpu,
            )
            return {"success": ok, "path": result if ok else None,
                    "error": result if not ok else None}

        self._worker = Worker(_do)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._progress.setVisible(busy)
        self._progress_lbl.setVisible(busy)
        if busy:
            self._progress.setRange(0, 0)
            self._progress_lbl.setText(tr("status_pdf_ocr"))
        self.busy_changed.emit(busy)

    def _on_result(self, result: dict) -> None:
        self._set_busy(False)
        self._worker = None
        if result["success"]:
            fp = result["path"]
            fn = os.path.basename(fp)
            get_history_manager().add_item(
                HistoryItem(task_type="pdf_ocr", file_name=fn, file_path=fp, status="success")
            )
            self.status_message.emit(f"Done → {fn}", False)
        else:
            self.status_message.emit(f"Error: {result['error']}", True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)


class PdfToolkitSection(QScrollArea):
    """PDF Toolkit — Compress, Merge, Split, Extract Images, OCR."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._active_mode = 0

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_mode_selector())

        self._panes = [
            _CompressPane(settings),
            _MergePane(settings),
            _SplitPane(settings),
            _ExtractPane(settings),
            _OcrPane(settings),
        ]
        self._stack = QStackedWidget()
        for pane in self._panes:
            pane_scroll = QScrollArea()
            pane_scroll.setWidgetResizable(True)
            pane_scroll.setFrameShape(QFrame.Shape.NoFrame)
            pane_scroll.setWidget(pane)
            self._stack.addWidget(pane_scroll)
            pane.status_message.connect(self.status_message)
            pane.busy_changed.connect(self.busy_changed)

        layout.addWidget(self._stack)
        self.setWidget(content)
        self._select_mode(0)

    def _build_mode_selector(self) -> QFrame:
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 14, 20, 14)
        v.setSpacing(8)
        self._mode_hdr = _hdr(tr("hdr_pdf_toolkit_mode"))
        v.addWidget(self._mode_hdr)

        row = QHBoxLayout()
        row.setSpacing(10)
        self._mode_btns: list[QPushButton] = []
        mode_keys = [
            "pdf_mode_compress",
            "pdf_mode_merge",
            "pdf_mode_split",
            "pdf_mode_extract",
            "pdf_mode_ocr",
        ]
        for i, key in enumerate(mode_keys):
            btn = QPushButton(tr(key))
            btn.setObjectName("ChipBtn")
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setMinimumWidth(130)
            btn.setMinimumHeight(36)
            btn.setStyleSheet("font-size: 13px; padding: 6px 18px;")
            btn.clicked.connect(lambda _c, idx=i: self._select_mode(idx))
            self._mode_btns.append(btn)
            row.addWidget(btn)
        row.addStretch()
        v.addLayout(row)
        return card

    def _select_mode(self, index: int):
        self._active_mode = index
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._mode_btns):
            active = i == index
            btn.setChecked(active)
            btn.setProperty("selected", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def retranslate_ui(self):
        self._mode_hdr.setText(tr("hdr_pdf_toolkit_mode"))
        mode_keys = ["pdf_mode_compress", "pdf_mode_merge", "pdf_mode_split", "pdf_mode_extract", "pdf_mode_ocr"]
        for btn, key in zip(self._mode_btns, mode_keys):
            btn.setText(tr(key))
        for pane in self._panes:
            pane.retranslate_ui()

    def populate_file(self, path: str):
        """Pre-fill source path into the active pane if it supports single-file input."""
        pane = self._panes[self._active_mode]
        if hasattr(pane, "populate_file"):
            pane.populate_file(path)

    def trigger_primary_action(self):
        self._panes[self._active_mode].trigger_primary_action()
