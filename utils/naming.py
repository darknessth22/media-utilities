"""Output filename template helper."""
from __future__ import annotations

import os
from datetime import datetime


def apply_name_template(template: str, src_path: str, *, ext: str = "", **kwargs) -> str:
    """Return a filename stem from *template* applied to *src_path*.

    Supported placeholders:
      {name}     — source filename without extension
      {ext}      — target extension (without dot)
      {date}     — YYYYMMDD
      {datetime} — YYYYMMDD_HHMMSS
      Any extra keyword arguments are also available as placeholders.

    Falls back to bare basename on template error. The returned string has no
    path separators and no file extension — callers append `.{ext}` themselves.
    """
    base = os.path.splitext(os.path.basename(src_path))[0]
    if not ext:
        ext = os.path.splitext(src_path)[1].lstrip(".")
    now = datetime.now()
    ctx: dict[str, str] = {
        "name": base,
        "ext": ext,
        "date": now.strftime("%Y%m%d"),
        "datetime": now.strftime("%Y%m%d_%H%M%S"),
        **kwargs,
    }
    try:
        result = template.format(**ctx)
        # Strip path separators so callers never get a sub-directory accidentally.
        return result.replace("/", "_").replace("\\", "_")
    except (KeyError, ValueError):
        return base
