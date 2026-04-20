# Quickstart: Playwright HLS Stream Intercept

## Prerequisites

```bash
pip install playwright
python -m playwright install chromium
```

Existing deps (yt-dlp, ffmpeg, PySide6) unchanged.

## How It Works

1. User pastes a URL in the Download tab and clicks Download.
2. App tries yt-dlp as normal.
3. If yt-dlp returns `no_video`, app automatically tries Playwright browser intercept.
4. Status bar shows: "Loading page…" → "Waiting for stream URL…" → "Stream URL captured."
5. Download proceeds via yt-dlp with the captured `.m3u8` URL and browser cookies.

## Fallback Chain

```
yt-dlp
  └─ fail (no_video) ──► HTTP direct download (existing)
                             └─ fail ──► HTML scrape (existing)
                                            └─ fail ──► Playwright intercept (NEW)
```

## Settings

| Setting | Default | Location |
|---------|---------|----------|
| `intercept_timeout` | `30` seconds | Settings tab → Advanced |

Range: 10–300 seconds.

## Cancellation

Click **Cancel** at any time during the intercept phase. The browser closes within ~1 second and the UI resets.

## Playwright Not Installed

If Playwright or Chromium is missing, the intercept step is skipped and the existing `no_video` error is shown with an added hint:

> "Browser intercept unavailable — install Playwright to enable fallback for JS-rendered sites."

## Running Tests

```bash
# Unit tests (no browser needed)
pytest tests/unit/test_interceptor.py -v

# Live integration test (requires network + playwright install)
LIVE_TEST=1 pytest tests/integration/test_intercept_live.py -v
```
