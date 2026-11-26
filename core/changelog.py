"""Release notes shown in the app: Settings, What's new, and the card after an update.

One file, assets/changelog.json, newest first:
    [{"version": "5.3.0", "date": "2026-11-27", "en": ["..."], "ar": ["..."]}, ...]
Add an entry with every release (WORKFLOW.md, Release).
"""
from __future__ import annotations

import json

from core.paths import resource_path


def load() -> list[dict]:
    try:
        with open(resource_path("assets/changelog.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return [e for e in data if isinstance(e, dict) and e.get("version")]


def notes(entry: dict, lang: str) -> list[str]:
    """The entry's bullets in *lang*, falling back to English."""
    return list(entry.get(lang) or entry.get("en") or [])


def for_version(version: str) -> dict | None:
    return next((e for e in load() if e["version"] == version), None)
