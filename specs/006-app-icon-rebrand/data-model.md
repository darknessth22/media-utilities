# Data Model: Custom App Icon & Rebrand to Medix

**Feature Branch**: `006-app-icon-rebrand`
**Date**: 2026-03-27

## Overview

This feature does not introduce new data entities, database tables, or persistent state. The changes are limited to:

1. **Static asset files** (icon images) — bundled with the application
2. **String constants** (application name) — hardcoded in source files

## Assets

### App Icon (runtime)
- **Location**: `assets/icons/app-icon.png`
- **Format**: PNG
- **Recommended size**: 256x256 pixels (minimum), will be scaled by Qt as needed
- **Used by**: `QApplication.setWindowIcon()` in `main.py`

### App Icon (executable)
- **Location**: `icon.ico` (project root)
- **Format**: Windows ICO (multi-size: 256, 128, 64, 32, 16)
- **Used by**: PyInstaller via `media_util_gui.spec` and `build_executable.py`

### In-App Logo (unchanged)
- **Location**: `assets/icons/dashboard.svg`
- **Format**: SVG
- **Used by**: Title bar logo, sidebar header logo (rendered via `_load_svg_icon()`)
- **Note**: This remains separate from the app icon. Users may optionally replace it for full rebranding.

## Name Constants

| Context | Old Value | New Value |
|---------|-----------|-----------|
| QApplication name | "Media Utility" | "Medix" |
| Window title label | "Media Utility" | "Medix" |
| Sidebar header label | "Media Utility" | "Medix" |
| System tray tooltip | "Media Utility" | "Medix" |
| Tray notifications | "Media Utility" | "Medix" |
| Executable name | "MediaUtility" | "Medix" |
| Installer app name | "Media Utility" | "Medix" |
| Install directory | `{autopf}\MediaUtility` | `{autopf}\Medix` |
