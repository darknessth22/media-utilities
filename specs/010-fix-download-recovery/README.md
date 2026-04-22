# Phase 010 — Download State Recovery

**Branch**: `010-fix-download-recovery`
**Status**: Draft | **Created**: 2026-04-21

## Goal

Fix two critical bugs: (1) cancelling a download freezes the app, and (2) after an invalid URL error the download button never comes back — forcing a full restart.

## What This Phase Delivers

### Cancel-and-Retry (P1)
- Cancel click → Download button restored **immediately** (no "Cancelling…" state)
- New download starts right away without waiting for background thread to fully stop
- Stale signals from cancelled operation discarded via **generation/token counter** — each new download gets a new token; old signals carrying stale tokens are silently dropped
- Clicking Cancel on an already-cancelled download has no negative side effect
- Partial downloaded file deleted from disk on cancel

### Error-and-Retry (P1)
- Invalid/unsupported/unreachable URL → Download button restored, user-friendly category-specific error shown
- Raw exception text never shown to user; messages: "Invalid or unsupported URL" / "Video is private or unavailable" / "Network error — check your connection"
- All fallback strategies exhausted → single clear error, UI fully operable
- Multiple consecutive invalid URLs each clear previous state correctly

### General State Resilience (P2)
- After any outcome (success / failure / cancel): progress bar, speed label, ETA label, and Download button all in consistent ready state
- 10 consecutive cancel-and-retry cycles leave app fully functional with no degradation
- Cancel during Playwright browser intercept → browser process killed immediately

## Key Dependencies
- `PySide6 QThread + Signal` — background worker
- Generation/token counter pattern for stale signal discard
- No new external dependencies

## Acceptance Criteria (abridged)
- Cancel → Download button back instantly, new download starts immediately
- Invalid URL → error message shown, Download button restored, next download works
- 10 cancel-retry cycles: app still fully functional

## Full Spec
See [`spec.md`](spec.md) for complete user stories, edge cases, and all functional requirements.
