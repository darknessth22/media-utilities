# Tasks: PySide6 GUI Migration

**Input**: Design documents from `/specs/001-qt-migration/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: Manual tests will be conducted based on User Scenarios in spec.md. Unit tests will be utilized for backward compatibility of backend code (as resolved in research.md).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Initialize Python environment and update dependencies for PySide6 in `requirements.txt`
- [x] T002 Generate or acquire SVG icon assets for the navigation menu in `assets/icons/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Update `UserSettings` dataclass to include `quit_on_close` and migrate in `core/settings.py`
- [x] T004 Implement `DARK_THEME_QSS` and `LIGHT_THEME_QSS` stylesheets strings in `gui/theme.py`
- [x] T005 [P] Implement OS theme detection via `QGuiApplication.styleHints().colorScheme()` in `gui/theme.py`
- [x] T006 Create PySide6 `QThread` worker class for handling async backend operations without blocking UI, including signal-based cancellation support

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Launch Modernized Application (Priority: P1) 🎯 MVP

**Goal**: As a user, I want the application to launch as a standard, visually appealing desktop application so that it feels professional and trustworthy.

**Independent Test**: Can be fully tested by launching the app and verifying the window frame, application icon (logo), and initial layout visually match the new modern (blue) design system.

### Implementation for User Story 1

- [x] T007 [US1] Set up main application skeleton `MainWindow` in `gui/app.py` including `QStatusBar` (shows current operation state or "Ready")
- [x] T008 [US1] Implement frameless title bar with `QSizeGrip` and custom drag controls in `gui/app.py`
- [x] T009 [US1] Build the fixed 180px left sidebar with custom nav items (SVGs + text) in `gui/app.py`
- [x] T010 [US1] Create the main content area (tabbed routing) and primary action button styling in `gui/app.py`
- [x] T011 [US1] Create the new **Settings** tab UI with controls for: "Quit on close" toggle, dark/light theme toggle, and default file paths configuration (FR-009).

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Perform Media Operations (Download/Convert/Trim) (Priority: P1)

**Goal**: As a user, I want to perform all essential media operations using the new interface without any loss of functionality.

**Independent Test**: Can be fully tested by navigating through the main tabs and executing a standard operation to ensure the backend integration is intact.

### Implementation for User Story 2

- [x] T012 [P] [US2] Reimplement Download tab UI layout and bind to core downloader via worker thread
- [x] T013 [P] [US2] Reimplement Convert/Batch Convert tabs and bind to core converter via worker thread
- [x] T014 [US2] Replace VLC video trimmer with PySide6 `QMediaPlayer` + `QVideoWidget` in `gui/tabs/trim_section.py`
- [x] T015 [P] [US2] Reimplement Document Convert tab UI and bind to core document functions
- [x] T016 [US2] Reimplement History tab using `QAbstractTableModel` connected to local JSON store
- [x] T017 [US2] Port Drag-and-Drop handler using `QDropEvent.mimeData().urls()` in `gui/dnd_handler.py`

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - System Tray & Notifications (Priority: P2)

**Goal**: As a user, I want the application to minimize to the system tray and provide native notifications so that it runs unobtrusively in the background.

**Independent Test**: Can be tested by minimizing the app to the tray and triggering a background download completion to see the notification.

### Implementation for User Story 3

- [x] T018 [P] [US3] Replace `pystray` with `QSystemTrayIcon` + `QMenu` in `core/tray.py`
- [x] T019 [US3] Implement native desktop notifications for task completion in `core/tray.py`
- [x] T020 [US3] Wire main window close event to obey `quit_on_close` user setting in `gui/app.py`

**Checkpoint**: All user stories should now be independently functional

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T021 [P] Remove all remaining traces of `tkinter`, `ttkbootstrap`, `darkdetect`, `python-vlc`, and `pystray`
- [x] T022 Overhaul `media_util_gui.py` to instantiate and execute the new PySide6 `QApplication`; update startup dependency validation to check for PySide6 instead of tkinter
- [x] T023 [P] Update PyInstaller spec `media_util_gui.spec` to include PySide6/QtMultimedia and exclude Tkinter
- [x] T024 Test executable build pipeline by running `build_executable.py`
- [x] T025 Update `README.md` and `SETUP.md` to reflect PySide6 migration, new dependencies, and updated setup steps
- [x] T026 Verify CLI entry point (`media_util_gui.py`) remains functional for scripting and automation use cases
- [x] T027 Benchmark startup time and memory usage vs. legacy Tkinter version to verify SC-004 (within 15%)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - Sequential delivery: P1 (US1) → P1 (US2) → P2 (US3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1**: Core shell; must be established first.
- **User Story 2**: Depends on User Story 1 (tab framework).
- **User Story 3**: Depends on User Story 1 and 2 (tray requires window and background tasks).

### Parallel Opportunities

- Foundation: QSS (T004), theme detection (T005), and worker base (T006) can be developed concurrently.
- User Story 2: Individual tabs (Download, Convert, Document) can be migrated in parallel.
- Polish: Cleanup of requirements (T021) and PyInstaller configurations (T023) can run in parallel.

---

## Parallel Example: User Story 2

```bash
# Tabs can be migrated independently given the worker framework is complete:
Task: "Reimplement Download tab UI layout and bind to core downloader via worker thread"
Task: "Reimplement Convert/Batch Convert tabs and bind to core converter via worker thread"
Task: "Reimplement Document Convert tab UI and bind to core document functions"
```

## Implementation Strategy

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test custom window borders and active theming → Deploy/Demo (MVP!)
3. Add User Story 2 → Test media processing features (download/convert/trim) → Deploy/Demo
4. Add User Story 3 → Test background notifications
5. Each story adds value without breaking previous stories 
