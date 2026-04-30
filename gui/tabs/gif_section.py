"""GIF Creator tab — converts a video segment to an animated GIF via FFmpeg."""
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
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker
from utils.ffmpeg import ffmpeg_path


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


class GifSection(QWidget):
    """Section widget: convert a video clip to an animated GIF."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_result_path: str | None = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_source_card())
        layout.addWidget(self._build_options_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

        scroll.setWidget(inner)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    # ── Cards ──────────────────────────────────────────────────────────────────

    def _build_source_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_src = _section_header(tr("hdr_source_video"))
        layout.addWidget(self._hdr_src)

        row = QHBoxLayout()
        self._file_input = QLineEdit()
        self._file_input.setObjectName("PillInput")
        self._file_input.setPlaceholderText(tr("ph_vid"))
        row.addWidget(self._file_input)

        self._browse_src_btn = QPushButton(tr("btn_browse"))
        self._browse_src_btn.setObjectName("BrowseBtn")
        self._browse_src_btn.setFixedWidth(90)
        self._browse_src_btn.clicked.connect(self._browse_file)
        row.addWidget(self._browse_src_btn)
        layout.addLayout(row)
        return card

    def _build_options_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_opts = _section_header(tr("hdr_gif_opts"))
        layout.addWidget(self._hdr_opts)

        row1 = QHBoxLayout()
        self._gif_lbl_start = QLabel(tr("lbl_start_time_s"))
        row1.addWidget(self._gif_lbl_start)
        row1.addStretch()
        self._start_spin = QSpinBox()
        self._start_spin.setRange(0, 86400)
        self._start_spin.setValue(0)
        self._start_spin.setFixedWidth(80)
        self._start_spin.setToolTip(tr("tooltip_gif_start_s"))
        row1.addWidget(self._start_spin)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        self._gif_lbl_dur = QLabel(tr("lbl_duration_s"))
        row2.addWidget(self._gif_lbl_dur)
        row2.addStretch()
        self._dur_spin = QSpinBox()
        self._dur_spin.setRange(1, 300)
        self._dur_spin.setValue(5)
        self._dur_spin.setFixedWidth(80)
        row2.addWidget(self._dur_spin)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        self._gif_lbl_width = QLabel(tr("lbl_width_px"))
        row3.addWidget(self._gif_lbl_width)
        row3.addStretch()
        self._width_spin = QSpinBox()
        self._width_spin.setRange(64, 1920)
        self._width_spin.setValue(480)
        self._width_spin.setSingleStep(16)
        self._width_spin.setFixedWidth(80)
        row3.addWidget(self._width_spin)
        layout.addLayout(row3)

        row4 = QHBoxLayout()
        self._gif_lbl_fps = QLabel(tr("lbl_fps"))
        row4.addWidget(self._gif_lbl_fps)
        row4.addStretch()
        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(1, 30)
        self._fps_spin.setValue(15)
        self._fps_spin.setFixedWidth(80)
        row4.addWidget(self._fps_spin)
        layout.addLayout(row4)

        return card

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_out = _section_header(tr("hdr_output_folder"))
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

    # ── Browse handlers ────────────────────────────────────────────────────────


    def retranslate_ui(self) -> None:
        self._hdr_src.setText(tr("hdr_source_video"))
        self._file_input.setPlaceholderText(tr("ph_vid"))
        self._browse_src_btn.setText(tr("btn_browse"))
        self._hdr_opts.setText(tr("hdr_gif_opts"))
        self._gif_lbl_start.setText(tr("lbl_start_time_s"))
        self._gif_lbl_dur.setText(tr("lbl_duration_s"))
        self._gif_lbl_width.setText(tr("lbl_width_px"))
        self._gif_lbl_fps.setText(tr("lbl_fps"))
        self._start_spin.setToolTip(tr("tooltip_gif_start_s"))
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._out_input.setPlaceholderText(tr("ph_same_dir"))
        self._browse_out_btn.setText(tr("btn_browse"))

    def _browse_file(self) -> None:
        start = os.path.dirname(self._file_input.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Video",
            start,
            "Video files (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.m4v)",
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
            self.status_message.emit("Please select a valid video file.", True)
            return

        start = self._start_spin.value()
        duration = self._dur_spin.value()
        width = self._width_spin.value()
        fps = self._fps_spin.value()
        out_dir = self._out_input.text().strip() or os.path.dirname(src)

        self._set_busy(True)
        self.status_message.emit(tr("dyn_creating_gif"), False)

        def do_gif():
            base = os.path.splitext(os.path.basename(src))[0]
            os.makedirs(out_dir, exist_ok=True)
            dest = os.path.join(out_dir, f"{base}.gif")
            flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
            # Two-pass palette method for high-quality GIFs
            vf = (
                f"fps={fps},scale={width}:-1:flags=lanczos,"
                "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
            )
            cmd = [
                ffmpeg_path, "-y",
                "-ss", str(start),
                "-t", str(duration),
                "-i", src,
                "-vf", vf,
                dest,
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=600, **flags)
                return {"success": True, "file_path": dest}
            except Exception as exc:
                return {"success": False, "error": str(exc)}

        self._worker = Worker(do_gif)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if busy:
            self._progress_label.setText(tr("dyn_creating_gif"))
        self.busy_changed.emit(busy)

    def _on_result(self, result: dict) -> None:
        self._set_busy(False)
        self._worker = None
        src = self._file_input.text()
        if result.get("success"):
            fp = result["file_path"]
            self._last_result_path = fp
            fn = os.path.basename(fp)
            get_history_manager().add_item(
                HistoryItem(task_type="gif", file_name=fn, file_path=fp, status="success")
            )
            self.status_message.emit(f"Done → {fn}", False)
        else:
            err = result.get("error") or "GIF creation failed."
            get_history_manager().add_item(
                HistoryItem(
                    task_type="gif",
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
