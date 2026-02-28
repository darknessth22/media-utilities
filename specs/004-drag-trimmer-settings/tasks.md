# Tasks: Drag-Drop, Rich Trimmer & Global Settings

**Input**: Design documents from `/specs/004-drag-trimmer-settings/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not requested in specification - manual testing defined in quickstart.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and dependency installation

- [x] T001 Add tkinterdnd2 and python-vlc to requirements.txt
- [x] T002 [P] Create utils/vlc_check.py with VLC availability detection function
- [x] T003 [P] Create core/settings.py stub with UserSettings dataclass and default config path logic

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Implement SettingsManager.get_config_path() with platform detection in core/settings.py
- [x] T005 Implement SettingsManager.load() with merge strategy in core/settings.py
- [x] T006 Implement SettingsManager.save() with atomic write in core/settings.py
- [x] T007 Implement SettingsManager.reset() in core/settings.py
- [x] T008 Implement vlc_check.is_vlc_available() with fallback messaging in utils/vlc_check.py
- [x] T009 Update gui/app.py to use TkinterDnD.Tk() as root window instead of standard tk.Tk()

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Drag and Drop File Loading (Priority: P1)

**Goal**: Users can drag files onto the app window to load them into the appropriate tab automatically

**Independent Test**: Drag any supported file onto the app window and verify the correct tab activates with the file loaded

### Implementation for User Story 1

- [x] T010 [P] [US1] Create gui/dnd_handler.py with DroppedFile dataclass per contracts/dnd_handler.py
- [x] T011 [P] [US1] Implement FILE_TYPE_MAP constant with extension-to-type mapping in gui/dnd_handler.py
- [x] T012 [US1] Implement DndHandler.detect_file_type() in gui/dnd_handler.py
- [x] T013 [US1] Implement DndHandler.map_to_tab() in gui/dnd_handler.py
- [x] T014 [US1] Implement DndHandler.process_drop() with path parsing and validation in gui/dnd_handler.py
- [x] T015 [US1] Implement multi-file drop handling (batch tab for same type, error for mixed) in gui/dnd_handler.py
- [x] T016 [US1] Add drop_target_register(DND_FILES) to main window in gui/app.py
- [x] T017 [US1] Implement on_drop callback handler in gui/app.py
- [x] T018 [US1] Implement tab switching logic based on DroppedFile.target_tab in gui/app.py
- [x] T019 [US1] Implement file path population into active tab's input field in gui/app.py
- [x] T020 [US1] Add user feedback for unsupported file types in gui/app.py
- [x] T021 [US1] Add "operation in progress" guard to reject drops during active operations in gui/app.py

**Checkpoint**: User Story 1 complete - drag-and-drop file loading works independently

---

## Phase 4: User Story 2 - Visual Timeline Trimmer (Priority: P2)

**Goal**: Users see an embedded video player with draggable timeline handles for visual trim point selection

**Independent Test**: Load a video in Trim tab, use timeline handles to select clip range, preview selection, and verify trim exports correct segment

### Implementation for User Story 2

- [ ] T022 [P] [US2] Create gui/video_trimmer.py with TrimSelection dataclass per contracts/video_trimmer.py
- [ ] T023 [P] [US2] Implement VLCPlayerState internal class in gui/video_trimmer.py
- [x] T024 [US2] Implement platform-specific VLC window embedding (hwnd/xwindow/nsobject) in gui/video_trimmer.py
- [x] T025 [US2] Implement VideoTrimmerWidget.load_video() with duration extraction in gui/video_trimmer.py
- [x] T026 [US2] Implement loading indicator and >4GB file size warning in gui/video_trimmer.py
- [x] T027 [US2] Implement timeline canvas with duration bar in gui/video_trimmer.py
- [x] T028 [US2] Implement draggable start handle (green) on timeline canvas in gui/video_trimmer.py
- [x] T029 [US2] Implement draggable end handle (red) on timeline canvas in gui/video_trimmer.py
- [x] T030 [US2] Implement handle constraint logic (end cannot be before start) in gui/video_trimmer.py
- [x] T031 [US2] Implement real-time timestamp display updates on handle drag in gui/video_trimmer.py
- [x] T032 [US2] Implement VideoTrimmerWidget.play() with segment looping in gui/video_trimmer.py
- [x] T033 [US2] Implement VideoTrimmerWidget.pause() and toggle_play() in gui/video_trimmer.py
- [x] T034 [US2] Implement mute/volume controls in gui/video_trimmer.py (detect audio track presence; disable mute button if no audio)
- [x] T035 [US2] Implement VideoTrimmerWidget.clear() and destroy() for cleanup in gui/video_trimmer.py
- [x] T036 [US2] Implement fallback text-input mode when VLC unavailable OR audio-only file loaded in gui/video_trimmer.py
- [x] T037 [US2] Implement create_video_trimmer() factory function in gui/video_trimmer.py
- [x] T038 [US2] Integrate VideoTrimmerWidget into Trim Media tab in gui/app.py
- [x] T039 [US2] Connect trimmer selection to existing trim function (pass start/end to ffmpeg) in gui/app.py
- [x] T040 [US2] Add error handling for corrupted video files in gui/app.py

**Checkpoint**: User Story 2 complete - visual trimmer works independently

---

## Phase 5: User Story 3 - Global Settings Panel (Priority: P3)

**Goal**: Users can configure persistent preferences (output folder, codec, theme) via a settings modal

**Independent Test**: Open Settings, change preferences, close and reopen app, verify settings persist

### Implementation for User Story 3

- [x] T041 [P] [US3] Create gui/settings_panel.py with SETTINGS_SECTIONS config per contracts/settings_panel.py
- [x] T042 [US3] Implement settings modal dialog frame in gui/settings_panel.py
- [x] T043 [US3] Implement folder picker field for output_folder in gui/settings_panel.py
- [x] T044 [US3] Implement dropdown field for default_codec in gui/settings_panel.py
- [x] T045 [US3] Implement dropdown field for theme_mode in gui/settings_panel.py
- [x] T046 [US3] Implement SettingsPanel.show() with form population in gui/settings_panel.py
- [x] T047 [US3] Implement SettingsPanel.hide() with save-on-close in gui/settings_panel.py
- [x] T048 [US3] Implement reset_to_defaults() with confirmation dialog in gui/settings_panel.py
- [x] T049 [US3] Implement create_settings_panel() factory function in gui/settings_panel.py
- [x] T050 [US3] Add gear icon button to status bar area in gui/app.py
- [x] T051 [US3] Wire gear button to open SettingsPanel in gui/app.py
- [x] T052 [US3] Load settings on app startup and apply (output folder, theme) in gui/app.py
- [x] T053 [US3] Apply theme_mode setting via existing theme.py integration in gui/app.py
- [x] T054 [US3] Apply default_codec setting to conversion operations in gui/app.py
- [x] T055 [US3] Apply output_folder setting as default in file save dialogs in gui/app.py
- [x] T056 [US3] Handle missing output_folder (deleted directory) with fallback prompt in gui/app.py

**Checkpoint**: User Story 3 complete - settings persist across restarts

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final refinements affecting multiple user stories

- [x] T057 [P] Verify cross-platform drag-drop on Windows, macOS, Linux
- [x] T058 [P] Verify VLC embedding on all platforms
- [x] T059 Add VLC not-installed warning dialog on startup with install instructions in gui/app.py
- [x] T060 Run quickstart.md manual testing checklist
- [x] T061 Update requirements.txt versions if needed after testing

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - User stories can proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational - No dependencies on US1 (uses different tab)
- **User Story 3 (P3)**: Can start after Foundational - No dependencies on US1/US2

### Within Each User Story

- Dataclasses/constants before logic
- Core logic before UI integration
- UI components before app.py integration

### Parallel Opportunities

**Phase 1 (Setup)**:
```
T002 (vlc_check.py) || T003 (core/settings.py stub)
```

**Phase 3 (US1)**:
```
T010 (DroppedFile dataclass) || T011 (FILE_TYPE_MAP)
```

**Phase 4 (US2)**:
```
T022 (TrimSelection dataclass) || T023 (VLCPlayerState)
```

**Cross-Story Parallelism** (if team capacity allows):
```
After Phase 2 complete:
  Developer A: Phase 3 (US1 - Drag-Drop)
  Developer B: Phase 4 (US2 - Trimmer)
  Developer C: Phase 5 (US3 - Settings)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Drag-Drop)
4. **STOP and VALIDATE**: Test drag-drop independently
5. Deploy/demo if ready - users can drag files to load them

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → **MVP!** (drag-drop works)
3. Add User Story 2 → Test independently → Visual trimming available
4. Add User Story 3 → Test independently → Settings persist
5. Each story adds value without breaking previous stories

### Suggested MVP Scope

**User Story 1 (Drag-Drop)** is the recommended MVP:
- Fundamental UX improvement
- Applies to all file types and tabs
- Provides immediate value
- Lower complexity than US2/US3
- 12 tasks (T010-T021)

---

## Summary

| Metric | Count |
|--------|-------|
| **Total Tasks** | 61 |
| **Setup Phase** | 3 |
| **Foundational Phase** | 6 |
| **User Story 1 (P1)** | 12 |
| **User Story 2 (P2)** | 19 |
| **User Story 3 (P3)** | 16 |
| **Polish Phase** | 5 |
| **Parallel Opportunities** | 8 explicitly marked [P] |

### Files to Create/Modify

| File | Action | User Story |
|------|--------|------------|
| requirements.txt | MODIFY | Setup |
| utils/vlc_check.py | CREATE | Setup/US2 |
| core/settings.py | CREATE | Foundational/US3 |
| gui/dnd_handler.py | CREATE | US1 |
| gui/video_trimmer.py | CREATE | US2 |
| gui/settings_panel.py | CREATE | US3 |
| gui/app.py | MODIFY | US1, US2, US3 |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Manual testing checklist available in quickstart.md
