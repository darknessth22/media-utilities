# Quickstart: Download Preview & Rich Progress

## What changes for a developer picking up this feature

### Files to modify

| File | What changes |
|------|-------------|
| `core/downloader.py` | Add `progress_cb` param to `download_media` + `_http_fallback_download`; extract `_make_progress_hook`; add `_fmt_speed`; add `get_preview_stream_url` |
| `gui/tabs/download_section.py` | Add preview player card; rich progress labels; connect `worker.signals.progress` |

### Files NOT changed

- `gui/worker.py` — `progress = Signal(int, int, str)` already there
- `core/history/` — no schema change
- `core/settings.py` — no new settings
- `gui/app.py` — no change

---

## Story 1 first (Rich Progress)

The two stories are independent. Implement Story 1 first:

1. In `core/downloader.py`:
   - Replace inline `_progress_hook` closure with `_make_progress_hook(cancel_check, progress_cb)`.
   - Add `_fmt_speed(bps)` helper.
   - Add `progress_cb` parameter to `download_media` and thread it through to `ydl_opts['progress_hooks']`.
   - Update `_http_fallback_download` to accept `progress_cb` and emit per-chunk progress.
   - Propagate `progress_cb` through `_download_generic_media`.

2. In `gui/tabs/download_section.py`:
   - Add `_speed_label` and `_eta_label` to `_build_progress_card()`.
   - Add `_on_progress(percent, eta, speed_str)` handler.
   - In `trigger_primary_action`, pass `lambda p, e, s: self._worker.signals.progress.emit(p, e, s)` as `progress_cb`.
   - Connect `self._worker.signals.progress.connect(self._on_progress)`.
   - In `_on_progress`: `setRange(0, 100)` + `setValue(percent)` when `percent != -1`; `setRange(0, 0)` for indeterminate.

**Test Story 1**: Start a YouTube download, verify bar fills, speed/ETA update every second.

---

## Story 2 (Preview Player)

After Story 1 passes:

1. In `core/downloader.py`: add `get_preview_stream_url(url)`.

2. In `gui/tabs/download_section.py`:
   - Add `_multimedia_available` guard (mirror trim tab pattern).
   - Add `_build_preview_card()` — QVideoWidget + play button + scrubber + start/end sliders.
   - Add "Load Preview" button to the trim card header.
   - Add `_load_preview(url)` — Worker → `get_preview_stream_url` → `_on_preview_loaded`.
   - Add `_on_start_slider_moved` / `_on_end_slider_moved` with sync to text inputs.
   - Modify `_on_url_changed` to hide/reset preview on URL change.

**Test Story 2**: YouTube URL → Load Preview → player shows → drag sliders → text inputs update → Download uses correct segment.

---

## Key patterns from trim tab to reuse

```python
# QMediaPlayer setup (trim_section.py:184-192)
self._video_widget = QVideoWidget()
self._audio_output = QAudioOutput()
self._player = QMediaPlayer()
self._player.setVideoOutput(self._video_widget)
self._player.setAudioOutput(self._audio_output)
self._player.durationChanged.connect(self._on_duration_changed)

# Position timer (trim_section.py:131-134)
self._pos_timer = QTimer(self)
self._pos_timer.setInterval(200)
self._pos_timer.timeout.connect(self._update_position)

# Set source for network URL (new — not in trim tab)
self._player.setSource(QUrl(stream_url))  # network URL, not local file
```

---

## Running the app

```bash
python main.py
```

No new dependencies to install.
