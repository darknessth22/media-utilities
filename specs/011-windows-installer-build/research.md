# Research: Windows Installer Build (011)

**Date**: 2026-04-22 | **Branch**: `011-windows-installer-build`

---

## 1. Installer Framework — Inno Setup vs Alternatives

**Decision**: Inno Setup 6.x (already chosen in existing `build_executable.py`)

**Rationale**: Script already generates `.iss`; Inno Setup is free, scriptable, and covers all FR requirements. NSIS and WiX Toolset are equally capable but would require rewriting existing scaffolding. MSIX is out of scope per spec.

**Key capabilities confirmed**:
- Silent install: `/VERYSILENT /SUPPRESSMSGBOXES` (FR-011)
- Directory picker: `[Setup]` `DisableDirPage=no` (default; FR-001)
- Upgrade-in-place: `AppId` GUID + `CloseApplications=yes` → Inno Setup replaces files, leaves AppData untouched (FR-013)
- Publisher/version metadata: `AppPublisher`, `VersionInfoVersion`, `VersionInfoCompany`, `UninstallDisplayIcon` → Add/Remove Programs (FR-014)
- Uninstaller: `[UninstallDelete]` scoped to `{app}` only; AppData dir never touched (FR-012)
- Desktop shortcut optional task (FR-004)

**Alternatives considered**: NSIS (more complex scripting), WiX 4 (XML verbose, overkill), cx_Freeze (no installer), MSIX (Store submission, out of scope).

---

## 2. ffmpeg Pinned Release & Checksum (FR-017)

**Decision**: Download from **gyan.dev** essentials build, pinned version `7.1-essentials_build`

**Rationale**: gyan.dev is the most referenced Windows ffmpeg distribution; "essentials" build omits non-codec libs, smaller than "full". BtbN (current) has no pinned release URL — always "latest", so checksum cannot be committed.

**Pinned URL**:
```
https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-7.1-essentials_build.zip
```

**Checksum source**: gyan.dev publishes SHA256 at `https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-7.1-essentials_build.zip.sha256`

**Build script approach**:
1. Download ZIP to temp path
2. Download `.sha256` file, parse hex digest
3. `hashlib.sha256` verify before extraction
4. Extract only `ffmpeg.exe` + `ffprobe.exe` from `bin/` subdir
5. Store pinned URL + expected hash in `build_config.json` (committed); overridable via env var `FFMPEG_OVERRIDE_URL`

**Alternatives considered**: BtbN "latest" (no pinnable checksum), winget (requires winget on build machine), Chocolatey (requires admin).

---

## 3. PyInstaller Qt Plugin Exclusion (FR-010)

**Decision**: Explicit `excludes` list in `.spec` + `--collect-data` scoping

**Rationale**: `collect_data_files('PySide6')` currently collects everything including locale translations (~50 MB), WebEngine (~200 MB if present), and unused platform plugins. Selective exclusion documented by PyInstaller community.

**What to exclude**:
```python
# In spec excludes= list
'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
'PySide6.Qt3D*', 'PySide6.QtCharts', 'PySide6.QtDataVisualization',
'PySide6.QtDesigner', 'PySide6.QtHelp', 'PySide6.QtQuick*',
'PySide6.QtLocation', 'PySide6.QtBluetooth', 'PySide6.QtNfc',
'PySide6.QtSerialPort', 'PySide6.QtSensors', 'PySide6.QtVirtualKeyboard'
```

**Qt platform plugins**: Only `qwindows.dll` needed; `qminimal.dll` optional for headless. Remove `qoffscreen.dll`, `qwebgl.dll`.

**Translations**: Replace `collect_data_files('PySide6')` with scoped collection excluding `translations/` subdirs for unused locales. Or use `--qt-translations` PyInstaller flag (6.x+).

**UPX on Qt DLLs**: UPX causes false-positive AV detections on Qt DLLs. Set `upx_exclude` to all PySide6 `.dll`/`.pyd` files. Keep UPX only for pure Python `.pyc` archives.

**Estimated savings**: Excluding WebEngine alone saves ~200 MB. Qt translations ~30 MB. Net installed size target: ≤ 300 MB without playwright.

---

## 4. Size Monitoring & Budget Enforcement (FR-008, FR-009)

**Decision**: Pure Python implementation in `build_executable.py` using `os.walk` + `size-budget.json`

**Rationale**: No external tool dependency. Build already runs Python; adding ~60 lines covers all requirements. NSIS-based size reporting is post-install only; we need pre-ship build-time check.

**Budget file schema** (`size-budget.json`):
```json
{
  "installer_mb": 120,
  "installed_mb": 280,
  "tolerance_pct": 5,
  "generated_at": "2026-04-22T00:00:00Z",
  "note": "Auto-generated. Review and commit. Raise intentionally via PR."
}
```

**Report file schema** (`dist/size-report.json`):
```json
{
  "installer_mb": 118.4,
  "installed_mb": 275.2,
  "top10": [
    {"path": "PySide6/Qt6Core.dll", "mb": 28.1},
    ...
  ],
  "timestamp": "2026-04-22T10:30:00Z",
  "passed_budget": true
}
```

**Budget check logic**:
1. If `size-budget.json` absent → measure sizes, write file, print instructions, exit 0 (first-run seed)
2. If present → enforce `installer_mb * (1 + tolerance_pct/100)` and same for installed; fail with top-10 if exceeded

**Alternatives considered**: du/dir shell commands (platform-specific), separate CI step (out of scope), hardcoded limits (can't update without code change).

---

## 5. Startup Performance (FR-005, FR-006, FR-007)

**Decision**: One-folder (directory) distribution confirmed — already used in existing `.spec` (`COLLECT` block present, no `onefile=True`)

**Rationale**: `onefile` self-extracts to `%TEMP%` on every cold launch. One-folder launches directly from install dir — OS page cache warms binaries, no extraction overhead.

**Additional optimizations**:
- `console=False` already set (no console window startup delay)
- UPX on Python archive only (not Qt DLLs — see above)
- Defer playwright browser check to first use (already implied by FR-016)
- No startup splash screen needed unless launch time SLO at risk

**Measurement approach**: Build includes `time_launch.ps1` helper that uses `Measure-Command` to record wall-clock time from process start to first `WM_SHOWWINDOW` message. Documented in quickstart.md.

---

## 6. Branding End-to-End (FR-003, FR-004, FR-014)

**Decision**: Single `icon.ico` (already exists at repo root from feature 006) flows through PyInstaller `icon=` and Inno Setup `SetupIconFile=` / `UninstallDisplayIcon=`

**Surfaces covered by existing + planned wiring**:
| Surface | Mechanism |
|---------|-----------|
| Installer `.exe` file icon | Inno Setup `SetupIconFile=icon.ico` |
| Installed `MediaUtility.exe` icon | PyInstaller `icon='icon.ico'` (already in spec) |
| Start Menu shortcut | `[Icons]` `Name: "{group}\Media Utility"` |
| Desktop shortcut | `[Icons]` with optional task |
| Add/Remove Programs icon | `UninstallDisplayIcon={app}\MediaUtility.exe` |
| Taskbar / Alt-Tab | Qt `QApplication.setWindowIcon()` (already in app) |
| System tray | `QSystemTrayIcon` (already in `core/tray.py`) |
| Add/Remove Programs metadata | `AppPublisher`, `AppVersion`, `VersionInfoVersion` |

**Missing in current `.iss`**: `AppPublisher` is placeholder `"Media Utility Developer"` → use `"Omniclouds"`. `AppVersion` hardcoded `1.0` → read from `core/version.py` or env var `APP_VERSION`.

---

## 7. User Data Preservation (FR-012, FR-013, SC-007)

**Decision**: AppData directory never touched by installer or uninstaller

**Rationale**: Settings JSON and history JSON are written to platform app-data dir (`%APPDATA%\media-utilities\` on Windows) by `core/settings.py`. Inno Setup `[UninstallDelete]` only lists `{app}` subtree. No `[Files]` entry touches `{userappdata}`.

**Upgrade path**: Inno Setup detects existing installation via `AppId` GUID → replaces `{app}` files → Start Menu / registry entries updated → AppData untouched.

**Verification**: Post-uninstall, `%APPDATA%\media-utilities\` still present with settings + history.
