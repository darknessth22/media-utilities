# Research: Download Preview & Rich Progress

## 1. yt-dlp Progress Hook Data

**Decision**: Use the existing `progress_hooks` mechanism — pass a hook that reads `d['status']`, `d['downloaded_bytes']`, `d['total_bytes']` / `d['total_bytes_estimate']`, `d['speed']`, and `d['eta']`.

**Rationale**: yt-dlp emits these fields on every `'downloading'` status call. They are stable API surface since yt-dlp 2021.x. No custom computation needed.

**Key fields**:
```python
d['status']             # 'downloading' | 'finished' | 'error'
d['downloaded_bytes']   # int, bytes received so far
d['total_bytes']        # int | None, total size (known)
d['total_bytes_estimate']  # float | None, estimated total
d['speed']              # float | None, bytes/s
d['eta']                # int | None, estimated seconds remaining
d['_percent_str']       # str, e.g. ' 45.2%' (formatted by yt-dlp)
```

**Percentage derivation**:
- If `total_bytes` or `total_bytes_estimate` is set: `pct = downloaded / total * 100`
- Else: `pct = None` → indeterminate bar

**Alternatives considered**: Computing speed/ETA independently in the GUI layer — rejected because yt-dlp already has this data; computing it again would diverge for adaptive streams.

---

## 2. Worker.signals.progress Signal

**Decision**: Reuse the existing `Worker.signals.progress = Signal(int, int, str)` with convention `(percent_or_-1, eta_seconds_or_-1, speed_str)`.

**Rationale**: The signal is already declared in `gui/worker.py:11`. Using `-1` as sentinel for "unknown" avoids adding a new signal or changing the signature.

**Convention**:
```python
# percent: 0–100 or -1 (indeterminate)
# eta:     seconds remaining ≥ 0, or -1 (unknown)
# speed:   human string e.g. "3.2 MB/s" or "" (unknown)
worker.signals.progress.emit(percent, eta, speed_str)
```

**Alternatives considered**: Adding a new `download_progress` signal with a dataclass — rejected as over-engineering; the existing 3-tuple covers all required display data.

---

## 3. HTTP Fallback Progress (urllib)

**Decision**: Add chunked read loop with elapsed-time speed computation and `Content-Length`-derived ETA.

**Rationale**: FR-011 explicitly requires the urllib path to emit progress. The current loop (downloader.py:97-106) reads in 8 KB chunks but doesn't track bytes or time.

**Implementation pattern**:
```python
import time
content_length = int(resp.headers.get('Content-Length', 0)) or None
downloaded = 0
start_time = time.monotonic()
while True:
    chunk = resp.read(_HTTP_CHUNK)
    if not chunk:
        break
    out_f.write(chunk)
    downloaded += len(chunk)
    elapsed = time.monotonic() - start_time
    speed = downloaded / elapsed if elapsed > 0 else 0
    if content_length:
        pct = int(downloaded / content_length * 100)
        eta = int((content_length - downloaded) / speed) if speed > 0 else -1
    else:
        pct = -1
        eta = -1
    if progress_cb:
        progress_cb(pct, eta, _fmt_speed(speed))
```

**Alternatives considered**: Delegating HTTP fallback progress to a separate thread timer — rejected; simpler to compute inline per chunk.

---

## 4. Video Preview Streaming

**Decision**: Call `yt_dlp.YoutubeDL({'quiet': True, 'format': 'best[height<=720]'}).extract_info(url, download=False)` to get a direct stream URL, then pass it to `QMediaPlayer.setSource(QUrl(stream_url))`.

**Rationale**: Confirmed in spec clarifications. No temp file, no new dependencies. `format: 'best[height<=720]'` limits preview resolution to avoid buffering a 4K stream.

**Stream URL extraction**:
```python
with YoutubeDL({'quiet': True, 'format': 'best[height<=720]'}) as ydl:
    info = ydl.extract_info(url, download=False)
# prefer formats with direct HTTP URL
url_map = info.get('url') or (info.get('formats') or [{}])[-1].get('url')
```

**Live stream detection**: `info.get('is_live')` or duration is None → disable preview, show message.

**Expiry**: Stream URLs from yt-dlp typically expire in 6 hours. If playback fails after a gap, fall back silently to full URL download (already the default).

**Alternatives considered**: Downloading to a temp file first — rejected (spec explicitly says no temp file). Using a local HTTP proxy — rejected (new dependency, overkill).

---

## 5. Preview Player in Download Tab Layout

**Decision**: Add a collapsible `QFrame` (zero `maximumHeight` when hidden, 300 px when shown) between the trim card and output card. "Load Preview" button lives in the trim card header row.

**Rationale**: Matches FR-006: "positioned between the options area and the progress bar; hidden (zero height) when no preview is loaded." The trim card is the closest equivalent to "options area."

**Widget reuse from trim tab**: `QVideoWidget`, `QMediaPlayer`, `QAudioOutput`, `QSlider` scrubber, play/pause button, time label — all constructed identically. No shared base class needed (YAGNI).

**Alternatives considered**: Separate "Preview" card — rejected, clutters layout when preview not in use. Subclassing TrimSection — rejected (the trim tab operates on local files; coupling the two tabs would violate Principle I).

---

## 6. Start/End Marker Sync

**Decision**: Two `QSlider` widgets (start marker, end marker) on the same timeline, each clamped so `start_slider.value() < end_slider.value()`. On move, update the corresponding `QLineEdit` in the trim card.

**Rationale**: FR-007 requires reusing the trim tab's `QSlider`-based component. The trim tab uses a single scrubber; the download preview needs two (start + end). Pattern is identical — `sliderMoved` → `setText` on the input.

**Sync direction**: Input field change → parse → set slider value. Slider move → format ms → set input text. Circular update guarded by a `_updating` boolean flag.

**Alternatives considered**: A custom dual-handle `QSlider` widget — useful but a new abstraction; rejected per YAGNI. Using only text inputs without sliders for now — rejected (spec requires visual markers).
