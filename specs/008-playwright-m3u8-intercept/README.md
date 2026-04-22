# Phase 008 — Playwright HLS Stream Intercept

**Branch**: `008-playwright-m3u8-intercept`
**Status**: Draft | **Created**: 2026-04-17

## Goal

Add a browser-based fallback download path: when yt-dlp fails on a JS-rendered site, launch a headless Playwright browser, intercept `.m3u8` HLS manifest requests from the page network traffic, and hand the captured stream URL to the existing download pipeline.

## What This Phase Delivers

### Automatic Browser Fallback (P1)
- yt-dlp attempted first; if it returns unsupported-URL or extraction failure → Playwright intercept fires automatically (no user action)
- Headless browser fully executes page JavaScript for the submitted URL
- All outgoing network requests monitored; `.m3u8` URLs captured
- Captured URL + session cookies + request headers passed directly to download pipeline
- Multiple `.m3u8` URLs → highest-quality variant selected from HLS master playlist

### Error Handling & Cancellation (P2)
- Configurable timeout on browser session; if no `.m3u8` intercepted → clear error message, UI returns to ready state
- Missing Playwright dependency → descriptive error without crash
- User can cancel in-progress browser session; browser process killed immediately

### Live Status During Intercept (P3)
- Status messages in download tab: "Loading page…", "Waiting for stream URL…", etc.
- Progress visible to user throughout; no frozen UI appearance

## Key Dependencies
- `playwright` (Python sync API) — headless browser
- `yt-dlp` — existing primary downloader
- `PySide6` — existing GUI

## Download Pipeline Order
1. yt-dlp → success → done
2. yt-dlp fails → Playwright intercept → capture `.m3u8` → download via yt-dlp/ffmpeg
3. Playwright timeout/failure → error message shown

## Acceptance Criteria (abridged)
- JS-gated video site: app downloads without user installing extra tools
- yt-dlp-supported sites: behavior unchanged
- Cancel during intercept: browser killed, UI resets cleanly
- No `.m3u8` found within timeout: clear error, no crash or hang

## Full Spec
See [`spec.md`](spec.md) for complete user stories, edge cases, and functional requirements.
