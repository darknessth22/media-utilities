"""Live integration tests for browser intercept.

Run with: LIVE_TEST=1 pytest tests/integration/test_intercept_live.py -v
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("LIVE_TEST") != "1",
    reason="Set LIVE_TEST=1 to run live browser intercept tests",
)

playwright = pytest.importorskip("playwright", reason="playwright not installed")


def test_intercept_m3u8_live_reachable_site():
    """Smoke test: intercept_m3u8 against a known HLS test stream."""
    from core.interceptor import intercept_m3u8

    result = intercept_m3u8(
        url="https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
        timeout=30,
        cancel_check=None,
        status_cb=None,
    )
    assert result.success, f"Expected success, got error: {result.error_code} — {result.error_message}"
    assert result.m3u8_url, "Expected non-empty m3u8_url"


def test_intercept_m3u8_live_no_stream():
    """Intercept against a page with no HLS stream returns no_stream error."""
    from core.interceptor import intercept_m3u8

    result = intercept_m3u8(
        url="https://example.com",
        timeout=10,
        cancel_check=None,
        status_cb=None,
    )
    assert not result.success
    assert result.error_code in ("no_stream", "nav_error")
