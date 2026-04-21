# Quickstart: Testing Download State Recovery

**Branch**: `010-fix-download-recovery`

---

## Prerequisites

- App running (`python main.py`)
- At least one valid downloadable URL (e.g., a public YouTube video)
- At least one invalid URL (e.g., `https://example.com/notavideo`)

---

## Test 1 — Cancel and retry (US1, SC-001, SC-004)

1. Open the **Media Download** tab.
2. Paste a valid URL. Click **Download**.
3. Within 2 seconds, click **Cancel**.
4. **Expected**: Button immediately shows "Download". Status bar shows "Download cancelled." No progress bar visible.
5. Paste the same (or different) valid URL. Click **Download** again.
6. **Expected**: Download starts normally — progress bar appears, button shows "Cancel".
7. Let download complete.
8. **Expected**: Success message. Button shows "Download".
9. Repeat steps 2–8 ten times. App must remain fully functional throughout.

---

## Test 2 — Invalid URL, then valid URL (US2, SC-002, SC-003)

1. Paste `https://example.com/notavideo`. Click **Download**.
2. Wait for error message.
3. **Expected**: Button shows "Download". Error message describes failure (no raw traceback visible).
4. Paste a valid URL. Click **Download**.
5. **Expected**: Download starts normally. No app restart required.

---

## Test 3 — Double cancel (FR-008)

1. Start a download. Click **Cancel**.
2. Immediately click **Cancel** again (or click Download with empty URL field).
3. **Expected**: No second "cancelled" message. No broken state. Button stays "Download".

---

## Test 4 — Partial file cleanup (FR-006)

1. Start a download to a known output directory.
2. Cancel mid-download.
3. Check the output directory.
4. **Expected**: No `.part` files left behind.

---

## Test 5 — Rapid cancel-start cycle (FR-007, SC-004)

1. Start a download.
2. Cancel immediately.
3. Start a new download immediately (do not wait).
4. **Expected**: New download starts without entering a broken state.
5. Repeat 10 times.

---

## Regression checks

- Convert, Trim, Document tabs: still functional after download cancel
- History tab: cancelled and failed downloads appear as expected
- Settings tab: no regressions
