# Feature Specification: Settings and Theme Icons

**Feature Branch**: `001-settings-theme-icons`  
**Created**: 2026-03-01  
**Status**: Draft  
**Input**: User description: "i want the settings and the dark mode to be icons not on bottom right line"

## User Scenarios & Testing *(mandatory)*

## Clarifications
### Session 2026-03-01
- Q: Where should the new icons be positioned? → A: Top-Right Corner

### User Story 1 - Toggle Theme via Icon (Priority: P1)

As a user, I want to click an icon to toggle between light and dark mode so that the interface feels more modern and takes up less screen space than a text button.

**Why this priority**: Theme toggling is a frequently used accessibility and preference feature.

**Independent Test**: Can be fully tested by clicking the new theme icon and verifying the application theme changes immediately.

**Acceptance Scenarios**:

1. **Given** the application is in Light Mode, **When** the user clicks the Theme Icon, **Then** the application switches to Dark Mode and the icon updates to reflect the new state.
2. **Given** the application is in Dark Mode, **When** the user clicks the Theme Icon, **Then** the application switches to Light Mode and the icon updates to reflect the new state.
3. **Given** the user hovers over the Theme Icon, **When** the mouse pointer is over the icon, **Then** a tooltip appears explaining the action (e.g., "Toggle Theme").

---

### User Story 2 - Access Settings via Icon (Priority: P1)

As a user, I want to access the Settings menu by clicking a gear/settings icon rather than a text link, so that the main interface is cleaner.

**Why this priority**: Settings access is critical for application configuration.

**Independent Test**: Can be fully tested by clicking the settings icon and verifying the Settings panel or dialog opens correctly.

**Acceptance Scenarios**:

1. **Given** the main application window is open, **When** the user clicks the Settings Icon, **Then** the Settings dialog/panel opens.
2. **Given** the user hovers over the Settings Icon, **When** the mouse pointer is over the icon, **Then** a tooltip appears explaining the action (e.g., "Settings").

---

### Edge Cases

- What happens when a custom OS theme is forced? (The manual toggle should override or work alongside it).
- How the icons scale or display on high-DPI (4K) monitors.
- Ensuring the icons remain visible and have sufficient contrast in both light and dark modes.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display a graphical icon for accessing Settings instead of text.
- **FR-002**: System MUST display a graphical icon for toggling the application theme (Dark/Light mode) instead of text.
- **FR-003**: System MUST provide tooltips on hover for both icons to ensure accessibility.
- **FR-004**: System MUST position the new icons in a designated area (Top-Right corner of the window).
- **FR-005**: System MUST update the theme icon visually depending on the active state (e.g., a moon icon for dark mode, a sun icon for light mode).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Icons replace the existing text-based "bottom right line" controls without loss of functionality.
- **SC-002**: Visual clutter on the main screen is reduced by removing text-based labels.
- **SC-003**: Tooltips reliably appear within a short duration of hovering over the new icons.
- **SC-004**: Users can successfully identify and use the new icons for theme toggling and settings access on their first attempt without instructions.
