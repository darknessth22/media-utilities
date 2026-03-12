# Feature Specification: PySide6 GUI Migration

**Feature Branch**: `001-qt-migration`  
**Created**: 2026-03-02  
**Status**: Draft  
**Input**: User description: "we need to migrate gui layer to PySide6 (The Enterprise Standard) to make the gui modern aesthetics i need to make the gui as proper desktop app with logo and colors blue aesthetics as well"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Launch Modernized Application (Priority: P1)

As a user, I want the application to launch as a standard, visually appealing desktop application so that it feels professional and trustworthy.

**Why this priority**: A high-quality first impression dictates the perceived reliability of the "Enterprise Standard" tool.

**Independent Test**: Can be fully tested by launching the app and verifying the window frame, application icon (logo), and initial layout visually match the new modern (blue) design system.

**Acceptance Scenarios**:

1. **Given** the application is installed, **When** the user launches the application, **Then** the main window appears with the new custom logo in the title bar and taskbar.
2. **Given** the application is running, **When** the user observes the interface, **Then** they see a modern, blue-themed aesthetic replacing the old Tkinter aesthetic.

---

### User Story 2 - Perform Media Operations (Download/Convert/Trim) (Priority: P1)

As a user, I want to perform all essential media operations (Downloading, Converting, Trimming) using the new interface without any loss of functionality compared to the previous version.

**Why this priority**: The core value of the utility must be preserved during the UI layer migration; a nice-looking app is useless if it cannot perform its primary functions.

**Independent Test**: Can be fully tested by navigating through the main tabs (Download, Convert, Batch Convert, Trim, Document Convert, History) and executing a standard operation (e.g., downloading a short video) to ensure the backend integration is intact.

**Acceptance Scenarios**:

1. **Given** the user is on the Download tab, **When** they enter a valid URL and click "Download", **Then** the progress indicator accurately reflects the download state and a success notification is shown upon completion.
2. **Given** the user drops a file into the application window, **When** the file is recognized, **Then** the application automatically switches to the appropriate tab (e.g., Convert or Trim) and populates the file path.
3. **Given** the application is processing a long task, **When** the user clicks the "Cancel" button, **Then** the operation halts gracefully and the UI remains responsive.

---

### User Story 3 - System Tray & Notifications (Priority: P2)

As a user, I want the application to minimize to the system tray and provide native notifications so that it runs unobtrusively in the background.

**Why this priority**: Essential for a "proper desktop app" experience, though slightly secondary to the core media processing capabilities.

**Independent Test**: Can be tested by minimizing the app to the tray and triggering a background download completion to see the notification.

**Acceptance Scenarios**:

1. **Given** the application window is open and "Quit on close" setting is OFF (default), **When** the user clicks the close ('X') button, **Then** the window hides and the application minimizes to the system tray with a custom icon.
1b. **Given** the application window is open and "Quit on close" setting is ON, **When** the user clicks the close ('X') button, **Then** the application terminates completely.
2. **Given** a background task finishes, **When** the result is ready, **Then** a native desktop notification appears with the result status (Success/Error).
3. **Given** the application is in the tray, **When** the user right-clicks the tray icon and selects "Exit", **Then** the application terminates completely.

## Clarifications

### Session 2026-03-02

- Q: Which Qt binding should the project use: PyQt6 or PySide6? → A: PySide6 (official Qt for Python, LGPL licensed)
- Q: What should clicking the window close (X) button do? → A: Minimize to tray by default, with a Settings checkbox ("Quit on close") to override to true-quit
- Q: What format does the existing History data store use? → A: JSON file (local JSON, no SQLite dependency)
- Q: What blue color palette should the UI use? → A: A refined Slate-Blue palette (see Visual Design System section) — softer than raw Material Blue to reduce eye fatigue during extended sessions, with full dark/light mode token sets.
- Q: What is explicitly out of scope for this migration? → A: Migration + dark mode + settings panel; out of scope: multi-language/i18n, auto-update mechanism, new media features not in current tkinter app

## Visual Design System

This section defines the layout architecture, component patterns, and color design tokens that implementations MUST follow. It is derived from the approved reference mockup (sidebar navigation + card-based content layout).

---

### Layout Architecture

The window is divided into two permanent regions:

```
┌────────────────────────────────────────────────────────────────┐
│  [Custom Title Bar]  App Name          [ ⋯ ] [ – ] [ □ ] [ ✕ ]│
├──────────────┬─────────────────────────────────────────────────┤
│              │  [Section Tab Strip]                            │
│   SIDEBAR    │─────────────────────────────────────────────────│
│  (fixed      │                                                  │
│  ~180 px)    │             MAIN CONTENT AREA                   │
│              │          (scrollable per-tab)                    │
│  [Logo]      │                                                  │
│              │─────────────────────────────────────────────────│
│  Nav Items   │  [ Primary Action Button — full width ]         │
│              ├─────────────────────────────────────────────────┤
│              │  Status Bar                                      │
└──────────────┴─────────────────────────────────────────────────┘
```

**Custom Title Bar** (`QWidget`, `WindowFlags: FramelessWindowHint`):
- Left: App logo icon + app name label
- Right: three-dot overflow menu button, minimize, maximize/restore, close
- Entire bar is the window drag region

**Left Sidebar** (`QWidget`, fixed width 180 px):
- Top: App logo (icon, 40×40 px) + app name
- Body: vertical stack of navigation items — each item is icon (24×24 px SVG) + text label
- Active item: accent-colored left border (3 px) + subtle accent background fill
- No scrollbar; all nav items fit vertically

**Section Tab Strip** (per-section `QTabBar`, top of content area):
- Flat, underline-style active indicator (no raised box tabs)
- Example: "MEDIA DOWNLOAD" | "CARD VIEW"

**Main Content Area**: card-based layout, cards use `border-radius: 10px`, 12 px internal padding

**Primary Action Button**: full-width, `border-radius: 22px` pill shape, accent background, placed at bottom of content above the status bar

**Status Bar** (`QStatusBar`): single-line, shows current operation state or "Ready"

---

### UI Component Patterns

| Component | Shape | Notes |
|---|---|---|
| URL / text input | Pill (`border-radius: 20px`) | Placeholder text in muted color |
| Option chip (quality, format) | Pill (`border-radius: 16px`) | Accent-filled when selected, outline when unselected |
| Radio button | Custom circle | Accent fill on selected state |
| Progress bar | Rounded rect | Accent color fill, track in surface-raised color |
| Primary button | Full-width pill | Accent background, white text |
| Icon-only button | Circle or rounded square | Used for Browse, Check Formats |
| Cards / panels | Rounded rect (`border-radius: 10px`) | Surface color, 1 px border |

---

### Color Design Tokens

Rationale: raw electric/saturated blue (#2196F3) causes eye fatigue during long media-processing sessions. The palette below uses a calmer slate-blue accent with high-contrast neutrals. Only one accent hue is used across the whole app; semantic colors (success/error/warning) are the only others.

#### Dark Mode (default)

| Token | Hex | Usage |
|---|---|---|
| `--bg-base` | `#0D1117` | Window background, title bar |
| `--bg-sidebar` | `#161B22` | Sidebar background |
| `--bg-surface` | `#1C2333` | Card / panel background |
| `--bg-surface-raised` | `#21262D` | Elevated card, input background |
| `--accent-primary` | `#3B82F6` | Active nav, primary button, selected chips, progress fill |
| `--accent-hover` | `#2563EB` | Button/chip hover state |
| `--accent-subtle` | `rgba(59,130,246,0.12)` | Active nav item background fill |
| `--accent-border` | `rgba(59,130,246,0.40)` | Active nav left-border, focused input ring |
| `--text-primary` | `#E6EDF3` | Main body text |
| `--text-secondary` | `#8B949E` | Labels, secondary info |
| `--text-muted` | `#484F58` | Placeholder, disabled text |
| `--border` | `#30363D` | Card borders, dividers |
| `--status-success` | `#3FB950` | Completed task indicator |
| `--status-error` | `#F85149` | Failed task indicator |
| `--status-warning` | `#D29922` | In-progress / warning indicator |

#### Light Mode

| Token | Hex | Usage |
|---|---|---|
| `--bg-base` | `#F6F8FA` | Window background |
| `--bg-sidebar` | `#FFFFFF` | Sidebar background |
| `--bg-surface` | `#FFFFFF` | Card / panel background |
| `--bg-surface-raised` | `#EFF6FF` | Elevated card, input background |
| `--accent-primary` | `#2563EB` | Active nav, primary button, selected chips |
| `--accent-hover` | `#1D4ED8` | Button/chip hover state |
| `--accent-subtle` | `rgba(37,99,235,0.08)` | Active nav item background fill |
| `--accent-border` | `rgba(37,99,235,0.35)` | Active nav left-border, focused input ring |
| `--text-primary` | `#0D1117` | Main body text |
| `--text-secondary` | `#57606A` | Labels, secondary info |
| `--text-muted` | `#8C959F` | Placeholder, disabled text |
| `--border` | `#D0D7DE` | Card borders, dividers |
| `--status-success` | `#1A7F37` | Completed task indicator |
| `--status-error` | `#CF222E` | Failed task indicator |
| `--status-warning` | `#9A6700` | In-progress / warning indicator |

> **Rule**: No additional accent colors are to be introduced. All interactive highlights must use `--accent-primary` or its derivatives. Status colors are used exclusively for state feedback (progress, history rows), never for decoration.

---

### QSS Implementation Notes

- All tokens MUST be implemented as two QSS stylesheet strings (`DARK_THEME_QSS`, `LIGHT_THEME_QSS`) swapped at runtime via `QApplication.setStyleSheet()`.
- Sidebar active state is toggled by setting a custom Qt property `active=true` on the nav button and refreshing its style via `style().unpolish()` / `polish()`.
- Font: system default sans-serif; do not hard-code a font family. Set base font size to 13 px.
- Icon assets MUST be SVG so they can be tinted programmatically to match the active/inactive text token per theme.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST replace all existing `tkinter` and `ttkbootstrap` UI components with `PySide6` equivalents.
- **FR-002**: The UI MUST implement the layout architecture and QSS styling system defined in the **Visual Design System** section, using the Slate-Blue design token sets for dark and light modes. Hard-coded hex values outside those token tables are not permitted.
- **FR-003**: The application MUST display a custom application logo in the title bar, taskbar/dock, and system tray.
- **FR-004**: System MUST maintain full integration with the existing backend logic (`core` module functions like `downloader`, `converter`, `document` conversion).
- **FR-005**: All existing UI tabs MUST be recreated: Download, Convert, Batch Convert, Trim, Document Convert, History, and a new **Settings** tab.
- **FR-009**: The Settings tab MUST provide controls for: "Quit on close" toggle, dark/light theme toggle, and default file paths configuration.
- **FR-010**: The system MUST support a dark/light theme toggle via QSS stylesheet switching, using the `DARK_THEME_QSS` / `LIGHT_THEME_QSS` token sets defined in the Visual Design System. The existing `gui/theme.py` (`darkdetect`-based) MUST be replaced; OS dark-mode detection MUST use `QGuiApplication.styleHints().colorScheme()` instead.
- **FR-006**: The system MUST support native Drag-and-Drop functionality for media files onto the application window to prepopulate input fields.
- **FR-007**: The system MUST implement asynchronous operation handling (via PySide6 `QThread` / signals-slots) to ensure the UI does not freeze during downloads or conversions.
- **FR-008**: The system MUST provide native system tray integration and desktop notifications upon task completion or failure. The existing `pystray`-based `core/tray.py` MUST be replaced with `QSystemTrayIcon`; `pystray` is removed from requirements.
- **FR-011**: The existing VLC-based visual trimmer (`gui/video_trimmer.py`, `python-vlc`) MUST be replaced with a `QWidget` using `PySide6.QtMultimedia` (`QMediaPlayer` + `QVideoWidget`). The fallback behaviour (text-only time inputs when video preview is unavailable) MUST be preserved.

### Migration Caveats

These are concrete, file-level breaking changes implied by this migration. An implementation that ignores any of these will encounter runtime errors or missing functionality.

| # | Area | Current (Tkinter) | Required (PySide6) | File(s) affected |
|---|---|---|---|---|
| M-1 | **Settings model** | `UserSettings` has no `quit_on_close` field | Add `quit_on_close: bool = False` to `UserSettings` dataclass; bump `version` to 2; add migration path in `SettingsManager.load()` | `core/settings.py` |
| M-2 | **System tray** | `pystray`-based `SystemTrayIntegration` class | Replace entirely with `QSystemTrayIcon` + `QMenu`; remove `pystray` from `requirements.txt` | `core/tray.py` |
| M-3 | **Drag-and-drop** | `tkinterdnd2` — `DndHandler.process_drop(raw_data: str)` parses a space/curly-brace delimited string | Replace with `QDropEvent.mimeData().urls()` — the `DroppedFile` dataclass and tab-routing logic in `gui/dnd_handler.py` are reusable, but `process_drop()` must be rewritten | `gui/dnd_handler.py` |
| M-4 | **Theme detection** | `darkdetect` polling thread in `gui/theme.py` | Use `QGuiApplication.styleHints().colorScheme()` + `QStyleHints.colorSchemeChanged` signal; remove `darkdetect` from requirements | `gui/theme.py` |
| M-5 | **SVG icon assets** | Only `assets/icons/sun.png`, `moon.png`, `settings.png` exist (PNG) | Create SVG versions of all nav icons (Dashboard, Media Download, Convert Media, Trim Media, Document Convert, History, Settings) plus the existing toggle icons. PNGs are **not** sufficient for QSS tinting | `assets/icons/` |
| M-6 | **Frameless window resize** | OS provides native resize border | `FramelessWindowHint` removes OS resize — add a `QSizeGrip` in the status-bar area and override `mousePressEvent` / `mouseMoveEvent` on the title bar for dragging | `gui/app.py` (new `MainWindow`) |
| M-7 | **Build tooling** | `media_util_gui.spec` lists tkinter hidden imports (`tkinterdnd2`, `ttkbootstrap`, `python-vlc`) | Update PyInstaller spec: remove tkinter imports, add `PySide6`, add `PySide6.QtMultimedia`; update `build_executable.py` and `requirements.txt` accordingly | `media_util_gui.spec`, `build_executable.py`, `requirements.txt` |

### Key Entities

- **Application Window (`QMainWindow`)**: The central routing point containing the tabbed widget and status bar.
- **Media Worker (`QThread`)**: The bridge entity managing backend operations synchronously without blocking the GUI.
- **History Data Source**: A local JSON file history store, bound to a custom `QAbstractTableModel` (or `QListWidget`) for Qt's Model/View architecture.

### Out of Scope

- Multi-language / internationalization (i18n)
- Auto-update mechanism
- New media processing features not present in the current tkinter application
- Mobile or web interface variants

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The application launches without encountering any `tkinter` import traces or related errors.
- **SC-002**: 100% of existing functional workflows (downloading, converting, trimming) succeed when initiated from the new Qt interface.
- **SC-003**: UI thread responsiveness during long-running tasks (like large video conversions) is maintained, with no "Application Not Responding" operating system warnings.
- **SC-004**: The overall memory footprint and startup time remain within 15% of the legacy Tkinter version.
