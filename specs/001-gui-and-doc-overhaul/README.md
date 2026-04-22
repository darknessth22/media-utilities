# Phase 001 — GUI Redesign & Document Conversion Fidelity

**Branch**: `001-gui-and-doc-overhaul`
**Status**: Draft | **Created**: 2026-02-19

## Goal

Replace the raw tkinter prototype with a modern, themed GUI and fix document conversion to preserve formatting — not just dump raw text.

## What This Phase Delivers

### Modern GUI (`ttkbootstrap`)
- Consistent visual hierarchy across all tabs (spacing, typography, color)
- Auto-detect OS light/dark theme at startup; toggle override button in toolbar
- Primary action buttons visually distinct from secondary controls
- Placeholder text on all input fields
- Minimum window size enforced to prevent layout breakage

### PDF → DOCX (Format-Preserving)
- Headings, bold, italic, and font sizes preserved as Word styles
- Bullet and numbered lists converted to native Word list formatting
- Simple tables (uniform rows/cols) converted to Word tables
- Embedded images extracted and placed near original position
- Scanned/image-only pages embedded as full-page images
- Page-level progress bar + completion summary

### DOCX → PDF (High-Fidelity)
- Uses `docx2pdf` (LibreOffice/Word backend) for native rendering
- Text wraps within margins; bold/italic/heading sizes preserved
- Tables, images, and lists rendered natively by the backend engine
- Cancellable mid-conversion with partial file cleanup

## Key Dependencies
- `ttkbootstrap` — modern tkinter theming
- `PyMuPDF (fitz)` — PDF extraction
- `python-docx` — DOCX generation
- `docx2pdf` — DOCX→PDF via LibreOffice/Word (runtime dependency)

## Acceptance Criteria (abridged)
- First-time user completes a conversion in <60 s without docs
- PDF→DOCX preserves ≥80% of formatting elements
- DOCX→PDF has no clipped/overflowing text on any page
- All existing features (download, batch convert, trim) unchanged

## Full Spec
See [`spec.md`](spec.md) for complete user stories, requirements, and edge cases.
