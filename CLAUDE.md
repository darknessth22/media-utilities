# media-utilities Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-11

## Active Technologies
- Python 3.10+ (3.12 recommended) + **PySide6** (GUI), **QMediaPlayer/QVideoWidget** (video trimmer), **QSystemTrayIcon** (system tray), **QGuiApplication.styleHints().colorScheme()** (OS theme detection), **QDropEvent.mimeData().urls()** (drag-and-drop)
- JSON config file in platform app data directory
- PyMuPDF/fitz (PDF extraction), python-docx (DOCX generation), docx2pdf (DOCX→PDF on Windows/macOS), LibreOffice headless (DOCX→PDF on Linux)
- Python 3.10+ (3.12 recommended) + PySide6 (GUI framework), Pillow (icon generation in build script), PyInstaller (executable packaging) (006-app-icon-rebrand)
- N/A (icon is a static asset bundled with the application) (006-app-icon-rebrand)
- Python 3.12 (3.10+ compatible) + yt-dlp (existing), urllib (stdlib — for HTTP fallback), PySide6 (existing GUI) (007-generic-url-download)
- Download history JSON (existing — no schema changes) (007-generic-url-download)
- Python 3.10+ (3.12 recommended) + playwright (Python sync API), yt-dlp (existing), PySide6 (existing) (008-playwright-m3u8-intercept)
- N/A — no new persistent storage; timeout setting added to `UserSettings` (008-playwright-m3u8-intercept)

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
- 008-playwright-m3u8-intercept: Added Python 3.10+ (3.12 recommended) + playwright (Python sync API), yt-dlp (existing), PySide6 (existing)
- 007-generic-url-download: Added Python 3.12 (3.10+ compatible) + yt-dlp (existing), urllib (stdlib — for HTTP fallback), PySide6 (existing GUI)
- 006-app-icon-rebrand: Added Python 3.10+ (3.12 recommended) + PySide6 (GUI framework), Pillow (icon generation in build script), PyInstaller (executable packaging)

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
