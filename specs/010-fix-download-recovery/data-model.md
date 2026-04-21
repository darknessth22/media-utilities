# Data Model: Download State Recovery

**Branch**: `010-fix-download-recovery` | **Date**: 2026-04-21

No new persistent entities. This feature adds two ephemeral state fields to `DownloadSection`.

---

## `DownloadSection` — new instance fields

| Field | Type | Default | Lifecycle | Purpose |
|-------|------|---------|-----------|---------|
| `_download_token` | `int` | `0` | Incremented on each `start` and each `cancel` | Stale-signal discriminator — each signal handler checks its captured token against this value before acting |
| `_active_output_dir` | `str \| None` | `None` | Set at download start; cleared in `_reset_ui()` | Used by `_cleanup_partial_files()` to scan for yt-dlp `.part` files on cancel |

---

## State machine: `DownloadSection`

```
        ┌──────────────────┐
        │     IDLE         │  _download_token = N
        │  button="Download"│  _worker = None
        └────────┬─────────┘
                 │ user clicks Download (valid URL)
                 ▼
        ┌──────────────────┐
        │    DOWNLOADING   │  _download_token = N+1
        │  button="Cancel" │  _worker = Worker(...)
        └──┬───────────┬───┘
           │           │
    cancel │           │ result / error
           ▼           ▼
     ┌──────────┐  ┌──────────┐
     │ CANCELLING│  │FINISHING │  (background thread still running)
     │(instant) │  │          │
     └────┬─────┘  └────┬─────┘
          │              │
          │ _reset_ui()  │ _reset_ui() (if token matches)
          │ token += 1   │
          │ worker = None│
          ▼              ▼
        ┌──────────────────┐
        │     IDLE         │  ready for next download
        └──────────────────┘
```

**Key invariant**: `_download_token` only ever increases. Any signal carrying a token value less than the current `_download_token` is from a superseded download and is silently discarded.

---

## No changes to persistent storage

- Download history JSON schema: unchanged
- `UserSettings`: unchanged
- No new config keys
