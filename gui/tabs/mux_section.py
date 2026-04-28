"""Audio/Video Muxing tab — Mute Video, Replace Audio, and Add Audio sub-tabs."""
from __future__ import annotations

import os

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
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from core.muxer import mix_audio_overlay, mute_video, replace_audio
from gui.worker import Worker

_VIDEO_EXTS = "Video (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.m4v)"
_AUDIO_EXTS = "Audio (*.mp3 *.wav *.aac *.flac *.ogg *.m4a *.opus)"


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


def _file_row(placeholder: str, filter_str: str, parent: QWidget):
    """Return (QLineEdit, QPushButton, QHBoxLayout) for a file-picker row."""
    row = QHBoxLayout()
    inp = QLineEdit()
    inp.setObjectName("PillInput")
    inp.setPlaceholderText(placeholder)
    row.addWidget(inp)

    btn = QPushButton("Browse…")
    btn.setObjectName("BrowseBtn")
    btn.setFixedWidth(90)
    row.addWidget(btn)
    return inp, btn, row


class _MutePane(QWidget):
    """Mute Video sub-tab — strips the audio track."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_result_path: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_source_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

    def _build_source_card(self) -> QFrame:
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        v.addWidget(_section_header("VIDEO FILE"))

        self._video_inp, browse_btn, row = _file_row("Video file to mute…", _VIDEO_EXTS, self)
        browse_btn.clicked.connect(self._browse_video)
        v.addLayout(row)
        return card

    def _build_output_card(self) -> QFrame:
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        v.addWidget(_section_header("OUTPUT FOLDER"))

        self._out_inp, browse_btn, row = _file_row("Same directory as source file", "", self)
        if self._settings.output_folder:
            self._out_inp.setText(self._settings.output_folder)
        browse_btn.clicked.connect(self._browse_output)
        v.addLayout(row)
        return card

    def _build_progress_card(self) -> QFrame:
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(8)

        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("TaskProgressBar")
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setVisible(False)
        v.addWidget(self._progress_bar)

        self._progress_label = QLabel()
        self._progress_label.setObjectName("TextSecondary")
        self._progress_label.setVisible(False)
        v.addWidget(self._progress_label)
        return card

    def _browse_video(self) -> None:
        start = os.path.dirname(self._video_inp.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "Select Video File", start, _VIDEO_EXTS)
        if path:
            self._video_inp.setText(path)

    def _browse_output(self) -> None:
        start = self._out_inp.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if d:
            self._out_inp.setText(d)

    def populate_file(self, path: str) -> None:
        self._video_inp.setText(path)

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        src = self._video_inp.text().strip()
        if not src or not os.path.isfile(src):
            self.status_message.emit("Please select a valid video file.", True)
            return

        out_dir = self._out_inp.text().strip() or None
        self._set_busy(True)
        self.status_message.emit("Muting video…", False)

        def do_mute():
            return mute_video(src, out_dir)

        self._worker = Worker(do_mute)
        self._worker.signals.result.connect(lambda ok: self._on_result(ok, src, out_dir))
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if busy:
            self._progress_label.setText("Stripping audio track…")
        self.busy_changed.emit(busy)

    def _on_result(self, success: bool, src: str, out_dir: str | None) -> None:
        self._set_busy(False)
        self._worker = None
        base = os.path.splitext(os.path.basename(src))[0]
        ext = os.path.splitext(src)[1]
        resolved_dir = out_dir or os.path.dirname(src)
        out_path = os.path.join(resolved_dir, f"{base}_muted{ext}")

        if success:
            self._last_result_path = out_path
            get_history_manager().add_item(
                HistoryItem(task_type="mux", file_name=os.path.basename(out_path),
                            file_path=out_path, status="success")
            )
            self.status_message.emit(f"Done → {os.path.basename(out_path)}", False)
        else:
            get_history_manager().add_item(
                HistoryItem(task_type="mux", file_name=os.path.basename(src),
                            file_path=src, status="error")
            )
            self.status_message.emit("Mute failed. Check the file is a valid video.", True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)


class _ReplaceAudioPane(QWidget):
    """Replace Audio sub-tab — swaps the audio track of a video."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_result_path: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_inputs_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

    def _build_inputs_card(self) -> QFrame:
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)

        v.addWidget(_section_header("VIDEO FILE"))
        self._video_inp, browse_vid, row_vid = _file_row("Video file (source of visuals)…", _VIDEO_EXTS, self)
        browse_vid.clicked.connect(self._browse_video)
        v.addLayout(row_vid)

        v.addWidget(_section_header("NEW AUDIO FILE"))
        self._audio_inp, browse_aud, row_aud = _file_row("Audio file (new sound track)…", _AUDIO_EXTS, self)
        browse_aud.clicked.connect(self._browse_audio)
        v.addLayout(row_aud)

        hint = QLabel(
            "Output stops at whichever stream ends first (FFmpeg -shortest flag). "
            "If the audio is longer than the video, the extra audio is discarded."
        )
        hint.setObjectName("TextMuted")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px;")
        v.addWidget(hint)
        return card

    def _build_output_card(self) -> QFrame:
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        v.addWidget(_section_header("OUTPUT FOLDER"))

        self._out_inp, browse_btn, row = _file_row("Same directory as video file", "", self)
        if self._settings.output_folder:
            self._out_inp.setText(self._settings.output_folder)
        browse_btn.clicked.connect(self._browse_output)
        v.addLayout(row)
        return card

    def _build_progress_card(self) -> QFrame:
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(8)

        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("TaskProgressBar")
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setVisible(False)
        v.addWidget(self._progress_bar)

        self._progress_label = QLabel()
        self._progress_label.setObjectName("TextSecondary")
        self._progress_label.setVisible(False)
        v.addWidget(self._progress_label)
        return card

    def _browse_video(self) -> None:
        start = os.path.dirname(self._video_inp.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "Select Video File", start, _VIDEO_EXTS)
        if path:
            self._video_inp.setText(path)

    def _browse_audio(self) -> None:
        start = os.path.dirname(self._audio_inp.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "Select New Audio File", start, _AUDIO_EXTS)
        if path:
            self._audio_inp.setText(path)

    def _browse_output(self) -> None:
        start = self._out_inp.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if d:
            self._out_inp.setText(d)

    def populate_file(self, path: str) -> None:
        self._video_inp.setText(path)

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        vid = self._video_inp.text().strip()
        aud = self._audio_inp.text().strip()

        if not vid or not os.path.isfile(vid):
            self.status_message.emit("Please select a valid video file.", True)
            return
        if not aud or not os.path.isfile(aud):
            self.status_message.emit("Please select a valid audio file.", True)
            return

        out_dir = self._out_inp.text().strip() or None
        self._set_busy(True)
        self.status_message.emit("Replacing audio track…", False)

        def do_replace():
            return replace_audio(vid, aud, out_dir)

        self._worker = Worker(do_replace)
        self._worker.signals.result.connect(lambda ok: self._on_result(ok, vid, out_dir))
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if busy:
            self._progress_label.setText("Replacing audio track…")
        self.busy_changed.emit(busy)

    def _on_result(self, success: bool, vid: str, out_dir: str | None) -> None:
        self._set_busy(False)
        self._worker = None
        base = os.path.splitext(os.path.basename(vid))[0]
        ext = os.path.splitext(vid)[1]
        resolved_dir = out_dir or os.path.dirname(vid)
        out_path = os.path.join(resolved_dir, f"{base}_remuxed{ext}")

        if success:
            self._last_result_path = out_path
            get_history_manager().add_item(
                HistoryItem(task_type="mux", file_name=os.path.basename(out_path),
                            file_path=out_path, status="success")
            )
            self.status_message.emit(f"Done → {os.path.basename(out_path)}", False)
        else:
            get_history_manager().add_item(
                HistoryItem(task_type="mux", file_name=os.path.basename(vid),
                            file_path=vid, status="error")
            )
            self.status_message.emit("Replace failed. Check the files are valid.", True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)


class _AddAudioPane(QWidget):
    """Add Audio sub-tab — mixes an audio file over the video's existing audio."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_result_path: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_inputs_card())
        layout.addWidget(self._build_volume_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

    def _build_inputs_card(self) -> QFrame:
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)

        v.addWidget(_section_header("VIDEO FILE"))
        self._video_inp, browse_vid, row_vid = _file_row(
            "Video file (keeps its own audio)…", _VIDEO_EXTS, self
        )
        browse_vid.clicked.connect(self._browse_video)
        v.addLayout(row_vid)

        v.addWidget(_section_header("AUDIO FILE TO ADD"))
        self._audio_inp, browse_aud, row_aud = _file_row(
            "Audio file to mix in…", _AUDIO_EXTS, self
        )
        browse_aud.clicked.connect(self._browse_audio)
        v.addLayout(row_aud)

        hint = QLabel(
            "The video's original audio is preserved. The added audio is mixed on top. "
            "Output length matches the video — any extra audio is discarded."
        )
        hint.setObjectName("TextMuted")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px;")
        v.addWidget(hint)
        return card

    def _build_volume_card(self) -> QFrame:
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        v.addWidget(_section_header("ADDED AUDIO VOLUME"))

        row = QHBoxLayout()
        row.setSpacing(12)

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 200)   # 0% – 200%
        self._vol_slider.setValue(100)       # default 100%
        self._vol_slider.setTickInterval(25)
        self._vol_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        row.addWidget(self._vol_slider, 1)

        self._vol_label = QLabel("100%")
        self._vol_label.setFixedWidth(44)
        self._vol_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self._vol_label)

        v.addLayout(row)

        tick_row = QHBoxLayout()
        tick_row.setContentsMargins(0, 0, 44 + 12, 0)
        for pct in ("0%", "50%", "100%", "150%", "200%"):
            lbl = QLabel(pct)
            lbl.setObjectName("TextMuted")
            lbl.setStyleSheet("font-size: 10px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            tick_row.addWidget(lbl, 1)
        v.addLayout(tick_row)
        return card

    def _build_output_card(self) -> QFrame:
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        v.addWidget(_section_header("OUTPUT FOLDER"))

        self._out_inp, browse_btn, row = _file_row("Same directory as video file", "", self)
        if self._settings.output_folder:
            self._out_inp.setText(self._settings.output_folder)
        browse_btn.clicked.connect(self._browse_output)
        v.addLayout(row)
        return card

    def _build_progress_card(self) -> QFrame:
        card = _card()
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(8)

        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("TaskProgressBar")
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setVisible(False)
        v.addWidget(self._progress_bar)

        self._progress_label = QLabel()
        self._progress_label.setObjectName("TextSecondary")
        self._progress_label.setVisible(False)
        v.addWidget(self._progress_label)
        return card

    def _on_volume_changed(self, value: int) -> None:
        self._vol_label.setText(f"{value}%")

    def _browse_video(self) -> None:
        start = os.path.dirname(self._video_inp.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "Select Video File", start, _VIDEO_EXTS)
        if path:
            self._video_inp.setText(path)

    def _browse_audio(self) -> None:
        start = os.path.dirname(self._audio_inp.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "Select Audio File", start, _AUDIO_EXTS)
        if path:
            self._audio_inp.setText(path)

    def _browse_output(self) -> None:
        start = self._out_inp.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if d:
            self._out_inp.setText(d)

    def populate_file(self, path: str) -> None:
        self._video_inp.setText(path)

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        vid = self._video_inp.text().strip()
        aud = self._audio_inp.text().strip()

        if not vid or not os.path.isfile(vid):
            self.status_message.emit("Please select a valid video file.", True)
            return
        if not aud or not os.path.isfile(aud):
            self.status_message.emit("Please select a valid audio file.", True)
            return

        volume = self._vol_slider.value() / 100.0
        out_dir = self._out_inp.text().strip() or None
        self._set_busy(True)
        self.status_message.emit("Mixing audio…", False)

        def do_mix():
            return mix_audio_overlay(vid, aud, volume, out_dir)

        self._worker = Worker(do_mix)
        self._worker.signals.result.connect(lambda ok: self._on_result(ok, vid, out_dir))
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if busy:
            self._progress_label.setText("Mixing audio tracks…")
        self.busy_changed.emit(busy)

    def _on_result(self, success: bool, vid: str, out_dir: str | None) -> None:
        self._set_busy(False)
        self._worker = None
        base = os.path.splitext(os.path.basename(vid))[0]
        ext = os.path.splitext(vid)[1]
        resolved_dir = out_dir or os.path.dirname(vid)
        out_path = os.path.join(resolved_dir, f"{base}_mixed{ext}")

        if success:
            self._last_result_path = out_path
            get_history_manager().add_item(
                HistoryItem(task_type="mux", file_name=os.path.basename(out_path),
                            file_path=out_path, status="success")
            )
            self.status_message.emit(f"Done → {os.path.basename(out_path)}", False)
        else:
            get_history_manager().add_item(
                HistoryItem(task_type="mux", file_name=os.path.basename(vid),
                            file_path=vid, status="error")
            )
            self.status_message.emit("Mix failed. Check the files are valid.", True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)


class MuxSection(QWidget):
    """Audio/Video Muxing section — Mute Video and Replace Audio sub-tabs."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        self._mute_pane = _MutePane(settings)
        self._replace_pane = _ReplaceAudioPane(settings)
        self._add_pane = _AddAudioPane(settings)
        self._stack.addWidget(self._mute_pane)    # index 0 — MUTE VIDEO
        self._stack.addWidget(self._replace_pane) # index 1 — REPLACE AUDIO
        self._stack.addWidget(self._add_pane)     # index 2 — ADD AUDIO

        root.addWidget(self._stack)
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Bubble signals from active pane
        for pane in (self._mute_pane, self._replace_pane, self._add_pane):
            pane.status_message.connect(self.status_message)
            pane.busy_changed.connect(self.busy_changed)

    def on_sub_tab_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)

    def trigger_primary_action(self) -> None:
        pane = self._stack.currentWidget()
        if hasattr(pane, "trigger_primary_action"):
            pane.trigger_primary_action()

    def populate_file(self, path: str) -> None:
        self._mute_pane.populate_file(path)
        self._replace_pane.populate_file(path)
        self._add_pane.populate_file(path)

    @property
    def _last_result_path(self) -> str | None:
        pane = self._stack.currentWidget()
        return getattr(pane, "_last_result_path", None)
