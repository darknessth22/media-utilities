# Feature Specification: Generic URL Video Download

**Feature Branch**: `007-generic-url-download`  
**Created**: 2026-04-17  
**Status**: Draft  
**Input**: User description: "i want to add a feature for making me able to download videos also from any link not just social media links important to not change anything in the current downloading for fb and yt and ig and x and tiktok but we need to add a mobility to donwload a video from other link as well"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Download Video From Any URL (Priority: P1)

User pastes a URL that is not from YouTube, Facebook, Instagram, TikTok, or Twitter/X — for example, a news site video, a direct video file link, or a video hosted on a lesser-known platform. User expects to download the video the same way they download social media content: paste URL, click Download, get file.

**Why this priority**: Core ask of the feature. Without this, the feature does not exist.

**Independent Test**: Paste a non-social-media video URL, click Download, verify file is saved to output folder.

**Acceptance Scenarios**:

1. **Given** user has a URL to a video on a non-social-media site, **When** they paste it into the URL field and click Download, **Then** the video downloads to the selected output folder with a recognizable filename.
2. **Given** user pastes a direct video file link (e.g., ending in `.mp4`, `.mkv`, `.webm`), **When** they click Download, **Then** the file is downloaded and saved to the output folder.
3. **Given** a URL that contains no downloadable video, **When** user clicks Download, **Then** a clear error message is shown explaining the URL is unsupported or no video was found.

---

### User Story 2 - Platform Detection Communicates Generic Support (Priority: P2)

User pastes a URL and sees a clear indicator that the app will attempt to download from it — even though it is not a known social media platform. User understands the app supports their URL before clicking Download.

**Why this priority**: Reduces user confusion and wasted attempts. User currently sees "Generic URL" but does not know if it is supported.

**Independent Test**: Paste a generic URL, verify the detected platform label clearly communicates download will be attempted.

**Acceptance Scenarios**:

1. **Given** user pastes a non-social-media URL, **When** the URL is entered, **Then** the platform label reads something clear like "Generic URL — download will be attempted" or equivalent.
2. **Given** user pastes a known social media URL (YouTube, Facebook, etc.), **When** the URL is entered, **Then** the platform label is unchanged from current behavior.

---

### User Story 3 - Consistent Download Experience for Generic URLs (Priority: P3)

User downloading from a generic URL gets the same options as social media downloads: audio/video mode selection, quality selection (when available), output folder selection, and progress feedback. No hidden differences in behavior.

**Why this priority**: Ensures feature parity so users are not confused by a degraded experience for non-social-media URLs.

**Independent Test**: Use a generic URL, confirm all download options (media type, output folder, quality check) behave the same as for YouTube.

**Acceptance Scenarios**:

1. **Given** user has a generic URL, **When** they use "Check Formats", **Then** available formats are listed if the source exposes them, or a clear message appears if formats are unavailable.
2. **Given** user selects audio-only mode for a generic URL, **When** they click Download, **Then** audio is extracted the same as for social media URLs.

---

### Edge Cases

- **[RESOLVED]** URL requires authentication/login: show specific error "This video requires login — not supported for generic URLs."
- **[RESOLVED]** URLs that time out or are unreachable: system enforces a 30-second timeout and displays a descriptive error message (no silent failure).
- What happens when a direct video file URL redirects to another URL before resolving?
- **[RESOLVED]** When the URL contains a video playlist, the system downloads only the first/primary video and displays a warning informing the user that a playlist was detected and only the main video was downloaded.
- **[RESOLVED]** For direct video file URLs (`.mp4`, `.mkv`, `.webm`, etc.): system tries yt-dlp first; if yt-dlp fails, falls back to plain HTTP download.
- What if the file at the URL is not a video (e.g., an HTML page with no embedded video)?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST attempt to download video content from any valid URL, not only from known social media platforms.
- **FR-002**: System MUST NOT alter the download behavior, options, or output for YouTube, Facebook, Instagram, TikTok, Twitter/X, or Spotify URLs.
- **FR-003**: System MUST provide a clear UI indication when a URL is identified as a generic (non-social-media) source, communicating that a download will be attempted.
- **FR-004**: System MUST display a cause-specific error message when a generic URL cannot be downloaded. Distinct messages required for: network timeout, no video found at URL, site not supported by download engine, and URL requires authentication/login.
- **FR-005**: Users MUST be able to select audio-only mode for generic URLs the same way they can for social media URLs. The full quality-fetching process (Check Formats, best audio selection) MUST behave identically for generic URLs as for known social media URLs.
- **FR-006**: Users MUST be able to select an output folder for generic URL downloads.
- **FR-007**: System MUST add completed or failed generic URL downloads to the download history, consistent with social media download history entries.
- **FR-008**: System MUST support direct video file URLs (links ending in a video file extension) as a valid download source.
- **FR-009**: When a generic URL resolves to a playlist, system MUST download only the first/primary video and display a warning that a playlist was detected.
- **FR-010**: Generic URL download attempts MUST enforce a 30-second network timeout; on timeout, display a descriptive error message.
- **FR-011**: For direct video file URLs, system MUST attempt yt-dlp first (preserving full quality/format selection and audio extraction); if yt-dlp fails, system MUST fall back to a plain HTTP file download (downloads the file as-is, best available).
- **FR-012**: When HTTP fallback is used and no metadata is available, the output filename MUST be derived from the last path segment of the URL (before any query string), preserving the file extension.

### Key Entities

- **Generic URL**: Any URL that does not match a known social media domain and is not a Spotify link. Treated as a candidate for video extraction.
- **Download Attempt**: An initiated download from any URL, regardless of platform. Has success/failure outcome and produces a history entry.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can successfully download a video from at least 3 different non-social-media video sources without any change to the workflow used for social media downloads.
- **SC-002**: All existing social media download operations (YouTube, Facebook, Instagram, TikTok, Twitter/X, Spotify) continue to produce identical results before and after this feature is introduced.
- **SC-003**: When a generic URL fails to download, 100% of failure cases display a user-readable error message (no silent failures, no raw exception text shown to user).
- **SC-004**: Generic URL downloads appear in history with the same information (filename, status, task type) as social media downloads.
- **SC-005**: Users require zero additional steps to download from a generic URL compared to a social media URL — same URL input, same Download button, same output.

## Clarifications

### Session 2026-04-17

- Q: When a generic URL resolves to a playlist, what should happen? → A: Download first/primary video only; warn user a playlist was detected.
- Q: What network timeout applies to generic URL downloads? → A: 30 seconds.
- Q: For direct file URLs (.mp4 etc.), should system fall back to plain HTTP if yt-dlp fails? → A: Yes, try yt-dlp first then fall back to HTTP download.
- Q: Filename for HTTP fallback downloads (no metadata available)? → A: Derive from URL path last segment before query string.
- Q: Should error messages be generic or specific per failure cause? → A: Specific per cause: timeout, no video found, site unsupported, requires login.
- Note: Quality fetching (Check Formats) and best audio selection MUST work identically for generic URLs as for social media URLs.

## Assumptions

- The underlying download engine already supports a wide range of non-social-media video sources; this feature primarily ensures that capability is accessible and communicated clearly in the UI.
- Direct video file URLs (e.g., `https://example.com/video.mp4`) are a valid target and should download even if no metadata extraction is possible.
- No new login or credential management is required for generic URLs; authenticated sources are out of scope for this feature.
- Quality format listing for generic URLs may return no results for many sites; this is acceptable as long as "Best available" still attempts a download.
