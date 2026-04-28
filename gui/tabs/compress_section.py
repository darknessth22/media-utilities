"""Compress Media tab — auto-detects image or video and compresses accordingly."""
from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.history.manager import get_history_manager
from core.history.models import HistoryItem
from gui.presets_bar import PresetsBar
from gui.worker import Worker
from utils.ffmpeg import ffmpeg_path, detect_hw_encoders

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v"}


def _detect_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _VIDEO_EXTS:
        return "video"
    return "unknown"


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


class CompressSection(QWidget):
    """Compress images or videos — auto-detects file type and shows relevant options."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: Worker | None = None
        self._last_result_path: str | None = None
        self._media_type = "unknown"
        self._available_hw: set[str] = detect_hw_encoders()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_presets_card())
        layout.addWidget(self._build_source_card())
        layout.addWidget(self._build_options_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_progress_card())

        scroll.setWidget(inner)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    # ── Preset support ─────────────────────────────────────────────────────────

    def get_preset_data(self) -> dict:
        return {
            "img_quality": self._quality_spin.value(),
            "img_max_dim": self._max_dim_spin.value(),
            "vid_crf": self._crf_spin.value(),
            "vid_preset": self._preset_combo.currentText(),
            "vid_hw": self._hw_combo.currentData(),
            "output_dir": self._out_input.text().strip(),
        }

    def load_preset_data(self, data: dict) -> None:
        if (q := data.get("img_quality")) is not None:
            self._quality_spin.setValue(q)
        if (d := data.get("img_max_dim")) is not None:
            self._max_dim_spin.setValue(d)
        if hw := data.get("vid_hw"):
            idx = self._hw_combo.findData(hw)
            if idx >= 0:
                self._hw_combo.setCurrentIndex(idx)
        if (crf := data.get("vid_crf")) is not None:
            self._crf_spin.setValue(crf)
        if p := data.get("vid_preset"):
            idx = self._preset_combo.findText(p)
            if idx >= 0:
                self._preset_combo.setCurrentIndex(idx)
        if out := data.get("output_dir"):
            self._out_input.setText(out)

    def _build_presets_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(0)
        layout.addWidget(
            PresetsBar(
                "compress",
                self._settings,
                self.get_preset_data,
                self.load_preset_data,
            )
        )
        return card

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
        self._file_input.setPlaceholderText("Image or video file…")
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

    def _build_options_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("COMPRESSION OPTIONS"))

        # Stacked: index 0 = image opts, index 1 = video opts, index 2 = placeholder
        self._opts_stack = QStackedWidget()

        # ── Image options ──────────────────────────────────────────────────────
        img_widget = QWidget()
        img_layout = QVBoxLayout(img_widget)
        img_layout.setContentsMargins(0, 0, 0, 0)
        img_layout.setSpacing(8)

        q_row = QHBoxLayout()
        q_row.addWidget(QLabel("Quality  (1–100)"))
        q_hint = QLabel("Higher = better quality, larger file")
        q_hint.setObjectName("TextMuted")
        q_hint.setStyleSheet("font-size: 11px;")
        q_row.addWidget(q_hint)
        q_row.addStretch()
        self._quality_spin = QSpinBox()
        self._quality_spin.setRange(1, 100)
        self._quality_spin.setValue(85)
        self._quality_spin.setFixedWidth(60)
        q_row.addWidget(self._quality_spin)
        img_layout.addLayout(q_row)

        dim_row = QHBoxLayout()
        dim_row.addWidget(QLabel("Max dimension (px)"))
        dim_hint = QLabel("0 = keep original size")
        dim_hint.setObjectName("TextMuted")
        dim_hint.setStyleSheet("font-size: 11px;")
        dim_row.addWidget(dim_hint)
        dim_row.addStretch()
        self._max_dim_spin = QSpinBox()
        self._max_dim_spin.setRange(0, 16000)
        self._max_dim_spin.setValue(0)
        self._max_dim_spin.setSingleStep(100)
        self._max_dim_spin.setFixedWidth(80)
        dim_row.addWidget(self._max_dim_spin)
        img_layout.addLayout(dim_row)

        self._opts_stack.addWidget(img_widget)

        # ── Video options ──────────────────────────────────────────────────────
        vid_widget = QWidget()
        vid_layout = QVBoxLayout(vid_widget)
        vid_layout.setContentsMargins(0, 0, 0, 0)
        vid_layout.setSpacing(8)

        crf_row = QHBoxLayout()
        crf_row.addWidget(QLabel("CRF  (18–51)"))
        crf_hint = QLabel("Lower = better quality, larger file  ·  28 is a good default")
        crf_hint.setObjectName("TextMuted")
        crf_hint.setStyleSheet("font-size: 11px;")
        crf_row.addWidget(crf_hint)
        crf_row.addStretch()
        self._crf_spin = QSpinBox()
        self._crf_spin.setRange(18, 51)
        self._crf_spin.setValue(28)
        self._crf_spin.setFixedWidth(80)
        crf_row.addWidget(self._crf_spin)
        vid_layout.addLayout(crf_row)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset"))
        self._preset_hint = QLabel("Slower = smaller file at same quality")
        self._preset_hint.setObjectName("TextMuted")
        self._preset_hint.setStyleSheet("font-size: 11px;")
        preset_row.addWidget(self._preset_hint)
        preset_row.addStretch()
        self._preset_combo = QComboBox()
        self._preset_combo.addItems([
            "ultrafast", "superfast", "veryfast", "faster",
            "fast", "medium", "slow", "slower", "veryslow",
        ])
        self._preset_combo.setCurrentText("medium")
        self._preset_combo.setFixedWidth(110)
        preset_row.addWidget(self._preset_combo)
        vid_layout.addLayout(preset_row)

        hw_row = QHBoxLayout()
        hw_row.addWidget(QLabel("Hardware Acceleration"))
        hw_hint = QLabel("GPU encoder — faster encode, slightly lower quality ceiling")
        hw_hint.setObjectName("TextMuted")
        hw_hint.setStyleSheet("font-size: 11px;")
        hw_row.addWidget(hw_hint)
        hw_row.addStretch()
        self._hw_combo = QComboBox()
        self._hw_combo.setFixedWidth(130)
        self._hw_combo.addItem("None (CPU)", "none")
        if "nvidia" in self._available_hw:
            self._hw_combo.addItem("NVIDIA (NVENC)", "nvidia")
        if "amd" in self._available_hw:
            self._hw_combo.addItem("AMD (AMF)", "amd")
        if "intel" in self._available_hw:
            self._hw_combo.addItem("Intel (QuickSync)", "intel")
        saved_hw = getattr(self._settings, "hw_accel", "none")
        idx = self._hw_combo.findData(saved_hw)
        if idx >= 0:
            self._hw_combo.setCurrentIndex(idx)
        self._hw_combo.currentIndexChanged.connect(self._on_hw_changed)
        hw_row.addWidget(self._hw_combo)
        vid_layout.addLayout(hw_row)

        self._opts_stack.addWidget(vid_widget)

        # ── Placeholder ────────────────────────────────────────────────────────
        placeholder = QWidget()
        ph_layout = QVBoxLayout(placeholder)
        ph_layout.setContentsMargins(0, 0, 0, 0)
        ph_lbl = QLabel("Browse a file to see compression options.")
        ph_lbl.setObjectName("TextMuted")
        ph_lbl.setStyleSheet("font-size: 12px;")
        ph_layout.addWidget(ph_lbl)
        self._opts_stack.addWidget(placeholder)

        self._opts_stack.setCurrentIndex(2)  # placeholder until file chosen
        layout.addWidget(self._opts_stack)
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

    _PRESET_OPTIONS = {
        "none":   (["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"], "medium", "Slower = smaller file at same quality"),
        "nvidia": (["p1", "p2", "p3", "p4", "p5", "p6", "p7"], "p4", "p1 = fastest · p7 = best quality — file size controlled by QP, not preset"),
        "amd":    (["speed", "balanced", "quality"], "balanced", "Tradeoff between encode speed and compression"),
        "intel":  (["veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"], "medium", "Slower = smaller file at same quality"),
    }

    def _on_hw_changed(self, _idx: int) -> None:
        hw = self._hw_combo.currentData()
        presets, default, hint = self._PRESET_OPTIONS.get(hw, self._PRESET_OPTIONS["none"])
        self._preset_combo.blockSignals(True)
        self._preset_combo.clear()
        self._preset_combo.addItems(presets)
        self._preset_combo.setCurrentText(default)
        self._preset_combo.blockSignals(False)
        self._preset_hint.setText(hint)

    # ── Source change handler ──────────────────────────────────────────────────

    def _on_source_changed(self, path: str) -> None:
        path = path.strip()
        mt = _detect_type(path) if os.path.isfile(path) else "unknown"
        self._media_type = mt
        label_map = {"image": "Image file", "video": "Video file"}
        self._type_label.setText(label_map.get(mt, ""))
        if mt == "image":
            self._opts_stack.setCurrentIndex(0)
        elif mt == "video":
            self._opts_stack.setCurrentIndex(1)
        else:
            self._opts_stack.setCurrentIndex(2)

    # ── Browse helpers ─────────────────────────────────────────────────────────

    def _browse_file(self) -> None:
        start = os.path.dirname(self._file_input.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image or Video",
            start,
            "Media files (*.jpg *.jpeg *.png *.webp *.bmp "
            "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.m4v)",
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
            self.status_message.emit("Please select a valid file.", True)
            return
        if self._media_type == "unknown":
            self.status_message.emit("Unsupported file type.", True)
            return

        out_dir = self._out_input.text().strip() or os.path.dirname(src)
        self._set_busy(True)
        self.status_message.emit("Compressing…", False)

        if self._media_type == "image":
            quality = self._quality_spin.value()
            max_dim = self._max_dim_spin.value()

            def do_work():
                return _compress_image(src, out_dir, quality, max_dim)
        else:
            crf = self._crf_spin.value()
            preset = self._preset_combo.currentText()
            hw_accel = self._hw_combo.currentData()

            def do_work():
                return _compress_video(src, out_dir, crf, preset, hw_accel)

        self._worker = Worker(do_work)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if busy:
            self._progress_label.setText("Compressing…")
        self.busy_changed.emit(busy)

    def _on_result(self, result: dict) -> None:
        self._set_busy(False)
        self._worker = None
        src = self._file_input.text()
        if result.get("success"):
            fp = result["file_path"]
            self._last_result_path = fp
            fn = os.path.basename(fp)
            ratio = result.get("ratio", 0)
            get_history_manager().add_item(
                HistoryItem(task_type="compress", file_name=fn, file_path=fp, status="success")
            )
            self.status_message.emit(f"Done → {fn}  ({ratio:.0f}% smaller)", False)
        else:
            err = result.get("error") or "Compression failed."
            get_history_manager().add_item(
                HistoryItem(
                    task_type="compress",
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


# ── Worker functions (run in background thread) ────────────────────────────────

def _compress_image(src: str, out_dir: str, quality: int, max_dim: int) -> dict:
    from PIL import Image
    try:
        base, ext = os.path.splitext(os.path.basename(src))
        os.makedirs(out_dir, exist_ok=True)
        dest_ext = ext.lower() if ext.lower() in {".jpg", ".jpeg", ".webp"} else ".jpg"
        dest = os.path.join(out_dir, f"{base}_compressed{dest_ext}")

        with Image.open(src) as img:
            if img.mode in ("RGBA", "P") and dest_ext in (".jpg", ".jpeg"):
                img = img.convert("RGB")
            if max_dim > 0:
                img.thumbnail((max_dim, max_dim), Image.LANCZOS)

            fmt = "JPEG" if dest_ext in (".jpg", ".jpeg") else dest_ext.lstrip(".").upper()
            if fmt == "PNG":
                img.save(dest, fmt, optimize=True)
            elif fmt == "WEBP":
                img.save(dest, fmt, quality=quality, method=6)
            else:
                img.save(dest, fmt, quality=quality, optimize=True)

        orig_size = os.path.getsize(src)
        new_size = os.path.getsize(dest)
        ratio = (1 - new_size / orig_size) * 100 if orig_size else 0
        return {"success": True, "file_path": dest, "ratio": ratio}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _build_video_cmd(src: str, dest: str, crf: int, preset: str, hw_accel: str) -> list[str]:
    base = [ffmpeg_path, "-y", "-i", src]
    audio = ["-c:a", "copy"]

    if hw_accel == "nvidia":
        # constqp = true constant-quality mode; -b:v 0 disables bitrate target so
        # the encoder doesn't overshoot the original file size
        return [*base, "-c:v", "h264_nvenc", "-preset", preset, "-rc", "constqp", "-qp", str(crf), "-b:v", "0", *audio, dest]

    if hw_accel == "amd":
        # AMF constant-QP mode; set all three QP params so B-frames don't drift
        return [*base, "-c:v", "h264_amf", "-quality", preset,
                "-rc", "1", "-qp_i", str(crf), "-qp_p", str(crf), "-qp_b", str(crf), *audio, dest]

    if hw_accel == "intel":
        # QSV global_quality is equivalent to CRF; look_ahead improves efficiency
        return [*base, "-c:v", "h264_qsv", "-preset", preset, "-global_quality", str(crf), "-look_ahead", "1", *audio, dest]

    # CPU default
    return [*base, "-c:v", "libx264", "-crf", str(crf), "-preset", preset, *audio, dest]


def _compress_video(src: str, out_dir: str, crf: int, preset: str, hw_accel: str = "none") -> dict:
    try:
        ext = os.path.splitext(src)[1].lower() or ".mp4"
        base = os.path.splitext(os.path.basename(src))[0]
        os.makedirs(out_dir, exist_ok=True)
        dest = os.path.join(out_dir, f"{base}_compressed{ext}")
        flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

        cmd = _build_video_cmd(src, dest, crf, preset, hw_accel)
        subprocess.run(cmd, check=True, capture_output=True, timeout=7200, **flags)

        orig_size = os.path.getsize(src)
        new_size = os.path.getsize(dest)
        ratio = (1 - new_size / orig_size) * 100 if orig_size else 0
        return {"success": True, "file_path": dest, "ratio": ratio}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
