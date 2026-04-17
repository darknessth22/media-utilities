# Research: Custom App Icon & Rebrand to Medix

**Feature Branch**: `006-app-icon-rebrand`
**Date**: 2026-03-27

## Research Findings

### 1. PySide6 Application Icon Propagation

**Decision**: Use `QApplication.setWindowIcon(QIcon("path"))` in `main.py` immediately after app creation. This propagates the icon to all windows, taskbar entries, and serves as the default tray icon.

**Rationale**: PySide6/Qt's `setWindowIcon()` at the application level is the single-point-of-control for all window-associated icons. Individual windows inherit this unless overridden. This avoids setting icons in multiple places.

**Alternatives considered**:
- Setting `setWindowIcon()` per-window: Redundant — app-level setting covers all windows.
- Using `.setIcon()` on QSystemTrayIcon separately: Already done in `core/tray.py` via `_make_tray_icon()`. The tray icon can continue using its own SVG rendering for the colored icon, or switch to the shared app icon.

### 2. Icon File Format for Windows Executable

**Decision**: Keep `icon.ico` at project root for PyInstaller. The ICO file must contain multiple sizes (256, 128, 64, 32, 16) for proper display in Windows Explorer, taskbar, and title bars.

**Rationale**: PyInstaller's `--icon` parameter on Windows requires `.ico` format. Multi-size ICO files ensure crisp rendering at all DPI scales and display contexts.

**Alternatives considered**:
- PNG only: PyInstaller on Windows does not accept PNG for the executable icon.
- Single-size ICO: Works but appears blurry at non-native sizes.

### 3. Runtime Icon Format

**Decision**: Use PNG (`assets/icons/app-icon.png`) for the runtime application icon loaded via `QIcon`. Keep the existing `dashboard.svg` as the in-app logo graphic (title bar logo, sidebar logo) separate from the application/taskbar icon.

**Rationale**: PNG is universally supported by Qt on all platforms. Separating the app icon (PNG, for OS-level taskbar/title bar) from the in-app logo (SVG, for custom UI elements) allows independent customization.

**Alternatives considered**:
- SVG for app icon: QIcon supports SVG but some platforms render it inconsistently for taskbar icons. PNG is safer.
- Replace dashboard.svg entirely: Unnecessary — the dashboard.svg serves a different purpose (in-app decorative logo with color tinting).

### 4. Rename Scope Analysis

**Decision**: Cosmetic rename only. Change all user-facing strings from "Media Utility" / "MediaUtility" to "Medix". Internal module names (`media_util_gui.py`, `media_util_gui.spec`), repository name, and Python package structure remain unchanged.

**Rationale**: Internal file/module renaming would break imports, build scripts, and git history without user benefit. The spec explicitly scopes the rename as branding-only.

**Alternatives considered**:
- Full rename including files: High risk, breaks existing tooling, not requested.
- Rename config directory: Would orphan existing user settings — backward compatibility violated.

### 5. Backward Compatibility for Settings

**Decision**: Keep the same `organizationName` ("Omniclouds") in `QApplication.setOrganizationName()`. The `applicationName` change from "Media Utility" to "Medix" affects Qt's `QStandardPaths` on some platforms (settings storage location). Since this project uses its own `SettingsManager` with a JSON config in platform app data, the Qt application name change does not affect config file location.

**Rationale**: The project's `SettingsManager` (in `core/settings.py`) manages its own config path independently of Qt's standard paths, so renaming the application name in Qt does not break existing settings.

**Alternatives considered**:
- Maintain old applicationName for backward compat: Unnecessary since settings are managed independently.

### 6. Fallback Behavior for Missing Icon

**Decision**: If `assets/icons/app-icon.png` is missing at runtime, `QIcon()` constructed with a non-existent path returns a null/empty icon. PySide6 then uses the OS default window icon. No crash, no special handling needed.

**Rationale**: Qt's built-in behavior already handles this gracefully. Adding explicit fallback code would violate YAGNI (Constitution Principle V).

**Alternatives considered**:
- Explicit file-exists check with fallback to bundled resource: Over-engineering for a scenario where the bundled asset should always be present.
