# Data Model: Playwright HLS Stream Intercept

## Entities

### 1. InterceptSession (in-memory only)

Represents one headless browser run.

| Field | Type | Description |
|-------|------|-------------|
| `url` | `str` | Target page URL |
| `state` | `InterceptState` | Current state (see transitions below) |
| `captured_urls` | `list[str]` | All `.m3u8` URLs seen in network traffic |
| `selected_url` | `str \| None` | Best-quality variant URL after HLS parse |
| `cookies` | `list[dict]` | Browser context cookies (Playwright format) |
| `headers` | `dict[str, str]` | Extra request headers to forward (User-Agent etc.) |
| `error` | `str \| None` | Human-readable error if state is `FAILED` or `TIMED_OUT` |
| `timeout` | `int` | Session timeout in seconds (from settings) |

**Not persisted** — lives only for the duration of the Worker task.

#### InterceptState transitions

```
IDLE ──► LOADING ──► WAITING ──► CAPTURED ──► (hand off to download pipeline)
                  │           │
                  ▼           ▼
               TIMED_OUT   CANCELLED
                  │
                  ▼
               FAILED
```

| State | Meaning |
|-------|---------|
| `IDLE` | Session created, not started |
| `LOADING` | `page.goto()` in progress |
| `WAITING` | Page loaded; polling for `.m3u8` requests |
| `CAPTURED` | At least one `.m3u8` URL intercepted; selecting best variant |
| `TIMED_OUT` | Timeout elapsed with no `.m3u8` captured |
| `CANCELLED` | User cancelled during browser session |
| `FAILED` | Browser launch or navigation error |

---

### 2. UserSettings (extended)

Add one field to the existing `UserSettings` dataclass:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `intercept_timeout` | `int` | `30` | Seconds before browser intercept session gives up |

Schema version bumped from `2` → `3` for migration.

---

### 3. HistoryItem (extended)

Add one field to the existing `HistoryItem` dataclass:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `source` | `str` | `"direct"` | `"direct"` or `"browser_intercept"` |

**Backward-compatible**: `from_dict` falls back to `"direct"` when field absent.

---

### 4. InterceptResult (return value from `intercept_m3u8`)

Not a stored entity — defines the function's return shape.

```python
@dataclass
class InterceptResult:
    success: bool
    m3u8_url: str | None        # best-quality variant URL
    cookies: list[dict]         # playwright cookie dicts
    headers: dict[str, str]     # headers to forward
    error_code: str | None      # "timed_out" | "cancelled" | "launch_failed" | "no_stream"
    error_message: str | None   # human-readable
```

---

## Validation Rules

- `intercept_timeout` MUST be in range `[10, 300]` seconds; values outside this range are clamped on save.
- `selected_url` MUST start with `http://` or `https://` before being passed to download pipeline.
- Cookie temp file MUST be deleted after download completes (success or failure).

## No Schema Changes Required

No database or JSON schema changes beyond the two `UserSettings` and `HistoryItem` field additions. Existing history files remain readable.
