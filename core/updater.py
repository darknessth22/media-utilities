"""Smart Updater — silent background check + in-app download/install.

Pings GitHub Releases (3 s timeout). On newer version, prompts user with
styled QMessageBox. Accept → streams Videl_Setup.exe to %TEMP%, launches
the Inno installer with /SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS,
quits the running app. Inno's RestartManager closes Videl, installs the
new build, relaunches it.

Falls back to opening the storefront in the browser when:
  - not running a frozen Windows build (dev mode), or
  - the in-app download/launch fails.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import webbrowser

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QWidget,
)

from packaging.version import InvalidVersion, Version

from core.version import VERSION as APP_VERSION
from utils.app_logger import get_logger

RELEASES_API_URL = "https://api.github.com/repos/darknessth22/media-utilities/releases/latest"
INSTALLER_DOWNLOAD_URL = (
    "https://github.com/darknessth22/media-utilities/releases/latest/download/Videl_Setup.exe"
)
STOREFRONT_URL = "https://darknessth22.github.io/media-utilities/"

_HTTP_TIMEOUT_SEC = 3.0
_DOWNLOAD_TIMEOUT_SEC = 60.0
_USER_AGENT = f"Videl-Updater/{APP_VERSION}"
_WIN_FROZEN = sys.platform == "win32" and getattr(sys, "frozen", False)

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


class InstallerDownloader(QThread):
    """Streams Videl_Setup.exe to a temp path with progress reporting."""

    progress = Signal(int, int)  # bytes_done, total_bytes (total=0 if unknown)
    finished_ok = Signal(str)    # local installer path
    failed = Signal(str)         # error message

    def __init__(self, dest_path: str, parent=None) -> None:
        super().__init__(parent)
        self._dest = dest_path
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:  # noqa: D401
        try:
            req = urllib.request.Request(
                INSTALLER_DOWNLOAD_URL,
                headers={"User-Agent": _USER_AGENT},
            )
            with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT_SEC) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                tmp_path = self._dest + ".part"
                with open(tmp_path, "wb") as fh:
                    while True:
                        if self._cancel:
                            fh.close()
                            try:
                                os.remove(tmp_path)
                            except OSError:
                                pass
                            self.failed.emit("cancelled")
                            return
                        chunk = resp.read(262144)
                        if not chunk:
                            break
                        fh.write(chunk)
                        done += len(chunk)
                        self.progress.emit(done, total)
            os.replace(tmp_path, self._dest)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            _log.warning("Installer download failed: %s", exc)
            self.failed.emit(str(exc))
            return

        self.finished_ok.emit(self._dest)


_DARK_QSS = """
QMessageBox, QProgressDialog { background-color: #0f172a; }
QMessageBox QLabel, QProgressDialog QLabel { color: #ffffff; font-size: 13px; }
QMessageBox QPushButton, QProgressDialog QPushButton {
    background-color: #1e293b; color: #ffffff;
    border: 1px solid #334155; border-radius: 6px;
    padding: 6px 16px; min-width: 110px;
}
QMessageBox QPushButton:hover, QProgressDialog QPushButton:hover { background-color: #334155; }
QMessageBox QPushButton[primary="true"] {
    background-color: #2563eb; border: 1px solid #2563eb;
}
QMessageBox QPushButton[primary="true"]:hover { background-color: #1d4ed8; }
QProgressBar {
    background-color: #1e293b; border: 1px solid #334155; border-radius: 6px;
    color: #ffffff; text-align: center;
}
QProgressBar::chunk { background-color: #2563eb; border-radius: 5px; }
"""


def _open_storefront() -> None:
    try:
        webbrowser.open(STOREFRONT_URL, new=2)
    except Exception as exc:
        _log.debug("Storefront open failed: %s", exc)


def _launch_installer_and_quit(installer_path: str) -> bool:
    """Spawn Inno installer detached, then quit the app. Returns False on launch failure."""
    try:
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        subprocess.Popen(
            [
                installer_path,
                "/SILENT",
                "/CLOSEAPPLICATIONS",
                "/RESTARTAPPLICATIONS",
                "/NORESTART",
            ],
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    except OSError as exc:
        _log.error("Installer launch failed: %s", exc)
        return False

    QApplication.quit()
    return True


def _run_in_app_update(parent: QWidget | None, latest: str) -> None:
    from core.i18n import tr

    dest = os.path.join(tempfile.gettempdir(), f"Videl_Setup_{latest}.exe")

    progress = QProgressDialog(parent)
    progress.setWindowTitle(tr("update_title"))
    progress.setLabelText(tr("update_downloading").format(latest=latest))
    progress.setRange(0, 100)
    progress.setValue(0)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    progress.setWindowModality(Qt.WindowModality.ApplicationModal)
    progress.setMinimumWidth(420)
    progress.setStyleSheet(_DARK_QSS)
    progress.setCancelButtonText(tr("update_cancel"))

    downloader = InstallerDownloader(dest, parent)

    def on_progress(done: int, total: int) -> None:
        if total > 0:
            pct = int(done * 100 / total)
            progress.setValue(pct)
            mb_done = done / 1048576
            mb_total = total / 1048576
            progress.setLabelText(
                tr("update_downloading_progress").format(
                    done=f"{mb_done:.1f}", total=f"{mb_total:.1f}"
                )
            )
        else:
            progress.setLabelText(tr("update_downloading").format(latest=latest))

    def on_failed(msg: str) -> None:
        progress.close()
        if msg == "cancelled":
            return
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("update_failed_title"))
        box.setText(tr("update_failed_body").format(error=msg))
        box.setStyleSheet(_DARK_QSS)
        open_btn = QPushButton(tr("update_open_browser"))
        open_btn.setProperty("primary", True)
        close_btn = QPushButton(tr("update_skip"))
        box.addButton(open_btn, QMessageBox.ButtonRole.AcceptRole)
        box.addButton(close_btn, QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            _open_storefront()

    def on_ok(path: str) -> None:
        progress.close()
        if not _launch_installer_and_quit(path):
            on_failed("launch failed")

    downloader.progress.connect(on_progress)
    downloader.failed.connect(on_failed)
    downloader.finished_ok.connect(on_ok)
    progress.canceled.connect(downloader.cancel)

    downloader.start()
    progress.exec()


def show_update_modal(parent: QWidget | None, latest: str, _html_url: str) -> None:
    """Display the update prompt. Frozen Windows: in-app download. Else: browser."""
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
    if box.clickedButton() is not download_btn:
        return

    if _WIN_FROZEN:
        _run_in_app_update(parent, latest)
    else:
        _open_storefront()


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
