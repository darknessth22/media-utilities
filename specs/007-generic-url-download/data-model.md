# Data Model: Generic URL Download (007)

**Phase**: 1 — Design  
**Date**: 2026-04-17

---

## Entities

This feature introduces no new persistent data structures. It extends existing behavior in two existing domains.

---

### Extended: DownloadResult (dict, core/downloader.py)

Currently returned by `download_media()`. Extended with new field:

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | Download succeeded |
| `file_path` | `str \| None` | Absolute path to downloaded file |
| `file_size` | `int \| None` | File size in bytes |
| `error_code` *(new)* | `str \| None` | Machine-readable error code for UI |
| `warning` *(new)* | `str \| None` | Non-fatal warning (e.g. playlist detected) |

**Error codes** (for `error_code` field):

| Code | Meaning |
|------|---------|
| `"timeout"` | Network timed out (30 s exceeded) |
| `"no_video"` | URL has no extractable video |
| `"unsupported"` | Site not supported by yt-dlp |
| `"auth_required"` | Login/authentication required |
| `"http_fallback_ok"` | yt-dlp failed; HTTP fallback succeeded |
| `"download_failed"` | Generic failure (no specific cause identified) |

---

### Existing: HistoryItem (core/history/models.py)

No changes. Generic URL downloads produce identical `HistoryItem` entries as social media downloads: `task_type="download"`, `file_name`, `file_path`, `status`.

---

## State Transitions: Generic URL Download Attempt

```
URL entered
    │
    ▼
[Platform detection] ──► label = "Generic URL — download will be attempted"
    │
    ▼
[User clicks Download]
    │
    ├─► [yt-dlp extract_info download=False, socket_timeout=30]
    │       │
    │       ├─ _type == "playlist" ──► warn user, set playlist_items="1"
    │       └─ normal ──► proceed
    │
    ├─► [yt-dlp download]
    │       │
    │       ├─ success ──► return DownloadResult(success=True)
    │       │
    │       └─ DownloadError
    │               │
    │               ├─ "timed out" ──► error_code="timeout"
    │               ├─ "login required" / 401/403 ──► error_code="auth_required"
    │               ├─ "Unsupported URL" / "Unable to extract" ──► error_code="unsupported"
    │               └─ other ──► error_code="no_video"
    │                       │
    │                       └─ URL is direct video file?
    │                               │
    │                               ├─ YES ──► HTTP fallback download via urllib
    │                               │           ├─ success ──► error_code="http_fallback_ok"
    │                               │           └─ fail ──► error_code="download_failed"
    │                               └─ NO ──► error_code="no_video"
    │
    ▼
[HistoryItem recorded]
[UI shows specific error message or success]
```

---

## Validation Rules

- **URL validation**: No pre-validation of URL format beyond "non-empty string". yt-dlp handles malformed URLs gracefully.
- **Direct video file detection**: URL path segment (before `?`) ends with: `.mp4`, `.mkv`, `.webm`, `.avi`, `.mov`, `.flv`, `.m4v`, `.ts`
- **Timeout scope**: 30-second `socket_timeout` applied ONLY when `platform == "generic"`. Social media platforms are unaffected.
- **Playlist scope**: `playlist_items: "1"` applied ONLY when `platform == "generic"` AND playlist detected in pre-flight call.
