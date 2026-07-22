"""Merge Videos tab — concatenates multiple video files via FFmpeg concat demuxer."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

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
from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.worker import Worker
from utils.ffmpeg import ffmpeg_path, ffprobe_path


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


class MergeSection(QWidget):
    """Section widget: merge multiple video files into one."""

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

        layout.addWidget(self._build_files_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

        scroll.setWidget(inner)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    # ── Cards ──────────────────────────────────────────────────────────────────

    def _build_files_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_files = _section_header(tr("hdr_video_files_list"))
        layout.addWidget(self._hdr_files)

        self._file_list = QListWidget()
        self._file_list.setObjectName("FileList")
        self._file_list.setFixedHeight(180)
        self._file_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        layout.addWidget(self._file_list)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._merge_add_btn = QPushButton(tr("btn_add_files"))
        self._merge_add_btn.setObjectName("BrowseBtn")
        self._merge_add_btn.clicked.connect(self._add_files)
        btn_row.addWidget(self._merge_add_btn)

        self._merge_up_btn = QPushButton("▲")
        self._merge_up_btn.setObjectName("BrowseBtn")
        self._merge_up_btn.setFixedWidth(36)
        self._merge_up_btn.setToolTip(tr("tip_merge_move_up"))
        self._merge_up_btn.clicked.connect(self._move_up)
        btn_row.addWidget(self._merge_up_btn)

        self._merge_down_btn = QPushButton("▼")
        self._merge_down_btn.setObjectName("BrowseBtn")
        self._merge_down_btn.setFixedWidth(36)
        self._merge_down_btn.setToolTip(tr("tip_merge_move_down"))
        self._merge_down_btn.clicked.connect(self._move_down)
        btn_row.addWidget(self._merge_down_btn)

        self._merge_remove_btn = QPushButton(tr("btn_remove"))
        self._merge_remove_btn.setObjectName("BrowseBtn")
        self._merge_remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(self._merge_remove_btn)

        self._merge_clear_btn = QPushButton(tr("btn_clear_all"))
        self._merge_clear_btn.setObjectName("BrowseBtn")
        self._merge_clear_btn.clicked.connect(self._file_list.clear)
        btn_row.addWidget(self._merge_clear_btn)

        layout.addLayout(btn_row)
        return card

    def _build_output_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_out = _section_header(tr("hdr_output_folder"))
        layout.addWidget(self._hdr_out)

        self._lbl_merge_fn = QLabel(tr("lbl_output_filename"))
        layout.addWidget(self._lbl_merge_fn)
        self._name_input = QLineEdit()
        self._name_input.setObjectName("PillInput")
        self._name_input.setPlaceholderText(tr("ph_merged_mp4"))
        layout.addWidget(self._name_input)

        self._lbl_merge_folder = QLabel(tr("lbl_output_folder_lbl"))
        layout.addWidget(self._lbl_merge_folder)
        row = QHBoxLayout()
        self._out_input = QLineEdit()
        self._out_input.setObjectName("PillInput")
        self._out_input.setPlaceholderText(tr("ph_first_video"))
        if self._settings.output_folder:
            self._out_input.setText(self._settings.output_folder)
        row.addWidget(self._out_input)

        self._merge_browse_out_btn = QPushButton(tr("btn_browse"))
        self._merge_browse_out_btn.setObjectName("BrowseBtn")
        self._merge_browse_out_btn.setFixedWidth(90)
        self._merge_browse_out_btn.clicked.connect(self._browse_output)
        row.addWidget(self._merge_browse_out_btn)
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

    # ── List helpers ───────────────────────────────────────────────────────────

    def populate_files(self, paths: list[str]) -> None:
        """Append dropped/external file paths into the merge list (dedup)."""
        for p in paths:
            existing = [self._file_list.item(i).text() for i in range(self._file_list.count())]
            if p not in existing:
                self._file_list.addItem(QListWidgetItem(p))

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Video Files",
            os.path.expanduser("~"),
            "Video files (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.m4v)",
        )
        for p in paths:
            existing = [self._file_list.item(i).text() for i in range(self._file_list.count())]
            if p not in existing:
                self._file_list.addItem(QListWidgetItem(p))

    def _move_up(self) -> None:
        row = self._file_list.currentRow()
        if row > 0:
            item = self._file_list.takeItem(row)
            self._file_list.insertItem(row - 1, item)
            self._file_list.setCurrentRow(row - 1)

    def _move_down(self) -> None:
        row = self._file_list.currentRow()
        if 0 <= row < self._file_list.count() - 1:
            item = self._file_list.takeItem(row)
            self._file_list.insertItem(row + 1, item)
            self._file_list.setCurrentRow(row + 1)

    def _remove_selected(self) -> None:
        row = self._file_list.currentRow()
        if row >= 0:
            self._file_list.takeItem(row)


    def retranslate_ui(self) -> None:
        self._hdr_files.setText(tr("hdr_video_files_list"))
        self._merge_add_btn.setText(tr("btn_add_files"))
        self._merge_up_btn.setToolTip(tr("tip_merge_move_up"))
        self._merge_down_btn.setToolTip(tr("tip_merge_move_down"))
        self._merge_remove_btn.setText(tr("btn_remove"))
        self._merge_clear_btn.setText(tr("btn_clear_all"))
        self._hdr_out.setText(tr("hdr_output_folder"))
        self._lbl_merge_fn.setText(tr("lbl_output_filename"))
        self._name_input.setPlaceholderText(tr("ph_merged_mp4"))
        self._lbl_merge_folder.setText(tr("lbl_output_folder_lbl"))
        self._out_input.setPlaceholderText(tr("ph_first_video"))
        self._merge_browse_out_btn.setText(tr("btn_browse"))

    def _browse_output(self) -> None:
        start = self._out_input.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if d:
            self._out_input.setText(d)

    def add_files_from_paths(self, paths: list[str]) -> None:
        for p in paths:
            existing = [self._file_list.item(i).text() for i in range(self._file_list.count())]
            if p not in existing:
                self._file_list.addItem(QListWidgetItem(p))

    # ── Action ─────────────────────────────────────────────────────────────────

    def trigger_primary_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._set_busy(False)
            self.status_message.emit("Cancelled.", False)
            return

        paths = [self._file_list.item(i).text() for i in range(self._file_list.count())]
        if len(paths) < 2:
            self.status_message.emit("Please add at least 2 video files.", True)
            return

        out_name = self._name_input.text().strip() or "merged.mp4"
        if not os.path.splitext(out_name)[1]:
            out_name += ".mp4"
        out_dir = self._out_input.text().strip() or os.path.dirname(paths[0])

        self._set_busy(True)
        self.status_message.emit(f"Merging {len(paths)} file(s)…", False)

        def do_merge():
            import json
            os.makedirs(out_dir, exist_ok=True)
            dest = os.path.join(out_dir, out_name)
            flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

            try:
                def _probe_video(path):
                    r = subprocess.run(
                        [ffprobe_path, "-v", "error",
                         "-show_entries",
                         "stream=codec_name,width,height,r_frame_rate,codec_type"
                         ":format=bit_rate,duration",
                         "-of", "json", path],
                        capture_output=True, text=True, timeout=30, **flags,
                    )
                    data = json.loads(r.stdout)
                    streams = data.get("streams", [])
                    v = next((s for s in streams if s.get("codec_type") == "video"), {})
                    a = next((s for s in streams if s.get("codec_type") == "audio"), {})
                    fmt = data.get("format", {})
                    fmt_bitrate = int(fmt.get("bit_rate") or 0)
                    duration = float(fmt.get("duration") or 0)
                    return v, a, fmt_bitrate, duration

                infos = [_probe_video(p) for p in paths]
                v0, _, fmt_bitrate0, _ = infos[0]
                w, h = v0.get("width", 0), v0.get("height", 0)
                fps_str = v0.get("r_frame_rate", "30/1")

                # All videos compatible for stream copy?
                def _compatible(v, a, br):
                    return (
                        v.get("codec_name") == v0.get("codec_name")
                        and v.get("width") == w
                        and v.get("height") == h
                        and v.get("r_frame_rate") == fps_str
                    )

                can_copy = all(_compatible(v, a, br) for v, a, br, _ in infos)

                n = len(paths)

                if can_copy:
                    # Fast path: no re-encode, just remux
                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=".txt", delete=False, encoding="utf-8"
                    ) as f:
                        concat_file = f.name
                        for p in paths:
                            f.write(f"file '{p.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n")
                    try:
                        cmd = [
                            ffmpeg_path, "-y",
                            "-f", "concat", "-safe", "0", "-i", concat_file,
                            "-c", "copy", dest,
                        ]
                        result = subprocess.run(cmd, capture_output=True, timeout=7200, **flags)
                        if result.returncode != 0:
                            return {"success": False, "error": result.stderr.decode(errors="replace")}
                        return {"success": True, "file_path": dest, "count": n}
                    finally:
                        try:
                            os.unlink(concat_file)
                        except OSError:
                            pass
                else:
                    # Slow path: normalize to first video's resolution/fps then re-encode
                    fps_parts = fps_str.split("/")
                    fps = round(int(fps_parts[0]) / int(fps_parts[1])) if len(fps_parts) == 2 else 30

                    # Always CRF — source bitrate is codec-dependent (AV1 != h264 at same kbps)
                    video_quality_args = ["-crf", "28"]

                    inputs = []
                    for p in paths:
                        inputs.extend(["-i", p])

                    has_audio = [bool(info[1]) for info in infos]
                    durations = [info[3] for info in infos]

                    v_filters = ";".join(
                        f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={fps}[v{i}]"
                        for i in range(n)
                    )
                    # anullsrc is infinite — must trim to video duration or concat never ends
                    silence_filters = ";".join(
                        f"anullsrc=channel_layout=stereo:sample_rate=44100,"
                        f"atrim=duration={durations[i]},asetpts=PTS-STARTPTS[sil{i}]"
                        for i in range(n) if not has_audio[i]
                    )
                    audio_refs = [
                        f"[{i}:a]" if has_audio[i] else f"[sil{i}]"
                        for i in range(n)
                    ]
                    concat_in = "".join(f"[v{i}]{audio_refs[i]}" for i in range(n))
                    parts = [v_filters]
                    if silence_filters:
                        parts.append(silence_filters)
                    parts.append(f"{concat_in}concat=n={n}:v=1:a=1[outv][outa]")
                    filter_str = ";".join(parts)

                    cmd = [
                        ffmpeg_path, "-y",
                        *inputs,
                        "-filter_complex", filter_str,
                        "-map", "[outv]", "-map", "[outa]",
                        "-c:v", "libx264", *video_quality_args, "-preset", "fast",
                        "-c:a", "aac", "-b:a", "192k",
                        dest,
                    ]
                    result = subprocess.run(cmd, capture_output=True, timeout=7200, **flags)
                    if result.returncode != 0:
                        return {"success": False, "error": result.stderr.decode(errors="replace")}
                    return {"success": True, "file_path": dest, "count": n}

            except Exception as exc:
                return {"success": False, "error": str(exc)}

        self._worker = Worker(do_merge)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if busy:
            self._progress_label.setText(tr("dyn_merging"))
        self.busy_changed.emit(busy)

    def _on_result(self, result: dict) -> None:
        self._set_busy(False)
        self._worker = None
        if result.get("success"):
            fp = result["file_path"]
            self._last_result_path = fp
            fn = os.path.basename(fp)
            count = result.get("count", 0)
            get_history_manager().add_item(
                HistoryItem(task_type="merge", file_name=fn, file_path=fp, status="success")
            )
            self.status_message.emit(f"Done → {fn}  ({count} clips merged)", False)
        else:
            err = result.get("error") or "Merge failed."
            self.status_message.emit(f"Error: {err}", True)

    def _on_error(self, err_tuple: tuple) -> None:
        self._set_busy(False)
        self._worker = None
        _, msg, _ = err_tuple
        self.status_message.emit(f"Error: {msg}", True)
