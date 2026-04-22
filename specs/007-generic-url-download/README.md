# Phase 007 — Generic URL Video Download

**Branch**: `007-generic-url-download`
**Status**: Draft | **Created**: 2026-04-17

## Goal

Extend the downloader to handle any video URL — not just known social media platforms (YouTube, Facebook, Instagram, TikTok, Twitter/X) — without changing the existing behavior for those platforms.

## What This Phase Delivers

### Any-URL Download (P1)
- Paste any video URL → app attempts download via yt-dlp
- Direct video file links (`.mp4`, `.mkv`, `.webm`, etc.) supported: yt-dlp first, then plain HTTP fallback
- Platform label reads "Generic URL — download will be attempted" for unrecognized domains
- Known social media URLs: behavior unchanged

### Error Handling
- Network timeout enforced at 30 seconds with descriptive message
- Distinct error messages: network timeout / no video found / site unsupported / requires login
- Playlist detected → download first/primary video only + warning to user
- Filename derived from URL path segment when HTTP fallback used and no metadata available

### Feature Parity for Generic URLs (P3)
- Audio-only mode works same as for social media URLs
- "Check Formats" works if source exposes format list
- Output folder selection available
- Completed/failed downloads recorded in history

## Key Dependencies
- `yt-dlp` — primary download engine (existing)
- `urllib` stdlib — HTTP fallback for direct file links
- No new external dependencies

## Acceptance Criteria (abridged)
- Non-social-media video URL downloads to output folder
- Direct `.mp4` link downloads (yt-dlp first, HTTP fallback if needed)
- YouTube/Facebook/etc. behavior identical to pre-feature state
- 30 s timeout triggers descriptive error message

## Full Spec
See [`spec.md`](spec.md) for complete user stories, edge cases, and all functional requirements.
