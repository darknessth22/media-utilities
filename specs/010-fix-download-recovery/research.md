# Research: Download State Recovery

**Branch**: `010-fix-download-recovery` | **Date**: 2026-04-21

---

## Q1: Does yt-dlp clean up `.part` files when an exception is raised from a progress hook?

**Decision**: No — `.part` files must be deleted manually.  
**Rationale**: When `Exception("Download cancelled by user")` is raised inside a yt-dlp progress hook, yt-dlp propagates the exception out of `YoutubeDL.__exit__` but does **not** invoke its own cleanup path for in-progress `.part` files. The `--no-part` flag disables `.part` files entirely (writes directly to final name) but that makes recovery from crashes worse.  
**Alternatives considered**:  
- `--no-part` flag — rejected; increases risk of corrupt final files on non-cancel errors  
- yt-dlp `postprocessor` hook — fires after download, not on cancel  
- Manual scan for `<title>.part` in output dir — chosen; simple and reliable  

---

## Q2: What is the idiomatic Qt pattern for discarding stale worker signals?

**Decision**: Generation/token counter captured in closure.  
**Rationale**: Qt signals are queued across threads; a signal emitted before `self._worker = None` will still be delivered to the slot after the next download has started. The only safe approach is to capture a token at signal-connection time and check it in the slot. This is the same pattern used in Qt documentation for cancellable network requests.  
**Alternatives considered**:  
- `QObject.disconnect()` before clearing `_worker` — unreliable; signals already in the event queue are still delivered  
- Checking `self._worker is not None` in slots — race condition; worker may be None for new download too  
- Subclassing `QThread` with per-worker ID — more complex, same semantic as token counter  

---

## Q3: Is setting `self._worker = None` immediately on cancel safe?

**Decision**: Yes — safe when combined with token counter.  
**Rationale**: `self._worker = None` only clears the Python reference; the underlying `QThread` continues to run until its `run()` returns. Python's GC will not collect it while the thread is running (Qt holds an internal reference). The token counter ensures stale signals from the orphaned thread are discarded.  
**Alternatives considered**:  
- `self._worker.wait()` — blocks the UI thread; rejected per spec (FR-001 requires instant restore)  
- `self._worker.quit()` — only works for threads with an event loop; `QThread.run()` here runs a plain function, so `quit()` is a no-op  

---

## Q4: What happens when Cancel is clicked during the Playwright browser-intercept phase?

**Decision**: Already handled correctly; no change needed.  
**Rationale**: `intercept_m3u8` in `core/interceptor.py` polls `cancel_check()` during its wait loop and kills the Chromium process when it returns `True`. The result is discarded via the token counter in the UI layer.  
**Alternatives considered**: None — existing approach is correct.  

---

## Q5: Does the HTTP fallback clean up partial files on cancel?

**Decision**: Yes — `_http_fallback_download` already deletes the partial file (`os.remove(dest)`) when `cancel_check()` returns `True`.  
**Rationale**: Code audit confirmed cleanup block at lines 152–163 of `core/downloader.py`.  
**No change needed** in HTTP fallback path.  

---

## Q6: What error codes can `download_media` return, and are all covered by `_GENERIC_ERROR_MESSAGES`?

**Decision**: All codes covered. No new codes needed.  

| `error_code` value | Source | Covered in `_GENERIC_ERROR_MESSAGES` |
|--------------------|--------|--------------------------------------|
| `"timeout"` | `_classify_yt_dlp_error` | ✅ |
| `"auth_required"` | `_classify_yt_dlp_error` | ✅ |
| `"no_video"` | `_classify_yt_dlp_error` | ✅ |
| `"download_failed"` | various fallback paths | ✅ |
| `"unsupported"` | (legacy, may not occur) | ✅ |
| `"cancelled"` | playwright intercept | mapped to "Download cancelled." in `_on_result` (success=False path via `_GENERIC_ERROR_MESSAGES` fallback) — **gap**: add explicit mapping |

**Action**: Add `"cancelled"` key to `_GENERIC_ERROR_MESSAGES` → `"Download cancelled."`.
