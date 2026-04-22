---
description: "Task list for Windows Installer Build with Size Monitoring & Fast Startup"
---

# Tasks: Windows Installer Build with Size Monitoring & Fast Startup

**Input**: Design documents from `/specs/011-windows-installer-build/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/size-budget-schema.json ✅, quickstart.md ✅

**Tests**: Not requested in spec — no test tasks generated.

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 = One-Click Install, US2 = Fast Cold Start, US3 = Small Footprint, US4 = Branded Identity

---

## Phase 1: Setup (Shared Infrastructure) [X]

**Purpose**: Create committed config files that the build script and all user stories depend on.

- [x] T001 Create `build_config.json` at repo root with pinned ffmpeg 7.1 config: `url`, `sha256_url`, `strip_prefix` fields per data-model.md BuildConfig entity
- [x] T002 [P] Verify `core/version.py` exists and exports a `VERSION` string; create it with `VERSION = "1.0.0"` if absent — needed for AppVersion injection into Inno Setup

---

## Phase 2: Foundational (Blocking Prerequisites) [X]

**Purpose**: Rewrite `build_executable.py` base structure that all user stories depend on. Must complete before any story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T003 Rewrite `build_executable.py` skeleton: load `build_config.json`, detect version from `APP_VERSION` env var or `core/version.py`, define step orchestration flow (steps 1–7 per plan.md Phase 1C) with stubs for each step
- [x] T004 Implement `download_ffmpeg_pinned(cfg)` in `build_executable.py`: download ZIP to temp path, download SHA256 from `cfg['sha256_url']`, verify with `hashlib.sha256`, extract only `ffmpeg.exe` + `ffprobe.exe` from `cfg['strip_prefix']` subdir, clean up temp — skip if both binaries already exist

**Checkpoint**: Foundation ready — build script skeleton + ffmpeg download complete. User story implementation can now begin.

---

## Phase 3: User Story 1 — One-Click Windows Install (Priority: P1) 🎯 MVP [X]

**Goal**: End user downloads single Windows installer, runs it, and launches app from Start Menu / desktop shortcut with all features working on a machine without Python.

**Independent Test**: Fresh Windows 10/11 VM without Python. Run `MediaUtility_Setup.exe`, launch from Start Menu, exercise download/convert/trim/document/history/settings/tray tabs. Uninstall via Add/Remove Programs — all files and shortcuts removed, `%APPDATA%\media-utilities\` untouched.

### Implementation for User Story 1

- [x] T005 [P] [US1] Create `installer.iss` at repo root with full Inno Setup 6 script per plan.md Phase 1B: `AppId` fixed GUID `{{A7F3E1C2-4B8D-4A5F-9C3E-2D6B1F8E0A4B}`, `AppName=Media Utilities`, `AppPublisher=Omniclouds`, `DefaultDirName={autopf}\media-utilities`, `AppVersion={#AppVersion}`, `SetupIconFile=icon.ico`, `UninstallDisplayIcon={app}\MediaUtility.exe`, `Compression=lzma2/ultra64`, `SolidCompression=yes`, `CloseApplications=yes`, `VersionInfoVersion={#AppVersion}`, `VersionInfoCompany=Omniclouds`, optional desktop icon task, `[UninstallDelete]` scoped to `{app}` only (never `{userappdata}`)
- [x] T006 [US1] Add `compile_installer(version)` function in `build_executable.py`: locate `iscc.exe` via `shutil.which('iscc')` falling back to `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`, call `subprocess.check_call([iscc, f'/DAppVersion={version}', 'installer.iss'])` — wire as step 4 in main orchestration
- [x] T007 [US1] Add ffmpeg binaries to `media_util_gui.spec` `datas` list: after `download_ffmpeg_pinned()` places `ffmpeg.exe` + `ffprobe.exe` in a local `bin/` directory, add `datas=[('bin/ffmpeg.exe', '.'), ('bin/ffprobe.exe', '.')]` so PyInstaller bundles them at dist root

**Checkpoint**: `python build_executable.py` produces `dist/MediaUtility_Setup.exe`. Installer runs on clean VM, app launches, all tabs work.

---

## Phase 4: User Story 2 — Fast Cold Start (Priority: P1) [X]

**Goal**: Cold launch from shortcut to interactive main window ≤ 3 s on mid-range Windows laptop; no per-launch self-extraction delay.

**Independent Test**: Run `time_launch.ps1` 5× on freshly installed app. Record median. Must be ≤ 3 s cold, ≤ 1.5 s warm. Confirm `dist/MediaUtility/` is a directory (not a single `.exe` that self-extracts).

### Implementation for User Story 2

- [x] T008 [P] [US2] Update `media_util_gui.spec`: confirm `EXE` has `console=False`; confirm `COLLECT` block is present (one-folder, not onefile); add `upx_exclude` list covering all `PySide6/*.dll` and `PySide6/*.pyd` patterns; keep `upx=True` for Python bootstrap archive only
- [x] T009 [P] [US2] Create `time_launch.ps1` at repo root: `Measure-Command` loop running 5 cold launches of `MediaUtility.exe`, printing each duration and median — matches quickstart.md measurement procedure

**Checkpoint**: `dist/MediaUtility/` is a directory. Launch time measured with `time_launch.ps1` hits SLO target on reference hardware.

---

## Phase 5: User Story 3 — Small Install Footprint (Priority: P2) [X]

**Goal**: Maintainer runs build and sees installer + installed sizes reported against committed budget. Regressions fail build naming top contributors.

**Independent Test**: Run `python build_executable.py` twice. First run (no `size-budget.json`): seeds file, exits 0 with instructions. Second run: enforces budget. Manually add a large dummy file to `dist/MediaUtility/` and re-run — build fails with contributor named.

### Implementation for User Story 3

- [x] T010 [P] [US3] Update `media_util_gui.spec`: replace blanket `collect_data_files('PySide6')` with scoped collection excluding `translations/` and `Qt6WebEngine*` subdirs; add to `excludes` list: `PySide6.QtWebEngine`, `PySide6.QtWebEngineCore`, `PySide6.QtWebEngineWidgets`, `PySide6.Qt3DCore`, `PySide6.Qt3DRender`, `PySide6.Qt3DInput`, `PySide6.QtCharts`, `PySide6.QtDataVisualization`, `PySide6.QtDesigner`, `PySide6.QtHelp`, `PySide6.QtQuick`, `PySide6.QtQuickWidgets`, `PySide6.QtQml`, `PySide6.QtLocation`, `PySide6.QtBluetooth`, `PySide6.QtNfc`, `PySide6.QtSerialPort`, `PySide6.QtSensors`, `PySide6.QtVirtualKeyboard`
- [x] T011 [US3] Implement `measure_sizes(dist_dir, installer_path)` in `build_executable.py`: walk `dist_dir` with `Path.rglob('*')` to sum all file sizes in MB; read installer `.exe` size; collect top-10 files by size descending — wire as step 5 after Inno Setup compile
- [x] T012 [US3] Implement `check_budget(installer_mb, installed_mb, top10)` and `write_size_report(...)` in `build_executable.py`: if `size-budget.json` absent, write file with measured values + `tolerance_pct=5` + ISO-8601 `generated_at`, print seed instructions, exit 0; if present, enforce `installer_mb * (1 + tol)` and `installed_mb * (1 + tol)`, call `sys.exit(1)` with top contributors on failure; always write `dist/size-report.json` per data-model.md SizeReport schema — wire as steps 6+7

**Checkpoint**: Build prints installer MB, installed MB, top-10. Missing budget → seeds file → commit → next run enforces.

---

## Phase 6: User Story 4 — Branded Identity (Priority: P2) [X]

**Goal**: App shows consistent branded logo on every Windows surface: installer UI, installed `.exe` icon, Start Menu, taskbar, Alt-Tab, tray, Add/Remove Programs.

**Independent Test**: Install app. Visually inspect: Explorer shows branded icon on `MediaUtility_Setup.exe` and `MediaUtility.exe`. Start Menu + taskbar + Alt-Tab show branded icon. Add/Remove Programs shows `Omniclouds` as publisher and branded icon. Tray icon (existing `core/tray.py`) shows branded icon.

### Implementation for User Story 4

- [x] T013 [P] [US4] Verify `media_util_gui.spec` has `icon='icon.ico'` pointing to `icon.ico` at repo root (from feature 006); if absent or pointing to wrong path, update the `EXE(...)` call — this wires branding into `MediaUtility.exe` file icon, taskbar, Alt-Tab
- [x] T014 [US4] Update `build_executable.py` version injection: ensure detected version string is passed to `compile_installer()` as `/DAppVersion=` flag so `VersionInfoVersion`, `AppVersion`, and `VersionInfoCompany` in `installer.iss` reflect the real release version — not hardcoded `"1.0"`

**Checkpoint**: Install app. Every branded surface (listed above) shows `icon.ico` logo. Add/Remove Programs shows `Omniclouds` publisher and correct version.

---

## Phase 7: Polish & Cross-Cutting Concerns [X]

**Purpose**: Documentation and final cross-cutting wiring.

- [x] T015 [P] Update `README.md` at repo root: add Install section (run `MediaUtility_Setup.exe`, silent flag), Upgrade section (run new installer over existing), Uninstall section (Add/Remove Programs or `unins000.exe`, `%APPDATA%` preserved), Size Budget section (explain `size-budget.json`, how to raise budget via PR) — per plan.md Phase 1E

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately. T001 and T002 are parallel.
- **Foundational (Phase 2)**: Depends on Phase 1 completion. T003 then T004 (sequential — T004 implements a function defined in T003 skeleton). **BLOCKS all user stories.**
- **User Stories (Phase 3–6)**: All depend on Foundational (Phase 2) completion.
  - US1 and US2 are both P1 — implement sequentially or in parallel (different files).
  - US3 and US4 are P2 — begin after US1/US2 or in parallel with them.
- **Polish (Phase 7)**: Depends on all implementation phases complete.

### User Story Dependencies

- **US1 (P1)**: Requires Phase 2. No dependency on other stories. T005 + T007 are parallel (different files); T006 requires T005.
- **US2 (P1)**: Requires Phase 2. No dependency on US1. T008 and T009 are fully parallel.
- **US3 (P2)**: Requires Phase 2. T010 independent (spec file); T011 then T012 sequential in `build_executable.py`.
- **US4 (P2)**: Requires Phase 2. T013 and T014 are parallel (different files). T014 requires T006 (version injection must exist).

### Parallel Opportunities

- T001 ‖ T002 (Phase 1)
- T005 ‖ T007 ‖ T008 ‖ T009 (across US1 and US2 — different files)
- T010 ‖ T013 (spec file changes vs. build script — different files)
- T013 ‖ T014 (different files within US4)

---

## Parallel Example: US1 + US2 simultaneously

```
# After Phase 2 complete, run in parallel:
Task T005: Create installer.iss                          → installer.iss
Task T007: Add ffmpeg datas to media_util_gui.spec       → media_util_gui.spec
Task T008: Update spec for UPX + one-folder confirm      → media_util_gui.spec  ← conflicts with T007
Task T009: Create time_launch.ps1                        → time_launch.ps1

# NOTE: T007 and T008 both touch media_util_gui.spec — do T007 then T008, or combine into one edit
# T005 and T009 are safe to run in parallel with anything
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001, T002)
2. Complete Phase 2: Foundational (T003, T004)
3. Complete Phase 3: User Story 1 (T005, T006, T007)
4. **STOP and VALIDATE**: Run `python build_executable.py` on Windows. Verify `dist/MediaUtility_Setup.exe` exists and installs correctly on clean VM.
5. Ship installer to testers.

### Incremental Delivery

1. Phase 1 + 2 → build pipeline base
2. US1 → working installer (MVP)
3. US2 → fast launch (UPX fix + one-folder confirmed + measurement script)
4. US3 → size monitoring (Qt exclusions + budget enforcement)
5. US4 → branding end-to-end verified
6. Polish → README updated

---

## Notes

- T007 and T008 both modify `media_util_gui.spec` — implement as a single editing session or sequentially to avoid conflicts.
- `size-budget.json` is not committed until the first successful build seeds it — T012 handles this automatically.
- `installer.iss` AppId GUID (`{{A7F3E1C2-4B8D-4A5F-9C3E-2D6B1F8E0A4B}`) must never change across versions — Inno Setup uses it to detect upgrade-in-place.
- Playwright browsers: FR-016 says never bundle them. No task needed — exclusion is by omission (build script never calls `playwright install`).
- Code signing is out of scope per spec — document SmartScreen warning in README (covered by T015).
