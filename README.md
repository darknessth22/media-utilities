# Videl

Free, open-source media toolkit for Windows, Linux and Android, plus a web app that needs no install. Download videos and music, convert, trim, compress and merge video, make GIFs, edit PDFs, remove image backgrounds, isolate vocals, upscale photos and more. Your files are processed on your own device, never uploaded.

- **Website and downloads:** [videl.app](https://videl.app)
- **Web app, runs in your browser:** [app.videl.app](https://app.videl.app)
- **Privacy:** [videl.app/privacy](https://videl.app/privacy)
- **Report a bug:** [app.videl.app/#/report](https://app.videl.app/#/report), or the Report a Bug page inside the apps

Built with PySide6 (desktop), Flutter (Android) and plain HTML and JavaScript (web app).

---

## Screenshots

![Videl desktop app, home screen](<new screen gui.png>)

![Videl desktop app tour](<app-gui.gif>)

---

## Download

- **Windows 10 or later:** [Videl_Setup.exe](https://github.com/darknessth22/media-utilities/releases/latest/download/Videl_Setup.exe)
- **Linux x86_64** (Ubuntu 22.04+ / glibc 2.35+): [Videl-x86_64.AppImage](https://github.com/darknessth22/media-utilities/releases/latest/download/Videl-x86_64.AppImage)
- **Android 10 or later** (arm64): [videl-android-arm64-v8a.apk](https://github.com/darknessth22/media-utilities/releases/latest/download/videl-android-arm64-v8a.apk)
- **Any modern browser:** [app.videl.app](https://app.videl.app), for the everyday tools without installing anything

All builds are on the [Releases](https://github.com/darknessth22/media-utilities/releases/latest) page. The apps update themselves.

---

## Features

### Desktop app (Windows and Linux)

**Download**
- Media Download: videos, audio and whole playlists from YouTube, TikTok, Instagram, X (Twitter), Facebook, Twitch, LinkedIn and 1000+ other sites, with quality and time-range choices
- Spotify links (track, album or playlist): each song is found on YouTube and saved as an MP3 with title, artist, album and cover art

**Video and audio**
- Convert, Compress, Trim, Merge, Transform (resize, crop, rotate) and GIF Creator
- Audio Mixing, Subtitles (burn in SRT, VTT or ASS captions), Jump-Cutter (removes silent gaps)
- Auto-Chunker (split files by duration or size), Batch Watermark, Metadata Scrubber (strips GPS, timestamps and EXIF)

**AI tools, offline after a one-time download**
- Vocal Isolator (separates vocals from music)
- AI Transcript (speech to text in English and Arabic, saved as SRT)
- AI Upscaler for photos and AI Video Upscaler (Real-ESRGAN, 2x or 4x)
- AI Photo Restore (colorize, fix faces and upscale old photos)
- BG Eraser (remove backgrounds, or erase an object or person and fill the gap)

**Images**
- Image Editor with reusable presets, Frame Grabber, Hex Palette, Pixel Art

**Documents**
- Document Convert (PDF, DOCX, PPTX and Markdown, with a Markdown viewer)
- PDF Toolkit (compress, merge, split and extract images)

**Files**
- Folder Rules (auto-sort and tidy folders), History of past jobs

Drop any file on the Home screen and Videl lists the tools that can use it: video tools for a video, image tools for a photo, PDF tools for a PDF, Subtitles for an .srt file. Pick one and it opens with the file loaded.

The interface is available in English and Arabic.

### Android app

The downloader (the same sites, plus Spotify links), Convert, Trim, Crop, GIF, Extract Audio, Mute and History.

### Free online tools in the web app

These run entirely in your browser, so nothing is uploaded and there is nothing to install:

- [Compress video](https://app.videl.app/compress-video)
- [Convert video and audio to MP4, MP3, WebM and more](https://app.videl.app/convert-video)
- [Video to MP3](https://app.videl.app/video-to-mp3)
- [Audio converter](https://app.videl.app/audio-converter)
- [Trim video and audio](https://app.videl.app/trim-video)
- [Video to GIF](https://app.videl.app/video-to-gif)
- [Merge videos](https://app.videl.app/merge-videos)
- [Remove or replace audio in a video](https://app.videl.app/remove-audio-from-video)
- [Split a video into parts](https://app.videl.app/split-video)
- [Rotate video](https://app.videl.app/rotate-video), [crop video](https://app.videl.app/crop-video) and [resize video](https://app.videl.app/resize-video)
- [Merge PDF files](https://app.videl.app/merge-pdf)
- [Split a PDF](https://app.videl.app/split-pdf)
- [Rotate PDF pages](https://app.videl.app/rotate-pdf)
- [JPG to PDF](https://app.videl.app/jpg-to-pdf)
- [PDF to JPG or PNG](https://app.videl.app/pdf-to-jpg)
- [Remove the background from an image](https://app.videl.app/remove-background)
- [Convert, resize and compress images](https://app.videl.app/convert-image)
- [Compress images](https://app.videl.app/compress-image)
- [Resize images](https://app.videl.app/resize-image)
- [PNG to JPG](https://app.videl.app/png-to-jpg)
- [WebP to JPG](https://app.videl.app/webp-to-jpg)
- [Pixel art maker](https://app.videl.app/pixel-art-maker)
- [Color palette generator](https://app.videl.app/color-palette-generator)

The web app's [Downloader](https://app.videl.app/#/tool/download) page sends a pasted link to the Videl desktop app, which downloads it on your own connection. Video sites block downloads made from a browser tab.

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

- **None (CPU):** `libx264`, always available
- **NVIDIA:** `h264_nvenc`, needs an NVIDIA GPU and drivers
- **AMD:** `h264_amf`, needs an AMD GPU and drivers
- **Intel:** `h264_qsv`, needs an Intel GPU and drivers
- **VideoToolbox:** `h264_videotoolbox`, macOS only

If a job fails after enabling hardware acceleration, switch back to None (CPU). Hardware acceleration only applies to video.

---

## Cookie Support

Public posts download without cookies. Cookies are needed for private or age-restricted posts, and when a site asks you to log in.

1. Install the *Get cookies.txt LOCALLY* extension in Chrome/Brave/Edge/Firefox
2. Log into the target site
3. Export cookies from that site
4. Settings → Cookies → select the exported `.txt` file

Alternatively, select a browser directly (less reliable).

---

## Limitations

- HEIC conversion requires `pillow-heif`
- DOCX → PDF on Linux requires LibreOffice
- Document Convert reads PDF, DOCX and PPTX, and targets PDF, DOCX, **PPTX** and MD (Markdown). PDF → PPTX picks its strategy from the source. A **design deck** (presentation-shaped pages with a full-bleed background and text composed over it) is rendered page-for-slide at the source aspect ratio, because such a page *is* the slide and decomposing it strands the background from its headline. **The text stays editable**: each page's glyphs are redacted out of the rendered background and re-placed as real PowerPoint textboxes at their original positions, sizes and colours, with centred text detected from line geometry. Pages render at up to 2880 px / JPEG-92, above the source images' own resolution — a 1920 px budget on a 1920 pt page meant zoom 1.0, i.e. 72 DPI, and looked visibly soft. Removing the original lettering takes three forms: live text is redacted, a headline drawn as **vector outlines** is covered per glyph (grown by the stroke width, or the whole block is left alone where the background is too varied for a patch to hide — and then that block keeps its artwork instead of being overlaid twice), and a headline's **drop shadow** — a small soft-masked image lying on the words — is deleted, or it survives as grey shading. Redaction runs with `graphics=0` so the page's colour fields and palette swatches, which are vector art, are untouched. **Letter spacing is recovered**: decks set tracking either with literal spaces ("T O L E O  T O W E R") or in the glyph advances, and both are rebuilt into words plus a measured em value written as real character spacing, so words no longer run together. Paragraph breaks inside a merged run are kept as spacing, Arabic and Hebrew are returned to logical order and marked RTL, and overlays are pinned to Calibri because the embedded font is rarely installed. The sample 36-page 1920×1080 deck converts in ~26 s to a 33 MB 16:9 deck with 114 editable text boxes over pixel-faithful backgrounds. A flowed **document** is instead *rebuilt*, not page-imaged: headings start new slides and become titles, body text and bullets are packed to a slide budget and continued on a "(cont.)" slide rather than overflowing off the bottom, and a tall table is split across slides with its header row repeated. Pictures get their own slide, fitted to the content area with the aspect ratio preserved, and a short paragraph following a figure is kept on that slide as its caption. **Vector figures** (charts and diagrams drawn as many primitives — one bar chart measured 13) are clustered by proximity and rasterised once at 150 DPI, because emitting one autoshape per primitive yields scattered lines rather than a figure; page-sized vector art such as a border is ignored. Markdown output writes pictures to a `<stem>_images/` folder beside the file and links them relatively. Verified structurally (zip integrity, OOXML parts, well-formed slide XML, no shape off-canvas) and by opening the result in PowerPoint itself. Markdown is an output format only — converting *from* markdown is deliberately not offered; instead the section has a **Markdown Viewer** sub-tab: a VSCode-style source pane on the left (syntax highlighting, line-number gutter, current-line highlight, wrap toggle, live line/word/char count) and a live preview on the right, rendered by Qt's native `setMarkdown()` so there is no extra dependency. The two panes are **scroll-synced** proportionally in both directions (toggleable), with open/save/save-as and a 180 ms debounce so typing does not re-parse every keystroke. Preview is skipped above 2 MB, where a synchronous re-render would freeze the window on every keystroke. PPTX is text-only by design (slide titles become headings, body text becomes nested bullets, tables are kept, pictures/charts/SmartArt are skipped) and converts to MD or DOCX, not PDF. PDF → MD reuses the same layout analysis as PDF → DOCX, so heading levels and lists are inferred and may need a tidy-up; DOCX → MD reads Word's own heading/list/table structure and is exact. a scanned PDF page yields a warning that its text is not searchable
- LinkedIn browser-extension button is disabled (their feed scrubs post URNs from the DOM); paste LinkedIn URLs into the Downloader manually
- Some platforms require cookies for authenticated downloads
- BG Eraser / Vocal Isolator / AI Upscaler install AI components on first use into `%LOCALAPPDATA%\Videl\ai_packages\` — first runs download model weights
- BG Eraser has two tabs: **Remove Background** (selectable model — BiRefNet Lite is the default and keeps hair/thin detail that u2net loses) and **Erase Object** (paint over any object or person with brush/lasso/rectangle to remove it and heal the gap, leaving the rest of the image untouched — strokes accumulate across passes, with undo). Brush, lasso, rectangle and circle tools, plus **Smart select** — draw a rough shape over an object or person and SAM detects its real outline, which is drawn on the canvas in green so you can confirm the detection before applying (~360 MB model fetched on first use; the encoder embedding is cached per image so each extra mark resolves in ~0.03 s, and the smart flag is per-stroke so detected objects and hand-painted touch-ups can be mixed). The canvas supports zoom, pan, rotate and a magnifier for precise brushwork; the view transform never moves your strokes. Healing defaults to **LaMa** (a ~198 MB ONNX model fetched on first use, running on the onnxruntime rembg already installs) which reconstructs texture so the fill is invisible even on patterned backgrounds; a fast OpenCV fill is available as an instant fallback but visibly blurs texture. Smart select is tunable with **Detection sensitivity** — *Tight* keeps only the single instance under the mark (isolates one person from a group that touches or overlaps, where a salient-object model returns all of them as one blob), *Balanced* completes the object but rejects a subject blob more than ~2.6× SAM's own mask as a merged group, and *Loose* always expands to the whole subject. Changing it re-detects immediately without redrawing. Two further selection controls: **Erase from selection** turns any tool into a negative brush that cuts out of the selection instead of adding to it, updating the on-canvas highlight live as you drag (the overlay is painted from a fold of all strokes including the in-progress one, mirroring the core's mask, so an over-eager detection can be trimmed by hand and checked before applying) — finer than Undo, which drops a whole stroke — and **Invert selection** flips which side goes, so you can select the one subject to *keep* and remove everything else (inverting also erodes rather than dilates the boundary, keeping the grow margin off the subject being kept)
- Vocal Isolator GPU (CUDA 12.8) requires compute capability ≥ 7.0; Maxwell/Pascal fall back to CPU
- AI Upscaler requires Vocal Isolator installed first (it reuses torch)
- PDF Compress works by re-rendering — gains are largest on image-heavy PDFs

---

## Maintainers

- `core/version.py` is the single source of truth for the app version
- `size-budget.json` defines installer/installed size limits — `build_executable.py` fails the build if exceeded by more than 5%
- Pushing to `master` runs CI (pytest) only. Release builds run only on tags: `vX.Y.Z` builds Windows, Linux and Android and publishes the GitHub Release; `android-*` builds Android only
- Release builds install the exact library versions in `constraints-build.txt`, so updates stay small
- How Videl is built, how a change ships, and known gotchas: [ARCHITECTURE.md](ARCHITECTURE.md), [WORKFLOW.md](WORKFLOW.md), [LEARNINGS.md](LEARNINGS.md)
