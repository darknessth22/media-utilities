"""Bug Reporter section — form that sends bug reports through the Videl relay."""
from __future__ import annotations

import base64
import json
import os
import platform
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QGuiApplication, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from core.i18n import tr
from core.version import VERSION
from gui.worker import Worker

# Reports go to our Cloudflare Worker (tools/bug_relay/), which sends the email
# server-side. Never ship a mail-service key in the app: anything inside a
# public installer or APK can be extracted.
_RELAY_URL = "https://videl-bug-relay.mostafafares080.workers.dev/report"


_MAX_SHOT_BYTES = 5 * 1024 * 1024   # the relay's limit


def _save_pasted_image(image: QImage, folder: Path) -> Path:
    """Save a clipboard image for the report: PNG, or JPEG when the PNG would
    pass the relay's 5 MB limit (a full-screen 4K PNG easily does)."""
    folder.mkdir(parents=True, exist_ok=True)
    stem = folder / time.strftime("pasted-screenshot-%Y%m%d-%H%M%S")
    path = stem.with_suffix(".png")
    image.save(str(path), "PNG")
    if path.stat().st_size > _MAX_SHOT_BYTES:
        path.unlink()
        path = stem.with_suffix(".jpg")
        image.convertToFormat(QImage.Format.Format_RGB888).save(str(path), "JPEG", 85)
    return path


def _user_agent() -> str:
    """'Videl/<version> (<OS>)'. The relay shows it as "Sent from" in the email."""
    if sys.platform == "win32":
        os_name = f"Windows {platform.release()}"
    else:
        try:
            os_name = platform.freedesktop_os_release()["PRETTY_NAME"]
        except (OSError, KeyError):
            os_name = platform.system()
    return f"Videl/{VERSION} ({os_name})".encode("ascii", "ignore").decode()

_BUG_TYPES_EN = ["UI Problem", "Feature Problem", "Crash / Error", "Performance", "Other"]
_BUG_TYPES_AR = ["مشكلة واجهة", "مشكلة ميزة", "تعطل / خطأ", "أداء", "أخرى"]

_IMAGE_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".bmp": "image/bmp",
}


def _send_email(subject: str, body: str, screenshot_path: str, reporter_email: str = "") -> None:
    """Send a bug report through the relay. Runs in a Worker thread."""
    # Packaging subprocess must never send anything.
    if os.environ.get("VIDEL_PYINSTALLER_BUILD") == "1":
        return None

    payload: dict = {"subject": subject, "body": body, "reporter_email": reporter_email}
    if screenshot_path:
        path = Path(screenshot_path)
        mime = _IMAGE_MIME.get(path.suffix.lower())
        if path.is_file() and mime:
            payload["screenshot"] = {
                "name": path.name,
                "type": mime,
                "data": base64.b64encode(path.read_bytes()).decode(),
            }

    req = urllib.request.Request(
        _RELAY_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": _user_agent()},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30):
            return None
    except urllib.error.HTTPError as exc:
        # The relay explains rejections ("Screenshot is larger than 5 MB.").
        try:
            message = json.loads(exc.read().decode("utf-8")).get("message", "")
        except Exception:
            message = ""
        raise RuntimeError(message or f"HTTP {exc.code}") from None


class BugReporterSection(QScrollArea):
    """Full-page bug report form. Sends through the relay in a background thread."""

    status_message = Signal(str, bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._screenshot_path: str = ""
        self._worker: Worker | None = None
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(20)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._title_lbl = QLabel(tr("bug_reporter_page_title"))
        self._title_lbl.setStyleSheet(
            "font-size: 22px; font-weight: bold; color: #E6EDF3;"
        )
        root.addWidget(self._title_lbl)

        self._subtitle_lbl = QLabel(tr("bug_reporter_page_subtitle"))
        self._subtitle_lbl.setWordWrap(True)
        self._subtitle_lbl.setStyleSheet("font-size: 13px; color: #8B949E;")
        root.addWidget(self._subtitle_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("Separator")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        card = QFrame()
        card.setObjectName("Card")
        form = QVBoxLayout(card)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(18)

        # Bug type
        self._lbl_type = self._field_label("bug_reporter_lbl_type")
        form.addWidget(self._lbl_type)
        self._type_combo = QComboBox()
        self._type_combo.addItems(_BUG_TYPES_EN)
        self._type_combo.setFixedHeight(36)
        form.addWidget(self._type_combo)

        # Title
        self._lbl_title = self._field_label("bug_reporter_lbl_title")
        form.addWidget(self._lbl_title)
        self._title_input = QLineEdit()
        self._title_input.setPlaceholderText(tr("bug_reporter_ph_title"))
        self._title_input.setFixedHeight(36)
        form.addWidget(self._title_input)

        # Description
        self._lbl_desc = self._field_label("bug_reporter_lbl_desc")
        form.addWidget(self._lbl_desc)
        self._desc_input = QPlainTextEdit()
        self._desc_input.setPlaceholderText(tr("bug_reporter_ph_desc"))
        self._desc_input.setMinimumHeight(140)
        self._desc_input.setMaximumHeight(240)
        form.addWidget(self._desc_input)

        # Screenshot
        self._lbl_ss = self._field_label("bug_reporter_lbl_screenshot")
        form.addWidget(self._lbl_ss)
        ss_row = QHBoxLayout()
        self._screenshot_lbl = QLabel(tr("bug_reporter_no_screenshot"))
        self._screenshot_lbl.setObjectName("TextMuted")
        self._screenshot_lbl.setStyleSheet("font-size: 12px; color: #8B949E;")
        self._screenshot_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        ss_row.addWidget(self._screenshot_lbl)

        self._screenshot_thumb = QLabel()
        self._screenshot_thumb.setFixedSize(56, 40)
        self._screenshot_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._screenshot_thumb.setStyleSheet(
            "background: #0D1117; border: 1px solid #30363D; border-radius: 4px;"
        )
        self._screenshot_thumb.setVisible(False)
        ss_row.addWidget(self._screenshot_thumb)

        self._browse_ss_btn = QPushButton(tr("bug_reporter_btn_browse_screenshot"))
        self._browse_ss_btn.setFixedWidth(120)
        self._browse_ss_btn.clicked.connect(self._pick_screenshot)
        ss_row.addWidget(self._browse_ss_btn)

        self._paste_ss_btn = QPushButton(tr("bug_reporter_btn_paste_screenshot"))
        self._paste_ss_btn.setFixedWidth(90)
        self._paste_ss_btn.setToolTip(tr("bug_reporter_tip_paste_screenshot"))
        self._paste_ss_btn.clicked.connect(lambda: self.paste_screenshot())
        ss_row.addWidget(self._paste_ss_btn)

        self._clear_ss_btn = QPushButton(tr("bug_reporter_btn_clear_screenshot"))
        self._clear_ss_btn.setFixedWidth(80)
        self._clear_ss_btn.setVisible(False)
        self._clear_ss_btn.clicked.connect(self._clear_screenshot)
        ss_row.addWidget(self._clear_ss_btn)
        form.addLayout(ss_row)

        # User email
        self._lbl_email = self._field_label("bug_reporter_lbl_email")
        form.addWidget(self._lbl_email)
        self._email_input = QLineEdit()
        self._email_input.setPlaceholderText(tr("bug_reporter_ph_email"))
        self._email_input.setFixedHeight(36)
        form.addWidget(self._email_input)

        # Feedback label (error / sending / success)
        self._feedback_lbl = QLabel("")
        self._feedback_lbl.setStyleSheet("font-size: 12px;")
        self._feedback_lbl.setVisible(False)
        form.addWidget(self._feedback_lbl)

        # Send button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._send_btn = QPushButton(tr("bug_reporter_btn_send"))
        self._send_btn.setFixedSize(160, 42)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setStyleSheet(
            "QPushButton { background: #3B82F6; color: #fff; border: none;"
            "  border-radius: 8px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background: #2563EB; }"
            "QPushButton:disabled { background: #21262D; color: #484F58; }"
        )
        self._send_btn.clicked.connect(self._on_send)
        btn_row.addWidget(self._send_btn)
        form.addLayout(btn_row)

        root.addWidget(card)
        self.setWidget(content)

        # Ctrl+V inside a text box: see eventFilter. Outside one, the window's
        # paste shortcut calls paste_screenshot() while this page is open.
        for box in (self._title_input, self._desc_input, self._email_input):
            box.installEventFilter(self)

    @staticmethod
    def _field_label(key: str) -> QLabel:
        lbl = QLabel(tr(key))
        lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #C9D1D9;")
        return lbl

    # ── Screenshot ────────────────────────────────────────────────────────────

    def _pick_screenshot(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("bug_reporter_ss_dialog_title"),
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if path:
            self._set_screenshot(path)

    def paste_screenshot(self, *, image_only: bool = False) -> bool:
        """Use the image on the clipboard as the screenshot.

        With image_only (Ctrl+V in a text box) a clipboard that also holds text
        is left alone, so ordinary text pasting keeps working.
        """
        clipboard = QGuiApplication.clipboard()
        mime = clipboard.mimeData()
        if not (mime and mime.hasImage()) or (image_only and mime.hasText()):
            if not image_only:
                self._set_feedback(tr("bug_reporter_err_no_clipboard_image"), error=True)
            return False
        folder = Path(tempfile.gettempdir()) / "videl-bug-screenshots"
        self._set_screenshot(str(_save_pasted_image(clipboard.image(), folder)))
        return True

    def eventFilter(self, obj, event) -> bool:
        if (
            event.type() == QEvent.Type.KeyPress
            and event.matches(QKeySequence.StandardKey.Paste)
            and self.paste_screenshot(image_only=True)
        ):
            return True
        return super().eventFilter(obj, event)

    def _set_screenshot(self, path: str) -> None:
        self._feedback_lbl.setVisible(False)
        self._screenshot_path = path
        self._screenshot_lbl.setText(Path(path).name)
        px = QPixmap(path).scaled(
            56, 40,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if not px.isNull():
            self._screenshot_thumb.setPixmap(px)
        self._screenshot_thumb.setVisible(True)
        self._clear_ss_btn.setVisible(True)

    def _clear_screenshot(self) -> None:
        self._screenshot_path = ""
        self._screenshot_lbl.setText(tr("bug_reporter_no_screenshot"))
        self._screenshot_thumb.clear()
        self._screenshot_thumb.setVisible(False)
        self._clear_ss_btn.setVisible(False)

    # ── Send ─────────────────────────────────────────────────────────────────

    def _on_send(self) -> None:
        title = self._title_input.text().strip()
        desc = self._desc_input.toPlainText().strip()
        email = self._email_input.text().strip()
        bug_type = self._type_combo.currentText()

        if not title:
            self._set_feedback(tr("bug_reporter_err_no_title"), error=True)
            return
        if not desc:
            self._set_feedback(tr("bug_reporter_err_no_desc"), error=True)
            return

        subject = f"[Videl Bug] {bug_type}: {title}"
        body_lines = [
            f"Bug Type: {bug_type}",
            f"Reporter Email: {email or '(not provided)'}",
            "",
            "--- Description ---",
            desc,
        ]
        body = "\n".join(body_lines)

        self._send_btn.setEnabled(False)
        self._set_feedback(tr("bug_reporter_sending"), error=False)

        screenshot = self._screenshot_path
        self._worker = Worker(_send_email, subject, body, screenshot, email)
        self._worker.signals.result.connect(self._on_send_success)
        self._worker.signals.error.connect(self._on_send_error)
        self._worker.start()

    def _on_send_success(self, _result) -> None:
        self._set_feedback(tr("bug_reporter_sent"), error=False, color="#3FB950")
        # Reset form so another report can be submitted
        self._title_input.clear()
        self._desc_input.clear()
        self._email_input.clear()
        self._clear_screenshot()
        self._send_btn.setText(tr("bug_reporter_btn_send"))
        self._send_btn.setEnabled(True)

    def _on_send_error(self, err_tuple) -> None:
        _exc_type, msg, _tb = err_tuple
        self._set_feedback(tr("bug_reporter_err_send").format(msg=msg), error=True)
        self._send_btn.setEnabled(True)

    def _set_feedback(self, msg: str, *, error: bool, color: str = "") -> None:
        c = color if color else ("#F85149" if error else "#8B949E")
        self._feedback_lbl.setStyleSheet(f"font-size: 12px; color: {c};")
        self._feedback_lbl.setText(msg)
        self._feedback_lbl.setVisible(True)

    # ── Retranslate ───────────────────────────────────────────────────────────

    def retranslate_ui(self) -> None:
        from core.i18n import I18n
        self._title_lbl.setText(tr("bug_reporter_page_title"))
        self._subtitle_lbl.setText(tr("bug_reporter_page_subtitle"))
        self._lbl_type.setText(tr("bug_reporter_lbl_type"))
        self._lbl_title.setText(tr("bug_reporter_lbl_title"))
        self._lbl_desc.setText(tr("bug_reporter_lbl_desc"))
        self._lbl_ss.setText(tr("bug_reporter_lbl_screenshot"))
        self._lbl_email.setText(tr("bug_reporter_lbl_email"))

        is_rtl = I18n.instance().is_rtl
        items = _BUG_TYPES_AR if is_rtl else _BUG_TYPES_EN
        idx = self._type_combo.currentIndex()
        self._type_combo.blockSignals(True)
        self._type_combo.clear()
        self._type_combo.addItems(items)
        self._type_combo.setCurrentIndex(idx)
        self._type_combo.blockSignals(False)

        self._title_input.setPlaceholderText(tr("bug_reporter_ph_title"))
        self._desc_input.setPlaceholderText(tr("bug_reporter_ph_desc"))
        self._email_input.setPlaceholderText(tr("bug_reporter_ph_email"))
        self._browse_ss_btn.setText(tr("bug_reporter_btn_browse_screenshot"))
        self._paste_ss_btn.setText(tr("bug_reporter_btn_paste_screenshot"))
        self._paste_ss_btn.setToolTip(tr("bug_reporter_tip_paste_screenshot"))
        self._clear_ss_btn.setText(tr("bug_reporter_btn_clear_screenshot"))
        if not self._screenshot_path:
            self._screenshot_lbl.setText(tr("bug_reporter_no_screenshot"))
        if self._send_btn.isEnabled():
            self._send_btn.setText(tr("bug_reporter_btn_send"))
