# media-utilities Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-02-19

## Active Technologies
- Python 3.10+ (3.12 recommended) + ttkbootstrap, python-vlc, tkinterdnd2, darkdetect (004-drag-trimmer-settings)
- JSON config file in platform app data directory (004-drag-trimmer-settings)

- Python 3.12 (3.10+ compatible) + ttkbootstrap (GUI theming), darkdetect (OS theme detection), PyMuPDF/fitz (PDF extraction), python-docx (DOCX generation), docx2pdf (DOCX→PDF on Windows/macOS), LibreOffice headless (DOCX→PDF on Linux) (001-gui-and-doc-overhaul)

## Project Structure

```text
src/
tests/
```

## Commands

cd src; pytest; ruff check .

## Code Style

Python 3.12 (3.10+ compatible): Follow standard conventions

## Recent Changes
- 004-drag-trimmer-settings: Added Python 3.10+ (3.12 recommended) + ttkbootstrap, python-vlc, tkinterdnd2, darkdetect

- 001-gui-and-doc-overhaul: Added Python 3.12 (3.10+ compatible) + ttkbootstrap (GUI theming), darkdetect (OS theme detection), PyMuPDF/fitz (PDF extraction), python-docx (DOCX generation), docx2pdf (DOCX→PDF on Windows/macOS), LibreOffice headless (DOCX→PDF on Linux)

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
