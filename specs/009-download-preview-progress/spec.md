# Feature Specification: Download Preview & Rich Progress

**Feature Branch**: `009-download-preview-progress`  
**Created**: 2026-04-20  
**Status**: Draft  
**Input**: User description: "for the downloading tab i want to show the video a preview like the trim tab to choose the parts i want to download only and also i want to add for the downloading progress in the gui to show the speed and the progress that is downloading not just loading gui and estimated time to finish"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Rich Download Progress Display (Priority: P1)

A user pastes a URL and clicks Download. Instead of an indeterminate spinner with no information, the progress area shows a percentage bar, current download speed (e.g. "3.2 MB/s"), and estimated time remaining (e.g. "~45 s left"). The user can see the download advancing in real time and knows when it will finish.

**Why this priority**: This is a standalone quality-of-life fix that requires no new external dependencies and immediately makes the download experience usable. It delivers value independent of the preview feature.

**Independent Test**: Start a download of any supported URL. Verify that the progress bar fills incrementally (not just indeterminate), a speed value updates every second, and an ETA is displayed and counts down.

**Acceptance Scenarios**:

1. **Given** a valid URL is entered and Download is clicked, **When** the download is in progress, **Then** the progress bar shows a non-indeterminate percentage (0–100%), a speed label shows MB/s or KB/s updating at least once per second, and an ETA label shows remaining seconds or minutes.
2. **Given** a download is running, **When** the download completes, **Then** the progress bar reaches 100%, speed and ETA labels clear, and the success message appears.
3. **Given** a download is running, **When** the user cancels, **Then** progress resets and cancellation is confirmed immediately.
4. **Given** the downloader cannot report progress (e.g. unknown total size), **When** the download is in progress, **Then** an indeterminate bar is shown as fallback and speed is still displayed if available.

---

### User Story 2 - Video Preview for Time-Range Selection (Priority: P2)

A user pastes a video URL, clicks a "Preview" or "Load Preview" button, and a video player appears in the download tab (similar to the trim tab). The user scrubs through the video and sets start and end time markers visually, then clicks Download. Only the selected segment is downloaded.

**Why this priority**: Builds on Story 1 infrastructure. Requires fetching a playable stream URL before the actual download, which adds complexity and a new async step. High value but separable.

**Independent Test**: Enter a YouTube URL, click Load Preview, confirm the video plays in the embedded player, drag start/end markers to select a segment, and verify that the start/end time fields are populated correctly before downloading.

**Acceptance Scenarios**:

1. **Given** a supported video URL is entered, **When** the user clicks "Load Preview", **Then** an embedded video player appears and begins streaming the video for preview without downloading it.
2. **Given** the preview player is visible, **When** the user moves the start marker, **Then** the Start time input field updates to match the marker position in HH:MM:SS format.
3. **Given** the preview player is visible, **When** the user moves the end marker, **Then** the End time input field updates to match the marker position.
4. **Given** start and end markers are set, **When** the user clicks Download, **Then** only the segment between start and end is downloaded (same behaviour as manually entering time range).
5. **Given** a URL is entered that cannot produce a playable preview (e.g. audio-only or unsupported site), **When** the user clicks "Load Preview", **Then** a clear message explains the preview is unavailable and the existing text-based time-range inputs remain usable.
6. **Given** the URL changes after preview was loaded, **When** the user starts typing a new URL, **Then** the preview player is hidden and time range inputs are reset.

---

### Edge Cases

- What happens when video duration is unknown (live streams)? Preview should be disabled with explanation; progress shows indeterminate bar with speed only.
- What happens when the network drops mid-download? Error message appears, progress resets, history records failure.
- What happens when start time ≥ end time in the preview markers? An inline validation message prevents starting the download.
- What happens when the preview stream URL expires before download starts? Download falls back to normal full-URL download with original URL.
- What happens on audio-only mode — is preview shown? Preview player is hidden; only the rich progress display applies.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display a determinate progress bar (0–100%) during download whenever total file size is known.
- **FR-002**: System MUST display current download speed (updated at least once per second) in human-readable units (KB/s or MB/s) during download.
- **FR-003**: System MUST display estimated time remaining (ETA) during download whenever total size and speed are known, formatted as seconds or minutes.
- **FR-004**: System MUST fall back to an indeterminate progress bar when total size is unknown, while still showing speed if available.
- **FR-005**: System MUST provide a "Load Preview" button in the download tab for video mode that streams the video for preview without downloading the full file.
- **FR-006**: System MUST embed a video player in the download tab when preview is loaded, matching the visual style of the trim tab's player. The player widget is positioned between the options area and the progress bar; it is hidden (zero height) when no preview is loaded and visible when preview is active.
- **FR-007**: System MUST provide draggable start and end markers on a timeline in the preview player, and sync their positions with the Start and End time input fields. The timeline scrubber MUST reuse the trim tab's existing `QSlider`-based start/end marker component.
- **FR-008**: System MUST validate that start time is less than end time before allowing download to proceed when a time range is set. When a time range is set, the downloader MUST use yt-dlp `--download-sections "*<start>-<end>"` to download only the selected segment without fetching the full file.
- **FR-009**: System MUST hide the preview player and reset time range inputs when the URL field is cleared or changed to a different URL.
- **FR-010**: System MUST display a clear message when preview is unavailable for a given URL (audio-only, live stream, unsupported site) and keep text-based time inputs accessible.
- **FR-011**: The rich progress display (speed, ETA, percentage) MUST work for all download paths including yt-dlp, HTTP fallback, and browser intercept modes. The HTTP fallback (urllib) MUST be updated to use a chunked read loop that tracks bytes received, computes speed from elapsed time, and derives ETA from `Content-Length` header when available.

### Key Entities

- **Download Progress Event**: A snapshot emitted during download containing percentage complete (0–100 or None), bytes-per-second speed, and estimated seconds remaining.
- **Preview Stream**: A temporary, playable URL or local stream used to render the video in the embedded player without saving to disk.
- **Time Range Selection**: A pair of (start, end) timestamps in seconds, set either via text input or preview markers, passed to the downloader.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: During any download where total size is known, the progress bar updates at least once per second with a non-indeterminate value.
- **SC-002**: Download speed is displayed within 2 seconds of download start for all download paths where speed data is available.
- **SC-003**: ETA is shown and updates continuously for all downloads where total size is determinable.
- **SC-004**: Users can load a video preview and set a time-range segment in under 30 seconds for any supported video URL.
- **SC-005**: Time input fields stay in sync with preview markers — changes to either the field or marker are reflected in the other within 500 ms.
- **SC-006**: All existing download functionality (quality selection, audio format, output folder, cancel) continues to work unchanged after this feature is added.

## Assumptions

- The downloader backend (yt-dlp) already emits progress hooks that include percentage, speed, and ETA data — this feature exposes that data in the UI rather than computing it independently.
- Preview streaming uses `yt_dlp.YoutubeDL.extract_info` to obtain a direct stream URL, which is passed directly to `QMediaPlayer` as a network URL — no local temp file is written and no new dependencies are introduced.
- The trim tab's QMediaPlayer + QVideoWidget infrastructure can be reused in the download tab without duplicating the multimedia backend logic.
- Audio-only downloads do not show a video preview player; rich progress display still applies.
- Progress events are delivered on a background thread and marshalled to the UI thread for display.

## Clarifications

### Session 2026-04-20

- Q: How does the preview player stream the video? → A: yt-dlp extracts a direct stream URL via `extract_info`; that URL is passed to `QMediaPlayer` as a network URL (no local download, no new dependencies).
- Q: How is the time-range segment extracted when start/end markers are set? → A: yt-dlp `--download-sections "*<start>-<end>"` — segment downloaded directly, no full file written.
- Q: Where does the preview player appear in the download tab layout? → A: Between the options area and the progress bar (pushes progress down); hidden when no preview is loaded.
- Q: What progress behavior is required for the HTTP fallback (urllib) path? → A: Add a chunked read loop to the HTTP fallback so it emits percentage, speed, and ETA — full FR-011 compliance required.
- Q: What widget is used for the preview timeline scrubber (start/end markers)? → A: Reuse the trim tab's existing `QSlider`-based start/end marker component directly.
