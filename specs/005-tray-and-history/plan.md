# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]
**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Implement a background running feature using a system tray icon, cross-platform native interactive notifications using `desktop-notifier`, and a new "History" tab in the GUI to track up to 10 recent downloads/conversions with open/play functionality. 

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Python 3.10+
**Primary Dependencies**: tkinter, pystray, Pillow, desktop-notifier
**Storage**: Local JSON file (`history.json`)
**Testing**: Manual GUI testing for tray and notifications; pytest for history model logic
**Target Platform**: Windows, macOS, Linux desktop
**Project Type**: Desktop UI Utility
**Performance Goals**: History tab loads in < 500ms
**Constraints**: Requires OS-level notification permissions
**Scale/Scope**: Limit history to 10 items. Single user local app.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Modular Architecture**: System tray logic will live in `core/tray.py`, notifications in `core/notifications.py`, and history model in `core/history.py`. The GUI tab will live in `gui/history_tab.py`.
- [x] **Cross-Platform**: `pystray` and `desktop-notifier` both abstract away Windows/macOS/Linux differences.
- [x] **Dependencies**: `pystray`, `Pillow`, and `desktop-notifier` are required for the new feature and will be pinned in `requirements.txt`.

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
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
core/
├── tray.py                # System tray integration
├── notifications.py       # Native OS notifications
└── history/
    ├── manager.py         # History persistence and retrieval
    └── models.py          # History item dataclass

gui/
├── main_window.py         # (Modified) Add tab, override close (X) to minimize
└── tabs/
    └── history_tab.py     # New history UI component
```

**Structure Decision**: Integrated as new modules within the existing `core/` and `gui/` directory structure, following the Modular Architecture principle.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
