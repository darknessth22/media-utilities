# Implementation Plan: [FEATURE]

**Branch**: `001-settings-theme-icons` | **Date**: 2026-03-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/001-settings-theme-icons/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Replace the existing text-based "Settings" link and implicit theme toggle on the bottom right of the main GUI window with explicit, graphical icons placed in the Top-Right corner of the window. This involves updating the Tkinter layout in the main GUI module and handling theme state persistence/toggling using visual indicators (e.g., sun/moon icons).

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Python 3.10+
**Primary Dependencies**: tkinter (standard library), existing `core` modules for settings management.
**Storage**: N/A for this specific UI change beyond the existing application settings file (`settings.json`).
**Testing**: Manual GUI testing for visual accuracy; potential unit tests for state toggle logic in pytest.
**Target Platform**: Desktop (Windows/macOS/Linux via Tkinter).
**Project Type**: Desktop UI Utility App.
**Performance Goals**: N/A (UI update, should be instantaneous).
**Constraints**: Must adhere to core principle of modularity (GUI separated from core logic). Must use standard tkinter or minimal libraries to avoid adding new external dependencies for simple icons.
**Scale/Scope**: Single UI screen update, mostly restricted to layout adjustments.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Modular Architecture**: Changes will be restricted to the presentation layer (`gui/` or main script) and any settings state logic in `core/`.
- [x] **Cross-Platform Compatibility**: Using standard `tkinter` UI components and cross-platform icon handling (no platform-specific pathing for icons).
- [x] **User Experience First**: Icons will include hover tooltips to ensure clarity.
- [x] **Quality & Testing**: Added manual test steps to ensure visual layout across OS if possible.
- [x] **Simplicity & YAGNI**: No over-engineering; simple Tkinter Button or Label widgets with image attachments. No new heavy dependencies introduced.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
### Source Code (repository root)

```text
gui/
└── [main GUI modules where the top frame/header is defined]
assets/
└── [where the icon images will be stored, e.g. sun.png, moon.png, settings.png]
```

**Structure Decision**: The feature primarily impacts the root UI or a specific `gui` module. We need to identify exactly where the main window layout is constructed (e.g., `gui/` directory or `media_util_gui.py`). We will also need a place to store the icon assets (e.g., a new `assets/icons/` directory if one does not exist, or within `gui/assets/`).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
