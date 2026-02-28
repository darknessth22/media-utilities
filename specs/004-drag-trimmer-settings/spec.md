# Feature Specification: Drag-Drop, Rich Trimmer & Global Settings

**Feature Branch**: `004-drag-trimmer-settings`
**Created**: 2026-02-28
**Status**: Draft
**Input**: User description: "Drag and Drop Support, Rich Visual Media Trimmer, and Global Settings & Persistence"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Drag and Drop File Loading (Priority: P1)

A user has a video file or PDF document on their desktop. Instead of clicking Browse and navigating through folder dialogs, they drag the file directly onto the application window. The app recognizes the file type, automatically switches to the appropriate tab (e.g., Trim Media for videos, Document Convert for PDFs), and loads the file ready for processing.

**Why this priority**: This is a fundamental UX improvement that reduces friction for the most common user action (loading files). It applies across all file types and all tabs, providing immediate value to every user.

**Independent Test**: Can be fully tested by dragging any supported file onto the app window and verifying the correct tab activates with the file loaded. Delivers immediate workflow improvement.

**Acceptance Scenarios**:

1. **Given** the app is running on the main window, **When** a user drags a video file (.mp4, .mkv, .avi, .mov, .webm, .flv) onto the window, **Then** the Trim Media tab activates and the file path appears in the file input field.
2. **Given** the app is running, **When** a user drags a PDF file onto the window, **Then** the Document Convert tab activates and the PDF path appears in the file input field.
3. **Given** the app is running, **When** a user drags an image file (.jpg, .png, .heic) onto the window, **Then** the Convert Media tab activates and the image path appears in the file input field.
4. **Given** the app is running, **When** a user drags an audio file (.mp3, .wav, .aac) onto the window, **Then** the Trim Media tab activates and the file path appears in the file input field.
5. **Given** the app is running, **When** a user drags a DOCX file onto the window, **Then** the Document Convert tab activates and the file path appears in the input field.
6. **Given** the app is running, **When** a user drags an unsupported file type onto the window, **Then** a user-friendly message appears indicating the file type is not supported.
7. **Given** the app is running, **When** a user drags multiple files onto the window, **Then** the Batch Convert tab activates (if all files are the same type) or a message indicates only single-file drag is supported for mixed types.

---

### User Story 2 - Visual Timeline Trimmer (Priority: P2)

A user wants to trim a video but doesn't know the exact timestamps. Instead of manually scrubbing through the video in an external player and typing timestamps, they see an embedded mini video player with a visual timeline. They drag handles on the timeline to set start and end points while seeing a live preview, making trimming intuitive and accurate.

**Why this priority**: This transforms the trimming experience from guesswork to visual precision. It's a significant UX enhancement but requires more complex implementation than drag-drop.

**Independent Test**: Can be fully tested by loading a video file in the Trim tab, using the timeline handles to select a clip range, previewing the selection, and trimming. Delivers visual trimming capability.

**Acceptance Scenarios**:

1. **Given** a video file is loaded in the Trim tab, **When** the file loads, **Then** a mini video player appears showing the first frame with playback controls (play/pause, mute).
2. **Given** a video is loaded in the player, **When** the video metadata loads, **Then** a horizontal timeline scrubber bar appears below the player showing the full video duration.
3. **Given** the timeline is displayed, **When** the user views the timeline, **Then** two draggable handles are visible (green for start, red for end) positioned at 0:00 and end of video respectively.
4. **Given** the timeline handles are visible, **When** the user drags the start handle, **Then** the video seeks to that position and the start time updates in real-time.
5. **Given** the timeline handles are visible, **When** the user drags the end handle, **Then** the end time updates and the handle cannot be dragged before the start handle.
6. **Given** start and end handles are positioned, **When** the user clicks Play, **Then** the video plays only the selected segment and loops back to the start position.
7. **Given** a clip range is selected, **When** the user clicks Trim, **Then** only the selected portion is exported (same behavior as current trim function).
8. **Given** a video with audio is loaded, **When** the user previews the selection, **Then** audio plays along with video during preview.

---

### User Story 3 - Global Settings Panel (Priority: P3)

A user regularly converts videos and always wants them saved to a specific folder with a specific codec. Instead of selecting the output folder each time, they open a Settings panel (via a gear icon), configure their default output folder, preferred video codec, and theme preference. These settings persist across app restarts.

**Why this priority**: Settings persistence improves long-term UX but is less urgent than core workflow improvements. Users can work without it; it adds convenience.

**Independent Test**: Can be fully tested by opening Settings, changing preferences, closing and reopening the app, and verifying settings persist. Delivers configuration persistence.

**Acceptance Scenarios**:

1. **Given** the app is running, **When** the user looks at the status bar area, **Then** a gear icon button is visible for accessing Settings.
2. **Given** the user clicks the Settings icon, **When** the Settings panel opens, **Then** a modal or slide-out panel appears with organized preference sections.
3. **Given** the Settings panel is open, **When** the user views the Output section, **Then** they can set a default output folder for all operations.
4. **Given** the Settings panel is open, **When** the user views the Video section, **Then** they can select a default video codec (H264, HEVC, VP9, or Original).
5. **Given** the Settings panel is open, **When** the user views the Appearance section, **Then** they can choose theme mode (Light, Dark, or System/Auto).
6. **Given** the user changes a setting, **When** they close the Settings panel, **Then** the setting is immediately applied.
7. **Given** the user has configured settings, **When** they close and reopen the application, **Then** all settings persist and are applied on startup.
8. **Given** the Settings panel is open, **When** the user wants to reset settings, **Then** a "Reset to Defaults" button restores original values.

---

### Edge Cases

- What happens when a user drags a file while an operation is in progress? The operation should complete; the dropped file is ignored with a message indicating "Operation in progress, please wait."
- What happens when a video file is corrupted and cannot be played in the trimmer? Display an error message and fall back to text-based timestamp entry mode.
- What happens when the config file is corrupted or manually edited incorrectly? Reset to defaults with a warning message to the user.
- What happens when the app updates with new settings keys? Merge existing user config with defaults - preserve user values for known keys, add default values for new keys.
- What happens when the default output folder no longer exists? Prompt user to select a new folder or fall back to current directory.
- What happens when the user drags a very large video onto the trimmer? Show a loading indicator and load video asynchronously without freezing the UI. For files exceeding 4GB, display a warning that performance may be degraded.
- What happens when the video has no audio track? Mute button is disabled; timeline functionality remains fully operational.
- What happens when the user tries to set end time before start time? Prevent this by snapping the end handle to always be after the start handle.

## Requirements *(mandatory)*

### Functional Requirements

**Drag and Drop**
- **FR-001**: System MUST accept drag-and-drop of files from the operating system onto the main application window.
- **FR-002**: System MUST identify file type by extension and switch to the appropriate tab (Video/Audio to Trim, Image to Convert, Document to Document Convert).
- **FR-003**: System MUST populate the active tab's file input field with the dropped file path.
- **FR-004**: System MUST support multi-file drag-drop for batch operations when files are of the same type.
- **FR-005**: System MUST display user-friendly feedback when an unsupported file is dropped.

**Visual Trimmer**
- **FR-006**: System MUST display an embedded video player when a video file is loaded in the Trim tab.
- **FR-007**: System MUST show a timeline scrubber bar with the total video duration.
- **FR-008**: System MUST provide draggable start and end handles on the timeline.
- **FR-009**: System MUST update timestamp displays in real-time as handles are dragged.
- **FR-010**: System MUST allow video preview playback of the selected segment.
- **FR-011**: System MUST support basic playback controls (play/pause, mute/unmute, volume).
- **FR-012**: System MUST maintain the existing text-based time input as a fallback option.

**Global Settings**
- **FR-013**: System MUST provide a Settings access point via a gear icon in the UI.
- **FR-014**: System MUST allow users to configure a default output folder path.
- **FR-015**: System MUST allow users to select a default video codec for conversions.
- **FR-016**: System MUST allow users to set theme preference (Light/Dark/Auto).
- **FR-017**: System MUST persist all settings to a configuration file between sessions.
- **FR-018**: System MUST load and apply saved settings on application startup.
- **FR-019**: System MUST provide a "Reset to Defaults" option.

### Key Entities

- **UserSettings**: Represents all configurable preferences (outputFolder, defaultCodec, themeMode). Stored persistently and loaded at startup.
- **TrimSelection**: Represents the start/end points selected by the user on the timeline. Contains timestamps and references to the loaded video.
- **DroppedFile**: Represents a file received via drag-and-drop. Contains path, detected type, and target tab mapping.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can load a file into the correct tab within 2 seconds using drag-and-drop (vs. 5+ seconds with Browse dialog).
- **SC-002**: Users can set precise trim points visually without manually entering timestamps in 90% of trimming operations.
- **SC-003**: Settings persist correctly across application restarts with 100% reliability.
- **SC-004**: First-time users can discover and configure settings within 30 seconds.
- **SC-005**: Video preview in the trimmer starts playback within 2 seconds of selection on standard hardware.
- **SC-006**: All three features work across Windows, macOS, and Linux platforms.
- **SC-007**: Drag-and-drop correctly identifies file types with 100% accuracy for supported formats.

## Clarifications

### Session 2026-02-28

- Q: What video playback library should be used for the embedded player? → A: python-vlc (VLC bindings)
- Q: Where and in what format should settings be persisted? → A: JSON file in platform-specific app data directory
- Q: How should VLC dependency be handled for distribution? → A: Require as system dependency (detect and warn if missing)
- Q: How should existing config files be handled when app schema changes? → A: Merge - preserve user values, add defaults for new keys
- Q: What video file size limit should the trimmer support? → A: 4GB soft limit (warn above, may have performance issues)

## Assumptions

- The visual trimmer will use `python-vlc` for video playback, requiring VLC to be installed on the user's system. The application will detect VLC availability at startup and display a warning with installation instructions if missing.
- Users have videos in common formats that are supported by the existing trimming function.
- The configuration file will be stored as JSON in the platform-specific app data directory: `~/.config/media-utilities/` on Linux, `%APPDATA%\media-utilities\` on Windows, `~/Library/Application Support/media-utilities/` on macOS.
- Default codec preference applies to download and conversion operations where codec choice is relevant.
- The visual trimmer is an enhancement to the Trim tab; audio-only files will continue using text-based timestamp entry.
- Video files up to 4GB are fully supported; files exceeding 4GB will display a performance warning but will still be processed.
