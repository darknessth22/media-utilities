"""
Contract: Settings Panel UI (gui/settings_panel.py)

This contract defines the interface for the settings modal/panel.
"""

from typing import Callable, Protocol
import tkinter as tk

from .settings import UserSettings


class SettingsPanel(Protocol):
    """Protocol for the settings panel UI component."""

    def show(self) -> None:
        """
        Display the settings panel.

        Behavior:
            - Opens as modal dialog (blocks main window)
            - Loads current settings into form fields
            - Centers on parent window
        """
        ...

    def hide(self) -> None:
        """
        Hide the settings panel.

        Behavior:
            - Saves current form state to settings
            - Closes the modal
            - Triggers on_settings_changed callback
        """
        ...

    def reset_to_defaults(self) -> None:
        """
        Reset all settings to defaults.

        Behavior:
            - Shows confirmation dialog
            - If confirmed, resets settings and updates form
            - Triggers on_settings_changed callback
        """
        ...


# Callback when settings are changed
OnSettingsChanged = Callable[[UserSettings], None]


def create_settings_panel(
    parent: tk.Widget,
    current_settings: UserSettings,
    on_settings_changed: OnSettingsChanged,
) -> SettingsPanel:
    """
    Factory function to create a SettingsPanel.

    Args:
        parent: Parent tkinter widget (main window)
        current_settings: Current UserSettings to populate form
        on_settings_changed: Callback when user saves settings

    Returns:
        SettingsPanel instance
    """
    ...


# UI Section definitions for the settings panel
SETTINGS_SECTIONS = [
    {
        "name": "Output",
        "fields": [
            {
                "key": "output_folder",
                "label": "Default Output Folder",
                "type": "folder_picker",
                "description": "Where to save converted/trimmed files by default",
            }
        ],
    },
    {
        "name": "Video",
        "fields": [
            {
                "key": "default_codec",
                "label": "Default Video Codec",
                "type": "dropdown",
                "options": [
                    ("Original (no re-encoding)", "original"),
                    ("H.264 (most compatible)", "h264"),
                    ("HEVC/H.265 (smaller files)", "hevc"),
                    ("VP9 (open source)", "vp9"),
                ],
                "description": "Codec to use when converting videos",
            }
        ],
    },
    {
        "name": "Appearance",
        "fields": [
            {
                "key": "theme_mode",
                "label": "Theme",
                "type": "dropdown",
                "options": [
                    ("Follow System", "auto"),
                    ("Light", "light"),
                    ("Dark", "dark"),
                ],
                "description": "Application color theme",
            }
        ],
    },
]
