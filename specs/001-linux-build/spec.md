# Feature Specification: Linux Build + GitHub Pages Refresh

**Feature Branch**: `001-linux-build`
**Created**: 2026-05-18
**Status**: Draft
**Input**: User description: "this app is for windows only for now i want to build it to linux with github actions like i do for the windows one so i need to make the required changes to build on linux and also change the gh pages of the app to contain the new added features in it and also add a button for download for linux"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Linux user installs Videl from official download (Priority: P1)

Linux user lands on Videl GitHub Pages site, clicks clearly-labeled Linux download button, gets Linux installer/package, installs, launches Videl with all tools (subtitles, transcript, downloads, vocal isolation, etc.) working same as Windows build.

**Why this priority**: Core ask. No Linux artifact = no Linux users. Everything else depends on this.

**Independent Test**: Fresh Linux machine downloads asset from latest GitHub release, installs, launches app, runs one task per tab successfully.

**Acceptance Scenarios**:

1. **Given** new tagged release pushed to GitHub, **When** CI completes, **Then** Linux artifact attached to release alongside Windows installer.
2. **Given** Linux user on supported distro, **When** they install and launch artifact, **Then** GUI opens, locales load, settings persist, sample subtitle/transcript/download jobs run end-to-end.
3. **Given** app starts on Linux, **When** user switches language to Arabic, **Then** RTL layout and Arabic strings render same as Windows.

---

### User Story 2 - Automated Linux build pipeline on every release (Priority: P1)

Maintainer pushes `vX.Y.Z` tag. GitHub Actions builds Windows AND Linux artifacts in parallel and publishes both to release.

**Why this priority**: Without automation, Linux build rots. Must run on same trigger as Windows build to stay in sync.

**Independent Test**: Push test tag → observe Linux workflow run → confirm artifact uploaded.

**Acceptance Scenarios**:

1. **Given** tag matching `v*` pushed, **When** Actions runs, **Then** Linux job completes green and uploads Linux artifact to release.
2. **Given** Linux job fails, **When** maintainer views Actions, **Then** logs clearly indicate failing step (dependency, packaging, signing, upload).
3. **Given** both Windows and Linux jobs succeed, **When** release published, **Then** both artifacts downloadable from release page.

---

### User Story 3 - GitHub Pages site reflects new features and offers Linux download (Priority: P2)

Visitor to Videl GitHub Pages site sees up-to-date feature list (subtitles overhaul, transcript improvements, download UX, vocal-first refactor, etc.) and two prominent download buttons: Windows and Linux. Both link to latest release asset.

**Why this priority**: Discovery + conversion. Site currently lists older features only and offers no Linux path.

**Independent Test**: Open published site in browser, verify new features visible, click Linux button → reach Linux release asset.

**Acceptance Scenarios**:

1. **Given** site visited, **When** page loads, **Then** feature list includes all capabilities present in current `master` (subtitles, transcript, downloads, vocal isolation, AI runtime, updater, multi-language UI).
2. **Given** site visited, **When** user clicks "Download for Linux", **Then** browser starts download of latest Linux artifact (or routes to releases page if direct link uses `/latest`).
3. **Given** site visited on mobile, **When** user views download section, **Then** both buttons remain readable and tappable.

---

### Edge Cases

- New tag pushed but Linux build fails: Windows release still publishes; Linux failure surfaces clearly without blocking Windows.
- User on unsupported Linux distro/version: site or release notes state supported targets; install fails with clear message rather than silent crash.
- App needs system libs (ffmpeg, GPU runtimes) absent on user's machine: app degrades gracefully or instructs user, matching Windows behavior.
- GitHub Pages caches old `index.html`: hard refresh shows new content; no stale asset link points to deleted release.
- Auto-update on Linux: downloads new AppImage and replaces current one in place; must handle read-only or system install paths (fall back to user-writable location or surface clear error).
- Filesystem path differences (case sensitivity, separators, user data dirs): all resource lookups resolve correctly in Linux build.

## Clarifications

### Session 2026-05-18

- Q: Linux packaging format? → A: AppImage (single-file portable executable, no root install)
- Q: AI models & heavy runtime (torch, demucs, rembg) bundling? → A: Match Windows — AppImage ships GUI + ffmpeg; torch/AI packages and models downloaded by app at first use
- Q: Minimum Linux distro / glibc target? → A: Ubuntu 22.04 baseline (glibc 2.35); build on ubuntu-22.04 runner
- Q: Auto-updater behavior on Linux? → A: Full self-update — download and replace AppImage in place
- Q: GitHub Pages download button link target? → A: Direct asset via `/releases/latest/download/<asset>` with stable asset names

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Project MUST produce distributable Linux artifact for Videl GUI app containing all features currently shipped on Windows.
- **FR-002**: GitHub Actions MUST build Linux artifact automatically on same release trigger as Windows installer (tag push `v*`).
- **FR-003**: Linux build job MUST upload its artifact to GitHub Release alongside Windows installer.
- **FR-004**: Linux artifact MUST launch on clean target Linux environment without requiring user to install Python manually. ffmpeg bundled in AppImage. Heavy AI deps (torch, demucs, rembg) and models downloaded by app on first use, mirroring Windows behavior.
- **FR-005**: All app features available on Windows MUST function on Linux: subtitle generation, transcript, media download, vocal isolation/AI runtime, settings persistence, history, language switching (EN/AR with RTL), tutorial, bug reporter, updater notification.
- **FR-006**: File and resource paths inside app MUST resolve correctly on Linux (case-sensitive filesystem, forward-slash paths, user config directory conventions).
- **FR-007**: PyInstaller spec (or equivalent packaging config) MUST include any Linux-specific data files, hidden imports, and binaries needed for frozen Linux build.
- **FR-008**: GitHub Pages site (`gh-pages` branch) MUST be updated to list current feature set of app on `master`.
- **FR-009**: GitHub Pages site MUST display "Download for Linux" call-to-action button visually consistent with existing Windows download button.
- **FR-010**: Linux download button MUST link to stable direct-asset URL pattern `https://github.com/<owner>/<repo>/releases/latest/download/<linux-asset-name>`. Asset name MUST be stable across releases. Windows button MUST follow same pattern.
- **FR-011**: Windows download button MUST continue to function unchanged after site update.
- **FR-012**: Release notes / site copy MUST state which Linux distributions/versions are supported.
- **FR-013**: Linux build failures MUST NOT block publication of Windows artifact when Windows job succeeds.
- **FR-014**: Documentation (README) MUST describe how to install and run Linux build, and how to build it locally.

### Key Entities

- **Linux Release Artifact**: Single downloadable file (or small set) attached to each GitHub Release, runnable on supported Linux desktops; contains app + bundled runtime.
- **Linux CI Workflow Job**: Actions job, peer of existing Windows build job, with own runner, dependencies, packaging step, artifact upload.
- **GitHub Pages Site**: Static `index.html` + assets on `gh-pages` branch; page contains feature list section and per-platform download buttons.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: New tagged release produces working Linux artifact in 100% of green pipeline runs, with no manual maintainer steps.
- **SC-002**: Linux user goes from landing on site to launching installed app in under 5 minutes on supported distro.
- **SC-003**: 100% of features verified working on Windows in same release also pass smoke test on Linux before release marked stable.
- **SC-004**: GitHub Pages site lists every user-facing tool tab present in current app and offers working download link for each supported platform (Windows, Linux).
- **SC-005**: Total CI wall time for tagged release (Windows + Linux in parallel) stays within 1.5× current Windows-only build time.
- **SC-006**: Zero broken links on updated GitHub Pages site at publication time (Windows download, Linux download, repo link, any feature anchors).

## Assumptions

- Target Linux scope: x86_64 desktop, Ubuntu 22.04+ / glibc 2.35+ (covers Debian 12+, Fedora 36+, recent Mint/Pop). ARM and older distros out of scope.
- Packaging format: AppImage (single-file portable executable). See Clarifications.
- GitHub Pages site stays single static `index.html` on `gh-pages` branch; no framework migration in scope.
- Code signing / notarization on Linux not required for first release (unlike Windows installer signing).
- Auto-updater on Linux: full self-update via AppImage replace. See Clarifications.
- FFmpeg and any required GPU/AI runtimes either bundled or documented as prerequisites — same policy as Windows build, adapted to Linux conventions.
