---
description: "Task list for Download State Recovery"
---

# Tasks: Download State Recovery

**Input**: Design documents from `/specs/010-fix-download-recovery/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, quickstart.md ✅

**Tests**: No test tasks — not requested in spec. Manual validation via quickstart.md.

**Organization**: Tasks grouped by user story. Single-file fix (primary: `gui/tabs/download_section.py`, minor: `core/downloader.py`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (independent of other in-flight tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths in every task description

---

## Phase 1: Setup (Audit)

**Purpose**: Confirm current widget/variable names in affected files before making changes

- [X] T001 Read `DownloadSection.__init__`, `trigger_primary_action`, `_on_result`, `_on_error`, `_on_progress`, `_set_busy`, and `_GENERIC_ERROR_MESSAGES` in `gui/tabs/download_section.py` to confirm attribute names and signal names match those referenced in plan.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: New state fields and helper methods that all three user stories depend on

**⚠️ CRITICAL**: No user story work can begin until T002–T005 are complete

- [X] T002 Add `self._download_token: int = 0` and `self._active_output_dir: str | None = None` to `DownloadSection.__init__` in `gui/tabs/download_section.py`
- [X] T003 Add `_reset_ui(self) -> None` method to `DownloadSection` in `gui/tabs/download_section.py`: call `self._set_busy(False)`, call `self._progress_label.setVisible(False)`, `self._speed_label.setVisible(False)`, `self._eta_label.setVisible(False)`, `self._progress_bar.setRange(0, 0)`, `self._progress_bar.setValue(0)` — do NOT clear `self._active_output_dir` here (cleanup reads it after this call); verify exact widget attribute names against T001 findings
- [X] T004 [P] Add `_cleanup_partial_files(self) -> None` method to `DownloadSection` in `gui/tabs/download_section.py`: scan `self._active_output_dir or "."` with `os.scandir`, call `os.remove(f.path)` for each entry where `f.name.endswith(".part") and f.is_file()`, swallow `OSError` silently; add `import os` at top of file if not already present
- [X] T005 In the download-start block of `trigger_primary_action` in `gui/tabs/download_section.py`: increment `self._download_token` before creating the worker, capture `token = self._download_token`, set `self._active_output_dir = out_dir`; re-wire all three worker signal connections as closures that check `token == self._download_token` before delegating to `_on_result`, `_on_error`, `_on_progress` (e.g. `worker.result.connect(lambda r: self._on_result(r) if token == self._download_token else None)`)

**Checkpoint**: Foundation ready — all three user-story phases can now proceed

---

## Phase 3: User Story 1 — Cancel and Retry Download (Priority: P1) 🎯 MVP

**Goal**: Cancel leaves the UI immediately ready for a new download; cancelled worker cannot interfere with the next download

**Independent Test**: Start a download, click Cancel within 2 s, verify button shows "Download" and status shows "Download cancelled", start a new download — it must start normally (quickstart.md Test 1, 10× cycle)

### Implementation for User Story 1

- [X] T006 [US1] Refactor cancel branch in `trigger_primary_action` in `gui/tabs/download_section.py`: add double-cancel guard `if self._worker is None: return` at top of branch; then call `self._worker.cancel()`, `self._download_token += 1`, `self._worker = None`, `self._cleanup_partial_files()` (reads `_active_output_dir` while still set), `self._reset_ui()`, `self._active_output_dir = None`, `self.status_message.emit("Download cancelled.")` (satisfies US1-A1); remove any old `self._set_busy(False)` or manual label-hide calls that `_reset_ui()` now covers

**Checkpoint**: User Story 1 fully functional — cancel-and-retry works; stale signals from cancelled worker are discarded by T005 closures

---

## Phase 4: User Story 2 — Download After Invalid URL Error (Priority: P1)

**Goal**: Any download failure resets the UI to a fully operable state with a user-friendly error message; no app restart required

**Independent Test**: Enter `https://example.com/notavideo`, wait for error message, verify button shows "Download" and no raw traceback is visible, enter a valid URL and click Download — new download must start (quickstart.md Test 2)

### Implementation for User Story 2

- [X] T007 [US2] Add `"cancelled": "Download cancelled."` key to `_GENERIC_ERROR_MESSAGES` dict in `gui/tabs/download_section.py` to close the gap identified in research.md Q6
- [X] T008 [US2] Audit `_on_error` in `gui/tabs/download_section.py`: replace any `self._set_busy(False)` call with `self._reset_ui()`; confirm the method only executes when called by a current-token closure (already guarded via T005 wiring); verify all `error_code` values are handled by `_GENERIC_ERROR_MESSAGES` fallback
- [X] T009 [US2] Audit `_on_result` in `gui/tabs/download_section.py`: replace any `self._set_busy(False)` call with `self._reset_ui()` on both success and failure exit paths; confirm method only executes for current-token closures (T005)

**Checkpoint**: User Stories 1 AND 2 independently functional — cancel-retry and error-retry both work

---

## Phase 5: User Story 3 — Download State Resilience Under Any Outcome (Priority: P2)

**Goal**: Every possible download outcome (success, failure, cancel, rapid successive attempts) leaves the Download tab in a consistent ready state with no UI degradation

**Independent Test**: Perform 10 rapid cancel-and-retry cycles; trigger errors under different conditions (slow network cancel, bad URLs back-to-back); verify Download button and all progress indicators are always restored (quickstart.md Tests 3–5)

### Implementation for User Story 3

- [X] T010 [US3] Add stale-signal guard `if token != self._download_token: return` at the very start of `_on_progress` in `gui/tabs/download_section.py` — `token` must be passed into the method or checked via closure from T005 wiring; prevents a finishing download's progress events from overwriting the new download's UI
- [X] T011 [US3] [P] Audit `core/downloader.py` cancel path: confirm `_http_fallback_download` deletes partial file when `cancel_check()` returns `True` (research.md Q5 says lines 152–163 already handle this); if the `cancel_check` callable is not already plumbed through to yt-dlp progress hook, add it so the hook raises on cancel

**Checkpoint**: All three user stories independently functional; app survives 10× cancel-retry and back-to-back errors

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Manual validation, automated unit test, lint, and regression checks

- [X] T012 Write pytest unit test in `tests/test_download_token.py` (create file): mock `DownloadSection` signals; verify (a) stale result/error/progress callbacks are discarded when token advances, (b) current-token callbacks execute — covers constitution Principle IV automated test requirement for the novel token counter logic
- [ ] T013 Run quickstart.md Test 1 manually (cancel-and-retry 10× cycle): verify SC-001 (button restores within 1 s), SC-004 (10 cycles without degradation)
- [ ] T014 [P] Run quickstart.md Tests 2–5: invalid URL retry (SC-002, SC-003), double cancel (FR-008), partial file cleanup (FR-006), rapid cancel-start (FR-007)
- [X] T015 [P] Run `ruff check .` from repo root and fix any lint warnings in `gui/tabs/download_section.py` or `core/downloader.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (T001 names needed) — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Phase 2 complete
- **US2 (Phase 4)**: Depends on Phase 2 complete — can run in parallel with US1 if two developers
- **US3 (Phase 5)**: Depends on Phase 2 complete — can run in parallel with US1 and US2
- **Polish (Phase 6)**: Depends on all desired stories complete

### User Story Dependencies

- **US1 (P1)**: Requires Foundation (Phase 2) only — no dependency on US2/US3
- **US2 (P1)**: Requires Foundation (Phase 2) only — no dependency on US1/US3
- **US3 (P2)**: Requires Foundation (Phase 2) only; T011 is independent of US1/US2

### Within Each User Story

- Foundation tasks (T002 → T003 → T004/T005 in order; T004 and T005 can be parallel)
- US1: just T006 (single task)
- US2: T007 → T008 → T009 (sequential, same method area)
- US3: T010 and T011 are parallel (different files)

### Parallel Opportunities

- T004 (cleanup method) and T005 (signal re-wiring) can be implemented in parallel (different methods)
- US1 (T006), US2 (T007–T009), US3 (T010–T011) can all run in parallel after Foundation
- T012, T013, T014, T015 (Polish) can all run in parallel after T012 unit test written

---

## Parallel Example: Foundation Phase

```bash
# After T002 and T003 complete, launch in parallel:
Task T004: "_cleanup_partial_files() in gui/tabs/download_section.py"
Task T005: "Signal re-wiring with token closures in trigger_primary_action"
```

## Parallel Example: User Story Phase

```bash
# After Foundation complete, all three stories in parallel (if multi-developer):
Developer A → T006 (US1 cancel branch)
Developer B → T007, T008, T009 (US2 error path)
Developer C → T010, T011 (US3 resilience)
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002–T005) — **CRITICAL, blocks everything**
3. Complete Phase 3: User Story 1 (T006)
4. **STOP and VALIDATE**: Run quickstart.md Test 1 — cancel-and-retry must work
5. Complete Phase 4: User Story 2 (T007–T009)
6. **STOP and VALIDATE**: Run quickstart.md Test 2 — invalid URL retry must work
7. Deploy/demo MVP if ready

### Incremental Delivery

1. Foundation → US1 → validate cancel-retry → Demo (core fix)
2. Add US2 → validate error-retry → Demo (full P1 scope)
3. Add US3 → validate 10× cycle + edge cases → Demo (hardened)
4. Polish → lint + regression checks → Ship

---

## Notes

- No new files. No new modules. Two affected files only: `gui/tabs/download_section.py` (primary), `core/downloader.py` (audit/minor)
- `_reset_ui()` is the single authoritative reset — never call `_set_busy(False)` directly in UI-recovery paths
- Token counter only ever increases; never reset to 0 after init
- `self._worker = None` is safe immediately on cancel — Qt holds the thread reference internally (research.md Q3)
- HTTP fallback cleanup already works (research.md Q5) — T011 is a verification task, not an implementation task unless the audit finds a gap
