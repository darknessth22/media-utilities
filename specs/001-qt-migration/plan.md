# Implementation Plan: PySide6 GUI Migration

**Branch**: `001-qt-migration` | **Date**: 2026-03-02 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-qt-migration/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Migrate the GUI layer from `tkinter` to `PySide6` to achieve a modern, "Enterprise Standard" aesthetic with a custom slate-blue design system, native OS integration, and improved asynchronous task handling, while preserving 100% of existing media processing capabilities.

## Technical Context

**Language/Version**: Python 3.10+ (3.12 recommended)
**Primary Dependencies**: PySide6, PySide6.QtMultimedia, yt-dlp, FFmpeg, Pillow, PyMuPDF, python-docx, openpyxl, python-pptx
**Storage**: Local JSON (History Data Source)
**Testing**: `unittest` for backend + Manual UI Testing (resolved in Phase 0)
**Target Platform**: Windows, macOS, Linux (Desktop Application)
**Project Type**: Desktop UI Application
**Performance Goals**: Memory footprint and startup time within 15% of legacy Tkinter version, UI thread responsiveness during long tasks.
**Constraints**: Framework swap must not introduce `tkinter` traces; PyInstaller build must be updated; no new media features.
**Scale/Scope**: Replace all UI components, add custom title bar, sidebar navigation, dark/light themes via QSS, drag-and-drop, system tray.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Modular Architecture**: PASS. The migration will replace `gui/` contents while bridging to existing `core/` functions without polluting them with UI logic.
- **II. Cross-Platform Compatibility**: PASS. PySide6 provides native cross-platform support. File paths and asset loading will remain platform-agnostic.
- **III. User Experience First**: PASS. Migration introduces modern UI with `QThread` for async non-blocking operations and accessible feedback.
- **IV. Quality & Testing**: PASS. Will rely on manual testing for UI layer against Acceptance Scenarios, and `unittest` for any required automated regressions.
- **V. Simplicity & YAGNI**: PASS. Explicitly excludes speculative features like i18n and auto-updates, focusing squarely on the UI migration.

## Project Structure

### Documentation (this feature)

```text
specs/001-qt-migration/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
core/
├── settings.py
├── tray.py
└── (existing core modules)
gui/
├── app.py (MainWindow)
├── theme.py
├── dnd_handler.py
├── video_trimmer.py
└── (other PySide6 UI views/components)
assets/
└── icons/ (SVG)
media_util_gui.py
```

**Structure Decision**: Reusing existing modular structure with a dedicated `gui/` package and `core/` package inside the root directory. This aligns with Constitution Principle I.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
