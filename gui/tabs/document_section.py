"""Document Convert tab — PySide6 UI bound to core.document.convert_document.

T015: Reimplement Document Convert tab UI and bind to core document functions.
"""
from __future__ import annotations

import os
import shutil

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

import re

from core.i18n import tr
from gui.widgets.markdown_editor import CodeEditor, MarkdownHighlighter
from core.document import convert_document
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker


# Qt's setMarkdown() stops parsing at an unclosed void HTML tag and silently
# drops the entire rest of the document — a real README with
# `<img src="..." width="400">` rendered only the text above the first image.
# Void tags are valid HTML (and GitHub renders them), so self-close them before
# handing the text to Qt. Paired and already-self-closed tags are untouched.
# setMarkdown() is synchronous; past roughly this size a re-render blocks
# the UI for seconds on every keystroke, so the preview steps aside.
_MD_PREVIEW_LIMIT = 2_000_000

_VOID_TAGS = "img|br|hr|input|meta|link|area|base|col|embed|source|track|wbr"
_VOID_TAG_RE = re.compile(
    r"<(%s)\b((?:[^<>\"']|\"[^\"]*\"|'[^']*')*?)/?>" % _VOID_TAGS,
    re.IGNORECASE)


def _close_void_html(text: str) -> str:
    """Rewrite `<img ...>` to `<img .../>` so Qt keeps parsing past it."""
    return _VOID_TAG_RE.sub(lambda m: f"<{m.group(1)}{m.group(2).rstrip()}/>", text)


class DocumentSection(QScrollArea):
    """Document Convert tab — Word to PDF, PDF to Word, Image to PDF."""

    status_message = Signal(str, bool)   # (text, is_error)
    busy_changed   = Signal(bool)

    _INPUT_FILTER = (
        "Documents (*.pdf *.docx *.pptx *.md *.markdown "
        "*.jpg *.jpeg *.png *.bmp *.gif *.webp)"
    )
    _FORMATS = ["PDF", "DOCX", "PPTX", "MD"]

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._selected_format = "DOCX"
        self._last_result_path: str | None = None
        self._current_sub_tab = 0
        self._md_path: str | None = None
        self._md_dirty = False

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Sub-tab 0 = Convert (the original cards), 1 = Markdown editor.
        self._stack = QStackedWidget()

        convert_page = QWidget()
        convert_layout = QVBoxLayout(convert_page)
        convert_layout.setContentsMargins(0, 0, 0, 0)
        convert_layout.setSpacing(16)
        convert_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        convert_layout.addWidget(self._build_source_card())
        convert_layout.addWidget(self._build_format_card())
        convert_layout.addWidget(self._build_output_card())
        convert_layout.addWidget(self._build_progress_card())
        self._stack.addWidget(convert_page)
        self._stack.addWidget(self._build_editor_page())

        layout.addWidget(self._stack)
        self.setWidget(content)

    # ── Card builders ─────────────────────────────────────────────────────────

    @staticmethod
    def _card() -> QFrame:
        f = QFrame()
        f.setObjectName("Card")
        return f

    @staticmethod
    def _section_header(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("TextSecondary")
        lbl.setStyleSheet(
            "font-size: 11px; font-weight: bold; letter-spacing: 1px; margin-bottom: 2px;"
        )
        return lbl

    def _build_source_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_src = self._section_header(tr("hdr_source_doc"))
        layout.addWidget(self._hdr_src)

        row = QHBoxLayout()
        self._file_input = QLineEdit()
        self._file_input.setObjectName("PillInput")
        self._file_input.setPlaceholderText(tr("ph_doc"))
        row.addWidget(self._file_input)

        self._browse_src_btn = QPushButton(tr("btn_browse"))
        self._browse_src_btn.setObjectName("BrowseBtn")
        self._browse_src_btn.setFixedWidth(90)
        self._browse_src_btn.clicked.connect(self._browse_file)
        row.addWidget(self._browse_src_btn)
        layout.addLayout(row)
        return card

    def _build_editor_page(self) -> QWidget:
        """Markdown source on the left, live rendered preview on the right.

        Uses Qt's own `setMarkdown()` rather than converting to HTML: it is
        built in, so there is no extra dependency and no second markdown
        dialect to keep in sync with `core.document`.
        """
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._hdr_md = self._section_header(tr("hdr_md_editor"))
        layout.addWidget(self._hdr_md)

        # ── toolbar ──────────────────────────────────────────────────────
        row = QHBoxLayout()
        row.setSpacing(8)
        for attr, key, slot in (
            ("_md_open_btn", "btn_md_open", self._md_open),
            ("_md_save_btn", "btn_md_save", self._md_save),
            ("_md_save_as_btn", "btn_md_save_as", self._md_save_as),
        ):
            btn = QPushButton(tr(key))
            btn.setObjectName("BrowseBtn")
            btn.clicked.connect(slot)
            setattr(self, attr, btn)
            row.addWidget(btn)

        row.addSpacing(12)
        self._md_sync_check = QCheckBox(tr("chk_md_sync"))
        self._md_sync_check.setChecked(True)
        self._md_sync_check.setToolTip(tr("tip_md_sync"))
        self._md_sync_check.setStyleSheet("font-size: 11px;")
        row.addWidget(self._md_sync_check)

        self._md_wrap_check = QCheckBox(tr("chk_md_wrap"))
        self._md_wrap_check.setStyleSheet("font-size: 11px;")
        self._md_wrap_check.toggled.connect(self._md_set_wrap)
        row.addWidget(self._md_wrap_check)

        row.addStretch()
        self._md_stats = QLabel("")
        self._md_stats.setObjectName("TextMuted")
        self._md_stats.setStyleSheet("font-size: 11px;")
        row.addWidget(self._md_stats)
        row.addSpacing(10)
        self._md_status = QLabel("")
        self._md_status.setObjectName("TextMuted")
        self._md_status.setStyleSheet("font-size: 11px;")
        row.addWidget(self._md_status)
        layout.addLayout(row)

        # ── split panes ──────────────────────────────────────────────────
        self._md_split = QSplitter(Qt.Orientation.Horizontal)
        self._md_split.setHandleWidth(6)
        self._md_split.setChildrenCollapsible(False)

        # Created before the editor: setPlaceholderText/setPlainText emit
        # textChanged, and the handler starts this timer.
        self._md_timer = QTimer(self)
        self._md_timer.setInterval(180)
        self._md_timer.setSingleShot(True)
        self._md_timer.timeout.connect(self._md_render)

        dark = self._is_dark_theme()
        self._md_edit = CodeEditor(dark=dark)
        self._md_edit.setPlaceholderText(tr("ph_md_editor"))
        self._md_edit.textChanged.connect(self._md_on_changed)
        self._md_highlighter = MarkdownHighlighter(self._md_edit.document(), dark)
        self._md_split.addWidget(self._md_edit)

        self._md_view = QTextBrowser()
        self._md_view.setOpenExternalLinks(False)
        # Readable measure: generous padding and a comfortable body font, rather
        # than text jammed against the frame edge.
        self._md_view.document().setDocumentMargin(18)
        # Local relative images (a README beside its screenshots) resolve only
        # if the browser knows where the file lives; set per load.
        self._md_view.setFrameShape(QFrame.Shape.NoFrame)
        self._md_split.addWidget(self._md_view)
        self._md_split.setSizes([560, 560])
        self._md_split.setMinimumHeight(460)
        layout.addWidget(self._md_split, 1)

        # ── scroll sync ──────────────────────────────────────────────────
        # Proportional, both ways, with a re-entry guard: setting one bar emits
        # valueChanged on it, which would otherwise bounce back and fight the
        # user's scrolling.
        self._md_syncing = False
        self._md_sync_target: tuple | None = None
        edit_bar = self._md_edit.verticalScrollBar()
        view_bar = self._md_view.verticalScrollBar()
        edit_bar.valueChanged.connect(
            lambda v: self._md_sync_scroll(self._md_edit, self._md_view))
        view_bar.valueChanged.connect(
            lambda v: self._md_sync_scroll(self._md_view, self._md_edit))
        # Lazy layout keeps moving the goalposts — re-seat when the range moves.
        view_bar.rangeChanged.connect(lambda *_: self._md_reapply_sync(view_bar))
        edit_bar.rangeChanged.connect(lambda *_: self._md_reapply_sync(edit_bar))

        outer.addWidget(card, 1)
        self.apply_theme(dark)
        self._md_update_status()
        return page

    # ── Markdown editor ───────────────────────────────────────────────────────

    @staticmethod
    def _is_dark_theme() -> bool:
        """Match the app palette so the editor is not a bright hole in dark mode."""
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                bg = app.palette().color(app.palette().ColorRole.Window)
                return bg.lightness() < 128
        except Exception:
            pass
        return True

    def apply_theme(self, dark: bool | None = None) -> None:
        """Re-colour the editor when the app theme changes."""
        if dark is None:
            dark = self._is_dark_theme()
        if not hasattr(self, "_md_edit"):
            return
        self._md_edit.set_theme(dark)
        self._md_highlighter.set_theme(dark)
        from gui.widgets.markdown_editor import DARK_THEME, LIGHT_THEME
        c = DARK_THEME if dark else LIGHT_THEME
        self._md_view.setStyleSheet(
            "QTextBrowser {"
            f" background-color: {c['editor_bg']};"
            f" color: {c['editor_fg']};"
            f" selection-background-color: {c['selection']};"
            " border: none; }"
        )
        self._md_split.setStyleSheet(
            f"QSplitter::handle {{ background-color: {c['border']}; }}")

    def _md_set_wrap(self, on: bool) -> None:
        self._md_edit.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if on
            else QPlainTextEdit.LineWrapMode.NoWrap)

    def _md_sync_scroll(self, source, target) -> None:
        """Mirror *source*'s scroll fraction onto *target*.

        Proportional rather than line-mapped: the rendered side has a different
        line count (a 3-line table renders as one row block), so matching
        fractions is the only mapping that holds for arbitrary documents.

        QTextBrowser lays out lazily, so its scrollbar `maximum()` keeps
        shrinking as it measures more of the document. Scrolling to a fraction
        of a stale maximum lands in the wrong place (measured: 84% instead of
        75%), so the wanted fraction is remembered and re-applied when the
        range next changes.
        """
        if self._md_syncing or not self._md_sync_check.isChecked():
            return
        src_bar, dst_bar = source.verticalScrollBar(), target.verticalScrollBar()
        if src_bar.maximum() <= 0 or dst_bar.maximum() <= 0:
            return
        self._md_syncing = True
        try:
            frac = src_bar.value() / src_bar.maximum()
            self._md_sync_target = (dst_bar, frac)
            dst_bar.setValue(round(frac * dst_bar.maximum()))
        finally:
            self._md_syncing = False

    def _md_reapply_sync(self, bar) -> None:
        """Re-seat a synced scrollbar after its range changed under us."""
        pending = getattr(self, "_md_sync_target", None)
        if not pending or self._md_syncing or bar.maximum() <= 0:
            return
        target_bar, frac = pending
        if target_bar is not bar:
            return
        want = round(frac * bar.maximum())
        if want == bar.value():
            return
        self._md_syncing = True
        try:
            bar.setValue(want)
        finally:
            self._md_syncing = False

    def on_sub_tab_changed(self, index: int) -> None:
        """Sub-tab switch (0 = Convert, 1 = Markdown editor)."""
        self._current_sub_tab = max(0, min(1, index))
        self._stack.setCurrentIndex(self._current_sub_tab)
        # Opening the editor on a .md already chosen in Convert saves a step.
        if self._current_sub_tab == 1 and not self._md_edit.toPlainText():
            src = self._file_input.text().strip()
            if src.lower().endswith((".md", ".markdown")) and os.path.isfile(src):
                self._md_load(src)

    def _md_on_changed(self) -> None:
        self._md_dirty = True
        self._md_timer.start()
        self._md_update_status()

    def _md_render(self) -> None:
        text = self._md_edit.toPlainText()
        # Very large documents make setMarkdown block for seconds on every
        # keystroke; show the source and say so rather than freeze the window.
        if len(text) > _MD_PREVIEW_LIMIT:
            self._md_view.setPlainText(
                tr("msg_md_too_large").format(mb=round(len(text) / 1_000_000, 1)))
            return
        # Keep the reader's scroll position; setMarkdown resets it otherwise.
        bar = self._md_view.verticalScrollBar()
        pos = bar.value()
        was = self._md_syncing
        self._md_syncing = True          # the reset would otherwise drag the editor
        try:
            self._md_view.setMarkdown(_close_void_html(text))
            bar.setValue(min(pos, bar.maximum()))
        finally:
            self._md_syncing = was

    def _md_update_status(self) -> None:
        name = os.path.basename(self._md_path) if self._md_path else tr("lbl_md_untitled")
        self._md_status.setText(f"{name}{' *' if self._md_dirty else ''}")
        text = self._md_edit.toPlainText()
        self._md_stats.setText(tr("lbl_md_stats").format(
            lines=text.count("\n") + 1, words=len(text.split()), chars=len(text)))

    def _md_load(self, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            self.status_message.emit(f"{tr('err_md_open')}: {exc}", True)
            return
        self._md_path = path
        # Relative image paths in a README are relative to ITS folder, not the
        # app's cwd, so the browser needs the file's directory as its base.
        try:
            from PySide6.QtCore import QUrl
            self._md_view.setSearchPaths([os.path.dirname(path)])
            self._md_view.document().setBaseUrl(
                QUrl.fromLocalFile(os.path.dirname(path) + os.sep))
        except Exception:
            pass
        self._md_edit.setPlainText(text)
        self._md_dirty = False
        self._md_render()
        self._md_update_status()

    def _md_open(self) -> None:
        start = os.path.dirname(self._md_path or self._file_input.text()) \
            or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, tr("btn_md_open"), start, "Markdown (*.md *.markdown);;All files (*)")
        if path:
            self._md_load(path)

    def _md_write(self, path: str) -> bool:
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(self._md_edit.toPlainText())
        except OSError as exc:
            self.status_message.emit(f"{tr('err_md_save')}: {exc}", True)
            return False
        self._md_path = path
        self._md_dirty = False
        self._md_update_status()
        self.status_message.emit(tr("msg_md_saved").format(
            name=os.path.basename(path)), False)
        return True

    def _md_save(self) -> None:
        if self._md_path:
            self._md_write(self._md_path)
        else:
            self._md_save_as()

    def _md_save_as(self) -> None:
        start = self._md_path or os.path.join(os.path.expanduser("~"), "untitled.md")
        path, _ = QFileDialog.getSaveFileName(
            self, tr("btn_md_save_as"), start, "Markdown (*.md);;All files (*)")
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".md"
        self._md_write(path)

    def _build_format_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_fmt = self._section_header(tr("hdr_target_format"))
        layout.addWidget(self._hdr_fmt)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._format_btns: dict[str, QPushButton] = {}
        for fmt in self._FORMATS:
            btn = QPushButton(fmt)
            btn.setObjectName("ChipBtn")
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setFixedWidth(72)
            btn.clicked.connect(lambda _checked, f=fmt: self._select_format(f))
            self._format_btns[fmt] = btn
            row.addWidget(btn)
        row.addStretch()
        layout.addLayout(row)

        self._select_format("DOCX")
        return card

    def _build_output_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_out = self._section_header(tr("hdr_output_folder"))
        layout.addWidget(self._hdr_out)

        row = QHBoxLayout()
        self._out_input = QLineEdit()
        self._out_input.setObjectName("PillInput")
        self._out_input.setPlaceholderText(tr("ph_same_dir"))
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

    def _build_progress_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("TaskProgressBar")
        self._progress_bar.setRange(0, 0)   # indeterminate initially
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._progress_label = QLabel()
        self._progress_label.setObjectName("TextSecondary")
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)
        return card

    # ── Interaction ───────────────────────────────────────────────────────────

    def _select_format(self, fmt: str) -> None:
        self._selected_format = fmt
        for name, btn in self._format_btns.items():
            active = name == fmt
            btn.setChecked(active)
            btn.setProperty("selected", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)


    def retranslate_ui(self) -> None:
        self._hdr_src.setText(tr("hdr_source_doc"))
        self._file_input.setPlaceholderText(tr("ph_doc"))
        self._browse_src_btn.setText(tr("btn_browse"))
        self._hdr_fmt.setText(tr("hdr_target_format"))
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._out_input.setPlaceholderText(tr("ph_same_dir"))
        self._browse_out_btn.setText(tr("btn_browse"))
        if self._progress_label.isVisible():
            self._progress_label.setText(tr("dyn_converting"))
        self._hdr_md.setText(tr("hdr_md_editor"))
        self._md_open_btn.setText(tr("btn_md_open"))
        self._md_save_btn.setText(tr("btn_md_save"))
        self._md_save_as_btn.setText(tr("btn_md_save_as"))
        self._md_edit.setPlaceholderText(tr("ph_md_editor"))
        self._md_sync_check.setText(tr("chk_md_sync"))
        self._md_sync_check.setToolTip(tr("tip_md_sync"))
        self._md_wrap_check.setText(tr("chk_md_wrap"))
        self._md_update_status()

    def _browse_file(self) -> None:
        start = os.path.dirname(self._file_input.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Document", start, self._INPUT_FILTER
        )
        if path:
            self._file_input.setText(path)

    def _browse_output(self) -> None:
        start = self._out_input.text() or os.path.expanduser("~")
        directory = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if directory:
            self._out_input.setText(directory)

    def populate_file(self, path: str) -> None:
        """Pre-populate source file input (called by DnD handler)."""
        self._file_input.setText(path)

    # ── Primary action ────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        """Invoked by MainWindow's primary action button."""
        # On the Markdown tab the button saves instead of converting — there is
        # nothing to convert there, and it is the only destructive-ish action.
        if self._current_sub_tab == 1:
            self._md_save()
            return
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        src = self._file_input.text().strip()
        if not src:
            self.status_message.emit("Please select a source document.", True)
            return
        if not os.path.exists(src):
            self.status_message.emit("Source file not found.", True)
            return

        fmt = self._selected_format.lower()
        out_dir = self._out_input.text().strip() or None

        self._set_busy(True)
        self.status_message.emit("Converting document…", False)

        # Capture for closure
        _src = src
        _fmt = fmt
        _out_dir = out_dir

        def do_convert():
            success, output_or_err, _summary = convert_document(_src, _fmt)
            if success and _out_dir and output_or_err:
                dest = os.path.join(_out_dir, os.path.basename(output_or_err))
                shutil.move(output_or_err, dest)
                return {"success": True, "file_path": dest}
            return {
                "success": success,
                "file_path": output_or_err if success else None,
                "error": output_or_err if not success else None,
            }

        self._worker = Worker(do_convert)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    # ── Worker callbacks ──────────────────────────────────────────────────────

    def _set_busy(self, busy: bool) -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if busy:
            self._progress_label.setText(tr("dyn_converting"))
        self.busy_changed.emit(busy)

    def _on_result(self, result: dict) -> None:
        self._set_busy(False)
        self._worker = None
        if result.get("success"):
            fp = result.get("file_path") or ""
            self._last_result_path = fp
            fn = os.path.basename(fp) if fp else "output"
            get_history_manager().add_item(
                HistoryItem(task_type="document", file_name=fn, file_path=fp, status="success")
            )
            self.status_message.emit(f"Done → {fn}", False)
        else:
            err = result.get("error") or "Conversion failed."
            get_history_manager().add_item(
                HistoryItem(
                    task_type="document",
                    file_name=os.path.basename(self._file_input.text()),
                    file_path=self._file_input.text(),
                    status="error",
                )
            )
            self.status_message.emit(f"Error: {err}", True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
