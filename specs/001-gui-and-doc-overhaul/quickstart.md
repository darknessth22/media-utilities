# Quickstart: GUI Redesign & Document Conversion Fidelity

**Branch**: `001-gui-and-doc-overhaul`

## Prerequisites

- Python 3.10+ (3.12 recommended)
- FFmpeg on PATH
- LibreOffice installed (for DOCX-to-PDF on Linux) or Microsoft Word (Windows/macOS)

## Setup

```bash
git checkout 001-gui-and-doc-overhaul
pip install -r requirements.txt
```

New dependencies added by this feature:
```
ttkbootstrap>=1.10.0
darkdetect>=0.8.0
docx2pdf>=0.1.8
```

## Running the Application

```bash
python main.py
```

The application auto-detects OS light/dark preference and applies the
corresponding theme. Use the theme toggle in the toolbar to override.

## Key Files to Modify

### GUI Layer (`gui/`)
- `gui/app.py` — Main GUI class; migrate from raw ttk to ttkbootstrap
- `gui/theme.py` — (NEW) Theme management: OS detection, toggle, persistence

### Core Logic (`core/`)
- `core/document.py` — Document conversion; rewrite PDF-to-DOCX extraction
  with structured block extraction (headings, tables, lists, images)

### Utils (`utils/`)
- `utils/deps.py` — Add ttkbootstrap, darkdetect, docx2pdf to dependency checks

### Entry Point
- `main.py` — Update to use `ttkbootstrap.Window` instead of `tkinter.Tk`

## Testing

### Manual Test: GUI Theme
1. Launch app → verify theme matches OS setting
2. Toggle theme → verify all widgets update consistently
3. Restart app → verify preference persisted

### Manual Test: PDF-to-DOCX
1. Convert a PDF with headings, bold/italic, a table, a list, and an image
2. Open resulting DOCX in Word/LibreOffice
3. Verify: headings use Word heading styles, bold/italic preserved,
   table has correct rows/columns, list uses native bullets, image placed

### Manual Test: DOCX-to-PDF
1. Convert a DOCX with formatting, tables, and images
2. Open resulting PDF
3. Verify: text wraps within margins, tables rendered, images placed

### Manual Test: Progress & Summary
1. Convert a multi-page PDF (20+ pages)
2. Verify progress bar shows page N of M
3. Verify completion summary shows element counts
