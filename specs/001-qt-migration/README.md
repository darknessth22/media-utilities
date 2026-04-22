# Phase 001 — PySide6 GUI Migration

**Branch**: `001-qt-migration`
**Status**: Draft | **Created**: 2026-03-02

## Goal

Migrate the entire GUI layer from tkinter to PySide6 (LGPL), delivering a proper desktop-grade application with a blue-themed aesthetic, custom title bar, sidebar navigation, system tray, and native notifications.

## What This Phase Delivers

### Layout Architecture
- Frameless window with custom title bar (drag region, minimize/maximize/close)
- Fixed 180 px left sidebar with icon + text nav items
- Section tab strip in main content area
- Full-width primary action button at bottom of content
- Status bar

### Visual Design System (Slate-Blue Palette)
- Full dark/light mode token sets (soft blue, not raw Material Blue)
- Custom icon (40×40 px SVG) in sidebar and title bar
- QSS stylesheets for all widgets

### System Tray & Notifications
- Minimize to tray on window close (default); "Quit on close" setting to override
- Right-click tray menu: Restore / Settings / Exit
- Native OS notification on task completion; fallback to in-app message box
- Clicking notification restores window and navigates to History tab

### Feature Parity
- All existing operations (download, convert, trim, document, history) work identically
- Drag-and-drop file loading auto-routes to correct tab
- Cancel button halts tasks gracefully; UI stays responsive

## Key Dependencies
- `PySide6` — Qt for Python (official, LGPL)
- `PySide6-Essentials` (QtWidgets, QtMultimedia, QtCore)
- History stored as local JSON (no SQLite)

## Acceptance Criteria (abridged)
- Custom logo visible in title bar, taskbar, and tray
- Blue-themed UI replaces all tkinter widgets
- Download/convert/trim operations produce same output as prior version
- App minimizes to tray and sends native notification on task completion

## Full Spec
See [`spec.md`](spec.md) for complete user stories, visual design tokens, requirements, and layout mockup.
