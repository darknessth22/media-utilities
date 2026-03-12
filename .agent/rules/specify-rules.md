# media-utilities Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-02-28

## Active Technologies
- Python 3.10+ + tkinter (standard library), existing `core` modules for settings management. (001-settings-theme-icons)
- N/A for this specific UI change beyond the existing application settings file (`settings.json`). (001-settings-theme-icons)
- Python 3.10+ (3.11+ recommended) + PySide6, PySide6.QtMultimedia, yt-dlp, FFmpeg, Pillow, PyMuPDF, python-docx, openpyxl, python-pptx (001-qt-migration)
- Local JSON (History Data Source) (001-qt-migration)

- Python 3.10+ + tkinter, pystray, Pillow, desktop-notifier (005-tray-and-history)

## Project Structure

```text
src/
tests/
```

## Commands

cd src; pytest; ruff check .

## Code Style

Python 3.10+: Follow standard conventions

## Recent Changes
- 001-qt-migration: Added Python 3.10+ (3.11+ recommended) + PySide6, PySide6.QtMultimedia, yt-dlp, FFmpeg, Pillow, PyMuPDF, python-docx, openpyxl, python-pptx
- 001-qt-migration: Added Python 3.10+ (3.11+ recommended) + PySide6, PySide6.QtMultimedia, yt-dlp, FFmpeg, Pillow, PyMuPDF, python-docx, openpyxl, python-pptx
- 001-settings-theme-icons: Added Python 3.10+ + tkinter (standard library), existing `core` modules for settings management.


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
