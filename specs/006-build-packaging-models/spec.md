# Feature Specification: Reliable Build & AI Model Packaging

**Feature Branch**: `006-build-packaging-models`
**Created**: 2026-05-01
**Status**: Draft
**Input**: User description: "build app locally and on GitHub without massive size from AI models. Either bundle them small or install at runtime — current runtime install is broken (spawns extra splash + window, downloads nothing). First approach worked but pulled from dev venv which user machines don't have, and full bundling pushes build past 2GB."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reliable runtime install of AI features (Priority: P1)

End user installs Videl, opens Background Eraser or Vocal Isolator. App detects AI package missing, shows clear in-place progress UI inside the existing window, downloads + installs the AI package on demand to a writable per-user location, then enables the feature — without spawning a second app instance or a duplicate splash screen.

**Why this priority**: Current runtime install is broken (extra splash, second window, no download). Without this, shipped builds are non-functional for AI tools even if they install successfully.

**Independent Test**: Install fresh Videl on a clean machine with no AI packages. Open Background Eraser tab → click install AI button → confirm: (a) only one Videl window visible at all times, (b) progress reported inline, (c) install completes, (d) feature works on next click without restart.

**Acceptance Scenarios**:

1. **Given** fresh install with no AI packages, **When** user opens an AI-dependent tab, **Then** UI shows "AI components not installed" state with single install button — no second splash or window appears.
2. **Given** user clicks install, **When** install runs, **Then** progress lines stream into the same window and the main window stays responsive.
3. **Given** install completes successfully, **When** user runs the AI feature, **Then** it works without restarting the app.
4. **Given** install fails (no internet, mirror down), **When** failure occurs, **Then** user sees an actionable error message and can retry; app does not crash or leave orphan windows.
5. **Given** user closes/reopens app after successful install, **When** app starts, **Then** AI packages are detected automatically and the feature is ready immediately.

---

### User Story 2 - Build pipeline succeeds locally and in GitHub Actions with bounded size (Priority: P1)

Maintainer runs `python build_executable.py` locally OR pushes to `main` to trigger CI. Both produce a working installer of bounded size (well under 2 GB) without leaking the dev venv's heavy AI/ML packages into the artifact.

**Why this priority**: Builds currently fail or balloon depending on which packages happen to be installed in the dev venv. CI is non-deterministic. Without this, releases cannot ship.

**Independent Test**: From a fresh clone on a dev machine that has heavy ML packages (torch, rembg, demucs) installed globally or in the active venv → run build → confirm artifact size matches the size budget and that PyInstaller did not pull in those heavy packages.

**Acceptance Scenarios**:

1. **Given** dev venv has rembg/demucs/torch installed, **When** maintainer runs the build, **Then** the produced installer does not include those packages and meets the size budget.
2. **Given** GitHub Actions runs the build workflow on `main`, **When** the job completes, **Then** the installer artifact is uploaded and matches the same size budget as a local build (within tolerance).
3. **Given** size budget is exceeded, **When** build runs, **Then** build fails with a top-contributors report so the regression is diagnosable.
4. **Given** build runs, **When** complete, **Then** a size report artifact is produced showing installer + installed sizes and top file contributors.

---

### User Story 3 - User informed about install size and disk requirements before downloading AI features (Priority: P2)

Before triggering an AI install, user sees the approximate download size and disk space the install will consume, plus where it will live, so install isn't surprising on metered/limited disk.

**Why this priority**: AI packages are hundreds of MB to multiple GB; surprising the user causes uninstalls and bad reviews. Not blocking core function.

**Independent Test**: Open AI tab pre-install → confirm UI shows estimated size and target location before user commits.

**Acceptance Scenarios**:

1. **Given** AI package is not installed, **When** user views the install prompt, **Then** approximate size and install location are shown.
2. **Given** insufficient disk space, **When** user attempts install, **Then** clear error appears before any download starts.

---

### Edge Cases

- App installed under `Program Files` (read-only for non-admin) — runtime install must write to a per-user writable location, never the install dir.
- User has corporate proxy / no direct internet — install surfaces a clear network error, not a silent hang.
- Mid-install the app is closed — partial install state is detected on next launch and either resumed cleanly or rolled back so retry succeeds.
- Antivirus quarantines pip-spawned activity — failure mode is visible, not a hang.
- Dev venv contains heavy packages (torch, tensorflow, opencv) — build artifact must NOT include them.
- GitHub Actions runner caches differ from local — build must be reproducible regardless.
- Same AI package previously installed by a different version of the app — app pins exact versions per release; on mismatch the installed set is auto-reinstalled to match the pinned manifest (no semver-range tolerance, no user prompt).
- User on a machine with no GPU — AI install auto-detects absence of CUDA-capable GPU and picks CPU-only variants to keep download size down (~200 MB torch CPU vs ~2.5 GB CUDA).
- User on a machine with NVIDIA CUDA GPU — auto-detection selects CUDA torch variant for speed; user is shown the larger download size before commit (per FR-013).

## Clarifications

### Session 2026-05-01

- Q: How do AI packages get installed at runtime? → A: `pip install` from PyPI into per-user dir using bundled Python runtime
- Q: Install granularity per AI tool? → A: Per-tool independent installs (each AI tab installs its own packages)
- Q: Partial install recovery on next launch? → A: Roll back to clean "not installed" state and prompt user to retry from scratch
- Q: CPU vs GPU variant selection for AI packages? → A: Auto-detect GPU at install time; pick CUDA variant if present, else CPU
- Q: Version-mismatch handling when AI package previously installed by different app version? → A: Pin exact versions per app release; auto-reinstall when installed set differs from pinned

## Requirements *(mandatory)*

### Functional Requirements

**Build artifact size & determinism**

- **FR-001**: Build pipeline MUST produce installer artifacts whose size is independent of which packages happen to be installed in the maintainer's dev environment.
- **FR-002**: Build pipeline MUST exclude heavy ML/AI runtime packages (rembg, demucs, torch, tensorflow, torchaudio, onnxruntime, cv2, numba, scipy, sklearn) from the shipped artifact. The exclusion list lives in `media_util_gui.spec` and is enforced by `tests/test_build_excludes.py`.
- **FR-003**: Build pipeline MUST enforce a configurable maximum installer size and fail the build with a top-contributors report when exceeded.
- **FR-004**: Build pipeline MUST behave identically (same artifact composition, same size within tolerance) whether invoked locally on Windows or via GitHub Actions on `main`.
- **FR-005**: Build pipeline MUST emit a machine-readable size report (installer MB, installed MB, top contributors) as a build artifact.

**Runtime AI package install UX**

- **FR-006**: Application MUST present a single in-window install flow for missing AI components — no additional splash screen, no second app instance, no extra OS window.
- **FR-007**: Application MUST stream install progress (download/extract/setup lines) inside the same main window where the user clicked install.
- **FR-007a**: Application MUST install AI packages by invoking `pip install` (from PyPI) using a bundled Python runtime shipped with the installer; no separate Python install on the user machine is required.
- **FR-008**: Application MUST keep the main window responsive (movable, closable, navigable to non-AI tabs) during install.
- **FR-009**: Application MUST install AI packages to a per-user writable location that does not require admin privileges, regardless of where the app itself is installed.
- **FR-010**: Application MUST detect already-installed AI packages on startup and enable AI features automatically without restart.
- **FR-010a**: Application MUST ship a per-release pinned version manifest (exact versions) for each AI component's package set, and on launch MUST compare installed versions to the manifest; on mismatch the component MUST be auto-reinstalled to match the pinned set without user prompt.
- **FR-011**: Application MUST surface install failures with actionable messages (network, disk space, permissions) and allow retry without restarting the app.
- **FR-012**: Application MUST detect partially completed installs on launch, roll back the partial state to a clean "not installed" status, and prompt the user to retry from scratch — no resume of in-flight installs.

**Discoverability & expectations**

- **FR-013**: Application MUST show approximate download size and target install location before the user commits to installing an AI component.
- **FR-014**: Application MUST verify available disk space before starting an install and refuse to start with a clear message when insufficient.
- **FR-014a**: Application MUST auto-detect a CUDA-capable GPU at install time and select the CUDA variant of AI packages when present; otherwise fall back to CPU-only variants. The detected variant and its download size MUST be shown in the pre-install size disclosure (FR-013).

**Localization**

- **FR-015**: All new install UI strings MUST be added in both English and Arabic locale files in the same change.

### Key Entities

- **AI Component**: A discrete optional capability per tool (e.g. "Background Eraser", "Vocal Isolator") installed independently, with a name, approximate size, install state (not installed / installing / installed / failed), and target install location. Each AI tab manages its own component install lifecycle; no shared/combined install.
- **Build Artifact**: The installer + unpacked dist directory produced by the build pipeline, characterised by installer size, installed size, top file contributors, and a size budget verdict.
- **Size Budget**: Per-build maximum sizes (installer MB, installed MB) with tolerance, used by build pipeline to fail fast on regressions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Installer size stays under the configured budget on every successful build (local and CI) — currently far below 2 GB; target ≤ 500 MB for the base installer without AI packages.
- **SC-002**: Builds run on a clean checkout vs. a dev venv polluted with rembg/demucs/torch produce installers within ±5% size and identical top-level file inventory under `dist/Videl/` (set of paths equal; hashes may differ for timestamped artifacts).
- **SC-003**: 0 occurrences of a second window or duplicate splash screen during runtime AI install across 10 consecutive fresh-install test runs.
- **SC-004**: Runtime AI install succeeds end-to-end on a clean Windows machine with no developer tools installed, in under 10 minutes on a typical broadband connection.
- **SC-005**: After successful AI install + app restart, AI features are available within 3 seconds of app launch with no further user action.
- **SC-006**: GitHub Actions build success rate ≥ 95% over the next 20 runs (excluding network-only flakes), versus current frequent failures.
- **SC-007**: When build size budget is exceeded, the failing build report identifies the top 10 contributing files so a maintainer can diagnose without re-running the build.

## Assumptions

- Target platform for shipped installer is Windows; macOS/Linux out of scope for this feature.
- AI packages will continue to be installed at runtime (not bundled) as the default approach; bundling remains an explicit non-goal unless size budget allows.
- Runtime install uses `pip install` from PyPI invoked via a bundled Python runtime; no system Python required on end-user machine.
- Network access on the end-user machine is available when they choose to install AI components — fully offline AI install is out of scope.
- The existing per-user install location pattern (`%LOCALAPPDATA%\Videl\ai_packages`) is acceptable as the writable target.
- Existing size-budget mechanism in `build_executable.py` is the right place to enforce limits; this feature tightens and verifies it, not replaces it.
- "Reasonable size" for the base installer is interpreted as ≤ 500 MB unless clarified otherwise.
