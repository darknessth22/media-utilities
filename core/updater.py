"""Smart Updater — silent background check + in-app delta/full install.

Pings GitHub Releases (3 s timeout). On newer version, prompts user with
styled QMessageBox.

Frozen Windows builds take the DELTA path: fetch the signed file manifest
(videl-files.manifest.json), hash the local install tree, download only the
changed files as content-addressed blobs from the rolling 'files-store'
release, stage them, then spawn a batch that waits for Videl to exit,
robocopy-merges the staged files in place, and relaunches via explorer.exe.
Falls back to the full Inno installer (Videl_Setup.exe — /SILENT
/CLOSEAPPLICATIONS /RESTARTAPPLICATIONS) when the manifest is missing or
unsigned, or the delta download/apply fails.

Falls back to opening the storefront in the browser when:
  - not running a frozen Windows build (dev mode), or
  - the in-app download/launch fails.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
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

# Delta updates: signed per-file manifest published on the latest release, and
# the rolling content-addressed blob store (one asset per unique file, named by
# its sha256). See tools/gen_manifest.py and tools/upload_blobs.py.
FILES_MANIFEST_URL = (
    "https://github.com/darknessth22/media-utilities/releases/latest/download/videl-files.manifest.json"
)
BLOB_BASE_URL = (
    "https://github.com/darknessth22/media-utilities/releases/download/files-store/"
)

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


class DeltaDownloader(QThread):
    """Streams a set of content-addressed blobs into a staging tree, verifying
    each file's sha256. Reports aggregate byte progress across all blobs."""

    progress = Signal(int, int)  # bytes_done, total_bytes
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, jobs: list[tuple[str, str, int]], staging_dir: str, parent=None) -> None:
        super().__init__(parent)
        self._jobs = jobs            # (rel_path, sha256, size)
        self._staging = staging_dir
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:  # noqa: D401
        total = sum(size for _rel, _sha, size in self._jobs)
        done = 0
        try:
            for rel_path, sha, _size in self._jobs:
                if self._cancel:
                    self.failed.emit("cancelled")
                    return
                dest = os.path.join(self._staging, rel_path)
                os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
                req = urllib.request.Request(
                    BLOB_BASE_URL + sha, headers={"User-Agent": _USER_AGENT}
                )
                h = hashlib.sha256()
                with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT_SEC) as resp, \
                        open(dest, "wb") as fh:
                    while True:
                        if self._cancel:
                            self.failed.emit("cancelled")
                            return
                        chunk = resp.read(262144)
                        if not chunk:
                            break
                        fh.write(chunk)
                        h.update(chunk)
                        done += len(chunk)
                        self.progress.emit(done, total)
                if h.hexdigest().lower() != sha.lower():
                    self.failed.emit(f"blob hash mismatch: {rel_path}")
                    return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            _log.warning("Delta blob download failed: %s", exc)
            self.failed.emit(str(exc))
            return

        self.finished_ok.emit()


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


# ── Delta updates (Windows frozen builds) ────────────────────────────────────

def _verify_files_manifest_signature(manifest: dict) -> bool:
    """Verify the Ed25519 signature over the {version, files} payload."""
    try:
        import base64
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from core._signing import PUBLIC_KEY_B64
    except Exception as exc:
        _log.error("Crypto import failed: %s", exc)
        return False

    sig_b64 = manifest.get("sig")
    files = manifest.get("files")
    version = manifest.get("version")
    if not sig_b64 or not isinstance(files, list) or not version:
        return False
    try:
        payload = {"version": version, "files": files}
        payload_bytes = json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        pad = "=" * (-len(PUBLIC_KEY_B64) % 4)
        pub_raw = base64.urlsafe_b64decode(PUBLIC_KEY_B64 + pad)
        pad2 = "=" * (-len(sig_b64) % 4)
        sig = base64.urlsafe_b64decode(sig_b64 + pad2)
        Ed25519PublicKey.from_public_bytes(pub_raw).verify(sig, payload_bytes)
        return True
    except Exception as exc:
        _log.warning("Files manifest signature invalid: %s", exc)
        return False


def _install_root() -> str:
    """Directory holding the running Videl.exe (the onedir install root)."""
    return os.path.dirname(os.path.abspath(sys.executable))


def _install_writable(root: str) -> bool:
    """True if files can be created in the install dir without elevation.

    os.access(W_OK) is unreliable for directories on Windows — probe for real.
    """
    probe = os.path.join(root, f".videl_write_probe_{os.getpid()}")
    try:
        with open(probe, "w", encoding="ascii") as fh:
            fh.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _local_sha256(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest().lower()


def _compute_delta(manifest: dict, install_root: str) -> list[tuple[str, str, int]]:
    """Return [(rel_path, sha256, size)] for files missing or changed locally."""
    jobs: list[tuple[str, str, int]] = []
    for entry in manifest.get("files", []):
        rel = entry.get("path") or ""
        sha = (entry.get("sha256") or "").lower()
        size = int(entry.get("size") or 0)
        if not rel or not sha:
            continue
        local = os.path.join(install_root, rel.replace("/", os.sep))
        if _local_sha256(local) != sha:
            jobs.append((rel.replace("/", os.sep), sha, size))
    return jobs


def _write_apply_script(staging: str, install_root: str, version: str) -> str:
    """Write the batch that waits for Videl to exit, robocopy-merges the staged
    files in, relaunches via explorer.exe (drops elevation), then self-deletes."""
    bat_path = os.path.join(tempfile.gettempdir(), f"videl_apply_{version}.bat")
    exe = os.path.join(install_root, "Videl.exe")
    lines = [
        "@echo off",
        "setlocal",
        f'set "LOG=%TEMP%\\videl_update_{version}.log"',
        f'echo Videl delta update {version} > "%LOG%"',
        ":wait",
        'tasklist /FI "IMAGENAME eq Videl.exe" 2>nul | find /I "Videl.exe" >nul',
        "if not errorlevel 1 (",
        "  ping -n 2 127.0.0.1 >nul",
        "  goto wait",
        ")",
        f'robocopy "{staging}" "{install_root}" /E /COPY:DAT /R:3 /W:2 /NP >> "%LOG%" 2>&1',
        f'start "" explorer.exe "{exe}"',
        f'rmdir /S /Q "{staging}"',
        '(goto) 2>nul & del "%~f0"',
        "",
    ]
    with open(bat_path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(lines))
    return bat_path


def _launch_applier_and_quit(bat_path: str, install_root: str) -> bool:
    """Spawn the apply batch detached (elevated if the install dir needs it),
    then quit the app. Returns False on launch failure / UAC decline."""
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    try:
        if _install_writable(install_root):
            subprocess.Popen(
                ["cmd", "/c", bat_path],
                creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
            )
        else:
            # Program Files install — the applier needs admin to write here.
            import ctypes
            rc = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", "cmd.exe", f'/c "{bat_path}"', None, 0
            )
            if rc <= 32:
                _log.error("Elevated applier launch failed/declined (rc=%s)", rc)
                return False
    except OSError as exc:
        _log.error("Applier launch failed: %s", exc)
        return False

    QApplication.quit()
    return True


def _run_delta_update(parent: QWidget | None, latest: str) -> None:
    """Download only changed files and merge them in place. Falls back to the
    full Inno installer when the manifest is missing/unsigned or the delta fails."""
    from core.i18n import tr

    manifest = _fetch_manifest(FILES_MANIFEST_URL)
    if manifest is None or not _verify_files_manifest_signature(manifest):
        _log.info("Delta manifest unavailable/unsigned — using full installer.")
        _run_in_app_update(parent, latest)
        return

    install_root = _install_root()
    jobs = _compute_delta(manifest, install_root)
    if not jobs:
        # Version bumped but no file content changed — fall back rather than no-op.
        _run_in_app_update(parent, latest)
        return

    staging = os.path.join(
        os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
        "Videl", "update-staging", latest,
    )
    shutil.rmtree(staging, ignore_errors=True)
    try:
        os.makedirs(staging, exist_ok=True)
    except OSError as exc:
        _log.error("Staging dir create failed: %s", exc)
        _run_in_app_update(parent, latest)
        return

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

    downloader = DeltaDownloader(jobs, staging, parent)

    def on_progress(done: int, total: int) -> None:
        if total > 0:
            progress.setValue(int(done * 100 / total))
            progress.setLabelText(
                tr("update_downloading_progress").format(
                    done=f"{done / 1048576:.1f}", total=f"{total / 1048576:.1f}"
                )
            )

    def on_failed(msg: str) -> None:
        progress.close()
        shutil.rmtree(staging, ignore_errors=True)
        if msg == "cancelled":
            return
        _log.warning("Delta update failed (%s) — using full installer.", msg)
        _run_in_app_update(parent, latest)

    def on_ok() -> None:
        progress.close()
        bat = _write_apply_script(staging, install_root, latest)
        if not _launch_applier_and_quit(bat, install_root):
            shutil.rmtree(staging, ignore_errors=True)
            _run_in_app_update(parent, latest)

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
        _run_delta_update(parent, latest)
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
