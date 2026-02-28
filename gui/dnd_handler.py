import os
import sys
from dataclasses import dataclass
from typing import List, Tuple, Literal, Optional

# Supported file type mapping according to data-model.md
FILE_TYPE_MAP = {
    "video": {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"},
    "audio": {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"},
    "image": {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".heic", ".heif"},
    "document": {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt"}
}

TAB_MAPPING = {
    "video": "trim",
    "audio": "trim",
    "image": "convert",
    "document": "document"
}

@dataclass
class DroppedFile:
    path: str
    extension: str
    file_type: Literal["video", "audio", "image", "document", "unknown"]
    target_tab: Optional[Literal["trim", "convert", "batch", "document"]]
    size_bytes: int
    is_large: bool

class DndHandler:
    @staticmethod
    def detect_file_type(extension: str) -> str:
        """Detect file type category based on extension."""
        ext = extension.lower()
        for type_name, exts in FILE_TYPE_MAP.items():
            if ext in exts:
                return type_name
        return "unknown"

    @staticmethod
    def map_to_tab(file_type: str, is_batch: bool = False) -> Optional[str]:
        """Map a generic file type or batch operation to a specific tab name."""
        if file_type == "unknown":
            return None
        if is_batch:
            return "batch"
        return TAB_MAPPING.get(file_type)

    @staticmethod
    def parse_dropped_paths(raw_data: str) -> List[str]:
        """
        Parse raw drop data from tkinterdnd2 which comes as a string.
        Paths with spaces are wrapped in curly braces {like this}.
        """
        if not raw_data:
            return []
        
        # tkinterdnd2 sends the file paths separated by space, but wraps paths with spaces in {}.
        return [f for f in raw_data.strip('{}').split('} {')] if '}' in raw_data else raw_data.split()

    @classmethod
    def process_drop(cls, raw_data: str) -> Tuple[List[DroppedFile], str]:
        """
        Process dropped files and return the dropped files and any error message.
        Error message will indicate if the file type is mixed for multi-file drop, or unknown.
        """
        paths = cls.parse_dropped_paths(raw_data)
        if not paths:
            return [], "No valid files found in drop payload."

        dropped_files = []
        file_types_found = set()

        for path in paths:
            if not os.path.exists(path):
                continue
            
            ext = os.path.splitext(path)[1].lower()
            file_type = cls.detect_file_type(ext)
            size = os.path.getsize(path)
            is_large = size > (4 * 1024 * 1024 * 1024)  # 4GB

            dropped_files.append(
                DroppedFile(
                    path=path,
                    extension=ext,
                    file_type=file_type, # type: ignore
                    target_tab=None,
                    size_bytes=size,
                    is_large=is_large
                )
            )
            file_types_found.add(file_type)

        if not dropped_files:
            return [], "No valid existing files were dropped."

        if "unknown" in file_types_found and len(file_types_found) == 1:
            return dropped_files, "Unsupported file format."
        elif "unknown" in file_types_found:
            return dropped_files, "Some files are of an unsupported format."

        is_batch = len(dropped_files) > 1

        if is_batch and len(file_types_found) > 1:
            return dropped_files, "Mixed file types detected. Batch conversion requires files of the same type."

        # Compute and assign the target tab
        if file_types_found:
            resolved_type = list(file_types_found)[0]
            if resolved_type != "unknown":
                if is_batch:
                    if resolved_type == "image":
                        target_tab = "batch"
                    else:
                        return dropped_files, f"Batch operations are only supported for image conversion, not {resolved_type}."
                else:
                    target_tab = cls.map_to_tab(resolved_type, False)
                
                for df in dropped_files:
                    df.target_tab = target_tab # type: ignore

        return dropped_files, ""
