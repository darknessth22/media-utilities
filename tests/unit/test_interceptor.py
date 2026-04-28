"""Unit tests for core.interceptor — HLS stream intercept logic."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.interceptor import InterceptResult, intercept_m3u8


def _make_pw_mock(captured_urls: list[str] | None = None, goto_raises: Exception | None = None):
    """Return a mock for sync_playwright (the callable).

    intercept_m3u8 calls: pw = sync_playwright().__enter__()
    So: sync_playwright_mock() -> cm; cm.__enter__() -> pw_instance
    """
    page = MagicMock()
    if goto_raises:
        page.goto.side_effect = goto_raises
    else:
        page.goto.return_value = None

    request_handlers: list = []

    def on_request(event, handler):
        if event == "request":
            request_handlers.append(handler)

    page.on.side_effect = on_request

    def wait_for_timeout(ms):
        for url in (captured_urls or []):
            req = MagicMock()
            req.url = url
            for h in request_handlers:
                h(req)

    page.wait_for_timeout.side_effect = wait_for_timeout

    ctx = MagicMock()
    ctx.new_page.return_value = page
    ctx.cookies.return_value = []

    browser = MagicMock()
    browser.new_context.return_value = ctx

    pw_instance = MagicMock()
    pw_instance.chromium = MagicMock()
    pw_instance.chromium.launch.return_value = browser

    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=pw_instance)
    cm.__exit__ = MagicMock(return_value=False)

    sync_playwright_callable = MagicMock(return_value=cm)
    return sync_playwright_callable


# ---------------------------------------------------------------------------
# T018 — launch_failed (Playwright not installed)
# ---------------------------------------------------------------------------

def test_launch_failed_when_playwright_not_installed():
    with patch("utils.deps.check_playwright_installed", return_value=(False, "run: pip install playwright")):
        result = intercept_m3u8("http://example.com/video")

    assert isinstance(result, InterceptResult)
    assert result.success is False
    assert result.error_code == "launch_failed"
    assert "playwright" in result.error_message.lower()


def test_launch_failed_when_playwright_import_error():
    with patch("utils.deps.check_playwright_installed", return_value=(True, "")):
        with patch.dict("sys.modules", {"playwright": None, "playwright.sync_api": None}):
            result = intercept_m3u8("http://example.com/video")

    assert result.success is False
    assert result.error_code == "launch_failed"


# ---------------------------------------------------------------------------
# T019 — no_stream (poll loop ends, no URLs captured)
# ---------------------------------------------------------------------------

def test_no_stream_when_no_m3u8_detected():
    pw_mock = _make_pw_mock(captured_urls=[])

    with patch("utils.deps.check_playwright_installed", return_value=(True, "")):
        with patch("playwright.sync_api.sync_playwright", return_value=pw_mock):
            result = intercept_m3u8("http://example.com/video", timeout=1)

    assert result.success is False
    assert result.error_code == "no_stream"


# ---------------------------------------------------------------------------
# T020 — nav_error (page.goto raises)
# ---------------------------------------------------------------------------

def test_nav_error_on_goto_exception():
    pw_mock = _make_pw_mock(goto_raises=Exception("net::ERR_NAME_NOT_RESOLVED"))

    with patch("utils.deps.check_playwright_installed", return_value=(True, "")):
        with patch("playwright.sync_api.sync_playwright", pw_mock):
            result = intercept_m3u8("http://nonexistent.invalid/video")

    assert result.success is False
    assert result.error_code == "nav_error"
    assert "ERR_NAME_NOT_RESOLVED" in result.error_message


# ---------------------------------------------------------------------------
# T021 — cancelled (cancel_check returns True)
# ---------------------------------------------------------------------------

def test_cancelled_when_cancel_check_returns_true():
    pw_mock = _make_pw_mock(captured_urls=[])

    with patch("utils.deps.check_playwright_installed", return_value=(True, "")):
        with patch("playwright.sync_api.sync_playwright", return_value=pw_mock):
            result = intercept_m3u8(
                "http://example.com/video",
                timeout=60,
                cancel_check=lambda: True,
            )

    assert result.success is False
    assert result.error_code == "cancelled"


# ---------------------------------------------------------------------------
# T022 — browser context always closed in finally
# ---------------------------------------------------------------------------

def _get_browser_ctx(pw_callable_mock):
    """Extract browser/ctx from the mock chain."""
    pw_instance = pw_callable_mock.return_value.__enter__.return_value
    browser = pw_instance.chromium.launch.return_value
    ctx = browser.new_context.return_value
    return browser, ctx


def test_browser_closed_on_success():
    pw_mock = _make_pw_mock(captured_urls=["http://cdn.example.com/stream.m3u8"])

    with patch("utils.deps.check_playwright_installed", return_value=(True, "")):
        with patch("playwright.sync_api.sync_playwright", pw_mock):
            with patch("core.interceptor._select_best_variant", return_value="http://cdn.example.com/stream.m3u8"):
                intercept_m3u8("http://example.com/video", timeout=5)

    browser, ctx = _get_browser_ctx(pw_mock)
    ctx.close.assert_called_once()
    browser.close.assert_called_once()


def test_browser_closed_on_nav_error():
    pw_mock = _make_pw_mock(goto_raises=Exception("timeout"))

    with patch("utils.deps.check_playwright_installed", return_value=(True, "")):
        with patch("playwright.sync_api.sync_playwright", pw_mock):
            intercept_m3u8("http://example.com/video")

    browser, ctx = _get_browser_ctx(pw_mock)
    ctx.close.assert_called_once()
    browser.close.assert_called_once()


def test_browser_closed_on_no_stream():
    pw_mock = _make_pw_mock(captured_urls=[])

    with patch("utils.deps.check_playwright_installed", return_value=(True, "")):
        with patch("playwright.sync_api.sync_playwright", pw_mock):
            intercept_m3u8("http://example.com/video", timeout=1)

    browser, ctx = _get_browser_ctx(pw_mock)
    ctx.close.assert_called_once()
    browser.close.assert_called_once()


# ---------------------------------------------------------------------------
# T032 — status_cb call sequence and cancel path
# ---------------------------------------------------------------------------

def test_status_cb_sequence_on_success():
    pw_mock = _make_pw_mock(captured_urls=["http://cdn.example.com/stream.m3u8"])
    emitted: list[str] = []

    with patch("utils.deps.check_playwright_installed", return_value=(True, "")):
        with patch("playwright.sync_api.sync_playwright", pw_mock):
            with patch("core.interceptor._select_best_variant", return_value="http://cdn.example.com/stream.m3u8"):
                result = intercept_m3u8(
                    "http://example.com/video",
                    timeout=5,
                    status_cb=emitted.append,
                )

    assert result.success is True
    assert emitted[0] == "Loading page\u2026"
    assert emitted[1] == "Waiting for stream URL\u2026"
    assert emitted[2] == "Stream URL captured. Resolving quality\u2026"
    assert emitted[3] == "Ready to download."


def test_status_cb_not_called_on_nav_error():
    pw_mock = _make_pw_mock(goto_raises=Exception("timeout"))
    emitted: list[str] = []

    with patch("utils.deps.check_playwright_installed", return_value=(True, "")):
        with patch("playwright.sync_api.sync_playwright", pw_mock):
            result = intercept_m3u8(
                "http://example.com/video",
                status_cb=emitted.append,
            )

    assert result.error_code == "nav_error"
    # Only "Loading page…" should have been emitted before goto failed
    assert emitted == ["Loading page\u2026"]


def test_cancel_exits_poll_loop():
    """cancel_check returning True breaks the poll loop immediately."""
    pw_mock = _make_pw_mock(captured_urls=[])
    call_count = 0

    def cancel_after_one():
        nonlocal call_count
        call_count += 1
        return call_count >= 1

    with patch("utils.deps.check_playwright_installed", return_value=(True, "")):
        with patch("playwright.sync_api.sync_playwright", return_value=pw_mock):
            result = intercept_m3u8(
                "http://example.com/video",
                timeout=60,
                cancel_check=cancel_after_one,
            )

    assert result.error_code == "cancelled"
    assert call_count >= 1
