# Internal API Contracts: Generic URL Download (007)

*Desktop app — no REST endpoints. Contracts are Python function signatures.*

---

## `core/downloader.py`

### `download_media()` — Extended Signature (unchanged parameters)

```python
def download_media(
    url: str,
    platform: str,
    media_type: str = "video",
    quality: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    audio_format: str = "mp3",
    output_dir: str | None = None,
    video_codec: str = "libx264",
    force_codec: bool = False,
    cancel_check=None,
) -> dict:
    ...
```

**Return type extended**:

```python
# Before (existing):
{"success": bool, "file_path": str | None, "file_size": int | None}

# After (this feature):
{
    "success":    bool,
    "file_path":  str | None,
    "file_size":  int | None,
    "error_code": str | None,   # NEW — see data-model.md for valid values
    "warning":    str | None,   # NEW — e.g. "Playlist detected — downloading first video only."
}
```

**Invariants**:
- When `platform != "generic"`: `error_code` and `warning` are `None`. Behavior identical to current.
- When `platform == "generic"` and `success=True`: `error_code` is `None` or `"http_fallback_ok"`.
- When `platform == "generic"` and `success=False`: `error_code` is one of `"timeout"`, `"no_video"`, `"unsupported"`, `"auth_required"`, `"download_failed"`.

---

### `_http_fallback_download()` — New private function

```python
def _http_fallback_download(url: str, output_dir: str | None, cancel_check=None) -> dict:
    """
    Download a direct video file URL via urllib when yt-dlp fails.
    
    cancel_check: optional callable; called between each 8 KB chunk.
        If it returns a truthy value, streaming stops and the function
        returns {"success": False, "error_code": "download_failed", ...}.
    
    Returns same dict shape as download_media():
    {
        "success": bool,
        "file_path": str | None,
        "file_size": int | None,
        "error_code": "http_fallback_ok" | "download_failed",
        "warning": None,
    }
    
    Filename derived from URL path last segment before query string.
    Streams in 8 KB chunks to avoid memory issues with large files.
    """
```

---

### `_is_direct_video_url()` — New private helper

```python
def _is_direct_video_url(url: str) -> bool:
    """
    Return True if the URL path (ignoring query string) ends with a
    known video file extension: .mp4 .mkv .webm .avi .mov .flv .m4v .ts
    """
```

---

### `_classify_yt_dlp_error()` — New private helper

```python
def _classify_yt_dlp_error(error_message: str) -> str:
    """
    Classify a yt-dlp DownloadError message into an error_code string.
    
    Returns one of:
        "timeout"        — "timed out", "Read timed out", "Connection timed out"
        "auth_required"  — "login required", "HTTP Error 401", "HTTP Error 403",
                           "private", "members only"
        "unsupported"    — "Unsupported URL", "Unable to extract"
        "no_video"       — all other cases
    """
```

---

## `gui/tabs/download_section.py`

### `_on_url_changed()` — Updated behavior

When `platform == "generic"`, label text changes from:
```
"Detected: Generic URL"
```
to:
```
"Detected: Generic URL — download will be attempted"
```

All other platforms: label text unchanged.

---

### `_on_result()` — Updated behavior

```python
def _on_result(self, result: dict) -> None:
    # 1. If result["warning"] is present, show as non-error status BEFORE main outcome.
    # 2. On success (result["success"] is True):
    #    - If result["error_code"] == "http_fallback_ok": show informational note
    #      "Downloaded via direct URL (yt-dlp unavailable for this link)." alongside
    #      the normal success message.
    #    - Otherwise: existing success path unchanged.
    # 3. On failure (result["success"] is False):
    #    Use result["error_code"] to select specific user-facing message from table below.
```

**Error code → UI message mapping**:

| `error_code` | Context | User-facing message |
|---|---|---|
| `"http_fallback_ok"` | success | `"Downloaded via direct URL (yt-dlp unavailable for this link)."` (informational note) |
| `"timeout"` | failure | `"Connection timed out. Check your network and try again."` |
| `"auth_required"` | failure | `"This video requires login — not supported for generic URLs."` |
| `"unsupported"` | failure | `"This site is not supported. Try a direct video file link instead."` |
| `"no_video"` | failure | `"No downloadable video found at this URL."` |
| `"download_failed"` | failure | `"Download failed. Check the URL or your network."` |
| `None` (social media) | failure | `"Download failed. Check the URL or network."` (existing message) |
