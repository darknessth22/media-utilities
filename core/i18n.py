"""Lightweight i18n engine — English / Arabic toggle with RTL support."""
from __future__ import annotations

import json
import os

from PySide6.QtCore import QObject, Signal

from core.paths import resource_path

_LOCALES_DIR = resource_path("locales")


class I18n(QObject):
    """Singleton translation engine. Emits language_changed on switch."""

    language_changed = Signal(str)  # "en" or "ar"

    _instance: "I18n | None" = None

    def __init__(self) -> None:
        super().__init__()
        self._lang = "en"
        self._strings: dict[str, str] = {}
        self._load("en")

    @classmethod
    def instance(cls) -> "I18n":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Public API ────────────────────────────────────────────────────────────

    def set_language(self, lang: str) -> None:
        if lang == self._lang:
            return
        self._lang = lang
        self._load(lang)
        self.language_changed.emit(lang)

    def tr(self, key: str) -> str:
        return self._strings.get(key, key)

    @property
    def current_language(self) -> str:
        return self._lang

    @property
    def is_rtl(self) -> bool:
        return self._lang == "ar"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load(self, lang: str) -> None:
        path = os.path.join(_LOCALES_DIR, f"{lang}.json")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                self._strings = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            self._strings = {}


def tr(key: str) -> str:
    """Module-level shortcut for I18n.instance().tr(key)."""
    return I18n.instance().tr(key)
