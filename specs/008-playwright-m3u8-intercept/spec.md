# Feature Specification: Playwright HLS Stream Intercept

**Feature Branch**: `008-playwright-m3u8-intercept`  
**Created**: 2026-04-17  
**Status**: Draft  
**Input**: User description: "i want a feature for Playwright (headless browser) — executes the JS, intercepts the .m3u8 network request for the sites that doesn't support yt-dlb"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Download from Unsupported Site via Browser Intercept (Priority: P1)

User pastes a URL from a site not supported by yt-dlp. The application detects this, launches a headless browser session, loads the page (executing all JavaScript), intercepts outgoing network requests for HLS manifest files (`.m3u8`), and captures the stream URL. The captured stream URL is then handed off to the existing download pipeline for actual download.

**Why this priority**: Core value of the feature — enables downloading from sites that rely on JS-rendered content to serve video streams, which yt-dlp cannot handle directly.

**Independent Test**: Can be tested end-to-end by entering a URL from a JS-gated streaming site; if the app successfully downloads the video without requiring user intervention, the story is complete.

**Acceptance Scenarios**:

1. **Given** a URL from a site not supported by yt-dlp, **When** the user submits it in the download tab, **Then** the system automatically uses the browser-based fallback, intercepts the `.m3u8` URL, and downloads the stream.
2. **Given** a page that loads the `.m3u8` URL only after user interaction (e.g., play button click), **When** the headless browser loads the page, **Then** the system waits for and captures the `.m3u8` request before timing out.
3. **Given** the browser intercept captures a `.m3u8` URL, **When** the download starts, **Then** the file is saved to the user's configured download path with progress shown in the UI.

---

### User Story 2 - Graceful Fallback and Error Handling (Priority: P2)

When the headless browser session runs but no `.m3u8` URL is intercepted within a reasonable timeout, the system informs the user clearly and does not crash or hang silently.

**Why this priority**: Without this, failed intercepts leave the user with no feedback and a frozen UI — important for reliability and trust.

**Independent Test**: Can be tested by submitting a URL from a site that serves video through a non-HLS mechanism; the app should show an error message and stop cleanly.

**Acceptance Scenarios**:

1. **Given** a page where no `.m3u8` request is made within the timeout window, **When** the session expires, **Then** the system shows an error message stating it could not detect a stream and the UI returns to ready state.
2. **Given** the headless browser fails to launch (e.g., missing dependency), **When** the user submits a URL, **Then** the system shows a descriptive error without crashing.

---

### User Story 3 - Transparent Status During Browser Session (Priority: P3)

While the headless browser session is running, the user can see status updates in the UI (e.g., "Loading page…", "Waiting for stream URL…") so they know the operation is in progress.

**Why this priority**: Improves user experience during what can be a multi-second wait — prevents users from thinking the app is frozen.

**Independent Test**: Can be verified by submitting a URL and observing that progress messages appear in the download tab during the intercept phase.

**Acceptance Scenarios**:

1. **Given** a browser intercept is in progress, **When** the user views the download tab, **Then** a status message reflects the current phase (page loading, waiting for stream, etc.).
2. **Given** the user wants to cancel, **When** they click cancel during the intercept phase, **Then** the browser session terminates and the UI resets.

---

### Edge Cases

- What happens when the page returns multiple `.m3u8` URLs (e.g., multiple quality variants)?
- How does the system handle redirects before the `.m3u8` URL is served?
- What if the `.m3u8` URL is behind authentication cookies set by the page (session-bound)?
- What happens when the site loads indefinitely and never fires a `.m3u8` request?
- How does the system handle pages that require geographic access not available on the host machine?
- What if the intercepted `.m3u8` URL expires before download begins?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST attempt download via yt-dlp first; if yt-dlp returns an unsupported-URL error or extraction failure, system MUST automatically retry via the browser-based intercept fallback — no user action required.
- **FR-002**: System MUST launch a headless browser session that fully executes page JavaScript for the submitted URL.
- **FR-003**: System MUST intercept all outgoing network requests during the browser session and identify any `.m3u8` manifest URLs.
- **FR-004**: System MUST pass the captured `.m3u8` URL along with browser session cookies and request headers to the existing download pipeline and begin download immediately upon capture — no user confirmation step — to minimize URL expiry risk.
- **FR-005**: System MUST enforce a configurable timeout on the browser session; if no `.m3u8` URL is intercepted within the timeout, the session terminates.
- **FR-006**: System MUST display real-time status messages in the download UI during the browser intercept phase.
- **FR-007**: System MUST show a clear error message when the intercept fails or no stream is found.
- **FR-008**: System MUST allow the user to cancel an in-progress browser intercept session.
- **FR-009**: When multiple `.m3u8` URLs are intercepted, system MUST parse the HLS master playlist and automatically select the highest-quality variant stream for download.
- **FR-010**: Downloaded file MUST be saved to the user's configured download path and appear in download history.

### Key Entities

- **Intercept Session**: Represents one headless browser run for a given URL — tracks state (loading, waiting, captured, timed-out, cancelled), the target URL, and any captured stream URLs.
- **Stream URL**: The `.m3u8` manifest URL captured from network traffic — associated with an intercept session and passed to the download pipeline.
- **Download Record**: Existing entity — updated to track whether the download originated from a direct download or browser intercept.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can successfully download video from a site unsupported by the standard downloader in under 60 seconds from URL submission (assuming adequate network speed).
- **SC-002**: The browser intercept correctly captures `.m3u8` URLs on 90% of tested JS-rendered streaming sites.
- **SC-003**: The system never hangs indefinitely — every browser session resolves (success, error, or cancel) within the configured timeout plus a 5-second grace period.
- **SC-004**: Users can identify the current intercept phase at all times via UI status messages — zero silent-loading states during the browser session.
- **SC-005**: Cancelling an in-progress intercept session stops the operation within 3 seconds and returns the UI to ready state.

## Clarifications

### Session 2026-04-17

- Q: How should the system detect that a URL needs browser intercept instead of yt-dlp? → A: Attempt yt-dlp first; on unsupported/error response, automatically retry via browser intercept.
- Q: When multiple .m3u8 URLs are captured, which is used? → A: Parse HLS master playlist; auto-select highest-quality variant by bandwidth.
- Q: Which headless browser engine to use? → A: Playwright (Python `playwright` package).
- Q: Should session cookies/headers be forwarded to download pipeline? → A: Yes — pass browser session cookies and request headers to yt-dlp/ffmpeg.
- Q: What happens if captured .m3u8 URL expires before download starts? → A: Start download immediately after capture with no confirmation step; show error and let user re-submit if URL has already expired.

## Assumptions

- The existing download pipeline already accepts a raw stream URL and can handle `.m3u8` manifests (via ffmpeg or similar); this feature only adds the URL discovery step.
- Playwright (Python `playwright` package) is the required headless browser engine — must be installable as a dependency without breaking existing packaging.
- The feature does not need to handle sites requiring active login — unauthenticated public streams are the primary target.
- Default intercept timeout is 30 seconds, configurable in app settings.
- When multiple `.m3u8` URLs are captured, the system parses the HLS master playlist and auto-selects the highest-quality variant by bandwidth tag.
