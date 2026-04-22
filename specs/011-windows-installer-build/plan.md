# Implementation Plan: Windows Installer Build with Size Monitoring & Fast Startup

**Branch**: `011-windows-installer-build` | **Date**: 2026-04-22 | **Spec**: `specs/011-windows-installer-build/spec.md`

## Summary

Produce a signed-ready Windows one-folder installer (Inno Setup 6) for media-utilities with: pinned ffmpeg (gyan.dev, SHA256 verified), Qt plugin exclusions to minimize size, per-build size reporting with committed budget enforcement, and full branded icon wiring across all Windows UI surfaces. Playwright browsers are excluded from the bundle (on-demand download at first use). Cold-launch target ≤ 3 s via one-folder (non-self-extracting) distribution.

## Technical Context

**Language/Version**: Python 3.12 (3.10+ compatible)  
**Primary Dependencies**: PyInstaller 6.x, Inno Setup 6.x (iscc.exe), PySide6, yt-dlp, playwright, ffmpeg 7.1 (gyan.dev essentials build)  
**Storage**: `size-budget.json` (committed), `build_config.json` (committed), `dist/size-report.json` (build artifact, not committed)  
**Testing**: Manual smoke checklist on clean Windows VM; `time_launch.ps1` for startup SLO verification  
**Target Platform**: Windows 10/11 x64  
**Project Type**: Desktop app + build pipeline  
**Performance Goals**: Cold launch ≤ 3 s, warm launch ≤ 1.5 s (FR-006, FR-007)  
**Constraints**: Installer size ≤ budget (default ~120 MB); installed size ≤ budget (default ~280 MB); playwright NOT bundled; ffmpeg pinned + checksum verified  
**Scale/Scope**: Single-maintainer build; no CI automation in this feature

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked post-design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Modular Architecture | ✅ PASS | Build pipeline changes are in `build_executable.py` + `.spec` + `installer.iss`. No new `core/` or `gui/` modules added; existing domain separation unchanged. |
| II. Cross-Platform Compatibility | ⚠️ JUSTIFIED | This feature is Windows-only by spec. `build_executable.py` already gates on `sys.platform`. Constitution explicitly says "Windows executable build pipeline (`build_executable.py`) MUST be maintained" — this feature improves that pipeline. No cross-platform regression. |
| III. User Experience First | ✅ PASS | Size check failure is verbose with named contributors. Playwright download is on-demand with progress UI (existing). Installer has directory picker, optional desktop shortcut. |
| IV. Quality & Testing | ✅ PASS | Manual smoke checklist defined in spec (SC-001). Launch-time measurement documented in quickstart.md. Size budget is a regression gate. |
| V. Simplicity & YAGNI | ✅ PASS | No new abstractions. Size monitoring is ~60 lines of `os.walk`. Budget is a flat JSON file. No CI pipeline added (out of scope). |

**Violations requiring justification**: None. Cross-platform exception is pre-authorized by Constitution §II.

## Project Structure

### Documentation (this feature)

```text
specs/011-windows-installer-build/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── size-budget-schema.json
└── tasks.md             # Phase 2 output (/speckit.tasks — not created here)
```

### Source Code Changes (repository root)

```text
media-utilities/
├── build_executable.py        # Rewrite: pinned ffmpeg+checksum, size report/budget, Qt exclusions wired, Inno Setup compile step
├── media_util_gui.spec        # Update: exclude unused Qt modules, upx_exclude Qt DLLs, scoped PySide6 data collection
├── installer.iss              # New (committed template): full Inno Setup script with all FR requirements
├── build_config.json          # New (committed): pinned ffmpeg URL + sha256_url + strip_prefix
├── size-budget.json           # New (auto-generated on first build, then committed by maintainer)
└── README.md                  # Update: install / upgrade / uninstall / budget sections
```

**Structure Decision**: Single project. No new packages or layers. All changes are to build tooling files at repo root. Source modules (`core/`, `gui/`, `utils/`) are untouched.

## Implementation Phases

### Phase 1A — PyInstaller Spec Hardening

Goal: reduce bundle size and fix UPX-on-Qt issue.

**Changes to `media_util_gui.spec`**:

1. Replace blanket `collect_data_files('PySide6')` with scoped collection excluding:
   - `translations/` (unused locales, ~30 MB)
   - `Qt6WebEngine*` directories (not used, ~200 MB if accidentally included)
2. Add to `excludes`:
   ```python
   'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
   'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
   'PySide6.QtCharts', 'PySide6.QtDataVisualization',
   'PySide6.QtDesigner', 'PySide6.QtHelp',
   'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.QtQml',
   'PySide6.QtLocation', 'PySide6.QtBluetooth', 'PySide6.QtNfc',
   'PySide6.QtSerialPort', 'PySide6.QtSensors', 'PySide6.QtVirtualKeyboard',
   ```
3. Set `upx_exclude` to all `PySide6/*.dll` and `PySide6/*.pyd` — UPX on Qt binaries causes AV false positives and minimal savings.
4. Keep `upx=True` for the Python bootstrap archive only.

### Phase 1B — Inno Setup Script (`installer.iss`)

Extract the inline installer string from `build_executable.py` into a committed `installer.iss` template. Key additions vs current:

```ini
[Setup]
AppId={{A7F3E1C2-4B8D-4A5F-9C3E-2D6B1F8E0A4B}  ; fixed GUID — never change
AppName=Media Utilities
AppVersion={#AppVersion}                          ; injected by build script via /DAppVersion=
AppPublisher=Omniclouds
DefaultDirName={autopf}\media-utilities
DefaultGroupName=Media Utilities
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\MediaUtility.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=yes
VersionInfoVersion={#AppVersion}
VersionInfoCompany=Omniclouds
VersionInfoProductName=Media Utilities

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\MediaUtility\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Media Utilities"; Filename: "{app}\MediaUtility.exe"; IconFilename: "{app}\MediaUtility.exe"
Name: "{group}\{cm:UninstallProgram,Media Utilities}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Media Utilities"; Filename: "{app}\MediaUtility.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MediaUtility.exe"; Description: "{cm:LaunchProgram,Media Utilities}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
; NOTE: {userappdata}\media-utilities is intentionally NOT listed — user data preserved
```

**Silent install** (FR-011): Inno Setup natively supports `/VERYSILENT /SUPPRESSMSGBOXES` — no extra config needed.

### Phase 1C — Build Script Rewrite (`build_executable.py`)

Rewrite `build_executable.py` with these additions (preserve existing step structure):

**Step 1: Load `build_config.json`**
```python
with open('build_config.json') as f:
    config = json.load(f)
ffmpeg_cfg = config['ffmpeg']
```

**Step 2: Download ffmpeg with checksum**
```python
def download_ffmpeg_pinned(cfg):
    # Skip if both binaries exist
    # Download ZIP to temp
    # Download sha256_url, parse hex digest
    # hashlib.sha256 verify
    # Extract only bin/ffmpeg.exe + bin/ffprobe.exe
    # Cleanup temp
```

**Step 3: Build PyInstaller** (unchanged except spec path)

**Step 4: Compile Inno Setup**
```python
def compile_installer(version):
    iscc = shutil.which('iscc') or r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
    subprocess.check_call([iscc, f'/DAppVersion={version}', 'installer.iss'])
```

**Step 5: Measure sizes**
```python
def measure_sizes(dist_dir, installer_path):
    installed_mb = sum(f.stat().st_size for f in Path(dist_dir).rglob('*') if f.is_file()) / 1e6
    installer_mb = Path(installer_path).stat().st_size / 1e6
    top10 = sorted([(p, p.stat().st_size/1e6) for p in Path(dist_dir).rglob('*') if p.is_file()],
                   key=lambda x: x[1], reverse=True)[:10]
    return installer_mb, installed_mb, top10
```

**Step 6: Budget check**
```python
def check_budget(installer_mb, installed_mb, top10):
    if not os.path.exists('size-budget.json'):
        # seed and exit 0 with instructions
    budget = json.load(open('size-budget.json'))
    tol = 1 + budget['tolerance_pct'] / 100
    failures = []
    if installer_mb > budget['installer_mb'] * tol:
        failures.append(f"Installer {installer_mb:.1f} MB > budget {budget['installer_mb']} MB")
    if installed_mb > budget['installed_mb'] * tol:
        failures.append(f"Installed {installed_mb:.1f} MB > budget {budget['installed_mb']} MB")
    if failures:
        print("BUILD FAILED — size budget exceeded:")
        for f in failures: print(f"  {f}")
        print("Top contributors:")
        for p, mb in top10: print(f"  {mb:.1f} MB  {p}")
        sys.exit(1)
```

**Step 7: Write `dist/size-report.json`**

### Phase 1D — `build_config.json` (committed)

```json
{
  "ffmpeg": {
    "version": "7.1",
    "url": "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-7.1-essentials_build.zip",
    "sha256_url": "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-7.1-essentials_build.zip.sha256",
    "strip_prefix": "ffmpeg-7.1-essentials_build/bin/"
  }
}
```

### Phase 1E — README Update

Add sections: Install, Upgrade, Uninstall, Size Budget. Reference `quickstart.md` in specs for maintainer procedures.

## Complexity Tracking

No constitution violations requiring justification.

## Open Questions (resolved)

All resolved in `research.md`. No blockers.
