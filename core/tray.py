"""System tray integration — QSystemTrayIcon (PySide6 edition).

Migration caveat M-2: replaces the pystray-based SystemTrayIntegration with
QSystemTrayIcon + QMenu.

T018 – QSystemTrayIcon + QMenu tray implementation
T019 – Native desktop notifications via QSystemTrayIcon.showMessage()

Spec acceptance scenarios covered:
  US3-1  : close (quit_on_close=OFF) → window hides, tray icon appears
  US3-1b : close (quit_on_close=ON)  → app terminates (handled in MainWindow)
  US3-2  : background task finishes → balloon notification from tray icon
  US3-3  : tray context-menu "Exit" → app terminates
"""
from __future__ import annotations

import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

_APP_ICON = os.path.join(os.path.dirname(__file__), "..", "assets", "videl_icon.png")


def _make_tray_icon(size: int = 22) -> QIcon:
    """Build a QIcon for the tray from the Videl PNG icon."""
    from PySide6.QtCore import Qt
    pixmap = QPixmap(_APP_ICON)
    if not pixmap.isNull():
        pixmap = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return QIcon(pixmap)


class SystemTrayIcon(QObject):
    """QSystemTrayIcon wrapper with Restore / Settings / Exit menu.

    Signals
    -------
    restore_requested  : user wants the window back (double-click or menu)
    settings_requested : user chose "Settings" from the tray menu
    quit_requested     : user chose "Exit" from the tray menu
    """

    restore_requested  = Signal()
    settings_requested = Signal()
    quit_requested     = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._tray = QSystemTrayIcon(_make_tray_icon(), self)
        self._tray.setToolTip("Videl")

        # ── Context menu ──────────────────────────────────────────────────────
        menu = QMenu()

        restore_action = menu.addAction("Restore")
        restore_action.setObjectName("TrayRestore")
        restore_action.triggered.connect(self.restore_requested)

        settings_action = menu.addAction("Settings")
        settings_action.triggered.connect(self.settings_requested)

        menu.addSeparator()

        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self.quit_requested)

        self._tray.setContextMenu(menu)

        # Double-click or single-click (platform default) restores the window
        self._tray.activated.connect(self._on_activated)

    # ── Public API ────────────────────────────────────────────────────────────

    @staticmethod
    def is_available() -> bool:
        """Return True if the current desktop supports a system tray."""
        return QSystemTrayIcon.isSystemTrayAvailable()

    def show(self) -> None:
        """Make the tray icon visible."""
        self._tray.show()

    def hide(self) -> None:
        """Remove the tray icon (called when the window is fully restored)."""
        self._tray.hide()

    def notify(
        self,
        title: str,
        message: str,
        is_error: bool = False,
        duration_ms: int = 5000,
    ) -> None:
        """Show a native balloon/toast notification from the tray icon.

        Parameters
        ----------
        title       : Bold notification heading
        message     : Body text
        is_error    : Use the Critical icon instead of Information
        duration_ms : How long the balloon stays visible (Windows: OS-controlled)
        """
        if not self._tray.isVisible():
            return   # Don't notify when the window is visible; status bar suffices
        icon_type = (
            QSystemTrayIcon.MessageIcon.Critical
            if is_error
            else QSystemTrayIcon.MessageIcon.Information
        )
        self._tray.showMessage(title, message, icon_type, duration_ms)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Restore the window on double-click (or single-click on some platforms)."""
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,   # single-click on Linux/macOS
        ):
            self.restore_requested.emit()
