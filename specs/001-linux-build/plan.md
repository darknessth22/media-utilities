# Implementation Plan: Linux Build + GitHub Pages Refresh

**Branch**: `001-linux-build` | **Date**: 2026-05-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-linux-build/spec.md`

## Summary

Ship Videl on Linux. Add CI job that builds an AppImage on `ubuntu-22.04` in parallel with existing Windows job on every `v*` tag, uploads it to the same GitHub Release as the Windows installer. Adapt PyInstaller spec + bootstrap so the frozen build runs on glibc 2.35+ with bundled ffmpeg/ffprobe (no AI deps — those still install on-demand into `~/.local/share/Videl/ai_packages`). Refresh `gh-pages` `index.html`: list current feature set (subtitles overhaul, transcript, downloads, vocal-first, updater, EN/AR RTL) and add a "Download for Linux" button next to the Windows one, both pointing at `/releases/latest/download/<stable-name>`. Extend in-app updater to swap the running AppImage in place.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: PySide6 (Qt 6), PyInstaller, yt-dlp, spotdl 4.2.0, PyMuPDF, Pillow + pillow-heif, python-docx, openpyxl, python-pptx, packaging, cryptography (manifest signing)
**Storage**: Filesystem only — settings JSON + history under platform user-config dir (Windows `%APPDATA%`, Linux `$XDG_CONFIG_HOME` / `~/.config/Videl`); AI packages cache under `~/.local/share/Videl/ai_packages` on Linux
**Testing**: pytest (smoke + regression); manual per-tab smoke on each platform pre-release
**Target Platform**: Windows 10+ (existing) AND Linux x86_64, Ubuntu 22.04+ / glibc 2.35+ (Debian 12+, Fedora 36+, recent Mint/Pop)
**Project Type**: Desktop GUI application (single project, modular `core/` + `gui/`)
**Performance Goals**: Parallel CI wall time ≤ 1.5× current Windows-only build (~SC-005); AppImage cold launch < 5 s on baseline hardware
**Constraints**: AppImage MUST be portable (no root install), ship ffmpeg/ffprobe bundled, defer torch/demucs/rembg to first-run download, work on glibc 2.35 (no newer libstdc++ symbols), preserve EN/AR RTL parity with Windows
**Scale/Scope**: Single-user desktop; one new CI job + one packaging script + spec updates + one static page refresh

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Modular Architecture | ✅ PASS | No new monolith. Linux packaging lives next to `build_executable.py`; updater extension stays in `core/updater.py`; path helpers in `utils/`. |
| II. Cross-Platform Compatibility | ✅ PASS | This feature *is* the principle's enforcement. All path / FS access continues via `pathlib`; new platform branches limited to packaging + updater swap path. |
| III. UX First | ✅ PASS | Linux build preserves all GUI tabs, progress, cancel, EN/AR. Pages site gains clear per-platform download CTAs. |
| IV. Quality & Testing | ✅ PASS | Smoke-test matrix in `quickstart.md` covers each tab on Linux; CI gates Linux job before release attaches asset. |
| V. Simplicity & YAGNI | ✅ PASS | AppImage chosen (single file, no install daemon, no flatpak/snap store overhead). No new abstractions — reuse existing build script with platform branches. |

No violations. Complexity Tracking section unused.

## Project Structure

### Documentation (this feature)

```text
specs/001-linux-build/
├── plan.md              # This file
├── spec.md              # Feature spec (already authored)
├── research.md          # Phase 0 — packaging/runtime/updater decisions
├── data-model.md        # Phase 1 — release artifacts, CI matrix, site model
├── quickstart.md        # Phase 1 — local Linux build + smoke test recipe
├── contracts/
│   ├── ci-workflow.md       # Required jobs, triggers, artifact names, exit conditions
│   ├── release-assets.md    # Stable asset filenames + URL pattern guarantees
│   └── pages-site.md        # gh-pages content contract (sections, buttons, links)
└── tasks.md             # Phase 2 — created by /speckit.tasks (NOT this command)
```

### Source Code (repository root)

```text
build_executable.py            # Existing Windows builder — extend with Linux branch
media_util_gui.spec            # PyInstaller spec — split Windows-only datas/binaries from cross-platform
build_appimage.sh              # NEW — Linux packaging entry: pyinstaller + linuxdeploy + appimagetool
build_config.json              # Add linux.ffmpeg.{url,sha256_url,strip_prefix}
requirements-build.txt         # No change (cross-platform already)

core/
├── updater.py                 # Extend: detect AppImage runtime, swap-in-place flow
├── version.py                 # Single source of truth (unchanged)
└── ...                        # No domain logic change

utils/
└── paths.py (or equiv.)       # Confirm user-data dir resolution via XDG on Linux

.github/workflows/
├── build.yml                  # Add `build-linux` job, parallel to existing Windows job
└── ci.yml                     # Unchanged unless pytest needs Linux runner addition

# gh-pages branch (separate worktree / branch checkout)
index.html                     # Refresh feature list + add Linux download button
assets/                        # Optional new icons/screenshots
```

**Structure Decision**: Single-project desktop app, unchanged. All new code lives at repo root (`build_appimage.sh`) or in existing modules (`core/updater.py`, `media_util_gui.spec`, `.github/workflows/build.yml`). The `gh-pages` branch is edited separately and is **not** part of `master`'s tree — treat it as a sibling deliverable referenced by `contracts/pages-site.md`.

## Complexity Tracking

*No constitution violations. Section intentionally empty.*
