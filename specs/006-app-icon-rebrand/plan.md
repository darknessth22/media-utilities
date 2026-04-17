# Implementation Plan: Custom App Icon & Rebrand to Medix

**Branch**: `006-app-icon-rebrand` | **Date**: 2026-03-27 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/006-app-icon-rebrand/spec.md`

## Summary

Replace the default Python icon with a user-supplied custom icon across all surfaces (window title bar, taskbar, system tray, executable) and rename the application from "Media Utility" / "MediaUtility" to "Medix" in all user-facing locations, build artifacts, and installer scripts. The icon is bundled as a project asset at a documented location; missing icon triggers graceful fallback.

## Technical Context

**Language/Version**: Python 3.10+ (3.12 recommended)
**Primary Dependencies**: PySide6 (GUI framework), Pillow (icon generation in build script), PyInstaller (executable packaging)
**Storage**: N/A (icon is a static asset bundled with the application)
**Testing**: Manual verification + pytest where applicable
**Target Platform**: Windows (primary), macOS and Linux (secondary — cross-platform per constitution)
**Project Type**: Desktop application
**Performance Goals**: N/A (no runtime performance impact — icon loading is a one-time startup operation)
**Constraints**: Icon must be loadable by PySide6's QIcon/QPixmap; ICO format required for Windows executable; existing config/history data must remain accessible after rename
**Scale/Scope**: ~22 code locations to update across 5 files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Modular Architecture | PASS | No new modules needed; changes are to existing GUI/core/build files. Icon asset lives in `assets/` as expected. |
| II. Cross-Platform Compatibility | PASS | PySide6 QIcon handles cross-platform icon loading natively. ICO for Windows exe, PNG/SVG for runtime. Platform-agnostic paths used. |
| III. User Experience First | PASS | Custom icon improves visual identity. Fallback behavior prevents crashes on missing icon. |
| IV. Quality & Testing | PASS | Manual test checklist covers all icon surfaces. Automated test can verify icon file exists. |
| V. Simplicity & YAGNI | PASS | Direct string replacements and asset swap — no new abstractions introduced. |

All gates pass. No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/006-app-icon-rebrand/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── spec.md              # Feature specification
├── data-model.md        # Phase 1 output (minimal — no data entities)
├── quickstart.md        # Phase 1 output (icon setup guide)
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```text
media-utilities/
├── main.py                     # App name: "Media Utility" → "Medix" (line 44)
├── build_executable.py         # Exe name, installer strings, icon path (~15 locations)
├── media_util_gui.spec         # PyInstaller spec: exe name, icon reference
├── assets/
│   └── icons/
│       ├── dashboard.svg       # Current app logo (SVG, used in title bar + sidebar)
│       ├── app-icon.ico        # NEW: Custom ICO file for Windows executable
│       └── app-icon.png        # NEW: Custom PNG file for runtime window/taskbar/tray icon
├── icon.ico                    # Existing ICO at root (update or replace)
├── gui/
│   └── app.py                  # Title bar label, sidebar label, tray notifications (~5 locations)
├── core/
│   └── tray.py                 # Tray tooltip (line 66)
└── media_util_gui.py           # Legacy entry point (docstring only)
```

**Structure Decision**: No new directories or modules. Changes are confined to existing files plus one new icon asset file. The user supplies their icon file and places it at the documented location.

## Complexity Tracking

> No constitution violations — table not needed.

## Change Map

### File: `main.py`
| Line | Current | New |
|------|---------|-----|
| 1 | `"""Entry point for Media Utility (PySide6).` | `"""Entry point for Medix (PySide6).` |
| 44 | `app.setApplicationName("Media Utility")` | `app.setApplicationName("Medix")` |
| (new) | — | Set `app.setWindowIcon(QIcon(...))` after app creation to set taskbar/window icon globally |

### File: `gui/app.py`
| Line | Current | New |
|------|---------|-----|
| 151 | `self._title = QLabel("Media Utility")` | `self._title = QLabel("Medix")` |
| 620 | `app_name = QLabel("Media Utility")` | `app_name = QLabel("Medix")` |
| 822 | `"Media Utility — Error" / "Media Utility"` | `"Medix — Error" / "Medix"` |
| 988 | `"Media Utility",` | `"Medix",` |

### File: `core/tray.py`
| Line | Current | New |
|------|---------|-----|
| 66 | `self._tray.setToolTip("Media Utility")` | `self._tray.setToolTip("Medix")` |

### File: `build_executable.py`
| Location | Current | New |
|----------|---------|-----|
| Docstring | "Media Utility GUI" | "Medix" |
| Inno Setup: AppName | "Media Utility" | "Medix" |
| Inno Setup: AppPublisher | "Media Utility Developer" | "Medix Developer" |
| Inno Setup: DefaultDirName | `{autopf}\\MediaUtility` | `{autopf}\\Medix` |
| Inno Setup: DefaultGroupName | "Media Utility" | "Medix" |
| Inno Setup: shortcuts | "Media Utility" | "Medix" |
| Exe filename refs | "MediaUtility" | "Medix" |
| Print statements | "MediaUtility" | "Medix" |

### File: `media_util_gui.spec`
| Line | Current | New |
|------|---------|-----|
| 110 | `name='MediaUtility'` | `name='Medix'` |
| 123 | `icon='icon.ico'` | `icon='icon.ico'` (keep — file is the same) |
| 134 | `name='MediaUtility'` | `name='Medix'` |

### File: `media_util_gui.py`
| Location | Current | New |
|----------|---------|-----|
| Docstring | Any "Media Utility" references | "Medix" |

### New: Icon Setup
- User places their custom `.ico` file at `icon.ico` (project root) for the executable build
- User places a custom PNG/SVG at `assets/icons/app-icon.png` (or replaces `dashboard.svg`) for runtime display
- `main.py` sets `app.setWindowIcon()` using the icon from `assets/icons/` — this propagates to window title bar, taskbar, and serves as fallback for tray
- Fallback: if icon file not found, QIcon returns a null icon and PySide6 uses the OS default (no crash)

## Icon Setup Steps (for user documentation)

1. **Prepare your icon**: Create or obtain an icon image. For best results:
   - Windows executable icon: `.ico` format with sizes 256x256, 128x128, 64x64, 32x32, 16x16
   - In-app icon: `.png` format, 256x256 or larger (will be scaled automatically)

2. **Place the executable icon**: Copy your `.ico` file to the project root as `icon.ico` (replaces the existing file). This is used by PyInstaller when building the `.exe`.

3. **Place the in-app icon**: Copy your `.png` file to `assets/icons/app-icon.png`. This is loaded at runtime for the window title bar, taskbar, and system tray.

4. **Rebuild** (if distributing as exe): Run `python build_executable.py` to create a new executable with the embedded icon.

5. **Verify**: Launch the application and check that your icon appears in the title bar, taskbar, and system tray.
