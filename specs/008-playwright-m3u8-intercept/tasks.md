# Tasks: Playwright HLS Stream Intercept

**Input**: Design documents from `/specs/008-playwright-m3u8-intercept/`
**Branch**: `008-playwright-m3u8-intercept`
**Generated**: 2026-04-17

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Ensure playwright dependency is declared and the project structure for new files is ready.

- [x] T001 Add `playwright` to project dependencies (requirements.txt or pyproject.toml)
- [x] T002 [P] Create empty `core/interceptor.py` with module docstring and `__all__` stub
- [x] T003 [P] Create empty `tests/unit/test_interceptor.py` with module docstring

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data structures and infrastructure all user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T004 Define `InterceptState` enum (`IDLE`, `LOADING`, `WAITING`, `CAPTURED`, `TIMED_OUT`, `CANCELLED`, `FAILED`) in `core/interceptor.py`
- [x] T005 [P] Define `InterceptResult` dataclass (`success`, `m3u8_url`, `cookies`, `headers`, `error_code`, `error_message`) in `core/interceptor.py`
- [x] T006 Add `intercept_timeout: int = 30` field to `UserSettings` dataclass in `core/settings.py`; bump schema version `2` → `3`; add `from_dict` fallback for missing field
- [x] T007 Add `source: str = "direct"` field to `HistoryItem` dataclass in `core/history/`; update `from_dict` with `"direct"` fallback for backward compatibility
- [x] T008 Implement `check_playwright_installed() -> tuple[bool, str]` in `utils/deps.py` using lazy import + subprocess probe per research.md §4

**Checkpoint**: Data model and deps check complete — user story implementation can begin.

---

## Phase 3: User Story 1 — Download from Unsupported Site via Browser Intercept (Priority: P1) 🎯 MVP

**Goal**: yt-dlp fails → Playwright launches headless Chromium → `.m3u8` intercepted → best variant selected → download proceeds with browser cookies.

**Independent Test**: Paste a URL from a JS-rendered streaming site; app downloads the video without user intervention and file appears in download history with `source="browser_intercept"`.

### Implementation for User Story 1

- [x] T009 [US1] Implement `_cookies_header(cookies: list[dict]) -> str` helper in `core/interceptor.py` (converts cookie list to `name=value; ...` string)
- [x] T010 [US1] Implement `_write_netscape_cookies(cookies: list[dict]) -> str` in `core/interceptor.py` per research.md §3 (writes temp Netscape file, returns path)
- [x] T011 [US1] Implement `_select_best_variant(master_url: str, cookies: list[dict]) -> str` in `core/interceptor.py` per research.md §2 (urllib fetch + regex BANDWIDTH parse, relative URI resolution)
- [x] T012 [US1] Implement `intercept_m3u8(url, timeout, cancel_check, status_cb) -> InterceptResult` core state-machine in `core/interceptor.py`: lazy playwright import, browser launch, `page.on("request")` listener, `page.goto()`, poll loop per research.md §5, browser close in `finally`
- [x] T013 [US1] Implement `_get_intercept_timeout() -> int` helper in `core/downloader.py` (reads `SettingsManager.load().intercept_timeout`, fallback `30`)
- [x] T014 [US1] Add optional `status_cb: Callable[[str], None] | None = None` parameter to `download_media` and `_download_generic_media` in `core/downloader.py`; propagate to `try_playwright_intercept`
- [x] T015 [US1] Implement `try_playwright_intercept(classified)` inner function in `_download_generic_media` in `core/downloader.py` per contracts/downloader-changes.md — call `intercept_m3u8`, write cookie file, run yt-dlp on m3u8 URL, delete cookie file in `finally`
- [x] T016 [US1] Wire `try_playwright_intercept` as final fallback (after `try_html_scrape`) in `_download_generic_media` in `core/downloader.py`
- [x] T017 [US1] Update `HistoryItem` creation in download result handling to set `source="browser_intercept"` when `error_code == "browser_intercept_ok"` in `core/downloader.py`

**Checkpoint**: User Story 1 fully functional — headless intercept downloads video and records history entry.

---

## Phase 4: User Story 2 — Graceful Fallback and Error Handling (Priority: P2)

**Goal**: Every failure mode (timeout, missing Playwright, nav error, no stream) surfaces a clear error message; UI returns to ready state; no crash or hang.

**Independent Test**: Submit a non-HLS URL — app shows descriptive error and stops cleanly within `timeout + 5 s`.

### Implementation for User Story 2

- [x] T018 [US2] Handle `"launch_failed"` error code in `intercept_m3u8`: if `check_playwright_installed()` returns `False`, return `InterceptResult(success=False, error_code="launch_failed", error_message=<hint text>)` immediately without launching browser in `core/interceptor.py`
- [x] T019 [US2] Handle `"no_stream"` error code: when poll loop exits with empty `captured_urls`, return `InterceptResult(success=False, error_code="no_stream", ...)` in `core/interceptor.py`
- [x] T020 [US2] Handle `"nav_error"` error code: wrap `page.goto()` in `try/except Exception` and return `InterceptResult(success=False, error_code="nav_error", error_message=str(e))` in `core/interceptor.py`
- [x] T021 [US2] Handle `"cancelled"` error code: when `cancel_check()` returns `True` inside poll loop, break and return `InterceptResult(success=False, error_code="cancelled", ...)` in `core/interceptor.py`
- [x] T022 [US2] Ensure `intercept_m3u8` closes browser context in `finally` block regardless of outcome (success, all error paths) in `core/interceptor.py`
- [x] T023 [US2] Map all `InterceptResult` error codes to user-facing messages in `try_playwright_intercept` return dict in `core/downloader.py`; include Playwright install hint when `error_code == "launch_failed"`
- [x] T024 [P] [US2] Add unit tests for all `InterceptResult` error paths (mock `sync_playwright`) in `tests/unit/test_interceptor.py`: `launch_failed`, `no_stream`, `nav_error`, `cancelled`

**Checkpoint**: All error paths return clean results; UI shows descriptive messages; no hangs.

---

## Phase 5: User Story 3 — Transparent Status During Browser Session (Priority: P3)

**Goal**: Status messages appear in the download tab throughout the intercept phase; cancel button works during intercept.

**Independent Test**: Submit a URL and observe "Loading page…" → "Waiting for stream URL…" → "Stream URL captured. Resolving quality…" → "Ready to download." messages in sequence; clicking Cancel during intercept closes browser and resets UI within 3 s.

### Implementation for User Story 3

- [x] T025 [US3] Emit `status_cb("Loading page…")` before `page.goto()` in `intercept_m3u8` in `core/interceptor.py`
- [x] T026 [US3] Emit `status_cb("Waiting for stream URL…")` after `page.goto()` succeeds, before poll loop in `intercept_m3u8` in `core/interceptor.py`
- [x] T027 [US3] Emit `status_cb("Stream URL captured. Resolving quality…")` immediately when first `.m3u8` URL is detected in `intercept_m3u8` in `core/interceptor.py`
- [x] T028 [US3] Emit `status_cb("Ready to download.")` after `_select_best_variant` resolves in `intercept_m3u8` in `core/interceptor.py`
- [x] T029 [US3] Wire `status_cb` from `Worker` signal to download tab status label in `gui/tabs/download_section.py`: create `on_intercept_status(msg: str)` slot that updates the existing status label during intercept phase
- [x] T030 [US3] Pass `status_cb=self.intercept_status_signal.emit` (or equivalent lambda) when calling `download_media` from `Worker` in `gui/worker.py` (or `gui/tabs/download_section.py` call site)
- [x] T031 [US3] Verify cancel button during intercept: confirm `Worker.cancel()` sets flag that `cancel_check()` reads; `intercept_m3u8` poll loop reads it every 500 ms and exits in `gui/tabs/download_section.py` + `gui/worker.py`
- [x] T032 [P] [US3] Add unit tests for `status_cb` call sequence and cancel path in `tests/unit/test_interceptor.py`: assert status strings emitted in order, assert `cancel_check` exits loop

**Checkpoint**: All three user stories complete — status messages visible, cancel functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T033 [P] Add `intercept_timeout` setting control (spinbox, range 10–300) to Settings tab Advanced section in `gui/tabs/settings_section.py`
- [x] T034 [P] Add clamping validation for `intercept_timeout` in `UserSettings.save()` / setter in `core/settings.py`
- [x] T035 Update `utils/deps.py` `check_playwright_installed` probe to use safer subprocess approach (per research.md §4 note on `--dry-run` portability)
- [x] T036 [P] Add optional `LIVE_TEST` guard to `tests/integration/test_intercept_live.py` (`pytest.importorskip` / `skipif` on `os.environ.get("LIVE_TEST") != "1"`)
- [x] T037 Run `ruff check .` and fix any linting issues across new and modified files
- [x] T038 Run `pytest tests/unit/test_interceptor.py -v` and confirm all unit tests pass

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **BLOCKS all user stories**
- **User Story phases (3–5)**: All depend on Phase 2 completion
  - US1 (Phase 3) has no dependency on US2/US3
  - US2 (Phase 4) depends on Phase 3 (error paths extend the state machine built in US1)
  - US3 (Phase 5) depends on Phase 3 (status_cb wiring requires `intercept_m3u8` to exist)
- **Polish (Phase 6)**: Depends on all user story phases complete

### Within Each User Story

- Foundational data structures (T004–T008) before any US implementation
- Helpers (`_cookies_header`, `_write_netscape_cookies`, `_select_best_variant`) before `intercept_m3u8`
- `intercept_m3u8` complete before downloader integration
- Downloader integration before GUI wiring

### Parallel Opportunities

- T002, T003 in Phase 1 parallel (different files)
- T005 parallel with T006, T007, T008 in Phase 2 (different files)
- T009, T010, T011 in Phase 3 parallel (different helpers, same file sections — assign carefully)
- T018, T019, T020, T021 in Phase 4 parallel (separate error code branches)
- T025–T028 in Phase 5 parallel (sequential status strings in same function — keep in order)
- T033, T034, T036, T037 in Phase 6 parallel

---

## Parallel Example: User Story 1

```bash
# Phase 3 helper tasks (run together):
Task T009: _cookies_header helper in core/interceptor.py
Task T010: _write_netscape_cookies helper in core/interceptor.py
Task T011: _select_best_variant in core/interceptor.py

# After helpers done, run together:
Task T013: _get_intercept_timeout in core/downloader.py
Task T012: intercept_m3u8 state machine in core/interceptor.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Submit JS-rendered streaming URL; confirm download succeeds and appears in history
5. Demo/ship MVP

### Incremental Delivery

1. Setup + Foundational → skeleton ready
2. User Story 1 → core intercept works → validate → demo (MVP)
3. User Story 2 → error handling → validate all failure scenarios
4. User Story 3 → status UX + cancel → validate status messages and cancel
5. Polish → settings control, linting, tests

---

## Notes

- `[P]` tasks touch different files — safe to parallelize
- `[Story]` label maps each task to a user story for traceability
- `intercept_m3u8` MUST use lazy `playwright` import (inside function body) per contracts/interceptor-api.md invariants
- Browser context MUST close in `finally` regardless of outcome
- Cookie temp file cleanup is the caller's responsibility (`try_playwright_intercept` in downloader.py)
- `intercept_timeout` clamped to `[10, 300]` on save per data-model.md validation rules
- History `source` field defaults to `"direct"` for backward compatibility — no migration needed
