"""Click-to-record widget for a single keyboard shortcut."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QPushButton


class KeybindButton(QPushButton):
    """Shows a shortcut; click it, press a combination, and it records that.

    Recording grabs the keyboard so the combination being pressed cannot also
    trigger the shortcut it is replacing — without that, pressing Ctrl+Q while
    rebinding "Quit" would quit the app.

    Esc cancels, Backspace/Delete clears back to the action's default.
    """

    captured = Signal(str)     # new sequence, or "" to reset to default

    _MODIFIER_KEYS = {
        Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
        Qt.Key.Key_Meta, Qt.Key.Key_AltGr, Qt.Key.Key_CapsLock,
        Qt.Key.Key_NumLock, Qt.Key.Key_ScrollLock,
    }

    def __init__(self, sequence: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("BrowseBtn")
        self.setMinimumWidth(150)
        self.setCheckable(True)
        self._sequence = sequence
        self._recording = False
        self._refresh()
        self.clicked.connect(self._toggle_recording)

    # ── State ────────────────────────────────────────────────────────────────

    def sequence(self) -> str:
        return self._sequence

    def set_sequence(self, sequence: str) -> None:
        self._sequence = sequence or ""
        self._refresh()

    def _refresh(self) -> None:
        from core.i18n import tr

        if self._recording:
            self.setText(tr("keybind_press_keys"))
        else:
            self.setText(self._sequence or tr("keybind_unset"))

    # ── Recording ────────────────────────────────────────────────────────────

    def _toggle_recording(self) -> None:
        self._recording = self.isChecked()
        if self._recording:
            self.grabKeyboard()
        else:
            self.releaseKeyboard()
        self._refresh()

    def _stop(self) -> None:
        self._recording = False
        self.setChecked(False)
        self.releaseKeyboard()
        self._refresh()

    def focusOutEvent(self, event) -> None:
        # Clicking elsewhere mid-capture must not leave the keyboard grabbed.
        if self._recording:
            self._stop()
        super().focusOutEvent(event)

    def keyPressEvent(self, event) -> None:
        if not self._recording:
            super().keyPressEvent(event)
            return

        key = event.key()
        # Ignore the modifiers themselves — wait for the real key.
        if key in self._MODIFIER_KEYS:
            return
        if key == Qt.Key.Key_Escape:
            self._stop()
            return
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self._stop()
            self.captured.emit("")          # caller resets to the default
            return

        modifiers = event.modifiers()
        sequence = QKeySequence(key | int(modifiers.value)).toString(
            QKeySequence.SequenceFormat.PortableText
        )
        self._stop()
        if sequence:
            self._sequence = sequence
            self._refresh()
            self.captured.emit(sequence)

    def keyReleaseEvent(self, event) -> None:
        if self._recording:
            return          # swallow, so the release cannot reach the app
        super().keyReleaseEvent(event)
