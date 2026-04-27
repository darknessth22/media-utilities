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
- Python 3.12 (3.10+ compatible) + PySide6 (GUI + QtMultimedia for preview), yt-dlp (progress hooks + stream extraction), urllib stdlib (HTTP fallback progress), playwright (existing browser intercept — no change to intercept path for progress) (009-download-preview-progress)
- N/A — no schema changes; download history JSON unchanged (009-download-preview-progress)
- Python 3.12 (3.10+ compatible) + PySide6 (QThread, Signal), yt-dlp, playwright (010-fix-download-recovery)
- N/A — no schema or file-format changes (010-fix-download-recovery)
- Python 3.12 (3.10+ compatible) + PyInstaller 6.x, Inno Setup 6.x (iscc.exe), PySide6, yt-dlp, playwright, ffmpeg 7.1 (gyan.dev essentials build) (011-windows-installer-build)
- `size-budget.json` (committed), `build_config.json` (committed), `dist/size-report.json` (build artifact, not committed) (011-windows-installer-build)

## Project Structure

```text
media-utilities/
├── main.py                    # Entry point
├── media_util_gui.py          # Legacy entry point (delegates to main.py)
├── build_executable.py        # PyInstaller build script
├── build.bat                  # Windows build shorthand
├── media_util_gui.spec        # PyInstaller spec
├── installer.iss              # Inno Setup installer script
├── build_config.json          # Build metadata
├── size-budget.json           # Installer/dist size limits
├── icon.ico                   # App icon
├── assets/
│   └── icons/                 # SVG + PNG sidebar and UI icons
├── bin/
│   ├── ffmpeg.exe             # Bundled FFmpeg (Windows)
│   ├── ffprobe.exe
│   └── ffplay.exe
├── gui/
│   ├── app.py                 # MainWindow (frameless, sidebar nav)
│   ├── theme.py               # ThemeManager + QSS stylesheets
│   ├── worker.py              # Worker(QThread) for async operations
│   ├── dnd_handler.py         # Drag-and-drop via QDropEvent.mimeData().urls()
│   └── tabs/
│       ├── download_section.py   # Download tab — queue, interactive playlist manager
│       ├── convert_section.py    # Single + batch media/image conversion
│       ├── trim_section.py       # Time-range trimming with preview
│       ├── document_section.py   # PDF / DOCX / XLSX / PPTX conversion
│       ├── gif_section.py        # Video → GIF creator
│       ├── compress_section.py   # Image + video compression
│       ├── merge_section.py      # Multi-file video merge
│       ├── mux_section.py        # Audio muxing (replace / mute audio track)
│       ├── spatial_section.py    # Resize, crop, rotate, flip
│       ├── history_section.py    # Operation history log
│       └── tutorial_section.py   # In-app how-to guide
├── core/
│   ├── downloader.py          # download_media, fetch_playlist_entries, get_available_formats
│   ├── converter.py           # convert_images, convert_media
│   ├── trimmer.py             # trim_media
│   ├── document.py            # convert_document (PDF/DOCX/XLSX/PPTX)
│   ├── muxer.py               # mute_video, replace_audio_track
│   ├── spatial.py             # resize, crop, rotate/flip via FFmpeg
│   ├── interceptor.py         # Playwright HLS stream interceptor
│   ├── notifications.py       # Desktop notification dispatcher
│   ├── tray.py                # SystemTrayIcon(QObject)
│   ├── settings.py            # UserSettings + SettingsManager
│   ├── version.py             # VERSION constant
│   └── history/
│       ├── manager.py         # HistoryManager (add, load, clear)
│       └── models.py          # HistoryItem dataclass
├── utils/
│   ├── ffmpeg.py              # FFmpeg/FFprobe path resolution
│   └── deps.py                # Runtime dependency checker
└── tests/
    ├── unit/
    │   └── test_interceptor.py
    └── integration/
        ├── test_intercept_live.py
        └── test_download_token.py
```

## Commands

pytest; ruff check .

## Code Style

Python 3.12 (3.10+ compatible): Follow standard conventions

## Recent Changes
- 011-windows-installer-build: Added Python 3.12 (3.10+ compatible) + PyInstaller 6.x, Inno Setup 6.x (iscc.exe), PySide6, yt-dlp, playwright, ffmpeg 7.1 (gyan.dev essentials build)
- 010-fix-download-recovery: Added Python 3.12 (3.10+ compatible) + PySide6 (QThread, Signal), yt-dlp, playwright
- 009-download-preview-progress: Added Python 3.12 (3.10+ compatible) + PySide6 (GUI + QtMultimedia for preview), yt-dlp (progress hooks + stream extraction), urllib stdlib (HTTP fallback progress), playwright (existing browser intercept — no change to intercept path for progress)

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
