# Implementation Plan: Download State Recovery

**Branch**: `010-fix-download-recovery` | **Date**: 2026-04-21 | **Spec**: specs/010-fix-download-recovery/spec.md  
**Input**: Feature specification from `/specs/010-fix-download-recovery/spec.md`

## Summary

Fix two bugs that leave the Download tab in an unrecoverable state: (1) cancelling a download leaves `self._worker` set to a still-running thread so the next click triggers another cancel instead of a new download; (2) any download outcome (cancel or error) may fail to fully reset all UI controls. Fix via a **generation-counter / token** pattern — each new download mints a new token; stale worker signals carrying an old token are silently discarded; UI is reset immediately on cancel without waiting for the background thread to stop.

## Technical Context

**Language/Version**: Python 3.12 (3.10+ compatible)  
**Primary Dependencies**: PySide6 (QThread, Signal), yt-dlp, playwright  
**Storage**: N/A — no schema or file-format changes  
**Testing**: pytest + manual GUI test (10× cancel-retry cycle)  
**Target Platform**: Windows / macOS / Linux desktop  
**Project Type**: desktop-app  
**Performance Goals**: Download button restores within 1 s of cancel (SC-001); 100% reliability on retry (SC-002, SC-003)  
**Constraints**: Background thread cannot be forcefully terminated — cooperative cancel only; partial file cleanup must work for both yt-dlp (`.part` files) and HTTP fallback  
**Scale/Scope**: Single-file changes in `gui/tabs/download_section.py` and minor hardening in `core/downloader.py`

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Modular Architecture | ✅ PASS | UI state fix stays in `gui/`; core logic fix stays in `core/` |
| II. Cross-Platform Compatibility | ✅ PASS | `pathlib` / `os.path` used for file ops; no platform paths |
| III. User Experience First | ✅ PASS | Instant button restore is the entire goal of this fix |
| IV. Quality & Testing | ✅ PASS | Manual cancel-retry cycle test + unit test for token logic |
| V. Simplicity & YAGNI | ✅ PASS | Token counter is the minimal correct pattern; no new abstractions |

No violations — Complexity Tracking table omitted.

## Project Structure

### Documentation (this feature)

```text
specs/010-fix-download-recovery/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
└── tasks.md             ← Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (affected files only)

```text
gui/tabs/download_section.py   ← primary change (token counter, _reset_ui, stale-signal guards)
core/downloader.py             ← minor: partial-file path callback for cancel cleanup
```

No new files. No new modules. No schema changes.

---

## Phase 0 — Research

See `research.md` for full findings. Summary:

| Question | Finding |
|----------|---------|
| yt-dlp partial file cleanup on exception | yt-dlp does NOT clean up `.part` files when an exception is raised from a progress hook — must delete manually |
| Qt stale-signal pattern | Generation/token counter is the idiomatic Qt pattern; check token in slot before acting |
| Worker `isRunning()` race | Setting `self._worker = None` immediately on cancel (before thread stops) breaks the isRunning guard; token counter is the correct substitute |
| Playwright cancel during browser phase | `cancel_check` propagates to `intercept_m3u8` which kills the browser process; already correct |

---

## Phase 1 — Design

### Root cause (detailed)

**Bug A — Cancel → can't download again**

`trigger_primary_action` on cancel:
```python
self._worker.cancel()       # sets is_cancelled=True
self._set_busy(False)       # button → "Download" ✓
self.status_message.emit(…)
return                      # ← self._worker still set, thread still running
```

On next click: `self._worker.isRunning()` → `True` → triggers cancel-branch again → user cannot start download.

**Bug B — Worker never sets `self._worker = None` on cancel path**

`Worker.run()` checks `if not self.is_cancelled:` before emitting `result`/`error`, so `_on_result` / `_on_error` are never called → `self._worker` is never cleared → the broken-state persists until the OS recycles the thread object.

**Bug C — Progress/intercept-status signals from stale worker reach UI during new download**

If a new download starts while old thread winds down, old signals update the new download's progress UI with stale data.

### Fix design

**Token counter pattern** (`_download_token: int`):

```
__init__: self._download_token = 0

on cancel:
  self._worker.cancel()
  self._download_token += 1   ← invalidate all in-flight signals
  self._worker = None          ← allow new download immediately
  self._reset_ui()             ← single authoritative reset method
  delete partial file

on new download start:
  self._download_token += 1
  token = self._download_token  ← captured in closure
  ... connect signals ...

in _on_result(result):
  if token != self._download_token: return   ← discard stale
  self._reset_ui()
  ...

in _on_error(err):
  if token != self._download_token: return
  self._reset_ui()
  ...

in _on_progress(p, e, s):
  if token != self._download_token: return
  ...
```

**`_reset_ui()` — single authoritative reset**:
- `self._set_busy(False)` (hides progress bar, emits `busy_changed(False)`)
- `self._progress_label.setVisible(False)`
- `self._speed_label.setVisible(False)`
- `self._eta_label.setVisible(False)`
- `self._progress_bar.setRange(0, 0)`
- `self._progress_bar.setValue(0)`

**Partial file cleanup on cancel**:

Track `self._active_output_dir: str | None` (set from `out_dir` at download start). On cancel, scan for `.part` files (yt-dlp naming convention: `<filename>.part`) in that directory and delete them. HTTP fallback already deletes its partial file internally when `cancel_check()` returns True.

```python
def _cleanup_partial_files(self) -> None:
    out = self._active_output_dir or "."
    try:
        for f in os.scandir(out):
            if f.name.endswith(".part") and f.is_file():
                os.remove(f.path)
    except OSError:
        pass
```

**Double-cancel guard (FR-008)**:

After cancel, `self._worker = None`. Second cancel click: `self._worker` is `None` → skip cancel branch → hit URL-empty check or start new download normally. No double-emit.

### Data model

No new entities. Single new integer field in `DownloadSection`:

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `_download_token` | `int` | `0` | Incremented on each new download and on cancel; used to discard stale signals |
| `_active_output_dir` | `str \| None` | `None` | Output dir of current/last download; used for `.part` file cleanup on cancel |

See `data-model.md` for full schema.

### Error message mapping (FR-004)

Already implemented in `_GENERIC_ERROR_MESSAGES`. No changes needed — verified all `error_code` values from `downloader.py` are covered.

### Sequence diagram (cancel-and-retry)

```
User            UI Thread            Background Thread (old)   Background Thread (new)
  │                │                        │
  │──[Cancel]──→  │                        │
  │                │ worker.cancel()         │ (sets is_cancelled=True)
  │                │ token += 1 (token=2)   │
  │                │ worker = None           │
  │                │ _reset_ui()             │
  │                │ button="Download"       │ (still running, will finish later)
  │                │                        │
  │──[Download]──→ │                        │
  │                │ token += 1 (token=3)   │
  │                │ closure captures t=3   │                    │ (starts)
  │                │                        │                    │
  │                │ ←──[result(stale)]──── │ (token=2, t=3 → discard)
  │                │                        │                    │
  │                │ ←──────────────────────│────────[result]──→ │ (token=3=t → accept)
  │                │ _on_result()           │                    │
```

---

## Contracts

See `contracts/internal-api.md` for the updated `download_media` contract (no signature changes; `cancel_check` semantics clarified).

---

## quickstart.md

See `quickstart.md` for manual test steps.
