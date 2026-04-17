# Implementation Plan: Generic URL Video Download

**Branch**: `007-generic-url-download` | **Date**: 2026-04-17 | **Spec**: specs/007-generic-url-download/spec.md  
**Input**: Feature specification from `/specs/007-generic-url-download/spec.md`

## Summary

Expose yt-dlp's already-present generic URL support through proper UI indication, cause-specific error handling, playlist restriction (first item only), 30-second timeout enforcement, and an HTTP fallback for direct video file URLs when yt-dlp fails. Social media download paths are untouched.

## Technical Context

**Language/Version**: Python 3.12 (3.10+ compatible)  
**Primary Dependencies**: yt-dlp (existing), urllib (stdlib — for HTTP fallback), PySide6 (existing GUI)  
**Storage**: Download history JSON (existing — no schema changes)  
**Testing**: pytest + manual test plan (quickstart.md)  
**Target Platform**: Windows, macOS, Linux desktop  
**Project Type**: Desktop app  
**Performance Goals**: 30-second network timeout for generic URLs  
**Constraints**: No new PyPI dependencies; must not alter social media download behavior  
**Scale/Scope**: Single user, desktop app

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Modular Architecture | PASS | Changes in `core/downloader.py` (domain) + `gui/tabs/download_section.py` (UI only). No cross-layer leakage. |
| II. Cross-Platform Compatibility | PASS | `urllib` is stdlib and cross-platform. `pathlib.PurePosixPath` used for URL parsing (not OS paths). |
| III. User Experience First | PASS | Clear platform label, cause-specific errors, playlist warning, progress unchanged. |
| IV. Quality & Testing | PASS | Manual test plan in quickstart.md covers all 7 scenarios from spec. |
| V. Simplicity & YAGNI | PASS | No new abstractions. `urllib` replaces `requests` (stdlib over new dep). HTTP fallback only for direct file URLs (concrete requirement). |

**Post-design re-check**: All principles still pass. No new modules required — changes confined to two existing files plus one new private helper in `core/downloader.py`.

## Project Structure

### Documentation (this feature)

```text
specs/007-generic-url-download/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── internal-api.md  # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks — not yet created)
```

### Source Code Changes (repository root)

```text
core/
└── downloader.py      # MODIFY: add _classify_yt_dlp_error(), _is_direct_video_url(),
                       #   _http_fallback_download(); extend download_media() for generic platform

gui/tabs/
└── download_section.py  # MODIFY: _on_url_changed() label, _on_result() error_code handling
```

No new files in `core/` or `gui/` — changes extend existing modules, consistent with Constitution §I.

## Implementation Approach

### Change 1 — `core/downloader.py`

Three new private helpers + modifications to `download_media()`.

**`_classify_yt_dlp_error(msg: str) -> str`**  
Inspect yt-dlp error message string. Map to one of: `"timeout"`, `"auth_required"`, `"unsupported"`, `"no_video"`.

**`_is_direct_video_url(url: str) -> bool`**  
Parse URL path with `urllib.parse.urlparse`. Check lowercase path extension against known video extensions.

**`_http_fallback_download(url: str, output_dir: str | None) -> dict`**  
`urllib.request.urlopen` with 30-second timeout. Stream 8 KB chunks to disk. Filename from URL path last segment (before `?`). Returns same dict shape as `download_media()`.

**`download_media()` — generic platform branch**:
1. Before download: call `extract_info(download=False, socket_timeout=30)`.
2. If `info.get("_type") == "playlist"` or `info.get("entries")`: add `playlist_items: "1"` to opts; set `warning = "Playlist detected — downloading first video only."`.
3. Proceed with download (existing yt-dlp path, plus `socket_timeout: 30` in opts).
4. On `DownloadError`: classify → `error_code`. If `_is_direct_video_url(url)` and code is not `"auth_required"` or `"timeout"`: try `_http_fallback_download()`.
5. Return extended dict: `{"success", "file_path", "file_size", "error_code", "warning"}`.

**Social media platforms**: No changes. The new fields `error_code` and `warning` default to `None` for all non-generic platforms.

### Change 2 — `gui/tabs/download_section.py`

**`_on_url_changed()`**: When `platform == "generic"`, label text = `"Detected: Generic URL — download will be attempted"`. All other platforms unchanged.

**`_on_result()`**: Read `result.get("warning")` → emit as non-error status before main message. Read `result.get("error_code")` → select from message table in contracts/internal-api.md.

## Complexity Tracking

> No Constitution violations. Table not required.
