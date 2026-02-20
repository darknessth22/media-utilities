# Implementation Plan: GUI Redesign & Document Conversion Fidelity

**Branch**: `001-gui-and-doc-overhaul` | **Date**: 2026-02-19 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-gui-and-doc-overhaul/spec.md`

## Summary

Modernize the Media Utility GUI using `ttkbootstrap` with OS-aware dark/light theming and overhaul the document conversion pipeline. PDF-to-DOCX conversion will use PyMuPDF structured extraction (`get_text("dict")` + `find_tables()`) mapped to python-docx elements for high-fidelity heading, table, list, and image preservation. DOCX-to-PDF conversion will use a cross-platform strategy: `docx2pdf` (Windows/macOS with Word) with LibreOffice headless fallback (Linux). Both directions gain page-level progress reporting and a completion summary of preserved/skipped elements.

## Technical Context

**Language/Version**: Python 3.12 (3.10+ compatible)
**Primary Dependencies**: ttkbootstrap (GUI theming), darkdetect (OS theme detection), PyMuPDF/fitz (PDF extraction), python-docx (DOCX generation), docx2pdf (DOCX→PDF on Windows/macOS), LibreOffice headless (DOCX→PDF on Linux)
**Storage**: Local filesystem; config at `~/.media_utility.json`
**Testing**: Manual testing with sample documents; existing test_executable.py for build validation
**Target Platform**: Windows, macOS, Linux (desktop)
**Project Type**: Single desktop application
**Performance Goals**: PDF-to-DOCX conversion <=2 seconds per page; GUI theme switch <200ms
**Constraints**: Documents up to 200 pages fully supported; existing features must remain functional
**Scale/Scope**: Single-user desktop app; 5 GUI tabs; ~800 lines GUI code, ~700 lines document conversion code

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Research Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Modular Architecture | PASS | GUI changes in `gui/`, conversion in `core/document.py`, new theme module in `gui/theme.py`. Domain logic stays separated from presentation. |
| II. Cross-Platform Compatibility | PASS (with note) | ttkbootstrap and darkdetect are cross-platform. DOCX-to-PDF requires platform-aware routing (docx2pdf for Windows/macOS, LibreOffice for Linux). Spec originally stated `python-docx2pdf` — research revealed it only supports Windows/macOS with Word. Plan adds LibreOffice fallback. |
| III. User Experience First | PASS | Feature is explicitly UX-focused: modern theming, progress feedback, completion summaries. |
| IV. Quality & Testing | PASS | Manual test plan defined in quickstart.md. Sample document testing for conversion fidelity. |
| V. Simplicity & YAGNI | PASS | Using established libraries (ttkbootstrap, darkdetect) rather than building custom. No speculative features. |

### Post-Design Re-Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Modular Architecture | PASS | New file `gui/theme.py` for theme management. `core/document.py` enhanced in-place. No monolithic additions. |
| II. Cross-Platform Compatibility | PASS | Platform-aware converter detection with graceful fallback chain. `darkdetect` handles OS detection cross-platform. |
| III. User Experience First | PASS | Page-level progress for PDF-to-DOCX. Indeterminate progress for DOCX-to-PDF (backend limitation). Completion summary with element counts. |
| IV. Quality & Testing | PASS | Contracts define error handling for all failure modes. |
| V. Simplicity & YAGNI | PASS | Three new dependencies (ttkbootstrap, darkdetect, docx2pdf) each justified by concrete spec requirements. No unnecessary abstractions. |

## Project Structure

### Documentation (this feature)

```text
specs/001-gui-and-doc-overhaul/
├── plan.md              # This file
├── research.md          # Phase 0: ttkbootstrap, PyMuPDF extraction, docx2pdf findings
├── data-model.md        # Phase 1: DocumentBlock, SpanInfo, ConversionSummary, ThemeConfig
├── quickstart.md        # Phase 1: Setup, running, manual test procedures
├── contracts/
│   ├── document-conversion.md  # convert_document() API contract
│   └── gui-theme.md            # ThemeManager API contract
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
core/
├── __init__.py
├── converter.py         # Image/media conversion (existing, unchanged)
├── document.py          # Document conversion (MODIFY: structured PDF extraction,
│                        #   platform-aware DOCX-to-PDF, progress callbacks, summaries)
├── downloader.py        # Media downloading (existing, unchanged)
└── trimmer.py           # Media trimming (existing, unchanged)

gui/
├── __init__.py
├── app.py               # Main GUI class (MODIFY: migrate to ttkbootstrap,
│                        #   bootstyle buttons, placeholder text, progress display,
│                        #   conversion summary, minimum window size)
└── theme.py             # NEW: ThemeManager — OS detection, toggle, persistence

utils/
├── __init__.py
├── deps.py              # Dependency checking (MODIFY: add ttkbootstrap, darkdetect,
│                        #   docx2pdf, LibreOffice detection)
└── ffmpeg.py            # FFmpeg binary location (existing, unchanged)

main.py                  # Entry point (MODIFY: use ttkbootstrap.Window, integrate ThemeManager)
requirements.txt         # Dependencies (MODIFY: add ttkbootstrap, darkdetect, docx2pdf)
build_executable.py      # Build system (MODIFY: add new dependencies to PyInstaller config)
media_util_gui.spec      # PyInstaller spec (MODIFY: add hidden imports for new deps)
```

**Structure Decision**: Existing modular structure (`core/`, `gui/`, `utils/`) is maintained. One new file added (`gui/theme.py`). All other changes are modifications to existing files. This aligns with Constitution Principle I (modular architecture) and the spec requirement FR-013 (enhancement, not rewrite).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| New dependency: `ttkbootstrap` | Required for modern themed GUI with built-in light/dark support | Custom `ttk.Style` definitions would require 500+ lines of manual theme code with no dark mode auto-switching |
| New dependency: `darkdetect` | Required for FR-004a (auto-detect OS theme preference) | Manual registry/plist reading would be platform-specific code, violating Principle II |
| New dependency: `docx2pdf` | Required for high-fidelity DOCX-to-PDF on Windows/macOS | Manual `reportlab`/`fpdf2` rendering would require building a complete layout engine |
| Platform-aware conversion routing | Cross-platform DOCX-to-PDF support | `docx2pdf` alone doesn't support Linux; single-backend approach violates Principle II |
