# Internal API Contracts: Download Preview & Rich Progress

This document specifies the function-level contracts for the two modules changed by this feature. These are internal interfaces — not REST endpoints.

---

## core/downloader.py

### `download_media` (modified signature)

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
    cancel_check: Callable[[], bool] | None = None,
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[int, int, str], None] | None = None,  # NEW
) -> dict:
    ...
```

**New parameter** — `progress_cb(percent: int, eta: int, speed_str: str) -> None`
- Called from `_progress_hook` on each `'downloading'` status event.
- `percent`: 0–100 or `-1` (indeterminate).
- `eta`: seconds remaining ≥ 0, or `-1` (unknown).
- `speed_str`: human-readable string `"3.2 MB/s"` / `"512 KB/s"` / `""`.
- Called on the worker thread — GUI must marshal via Qt signal.
- Propagated to `_download_generic_media` and the main yt-dlp call paths.

**Return value**: unchanged `{"success", "file_path", "file_size", "error_code", "warning"}`.

---

### `_progress_hook` (modified, internal)

```python
def _make_progress_hook(cancel_check, progress_cb) -> Callable[[dict], None]:
    def _hook(d: dict) -> None:
        if cancel_check and cancel_check():
            raise Exception("Download cancelled by user")
        if d.get('status') != 'downloading' or not progress_cb:
            return
        downloaded = d.get('downloaded_bytes') or 0
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        pct = int(downloaded / total * 100) if total else -1
        speed = d.get('speed') or 0
        eta = d.get('eta') if d.get('eta') is not None else -1
        speed_str = _fmt_speed(speed)
        progress_cb(pct, eta, speed_str)
    return _hook
```

**Replaces** the current inline `_progress_hook` closure — extracted so the same hook can be shared between the main download path and the generic path.

---

### `_fmt_speed(bps: float) -> str` (new helper, internal)

```python
def _fmt_speed(bps: float) -> str:
    if bps <= 0:
        return ""
    if bps >= 1_048_576:
        return f"{bps / 1_048_576:.1f} MB/s"
    return f"{bps / 1024:.0f} KB/s"
```

---

### `_http_fallback_download` (modified signature)

```python
def _http_fallback_download(
    url: str,
    output_dir: str | None,
    cancel_check=None,
    progress_cb: Callable[[int, int, str], None] | None = None,  # NEW
) -> dict:
    ...
```

- Reads `Content-Length` header to compute percentage and ETA.
- Calls `progress_cb` after each `_HTTP_CHUNK` write.
- Falls back gracefully when `Content-Length` is absent (`pct=-1`, `eta=-1`).

---

### `get_preview_stream_url(url: str) -> dict` (new function)

```python
def get_preview_stream_url(url: str) -> dict:
    """Extract a direct stream URL for in-app preview without downloading.

    Returns
    -------
    dict with keys:
        stream_url : str | None   — direct HTTP URL for QMediaPlayer
        duration_ms : int | None  — total duration in ms; None for live
        is_live : bool            — True if live stream (preview unsupported)
        title : str               — video title
        error : str | None        — human-readable error message, or None
    """
```

**Implementation**:
- Calls `YoutubeDL({'quiet': True, 'format': 'best[height<=720]'}).extract_info(url, download=False)`.
- Reads `info['is_live']` and `info.get('duration')` to detect live/audio-only.
- Picks stream URL from `info.get('url')` or last entry in `info.get('formats', [])`.
- On any exception: returns `{"stream_url": None, ..., "error": str(e)}`.

---

## gui/tabs/download_section.py

### `DownloadSection` — new public / private methods

#### `_build_preview_card() -> QFrame` (new)

Builds the collapsible preview player card (QVideoWidget + scrubber + play controls + start/end marker sliders). Returns a QFrame that is hidden by default (`setVisible(False)`).

#### `_load_preview(url: str) -> None` (new)

Triggered by "Load Preview" button. Starts a `Worker` that calls `get_preview_stream_url(url)`. On success, shows the preview card, sets `QMediaPlayer.setSource(QUrl(stream_url))`, and updates `_preview_duration_ms`.

#### `_on_preview_loaded(result: dict) -> None` (new)

Worker result handler for `_load_preview`. Hides preview and shows an error message if `result['error']` is set or `result['is_live']` is True.

#### `_on_start_slider_moved(value: int) -> None` (new)

Updates `_start_input.setText(_ms_to_str(value))`. Clamps end slider if needed.

#### `_on_end_slider_moved(value: int) -> None` (new)

Updates `_end_input.setText(_ms_to_str(value))`. Clamps start slider if needed.

#### `_on_url_changed` (modified)

Existing method — add: hide preview card, reset start/end sliders and inputs, stop any running preview worker.

#### `_set_busy` (modified)

Existing method — update `_progress_bar.setRange(0, 100)` when `percent != -1`, `setRange(0, 0)` for indeterminate. Show/hide `_speed_label` and `_eta_label`.

#### `_on_progress(percent: int, eta: int, speed_str: str) -> None` (new)

Connected to `worker.signals.progress`. Updates progress bar, speed label, ETA label.

---

## gui/worker.py — No Changes

`Worker.signals.progress = Signal(int, int, str)` is already declared at line 11. The download section connects to it; `download_media` calls `progress_cb` which emits it.
