"""Drag-and-drop file handler — PySide6 edition.

Migration caveat M-3: replaces tkinterdnd2 string-based parse with
QDropEvent.mimeData().urls() (list of QUrl objects).

The DroppedFile dataclass and tab-routing logic are preserved from the
legacy implementation; only process_drop() has been rewritten.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Literal, Optional, Tuple

from PySide6.QtCore import QUrl

FILE_TYPE_MAP: dict[str, set[str]] = {
    "video":    {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"},
    "audio":    {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"},
    "image":    {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".heic", ".heif"},
    "document": {".pdf", ".docx", ".doc"},
}

TAB_MAPPING: dict[str, str] = {
    "video":    "trim",
    "audio":    "trim",
    "image":    "convert",
    "document": "document",
}


@dataclass
class DroppedFile:
    path: str
    extension: str
    file_type: Literal["video", "audio", "image", "document", "unknown"]
    target_tab: Optional[Literal["trim", "convert", "batch", "document"]]
    size_bytes: int
    is_large: bool  # True when file exceeds 4 GB


class DndHandler:
    @staticmethod
    def detect_file_type(extension: str) -> str:
        """Return a broad category name for *extension* (with leading dot)."""
        ext = extension.lower()
        for type_name, exts in FILE_TYPE_MAP.items():
            if ext in exts:
                return type_name
        return "unknown"

    @staticmethod
    def map_to_tab(file_type: str, is_batch: bool = False) -> Optional[str]:
        """Map a file-type category to a section id."""
        if file_type == "unknown":
            return None
        if is_batch:
            return "batch"
        return TAB_MAPPING.get(file_type)

    @classmethod
    def process_drop(cls, urls: List[QUrl]) -> Tuple[List[DroppedFile], str]:
        """Process a list of QUrl objects from QDropEvent.mimeData().urls().

        Returns (dropped_files, error_message).  error_message is empty on
        full success; non-empty means at least a partial problem occurred.
        """
        paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
        if not paths:
            return [], "No valid local files found in drop payload."

        dropped_files: list[DroppedFile] = []
        file_types_found: set[str] = set()

        for path in paths:
            if not os.path.exists(path):
                continue
            ext = os.path.splitext(path)[1].lower()
            file_type = cls.detect_file_type(ext)
            size = os.path.getsize(path)
            dropped_files.append(
                DroppedFile(
                    path=path,
                    extension=ext,
                    file_type=file_type,  # type: ignore[arg-type]
                    target_tab=None,
                    size_bytes=size,
                    is_large=size > 4 * 1024 * 1024 * 1024,
                )
            )
            file_types_found.add(file_type)

        if not dropped_files:
            return [], "No valid existing files were dropped."

        if "unknown" in file_types_found and len(file_types_found) == 1:
            return dropped_files, "Unsupported file format."
        if "unknown" in file_types_found:
            return dropped_files, "Some files are of an unsupported format."

        is_batch = len(dropped_files) > 1
        if is_batch and len(file_types_found) > 1:
            return dropped_files, (
                "Mixed file types detected. "
                "Batch conversion requires files of the same type."
            )

        if file_types_found:
            resolved_type = next(iter(file_types_found))
            if resolved_type != "unknown":
                if is_batch:
                    if resolved_type == "image":
                        target_tab: Optional[str] = "batch"
                    else:
                        return dropped_files, (
                            f"Batch operations are only supported for image "
                            f"conversion, not {resolved_type}."
                        )
                else:
                    target_tab = cls.map_to_tab(resolved_type, False)

                for df in dropped_files:
                    df.target_tab = target_tab  # type: ignore[assignment]

        return dropped_files, ""
