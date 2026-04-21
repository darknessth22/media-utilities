# Implementation Plan: Download Preview & Rich Progress

**Branch**: `009-download-preview-progress` | **Date**: 2026-04-20 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/009-download-preview-progress/spec.md`

## Summary

Add rich progress display (%, speed, ETA) to all download paths and an embedded video preview player with draggable start/end markers in the download tab. No new dependencies — uses yt-dlp progress hooks (already wired but unused), the existing `Worker.signals.progress` signal (already declared), and PySide6.QtMultimedia (already used in the trim tab).

## Technical Context

**Language/Version**: Python 3.12 (3.10+ compatible)  
**Primary Dependencies**: PySide6 (GUI + QtMultimedia for preview), yt-dlp (progress hooks + stream extraction), urllib stdlib (HTTP fallback progress), playwright (existing browser intercept — no change to intercept path for progress)  
**Storage**: N/A — no schema changes; download history JSON unchanged  
**Testing**: pytest (existing); manual UI testing required per constitution  
**Target Platform**: Windows / macOS / Linux desktop  
**Project Type**: Desktop application  
**Performance Goals**: Progress bar updates ≥ 1 Hz; speed label within 2 s of download start; preview player loads stream within 5 s on a typical broadband connection  
**Constraints**: No new pip dependencies; `QMediaPlayer` streams the preview URL directly (no temp file); HTTP fallback must track `Content-Length` for ETA  
**Scale/Scope**: Single-user desktop; one download at a time

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Modular Architecture | ✅ PASS | Changes stay in `core/downloader.py` (domain logic) and `gui/tabs/download_section.py` (UI). No new modules required; no GUI→core reverse dependency. |
| II. Cross-Platform | ✅ PASS | `QMediaPlayer` + `QVideoWidget` are cross-platform. No platform ifdefs added. |
| III. UX First | ✅ PASS | Feature IS the UX improvement. Progress, preview, cancel all remain accessible. |
| IV. Quality & Testing | ✅ PASS | Manual test plan provided in spec; regression test for existing download paths required. |
| V. YAGNI | ✅ PASS | Reusing `Worker.signals.progress` (already declared), existing QMediaPlayer pattern from trim tab, existing `QSlider` scrubber. No speculative abstractions. |

**No violations. Proceed.**

## Project Structure

### Documentation (this feature)

```text
specs/009-download-preview-progress/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/
│   └── internal-api.md  ← Phase 1 output (function signatures)
└── tasks.md             ← Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (files touched)

```text
core/
└── downloader.py          # add progress_cb param; enrich _progress_hook; chunked HTTP fallback

gui/
├── worker.py              # Worker.signals.progress already declared — no change needed
└── tabs/
    └── download_section.py  # add preview player card; rich progress UI; preview load logic
```

**Structure Decision**: Single-project, existing layout. All changes are extensions to existing modules. No new files in `core/` or `gui/` — the feature does not warrant a new domain module.

## Complexity Tracking

> No constitution violations — table not required.
