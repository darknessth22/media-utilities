"""Named multi-monitor wallpaper setups.

Separate from `image_editor.save_user_preset` (which stores a single-image edit
recipe). A setup captures the whole wallpaper card state: a list of MonitorSpec
dicts. Useful for switching between "Work setup", "Gaming setup" etc.

Stored at ``user_config_dir()/wallpaper_setups.json`` — schema::

    {
      "<name>": {"rows": [<MonitorSpec asdict>, ...]},
      ...
    }
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Iterable

from core.image_editor import MonitorSpec, preset_to_config
from utils.paths import user_config_dir


def _store_path() -> str:
    return os.path.join(str(user_config_dir()), "wallpaper_setups.json")


def load_all() -> dict[str, dict]:
    p = _store_path()
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def list_names() -> list[str]:
    return sorted(load_all().keys())


def save(name: str, specs: Iterable[MonitorSpec]) -> None:
    name = name.strip()
    if not name:
        raise ValueError("Setup name cannot be empty.")
    all_setups = load_all()
    all_setups[name] = {"rows": [asdict(s) for s in specs]}
    p = _store_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(all_setups, f, indent=2)


def load(name: str) -> list[MonitorSpec]:
    """Restore a named setup as a list of MonitorSpec objects."""
    blob = load_all().get(name)
    if not blob:
        return []
    rows = blob.get("rows") or []
    out: list[MonitorSpec] = []
    for row in rows:
        spec = MonitorSpec()
        for k in spec.__dataclass_fields__:
            if k not in row:
                continue
            if k == "edit_cfg" and isinstance(row[k], dict):
                spec.edit_cfg = preset_to_config(row[k])
            else:
                setattr(spec, k, row[k])
        out.append(spec)
    return out


def delete(name: str) -> bool:
    all_setups = load_all()
    if name not in all_setups:
        return False
    del all_setups[name]
    p = _store_path()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(all_setups, f, indent=2)
    return True
