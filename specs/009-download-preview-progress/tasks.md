# Tasks: Download Preview & Rich Progress

**Input**: Design documents from `/specs/009-download-preview-progress/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/internal-api.md ✅, quickstart.md ✅

**Tests**: Not requested in spec — no test tasks generated.

**Organization**: Tasks grouped by user story. US1 (rich progress) first; US2 (preview player) second. Both can be validated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallelizable (different files, no blocking dependency)
- **[Story]**: User story label — US1 or US2
- Exact file paths included in every description

---

## Phase 1: Setup (Verify Existing Infrastructure)

**Purpose**: Confirm the existing signal declaration and trim tab patterns before writing any code.

- [x] T001 Audit `Worker.signals.progress = Signal(int, int, str)` at `gui/worker.py:11`; confirm existing inline `_progress_hook` closure location in `core/downloader.py`
- [x] T002 [P] Read `gui/tabs/trim_section.py` QMediaPlayer/QVideoWidget setup (lines 131–192 region) to extract the exact reuse pattern for Story 2

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared helpers in `core/downloader.py` that both user stories depend on. Must be complete before either story can be wired up.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T003 Add `_fmt_speed(bps: float) -> str` helper function to `core/downloader.py` (returns `"X.X MB/s"` / `"XXX KB/s"` / `""` per contracts/internal-api.md)
- [x] T004 Extract the inline `_progress_hook` closure into `_make_progress_hook(cancel_check, progress_cb) -> Callable[[dict], None]` in `core/downloader.py`, referencing `_fmt_speed` for speed formatting

**Checkpoint**: `_fmt_speed` and `_make_progress_hook` exist and are importable — user story work can begin.

---

## Phase 3: User Story 1 — Rich Download Progress Display (Priority: P1) 🎯 MVP

**Goal**: Progress bar shows 0–100%, speed label updates every second, ETA counts down for all download paths (yt-dlp, HTTP fallback, generic).

**Independent Test**: Start any YouTube download → progress bar fills incrementally (not indeterminate), speed label shows MB/s or KB/s, ETA label counts down. On completion bar reaches 100% and labels clear.

### Implementation for User Story 1

- [x] T005 [US1] Add `progress_cb: Callable[[int, int, str], None] | None = None` param to `download_media` in `core/downloader.py`; replace old inline hook usage with `_make_progress_hook(cancel_check, progress_cb)` in `ydl_opts['progress_hooks']`
- [x] T006 [US1] Propagate `progress_cb` through `_download_generic_media` in `core/downloader.py` — add param, pass through to inner `download_media` calls
- [x] T007 [US1] Update `_http_fallback_download` in `core/downloader.py` to accept `progress_cb`; replace current bulk-read with chunked loop (8 KB chunks), read `Content-Length` header, compute `pct`/`eta`/`speed_str` per chunk per research.md §3, call `progress_cb` after each write
- [x] T008 [P] [US1] Add `_speed_label` (QLabel, initially hidden) and `_eta_label` (QLabel, initially hidden) widgets to `_build_progress_card()` in `gui/tabs/download_section.py`; position below progress bar
- [x] T009 [P] [US1] Add `_on_progress(self, percent: int, eta: int, speed_str: str) -> None` method to `DownloadSection` in `gui/tabs/download_section.py`; logic: `setRange(0,100)` + `setValue(percent)` when `percent != -1`, else `setRange(0,0)`; update `_speed_label` and `_eta_label` text or hide when values are `-1` / `""`
- [x] T010 [US1] In `trigger_primary_action` in `gui/tabs/download_section.py`: pass `lambda p, e, s: self._worker.signals.progress.emit(p, e, s)` as `progress_cb`; connect `self._worker.signals.progress.connect(self._on_progress)` (depends T008, T009)
- [x] T011 [US1] Update `_set_busy` in `gui/tabs/download_section.py` to show `_speed_label` and `_eta_label` when busy starts and clear + hide them when busy ends

**Checkpoint**: User Story 1 fully functional. Bar fills, speed and ETA display, labels clear on done/cancel. Existing quality/audio/folder/cancel controls unchanged.

---

## Phase 4: User Story 2 — Video Preview for Time-Range Selection (Priority: P2)

**Goal**: "Load Preview" button streams video into an embedded player; draggable start/end sliders populate time-range inputs; Download uses `--download-sections` for the selected segment.

**Independent Test**: YouTube URL → click "Load Preview" → embedded player appears and plays → drag start/end sliders → text inputs update in HH:MM:SS → click Download → only selected segment downloaded. URL change hides player and resets inputs.

### Implementation for User Story 2

- [x] T012 [US2] Add `get_preview_stream_url(url: str) -> dict` to `core/downloader.py`; implement per contracts/internal-api.md: call `YoutubeDL({'quiet': True, 'format': 'best[height<=720]'}).extract_info(url, download=False)`, detect `is_live`, extract `stream_url`/`duration_ms`/`title`, return error key on exception
- [x] T013 [US2] Add `_multimedia_available` guard at top of `DownloadSection.__init__` in `gui/tabs/download_section.py` (mirror trim tab pattern); add imports `QMediaPlayer`, `QVideoWidget`, `QAudioOutput`, `QUrl`, `QTimer` from `PySide6.QtMultimedia` / `PySide6.QtCore`
- [x] T014 [US2] Add `_build_preview_card(self) -> QFrame` method to `DownloadSection` in `gui/tabs/download_section.py`; card contains `QVideoWidget` (min 200 px height), play/pause button, position `QSlider` scrubber, time label; card hidden by default (`setVisible(False)`); initialize `_player` (QMediaPlayer), `_audio_output` (QAudioOutput), `_pos_timer` (QTimer 200 ms) following trim_section.py pattern; insert card between options area and progress bar
- [x] T015 [US2] Add start-marker `QSlider` and end-marker `QSlider` to preview card in `gui/tabs/download_section.py`; add `_on_start_slider_moved(value: int)` and `_on_end_slider_moved(value: int)` handlers that call `_ms_to_str(value)` and update `_start_input` / `_end_input` text fields; add `_ms_to_str` helper; guard circular updates with `_updating` boolean flag
- [x] T016 [US2] Add "Load Preview" button to trim card header row in `gui/tabs/download_section.py`; disable when URL field is empty; visible only when `_multimedia_available` is True
- [x] T017 [US2] Add `_load_preview(self, url: str) -> None` method to `DownloadSection` in `gui/tabs/download_section.py`; spawn Worker calling `get_preview_stream_url(url)`; show spinner/disabled state while loading; add `_on_preview_loaded(self, result: dict) -> None` result handler that on success calls `_player.setSource(QUrl(stream_url))`, sets slider ranges from `duration_ms`, shows preview card; on failure (error or is_live) shows FR-010 inline message and keeps card hidden
- [x] T018 [US2] Modify `_on_url_changed` in `gui/tabs/download_section.py` to hide preview card, stop `_player`, reset start/end sliders to 0, clear start/end input fields, cancel any in-flight preview worker when URL changes
- [x] T019 [US2] Add FR-008 validation in `trigger_primary_action` in `gui/tabs/download_section.py`: when preview is active and start_ms ≥ end_ms, show inline validation message and abort download; when valid range set, append `--download-sections "*{start_s}-{end_s}"` to downloader kwargs
- [x] T020 [US2] Add FR-010 fallback message display when `_load_preview` receives `is_live=True`, `error` set, or audio-only (no video stream) — show message label in preview card area, keep text-based time inputs accessible in `gui/tabs/download_section.py`

**Checkpoint**: User Stories 1 AND 2 both independently functional.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Edge-case verification and regression validation across both stories.

- [x] T021 Verify FR-004 indeterminate fallback path in `gui/tabs/download_section.py` — download a URL where size is unknown (e.g., live radio) and confirm bar is indeterminate while speed label still appears when speed data is available
- [x] T022 [P] Manual regression check per `specs/009-download-preview-progress/quickstart.md` — confirm quality selection, audio format, output folder, cancel all work unchanged after US1 changes
- [x] T023 [P] Verify SC-004/SC-005 sync timing — drag a preview slider and confirm time input updates within 500 ms; confirm start ≥ end validation fires before download starts

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **BLOCKS both user stories**
- **User Story 1 (Phase 3)**: Depends on Phase 2 completion
- **User Story 2 (Phase 4)**: Depends on Phase 2 completion; independent of US1 (can start in parallel with US1 after Phase 2)
- **Polish (Phase 5)**: Depends on all desired stories complete

### User Story Dependencies

- **US1 (P1)**: Depends on T003, T004 (foundational helpers). No dependency on US2.
- **US2 (P2)**: Depends on T003, T004. No dependency on US1. Can run in parallel with US1 after Phase 2.

### Within User Story 1

```
T003 → T004 → T005 → T006 → T007 (parallel with T008)
                    → T007 ─┐
                    → T008 ─┴→ T010 → T011
```

### Within User Story 2

```
T012 (parallel with T013)
T013 → T014 → T015 → T016
T014 → T015 → T016 → T017
T016 → T017
T017 → T018 → T019
T019 → T020
```

### Parallel Opportunities

- T001 and T002 (Phase 1) — different files
- T003 can start as soon as Phase 1 done
- T008 and T009 (US1 GUI widgets + handler method) — same file, independent additions
- T012 and T013 (US2 backend fn + guard import) — different concerns
- US1 and US2 phases can run in parallel after Phase 2 (different team members)
- T022 and T023 (Phase 5 manual checks) — independent tests

---

## Parallel Example: User Story 1

```bash
# After T004, these two GUI tasks can proceed in parallel:
Task T008: Add _speed_label + _eta_label widgets to _build_progress_card()
Task T009: Add _on_progress handler method to DownloadSection
# Then:
Task T010: Connect signal and pass progress_cb (depends T008, T009)
```

## Parallel Example: User Story 2

```bash
# After Phase 2, these can start in parallel with US1:
Task T012: Add get_preview_stream_url() to core/downloader.py
Task T013: Add _multimedia_available guard + imports to download_section.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T002)
2. Complete Phase 2: Foundational (T003–T004) — CRITICAL
3. Complete Phase 3: User Story 1 (T005–T011)
4. **STOP AND VALIDATE**: Download any URL, confirm bar fills, speed/ETA display
5. Ship US1 as standalone improvement before adding preview

### Incremental Delivery

1. Setup + Foundational → helpers ready
2. User Story 1 → test progress display → demo/ship (MVP)
3. User Story 2 → test preview player → demo/ship
4. Polish → edge cases confirmed

### Parallel Team Strategy

With two developers after Phase 2:

- Developer A: US1 (T005–T011) in `core/downloader.py` + `gui/tabs/download_section.py` progress path
- Developer B: US2 (T012–T020) in `core/downloader.py` `get_preview_stream_url` + `gui/tabs/download_section.py` preview card

Stories touch the same files but different methods — merge conflicts are minimal if each dev owns distinct method additions.

---

## Notes

- No new dependencies or new files — all changes extend existing modules
- `gui/worker.py` is **not modified** — `Signal(int, int, str)` already declared at line 11
- `core/history/`, `core/settings.py`, `gui/app.py` are **not modified**
- `_updating` boolean flag in US2 prevents circular slider ↔ input sync loops
- Preview stream URL expiry (~6 h): if `QMediaPlayer` errors after a gap, fall back silently to full URL download — no extra code needed (existing Worker error path handles it)
- [P] tasks = different files or independent additions with no blocking dependency
- Commit after each task or logical group; stop at each checkpoint to validate independently
