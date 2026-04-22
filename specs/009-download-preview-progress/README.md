# Phase 009 — Download Preview & Rich Progress

**Branch**: `009-download-preview-progress`
**Status**: Draft | **Created**: 2026-04-20

## Goal

Replace the indeterminate spinner in the download tab with real progress information (%, speed, ETA), and add an optional video preview player so users can visually select a time range before downloading.

## What This Phase Delivers

### Rich Download Progress (P1)
- Determinate progress bar (0–100%) when total file size is known
- Download speed label — updates at least once per second in KB/s or MB/s
- ETA label — remaining seconds or minutes, updates live
- Fallback to indeterminate bar when size unknown; speed still shown if available
- Works for all download paths: yt-dlp, HTTP fallback, and Playwright browser intercept
- Progress/speed/ETA all reset cleanly on success, failure, or cancel

### Download Preview Player (P2)
- "Load Preview" button in download tab (video mode only)
- Embedded video player appears between options area and progress bar (zero height when hidden)
- Reuses trim tab's `QSlider`-based start/end marker component
- Dragging start/end markers syncs with Start/End time input fields (HH:MM:SS)
- Clicking Download with markers set → only that segment downloaded via yt-dlp `--download-sections`
- URL change → preview player hides and time range resets
- Preview unavailable (audio-only, live stream, unsupported site) → clear message, text inputs still usable

## Key Dependencies
- `PySide6 QtMultimedia` — embedded video player
- `yt-dlp` — progress hooks + `--download-sections` for segment download
- `urllib` stdlib — updated to chunked read loop for HTTP fallback progress
- Reuses trim tab's `QSlider` timeline component

## Acceptance Criteria (abridged)
- Progress bar fills incrementally (not indeterminate) for any known-size download
- Speed label updates every second; ETA counts down
- Load Preview streams video without downloading full file
- Start/end markers set time range; Download fetches only that segment
- All reset cleanly after any download outcome

## Full Spec
See [`spec.md`](spec.md) for complete user stories, edge cases, and functional requirements.
