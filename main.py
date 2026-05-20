"""Entry point for Videl (PySide6).

Run with:
    python main.py
"""
import os
import signal
import sys
import tempfile
import faulthandler

# PyInstaller --windowed sets sys.stdout/stderr=None. Anything writing to them
# (faulthandler, library prints, warnings) then crashes. Swap in /dev/null
# sinks before any further imports, then route faulthandler to a logfile so we
# can still diagnose crashes in frozen builds.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", buffering=1)
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", buffering=1)

if getattr(sys, "frozen", False):
    try:
        _fh_log = open(
            os.path.join(tempfile.gettempdir(), "videl_faulthandler.log"),
            "w", buffering=1,
        )
        faulthandler.enable(_fh_log)
    except Exception:
        pass
else:
    faulthandler.enable()

# Load .env before any package imports that read secrets at import time (e.g. bug reporter).
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.isfile(_env_path):
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            _k = _k.strip()
            _v = _v.strip()
            # Strip optional surrounding quotes (KEY="value" / KEY='value').
            if len(_v) >= 2 and _v[0] == _v[-1] and _v[0] in ("'", '"'):
                _v = _v[1:-1]
            os.environ.setdefault(_k, _v)

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt, QThread, QTimer, Signal, qInstallMessageHandler, QtMsgType


def _qt_message_handler(mode, _context, message):
    """Filter out the benign QFont::setPointSize warning caused by pixel-based QSS."""
    if "QFont::setPointSize" in message:
        return
    if mode == QtMsgType.QtWarningMsg:
        sys.stderr.write(f"Qt Warning: {message}\n")
    elif mode == QtMsgType.QtCriticalMsg:
        sys.stderr.write(f"Qt Critical: {message}\n")
    elif mode == QtMsgType.QtFatalMsg:
        sys.stderr.write(f"Qt Fatal: {message}\n")


qInstallMessageHandler(_qt_message_handler)

from utils import model_manager
_RECONCILE_RESULT = model_manager.reconcile_on_launch()
model_manager.ensure_ai_packages_on_path()

# Single-instance mutex — installer uses this name to detect a running instance.
# If the mutex already exists, another Videl is running: bail out before any UI
# (incl. splash) is created so a second instance cannot spawn a duplicate splash.
if sys.platform == "win32":
    import ctypes
    _ERROR_ALREADY_EXISTS = 183
    # Frozen builds and dev runs both honour the single-instance lock, but
    # use distinct mutex names so a running installed Videl doesn't block a
    # developer launch (and vice-versa). Session-local namespace prevents
    # another process in a different session from squatting the name.
    _mutex_name = "Local\\VidelAppMutex" if getattr(sys, "frozen", False) else "Local\\VidelAppMutex.dev"
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, _mutex_name)
    if ctypes.windll.kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
        sys.exit(0)

from core.settings import SettingsManager
from core.version import VERSION
from core.i18n import I18n
from gui.app import MainWindow
from gui.theme import ThemeManager
from gui.pages.splash_screen import SplashScreen

_APP_ICON = os.path.join(os.path.dirname(__file__), "assets", "videl_icon.png")


class _DepsChecker(QThread):
    """Background thread that validates runtime dependencies."""
    done = Signal(str)  # "" = all OK, "ffmpeg_missing" = critical error

    def run(self) -> None:
        from utils.deps import check_dependencies
        result = check_dependencies()
        self.done.emit(result or "")


def main() -> None:
    app = QApplication(sys.argv)
    # Force Fusion style so the QSS (rounded corners, button colours, sidebar)
    # renders identically across Windows and Linux. The Linux default style
    # (Breeze / GTK) silently drops custom border-radius on native widgets.
    try:
        from PySide6.QtWidgets import QStyleFactory
        if "Fusion" in QStyleFactory.keys():
            app.setStyle("Fusion")
    except Exception:
        pass
    app.setApplicationName("Videl")
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("Videl")
    from PySide6.QtGui import QIcon
    app.setWindowIcon(QIcon(_APP_ICON))
    # Prevent the process from exiting when the last window is hidden to tray.
    app.setQuitOnLastWindowClosed(False)

    # Load user settings
    settings = SettingsManager.load()

    # Initialise i18n and layout direction before the window is created
    i18n = I18n.instance()
    i18n.set_language(getattr(settings, "language", "en"))

    # Initialise and apply theme (RTL must be set before first paint)
    theme_manager = ThemeManager(app)
    theme_manager.set_rtl(i18n.is_rtl)
    theme_manager.set_mode(settings.theme_mode)

    # Show splash; create main window only when user clicks "Get Started".
    splash = SplashScreen()
    splash.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
    screen = app.primaryScreen().availableGeometry()
    sw = min(1100, screen.width())
    sh = min(700, screen.height())
    splash.setGeometry(
        screen.x() + (screen.width() - sw) // 2,
        screen.y() + (screen.height() - sh) // 2,
        sw, sh,
    )
    splash.show()

    def _on_ready():
        splash.close()
        win = MainWindow(settings, theme_manager)
        win.show()
        # Surface corrupt-config recovery from SettingsManager.load(), if any.
        from core.settings import LAST_LOAD_ERROR, LAST_LOAD_BACKUP_PATH
        if LAST_LOAD_ERROR:
            from core.i18n import tr
            if LAST_LOAD_BACKUP_PATH:
                win.update_status(
                    tr("settings_corrupt_backed_up").format(path=LAST_LOAD_BACKUP_PATH),
                    is_error=True,
                )
            else:
                win.update_status(
                    tr("settings_load_error").format(error=LAST_LOAD_ERROR),
                    is_error=True,
                )
        _apply_reconcile(win, _RECONCILE_RESULT)
        checker = _DepsChecker(win)
        checker.done.connect(lambda err: _on_deps_checked(err, win))
        checker.start()
        # Silent Smart Updater — keep ref on window to prevent GC.
        from core.updater import start_update_check
        win._update_checker = start_update_check(win)

    splash.ready_to_start.connect(_on_ready)

    # Allow Ctrl+C (SIGINT) to quit the Qt event loop cleanly.
    # Qt's C++ loop doesn't return to Python regularly, so we use a short
    # no-op timer to give Python a chance to handle the signal every 200 ms.
    signal.signal(signal.SIGINT, lambda *_: QApplication.quit())
    _sigint_timer = QTimer()
    _sigint_timer.start(200)
    _sigint_timer.timeout.connect(lambda: None)



    sys.exit(app.exec())


def _apply_reconcile(window: MainWindow, result) -> None:
    """Surface rolled-back / needs-reinstall results from launch reconcile."""
    from core.i18n import tr

    for cid in result.rolled_back:
        window.update_status(tr("install_interrupted_toast"), is_error=True)
        break  # one-shot toast, not per id

    if not result.needs_reinstall:
        return

    window.update_status(tr("install_needs_reinstall_toast"))

    def _kick_off(component_id: str) -> None:
        try:
            proc = model_manager.start_install(
                component_id,
                on_line=lambda line: window.update_status(
                    tr("install_progress").format(line=line[:120])
                ),
            )
        except Exception as exc:  # missing runtime / disk / etc.
            window.update_status(
                tr("install_error_generic").format(error=str(exc)), is_error=True
            )
            return

        def _on_finished(exit_code: int, _status) -> None:
            tail = bytes(proc.readAllStandardOutput()).decode("utf-8", errors="replace")
            model_manager.finalize_install(component_id, exit_code, tail)
            if exit_code == 0:
                model_manager.ensure_ai_packages_on_path()
                window.update_status(tr("install_done"))
            else:
                window.update_status(
                    tr("install_error_generic").format(error=f"exit {exit_code}"),
                    is_error=True,
                )

        proc.finished.connect(_on_finished)

    for cid in result.needs_reinstall:
        _kick_off(cid)


def _on_deps_checked(error: str, window: MainWindow) -> None:
    if error == "ffmpeg_missing":
        from core.i18n import tr
        QMessageBox.critical(
            window,
            tr("dep_error_title"),
            tr("dep_error_ffmpeg"),
        )
        window.update_status(tr("dep_error_status"), is_error=True)


if __name__ == "__main__":
    main()
