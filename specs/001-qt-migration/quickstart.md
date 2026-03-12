# Quickstart: PyQt6 GUI Migration

This guide outlines how to bootstrap and run the new PySide6-based interface for Media Utilities.

## Prerequisites
- Python 3.10+
- Dependencies installed from `requirements.txt` (includes PySide6, PySide6.QtMultimedia)
- FFmpeg installed and available on system PATH

## Running the App

```bash
# 1. Activate your virtual environment (if applicable)
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# 2. Run the new PyQt6 entry point
python media_util_gui.py
```

## Development Hot-Reloading

Since the UI relies heavily on QSS (Qt Style Sheets) for the `DARK_THEME_QSS` and `LIGHT_THEME_QSS` tokens:
1. Make changes to the QSS strings in `gui/theme.py`.
2. To test, simply restart the application or toggle the theme in the Settings tab to trigger a style re-polish.

## Building the Executable (Windows)

The build pipeline relies on PyInstaller.

```powershell
python build_executable.py
```
*Note: Ensure `media_util_gui.spec` has been updated to include PySide6 imports and exclude `tkinter` dependencies.*
