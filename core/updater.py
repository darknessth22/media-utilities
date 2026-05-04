"""Smart Updater — silent background check against GitHub Releases.

Pings the public Releases API with a strict 3 s timeout. On newer version
found, emits ``update_available`` to the UI thread which then shows a styled
QMessageBox. Clicking the download button opens the GitHub Pages storefront
in the user's default browser. Network/API failures are swallowed silently.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
import webbrowser

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMessageBox, QPushButton, QWidget

from packaging.version import InvalidVersion, Version

from utils.app_logger import get_logger

# Hardcoded per spec — bump in lockstep with the published Git tag.
APP_VERSION = "3.1.0"

RELEASES_API_URL = "https://api.github.com/repos/darknessth22/media-utilities/releases/latest"
STOREFRONT_URL = "https://darknessth22.github.io/media-utilities/"

_HTTP_TIMEOUT_SEC = 3.0
_USER_AGENT = f"Videl-Updater/{APP_VERSION}"

_log = get_logger()


class UpdateChecker(QThread):
    """Background worker that pings GitHub Releases. Fails silently."""

    update_available = Signal(str, str)  # latest_version, html_url

    def run(self) -> None:  # noqa: D401 — Qt override
        try:
            req = urllib.request.Request(
                RELEASES_API_URL,
                headers={"User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json"},
            )
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SEC) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            _log.debug("UpdateChecker: silent fail (%s)", exc)
            return

        tag = (payload.get("tag_name") or "").lstrip("vV").strip()
        html_url = payload.get("html_url") or STOREFRONT_URL
        if not tag:
            return

        try:
            if Version(tag) <= Version(APP_VERSION):
                return
        except InvalidVersion:
            _log.debug("UpdateChecker: bad tag %r", tag)
            return

        self.update_available.emit(tag, html_url)


_DARK_QSS = """
QMessageBox { background-color: #0f172a; }
QMessageBox QLabel { color: #ffffff; font-size: 13px; }
QMessageBox QPushButton {
    background-color: #1e293b; color: #ffffff;
    border: 1px solid #334155; border-radius: 6px;
    padding: 6px 16px; min-width: 110px;
}
QMessageBox QPushButton:hover { background-color: #334155; }
QMessageBox QPushButton[primary="true"] {
    background-color: #2563eb; border: 1px solid #2563eb;
}
QMessageBox QPushButton[primary="true"]:hover { background-color: #1d4ed8; }
"""


def show_update_modal(parent: QWidget | None, latest: str, _html_url: str) -> None:
    """Display the update prompt. Browser opens to storefront on accept."""
    from core.i18n import tr

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(tr("update_title"))
    box.setText(tr("update_body").format(current=APP_VERSION, latest=latest))
    box.setStyleSheet(_DARK_QSS)

    download_btn = QPushButton(tr("update_download"))
    download_btn.setProperty("primary", True)
    skip_btn = QPushButton(tr("update_skip"))

    box.addButton(download_btn, QMessageBox.ButtonRole.AcceptRole)
    box.addButton(skip_btn, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(download_btn)

    box.exec()
    if box.clickedButton() is download_btn:
        try:
            webbrowser.open(STOREFRONT_URL, new=2)
        except Exception as exc:  # webbrowser is best-effort
            _log.debug("Storefront open failed: %s", exc)


def start_update_check(parent: QWidget) -> UpdateChecker:
    """Kick off the silent check. Caller keeps a reference to prevent GC."""
    checker = UpdateChecker(parent)
    checker.update_available.connect(
        lambda tag, url: show_update_modal(
            parent if isinstance(parent, QWidget) else QGuiApplication.focusWindow(),
            tag,
            url,
        )
    )
    checker.start()
    return checker
