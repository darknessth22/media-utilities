# Media Utility — Setup & Usage Guide

Everything you need to go from a fresh machine to a running app.

---

## Requirements

| Tool | Minimum version | Notes |
|------|----------------|-------|
| Python | 3.10 | 3.11+ recommended |
| FFmpeg | any recent | must be on PATH or in the project folder |
| Git | any | to clone the repo |
| LibreOffice | any | (Optional) for DOCX to PDF on Linux |

---

## 1. Install Python

Download from [python.org](https://www.python.org/downloads/) and run the installer.
**Check "Add Python to PATH"** during setup.

Verify:

```bash
python --version
# Python 3.11.x
```

---

## 2. Install FFmpeg

FFmpeg is required for all media operations (download, convert, trim).

### Windows (recommended — winget)
```bash
winget install Gyan.FFmpeg
```
Restart your terminal after install. Verify:
```bash
ffmpeg -version
```

### Windows (manual)
1. Download the latest build from [ffmpeg.org](https://ffmpeg.org/download.html) → Windows builds by BtbN.
2. Extract the zip.
3. Copy `ffmpeg.exe` and `ffprobe.exe` to either:
   - `C:\Windows\System32\` (system-wide), **or**
   - The `media-utilities\` project folder (local only)

### Linux
```bash
sudo apt install ffmpeg      # Debian/Ubuntu
sudo pacman -S ffmpeg        # Arch
```

### macOS
```bash
brew install ffmpeg
```

---

## 3. Clone the repository

```bash
git clone https://github.com/darknessth22/media-utilities.git
cd media-utilities
```

---

## 4. Create a virtual environment

Using a virtual environment keeps dependencies isolated from your system Python.

```bash
# Create the environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate

# macOS / Linux:
source venv/bin/activate
```

Your prompt should now show `(venv)`.

---

## 5. Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `PySide6>=6.6.0` — Qt GUI framework (replaces tkinter/ttkbootstrap)
- `yt-dlp` — video/audio downloads
- `Pillow` + `pillow-heif` — image conversion (including HEIC)
- `PyMuPDF` — PDF processing
- `python-docx`, `openpyxl`, `python-pptx` — Office document conversion
- `docx2pdf` — DOCX to PDF conversions
- `spotdl==4.2.0` — Spotify support
- `pyinstaller` — building the `.exe` (optional, only needed for distribution)

---

## 6. Run the app

```bash
python main.py
```

The app will:
1. Check/install any missing Python dependencies in the background.
2. Open the main window with a sidebar providing 10 sections: Download, Convert, Trim, Document Convert, GIF Creator, Compress, Merge Videos, History, Settings, How to Use.

> **Legacy entry point:** `python media_util_gui.py` also works — it still contains the original single-file version and will remain available until the next major release.

---

## 7. Spotify support (optional)

Spotify downloads use `spotdl`, which is already installed via `requirements.txt`. It pulls audio from YouTube and tags it with Spotify metadata.

Verify spotdl is working:
```bash
spotdl --version
# spotdl/4.2.0 ...
```

If the version shown is different from `4.2.0`, reinstall the pinned version:
```bash
pip install spotdl==4.2.0
```

---

## 8. Build a standalone Windows executable (optional)

To distribute the app without requiring users to install Python:

```bash
python build_executable.py
```

This script will:
1. Download `ffmpeg.exe` automatically (if not already present).
2. Install all dependencies.
3. Build `dist/MediaUtility/MediaUtility.exe` using PyInstaller.
4. Generate an Inno Setup installer script (`media_utility_installer.iss`).

The output directory (`dist/MediaUtility/`) is a portable folder — copy it anywhere and run `MediaUtility.exe`.

To create a proper Windows installer:
1. Install [Inno Setup](https://jrsoftware.org/isinfo.php).
2. Open `media_utility_installer.iss` with Inno Setup.
3. Click **Build → Compile**. The installer is saved to `installer/MediaUtility_Setup.exe`.

---

## Project structure

```
media-utilities/
├── main.py                  # Entry point — run this
├── media_util_gui.py        # Legacy entry point (delegates to main.py)
├── requirements.txt
├── build_executable.py      # Builds the .exe
├── media_util_gui.spec      # PyInstaller config (PySide6)
│
├── gui/
│   ├── app.py               # MainWindow — frameless sidebar UI
│   ├── theme.py             # ThemeManager + dark/light QSS
│   ├── worker.py            # Worker(QThread) for async operations
│   ├── dnd_handler.py       # Drag-and-drop routing
│   └── tabs/
│       ├── download_section.py
│       ├── convert_section.py
│       ├── trim_section.py
│       ├── document_section.py
│       ├── gif_section.py
│       ├── compress_section.py
│       ├── merge_section.py
│       ├── history_section.py
│       ├── settings_section.py
│       └── tutorial_section.py
│
├── core/
│   ├── downloader.py        # download_media, get_available_formats
│   ├── converter.py         # convert_images, convert_media
│   ├── trimmer.py           # trim_media
│   ├── document.py          # convert_document (PDF/DOCX/XLSX/PPTX)
│   ├── tray.py              # SystemTrayIcon (QSystemTrayIcon wrapper)
│   ├── settings.py          # UserSettings + SettingsManager
│   └── history/             # HistoryManager + HistoryItem
│
└── utils/
    ├── ffmpeg.py            # FFmpeg/FFprobe path resolution
    └── deps.py              # Dependency checking and auto-install
```

---

## Troubleshooting

### "FFmpeg not found" dialog on startup
FFmpeg is not on your PATH and is not in the project folder.
Fix: run `winget install Gyan.FFmpeg` (Windows) or `brew install ffmpeg` (macOS), then restart the app.

### spotdl version warning in the console
```
Warning: spotdl version mismatch. Expected 4.2.0, got: X.Y.Z
```
Reinstall the pinned version:
```bash
pip install spotdl==4.2.0
```

### Download fails for Instagram / Facebook
These platforms require authentication. Place a `cookies.txt` file (Netscape format) in the project directory. Export cookies from your browser using an extension such as "Get cookies.txt LOCALLY".

### Document conversion output looks wrong
PDF ↔ DOCX/XLSX/PPTX conversion is inherently imperfect for complex layouts. Best results are with text-only or text-heavy documents. Tables, multi-column layouts, and custom fonts will rarely survive intact.

### PyInstaller build fails
1. Ensure the virtual environment is active: `venv\Scripts\activate`
2. Reinstall dependencies: `pip install -r requirements.txt`
3. Delete `build/` and `dist/` and retry: `python build_executable.py`

---

## Running tests

```bash
# Test document conversion (requires a PDF in the project directory)
python test_document_conversion.py

# Test the built executable (run after build_executable.py)
python test_executable.py
```
