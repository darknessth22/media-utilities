# Data Model: Download Preview & Rich Progress

## Entities

### DownloadProgressEvent

Emitted by `_progress_hook` (yt-dlp) or the HTTP fallback read loop.

| Field | Type | Description |
|-------|------|-------------|
| `percent` | `int \| None` | 0–100, or None when total size unknown |
| `speed_bps` | `float \| None` | bytes/s, or None when unavailable |
| `eta_seconds` | `int \| None` | estimated seconds remaining, or None |

**Wire format** (Worker signal): `Signal(int, int, str)` → `(percent_or_-1, eta_or_-1, speed_str)`
- `-1` is the sentinel for "unknown/unavailable"
- `speed_str` is pre-formatted: `"3.2 MB/s"`, `"512 KB/s"`, or `""`

**State transitions**:
```
idle → downloading (percent 0-100, or -1) → finished (percent=100) → idle
                                           → error → idle
                                           → cancelled → idle
```

---

### PreviewStream

Transient object — exists only while the preview player is active.

| Field | Type | Description |
|-------|------|-------------|
| `stream_url` | `str` | Direct HTTP(S) URL returned by yt-dlp `extract_info` |
| `duration_ms` | `int \| None` | Total duration in ms; None for live streams |
| `is_live` | `bool` | True → preview disabled |
| `title` | `str` | Video title for display |

**Not persisted** — discarded when URL changes or preview is dismissed.

---

### TimeRangeSelection

Shared state between the preview sliders and the text inputs.

| Field | Type | Description |
|-------|------|-------------|
| `start_ms` | `int` | Start position in milliseconds (0 = beginning) |
| `end_ms` | `int \| None` | End position in ms; None = end of video |

**Validation rule**: `start_ms < end_ms` (when `end_ms` is not None).  
**Format for yt-dlp**: `--download-sections "*{start_s}-{end_s}"` where `start_s = start_ms // 1000`.

---

## State Machine: DownloadSection

```
IDLE
  │  URL entered + Download clicked
  ▼
DOWNLOADING
  │  progress events → update bar, speed, ETA labels
  │  Cancel clicked → Worker.cancel() → IDLE
  │  error / network drop → IDLE (error message)
  ▼
DONE → IDLE (success message, history entry)

IDLE
  │  URL entered + Load Preview clicked
  ▼
PREVIEW_LOADING (spinner)
  │  extract_info fails / live / audio-only → IDLE (message)
  ▼
PREVIEW_ACTIVE
  │  URL field changes → IDLE (player hidden, time inputs reset)
  │  Download clicked → DOWNLOADING (time range passed to downloader)
  ▼
  (same DOWNLOADING flow as above)
```

---

## No Schema Changes

Download history (`HistoryItem`) is unchanged — no new fields required.  
`UserSettings` is unchanged — no new settings for this feature.
