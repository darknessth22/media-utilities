"""Entry point for Media Utility (PySide6).

Run with:
    python main.py
"""
import signal
import sys

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QThread, QTimer, Signal, qInstallMessageHandler, QtMsgType


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

from core.settings import SettingsManager
from gui.app import MainWindow
from gui.theme import ThemeManager


class _DepsChecker(QThread):
    """Background thread that validates runtime dependencies."""
    done = Signal(str)  # "" = all OK, "ffmpeg_missing" = critical error

    def run(self) -> None:
        from utils.deps import check_dependencies
        result = check_dependencies()
        self.done.emit(result or "")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Media Utility")
    app.setOrganizationName("Omniclouds")
    # Prevent the process from exiting when the last window is hidden to tray.
    app.setQuitOnLastWindowClosed(False)

    # Load user settings
    settings = SettingsManager.load()

    # Initialise and apply theme
    theme_manager = ThemeManager(app)
    theme_manager.set_mode(settings.theme_mode)

    # Create and show the main window immediately so the user sees the UI.
    window = MainWindow(settings, theme_manager)
    window.show()

    # Allow Ctrl+C (SIGINT) to quit the Qt event loop cleanly.
    # Qt's C++ loop doesn't return to Python regularly, so we use a short
    # no-op timer to give Python a chance to handle the signal every 200 ms.
    signal.signal(signal.SIGINT, lambda *_: QApplication.quit())
    _sigint_timer = QTimer()
    _sigint_timer.start(200)
    _sigint_timer.timeout.connect(lambda: None)

    # Check dependencies in the background; notify on critical failure.
    checker = _DepsChecker(window)
    checker.done.connect(lambda err: _on_deps_checked(err, window))
    checker.start()

    sys.exit(app.exec())


def _on_deps_checked(error: str, window: MainWindow) -> None:
    if error == "ffmpeg_missing":
        QMessageBox.critical(
            window,
            "Missing Dependency",
            "FFmpeg was not found on this system.\n\n"
            "Media conversion, trimming, and download features will not work.\n\n"
            "Install FFmpeg and add it to your system PATH, or place ffmpeg.exe "
            "in the same directory as this application.\n\n"
            "Download from: https://ffmpeg.org/download.html",
        )
        window.update_status("FFmpeg not found — some features unavailable.", is_error=True)


if __name__ == "__main__":
    main()
