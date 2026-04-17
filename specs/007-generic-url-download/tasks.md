# Tasks: Generic URL Video Download

**Input**: Design documents from `/specs/007-generic-url-download/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/internal-api.md ✓, quickstart.md ✓

**Tests**: No test tasks — manual test plan in quickstart.md covers all 7 scenarios (tests not requested in spec).

**Organization**: Tasks grouped by user story. Only 2 files change: `core/downloader.py` and `gui/tabs/download_section.py`. No new files required.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files or independent sections)
- **[Story]**: User story label (US1, US2, US3)

---

## Phase 1: Setup

**Purpose**: Confirm working environment before any edits.

- [X] T001 Verify active branch is `007-generic-url-download` and working directory is clean
- [X] T002 Confirm `yt-dlp` present in `requirements.txt` (no new deps needed per research.md Finding 5)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Extend `download_media()` return dict to include `error_code` and `warning` on ALL existing return paths (non-generic platforms return `None` for both). Required before any user story so callers can safely access new keys.

**⚠️ CRITICAL**: Must complete before US1, US2, US3 work begins.

- [X] T003 Read `core/downloader.py`, enumerate every `return {…}` statement inside `download_media()`, and add `"error_code": None, "warning": None` to each so non-generic callers receive the new keys without breaking changes

**Checkpoint**: `download_media()` always returns `error_code` and `warning` keys — safe to build on.

---

## Phase 3: User Story 1 — Download Video From Any URL (Priority: P1) 🎯 MVP

**Goal**: User pastes any non-social-media URL and downloads the video the same way as social media content — same button, same output folder, correct error messages per failure cause, playlist restriction, timeout enforcement, and HTTP fallback for direct video files.

**Independent Test**: Paste a non-social-media video URL → click Download → file saved to output folder. Also: paste RFC-5737 unreachable IP URL → wait 35 s → see timeout message (quickstart Test 5).

### Implementation

- [X] T004 [P] [US1] Add `_classify_yt_dlp_error(msg: str) -> str` private helper in `core/downloader.py` — maps yt-dlp error substrings to `"timeout"` / `"auth_required"` / `"unsupported"` / `"no_video"` per contracts/internal-api.md and research.md Finding 1
- [X] T005 [P] [US1] Add `_is_direct_video_url(url: str) -> bool` private helper in `core/downloader.py` — uses `urllib.parse.urlparse` to check URL path extension against `.mp4 .mkv .webm .avi .mov .flv .m4v .ts` per research.md Finding 4
- [X] T006 [P] [US1] Add `_http_fallback_download(url: str, output_dir: str | None, cancel_check=None) -> dict` private helper in `core/downloader.py` — `urllib.request.urlopen` with 30 s timeout, 8 KB chunk streaming (call `cancel_check()` between each chunk and raise/return failure if truthy), filename from `PurePosixPath(urlparse(url).path).name`, returns same dict shape as `download_media()` with `error_code="http_fallback_ok"` on success or `"download_failed"` on failure per contracts/internal-api.md
- [X] T007 [US1] Add generic platform branch to `download_media()` in `core/downloader.py` (depends on T004, T005, T006): (1) pre-flight `extract_info(download=False, socket_timeout=30)`; (2) if playlist detected set `playlist_items="1"` and `warning="Playlist detected — downloading first video only."`; (3) download with `socket_timeout: 30` in opts; (4) on `DownloadError` call `_classify_yt_dlp_error()` → if direct video URL and code not `auth_required`/`timeout` try `_http_fallback_download()`; (5) return extended dict per data-model.md
- [X] T008 [US1] Update `_on_result()` in `gui/tabs/download_section.py`: (1) if `result.get("warning")` is present, display it as a non-error status message before the main outcome message; (2) on failure (`success=False`), use `result.get("error_code")` to select the user-facing error string from the failure mapping in contracts/internal-api.md; (3) on success with `error_code == "http_fallback_ok"`, display `"Downloaded via direct URL (yt-dlp unavailable for this link)."` as an informational note alongside the normal success message

- [ ] T008b [US1] Manually verify (via quickstart Tests 1 + 3) that a completed generic URL download and a failed generic URL download each produce a `HistoryItem` entry in `core/history/` with `task_type="download"` and correct `status` (`"success"` / `"error"`) — fix history recording in `core/downloader.py` if entries are missing (FR-007)

**Checkpoint**: US1 fully functional — generic URL downloads, error messages, timeout, playlist restriction, HTTP fallback, and history recording all work independently.

---

## Phase 4: User Story 2 — Platform Detection Communicates Generic Support (Priority: P2)

**Goal**: User sees a clear label confirming download will be attempted for any non-social-media URL. Social media labels unchanged.

**Independent Test**: Paste a generic URL → label reads `"Detected: Generic URL — download will be attempted"`. Paste a YouTube URL → label unchanged (quickstart Test 7).

### Implementation

- [X] T009 [US2] Update `_on_url_changed()` in `gui/tabs/download_section.py` — when `platform == "generic"` set label to `"Detected: Generic URL — download will be attempted"`; all other platforms unchanged per contracts/internal-api.md

**Checkpoint**: Label change visible immediately on URL paste. Social media label regression passes.

---

## Phase 5: User Story 3 — Consistent Download Experience for Generic URLs (Priority: P3)

**Goal**: Audio-only mode, quality selection (Check Formats), and output folder work identically for generic URLs as for social media URLs — no hidden degradation.

**Independent Test**: Paste a generic URL → select audio-only → click Download → audio extracted. Also: click "Check Formats" → formats listed or clear "unavailable" message shown (quickstart Test 1 audio variant).

### Implementation

- [X] T010 [US3] Verify generic platform branch in `core/downloader.py` passes `media_type`, `quality`, `audio_format`, `output_dir`, `video_codec`, `force_codec`, and `cancel_check` through to yt-dlp opts unchanged — no special-casing of these params for generic vs social media paths; add any missing passthrough if found
- [X] T011 [US3] Verify `_on_url_changed()` and any format-check logic in `gui/tabs/download_section.py` does not block or short-circuit "Check Formats" button for `platform == "generic"`; fix if found

**Checkpoint**: All three user stories independently functional. Generic URL behaves like YouTube for all user-visible options.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T012 [P] Run `ruff check .` from repo root and fix any lint errors introduced by this feature
- [X] T013 [P] Update `README.md` to document generic URL support — add one entry to the features list or downloads section noting that any video URL (not only social media) can be used (constitution Dev Workflow requirement)
- [ ] T014 Execute full manual test plan from `specs/007-generic-url-download/quickstart.md` — all 7 tests must pass (Tests 1–6 cover new behavior; Test 7 is social media regression)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — T004/T005/T006 can run in parallel; T007 depends on all three; T008 depends on T007
- **US2 (Phase 4)**: Depends on Phase 2 — independent of US1; single task
- **US3 (Phase 5)**: Depends on Phase 3 (T007 must exist before verifying passthrough)
- **Polish (Phase 6)**: Depends on all user story phases complete

### User Story Dependencies

- **US1 (P1)**: Foundational done → T004 ∥ T005 ∥ T006 → T007 → T008 → T008b
- **US2 (P2)**: Foundational done → T009 (independent of US1)
- **US3 (P3)**: US1 done → T010 → T011

### Parallel Opportunities Within US1

```
# After T003 (foundational) completes:
T004  _classify_yt_dlp_error()     ← can start
T005  _is_direct_video_url()       ← can start in parallel with T004
T006  _http_fallback_download()    ← can start in parallel with T004, T005

# After T004 + T005 + T006 all complete:
T007  generic branch in download_media()   ← sequential, depends on all three

# After T007:
T008   _on_result() UI updates             ← sequential
T008b  history verification                ← sequential, depends on T008
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup (T001–T002)
2. Complete Phase 2: Foundational (T003)
3. Complete Phase 3: US1 (T004–T008)
4. **STOP and VALIDATE**: Run quickstart Tests 1–6
5. Ship MVP — generic URL downloads work end-to-end

### Incremental Delivery

1. Setup + Foundational → base ready
2. US1 → core download works (MVP)
3. US2 → label clarity (quick win, single line change)
4. US3 → verify feature parity (validation only, likely no code change)
5. Polish → lint + full manual test pass

---

## Notes

- No new files — all changes in 2 existing files
- No new PyPI dependencies — `urllib` is stdlib (research.md Finding 5)
- Social media paths MUST remain untouched — `error_code`/`warning` default to `None` there (T003)
- `socket_timeout: 30` applied ONLY in generic branch (research.md Finding 3)
- `playlist_items: "1"` applied ONLY when generic AND playlist detected in pre-flight (research.md Finding 2)
