# Quickstart: Build & Install (011)

**Branch**: `011-windows-installer-build`

## Prerequisites

- Windows 10/11 x64 build machine (WSL2 acceptable for PyInstaller step)
- Python 3.12 in PATH
- [Inno Setup 6.x](https://jrsoftware.org/isinfo.php) installed (adds `iscc.exe` to PATH)
- Internet access during build (ffmpeg download on first run)

## Build

```powershell
# From repo root
python build_executable.py
```

On first run with no `size-budget.json` present:
1. Downloads pinned ffmpeg (verified SHA256)
2. Builds PyInstaller one-folder bundle → `dist/MediaUtility/`
3. Compiles `installer.iss` → `dist/MediaUtility_Setup.exe`
4. Measures sizes, **writes** `size-budget.json`, prints instructions
5. Exits with code 0 — **review and commit `size-budget.json`**

On subsequent runs:
1. Same steps 1–3
2. Measures sizes, compares against `size-budget.json`
3. Fails build (exit 1) if either threshold exceeded, naming top contributors
4. Writes `dist/size-report.json` regardless of pass/fail

## Install

```
MediaUtility_Setup.exe
```

- Default install path: `C:\Program Files\media-utilities`
- Creates Start Menu group + optional desktop shortcut
- Silent: `MediaUtility_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES`

## Upgrade

Run new installer over existing installation — no manual uninstall needed. User data in `%APPDATA%\media-utilities\` is preserved.

## Uninstall

Via Add/Remove Programs or `C:\Program Files\media-utilities\unins000.exe`.
User data (`%APPDATA%\media-utilities\`) is **not** removed.

## Size Budget Management

```jsonc
// size-budget.json (committed)
{
  "installer_mb": 120,   // raise here to allow larger installer
  "installed_mb": 280,   // raise here to allow larger install dir
  "tolerance_pct": 5     // % headroom before failure
}
```

Raise values intentionally via PR. Build fails within seconds if exceeded, naming the top-10 size contributors.

## Measure Launch Time (manual)

```powershell
# Run 5 cold launches, record median
1..5 | ForEach-Object {
    (Measure-Command { Start-Process "C:\Program Files\media-utilities\MediaUtility.exe" -Wait }).TotalSeconds
}
```

Target: ≤ 3 s cold, ≤ 1.5 s warm.

## Playwright Browser Download (first use)

Playwright browsers are **not** bundled. On first use of the playwright download fallback, the app prompts the user and downloads Chromium on-demand. Cached under `%LOCALAPPDATA%\ms-playwright\`.
