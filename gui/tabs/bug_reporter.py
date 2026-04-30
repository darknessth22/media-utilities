"""Bug Reporter section — form that sends bug reports via SendGrid HTTP API."""
from __future__ import annotations

import base64
import json
import os
import urllib.request
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from core.i18n import tr
from gui.worker import Worker

_SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"
_SENDER_EMAIL = "videl.support@gmail.com"
_SENDER_NAME = "Videl Bug Reporter"
_RECIPIENT_EMAIL = "videl.support@gmail.com"
_SENDGRID_API_KEY_BUILTIN = "@@SENDGRID_API_KEY@@"  # replaced at build time

_BUG_TYPES_EN = ["UI Problem", "Feature Problem", "Crash / Error", "Performance", "Other"]
_BUG_TYPES_AR = ["مشكلة واجهة", "مشكلة ميزة", "تعطل / خطأ", "أداء", "أخرى"]


def _send_email(subject: str, body: str, screenshot_path: str, reporter_email: str = "") -> None:
    """Send bug report via SendGrid API. Runs in a Worker thread."""
    # Packaging subprocess must not require secrets (GitHub Actions, etc.).
    if os.environ.get("VIDEL_PYINSTALLER_BUILD") == "1":
        return None

    api_key = (os.environ.get("SENDGRID_API_KEY") or "").strip()
    if not api_key and not _SENDGRID_API_KEY_BUILTIN.startswith("@@"):
        api_key = _SENDGRID_API_KEY_BUILTIN
    if not api_key:
        raise RuntimeError("SENDGRID_API_KEY is not set (check .env or system environment).")

    to_list = [{"email": _RECIPIENT_EMAIL}]
    if reporter_email:
        to_list.append({"email": reporter_email})

    payload: dict = {
        "personalizations": [{"to": to_list}],
        "from": {"email": _SENDER_EMAIL, "name": _SENDER_NAME},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }

    if screenshot_path:
        path = Path(screenshot_path)
        if path.is_file():
            data = base64.b64encode(path.read_bytes()).decode()
            suffix = path.suffix.lower()
            mime = {
                ".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".webp": "image/webp",
                ".bmp": "image/bmp",
            }.get(suffix, "application/octet-stream")
            payload["attachments"] = [{
                "content": data,
                "type": mime,
                "filename": path.name,
                "disposition": "attachment",
            }]

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _SENDGRID_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status not in (200, 202):
            raise RuntimeError(f"SendGrid returned HTTP {resp.status}")


class BugReporterSection(QScrollArea):
    """Full-page bug report form. Sends directly via SMTP in a background thread."""

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
        if not path:
            return
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
        self._clear_ss_btn.setText(tr("bug_reporter_btn_clear_screenshot"))
        if not self._screenshot_path:
            self._screenshot_lbl.setText(tr("bug_reporter_no_screenshot"))
        if self._send_btn.isEnabled():
            self._send_btn.setText(tr("bug_reporter_btn_send"))
