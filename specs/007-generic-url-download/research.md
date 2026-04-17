# Research: Generic URL Download (007)

**Phase**: 0 — Pre-design  
**Date**: 2026-04-17

---

## Finding 1 — yt-dlp Error Classification

**Decision**: Catch `yt_dlp.utils.DownloadError` and inspect `str(e)` for known substrings to classify failure cause.

**Rationale**: yt-dlp wraps all download/extraction failures in `DownloadError`. The exception message carries the cause detail. Key patterns:
- **Timeout**: `"timed out"`, `"Read timed out"`, `"Connection timed out"`
- **No video / unsupported site**: `"Unsupported URL"`, `"Unable to extract"`, `"No video formats found"`, `"This video is unavailable"`
- **Authentication required**: `"HTTP Error 403"`, `"HTTP Error 401"`, `"login required"`, `"This video is private"`
- **Generic failure**: anything else

**Alternatives considered**: Catching `ExtractorError` separately — rejected because `DownloadError` wraps it and message inspection achieves the same classification without needing to import additional yt-dlp internals.

---

## Finding 2 — yt-dlp Playlist Restriction

**Decision**: Use `playlist_items: "1"` in yt-dlp opts for generic URLs; detect playlist after `extract_info(..., download=False)` by checking `info.get("_type") == "playlist"` or presence of `info.get("entries")`.

**Rationale**: `playlist_items: "1"` reliably restricts download to the first entry on any URL type. `noplaylist: True` has known inconsistencies (ignored on some extractors). Pre-flight detection via a `download=False` call allows warning the user before download begins.

**Alternatives considered**: `noplaylist: True` — rejected due to known bugs. Skipping detection and downloading first item silently — rejected per FR-009 (user must be warned).

---

## Finding 3 — yt-dlp Socket Timeout

**Decision**: Set `socket_timeout: 30` in `YoutubeDL` options dict for generic URL downloads.

**Rationale**: `socket_timeout` is the correct API-level key (not a CLI flag). Default yt-dlp timeout is 20 s; 30 s matches the spec requirement. Social media downloads are unchanged (no `socket_timeout` override).

**Alternatives considered**: Applying timeout globally — rejected per FR-002 (must not alter social media behavior).

---

## Finding 4 — HTTP Fallback for Direct Video File URLs

**Decision**: Use `urllib.request.urlopen` with manual chunk streaming (8 KB chunks) for HTTP fallback. No new dependency required.

**Rationale**: `urllib` is Python stdlib — zero new dependencies, satisfying Constitution §V (prefer stdlib). `curl-cffi` is already in requirements.txt but is unnecessary for a simple file download. `requests` is not in requirements.txt; adding it violates Constitution §V when stdlib suffices.

Direct video file detection: check URL path (before query string) ends with a known video extension (`.mp4`, `.mkv`, `.webm`, `.avi`, `.mov`, `.flv`, `.m4v`, `.ts`).

Filename derivation (FR-012): `urllib.parse.urlparse(url).path` → `pathlib.PurePosixPath(...).name` → strip query string → use as output filename.

**Alternatives considered**: `requests` streaming — rejected (not in requirements.txt). `curl-cffi` streaming — rejected (overkill for a simple file download, less familiar API for this use case).

---

## Finding 5 — No New Dependencies Needed

All required capabilities are covered by:
- `yt-dlp` (already in requirements.txt): generic URL extraction, playlist handling, timeout
- `urllib` (Python stdlib): HTTP fallback download
- `pathlib` (Python stdlib): filename derivation

No additions to `requirements.txt` required.
