# Phase 005 — System Tray & History Dashboard

**Branch**: `005-tray-and-history`
**Status**: Draft | **Created**: 2026-02-28

## Goal

Enable the app to run in the background via the system tray and fire native OS notifications when tasks finish, plus a History tab for finding and acting on recently processed files.

## What This Phase Delivers

### System Tray & Native Notifications (P1)
- Close button minimizes app to system tray (default); "Quit on close" setting to change behavior
- Right-click tray icon menu: **Restore** / **Settings** / **Quit**
- Click tray icon → restore main window
- Native Windows/macOS notification fires on download or conversion completion
- Clicking notification restores window and opens History tab
- Fallback to in-app message box if OS notifications are disabled

### History Dashboard Tab (P2)
- Chronological list of recent downloads and conversions
- Each entry shows filename, type, timestamp
- **Open Folder** button — opens file location in native file explorer
- **Play** button — opens file in system default media player
- Missing files shown gracefully (buttons disabled or file-missing indicator)
- **Clear All History** button empties the list
- History persists across sessions; stores last 10 items (JSON)

## Key Dependencies
- `QSystemTrayIcon` — PySide6 system tray
- Local JSON file for history persistence (no SQLite)
- OS notification API (platform-native via PySide6 or `plyer` fallback)

## Acceptance Criteria (abridged)
- Long download completes while app is minimized → native notification appears
- Clicking notification restores app on History tab
- "Open Folder" opens correct directory in file explorer
- History survives app restart with last 10 entries

## Full Spec
See [`spec.md`](spec.md) for complete user stories, requirements, and edge cases.
