# Videl

Offline media workstation for Windows — download, convert, trim, compress, merge, transform, watermark, scrub metadata, split, upscale, isolate vocals, erase backgrounds, work with PDFs, and more. Built with PySide6.

---

## UI

![Videl GUI](<new screen gui.png>)

![App Overview](<app-gui.gif>)

---

## Features

## Requirements

- Windows 10+ · Linux x86_64 (Ubuntu 22.04+ / glibc 2.35+)
- Python 3.12+ (only when running from source)
- FFmpeg (bundled in the installer / AppImage; otherwise must be on PATH)
- Linux runtime libs: `libfuse2` (to run AppImages on Ubuntu 22.04+)

### Python dependencies (from-source only)
```bash
pip install -r requirements.txt
```

AI components (`rembg`, `demucs`, `torch`, `onnxruntime`, `realesrgan` …) are **not** in the app environment. The Windows installer ships a bundled embeddable Python under `runtime/python/`; on first use of an AI tab, Videl runs `pip install` against that bundled Python and writes packages to `%LOCALAPPDATA%\Videl\ai_packages\<component>\` (per-user, no admin required).

---

## Installation

### Windows installer (recommended)
1. Download `Videl_Setup.exe` from [Releases](https://github.com/darknessth22/media-utilities/releases/latest)
2. Run and follow the prompts — FFmpeg + bundled Python included
3. Silent install: `Videl_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES`

Upgrade: run the new installer over the old one — settings, history, and AI packages are preserved.
Uninstall: Add/Remove Programs, or `unins000.exe` in the install directory.
App data (`%APPDATA%\Videl`) and AI packages (`%LOCALAPPDATA%\Videl\ai_packages`) are kept on uninstall.

### Linux AppImage
1. Download `Videl-x86_64.AppImage` from [Releases](https://github.com/darknessth22/media-utilities/releases/latest)
2. `chmod +x Videl-x86_64.AppImage && ./Videl-x86_64.AppImage`
3. Requires `libfuse2` (`sudo apt-get install libfuse2` on Ubuntu 22.04+).

Settings live under `${XDG_CONFIG_HOME:-~/.config}/Videl/`, AI packages under `${XDG_DATA_HOME:-~/.local/share}/Videl/ai_packages/`. The in-app updater replaces the AppImage in place and re-launches.

### Build the Linux AppImage from source

Host: Ubuntu 22.04+ (glibc 2.35+). One-time setup, build flow, and AppImage tooling pins are in [`specs/001-linux-build/quickstart.md`](specs/001-linux-build/quickstart.md). Short version:

```bash
sudo apt-get install -y python3.12 python3.12-venv libfuse2 jq
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-build.txt
# Place linuxdeploy*.AppImage + appimagetool*.AppImage under tools/ (chmod +x).
bash build_appimage.sh
# → dist/Videl-x86_64.AppImage
```

### From source
```bash
git clone https://github.com/darknessth22/media-utilities.git
cd media-utilities
pip install -r requirements.txt
python main.py
```

---

## Hardware Acceleration

The Compress / Watermark sections expose a Hardware Acceleration dropdown populated with encoders detected on the current machine.

| Option | Encoder | Requires |
|---|---|---|
| None (CPU) | libx264 | Always available |
| NVIDIA | h264_nvenc | NVIDIA GPU + drivers |
| AMD | h264_amf | AMD GPU + drivers |
| Intel | h264_qsv | Intel GPU + drivers |
| VideoToolbox | h264_videotoolbox | macOS only |

If a job fails after enabling hardware acceleration, switch back to None (CPU). Hardware acceleration only applies to video.

---

## Cookie Support

Required for Instagram, TikTok, and other authenticated platforms.

1. Install the *Get cookies.txt LOCALLY* extension in Chrome/Brave/Edge/Firefox
2. Log into the target site
3. Export cookies from that site
4. Settings → Cookies → select the exported `.txt` file

Alternatively, select a browser directly (less reliable).

---

## Limitations

- HEIC conversion requires `pillow-heif`
- DOCX → PDF on Linux requires LibreOffice
- LinkedIn browser-extension button is disabled (their feed scrubs post URNs from the DOM); paste LinkedIn URLs into the Downloader manually
- Some platforms require cookies for authenticated downloads
- BG Eraser / Vocal Isolator / AI Upscaler install AI components on first use into `%LOCALAPPDATA%\Videl\ai_packages\` — first runs download model weights
- Vocal Isolator GPU (CUDA 12.8) requires compute capability ≥ 7.0; Maxwell/Pascal fall back to CPU
- AI Upscaler requires Vocal Isolator installed first (it reuses torch)
- PDF Compress works by re-rendering — gains are largest on image-heavy PDFs

---

## Maintainers

- `core/version.py` is the single source of truth for the app version
- `size-budget.json` defines installer/installed size limits — `build_executable.py` fails the build if exceeded by more than 5%
- Push to `master` triggers CI (pytest) + Build (PyInstaller + Inno Setup → Releases)
- Tagging `vX.Y.Z` triggers a release artifact upload
