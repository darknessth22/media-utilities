# Videl

Offline media workstation for Windows — download, convert, trim, compress, merge, transform, watermark, scrub metadata, split, upscale, isolate vocals, erase backgrounds, work with PDFs, and more. Built with PySide6.

---

## UI

![Videl GUI](<new screen gui.png>)

![App Overview](<app-gui.gif>)

---

## Features

### Home & Navigation
- **Drop-zone hero** — drag any media file onto the welcome banner on Home and Videl auto-routes it to the matching tool (video → Convert, `.pdf` → PDF Toolkit, `.gif` → GIF Creator, etc.).
- **Recent strip** — your last few opened tools surface at the top of Home for one-click return; replaces the old duplicate Quick Access row.
- **Command palette (Ctrl+K)** — fuzzy-search every tool by name or description from anywhere in the app; ↑/↓ navigate, Enter opens, Esc closes.
- **Category filters** — on the Tools page, filter the grid by All / Video / Audio / Image / Document.
- **Accent-tinted icon tiles** — each tool's icon sits on a tinted square in its own brand color, with a hover lift on every card.

### Browser Extension (Download with Videl)
- Floats a "Download with Videl" button over every `<video>` on the web (top-right corner, follows the video on scroll).
- Click → Videl jumps to the foreground with the URL pre-loaded in the Downloader tab.
- Talks to the desktop app via a local-only HTTP bridge on `127.0.0.1:17654` (loopback, never exposed on the network).
- Page URL is preferred over the raw `<video>` source so yt-dlp's per-site extractors handle YouTube, TikTok, Twitter/X, Twitch, Facebook, Instagram, etc.
- LinkedIn is excluded — their new SDUI feed strips post URNs from the DOM, so reliable per-post URL extraction is not possible. Paste LinkedIn URLs into the Downloader tab manually.
- Source lives in [`browser_extension/`](browser_extension/) — load it unpacked from `chrome://extensions` (Developer mode → Load unpacked).

### Download
- YouTube, TikTok, Instagram, Facebook, Twitter/X, Twitch, LinkedIn, Spotify, and generic URLs
- Video or audio-only, with format/quality selection
- YouTube playlist manager — load the full list in seconds, check which items to download
- Per-job queue with progress, speed, ETA, and individual cancel buttons
- Time-range clip extraction (start/end)
- Cookie support for authenticated platforms (Instagram, TikTok)
- **Presets** — save your favourite type/format/quality/output-folder combo and reload in one click

### Convert
- Video: MP4, MKV, AVI, MOV, WEBM, FLV — including video-to-audio (MP3)
- Audio: MP3, WAV, AAC, FLAC, OGG, M4A
- Images: JPG, PNG, WEBP, BMP, GIF, HEIC
- Batch image conversion
- **Output naming templates** — control filenames with `{name}`, `{ext}`, `{date}`, `{datetime}` placeholders (configured in Settings)

### Trim
- Cut video or audio to a time range (HH:MM:SS or MM:SS)
- Inline preview player with start/end markers

### Document Convert
- PDF ↔ DOCX, PDF → Images, Images → PDF
- DOCX → PDF (Word on Windows/macOS, LibreOffice on Linux)

### GIF Creator
- Video segment → animated GIF
- Control start time, duration, width, and FPS
- Two-pass FFmpeg palette method for accurate colours

### Compress
- **Images**: quality (1–100), optional max dimension downscale
- **Video**: CRF (18–51), encoding preset (ultrafast → veryslow)
- **Hardware acceleration**: NVIDIA NVENC, AMD AMF, Intel QuickSync, Apple VideoToolbox — auto-detected, selectable per session
- **Presets** — save profiles like "Client Web (CRF 28, fast)" or "Archive (CRF 22, slow, NVENC)"

### Transform
- **Resize**: preset resolutions (4K, 1080p, 720p, TikTok, Instagram Square…) or custom W×H with lock-AR
- **Crop**: aspect-ratio presets (16:9, 9:16, 1:1…) or manual W/H/X/Y with live preview
- **Rotate / Flip**: 90° CW, 90° CCW, 180°, Flip H, Flip V — operations chain and preview live
- **Presets** — separate preset bars for Resize and Crop

### Audio Mux
- **Mute Video** — strip the audio track entirely
- **Replace Audio** — swap the audio track with any audio file
- **Add Audio** — mix an overlay audio track with adjustable volume (0–200%)
- Video track is always stream-copied (no re-encode, lossless)

### Merge Videos
- Join multiple video files in any order
- Lossless stream copy when compatible; auto re-encode when codecs/resolutions differ

### Watermark
- Stamp a **logo image** (PNG with transparency) or **text** onto any video or image
- Batch mode — queue multiple files, all processed in one run
- **Logo options**: position, scale (% of frame width), opacity
- **Text options**: custom text, position, font size, font color, opacity, semi-transparent background box
- **Video encode settings**: CRF/QP, preset, hardware acceleration (same GPU support as Compress)
- Images processed instantly; videos re-encoded at CRF 18 by default
- Output: `<name>_watermarked.<ext>`

### Metadata Scrubber (Forensics-Grade)
- Strip **all metadata** from video and audio files — GPS, timestamps, EXIF tags, chapter markers
- Forensics-grade re-encode pipeline removes embedded camera/encoder fingerprints
- Batch mode with progress tracking
- Supported: MP4, MKV, AVI, MOV, WEBM, FLV, M4V, WMV, MP3, WAV, AAC, FLAC, OGG, M4A
- Output: `<name>_clean.<ext>`

### Auto-Chunker
- Split a video or audio file into equal parts by **duration** or **target size (MB)**
- Stream copy — no re-encode, no quality loss
- **By duration**: e.g. 10 min per part
- **By size**: e.g. 25 MB chunks for WhatsApp; duration auto-calculated from bitrate
- Output: `<name>_part000.<ext>`, `<name>_part001.<ext>`, …

### Frame Grabber
- Extract a single frame from any video as a full-resolution JPEG or PNG
- Set the exact timestamp (HH:MM:SS) to capture
- Inline thumbnail preview
- Output: `<name>_frame_<timestamp>.<ext>`

### Hex Palette Extractor
- Analyse any image and extract its dominant colour palette (2–32 colours)
- Hex codes + colour swatches — click any swatch to copy the hex code
- Optional colour wheel view showing hue/saturation distribution

### BG Eraser
- Remove the background from a photo in one click — fully offline after first run
- Powered by `rembg` (U2-Net)
- Input + result preview on a checkerboard transparency grid
- Output: `<name>_nobg.png` (PNG with transparency)
- First-launch in-tab installer fetches AI components into `%LOCALAPPDATA%\Videl\ai_packages\bg_eraser`
- First model run downloads ~170 MB; subsequent runs are offline

### Vocal Isolator
- Separate any song or video into **Vocals** + **Accompaniment**
- Powered by Meta's **HTDemucs v4** — studio-grade 2-stem separation, fully offline after first run
- Auto GPU routing: NVIDIA CUDA on supported cards (compute ≥ 7.0 — RTX 20/30/40/50, V100, A100, H100), CPU otherwise. Maxwell/Pascal disabled (CUDA 12.8 build)
- Real-time progress bar from the demucs subprocess
- Runs on a background thread — keep using Videl meanwhile
- First-launch installer pulls `demucs` + `torch` (CPU or CUDA wheel) into `%LOCALAPPDATA%\Videl\ai_packages\vocal_isolator`
- First model run downloads ~300 MB HTDemucs weights
- Output: `vocals.wav` + `no_vocals.wav` next to the source

### AI Upscaler
- Upscale photos **2× or 4×** with **Real-ESRGAN** (RealESRGAN_x4plus)
- VRAM-friendly tiling (Off / 128 / 256 / 512) — 4K outputs run on 4–8 GB cards without OOM
- **Reuses PyTorch from the Vocal Isolator install** — no duplicate ~3 GB CUDA torch download. Install Vocal Isolator first
- First-launch installer fetches upscaler-only deps (`realesrgan`, `basicsr`, `facexlib`, `gfpgan`, `opencv-python`, `scipy`, `scikit-image`, ~180 MB) with `--no-deps`
- First upscale run downloads ~64 MB x4plus weights
- Output: `<name>_upscaled_x4.<ext>` (PNG / JPG / WebP)

### PDF Toolkit
- **Compress** — re-render at Screen (72 dpi), Web (150 dpi), or Print (300 dpi)
- **Merge** — combine PDFs; drag rows to set page order
- **Split** — every page as its own PDF, or extract a custom range (`1-3, 5, 7-9`)
- **Extract Images** — pull embedded images out as JPEGs, or render every page as a high-res JPEG
- **OCR** — turn scanned PDFs into searchable PDFs (invisible text layer, Ctrl+F works) or plain `.txt` files
  - Two pluggable engines, installed on demand:
    - **RapidOCR** (~120 MB) — ONNX-based, lightweight, English + CJK (bundled models)
    - **EasyOCR** (~350 MB CPU; CUDA build reuses Vocal Isolator's PyTorch) — 80+ languages, optional GPU
  - Adjustable render DPI (72–600); language picker per engine
- Powered by PyMuPDF — no external tools

### Subtitles (Burn-In)
- Hardcode an SRT/VTT/ASS subtitle file into a video so captions render on every player and platform
- **Drag-and-drop** video or subtitle files; sibling `.srt` files are auto-detected when a video is loaded
- **Embedded sub tracks** — `ffprobe` lists every subtitle stream in the source MKV/MP4; pick one and Videl extracts it to SRT for burning
- **Full libass styling** — font, size, bold/italic, primary/outline/box colors (swatch pickers with alpha for transparent outline/box), outline + shadow thickness, optional background box (BorderStyle 3), and bottom-margin spinner. Captions are rendered bottom-center (industry standard); use bottom-margin to lift off the frame edge
- **Encoding picker** — UTF-8 / UTF-8 BOM / Windows-1256 (Arabic) / Windows-1252 / Latin-1 / auto. Out-of-sync subs can be nudged via **time-offset** (seconds, applied to SRT/VTT)
- **Live subtitle preview** of the first few cues right under the file picker — confirms the right file and encoding before burning
- **Encoding presets** — Fast / Balanced / High Quality auto-set CRF + libx264 preset; CRF (14–32) and hardware encoder (NVIDIA NVENC / AMD AMF / Intel QuickSync / CPU) remain tunable
- **Real progress** — % bar, elapsed and ETA parsed from `ffmpeg -progress`, with a Cancel button that terminates ffmpeg cleanly
- **Filename template** — `{name}_subbed` by default; overwrite confirmation if the file already exists
- Audio stream-copied; **Open folder** / **Play** buttons appear after a successful burn
- Companion: in the **Downloader** tab, tick **Download subtitles** to fetch `.srt` files alongside the video (yt-dlp `--write-subs` / `--write-auto-subs`, comma-separated languages, optional auto-generated tracks)

### AI Transcript (Speech-to-Text)
- Fully offline transcription via [whisper.cpp](https://github.com/ggerganov/whisper.cpp) — Videl downloads the upstream prebuilt binary, no pip install needed
- **Backend picker** — choose **CPU** (~80 MB, works on any machine) or **NVIDIA CUDA** (~600 MB, 10–20× faster on RTX cards). Auto-detected NVIDIA GPUs get CUDA recommended.
- **Model picker** — install any Whisper model: tiny / base / small / medium / large-v3 / large-v3-turbo, in either Q5_0 quantized (~⅓ size) or full f16. Multiple models coexist; install/delete per model from the tab
- **English + Arabic** plus auto-detect — transcribes in the source language (Arabic audio → Arabic SRT, English audio → English SRT)
- Outputs an SRT subtitle file (timestamps + text) next to the source — drop straight into the Subtitles tab to burn into video
- Backends live in `%LOCALAPPDATA%\Videl\whisper_bin\{cpu,cuda}\`; models in `%LOCALAPPDATA%\Videl\whisper_models\`
- Accepts audio (mp3, wav, flac, m4a, aac, ogg, opus) or video (mp4, mkv, mov, webm, …); ffmpeg auto-extracts a 16 kHz mono WAV internally

### Jump-Cutter (Auto-Silence Removal)
- Detects silent gaps with FFmpeg `silencedetect`, re-encodes keeping only loud parts
- **Silence sensitivity** slider (-20 dB strict → -40 dB aggressive)
- **Minimum silence duration** slider (0.1 s – 3.0 s)
- **Edge padding** preserves a margin of silence around each cut so speech does not clip
- **Inline media preview** — built-in player with scrubber, play/pause, mute, and volume so you can hear/see exactly which part of the file you're marking
- **Protected ranges** — visual range editor: scrub the player and tap **Mark In** / **Mark Out**, or use per-row "Set start/end" buttons; multiple ranges with a mini-timeline showing green protected bands; silence inside any protected range is preserved
- Works for both audio and video; output: `<name>_jumpcut.<ext>`

### History
- Log of all operations with status, filename, timestamp
- Persists across restarts

### Bug Reporter
- One-click in-app bug report — captures app version, OS, log tail
- Sent via SendGrid to the maintainers

### Smart Updater
- Silent GitHub Releases check on launch
- Prompts when a newer tag exists; downloads + installs in-place via Inno RestartManager (no manual reinstall)

### i18n (EN / AR)
- Full English + Arabic UI translations
- RTL layout flip when Arabic is selected

### Settings
| Setting | Description |
|---|---|
| Theme | Auto (OS), Light, Dark |
| Language | English, Arabic (RTL) |
| Output folder | Default save location |
| Default codec | Fallback codec for conversions |
| Quit on close | Close = quit or minimize to tray |
| Intercept timeout | Browser-based download intercept wait (10–300 s) |
| **Output naming template** | `{name}`, `{ext}`, `{date}`, `{datetime}` |
| Hardware acceleration | None, NVIDIA, AMD, Intel, VideoToolbox |
| Cookies | File path or browser source for authenticated downloads |
| Spotify credentials | Custom Client ID/Secret to avoid shared rate limits |

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl + Enter` | Trigger primary action for the current section |
| `Esc` | Cancel an in-progress operation |
| `Ctrl + V` | Paste clipboard URL → Download section (when no text field is focused) |
| `Ctrl + K` | Open the command palette to fuzzy-jump to any tool |
| `Ctrl + H` | Go to Home |
| `Ctrl + T` | Go to Tools |
| `Ctrl + ,` | Open Settings |
| `F1` | Open How to Use |

---

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

## Output Naming Templates

Configure in **Settings → Output Naming Template**. Applies to converted and compressed files.

| Placeholder | Value |
|---|---|
| `{name}` | Source filename without extension |
| `{ext}` | Target format extension |
| `{date}` | `YYYYMMDD` |
| `{datetime}` | `YYYYMMDD_HHMMSS` |

---

## Presets

Compress, Transform → Resize, Transform → Crop, and Download have a **Preset bar** at the top.

- **Save…** — captures current settings under a name
- **Load** — restores the selected preset
- **Delete** — removes the selected preset

Presets persist in `config.json` across restarts.

---

## Spotify Support

Uses `spotdl` — matches track metadata from Spotify and downloads audio from YouTube.

- Proper metadata (artist, title, album, artwork)
- High-quality audio (up to 320 kbps)
- No DRM circumvention
- Audio source is YouTube, not Spotify directly

Custom Spotify credentials in Settings to avoid shared rate limits.

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
