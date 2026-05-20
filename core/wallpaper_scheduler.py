"""Time-based auto-apply for named wallpaper setups.

Schedules persist at ``user_config_dir()/wallpaper_schedule.json``. Each entry::

    {
      "id": "<auto-uuid>",
      "setup_name": "Work setup",
      "weekdays": [0,1,2,3,4],   # Monday=0..Sunday=6
      "time": "08:30",           # 24h HH:MM
      "enabled": true,
      "last_fired_iso": null
    }

The runtime piece is a thin QObject — `WallpaperScheduler` — that polls every
60 s, fires due entries by calling a user-supplied callback ``on_fire(name)``
and updates ``last_fired_iso`` so the same entry doesn't fire twice in a minute.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer

from utils.paths import user_config_dir


@dataclass
class ScheduleEntry:
    id: str = ""
    setup_name: str = ""
    weekdays: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    time: str = "08:00"
    enabled: bool = True
    last_fired_iso: Optional[str] = None


def _store_path() -> str:
    return os.path.join(str(user_config_dir()), "wallpaper_schedule.json")


def load_entries() -> list[ScheduleEntry]:
    p = _store_path()
    if not os.path.isfile(p):
        return []
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    out: list[ScheduleEntry] = []
    for blob in data.get("entries", []):
        e = ScheduleEntry()
        for k in e.__dataclass_fields__:
            if k in blob:
                setattr(e, k, blob[k])
        if not e.id:
            e.id = uuid.uuid4().hex
        out.append(e)
    return out


def save_entries(entries: list[ScheduleEntry]) -> None:
    p = _store_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"entries": [asdict(e) for e in entries]}, f, indent=2)


class WallpaperScheduler(QObject):
    """Polls every 60s and fires entries whose time/weekday match.

    `on_fire(setup_name: str)` is called for each due entry. Caller is
    responsible for actually loading the setup and applying it.
    """

    def __init__(self, on_fire: Callable[[str], None], parent=None) -> None:
        super().__init__(parent)
        self._on_fire = on_fire
        self._timer = QTimer(self)
        self._timer.setInterval(60_000)  # poll once a minute
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._tick()  # fire any immediately-due entries on boot
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        entries = load_entries()
        if not entries:
            return
        now = datetime.now()
        hhmm = now.strftime("%H:%M")
        weekday = now.weekday()
        today_iso = now.strftime("%Y-%m-%dT%H:%M")
        changed = False
        for e in entries:
            if not e.enabled or not e.setup_name:
                continue
            if weekday not in (e.weekdays or []):
                continue
            if e.time != hhmm:
                continue
            # Dedup: don't fire twice within the same minute.
            if e.last_fired_iso == today_iso:
                continue
            try:
                self._on_fire(e.setup_name)
            except Exception:
                # User code should swallow its own errors; we never abort the loop.
                pass
            e.last_fired_iso = today_iso
            changed = True
        if changed:
            save_entries(entries)
