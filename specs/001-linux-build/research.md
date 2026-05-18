# Phase 0 — Research: Linux Build + GitHub Pages Refresh

Spec clarifications already locked the major choices (AppImage, ubuntu-22.04 baseline, full self-update, direct `/releases/latest/download/` URLs, on-demand AI deps). This file records the remaining unknowns surfaced by Technical Context and the resolution for each.

## R1 — Packaging tool chain on top of PyInstaller

**Decision**: PyInstaller (one-dir) → `linuxdeploy` (collect Qt + dependent libs via `linuxdeploy-plugin-qt`) → `appimagetool` (squashfs into single-file AppImage).

**Rationale**:
- PyInstaller already produces the frozen tree on Windows; reusing it keeps `media_util_gui.spec` as a single source of truth (one-dir output, not one-file — AppImage wraps the directory).
- `linuxdeploy-plugin-qt` knows the Qt 6 plugin layout (platforms, multimedia backends, imageformats) and patches RPATH correctly. Doing the equivalent by hand in `build_appimage.sh` would replicate logic that already exists.
- `appimagetool` is the canonical AppImage builder; output is a single executable with no install step — matches the spec's "single-file portable" guarantee.

**Alternatives considered**:
- **Flatpak**: requires user to install `flatpak` + add a remote; not single-file portable; sandbox would block our on-demand pip installs into `~/.local/share/Videl/ai_packages`. Rejected.
- **Snap**: store-centric, requires snapd; same sandbox issues as Flatpak; auto-update would conflict with our in-app updater. Rejected.
- **Plain tarball**: works but pushes Qt plugin path patching onto the user; no desktop integration. Rejected — would fail SC-002 (5-minute landing-to-launch).
- **Nuitka**: not currently used on Windows; introducing a second compiler for one platform violates Simplicity. Rejected.

## R2 — glibc / libstdc++ baseline

**Decision**: Build on the `ubuntu-22.04` GitHub-hosted runner. Pin in workflow with `runs-on: ubuntu-22.04` (not `ubuntu-latest`). Document supported floor in README + release notes as "Ubuntu 22.04 / glibc 2.35 or newer".

**Rationale**: AppImages are forward-compatible (newer glibc runs binaries built against older glibc) but not backward — building on ubuntu-latest (24.04) would silently raise the minimum glibc and break Ubuntu 22.04 LTS users still inside their support window.

**Alternatives considered**: Build inside a manylinux2014 container (glibc 2.17). Rejected — overkill for a desktop GUI; PySide6 wheels themselves target glibc 2.28+.

## R3 — FFmpeg bundling on Linux

**Decision**: Download a static `johnvansickle` linux-x64 ffmpeg+ffprobe build (GPL-licensed, statically linked) during CI and place `bin/ffmpeg` + `bin/ffprobe` next to the executable inside the AppImage. Pin URL + SHA256 in `build_config.json` under a new `linux` key, mirroring the existing Windows `gyan.dev` entry.

**Rationale**: Matches Windows behavior (FR-004). Static build sidesteps glibc/library mismatches inside the AppImage. johnvansickle.com is the de facto pinned source used by many AppImage projects.

**Alternatives considered**:
- Rely on system ffmpeg via PATH — rejected, violates "no manual prereqs" intent of FR-004.
- Build ffmpeg from source in CI — rejected, adds ~20 min wall time; conflicts with SC-005.

## R4 — User-data directory on Linux

**Decision**: Resolve config at `${XDG_CONFIG_HOME:-$HOME/.config}/Videl/` and AI package cache at `${XDG_DATA_HOME:-$HOME/.local/share}/Videl/ai_packages/`. Audit existing path helpers (`utils/paths.py` or equivalent) to ensure they branch on `sys.platform` and use XDG vars rather than hardcoded `%LOCALAPPDATA%`.

**Rationale**: XDG Base Directory spec is universal across the target distros; matches the spirit of FR-006 (filesystem path differences). Keeps settings/history per-user without root.

**Alternatives considered**: Single `~/.videl/` dotfile dir — rejected, ignores user expectations on modern Linux desktops.

## R5 — Auto-updater: in-place AppImage swap

**Decision**: On Linux frozen build, `core/updater.py` detects `APPIMAGE` environment variable (set automatically when an AppImage runs) → downloads the new AppImage to a temp file → validates signed manifest (existing Ed25519 flow, same key as Windows) → `chmod +x` → atomically `os.replace()` over `$APPIMAGE` → restart via `os.execv()`. If `$APPIMAGE` is read-only (system install) or in `/opt`, surface a clear error directing the user to download manually from the storefront.

**Rationale**: Matches spec clarification ("full self-update"). `os.replace()` on the same filesystem is atomic on Linux. Reusing the existing signed-manifest verifier (the Ed25519 PEM secret already set up for Windows) means no new key management.

**Alternatives considered**:
- Use `appimageupdate` / zsync delta — rejected, requires publishing `.zsync` files and an extra signing path; YAGNI for first release.
- External shell helper script — rejected, more moving parts; in-process replace is sufficient.

## R6 — Stable Linux asset filename

**Decision**: `Videl-x86_64.AppImage` (and signed manifest `Videl-x86_64.AppImage.sig.json`). No version suffix in the filename — the version lives inside the AppImage and in the release tag. URL contract: `https://github.com/darknessth22/media-utilities/releases/latest/download/Videl-x86_64.AppImage`.

**Rationale**: Required by FR-010 — direct-asset link via `/releases/latest/download/` only works when the asset name is stable across releases. Architecture suffix matches AppImage community convention and keeps the door open for future ARM64 without breaking existing links.

**Alternatives considered**: Embedding version in filename — rejected, breaks the latest-download URL pattern.

## R7 — Build-parity check on Linux

**Decision**: Skip the clean-vs-polluted parity check on Linux for the first release. Linux job runs the clean build only, uploads artifact + signed manifest, and exits. Document this as a follow-up if the Windows parity check ever fires regressions that look Linux-relevant.

**Rationale**: The parity check exists because PyInstaller on Windows historically swept up AI packages installed in the same venv. The Linux job uses a fresh venv on a throwaway runner each time — there's no "polluted" state to guard against. Doubling CI wall time for a guard that has no signal would violate SC-005.

**Alternatives considered**: Mirror the full Windows two-build parity check — rejected, no failure mode it would catch on a fresh runner.

## R8 — GitHub Pages refresh mechanics

**Decision**: Edit `index.html` on the `gh-pages` branch via a worktree checkout (`git worktree add ../media-utilities-pages gh-pages`). Single static page — no framework, no build step, matches existing site. Two side-by-side download buttons (Windows / Linux) with platform icons; feature list section regenerated from the current README features table. Both buttons use `/releases/latest/download/<asset>` URLs.

**Rationale**: Spec Assumptions explicitly keep `gh-pages` as a single static `index.html`. Worktree avoids context-switching off `001-linux-build` during editing.

**Alternatives considered**: Migrate to Jekyll / Astro — rejected, out of scope per Assumptions.

---

**Outcome**: All Technical Context items have a concrete decision. No `NEEDS CLARIFICATION` markers remain.
