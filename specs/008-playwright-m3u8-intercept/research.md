# Research: Playwright HLS Stream Intercept

## 1. Playwright Python — Network Intercept Pattern

**Decision**: Use `page.on("request", handler)` (non-blocking listener) rather than `page.route()` (blocking interceptor).

**Rationale**: `page.route()` pauses the request until the handler calls `route.continue_()`. For HLS intercept we only need to observe, not modify — a passive listener avoids stalling the page load and reduces risk of breaking JS that depends on the response arriving quickly.

```python
from playwright.sync_api import sync_playwright

captured: list[str] = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context()
    page = ctx.new_page()
    page.on("request", lambda req: captured.append(req.url)
            if ".m3u8" in req.url else None)
    page.goto(url, timeout=timeout_ms, wait_until="networkidle")
    browser.close()
```

**Alternatives considered**:
- `page.route("**/*.m3u8")` — would pause each request; overkill and fragile for varied URL patterns.
- CDP `Fetch.enable` directly — lower-level, no cross-browser benefit here.

---

## 2. HLS Master Playlist — Highest-Quality Variant Selection

**Decision**: Fetch the captured `.m3u8` URL with `urllib`, parse `#EXT-X-STREAM-INF` tags manually (no extra library), pick the variant with the highest `BANDWIDTH` value.

**Rationale**: The `m3u8` PyPI library adds a dependency for a 15-line parse task. Standard-library `urllib` + regex is sufficient and aligns with Constitution §V (YAGNI).

```python
import re, urllib.request

def _select_best_variant(master_url: str, cookies: dict) -> str:
    """Return URL of highest-bandwidth variant from an HLS master playlist."""
    req = urllib.request.Request(master_url, headers={"Cookie": _cookies_header(cookies)})
    with urllib.request.urlopen(req, timeout=10) as r:
        text = r.read().decode()

    # Not a master playlist — return as-is
    if "#EXT-X-STREAM-INF" not in text:
        return master_url

    best_bw, best_uri = -1, master_url
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.search(r"BANDWIDTH=(\d+)", line)
        if m and i + 1 < len(lines):
            bw = int(m.group(1))
            if bw > best_bw:
                best_bw = bw
                uri = lines[i + 1].strip()
                best_uri = uri if uri.startswith("http") else _resolve_relative(master_url, uri)
    return best_uri
```

**Alternatives considered**:
- `m3u8` library — clean API but unnecessary dependency.
- Always using the raw captured URL — ignores quality selection requirement (FR-009).

---

## 3. Forwarding Browser Cookies to yt-dlp

**Decision**: Write cookies to a temp Netscape-format `cookies.txt` file and pass its path via `ydl_opts["cookiefile"]`.

**Rationale**: yt-dlp's `cookiefile` option is the official supported path for pre-existing cookies. In-memory alternatives (monkey-patching yt-dlp internals) are fragile across yt-dlp versions.

```python
import tempfile, os

def _write_netscape_cookies(cookies: list[dict]) -> str:
    """Write playwright cookie dicts to a temp Netscape cookies file; return path."""
    fd, path = tempfile.mkstemp(suffix=".txt", prefix="mu_cookies_")
    with os.fdopen(fd, "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for c in cookies:
            domain = c.get("domain", "")
            flag = "TRUE" if domain.startswith(".") else "FALSE"
            secure = "TRUE" if c.get("secure") else "FALSE"
            expires = int(c.get("expires", 0)) if c.get("expires") else 0
            name = c.get("name", "")
            value = c.get("value", "")
            path_val = c.get("path", "/")
            f.write(f"{domain}\t{flag}\t{path_val}\t{secure}\t{expires}\t{name}\t{value}\n")
    return path
```

**Alternatives considered**:
- `http_headers` dict with `Cookie` string — doesn't handle domain-scoped cookies correctly for multi-request downloads.
- Playwright `storage_state()` JSON — requires yt-dlp custom extractor code.

---

## 4. Playwright Dependency & Missing-Binary Handling

**Decision**: Detect Playwright at import time in `utils/deps.py`; surface a user-friendly error if the `playwright` package or Chromium binary is missing.

```python
def check_playwright_installed() -> tuple[bool, str]:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        # Probe binary existence without launching
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"],
            capture_output=True, text=True
        )
        if "chromium" in result.stdout.lower() and "already installed" not in result.stdout.lower():
            return False, "Playwright Chromium not installed. Run: python -m playwright install chromium"
        return True, ""
    except ImportError:
        return False, "Playwright not installed. Run: pip install playwright && python -m playwright install chromium"
```

**Note**: `--dry-run` flag may not exist on all Playwright versions. Safer probe: try launching a tiny browser context with `timeout=5000`. Research outcome: probe by attempting `sync_playwright().__enter__()` in a subprocess to avoid polluting the main process on failure.

**Alternatives considered**:
- Require Playwright at app startup — too heavy; most users never need browser intercept.
- Lazy import only when intercept triggered — chosen approach (import inside function, not at module level).

---

## 5. Cancellation During Browser Session

**Decision**: Poll `cancel_check()` inside a `threading.Event`-based wait loop; signal the browser to close via a shared flag.

**Rationale**: Playwright sync API blocks on `page.goto()` and has no built-in cooperative cancellation. Running intercept logic in the existing `Worker(QThread)`, with `cancel_check` polled every 500 ms in a timeout-counting loop alongside `page.wait_for_timeout(500)`.

```python
deadline = time.monotonic() + timeout
while time.monotonic() < deadline:
    if cancel_check and cancel_check():
        break
    if captured_urls:
        break
    page.wait_for_timeout(500)   # yields control briefly
```

**Alternatives considered**:
- Playwright async API with `asyncio.Task.cancel()` — would require an event loop incompatible with QThread.
- `threading.Thread` for browser + `thread.join(timeout)` — not cancellable from QThread worker cleanly.

---

## 6. Integration Point in `_download_generic_media`

**Decision**: Add a third fallback `try_playwright_intercept` after `try_html_scrape`, called only when `classified == "no_video"`.

```python
# After try_html_scrape...
playwright_result = try_playwright_intercept()
if playwright_result is not None:
    return playwright_result
```

This keeps the existing fallback chain intact (yt-dlp → HTTP direct → HTML scrape → Playwright) and only adds latency when the earlier strategies fail.

**Alternatives considered**:
- Call Playwright first before yt-dlp — contradicts FR-001 (yt-dlp first).
- Separate download entry point — adds API surface complexity.
