# Quickstart: Generic URL Download (007)

**For**: Developer implementing or testing this feature  
**Branch**: `007-generic-url-download`

---

## What Changed

| File | Change |
|------|--------|
| `core/downloader.py` | `download_media()` extended: generic-URL-specific yt-dlp opts (timeout, playlist restriction), error classification, HTTP fallback |
| `gui/tabs/download_section.py` | Platform label updated for generic URLs; `_on_result()` and `_on_error()` use `error_code` and `warning` from result |

---

## Running the App

```bash
cd E:\Omniclouds\media-utilities
python main.py
```

---

## Manual Test Plan

### Test 1 — Generic video URL (yt-dlp supported site)

1. Paste a video URL from a non-social-media site (e.g., a news site with embedded video).
2. Verify platform label reads `"Generic URL — download will be attempted"`.
3. Click Download.
4. Verify file appears in output folder.
5. Verify history entry created with `status="success"`.

### Test 2 — Direct video file URL (.mp4)

1. Paste a direct `.mp4` URL (e.g., `https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4`).
2. Click Download.
3. Verify file downloaded (via yt-dlp or HTTP fallback).
4. Verify filename is either the video title (yt-dlp) or the URL path segment (HTTP fallback).

### Test 3 — Unsupported URL (no video)

1. Paste a URL to a plain webpage with no video.
2. Click Download.
3. Verify error message is specific: `"No downloadable video found at this URL."`
4. Verify history entry created with `status="error"`.

### Test 4 — Playlist URL

1. Paste a playlist URL (e.g., a YouTube playlist or any multi-item URL).
   - Note: for social media playlists, existing behavior is preserved.
   - For generic playlist URLs: system should download first item only.
2. Verify warning shown: `"Playlist detected — downloading first video only."`
3. Verify only one file downloaded.

### Test 5 — Timeout (simulate with unreachable host)

1. Paste `http://203.0.113.1/video.mp4` (RFC 5737 reserved/unreachable IP).
2. Click Download.
3. Wait up to 35 seconds.
4. Verify error message: `"Connection timed out. Check your network and try again."`

### Test 6 — Auth-required URL

1. Paste a URL known to require login.
2. Click Download.
3. Verify error: `"This video requires login — not supported for generic URLs."`

### Test 7 — Social media URLs unchanged (regression)

1. Paste a YouTube URL.
2. Verify platform label still reads `"YouTube"` (not generic).
3. Download and verify behavior identical to before this feature.
4. Repeat for Facebook, Instagram, TikTok, Twitter/X, Spotify.

---

## Lint & Tests

```bash
ruff check .
pytest
```
