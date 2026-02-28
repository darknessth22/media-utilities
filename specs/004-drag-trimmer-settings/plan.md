# Implementation Plan: Drag-Drop, Rich Trimmer & Global Settings

**Branch**: `004-drag-trimmer-settings` | **Date**: 2026-02-28 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-drag-trimmer-settings/spec.md`

## Summary

This feature adds three user experience enhancements to Media Utilities:
1. **Drag-and-Drop** - Users can drag files onto the app window to load them into the appropriate tab
2. **Visual Timeline Trimmer** - Embedded video player with draggable timeline handles for precise trimming
3. **Global Settings Panel** - Persistent configuration for output folder, codec preferences, and theme

Technical approach: Use tkinter's native DnD support via `tkinterdnd2`, embed VLC player via `python-vlc` for video preview, and store settings as JSON in platform-specific app data directories.

## Technical Context

**Language/Version**: Python 3.10+ (3.12 recommended)
**Primary Dependencies**: ttkbootstrap, python-vlc, tkinterdnd2, darkdetect
**Storage**: JSON config file in platform app data directory
**Testing**: Manual testing (pytest available for unit tests)
**Target Platform**: Windows, macOS, Linux (cross-platform desktop)
**Project Type**: Desktop GUI application
**Performance Goals**: File load via drag <2s, video preview start <2s
**Constraints**: VLC must be installed on system, files up to 4GB supported
**Scale/Scope**: Single-user desktop application

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Modular Architecture | PASS | New modules: `gui/settings.py`, `gui/trimmer_widget.py`, `gui/dnd_handler.py`. Logic in `core/`, UI in `gui/`. |
| II. Cross-Platform Compatibility | PASS | tkinterdnd2 is cross-platform, VLC available on all platforms, config paths use platform detection. |
| III. User Experience First | PASS | All features accessible via GUI with progress feedback. Drag-drop provides immediate feedback. |
| IV. Quality & Testing | PASS | Manual testing defined in spec. Regression tests for critical paths. |
| V. Simplicity & YAGNI | PASS | Direct implementation, no speculative abstractions. Settings schema is minimal. |

**Gate Result**: PASSED - No violations detected.

## Project Structure

### Documentation (this feature)

```text
specs/004-drag-trimmer-settings/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (internal API contracts)
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
core/
├── __init__.py
├── converter.py         # Image conversion (existing)
├── document.py          # Document conversion (existing)
├── downloader.py        # Media download (existing)
├── trimmer.py           # Media trimming (existing)
└── settings.py          # NEW: Settings persistence logic

gui/
├── __init__.py
├── app.py               # MODIFY: Main app window (add DnD, settings button)
├── theme.py             # Theme management (existing)
├── dnd_handler.py       # NEW: Drag-and-drop handling logic
├── settings_panel.py    # NEW: Settings modal UI
└── video_trimmer.py     # NEW: VLC-based video player widget

utils/
├── __init__.py
├── deps.py              # Dependency checking (existing)
├── ffmpeg.py            # FFmpeg utilities (existing)
└── vlc_check.py         # NEW: VLC availability detection

tests/
├── test_settings.py     # NEW: Settings persistence tests
└── test_dnd.py          # NEW: Drag-drop file type detection tests
```

**Structure Decision**: Follows existing modular layout. New functionality added as separate modules under `gui/` and `core/`. No new top-level directories needed.

## Complexity Tracking

No constitution violations requiring justification.
