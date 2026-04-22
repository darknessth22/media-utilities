# Feature Specification: Windows Installer Build with Size Monitoring & Fast Startup

**Feature Branch**: `011-windows-installer-build`
**Created**: 2026-04-22
**Status**: Draft
**Input**: User description: "i want to build this project to a windows application but monitor the size and keeps all functions and with the porper logo also to make sure after the build for the installer to open fast"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One-Click Windows Install (Priority: P1)

End user downloads single Windows installer for media-utilities, runs it, and launches app from Start Menu / desktop shortcut. App opens with branded icon and all existing functions (download, convert, trim, document, history, settings, tray) work identically to dev run.

**Why this priority**: Ship-blocker. Without working installer app cannot reach non-developer users. Every other goal (size, speed, branding) depends on installer existing.

**Independent Test**: Fresh Windows 10/11 VM without Python. Run installer, launch app, exercise each tab. All features work. Uninstall cleanly.

**Acceptance Scenarios**:

1. **Given** clean Windows machine without Python/ffmpeg, **When** user runs installer and launches app, **Then** main window opens and every tab functional.
2. **Given** installed app, **When** user opens from Start Menu, **Then** taskbar + window + tray show branded logo (not default PyInstaller/Python icon).
3. **Given** installed app, **When** user runs uninstaller, **Then** all files, shortcuts, and registry entries removed except user data/history.

---

### User Story 2 - Fast Cold Start (Priority: P1)

User double-clicks installed app shortcut. Main window visible and interactive quickly enough to feel native, not like a heavy bundle unpacking.

**Why this priority**: PyInstaller onefile builds self-extract on every launch = multi-second delay + AV scan thrash. User explicitly asked "installer to open fast" (interpreted as *app* open fast after install, since installers themselves run once).

**Independent Test**: Stopwatch cold-start 5× on mid-range Windows laptop. Record time from double-click to interactive main window.

**Acceptance Scenarios**:

1. **Given** freshly installed app and cold OS cache, **When** user double-clicks shortcut, **Then** main window appears within 3 seconds.
2. **Given** warm OS cache (2nd launch), **When** user launches app, **Then** main window appears within 1.5 seconds.
3. **Given** Windows Defender real-time scan active, **When** app launches, **Then** no per-launch re-extraction delay (build is directory-based, not self-extracting onefile).

---

### User Story 3 - Small Install Footprint (Priority: P2)

Maintainer builds release and sees total installer + installed size stays within budget. Build script reports size on each run. Regressions fail CI / flag maintainer.

**Why this priority**: User asked to "monitor the size". Bloat silently grows across releases (Qt plugins, bundled ffmpeg, playwright browsers). Measurement + budget prevents drift.

**Independent Test**: Run build. Output shows installer `.exe` size + unpacked install size + top-10 largest files/dirs. Compare to committed budget file; fail build if exceeded.

**Acceptance Scenarios**:

1. **Given** build completes, **When** maintainer reads build log, **Then** sees installer size, installed size, and top-10 size contributors.
2. **Given** change adds dependency that pushes size over budget, **When** build runs, **Then** build fails with clear message naming the contributor.
3. **Given** size budget raised intentionally, **When** maintainer commits new budget value, **Then** build passes.

---

### User Story 4 - Branded Identity (Priority: P2)

App presents consistent branded logo everywhere Windows shows it: installer UI, installed `.exe` icon, Start Menu shortcut, taskbar, Alt-Tab, tray icon, window title bar, Add/Remove Programs entry.

**Why this priority**: User said "with the proper logo". Existing icon asset from feature 006 must flow end-to-end through the packaging pipeline, not just the running app.

**Independent Test**: Install app. Visually inspect every surface listed above. All show same branded icon, not Python/PyInstaller default.

**Acceptance Scenarios**:

1. **Given** installed app, **When** user opens Add/Remove Programs, **Then** media-utilities entry shows branded icon + publisher name + version.
2. **Given** running app, **When** user Alt-Tabs, **Then** branded icon appears in task switcher.
3. **Given** installer `.exe` on disk, **When** user views in Explorer, **Then** file icon is branded logo.

---

### Edge Cases

- Windows SmartScreen blocks unsigned installer → document expected behavior and "More info → Run anyway" path; do not block release on code signing.
- User installs over previous version → upgrade preserves history + settings, replaces binaries.
- Install path contains spaces / non-ASCII characters → app still launches and writes to correct app-data dir.
- Antivirus quarantines bundled ffmpeg or playwright browser → log clear error at first launch, not silent failure.
- Disk full mid-install → installer rolls back cleanly.
- Playwright browsers are large and optional → spec must decide bundled vs on-demand (see Assumptions).
- User launches app immediately after install before shortcut indexing → shortcut still works.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Build pipeline MUST produce single Windows installer artifact that installs media-utilities on Windows 10 and 11 (x64) without requiring Python or other pre-installed runtimes. Installer MUST present a directory-picker dialog defaulting to `Program Files\media-utilities`; user may change install path.
- **FR-002**: Installed app MUST retain every feature available in source run: download (yt-dlp, playwright fallback, generic URL, progress/preview), convert, trim, document tools, history, settings, system tray, drag-and-drop, theme switching.
- **FR-003**: Installer and installed `.exe` MUST use project's branded logo (from feature 006) as their file icon and embedded resource icon.
- **FR-004**: Installed app MUST show branded icon in window title bar, taskbar, Alt-Tab switcher, system tray, Start Menu shortcut, desktop shortcut (if created), and Add/Remove Programs entry.
- **FR-005**: Build MUST use directory-based (one-folder) distribution, not self-extracting single-file bundle, so cold launch does not pay re-extraction cost on every run.
- **FR-006**: Cold-launch time from shortcut click to interactive main window MUST be ≤ 3 seconds on mid-range Windows laptop (8GB RAM, SSD, no recent launch).
- **FR-007**: Warm-launch time MUST be ≤ 1.5 seconds under same hardware profile.
- **FR-008**: Build script MUST print, at end of each run: installer file size, total installed size, top-10 largest files or directories in bundle.
- **FR-009**: Build MUST enforce committed size budget for both installer size and installed size; exceeding budget MUST fail build with message naming top contributors. If `size-budget.json` does not exist, build auto-generates it from measured sizes and exits with instructions to review and commit it; subsequent runs enforce that file.
- **FR-010**: Build MUST exclude unused Qt plugins, unused Python stdlib modules, test fixtures, `.pyc`/`__pycache__`, source maps, other artifacts not required at runtime.
- **FR-011**: Installer MUST support silent/unattended install (standard flag) for admin deployment.
- **FR-012**: Installer MUST register uninstaller that removes all installed files and shortcuts but MUST preserve user data (settings JSON, download history) in platform app-data directory.
- **FR-013**: Installer MUST support upgrade-in-place over previous installed version without requiring manual uninstall and without destroying user data.
- **FR-014**: Installer MUST write publisher, product name, version, and icon metadata so Add/Remove Programs and installed `.exe` properties dialog display correct branded information.
- **FR-015**: Build artifacts (installer, checksum) MUST be reproducible enough that running build twice on same source produces installers of equal size (byte-identical not required).
- **FR-016**: Playwright browsers MUST NOT be bundled in the installer. They are downloaded on-demand at first use with clear progress UI and cached for subsequent launches; installer size budget excludes playwright binaries.
- **FR-017**: Bundled `ffmpeg` binary MUST remain functional from installed location (trim + convert tabs). Build script MUST download a pinned ffmpeg Windows x64 release (e.g. from gyan.dev) and verify its checksum before bundling; no system PATH copy or manually placed binary.
- **FR-018**: README / release notes MUST document install, upgrade, uninstall, and size budget procedures.

### Key Entities

- **Installer Artifact**: single `.exe` shipped to users; has size, version, icon, publisher metadata, signature status.
- **Installed Application**: directory of files placed under Program Files (or user-chosen path); contains launcher `.exe`, Qt runtime, Python runtime, bundled ffmpeg, assets, icon.
- **Size Budget**: committed numeric thresholds (installer MB, installed MB) checked by build; editable via PR.
- **Size Report**: per-build textual/JSON report of installer size, installed size, top-10 contributors; surfaced in build log and saved beside artifact.
- **User Data**: settings JSON + download history JSON under platform app-data dir; must survive uninstall/upgrade.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of existing feature tabs (download, convert, trim, document, history, settings, tray) remain functional in installed build, verified by manual smoke checklist on clean Windows VM.
- **SC-002**: Cold start time from shortcut double-click to interactive main window ≤ 3 seconds on reference hardware; measured over 5 runs, median reported.
- **SC-003**: Warm start time ≤ 1.5 seconds on reference hardware; median of 5 runs.
- **SC-004**: Installer size ≤ committed budget (initial budget set during first successful build; default ceiling 150 MB without playwright browsers, 400 MB with).
- **SC-005**: Installed (unpacked) size ≤ committed budget; default ceiling 1.5× installer size.
- **SC-006**: Every Windows UI surface (taskbar, Alt-Tab, tray, Start Menu, Add/Remove Programs, installer UI, `.exe` file icon) shows branded logo; verified by installer-time visual checklist.
- **SC-007**: Upgrade from previous installed version preserves user settings and history in ≥ 99% of test runs (no data loss in ≥ 10 upgrade trials).
- **SC-008**: Build fails within 30 seconds of exceeding size budget, with top contributors named in failure message.
- **SC-009**: Uninstall removes all installed files and shortcuts and leaves user data dir untouched; verified by filesystem diff on clean VM.

## Clarifications

### Session 2026-04-22

- Q: Where does the build script obtain the ffmpeg binary for bundling? → A: Download pinned ffmpeg release from internet during build (e.g. gyan.dev), verify checksum.
- Q: Is on-demand playwright browser download the confirmed decision (not bundled)? → A: Confirmed — playwright browsers downloaded on-demand at first use; never bundled in installer.
- Q: How is the size budget seeded? → A: Build script auto-generates `size-budget.json` on first run (no existing file); maintainer commits it; future builds enforce it.
- Q: Does installer show a directory-picker? → A: Yes — defaults to `Program Files\media-utilities`, user may change.
- Q: Is CI integration in scope? → A: No — manual build script only; no CI workflow committed in this feature.

## Assumptions

- Reference hardware for launch-time SLO: Windows 11, 8 GB RAM, NVMe SSD, mid-range CPU (Ryzen 5 / Core i5 class).
- Code signing out of scope for this feature; SmartScreen warning on first install is acceptable and documented.
- "Installer opens fast" in user prompt interpreted as *the installed application* launching fast after install, not installer UI's own startup; installers are one-shot and not perf-critical.
- Playwright browser binaries (Chromium) very large; default plan is **on-demand download at first use** with progress UI, not bundled. If bundling required, size budget raised accordingly (see FR-016).
- Branded logo asset already exists from feature 006 (`006-app-icon-rebrand`) and will be reused as-is (`.ico` multi-resolution).
- Target architecture is Windows x64 only; ARM64 and 32-bit are out of scope.
- Installer framework choice (Inno Setup, NSIS, MSIX, WiX, etc.) is implementation detail for `/speckit.plan`; spec requires only observable behaviors above.
- CI integration is out of scope; build is triggered manually by maintainer running `build_executable.py` (or equivalent). No GitHub Actions workflow committed in this feature.
- Size budget values committed to repo and reviewed per release; raising budget is explicit (PR change), not silent.

## Out of Scope

- macOS / Linux packaging.
- Auto-update mechanism (user re-downloads new installer).
- Code signing / EV certificate procurement.
- Microsoft Store (MSIX) submission.
- Telemetry or crash reporting backend.
