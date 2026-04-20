# Contract: core/interceptor.py

## Public API

### `intercept_m3u8(url, timeout, cancel_check, status_cb) -> InterceptResult`

Launch a headless Chromium session, intercept `.m3u8` network requests, resolve the best-quality variant URL.

**Signature**
```python
def intercept_m3u8(
    url: str,
    timeout: int = 30,
    cancel_check: Callable[[], bool] | None = None,
    status_cb: Callable[[str], None] | None = None,
) -> InterceptResult:
```

**Parameters**
| Name | Type | Description |
|------|------|-------------|
| `url` | `str` | Target page URL to load |
| `timeout` | `int` | Seconds to wait for `.m3u8` before giving up |
| `cancel_check` | `() -> bool \| None` | Called every 500 ms; return `True` to abort |
| `status_cb` | `(str) -> None \| None` | Called with human-readable phase strings for UI display |

**Status strings emitted via `status_cb`**
- `"Loading page…"`
- `"Waiting for stream URL…"`
- `"Stream URL captured. Resolving quality…"`
- `"Ready to download."`

**Returns**: `InterceptResult` (see data-model.md)

**Error codes**
| Code | Condition |
|------|-----------|
| `"launch_failed"` | Playwright not installed or Chromium binary missing |
| `"no_stream"` | Timeout elapsed, no `.m3u8` intercepted |
| `"cancelled"` | `cancel_check()` returned `True` |
| `"nav_error"` | `page.goto()` raised (network error, DNS failure, etc.) |

---

### `_select_best_variant(master_url, cookies) -> str`

Internal. Fetch HLS master playlist, return URI of highest-BANDWIDTH `#EXT-X-STREAM-INF` entry. Returns `master_url` unchanged if playlist is not a master manifest.

### `_write_netscape_cookies(cookies) -> str`

Internal. Serialize playwright cookie list to a temp Netscape-format file. Caller must delete the file after use.

### `_cookies_header(cookies) -> str`

Internal. Convert cookie list to `name=value; name2=value2` string for `Cookie:` header.

---

## Invariants

- `intercept_m3u8` MUST close the browser context regardless of outcome (success, timeout, cancel, error).
- Cookie temp file created by `_write_netscape_cookies` is the CALLER's responsibility to delete.
- `intercept_m3u8` MUST NOT import `playwright` at module level — import inside function body so missing package is a runtime error, not an import error.
