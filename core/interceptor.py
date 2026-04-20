"""Playwright-based HLS stream interceptor for JS-rendered sites."""
from __future__ import annotations

import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable
from urllib.parse import urljoin
from urllib.request import Request, urlopen

__all__ = ["InterceptState", "InterceptResult", "intercept_m3u8"]


class InterceptState(Enum):
    IDLE = "idle"
    LOADING = "loading"
    WAITING = "waiting"
    CAPTURED = "captured"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class InterceptResult:
    success: bool
    m3u8_url: str | None = None
    cookies: list[dict] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


def _cookies_header(cookies: list[dict]) -> str:
    """Convert playwright cookie list to 'name=value; ...' string."""
    return "; ".join(f"{c.get('name', '')}={c.get('value', '')}" for c in cookies if c.get("name"))


def _write_netscape_cookies(cookies: list[dict]) -> str:
    """Write playwright cookies to a temp Netscape-format file; return path."""
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


def _select_best_variant(master_url: str, cookies: list[dict]) -> str:
    """Fetch HLS master playlist; return highest-BANDWIDTH variant URI."""
    try:
        req = Request(master_url, headers={"Cookie": _cookies_header(cookies)})
        with urlopen(req, timeout=10) as r:
            text = r.read().decode()
    except Exception:
        return master_url

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
                best_uri = uri if uri.startswith("http") else urljoin(master_url, uri)
    return best_uri


def intercept_m3u8(
    url: str,
    timeout: int = 30,
    cancel_check: Callable[[], bool] | None = None,
    status_cb: Callable[[str], None] | None = None,
) -> InterceptResult:
    """Launch headless Chromium, intercept .m3u8 requests, resolve best variant."""
    from utils.deps import check_playwright_installed
    ok, hint = check_playwright_installed()
    if not ok:
        return InterceptResult(success=False, error_code="launch_failed", error_message=hint)

    # Lazy import — must NOT be at module level
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return InterceptResult(
            success=False,
            error_code="launch_failed",
            error_message="Playwright not installed. Run: pip install playwright && python -m playwright install chromium",
        )

    captured_urls: list[str] = []
    pw = None
    browser = None
    ctx = None

    try:
        pw = sync_playwright().__enter__()
        try:
            browser = pw.chromium.launch(headless=True)
        except Exception as e:
            return InterceptResult(success=False, error_code="launch_failed", error_message=str(e))

        ctx = browser.new_context()
        page = ctx.new_page()
        page.on("request", lambda req: captured_urls.append(req.url) if ".m3u8" in req.url else None)

        if status_cb:
            status_cb("Loading page\u2026")

        try:
            page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
        except Exception as e:
            return InterceptResult(success=False, error_code="nav_error", error_message=str(e))

        if status_cb:
            status_cb("Waiting for stream URL\u2026")

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cancel_check and cancel_check():
                return InterceptResult(success=False, error_code="cancelled", error_message="Cancelled by user")
            if captured_urls:
                break
            page.wait_for_timeout(500)

        if not captured_urls:
            return InterceptResult(success=False, error_code="no_stream", error_message="No .m3u8 stream detected within timeout")

        if status_cb:
            status_cb("Stream URL captured. Resolving quality\u2026")

        raw_url = captured_urls[0]
        cookies = ctx.cookies()
        best_url = _select_best_variant(raw_url, cookies)

        if status_cb:
            status_cb("Ready to download.")

        return InterceptResult(
            success=True,
            m3u8_url=best_url,
            cookies=cookies,
            headers={},
        )
    finally:
        try:
            if ctx:
                ctx.close()
            if browser:
                browser.close()
            if pw:
                pw.__exit__(None, None, None)
        except Exception:
            pass
