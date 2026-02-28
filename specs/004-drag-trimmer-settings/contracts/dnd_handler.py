"""
Contract: Drag-and-Drop Handler (gui/dnd_handler.py)

This contract defines the interface for handling file drops.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Protocol


FileType = Literal["video", "audio", "image", "document", "unknown"]
TargetTab = Literal["trim", "convert", "batch", "document"]


@dataclass
class DroppedFile:
    """Represents a file received via drag-and-drop."""

    path: Path
    extension: str
    file_type: FileType
    target_tab: TargetTab | None
    size_bytes: int
    is_large: bool  # True if >4GB


@dataclass
class DropResult:
    """Result of processing dropped files."""

    success: bool
    files: list[DroppedFile]
    target_tab: TargetTab | None
    error_message: str | None = None


class DndHandler(Protocol):
    """Protocol for drag-and-drop handling operations."""

    def detect_file_type(self, path: Path) -> FileType:
        """
        Detect file type based on extension.

        Args:
            path: File path to analyze

        Returns:
            Detected FileType enum value
        """
        ...

    def map_to_tab(self, file_type: FileType) -> TargetTab | None:
        """
        Map file type to target tab.

        Args:
            file_type: Detected file type

        Returns:
            Target tab ID or None if unsupported
        """
        ...

    def process_drop(self, raw_data: str) -> DropResult:
        """
        Process raw drop event data.

        Args:
            raw_data: Raw string from tkinterdnd2 drop event

        Returns:
            DropResult with parsed files and routing info

        Behavior:
            - Parses space-separated paths (handles quoted paths)
            - Validates each file exists
            - Detects file types
            - For multiple files of same type: target_tab = "batch"
            - For multiple files of mixed types: error_message set
            - For single file: target_tab based on file type
        """
        ...


# Callback type for when a file is successfully dropped
OnFileDropped = Callable[[DroppedFile], None]

# Callback type for batch drops
OnBatchDropped = Callable[[list[DroppedFile]], None]

# Callback type for drop errors
OnDropError = Callable[[str], None]
