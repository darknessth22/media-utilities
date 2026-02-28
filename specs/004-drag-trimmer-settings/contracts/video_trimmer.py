"""
Contract: Video Trimmer Widget (gui/video_trimmer.py)

This contract defines the interface for the visual video trimmer component.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol
import tkinter as tk


@dataclass
class TrimSelection:
    """Current trim selection state."""

    video_path: Path
    duration_ms: int
    start_ms: int
    end_ms: int
    is_playing: bool
    is_muted: bool
    volume: int  # 0-100


class VideoTrimmerWidget(Protocol):
    """Protocol for the visual video trimmer widget."""

    # Properties
    @property
    def is_vlc_available(self) -> bool:
        """Whether VLC is installed and functional."""
        ...

    @property
    def selection(self) -> TrimSelection | None:
        """Current trim selection, or None if no video loaded."""
        ...

    # Lifecycle
    def load_video(self, path: Path) -> bool:
        """
        Load a video file into the player.

        Args:
            path: Path to video file

        Returns:
            True if loaded successfully, False otherwise

        Behavior:
            - Shows loading indicator during load
            - Extracts duration from metadata
            - Displays first frame
            - Initializes handles at start/end
            - Shows warning if file >4GB
            - Returns False and shows error if file corrupted
        """
        ...

    def clear(self) -> None:
        """
        Clear the current video and reset state.

        Behavior:
            - Stops playback if playing
            - Releases VLC resources
            - Resets UI to empty state
        """
        ...

    def destroy(self) -> None:
        """
        Clean up all resources.

        Behavior:
            - Stops playback
            - Releases VLC instance
            - Destroys tkinter widget
        """
        ...

    # Playback controls
    def play(self) -> None:
        """
        Start or resume playback of selected segment.

        Behavior:
            - Plays from start_ms to end_ms
            - Loops back to start_ms when reaching end_ms
            - No-op if no video loaded
        """
        ...

    def pause(self) -> None:
        """Pause playback. No-op if not playing."""
        ...

    def toggle_play(self) -> None:
        """Toggle between play and pause."""
        ...

    def set_muted(self, muted: bool) -> None:
        """Set mute state."""
        ...

    def set_volume(self, volume: int) -> None:
        """
        Set volume level.

        Args:
            volume: Volume level 0-100
        """
        ...

    # Selection controls
    def set_start_ms(self, ms: int) -> None:
        """
        Set start point.

        Args:
            ms: Start time in milliseconds

        Behavior:
            - Clamps to valid range [0, end_ms - 1]
            - Seeks video to new position
            - Updates timeline handle position
        """
        ...

    def set_end_ms(self, ms: int) -> None:
        """
        Set end point.

        Args:
            ms: End time in milliseconds

        Behavior:
            - Clamps to valid range [start_ms + 1, duration_ms]
            - Updates timeline handle position
        """
        ...

    def get_selection_timestamps(self) -> tuple[str, str]:
        """
        Get formatted timestamps for current selection.

        Returns:
            Tuple of (start_timestamp, end_timestamp) in HH:MM:SS.mmm format
        """
        ...


# Callback when selection changes (for syncing with text inputs)
OnSelectionChanged = Callable[[int, int], None]  # (start_ms, end_ms)

# Callback when video load fails
OnLoadError = Callable[[str], None]  # error message


def create_video_trimmer(
    parent: tk.Widget,
    on_selection_changed: OnSelectionChanged | None = None,
    on_load_error: OnLoadError | None = None,
) -> VideoTrimmerWidget:
    """
    Factory function to create a VideoTrimmerWidget.

    Args:
        parent: Parent tkinter widget
        on_selection_changed: Callback when trim points change
        on_load_error: Callback when video loading fails

    Returns:
        VideoTrimmerWidget instance (or fallback if VLC unavailable)
    """
    ...
