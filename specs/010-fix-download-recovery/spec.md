# Feature Specification: Download State Recovery

**Feature Branch**: `010-fix-download-recovery`  
**Created**: 2026-04-21  
**Status**: Draft  
**Input**: User description: "Fix bugs when cancelling the download the app freezes or when using invalid url I can't download anything again till I close and reopen the app"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cancel and Retry Download (Priority: P1)

A user starts a download, decides to cancel it (e.g., wrong URL or changes their mind), and immediately wants to start a new download without restarting the app.

**Why this priority**: Core workflow is broken — cancelling a download leaves the app in an unusable state until the user force-restarts, which is a critical UX failure.

**Independent Test**: Can be fully tested by starting a download, clicking Cancel, and immediately clicking Download again with a different URL — delivers a working cancel-and-retry flow.

**Acceptance Scenarios**:

1. **Given** a download is in progress, **When** the user clicks Cancel, **Then** the UI immediately shows the Download button (not Cancel) and the status shows "Download cancelled"
2. **Given** the user has just cancelled a download, **When** the user enters a new URL and clicks Download, **Then** a new download starts successfully without any error or frozen state
3. **Given** a download is in progress and the user cancels, **When** the background network operation is still completing, **Then** the UI remains fully responsive and the user can start a new download immediately
4. **Given** the user cancels a download and immediately clicks Download again with no URL entered, **When** the button is clicked, **Then** the app shows "Please enter a URL" as it would under normal conditions

---

### User Story 2 - Download After Invalid URL Error (Priority: P1)

A user enters a URL that cannot be downloaded (invalid, unsupported site, private video, etc.), sees an error, then wants to try again with a corrected URL — all without restarting the app.

**Why this priority**: Equally critical — invalid URLs are common (typos, unsupported sites), and users must be able to correct and retry naturally.

**Independent Test**: Can be fully tested by entering an invalid URL, waiting for the error message, entering a valid URL, and clicking Download — delivers a working error-and-retry flow.

**Acceptance Scenarios**:

1. **Given** the user enters an invalid or unsupported URL and clicks Download, **When** the download attempt fails with an error, **Then** the Download button is restored and the error is described in the status area
2. **Given** an invalid URL error has been shown, **When** the user enters a valid URL and clicks Download, **Then** a new download starts normally without any app restart
3. **Given** an unsupported URL causes all fallback strategies to be exhausted, **When** all attempts fail, **Then** the UI resets to an operable state and shows a single clear error message
4. **Given** the user enters multiple invalid URLs in succession, **When** each fails, **Then** each failure clears the previous state correctly and allows the next attempt

---

### User Story 3 - Download State Resilience Under Any Outcome (Priority: P2)

The download section recovers cleanly from any outcome — success, failure, or cancellation — leaving the app in a consistent, ready state for the next action.

**Why this priority**: Builds user trust; prevents edge cases from producing permanently broken state.

**Independent Test**: Can be tested by triggering errors under different conditions (slow network, rapid cancel, bad URLs) and verifying the Download button is always restored to a clickable state.

**Acceptance Scenarios**:

1. **Given** any download outcome (success, failure, cancel), **When** the operation concludes, **Then** the Download button, progress bar, speed indicator, and ETA label are all in a consistent, ready state
2. **Given** a download hangs due to a slow network connection, **When** the user cancels, **Then** the UI reflects the cancelled state promptly regardless of how long the background operation takes
3. **Given** the user performs 10 consecutive cancel-and-retry cycles, **When** each cycle completes, **Then** the app remains fully functional with no degradation

---

### Edge Cases

- What happens when the user cancels immediately after clicking Download, before the first network connection is made?
- What happens if Cancel is clicked a second time on an already-cancelled download?
- What if the user starts a new download while a background thread from a cancelled download is still winding down? → **Resolved**: stale signals are discarded via token counter; new download proceeds unaffected.
- What if Cancel is clicked during the browser intercept phase (long-running browser automation)? → **Resolved**: browser process killed immediately on cancel; result discarded via token counter.
- What if the network drops mid-download — does the UI recover correctly?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST reset the Download button to its initial clickable state instantly (no intermediate "Cancelling…" state) when the user clicks Cancel, regardless of how long the background download operation takes to terminate
- **FR-002**: System MUST allow the user to start a new download immediately after cancelling a previous one, without waiting for the cancelled background operation to fully stop
- **FR-003**: System MUST reset the Download button to its initial clickable state when a download fails due to an invalid, unsupported, or unreachable URL
- **FR-004**: System MUST display a user-friendly, category-specific error message when a download fails (e.g., "Invalid or unsupported URL", "Video is private or unavailable", "Network error — check your connection") and restore all UI controls (button, progress bar, speed label, ETA label) to their pre-download state; raw exception text must not be shown to the user
- **FR-005**: System MUST prevent a cancelled background operation from blocking or interfering with a newly started download; implemented via a generation/token counter — each new download gets a new token and any signal carrying a stale token is silently discarded before reaching the UI
- **FR-006**: System MUST clean up all download state indicators consistently after every download outcome: success, failure, and cancellation; on cancellation, any partially downloaded file MUST be deleted from disk immediately
- **FR-007**: System MUST handle rapid successive download attempts (start → cancel → start immediately) without entering a broken or inconsistent UI state
- **FR-008**: System MUST ensure that clicking Cancel on an already-cancelled download has no negative side effect (e.g., does not emit a second "cancelled" message or prevent the next download)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After clicking Cancel, the Download button becomes available for a new download within 1 second of the cancel action, in 100% of cases
- **SC-002**: After an invalid URL error is displayed, the user can successfully start a new download on their next attempt without any app restart, with 100% reliability
- **SC-003**: Zero scenarios remain where the app must be restarted to recover from a failed or cancelled download — all error and cancel states resolve automatically
- **SC-004**: A user can perform 10 consecutive cancel-and-retry cycles without the app entering a broken state
- **SC-005**: Error messages clearly describe the failure cause so the user understands what to do next, without needing to consult documentation

## Assumptions

- The background download thread cannot be forcefully terminated mid-operation; only a cooperative cancellation flag is available
- It is acceptable for a cancelled background thread to continue running briefly in the background, provided the UI is fully responsive and the user can start new downloads immediately
- Browser intercept fallback may take up to 30 seconds to time out on an invalid URL; if the user cancels during this phase, the browser process is killed immediately rather than left running in background
- Progress indicators (bar, speed, ETA) should be hidden as part of UI recovery, not only the Download button
- Download history entries for failed/cancelled downloads should continue to be recorded as they are today

## Clarifications

### Session 2026-04-21

- Q: When a cancelled background download thread later emits signals (progress, completion, error) after UI reset — possibly during a new download — how should stale signals be handled? → A: Token/generation counter — each new download gets a new token; stale signals silently discarded.
- Q: When a download is cancelled mid-progress, what should happen to the partially downloaded file on disk? → A: Delete partial file immediately on cancel.
- Q: When Cancel is clicked during the browser intercept phase (Playwright, up to 30s), what should happen to the browser process? → A: Kill browser process immediately on cancel.
- Q: Should the UI show an intermediate "Cancelling…" state between cancel click and button restoration? → A: Restore button/controls instantly — no intermediate state.
- Q: What level of detail should error messages show on download failure? → A: User-friendly paraphrase per error category (invalid URL, unsupported site, network error, etc.); no raw exceptions.
