"""Cross-platform user-data path resolver.

Single source of truth for where Videl writes per-user state. Branches on
`sys.platform` so the same call returns the right location on Windows, Linux,
and macOS.

Layout:
  Windows  config   = %APPDATA%\\Videl
           data     = %LOCALAPPDATA%\\Videl
  Linux    config   = $XDG_CONFIG_HOME/Videl       (fallback ~/.config/Videl)
           data     = $XDG_DATA_HOME/Videl         (fallback ~/.local/share/Videl)
  macOS    both     = ~/Library/Application Support/Videl

Use `user_config_dir()` for small JSON state (settings, history). Use
`user_data_dir()` / `ai_packages_dir()` for large caches (AI packages, whisper
binaries + models).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Videl"


def user_config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / APP_NAME


def user_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / APP_NAME


def ai_packages_dir() -> Path:
    return user_data_dir() / "ai_packages"
