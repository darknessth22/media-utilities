"""Reusable preset save/load toolbar for operation sections."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QWidget,
)

from core.settings import SettingsManager


class PresetsBar(QWidget):
    """Compact bar: [Preset: ▼ combo] [Load] [Save…] [Delete]

    Args:
        section_key:   Key under UserSettings.presets to scope this section's presets.
        settings:      Live UserSettings instance (mutated in-place on save/delete).
        get_data_fn:   Callable() -> dict — captures current section UI state.
        load_data_fn:  Callable(dict) -> None — restores UI state from a preset dict.
    """

    preset_loaded = Signal(str)  # preset name that was loaded

    def __init__(
        self,
        section_key: str,
        settings,
        get_data_fn: Callable[[], dict],
        load_data_fn: Callable[[dict], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._section_key = section_key
        self._settings = settings
        self._get_data = get_data_fn
        self._load_data = load_data_fn

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        lbl = QLabel("Preset:")
        lbl.setObjectName("TextMuted")
        lbl.setStyleSheet("font-size: 12px;")
        row.addWidget(lbl)

        self._combo = QComboBox()
        self._combo.setFixedWidth(200)
        self._combo.setPlaceholderText("— select preset —")
        row.addWidget(self._combo)

        load_btn = QPushButton("Load")
        load_btn.setObjectName("BrowseBtn")
        load_btn.setFixedWidth(56)
        load_btn.clicked.connect(self._on_load)
        row.addWidget(load_btn)

        save_btn = QPushButton("Save…")
        save_btn.setObjectName("BrowseBtn")
        save_btn.setFixedWidth(60)
        save_btn.clicked.connect(self._on_save)
        row.addWidget(save_btn)

        self._del_btn = QPushButton("Delete")
        self._del_btn.setObjectName("BrowseBtn")
        self._del_btn.setFixedWidth(60)
        self._del_btn.clicked.connect(self._on_delete)
        row.addWidget(self._del_btn)

        row.addStretch()
        self._refresh_combo()

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _section_presets(self) -> dict[str, dict]:
        return self._settings.presets.get(self._section_key, {})

    def _refresh_combo(self) -> None:
        self._combo.blockSignals(True)
        current = self._combo.currentText()
        self._combo.clear()
        for name in sorted(self._section_presets()):
            self._combo.addItem(name)
        idx = self._combo.findText(current)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        self._combo.blockSignals(False)
        self._del_btn.setEnabled(self._combo.count() > 0)

    # ── Slot handlers ──────────────────────────────────────────────────────────

    def _on_load(self) -> None:
        name = self._combo.currentText()
        data = self._section_presets().get(name)
        if data:
            self._load_data(data)
            self.preset_loaded.emit(name)

    def _on_save(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Save Preset", "Enter a name for this preset:"
        )
        name = name.strip()
        if not ok or not name:
            return
        data = self._get_data()
        self._settings.presets.setdefault(self._section_key, {})[name] = data
        SettingsManager.save(self._settings)
        self._refresh_combo()
        idx = self._combo.findText(name)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)

    def _on_delete(self) -> None:
        name = self._combo.currentText()
        section = self._settings.presets.get(self._section_key, {})
        if name in section:
            del section[name]
            SettingsManager.save(self._settings)
            self._refresh_combo()
