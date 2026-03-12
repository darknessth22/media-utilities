# media-utilities Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-11

## Active Technologies
- Python 3.10+ (3.12 recommended) + **PySide6** (GUI), **QMediaPlayer/QVideoWidget** (video trimmer), **QSystemTrayIcon** (system tray), **QGuiApplication.styleHints().colorScheme()** (OS theme detection), **QDropEvent.mimeData().urls()** (drag-and-drop)
- JSON config file in platform app data directory
- PyMuPDF/fitz (PDF extraction), python-docx (DOCX generation), docx2pdf (DOCX→PDF on Windows/macOS), LibreOffice headless (DOCX→PDF on Linux)

## Project Structure

```text
media-utilities/
├── main.py                    # Entry point
├── media_util_gui.py          # Legacy entry point (delegates to main.py)
├── build_executable.py        # PyInstaller build script
├── media_util_gui.spec        # PyInstaller spec
├── gui/
│   ├── app.py                 # MainWindow (frameless, sidebar nav)
│   ├── theme.py               # ThemeManager + QSS stylesheets
│   ├── worker.py              # Worker(QThread) for async operations
│   ├── dnd_handler.py         # Drag-and-drop via QDropEvent.mimeData().urls()
│   └── tabs/
│       ├── download_section.py
│       ├── convert_section.py
│       ├── trim_section.py
│       ├── document_section.py
│       ├── history_section.py
│       └── settings_section.py
├── core/
│   ├── downloader.py
│   ├── converter.py
│   ├── trimmer.py
│   ├── document.py
│   ├── tray.py                # SystemTrayIcon(QObject)
│   ├── settings.py
│   └── history/
└── utils/
    ├── ffmpeg.py
    └── deps.py
```

## Commands

pytest; ruff check .

## Code Style

Python 3.12 (3.10+ compatible): Follow standard conventions

## Recent Changes
- 001-qt-migration (Phase N complete): Migrated from tkinter/ttkbootstrap/python-vlc/pystray/darkdetect to PySide6. All legacy GUI files removed. GUI now uses frameless MainWindow with 6-section sidebar navigation.

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
