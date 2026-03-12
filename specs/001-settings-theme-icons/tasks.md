---
description: "Task list for Settings and Theme Icons feature"
---

# Tasks: Settings and Theme Icons

**Input**: Design documents from `/specs/001-settings-theme-icons/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story. Tests are not explicitly requested but are outlined as manual steps in the plan.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Identify the target lines in `gui/app.py` for UI injection (Top-Right corner layout preparation).
- [x] T002 Identify or create the `assets/icons/` directory.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Acquire or generate `sun.png` in `assets/icons/`.
- [x] T004 Acquire or generate `moon.png` in `assets/icons/`.
- [x] T005 Acquire or generate `settings.png` in `assets/icons/`.
- [x] T006 Implement the new `header_frame` at the top of the root window in `gui/app.py`.
- [x] T021 Move the application title or existing top-level branding into the left side of `header_frame` in `gui/app.py`.

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Toggle Theme via Icon (Priority: P1) 🎯 MVP

**Goal**: As a user, I want to click an icon to toggle between light and dark mode so that the interface feels more modern and takes up less screen space than a text button.

**Independent Test**: Can be fully tested by clicking the new theme icon and verifying the application theme changes immediately.

### Implementation for User Story 1

- [x] T007 [P] [US1] Inject a `ttk.Button` or `tk.Button` into the right side of `header_frame` in `gui/app.py` for the theme toggle.
- [x] T008 [US1] Load `sun.png` and `moon.png` using `PIL.ImageTk.PhotoImage` in `gui/app.py`.
- [x] T009 [US1] Connect the theme toggle button to `self._toggle_theme` in `gui/app.py`.
- [x] T010 [P] [US1] Add a ToolTip to the theme toggle button ("Toggle Theme") in `gui/app.py`.
- [x] T011 [US1] Update `self._toggle_theme` in `gui/app.py` to change the button image depending on the mode (Sun for light, Moon for dark).
- [x] T020 [US1] Set the initial correct icon image in `gui/app.py` `__init__` based on the loaded `self.settings.theme_mode`.
- [x] T012 [US1] Remove the old text-based `self.theme_btn` from the bottom `status_frame` in `gui/app.py`.

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Access Settings via Icon (Priority: P1)

**Goal**: As a user, I want to access the Settings menu by clicking a gear/settings icon rather than a text link, so that the main interface is cleaner.

**Independent Test**: Can be fully tested by clicking the settings icon and verifying the Settings panel or dialog opens correctly.

### Implementation for User Story 2

- [x] T013 [P] [US2] Inject a `ttk.Button` or `tk.Button` into the right side of `header_frame` in `gui/app.py` for settings access.
- [x] T014 [US2] Load `settings.png` using `PIL.ImageTk.PhotoImage` in `gui/app.py`.
- [x] T015 [US2] Connect the settings button to `self._open_settings` in `gui/app.py`.
- [x] T016 [P] [US2] Add a ToolTip to the settings button ("Settings") in `gui/app.py`.
- [x] T017 [US2] Remove the old text-based `self.settings_btn` from the bottom `status_frame` in `gui/app.py`.

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T018 Run `quickstart.md` validation to ensure the new icons work as expected.
- [x] T019 Visually verify icon scaling across different OS or DPI settings if possible.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational (Phase 2) - Can be implemented independently of US1 since they are separate buttons.

### Parallel Opportunities

- Icon acquisition (T003, T004, T005) can run in parallel.
- Tooltips (T010, T016) can be added in parallel with core button logic once the buttons are defined.
