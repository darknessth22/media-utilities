# Contract: Changes to core/downloader.py

## New fallback in `_download_generic_media`

Add `try_playwright_intercept` as the final fallback in the existing chain.

### Call site (after `try_html_scrape`)

```python
def try_playwright_intercept(classified: str) -> dict | None:
    if classified in ("auth_required", "timeout"):
        return None
    from core.interceptor import intercept_m3u8
    result = intercept_m3u8(
        url=url,
        timeout=_get_intercept_timeout(),   # reads from settings, default 30
        cancel_check=cancel_check,
        status_cb=status_cb,                # new optional param on _download_generic_media
    )
    if not result.success:
        return {
            "success": False,
            "file_path": None,
            "file_size": None,
            "error_code": result.error_code or "no_video",
            "warning": result.error_message,
        }
    # Download the resolved m3u8 URL with cookies
    import os, tempfile
    from core.interceptor import _write_netscape_cookies
    cookie_file = _write_netscape_cookies(result.cookies)
    try:
        dl_opts = {
            **ydl_opts,
            "cookiefile": cookie_file,
            "http_headers": result.headers,
        }
        with YoutubeDL(dl_opts) as ydl:
            info = ydl.extract_info(result.m3u8_url, download=True)
            downloaded_file = ydl.prepare_filename(info)
        final_size = _finalize_downloaded_file(downloaded_file, media_type, video_codec, force_codec)
        return {
            "success": True,
            "file_path": downloaded_file,
            "file_size": final_size,
            "error_code": "browser_intercept_ok",
            "warning": warning,
        }
    except Exception as e:
        return {
            "success": False,
            "file_path": None,
            "file_size": None,
            "error_code": "download_failed",
            "warning": str(e),
        }
    finally:
        try:
            os.remove(cookie_file)
        except OSError:
            pass
```

### Signature change for `_download_generic_media`

Add optional `status_cb: Callable[[str], None] | None = None` parameter. Propagate to `intercept_m3u8`.

### Signature change for `download_media`

Add optional `status_cb: Callable[[str], None] | None = None` parameter. Pass through to `_download_generic_media`.

---

## `_get_intercept_timeout` helper

```python
def _get_intercept_timeout() -> int:
    """Read intercept_timeout from settings; fallback to 30."""
    try:
        from core.settings import SettingsManager
        return SettingsManager.load().intercept_timeout
    except Exception:
        return 30
```

---

## Return dict — new error codes

| `error_code` | Meaning |
|-------------|---------|
| `"browser_intercept_ok"` | Success via Playwright path |
| `"no_stream"` | Browser session found no `.m3u8` |
| `"cancelled"` | User cancelled during browser session |
| `"launch_failed"` | Playwright/Chromium not available |
