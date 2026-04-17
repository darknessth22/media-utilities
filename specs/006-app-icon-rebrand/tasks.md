# Tasks: Custom App Icon & Rebrand to Medix

**Input**: Design documents from `/specs/006-app-icon-rebrand/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: No automated tests explicitly requested. Manual verification per acceptance scenarios.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Ensure icon asset files are in place before implementation begins

- [ ] T001 Create `assets/icons/` directory if it does not exist and generate a minimal valid 256x256 PNG (solid-color development placeholder) at `assets/icons/app-icon.png` — user replaces with their artwork per quickstart.md
- [ ] T002 [P] Verify `icon.ico` exists at project root; if not, create a placeholder ICO file at `icon.ico`

**Checkpoint**: Icon assets are in place. Implementation can begin.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: No foundational infrastructure changes needed — this feature modifies existing files only. Skip to user stories.

**⚠️ NOTE**: The icon asset from Phase 1 is the only prerequisite. No database, routing, or framework setup required.

---

## Phase 3: User Story 1 — Replace Default Python Icon with Custom Icon (Priority: P1) :dart: MVP

**Goal**: Display a custom branded icon in the window title bar, OS taskbar, system tray, and built executable instead of the default Python icon.

**Independent Test**: Launch the application and verify the custom icon appears in the window title bar, taskbar, and system tray. Confirm the default Python icon is no longer visible anywhere.

### Implementation for User Story 1

- [ ] T003 [US1] Import `QIcon` and call `app.setWindowIcon(QIcon("assets/icons/app-icon.png"))` in `main.py` after `QApplication` creation (around line 44), using `os.path.join` and resource path resolution for frozen/dev environments
- [ ] T004 [US1] Verify `core/tray.py` tray icon setup — confirm `_make_tray_icon()` (line ~66) uses the custom icon or inherits the app-level icon; update if needed in `core/tray.py`
- [ ] T005 [US1] Confirm `media_util_gui.spec` references `icon.ico` for the PyInstaller `icon=` parameter (line ~123) in `media_util_gui.spec`
- [ ] T006 [US1] Update `build_executable.py` to ensure the `--icon` flag points to `icon.ico` and `app-icon.png` is included in PyInstaller data files via `build_executable.py`

**Checkpoint**: Custom icon displays in title bar, taskbar, and tray. Executable shows the custom icon in file explorer.

---

## Phase 4: User Story 2 — Rename Application to Medix (Priority: P1)

**Goal**: Replace all user-facing occurrences of "Media Utility" / "MediaUtility" with "Medix" across the application UI, build scripts, and installer configuration.

**Independent Test**: Search all source files for "Media Utility" and "MediaUtility" — zero matches should remain in user-facing strings. Launch the app and verify "Medix" appears in window title, taskbar, and tray tooltip.

### Implementation for User Story 2

- [ ] T007 [P] [US2] Rename application name in `main.py`: update docstring (line 1) from "Media Utility" to "Medix" and `app.setApplicationName("Media Utility")` → `app.setApplicationName("Medix")` (line 44)
- [ ] T008 [P] [US2] Rename all "Media Utility" occurrences in `gui/app.py`: title bar label (line ~151), sidebar label (line ~620), error dialog titles (line ~822), and tray notification title (line ~988)
- [ ] T009 [P] [US2] Rename tray tooltip in `core/tray.py`: `self._tray.setToolTip("Media Utility")` → `self._tray.setToolTip("Medix")` (line ~66)
- [ ] T010 [P] [US2] Rename all occurrences in `build_executable.py`: docstring, Inno Setup AppName, AppPublisher, DefaultDirName (`{autopf}\\MediaUtility` → `{autopf}\\Medix`), DefaultGroupName, shortcut labels, exe filename refs, and print statements
- [ ] T011 [P] [US2] Rename exe name in `media_util_gui.spec`: `name='MediaUtility'` → `name='Medix'` (lines ~110 and ~134)
- [ ] T012 [P] [US2] Update docstring in `media_util_gui.py` to reference "Medix" instead of "Media Utility"

**Checkpoint**: All user-facing strings say "Medix". No references to "Media Utility" or "MediaUtility" remain in UI or build artifacts.

---

## Phase 5: User Story 3 — Icon Setup Instructions (Priority: P2)

**Goal**: Provide clear, documented steps so a user or developer can replace the application icon with their own artwork.

**Independent Test**: Follow the documented steps in quickstart.md with a new icon file and verify the application displays the new icon correctly.

### Implementation for User Story 3

- [ ] T013 [US3] Review and finalize `specs/006-app-icon-rebrand/quickstart.md` — ensure all file paths, format requirements, and troubleshooting steps match the actual implementation from US1
- [ ] T014 [US3] Add an inline comment in `main.py` near the `setWindowIcon()` call documenting the expected icon path and fallback behavior for future developers

**Checkpoint**: A user following quickstart.md can replace the icon and see their custom icon in-app.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final verification and cleanup across all stories

- [ ] T015 [P] Run a project-wide search for any remaining "Media Utility" or "MediaUtility" strings that were missed, across all files
- [ ] T016 [P] Verify graceful fallback: temporarily rename `assets/icons/app-icon.png` and confirm the app launches without crashing (FR-009)
- [ ] T017 Verify backward compatibility: confirm existing user config/history data is still loaded correctly after the rename (FR-012) by checking `core/settings.py` path logic
- [ ] T018 Run `ruff check .` and `pytest` to ensure no regressions
- [ ] T019 [P] Update README.md and SETUP.md to reflect the "Medix" rebrand and document the icon setup process (reference quickstart.md)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **User Story 1 (Phase 3)**: Depends on Setup (Phase 1) — needs icon assets in place
- **User Story 2 (Phase 4)**: Depends on Setup (Phase 1) — no dependency on US1
- **User Story 3 (Phase 5)**: Depends on US1 completion (Phase 3) — documentation must match implementation
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Setup. No dependency on US2.
- **User Story 2 (P1)**: Can start after Setup. No dependency on US1. **Can run in parallel with US1.**
- **User Story 3 (P2)**: Depends on US1 — documentation references icon paths and behavior from US1.

### Within Each User Story

- US1: Asset placement → main.py icon setup → tray verification → build script updates
- US2: All tasks are [P] (parallel) — each modifies a different file
- US3: Sequential — review docs, then add code comment

### Parallel Opportunities

- **T001 and T002** can run in parallel (different files)
- **T007, T008, T009, T010, T011, T012** (all US2 tasks) can run in parallel — each touches a different file
- **US1 and US2** can be worked on in parallel after Setup
- **T015, T016** (Polish) can run in parallel

---

## Parallel Example: User Story 2

```bash
# All US2 rename tasks can run simultaneously (different files):
Task T007: Rename in main.py
Task T008: Rename in gui/app.py
Task T009: Rename in core/tray.py
Task T010: Rename in build_executable.py
Task T011: Rename in media_util_gui.spec
Task T012: Rename in media_util_gui.py
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Complete Phase 1: Setup (place icon assets)
2. Complete Phase 3: User Story 1 (custom icon displays everywhere)
3. Complete Phase 4: User Story 2 (all strings say "Medix") — can run in parallel with US1
4. **STOP and VALIDATE**: Launch app, verify icon + name in title bar, taskbar, tray
5. Deploy/demo if ready

### Incremental Delivery

1. Setup → Icon assets in place
2. US1 + US2 (parallel) → App has custom icon and "Medix" branding → Test independently → MVP complete
3. US3 → Documentation finalized → Full feature complete
4. Polish → Search for stragglers, verify fallback, run linters

### Suggested MVP Scope

User Stories 1 and 2 together form the MVP — the app is fully rebranded with a custom icon and the "Medix" name. User Story 3 (documentation) is a follow-up enhancement.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently testable
- No automated tests requested — manual verification per acceptance scenarios
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
