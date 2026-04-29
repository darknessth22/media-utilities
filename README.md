# Media Utility

A desktop application for downloading, converting, trimming, compressing, merging, transforming, and managing media files. Built with PySide6.

---

## UI

![Videl GUI](<new screen gui.png>)

## Overview

![App Overview](<app-gui.gif>)

---

## Features

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
- **Presets** — separate preset bars for Resize (e.g. "YouTube 1080p") and Crop (e.g. "TikTok 9:16")

### Audio Mux
- **Mute Video** — strip the audio track entirely
- **Replace Audio** — swap the audio track with any audio file
- **Add Audio** — mix an overlay audio track with adjustable volume (0–200%)
- Video track is always stream-copied (no re-encode, lossless)

### Merge Videos
- Join multiple video files in any order
- Lossless stream copy when compatible; auto re-encode when codecs/resolutions differ

### History
- Log of all operations with status, filename, timestamp
- Persists across restarts

### Settings
| Setting | Description |
|---|---|
| Theme | Auto (OS), Light, Dark |
| Output folder | Default save location for all operations |
| Default codec | Fallback codec for conversions |
| Quit on close | Close = quit or minimize to tray |
| Intercept timeout | Browser-based download intercept wait (10–300 s) |
| **Output naming template** | Filename pattern for converted files — supports `{name}`, `{ext}`, `{date}`, `{datetime}` |
| Hardware acceleration | GPU encoder/decoder for video compression — None, NVIDIA, AMD, Intel, VideoToolbox |
| Cookies | File path or browser source for authenticated downloads |
| Spotify credentials | Custom Client ID/Secret to avoid shared rate limits |

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl + Enter` | Trigger the primary action for the current section |
| `Esc` | Cancel an in-progress operation |
| `Ctrl + V` | Paste clipboard URL → Download section (when no text field is focused) |

---

## Requirements

- Python 3.10+
- FFmpeg (bundled in the Windows installer; otherwise must be on PATH)

### Python dependencies
```bash
pip install PySide6>=6.6.0 yt-dlp Pillow pillow-heif PyMuPDF python-docx openpyxl python-pptx spotdl docx2pdf
```

---

## Installation

### Windows installer (recommended)
1. Download `MediaUtility_Setup.exe`
2. Run and follow the prompts — FFmpeg is bundled
3. Silent install: `MediaUtility_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES`

Upgrade: run the new installer over the old one — settings and history are preserved.  
Uninstall: Add/Remove Programs, or run `unins000.exe` in the install directory.  
App data (`%APPDATA%\media-utilities`) is kept on uninstall.

### From source
```bash
git clone <repo>
cd media-utilities
pip install -r requirements.txt
python main.py
```

---

## Hardware Acceleration

The Compress section exposes a Hardware Acceleration dropdown populated with encoders detected on the current machine.

| Option | Encoder | Requires |
|---|---|---|
| None (CPU) | libx264 | Always available |
| NVIDIA | h264_nvenc | NVIDIA GPU + drivers |
| AMD | h264_amf | AMD GPU + drivers |
| Intel | h264_qsv | Intel GPU + drivers |
| VideoToolbox | h264_videotoolbox | macOS only |

If a compression job fails after enabling hardware acceleration, switch back to None (CPU).  
Hardware acceleration only applies to video — image compression always runs on CPU.

---

## Output Naming Templates

Configure in **Settings → Output Naming Template**. Applies to all converted and compressed files.

| Placeholder | Value |
|---|---|
| `{name}` | Source filename without extension |
| `{ext}` | Target format extension |
| `{date}` | `YYYYMMDD` |
| `{datetime}` | `YYYYMMDD_HHMMSS` |

**Examples**

| Template | Input | Output |
|---|---|---|
| `{name}_converted` *(default)* | `clip.mp4` → MP4 | `clip_converted.mp4` |
| `{name}` | `clip.mp4` → MP4 | `clip.mp4` |
| `{name}_{date}` | `clip.mp4` → MP4 | `clip_20260101.mp4` |
| `client_{name}_{datetime}` | `clip.mp4` → MP4 | `client_clip_20260101_120000.mp4` |

A live preview updates as you type in the Settings field.

---

## Presets

Compress, Transform → Resize, Transform → Crop, and Download sections each have a **Preset bar** at the top.

- **Save…** — captures the current settings and prompts for a name
- **Load** — restores the selected preset
- **Delete** — removes the selected preset

Presets are stored in `config.json` alongside other settings and persist across restarts.

**Typical use cases**

| Section | Example preset name | What it saves |
|---|---|---|
| Compress | "Client Web" | CRF 28, fast, CPU, output folder |
| Compress | "Archive HQ" | CRF 22, slow, NVENC |
| Compress | "Thumbnail" | Quality 80, max 1200 px |
| Transform → Resize | "YouTube 1080p" | 1920×1080, output folder |
| Transform → Resize | "TikTok Vertical" | 1080×1920 |
| Transform → Crop | "16:9 Center" | 1280×720, X=320, Y=180 |
| Download | "Spotify MP3" | Audio only, MP3, output folder |

---

## Spotify Support

Uses `spotdl` — matches track metadata from Spotify and downloads audio from YouTube.

- Proper metadata (artist, title, album, artwork)
- High-quality audio (up to 320 kbps)
- No DRM circumvention
- Audio source is YouTube, not Spotify directly

Supported URL types: tracks, albums, playlists.

Custom Spotify credentials can be set in Settings to avoid shared rate limits.

---

## Cookie Support

Required for Instagram, TikTok, and other authenticated platforms.

1. Install the *Get cookies.txt LOCALLY* extension in Chrome/Brave/Edge/Firefox
2. Log into the target site
3. Export cookies from that site
4. In Settings → Cookies, select the exported `.txt` file

Alternatively, select a browser directly (less reliable — may fail if the browser is open or uses OS-level cookie encryption).

---

## Limitations

- HEIC conversion requires `pillow-heif` installed
- DOCX → PDF on Linux requires LibreOffice
- Some platforms require cookies for authenticated downloads
- Hardware acceleration availability depends on the GPU and installed drivers
- Spotify downloads depend on YouTube availability of the track

---

## Size Budget (maintainers)

`size-budget.json` defines limits for the installer and installed files.  
The build script `build_executable.py` fails if the build exceeds the budget + 5% tolerance.  
Update `size-budget.json` in the PR if a new feature legitimately increases size.
