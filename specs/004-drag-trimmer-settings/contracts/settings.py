"""
Contract: Settings Module (core/settings.py)

This contract defines the public interface for settings persistence.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol


CodecType = Literal["h264", "hevc", "vp9", "original"]
ThemeMode = Literal["light", "dark", "auto"]


@dataclass
class UserSettings:
    """User preferences data structure."""

    output_folder: str | None = None
    default_codec: CodecType = "original"
    theme_mode: ThemeMode = "auto"
    version: int = 1


class SettingsManager(Protocol):
    """Protocol for settings persistence operations."""

    def load(self) -> UserSettings:
        """
        Load settings from disk.

        Returns:
            UserSettings with values from config file, merged with defaults.

        Behavior:
            - If config file doesn't exist, returns defaults
            - If config file is corrupted, logs warning and returns defaults
            - If config file has missing keys, fills with defaults (merge)
            - If config file has unknown keys, ignores them
        """
        ...

    def save(self, settings: UserSettings) -> None:
        """
        Persist settings to disk.

        Args:
            settings: UserSettings to save

        Behavior:
            - Creates parent directories if needed
            - Overwrites existing file atomically
            - Raises PermissionError if directory not writable
        """
        ...

    def reset(self) -> UserSettings:
        """
        Reset settings to defaults and persist.

        Returns:
            Fresh UserSettings with all defaults
        """
        ...

    @staticmethod
    def get_config_path() -> Path:
        """
        Get platform-specific config file path.

        Returns:
            Windows: %APPDATA%/media-utilities/config.json
            macOS: ~/Library/Application Support/media-utilities/config.json
            Linux: ~/.config/media-utilities/config.json
        """
        ...
