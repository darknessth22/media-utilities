"""Developer Console — raw crash-log viewer for failed tasks.

Shows the captured FFmpeg / Whisper / Demucs output from the most recent
failed task, with a one-click "Copy Crash Log to Clipboard" button so users
can paste it straight into a GitHub issue.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from core.crash_log import crash_log_dir, last_crash
from core.i18n import tr


class CrashLogDialog(QDialog):
    """Modal viewer for one recorded subprocess crash log."""

    def __init__(self, crash: dict, parent=None) -> None:
        super().__init__(parent)
        self._crash = crash
        self.setObjectName("CrashLogDialog")
        self.setWindowTitle(tr("crashlog_title"))
        self.setModal(True)
        self.resize(740, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        source = str(crash.get("source", "?"))
        when = crash.get("time")
        when_str = when.strftime("%Y-%m-%d %H:%M:%S") if hasattr(when, "strftime") else ""
        self._heading = QLabel(tr("crashlog_heading").format(source=source, time=when_str))
        self._heading.setObjectName("TextSecondary")
        self._heading.setWordWrap(True)
        layout.addWidget(self._heading)

        self._view = QPlainTextEdit()
        self._view.setObjectName("CrashLogView")
        self._view.setReadOnly(True)
        self._view.setPlainText(crash.get("text", ""))
        self._view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(9)
        self._view.setFont(mono)
        layout.addWidget(self._view, 1)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._copy_btn = QPushButton(tr("crashlog_copy"))
        self._copy_btn.setObjectName("BrowseBtn")
        self._copy_btn.clicked.connect(self._copy)
        row.addWidget(self._copy_btn)

        self._folder_btn = QPushButton(tr("crashlog_open_folder"))
        self._folder_btn.setObjectName("BrowseBtn")
        self._folder_btn.clicked.connect(self._open_folder)
        row.addWidget(self._folder_btn)

        row.addStretch()

        self._close_btn = QPushButton(tr("crashlog_close"))
        self._close_btn.setObjectName("BrowseBtn")
        self._close_btn.clicked.connect(self.accept)
        row.addWidget(self._close_btn)
        layout.addLayout(row)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._crash.get("text", ""))
        self._copy_btn.setText(tr("crashlog_copied"))
        # Revert the label so it stays obvious the button is still usable.
        QTimer.singleShot(2000, lambda: self._copy_btn.setText(tr("crashlog_copy")))

    def _open_folder(self) -> None:
        path = self._crash.get("path")
        target = os.path.dirname(path) if path and os.path.isfile(path) else crash_log_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(target))


def show_crash_log(parent=None) -> bool:
    """Pop the most recent crash log. Returns False if there is none recorded."""
    crash = last_crash()
    if not crash:
        return False
    CrashLogDialog(crash, parent).exec()
    return True
