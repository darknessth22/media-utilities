"""Entry point for Videl (PySide6).

Run with:
    python main.py
"""
import os
import signal
import sys

# Load .env before any package imports that read secrets at import time (e.g. bug reporter).
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.isfile(_env_path):
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

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

from utils.model_manager import ensure_ai_packages_on_path
ensure_ai_packages_on_path()

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
        checker = _DepsChecker(win)
        checker.done.connect(lambda err: _on_deps_checked(err, win))
        checker.start()

    splash.ready_to_start.connect(_on_ready)

    # Allow Ctrl+C (SIGINT) to quit the Qt event loop cleanly.
    # Qt's C++ loop doesn't return to Python regularly, so we use a short
    # no-op timer to give Python a chance to handle the signal every 200 ms.
    signal.signal(signal.SIGINT, lambda *_: QApplication.quit())
    _sigint_timer = QTimer()
    _sigint_timer.start(200)
    _sigint_timer.timeout.connect(lambda: None)



    sys.exit(app.exec())


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
