# Phase 004 — Drag-Drop, Visual Trimmer & Global Settings

**Branch**: `004-drag-trimmer-settings`
**Status**: Draft | **Created**: 2026-02-28

## Goal

Three quality-of-life upgrades: drag-and-drop file loading, a visual timeline trimmer replacing manual timestamp entry, and a persistent global settings panel.

## What This Phase Delivers

### Drag-and-Drop File Loading (P1)
- Drop any supported file onto the app window → correct tab activates and file path populated automatically
- Video/audio → Trim Media tab
- PDF/DOCX → Document Convert tab
- Image → Convert Media tab
- Multiple files of same type → Batch Convert tab
- Unsupported type → user-friendly rejection message
- Drop blocked with message if an operation is already in progress

### Visual Timeline Trimmer (P2)
- Mini embedded video player with play/pause and mute controls
- Horizontal timeline with two draggable handles (green = start, red = end)
- Handles update start/end time fields in real time; video seeks on drag
- Loop playback of selected segment for preview
- Graceful fallback to text-based timestamp entry if video cannot be loaded

### Global Settings Panel (P3)
- Gear icon opens modal/slide-out settings panel
- Configurable: default output folder, default video codec (H264/HEVC/VP9/Original), theme mode (Light/Dark/System)
- Settings applied immediately on close; persist across restarts via config file
- "Reset to Defaults" button
- Corrupt or missing config file resets to defaults with a warning

## Key Dependencies
- `QDropEvent.mimeData().urls()` — PySide6 drag-and-drop
- `QMediaPlayer / QVideoWidget` — embedded video preview
- JSON config file in platform app-data directory

## Acceptance Criteria (abridged)
- Dropping a `.mp4` file activates Trim tab with path populated
- Trimmer timeline handles update start/end time fields in real time
- Settings survive app restart

## Full Spec
See [`spec.md`](spec.md) for complete user stories, edge cases, and requirements.
