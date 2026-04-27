"""Convert / Batch Convert tab — PySide6 UI bound to core.converter.

T013: Reimplement Convert/Batch Convert tabs and bind to core converter via
      worker thread.

Sub-tabs
--------
  CONVERT      – single-file conversion (image → image, video → video, audio → audio)
  BATCH CONVERT – multi-file image conversion only (mirrors convert_images() API)
"""
from __future__ import annotations

import os
import subprocess
import sys

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
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.converter import convert_images
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker
from utils.ffmpeg import ffmpeg_path
from utils.naming import apply_name_template

# ── Format tables ──────────────────────────────────────────────────────────────

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".heic", ".heif"}
_AUDIO_EXTS = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"}
_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}

_IMAGE_FORMATS = ["JPG", "PNG", "WEBP", "BMP", "GIF", "HEIC"]
_AUDIO_FORMATS = ["MP3", "WAV", "AAC", "FLAC", "OGG", "M4A"]
_VIDEO_FORMATS = ["MP4", "MKV", "AVI", "MOV", "WEBM", "FLV", "MP3"]


def _detect_media_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _AUDIO_EXTS:
        return "audio"
    if ext in _VIDEO_EXTS:
        return "video"
    return "unknown"


def _ffmpeg_convert(
    src: str, target_fmt: str, output_dir: str | None, name_template: str = "{name}_converted"
) -> dict:
    """Convert video/audio to *target_fmt* via FFmpeg."""
    stem = apply_name_template(name_template, src, ext=target_fmt.lower())
    out_dir = output_dir or os.path.dirname(src)
    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(out_dir, f"{stem}.{target_fmt.lower()}")
    flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
    src_ext = os.path.splitext(src)[1].lower().lstrip(".")
    target_is_audio = target_fmt.lower() in {f.lower() for f in _AUDIO_FORMATS}
    src_is_video = src_ext in {e.lstrip(".") for e in _VIDEO_EXTS}
    cmd = [ffmpeg_path, "-y", "-i", src]
    if src_is_video and target_is_audio:
        cmd += ["-vn"]
    cmd.append(dest)
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=3600, **flags)
        return {"success": True, "file_path": dest}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ── Shared helpers ─────────────────────────────────────────────────────────────

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


# ── Single-convert view ───────────────────────────────────────────────────────


class _SingleConvertView(QWidget):
    """Inner widget for the CONVERT sub-tab (single file)."""

    status_message = Signal(str, bool)
    busy_changed   = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._media_type = "unknown"
        self._selected_format = ""
        self._last_result_path: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        root.addWidget(self._build_source_card())
        root.addWidget(self._build_format_card())
        root.addWidget(self._build_output_card())
        root.addWidget(self._build_progress_card())

    # ── Cards ──────────────────────────────────────────────────────────────────

    def _build_source_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("SOURCE FILE"))

        row = QHBoxLayout()
        self._file_input = QLineEdit()
        self._file_input.setObjectName("PillInput")
        self._file_input.setPlaceholderText("Image, video, or audio file…")
        self._file_input.textChanged.connect(self._on_source_changed)
        row.addWidget(self._file_input)

        browse_btn = QPushButton("Browse…")
        browse_btn.setObjectName("BrowseBtn")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_file)
        row.addWidget(browse_btn)
        layout.addLayout(row)

        self._type_label = QLabel()
        self._type_label.setObjectName("TextMuted")
        self._type_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._type_label)
        return card

    def _build_format_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("TARGET FORMAT"))

        self._format_container = QWidget()
        self._format_container.setStyleSheet("background: transparent;")
        self._format_layout = QHBoxLayout(self._format_container)
        self._format_layout.setContentsMargins(0, 0, 0, 0)
        self._format_layout.setSpacing(8)
        self._format_btns: dict[str, QPushButton] = {}
        layout.addWidget(self._format_container)

        self._format_hint = QLabel("Browse a file to see available formats.")
        self._format_hint.setObjectName("TextMuted")
        self._format_hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._format_hint)
        return card

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("OUTPUT FOLDER"))

        row = QHBoxLayout()
        self._out_input = QLineEdit()
        self._out_input.setObjectName("PillInput")
        self._out_input.setPlaceholderText("Same directory as source file")
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

        self._progress_label = QLabel()
        self._progress_label.setObjectName("TextSecondary")
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)
        return card

    # ── Dynamic format chips ───────────────────────────────────────────────────

    def _populate_format_chips(self, media_type: str) -> None:
        # Clear existing chips
        for btn in self._format_btns.values():
            btn.deleteLater()
        self._format_btns.clear()

        if media_type == "image":
            formats = _IMAGE_FORMATS
        elif media_type == "audio":
            formats = _AUDIO_FORMATS
        elif media_type == "video":
            formats = _VIDEO_FORMATS
        else:
            self._format_hint.setVisible(True)
            return

        self._format_hint.setVisible(False)
        for fmt in formats:
            btn = QPushButton(fmt)
            btn.setObjectName("ChipBtn")
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setFixedWidth(64)
            btn.clicked.connect(lambda _checked, f=fmt: self._select_format(f))
            self._format_btns[fmt] = btn
            self._format_layout.addWidget(btn)
        self._format_layout.addStretch()

        # Auto-select first format
        if formats:
            self._select_format(formats[0])

    def _select_format(self, fmt: str) -> None:
        self._selected_format = fmt
        for name, btn in self._format_btns.items():
            active = name == fmt
            btn.setChecked(active)
            btn.setProperty("selected", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ── Browse / Change handlers ───────────────────────────────────────────────

    def _on_source_changed(self, path: str) -> None:
        path = path.strip()
        mt = _detect_media_type(path) if os.path.isfile(path) else "unknown"
        if mt != self._media_type:
            self._media_type = mt
            self._populate_format_chips(mt)
        label_map = {"image": "Image file", "audio": "Audio file", "video": "Video file"}
        self._type_label.setText(label_map.get(mt, ""))

    def _browse_file(self) -> None:
        start = os.path.dirname(self._file_input.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File",
            start,
            "All Media (*.jpg *.jpeg *.png *.bmp *.gif *.webp *.heic *.heif "
            "*.mp4 *.mkv *.avi *.mov *.webm *.flv "
            "*.mp3 *.wav *.aac *.flac *.ogg *.m4a)",
        )
        if path:
            self._file_input.setText(path)

    def _browse_output(self) -> None:
        start = self._out_input.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if d:
            self._out_input.setText(d)

    def populate_file(self, path: str) -> None:
        self._file_input.setText(path)

    # ── Action ─────────────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        src = self._file_input.text().strip()
        if not src or not os.path.exists(src):
            self.status_message.emit("Please select a valid source file.", True)
            return
        if not self._selected_format:
            self.status_message.emit("Please select a target format.", True)
            return

        mt = self._media_type
        fmt = self._selected_format
        out_dir = self._out_input.text().strip() or None
        name_tmpl = self._settings.output_name_template

        self._set_busy(True)
        self.status_message.emit("Converting…", False)

        def do_convert():
            if mt == "image":
                ok = convert_images([src], fmt.lower(), out_dir)
                if ok:
                    stem = apply_name_template(name_tmpl, src, ext=fmt.lower())
                    dest_dir = out_dir or os.path.dirname(src)
                    dest = os.path.join(dest_dir, f"{stem}.{fmt.lower()}")
                    return {"success": True, "file_path": dest}
                return {"success": False, "error": "Image conversion failed."}
            else:
                return _ffmpeg_convert(src, fmt, out_dir, name_tmpl)

        self._worker = Worker(do_convert)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if busy:
            self._progress_label.setText("Converting…")
        self.busy_changed.emit(busy)

    def _on_result(self, result: dict) -> None:
        self._set_busy(False)
        self._worker = None
        src = self._file_input.text()
        if result.get("success"):
            fp = result.get("file_path") or ""
            self._last_result_path = fp
            fn = os.path.basename(fp)
            get_history_manager().add_item(
                HistoryItem(task_type="convert", file_name=fn, file_path=fp, status="success")
            )
            self.status_message.emit(f"Done → {fn}", False)
        else:
            err = result.get("error") or "Conversion failed."
            get_history_manager().add_item(
                HistoryItem(
                    task_type="convert",
                    file_name=os.path.basename(src),
                    file_path=src,
                    status="error",
                )
            )
            self.status_message.emit(f"Error: {err}", True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)


# ── Batch-convert view ────────────────────────────────────────────────────────


class _BatchConvertView(QWidget):
    """Inner widget for the BATCH CONVERT sub-tab (images only)."""

    status_message = Signal(str, bool)
    busy_changed   = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._selected_format = "PNG"
        self._last_result_path: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        root.addWidget(self._build_files_card())
        root.addWidget(self._build_format_card())
        root.addWidget(self._build_output_card())
        root.addWidget(self._build_progress_card())

    # ── Cards ──────────────────────────────────────────────────────────────────

    def _build_files_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("IMAGE FILES  (drag here or click Add)"))

        self._file_list = QListWidget()
        self._file_list.setObjectName("FileList")
        self._file_list.setFixedHeight(140)
        self._file_list.setAcceptDrops(False)
        layout.addWidget(self._file_list)

        row = QHBoxLayout()
        row.addStretch()

        add_btn = QPushButton("Add Files…")
        add_btn.setObjectName("BrowseBtn")
        add_btn.clicked.connect(self._add_files)
        row.addWidget(add_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("BrowseBtn")
        clear_btn.clicked.connect(self._file_list.clear)
        row.addWidget(clear_btn)
        layout.addLayout(row)
        return card

    def _build_format_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("TARGET FORMAT  (images only)"))

        row = QHBoxLayout()
        row.setSpacing(8)
        self._format_btns: dict[str, QPushButton] = {}
        for fmt in _IMAGE_FORMATS:
            btn = QPushButton(fmt)
            btn.setObjectName("ChipBtn")
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setFixedWidth(64)
            btn.clicked.connect(lambda _c, f=fmt: self._select_format(f))
            self._format_btns[fmt] = btn
            row.addWidget(btn)
        row.addStretch()
        layout.addLayout(row)
        self._select_format("PNG")
        return card

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("OUTPUT FOLDER"))

        row = QHBoxLayout()
        self._out_input = QLineEdit()
        self._out_input.setObjectName("PillInput")
        self._out_input.setPlaceholderText("Same directory as source files")
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

        self._progress_label = QLabel()
        self._progress_label.setObjectName("TextSecondary")
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)
        return card

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _select_format(self, fmt: str) -> None:
        self._selected_format = fmt
        for name, btn in self._format_btns.items():
            active = name == fmt
            btn.setChecked(active)
            btn.setProperty("selected", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Image Files",
            os.path.expanduser("~"),
            "Images (*.jpg *.jpeg *.png *.bmp *.gif *.webp *.heic *.heif)",
        )
        for p in paths:
            if not any(
                self._file_list.item(i).text() == p
                for i in range(self._file_list.count())
            ):
                self._file_list.addItem(QListWidgetItem(p))

    def _browse_output(self) -> None:
        start = self._out_input.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if d:
            self._out_input.setText(d)

    def add_files_from_paths(self, paths: list[str]) -> None:
        """Pre-populate file list (called by DnD handler)."""
        for p in paths:
            if not any(
                self._file_list.item(i).text() == p
                for i in range(self._file_list.count())
            ):
                self._file_list.addItem(QListWidgetItem(p))

    # ── Action ─────────────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        paths = [self._file_list.item(i).text() for i in range(self._file_list.count())]
        if not paths:
            self.status_message.emit("Please add at least one image file.", True)
            return

        fmt = self._selected_format
        out_dir = self._out_input.text().strip() or None
        count = len(paths)

        self._set_busy(True)
        self.status_message.emit(f"Converting {count} image(s)…", False)

        def do_batch():
            ok = convert_images(paths, fmt.lower(), out_dir)
            if ok:
                dest_dir = out_dir or os.path.dirname(paths[0])
                return {"success": True, "count": count, "dest_dir": dest_dir}
            return {"success": False, "error": "Batch conversion failed."}

        self._worker = Worker(do_batch)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if busy:
            self._progress_label.setText("Converting images…")
        self.busy_changed.emit(busy)

    def _on_result(self, result: dict) -> None:
        self._set_busy(False)
        self._worker = None
        if result.get("success"):
            n = result.get("count", 0)
            dest_dir = result.get("dest_dir", "")
            last_dest = ""
            for i in range(self._file_list.count()):
                p = self._file_list.item(i).text()
                base = os.path.splitext(os.path.basename(p))[0]
                dest = os.path.join(
                    dest_dir or os.path.dirname(p),
                    f"{base}.{self._selected_format.lower()}",
                )
                last_dest = dest
                get_history_manager().add_item(
                    HistoryItem(task_type="convert", file_name=os.path.basename(dest), file_path=dest, status="success")
                )
            self._last_result_path = last_dest
            self.status_message.emit(f"Done — {n} file(s) converted.", False)
        else:
            err = result.get("error") or "Batch conversion failed."
            self.status_message.emit(f"Error: {err}", True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)


# ── Public section widget ─────────────────────────────────────────────────────


class ConvertSection(QWidget):
    """Top-level section widget hosting CONVERT and BATCH CONVERT sub-tabs."""

    status_message = Signal(str, bool)
    busy_changed   = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._current_sub_tab = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Scroll area wrapping the inner stack
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        self._single_view = _SingleConvertView(settings)
        self._batch_view = _BatchConvertView(settings)
        self._stack.addWidget(self._single_view)
        self._stack.addWidget(self._batch_view)
        inner_layout.addWidget(self._stack)

        scroll.setWidget(inner)
        root.addWidget(scroll)

        # Forward status and busy signals
        self._single_view.status_message.connect(self.status_message)
        self._batch_view.status_message.connect(self.status_message)
        self._single_view.busy_changed.connect(self.busy_changed)
        self._batch_view.busy_changed.connect(self.busy_changed)

    @property
    def _last_result_path(self) -> str | None:
        view = self._single_view if self._current_sub_tab == 0 else self._batch_view
        return getattr(view, "_last_result_path", None)

    # ── Public API ────────────────────────────────────────────────────────────

    def on_sub_tab_changed(self, index: int) -> None:
        """Called by MainWindow when the section tab bar changes (0=CONVERT, 1=BATCH CONVERT)."""
        self._current_sub_tab = index
        self._stack.setCurrentIndex(index)

    def trigger_primary_action(self) -> None:
        if self._current_sub_tab == 0:
            self._single_view.trigger_primary_action()
        else:
            self._batch_view.trigger_primary_action()

    def populate_file(self, path: str) -> None:
        """Pre-populate from DnD (routes to single-convert view)."""
        self._single_view.populate_file(path)
        self._stack.setCurrentIndex(0)
        self._current_sub_tab = 0

    def populate_batch_files(self, paths: list[str]) -> None:
        """Pre-populate batch list from DnD."""
        self._batch_view.add_files_from_paths(paths)
        self._stack.setCurrentIndex(1)
        self._current_sub_tab = 1
