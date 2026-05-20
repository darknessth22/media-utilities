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

import hashlib
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
# Signed manifest published alongside the installer. Format (one .sig.json):
#   {"sha256": "<hex>", "size": <int>, "version": "x.y.z",
#    "sig": "<urlsafe-b64 ed25519 sig over compact JSON of {sha256,size,version}>"}
INSTALLER_MANIFEST_URL = (
    "https://github.com/darknessth22/media-utilities/releases/latest/download/Videl_Setup.exe.sig.json"
)
APPIMAGE_DOWNLOAD_URL = (
    "https://github.com/darknessth22/media-utilities/releases/latest/download/Videl-x86_64.AppImage"
)
APPIMAGE_MANIFEST_URL = (
    "https://github.com/darknessth22/media-utilities/releases/latest/download/Videl-x86_64.AppImage.sig.json"
)
STOREFRONT_URL = "https://darknessth22.github.io/media-utilities/"

_HTTP_TIMEOUT_SEC = 3.0
_DOWNLOAD_TIMEOUT_SEC = 60.0
_USER_AGENT = f"Videl-Updater/{APP_VERSION}"
_WIN_FROZEN = sys.platform == "win32" and getattr(sys, "frozen", False)
_LINUX_APPIMAGE_PATH = os.environ.get("APPIMAGE") if sys.platform.startswith("linux") else None
_LINUX_APPIMAGE = bool(_LINUX_APPIMAGE_PATH)

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

    def __init__(self, dest_path: str, parent=None, url: str = INSTALLER_DOWNLOAD_URL) -> None:
        super().__init__(parent)
        self._dest = dest_path
        self._url = url
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:  # noqa: D401
        try:
            req = urllib.request.Request(
                self._url,
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


def _fetch_manifest(url: str = INSTALLER_MANIFEST_URL) -> dict | None:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        if not isinstance(data, dict):
            return None
        return data
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        _log.warning("Manifest fetch failed: %s", exc)
        return None


def _verify_manifest_signature(manifest: dict) -> bool:
    """Verify Ed25519 signature on the {sha256,size,version} payload."""
    try:
        import base64
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from core._signing import PUBLIC_KEY_B64
    except Exception as exc:
        _log.error("Crypto import failed: %s", exc)
        return False

    sig_b64 = manifest.get("sig")
    if not sig_b64:
        return False
    payload = {
        "sha256": manifest.get("sha256"),
        "size": manifest.get("size"),
        "version": manifest.get("version"),
    }
    if not all(payload.values()):
        return False
    try:
        payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        pad = "=" * (-len(PUBLIC_KEY_B64) % 4)
        pub_raw = base64.urlsafe_b64decode(PUBLIC_KEY_B64 + pad)
        pad2 = "=" * (-len(sig_b64) % 4)
        sig = base64.urlsafe_b64decode(sig_b64 + pad2)
        Ed25519PublicKey.from_public_bytes(pub_raw).verify(sig, payload_bytes)
        return True
    except Exception as exc:
        _log.warning("Manifest signature invalid: %s", exc)
        return False


def _verify_installer(path: str, manifest: dict) -> bool:
    expected_sha = (manifest.get("sha256") or "").lower()
    expected_size = int(manifest.get("size") or 0)
    if not expected_sha or expected_size <= 0:
        return False
    try:
        actual_size = os.path.getsize(path)
    except OSError:
        return False
    if actual_size != expected_size:
        _log.warning("Installer size mismatch: got %d, want %d", actual_size, expected_size)
        return False
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError as exc:
        _log.warning("Installer hash read failed: %s", exc)
        return False
    actual_sha = h.hexdigest().lower()
    if actual_sha != expected_sha:
        _log.warning("Installer sha256 mismatch")
        return False
    return True


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

    # Fetch + verify signed manifest BEFORE downloading the installer. If the
    # manifest is missing or its signature doesn't validate against the bundled
    # Ed25519 public key, abort: a compromised release pipeline shouldn't be
    # able to ship arbitrary installers to users.
    manifest = _fetch_manifest()
    if manifest is None or not _verify_manifest_signature(manifest):
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("update_failed_title"))
        box.setText(tr("update_failed_body").format(error="signature verification failed"))
        box.setStyleSheet(_DARK_QSS)
        open_btn = QPushButton(tr("update_open_browser"))
        open_btn.setProperty("primary", True)
        close_btn = QPushButton(tr("update_skip"))
        box.addButton(open_btn, QMessageBox.ButtonRole.AcceptRole)
        box.addButton(close_btn, QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            _open_storefront()
        return

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
        if not _verify_installer(path, manifest):
            try:
                os.remove(path)
            except OSError:
                pass
            on_failed("installer integrity check failed")
            return
        if not _launch_installer_and_quit(path):
            on_failed("launch failed")

    downloader.progress.connect(on_progress)
    downloader.failed.connect(on_failed)
    downloader.finished_ok.connect(on_ok)
    progress.canceled.connect(downloader.cancel)

    downloader.start()
    progress.exec()


def _run_linux_appimage_update(parent: QWidget | None, latest: str) -> None:
    """Replace the running AppImage in place and re-exec.

    Strategy: download new AppImage to a temp file on the SAME filesystem as
    $APPIMAGE (so os.replace is atomic), verify sha256+size against the signed
    manifest, chmod 0755, os.replace over $APPIMAGE, then os.execv to relaunch.
    On read-only target or signature/integrity failure, fall back to opening
    the storefront.
    """
    from core.i18n import tr

    appimage_path = _LINUX_APPIMAGE_PATH or ""
    if not appimage_path or not os.path.isfile(appimage_path):
        _open_storefront()
        return

    target_dir = os.path.dirname(os.path.abspath(appimage_path)) or "."
    if not os.access(target_dir, os.W_OK) or not os.access(appimage_path, os.W_OK):
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("update_failed_title"))
        box.setText(tr("update_failed_appimage_readonly"))
        box.setStyleSheet(_DARK_QSS)
        open_btn = QPushButton(tr("update_open_browser"))
        open_btn.setProperty("primary", True)
        close_btn = QPushButton(tr("update_skip"))
        box.addButton(open_btn, QMessageBox.ButtonRole.AcceptRole)
        box.addButton(close_btn, QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            _open_storefront()
        return

    manifest = _fetch_manifest(APPIMAGE_MANIFEST_URL)
    if manifest is None or not _verify_manifest_signature(manifest):
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("update_failed_title"))
        box.setText(tr("update_failed_body").format(error="signature verification failed"))
        box.setStyleSheet(_DARK_QSS)
        open_btn = QPushButton(tr("update_open_browser"))
        open_btn.setProperty("primary", True)
        close_btn = QPushButton(tr("update_skip"))
        box.addButton(open_btn, QMessageBox.ButtonRole.AcceptRole)
        box.addButton(close_btn, QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            _open_storefront()
        return

    # Temp file on SAME filesystem as $APPIMAGE → os.replace is atomic.
    dest = os.path.join(target_dir, f".Videl-x86_64.AppImage.new-{latest}")

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

    downloader = InstallerDownloader(dest, parent, url=APPIMAGE_DOWNLOAD_URL)

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
        try:
            if os.path.exists(dest):
                os.remove(dest)
        except OSError:
            pass
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
        if not _verify_installer(path, manifest):
            try:
                os.remove(path)
            except OSError:
                pass
            on_failed("AppImage integrity check failed")
            return
        try:
            os.chmod(path, 0o755)
            os.replace(path, appimage_path)
        except OSError as exc:
            _log.error("AppImage replace failed: %s", exc)
            on_failed(str(exc))
            return
        # Relaunch the new AppImage in place of the current process.
        try:
            QApplication.quit()
            os.execv(appimage_path, [appimage_path, *sys.argv[1:]])
        except OSError as exc:
            _log.error("os.execv failed: %s", exc)
            # App already quit; nothing left to do.

    downloader.progress.connect(on_progress)
    downloader.failed.connect(on_failed)
    downloader.finished_ok.connect(on_ok)
    progress.canceled.connect(downloader.cancel)

    downloader.start()
    progress.exec()


def show_update_modal(parent: QWidget | None, latest: str, _html_url: str) -> None:
    """Display the update prompt. Frozen Windows / Linux AppImage: in-app. Else: browser."""
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
    elif _LINUX_APPIMAGE:
        _run_linux_appimage_update(parent, latest)
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
