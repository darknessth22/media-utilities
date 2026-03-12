
<!--
Sync Impact Report
===========================
Version change: N/A → 1.0.0 (initial ratification)
Modified principles: N/A (all new)
Added sections:
  - Core Principles (5 principles)
  - Technology Stack & Dependencies
  - Development Workflow
  - Governance
Removed sections: None
Templates requiring updates:
  - .specify/templates/plan-template.md ✅ compatible (Constitution Check section is generic)
  - .specify/templates/spec-template.md ✅ compatible (no constitution-specific references)
  - .specify/templates/tasks-template.md ✅ compatible (no constitution-specific references)
  - .specify/templates/commands/ — no command files exist yet
Follow-up TODOs: None
===========================
-->

# Media Utilities Constitution

## Core Principles

### I. Modular Architecture

All domain logic MUST be separated from presentation code.
Each functional domain (downloading, conversion, trimming,
document processing) MUST reside in its own module under `core/`.
Shared utilities MUST be isolated in `utils/`.
The GUI layer (`gui/`) MUST depend on `core/` — never the reverse.
New features MUST be added as new modules or extensions to existing
ones; monolithic single-file additions are not permitted.

**Rationale**: The project evolved from a single-file script
(`media_util_gui.py`) into a modular layout. Maintaining this
separation ensures each domain can be developed, tested, and
maintained independently.

### II. Cross-Platform Compatibility

The application MUST run on Windows, macOS, and Linux without
platform-specific code paths unless absolutely necessary.
External tool dependencies (e.g., FFmpeg) MUST be detected at
runtime with clear, user-facing error messages when missing.
File paths MUST use platform-agnostic APIs (`pathlib` or `os.path`).
The Windows executable build pipeline (`build_executable.py`) MUST
be maintained alongside the Python source distribution.

**Rationale**: Media Utilities serves users on all major desktop
platforms. Platform assumptions lead to silent failures that are
difficult for end users to diagnose.

### III. User Experience First

Every feature MUST be accessible via the GUI with intuitive controls
and clear labeling. Long-running operations MUST provide progress
feedback and support cancellation. Error messages MUST be
user-friendly and suggest concrete resolution steps. The CLI
interface MUST remain available for scripting and automation use
cases.

**Rationale**: The primary audience includes non-technical users
who rely on the GUI. A confusing or unresponsive interface
negates the value of the underlying functionality.

### IV. Quality & Testing

All new features MUST include manual or automated test coverage
before release. Critical paths (download, convert, trim, document
conversion) MUST have regression tests. Dependencies MUST be
pinned to known-good versions in `requirements.txt`. The
application MUST validate dependencies on startup and inform
users of any missing components.

**Rationale**: Media operations involve external tools and diverse
file formats. Without testing discipline, regressions go unnoticed
until users encounter them in production.

### V. Simplicity & YAGNI

New abstractions MUST justify their existence — prefer direct,
readable code over premature generalization. Features MUST NOT be
added speculatively; each addition MUST address a concrete user
need. Code duplication is acceptable when the alternative is a
premature abstraction. Configuration MUST have sensible defaults;
advanced options are optional, not mandatory.

**Rationale**: A utility tool succeeds by being straightforward.
Over-engineering increases maintenance burden without proportional
user benefit.

## Technology Stack & Dependencies

- **Runtime**: Python 3.10+ (3.12 recommended)
- **GUI Framework**: PySide6 (official Qt for Python, LGPL licensed)
  with PySide6.QtMultimedia for media playback
- **Media Processing**: FFmpeg (external, MUST be on PATH or in
  project directory)
- **Downloading**: yt-dlp for video/audio, spotdl 4.2.0 for
  Spotify metadata + YouTube audio
- **Image Processing**: Pillow, pillow-heif (HEIC support)
- **Document Conversion**: PyMuPDF (PDF), python-docx (DOCX),
  openpyxl (XLSX), python-pptx (PPTX)
- **Distribution**: PyInstaller for Windows executable builds
- **Version Pinning**: All dependencies MUST be listed in
  `requirements.txt` with minimum version constraints. spotdl
  MUST remain pinned to an exact version due to API instability.

Adding a new dependency MUST be justified by a concrete feature
requirement. Standard-library alternatives MUST be preferred when
they meet the need.

## Development Workflow

- All changes MUST be developed on feature branches off `master`.
- Commit messages MUST be descriptive and follow conventional
  style (e.g., `feat:`, `fix:`, `docs:`, `refactor:`).
- All changes MUST be tested manually at minimum before merging
  to `master`. Automated tests are strongly encouraged.
- `README.md` and `SETUP.md` MUST be updated when user-facing
  features or setup steps change.
- The legacy single-file entry point (`media_util_gui.py`) MUST
  remain functional until explicitly deprecated in a future
  major release.

## Governance

This constitution supersedes ad-hoc practices and serves as the
authoritative reference for project standards and decision-making.

**Amendment Procedure**:
1. Propose the change with a rationale.
2. Document the amendment in this file with an updated version.
3. Update dependent templates if the change affects spec, plan,
   or task generation workflows.
4. Commit with message: `docs: amend constitution to vX.Y.Z`.

**Versioning Policy**: This constitution follows semantic
versioning:
- **MAJOR**: Principle removal or backward-incompatible
  redefinition.
- **MINOR**: New principle or materially expanded guidance.
- **PATCH**: Clarifications, wording, or non-semantic
  refinements.

**Compliance Review**: All pull requests and code reviews SHOULD
verify that changes align with the principles above. Violations
MUST be documented and justified in the PR description.

**Version**: 1.0.0 | **Ratified**: 2026-02-19 | **Last Amended**: 2026-02-19
