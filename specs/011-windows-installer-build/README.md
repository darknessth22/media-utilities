# Phase 011 — Windows Installer Build

**Branch**: `011-windows-installer-build`
**Status**: Draft | **Created**: 2026-04-22

## Goal

Package the app as a signed Windows installer (.exe) that launches fast, shows the branded Medix icon everywhere Windows displays it, and keeps total install size within a tracked budget.

## What This Phase Delivers

### One-Click Windows Installer (P1)
- Single `.exe` installer produced by **Inno Setup 6**
- Works on clean Windows 10/11 with no Python or ffmpeg pre-installed
- Installs to `Program Files`; creates Start Menu shortcut + desktop shortcut
- Uninstaller removes all files, shortcuts, and registry entries (preserves user data/history)
- Upgrade install preserves history + settings, replaces binaries

### Fast Cold Start (P1)
- **Directory-based** PyInstaller build (not `--onefile`) — no per-launch self-extraction
- Cold start target: main window interactive in **≤ 3 seconds** on mid-range hardware
- Warm start target: **≤ 1.5 seconds**
- No AV re-scan thrash on each launch (static directory, not re-extracted each time)

### Size Monitoring (P2)
- `size-budget.json` committed in repo defines installer size + unpacked size limits
- `build_executable.py` reports installer size, installed size, and top-10 largest contributors after every build
- Build fails with clear message if any limit exceeded
- Raising the budget requires intentional commit of updated `size-budget.json`

### Full Branding (P2)
- Branded icon visible in: installer UI, Start Menu shortcut, taskbar, Alt-Tab switcher, tray, window title bar, Add/Remove Programs entry
- Installer `.exe` file icon = Medix logo
- Publisher name and version set in Add/Remove Programs

## Key Dependencies
- `PyInstaller 6.x` — directory-based bundle
- `Inno Setup 6.x` (`iscc.exe`) — Windows installer
- `ffmpeg 7.1` (gyan.dev essentials build) — bundled in installer
- `PySide6`, `yt-dlp`, `playwright` — existing app dependencies

## Build Artifacts (not committed)
- `dist/` — PyInstaller output directory
- `build/` — PyInstaller work directory
- `Output/` — Inno Setup installer `.exe`
- `bin/` — ffmpeg/ffprobe/ffplay executables for bundling

## Running the Build
```bat
build.bat
```
Or directly:
```bash
python build_executable.py
```

## Acceptance Criteria (abridged)
- Fresh Windows VM: installer runs, app launches, all tabs functional
- Cold start ≤ 3 s; warm start ≤ 1.5 s
- Build log shows size report; exceeding budget fails build
- Medix icon visible on all Windows surfaces listed above

## Full Spec
See [`spec.md`](spec.md) for complete user stories, edge cases, and functional requirements.
