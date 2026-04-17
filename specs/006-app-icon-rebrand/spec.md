# Feature Specification: Custom App Icon & Rebrand to Medix

**Feature Branch**: `006-app-icon-rebrand`
**Created**: 2026-03-27
**Status**: Draft
**Input**: User description: "Add a custom application icon visible in-app and taskbar, replacing the default Python icon. Rename the application from MediaUtility to Medix. Provide steps for the user to supply their own icon file."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Replace Default Python Icon with Custom Icon (Priority: P1)

As a user, I want the application to display a custom branded icon instead of the default Python icon, both in the window title bar and in the operating system taskbar/system tray, so the application looks professional and is easy to identify among other running programs.

**Why this priority**: The default Python icon makes the application look unfinished and hard to distinguish from other Python apps. A custom icon is the most visible branding element.

**Independent Test**: Launch the application and verify the custom icon appears in the window title bar, taskbar, and system tray. Confirm the default Python icon is no longer visible anywhere.

**Acceptance Scenarios**:

1. **Given** the application is installed with a custom icon file, **When** the user launches the application, **Then** the custom icon is displayed in the window title bar
2. **Given** the application is running, **When** the user looks at the operating system taskbar, **Then** the custom icon is displayed instead of the default Python icon
3. **Given** the application has a system tray icon, **When** the user looks at the system tray, **Then** the custom icon is displayed there as well
4. **Given** the application is built as a standalone executable, **When** the user views the executable file in the file explorer, **Then** the custom icon is shown as the file icon

---

### User Story 2 - Rename Application to Medix (Priority: P1)

As a user, I want the application to be called "Medix" instead of "MediaUtility" everywhere it appears, so the branding is consistent and the app has a distinct identity.

**Why this priority**: The name is a core branding element that appears throughout the application. It must be consistent across all touchpoints for a professional user experience.

**Independent Test**: Search for all occurrences of the old name in the application UI, window titles, and build artifacts. Verify all references show "Medix" instead of "MediaUtility".

**Acceptance Scenarios**:

1. **Given** the application is launched, **When** the user views the window title, **Then** it displays "Medix" (not "MediaUtility")
2. **Given** the application is running, **When** the user views the taskbar entry, **Then** the tooltip/label shows "Medix"
3. **Given** the application is built as a standalone executable, **When** the user views the executable file name, **Then** it reflects the "Medix" branding
4. **Given** the application has a system tray icon, **When** the user hovers over the tray icon, **Then** the tooltip shows "Medix"

---

### User Story 3 - Icon Setup Instructions (Priority: P2)

As a developer or user who wants to customize the icon, I want clear steps on how to prepare and place a custom icon file so the application uses it, so I can easily brand the app with my own artwork.

**Why this priority**: Users need to know how to supply their own icon. Without instructions, the icon replacement process is unclear and may result in broken or missing icons.

**Independent Test**: Follow the documented steps with a new icon file and verify the application displays the new icon correctly.

**Acceptance Scenarios**:

1. **Given** the user has an image file they want to use as the app icon, **When** they follow the documented steps, **Then** the application displays their chosen icon
2. **Given** the user provides an icon in a common image format (PNG, ICO), **When** the application loads, **Then** it accepts the icon without errors
3. **Given** the user provides an icon with incorrect dimensions or format, **When** the application loads, **Then** it falls back gracefully to a default icon

---

### Edge Cases

- What happens if the icon file is missing or corrupted at launch time? The application should fall back to a default embedded icon or the framework default, not crash.
- What happens if the icon file is an unsupported format? The application should ignore it and use a fallback.
- What happens if the user provides a very large or very small icon? The application should scale it appropriately for each context (title bar, taskbar, system tray, executable).
- What happens to existing references to the old name "MediaUtility" in configuration files or saved history? They should still be readable (backward compatibility for stored data).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Application MUST display a custom icon in the window title bar when launched
- **FR-002**: Application MUST display the custom icon in the operating system taskbar
- **FR-003**: Application MUST display the custom icon in the system tray
- **FR-004**: Built executable MUST use the custom icon as its file icon
- **FR-005**: Application MUST display "Medix" as the application name in the window title
- **FR-006**: Application MUST display "Medix" in the taskbar tooltip/label
- **FR-007**: Application MUST display "Medix" in the system tray tooltip
- **FR-008**: Build process MUST produce an executable named with the "Medix" branding
- **FR-009**: Application MUST gracefully handle a missing or corrupted icon file by falling back to a default
- **FR-010**: Application MUST support ICO format (Windows) and PNG format (cross-platform) for icons
- **FR-011**: The icon file location MUST be documented so users know where to place a replacement icon
- **FR-012**: Existing user configuration and history data MUST remain accessible after the rename (backward compatibility)

### Key Entities

- **App Icon**: The image file used for branding across window, taskbar, tray, and executable. Stored as a project asset in a known location.
- **App Identity**: The name "Medix" used across all user-facing labels, titles, tooltips, and build artifacts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of application windows display the custom icon instead of the default Python icon
- **SC-002**: The name "Medix" appears in all user-facing locations (window title, taskbar, tray tooltip, executable name) with zero references to "MediaUtility"
- **SC-003**: A user following the icon setup instructions can replace the icon in under 5 minutes
- **SC-004**: Application launches without error when the custom icon file is missing, using a fallback icon
- **SC-005**: The built executable displays the custom icon when viewed in the operating system file explorer

## Assumptions

- The user will provide their own icon artwork; this spec does not cover icon design or creation
- The primary target platform is Windows (ICO format for executable icon); PNG is acceptable for in-app usage
- The rename is cosmetic/branding only; internal module names, file names, and repository name remain unchanged unless explicitly requested
- The system tray feature already exists in the application
