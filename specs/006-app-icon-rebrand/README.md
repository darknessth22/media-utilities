# Phase 006 — Custom App Icon & Rebrand to Medix

**Branch**: `006-app-icon-rebrand`
**Status**: Draft | **Created**: 2026-03-27

## Goal

Replace the default Python icon with a custom branded icon and rename the application from **MediaUtility** to **Medix** everywhere it appears.

## What This Phase Delivers

### Custom Icon (P1)
- Custom icon shown in: window title bar, OS taskbar, system tray, built executable file
- ICO format (Windows) and PNG format (cross-platform) supported
- Graceful fallback to default if icon file is missing or corrupted
- Icon auto-scaled for each context (title bar, taskbar, tray, executable)

### Application Rename to Medix (P1)
- Window title → "Medix"
- Taskbar tooltip/label → "Medix"
- System tray tooltip → "Medix"
- Built executable filename reflects "Medix" branding
- Add/Remove Programs entry shows "Medix"
- Backward compatibility: existing config/history files with "MediaUtility" remain readable

### Icon Setup Documentation (P2)
- Steps for users/developers to supply a custom icon file
- Accepts PNG or ICO; falls back gracefully on unsupported format
- Icon dimensions/format errors handled without crash

## Key Dependencies
- `Pillow` — icon generation/conversion in build script
- `PyInstaller` — icon embedding in executable (`--icon` flag)
- Inno Setup — installer icon (`SetupIconFile`)

## Acceptance Criteria (abridged)
- Custom icon visible in title bar, taskbar, tray, and built exe
- "Medix" appears in window title, taskbar, tray tooltip, and Add/Remove Programs
- Missing icon file does not crash the app

## Full Spec
See [`spec.md`](spec.md) for complete user stories, requirements, and edge cases.
