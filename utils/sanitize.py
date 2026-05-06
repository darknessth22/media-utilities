"""Path sanitization utilities for auto-generated filenames."""
from __future__ import annotations

import re
import unicodedata

# Characters illegal on Windows, macOS, and Linux filesystems
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Sequences of dots that form reserved device names on Windows
_RESERVED_NAMES = re.compile(
    r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)', re.IGNORECASE
)
# Collapse runs of whitespace/underscores/hyphens
_COLLAPSE_SEP = re.compile(r'[\s_\-]{2,}')
# Strip leading/trailing dots and spaces (illegal on Windows)
_EDGE_DOTS = re.compile(r'^[\s.]+|[\s.]+$')


def sanitize_filename(name: str, replacement: str = "_", max_length: int = 200) -> str:
    """Strip dangerous characters from an auto-generated filename stem.

    - Normalises unicode to NFC
    - Replaces illegal filesystem characters
    - Rejects Windows reserved device names
    - Collapses repeated separators
    - Trims leading/trailing dots and spaces
    - Caps length at *max_length* characters

    Returns a safe filename stem (no extension, no path separators).
    Raises ValueError if the result would be empty after sanitization.
    """
    if not isinstance(name, str):
        raise TypeError(f"Expected str, got {type(name).__name__}")

    # Normalise unicode
    name = unicodedata.normalize("NFC", name)

    # Replace illegal characters
    name = _ILLEGAL_CHARS.sub(replacement, name)

    # Collapse repeated separators
    name = _COLLAPSE_SEP.sub("_", name)

    # Strip leading/trailing dots and spaces
    name = _EDGE_DOTS.sub("", name)

    # Enforce max length (preserve extension suffix if caller passes one)
    name = name[:max_length]

    # Re-strip edges in case truncation produced a trailing dot/space
    name = _EDGE_DOTS.sub("", name)

    if not name:
        raise ValueError("Filename is empty after sanitization")

    # Reject Windows reserved device names
    if _RESERVED_NAMES.match(name):
        name = f"_{name}"

    return name


def is_safe_filename(name: str) -> bool:
    """Return True if *name* requires no sanitization."""
    try:
        return sanitize_filename(name) == name
    except ValueError:
        return False
