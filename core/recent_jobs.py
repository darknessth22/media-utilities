"""Recent-tools store. Tracks the last N tools the user opened so the home
page can surface them as a Recent strip — the slot previously occupied by
the Quick Access duplicate row.

Stored alongside config.json in the platform-specific Videl data dir.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Tuple

from core.settings import SettingsManager

_FILENAME = "recent_jobs.json"
_MAX_ENTRIES = 8


def _store_path() -> Path:
    return SettingsManager.get_config_path().parent / _FILENAME


def _read() -> list[dict]:
    p = _store_path()
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return [e for e in data if isinstance(e, dict) and "tool_id" in e]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _write(entries: list[dict]) -> None:
    try:
        p = _store_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as fh:
            json.dump(entries, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def record_open(tool_id: str, section_idx: int) -> None:
    """Push a tool to the front of the recents list (de-duped)."""
    entries = [e for e in _read() if e.get("tool_id") != tool_id]
    entries.insert(0, {
        "tool_id": tool_id,
        "section_idx": section_idx,
        "ts": int(time.time()),
    })
    _write(entries[:_MAX_ENTRIES])


def list_recent(limit: int = 5) -> List[Tuple[str, int]]:
    """Return [(tool_id, section_idx)] for the most-recent N tools."""
    return [(e["tool_id"], int(e.get("section_idx", 0))) for e in _read()[:limit]]


def clear() -> None:
    _write([])
