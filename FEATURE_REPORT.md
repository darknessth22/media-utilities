# Videl — Feature Report

**Version:** 4.0.0
**Platforms:** Windows 10+ · Linux x86_64 (Ubuntu 22.04+)
**Stack:** PySide6 · FFmpeg · Pillow · PyTorch · PyMuPDF

**Totals:** 22 tools + 4 system sections — all shipped.

Source of truth: `_SECTIONS_META` in `gui/app.py`, cross-checked against `README.md` and the `core/` modules.

---

## 🎬 Video tools

| Tool | Does | Status |
|---|---|---|
| Convert | MP4 / MKV / AVI / MOV / WEBM / FLV, plus video→audio | ✅ Done |
| Trim | Cut video/audio to a time range, inline preview player | ✅ Done |
| GIF Creator | Video segment → animated GIF, two-pass palette | ✅ Done |
| Compress | CRF + encoding preset, hardware acceleration | ✅ Done |
| Transform | Resize / crop / rotate / flip with live preview | ✅ Done |
| Audio Mux | Mute / replace / add audio track (video stream-copied) | ✅ Done |
| Merge | Join videos, lossless stream-copy or auto re-encode | ✅ Done |
| Watermark | Logo or text, video + image, batch, hardware accel | ✅ Done |
| Metadata Scrubber | Forensics-grade metadata strip (GPS, EXIF, fingerprints) | ✅ Done |
| Auto-Chunker | Split by duration or target size, stream-copy | ✅ Done |
| Frame Grabber | Extract a single frame as JPEG/PNG at a timestamp | ✅ Done |
| Jump-Cutter | Auto silence removal with protected ranges | ✅ Done |
| Subtitles | Burn-in SRT/VTT/ASS, full libass styling, encoding picker | ✅ Done |

## 🔊 Audio

| Tool | Does | Status |
|---|---|---|
| Vocal Isolator | HTDemucs v4 two-stem separation, GPU auto-routing | ✅ Done |
| Convert / Trim / Chunk / Scrubber | Also operate on audio files | ✅ Done |

## 🖼️ Image

| Tool | Does | Status |
|---|---|---|
| Palette Extractor | Dominant colour palette (2–32), hex codes + colour wheel | ✅ Done |
| BG Eraser | One-click background removal (rembg / U2-Net) | ✅ Done |
| AI Upscaler | 2× / 4× Real-ESRGAN with VRAM-friendly tiling | ✅ Done |
| Image Editor | Full raster editor — see breakdown below | ✅ Done |

### Image Editor — sub-tabs: Transform · Color · Enhance · Masks · Presets · Wallpaper

- Aspect / monitor presets, fit modes (cover/fill/center/stretch), crop & free-rotate, flip
- 18 filter presets with strength blend, interactive tone curve, live RGB histogram
- Enhance: auto-enhance, exposure/gamma, dehaze, vibrance, clarity, denoise, unsharp mask
- Effects: sharpen, blur, grain, vignette, glass blur, duotone, gradient overlay
- **Masks (v4.0.0):** 5 types — radial / linear / color-range / luminance-range / brush; 15 per-mask adjust channels; per-mask opacity; boolean combine (add/subtract/intersect); radial rotation; show-mask overlay
- Undo/redo, hold-to-compare, EXIF-aware loading, user presets (JSON)
- Wallpaper studio: multi-monitor detect / export / apply, schedule, slideshow, named setups

## 📄 Document

| Tool | Does | Status |
|---|---|---|
| Document Convert | PDF ↔ DOCX, PDF → images, images → PDF | ✅ Done |
| PDF Toolkit | Compress / merge / split / extract images / OCR | ✅ Done |

## 🌐 Acquisition & Speech

| Tool | Does | Status |
|---|---|---|
| Download | yt-dlp — YouTube/TikTok/Instagram/X/Spotify + playlists | ✅ Done |
| Browser Extension | "Download with Videl" overlay button, local HTTP bridge | ✅ Done |
| AI Transcript | whisper.cpp speech-to-text → SRT, EN/AR, CPU/CUDA | ✅ Done |

## ⚙️ System & infrastructure

| Feature | Status |
|---|---|
| Home — drop-zone routing, recent strip, command palette (Ctrl+K), category filters | ✅ Done |
| History — operation log, persists across restarts | ✅ Done |
| Settings — theme, language, codec, naming templates, HW-accel, cookies | ✅ Done |
| Tutorial / How to Use (F1) | ✅ Done |
| Bug Reporter — in-app report via SendGrid | ✅ Done |
| Smart Updater + delta updates (Windows content-addressed blobs) | ✅ Done |
| i18n — full EN/AR translations + RTL layout flip | ✅ Done |
| Developer Console / crash logs | ✅ Done |
| Presets system — Compress, Transform, Download | ✅ Done |
| Hardware acceleration — NVENC / AMF / QuickSync / VideoToolbox | ✅ Done |
| Cross-platform — Windows installer + Linux AppImage | ✅ Done |
| Ed25519-signed installer + signed update manifest | ✅ Done |

---

## ⚡ GPU / CUDA acceleration

Videl has two independent acceleration paths — they use different hardware and
are wired into different tools.

### A. GPU video encoding (FFmpeg hardware H.264 encoders)

Auto-detected per machine, selectable per session, with CPU `libx264` fallback.
NVIDIA / AMD / Intel on Windows + Linux; Apple VideoToolbox on macOS.

| Tool | Hardware encoders | Notes |
|---|---|---|
| Compress | NVENC / AMF / QuickSync / VideoToolbox | Hardware Acceleration dropdown |
| Watermark | NVENC / AMF / QuickSync / VideoToolbox | video re-encode path |
| Subtitles (burn-in) | NVENC / AMF / QuickSync / CPU | tunable encoder + CRF |

Encoder labels are detected via `utils.ffmpeg.detect_hw_encoders()`. Hardware
encoding only applies to video; if a job fails after enabling it, switch to CPU.

### B. CUDA compute (NVIDIA-only — PyTorch / whisper.cpp)

NVIDIA-only acceleration for the AI tools. CPU fallback is always available.
The PyTorch tools use a CUDA 12.8 build and require **compute capability ≥ 7.0**
(RTX 20/30/40/50, V100, A100, H100). Maxwell / Pascal cards fall back to CPU.

| Tool | Engine | GPU path | CPU fallback |
|---|---|---|---|
| Vocal Isolator | HTDemucs v4 (PyTorch) | CUDA ≥ 7.0, auto-routed | ✅ |
| AI Upscaler | Real-ESRGAN (PyTorch) | CUDA — reuses Vocal Isolator's torch | ✅ |
| AI Transcript | whisper.cpp | CUDA backend (`whisper-cublas`, ~600 MB) | ✅ CPU backend (~80 MB) |
| PDF Toolkit — OCR | EasyOCR | optional CUDA — reuses Vocal Isolator's torch | ✅ (RapidOCR is CPU-only ONNX) |

Notes:
- AI Upscaler requires Vocal Isolator installed first — they share one PyTorch runtime (`ai_packages/torch_runtime/`), so CUDA torch is downloaded only once.
- AI Transcript ships two separate prebuilt whisper.cpp binaries; the backend (CPU vs CUDA) is picked in-tab, and NVIDIA machines get CUDA recommended.
- BG Eraser (rembg / U2-Net via onnxruntime) runs on **CPU** — no CUDA path is wired in the app.
- The two paths are orthogonal: a machine can use NVENC for video encoding while running the PyTorch tools on CPU, or vice versa.

---

## Assessment

Mature, broad media workstation — 22 tools, 5 AI-powered, fully offline-first. No half-finished
sections; every entry in `_SECTIONS_META` has a working tab and a backing `core/` module.

### Known gaps (none blocking)

- No vector / layers / collage editing — deliberately out of scope (raster + media lane only).
- Image Editor output card lacks format and quality controls — output extension always matches
  the source; JPEG/WebP quality is fixed at 92.
- Edited images are saved without EXIF metadata (orientation is read on load, not written back).
- `README.md` Effects line is stale — lists 4 effects, the editor now has 7.

---

*Generated 2026-05-21 · reflects release v4.0.0.*
