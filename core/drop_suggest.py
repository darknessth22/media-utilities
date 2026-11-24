"""Which tools can take the files dropped on Home (like the web app's drop suggestions).

Each tool lists the extensions its own file picker and core module accept, so a
suggestion never leads to a tool that refuses the file.
"""
from __future__ import annotations

import os

_VIDEO = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v"}
_VIDEO_BASIC = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}
_AUDIO = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"}
_IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
_TIFF = {".tif", ".tiff"}
_SUBS = {".srt", ".vtt", ".ass", ".ssa"}

# Most useful first: this is the order the buttons appear in.
_ACCEPTS: dict[str, set[str]] = {
    "convert": _VIDEO | _AUDIO | _IMAGE | {".gif", ".heic", ".heif", ".ico"},
    "compress": _VIDEO | _IMAGE,
    "trim": _VIDEO_BASIC | _AUDIO,
    "gif": _VIDEO,
    "merge": _VIDEO,
    "pdf_toolkit": {".pdf"},
    "document": {".pdf", ".docx", ".pptx", ".md", ".markdown", ".gif"} | _IMAGE,
    "subtitles": _VIDEO | _SUBS,
    "bg_eraser": _IMAGE | _TIFF,
    "upscaler": _IMAGE | _TIFF,
    "photo_restore": {".png", ".jpg", ".jpeg", ".webp"},
    "image_editor": _IMAGE | _TIFF,
    "spatial": _VIDEO | _IMAGE,
    "chunk": _VIDEO_BASIC | _AUDIO,
    "mux": _VIDEO,
    "transcript": _VIDEO | _AUDIO | {".opus", ".wma"},
    "vocal_isolator": _VIDEO_BASIC | _AUDIO | {".opus", ".wma"},
    "frame_grabber": _VIDEO | {".ts", ".mts", ".mxf", ".ogv"},
    "jumpcut": _VIDEO_BASIC | _AUDIO,
    "watermark": _VIDEO | _IMAGE | _TIFF,
    "scrub": _VIDEO | _AUDIO,
    "video_upscaler": _VIDEO | {".mpg", ".mpeg"},
    "pixel_art": _IMAGE | _TIFF | {".gif"} | _VIDEO,
    "palette": _IMAGE | _TIFF | {".gif"} | _VIDEO,
}

# Tools whose section takes several files at once (populate_files or
# populate_batch_files); the rest take one.
MULTI = {"convert", "merge", "image_editor", "pixel_art", "scrub", "watermark"}


def suggest_tools(paths: list[str]) -> list[str]:
    """Tool ids that accept every one of these files, most useful first."""
    exts = {os.path.splitext(p)[1].lower() for p in paths}
    if not exts:
        return []
    return [tool for tool, ok in _ACCEPTS.items()
            if exts <= ok and (len(paths) == 1 or tool in MULTI)]
