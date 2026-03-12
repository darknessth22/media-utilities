# Research Document: System Tray and Native Notifications

## Research 1: Cross-Platform System Tray Library for Python

**Decision**: Use `pystray` with `Pillow` (PIL)

**Rationale**: `pystray` is the most widely recommended and actively maintained library for creating cross-platform system tray icons in Python. It supports Windows, macOS, and Linux (Xorg, GNOME) natively. It directly supports creating right-click context menus, which fulfills FR-002 ("Restore", "Settings", "Quit/Exit"). It also allows binding actions to the tray icon itself (e.g., double-click or single-click depending on the OS), fulfilling the requirement to restore the main window when clicked.

**Alternatives considered**:
- `rumps`: Primarily macOS only.
- `infi.systray`: Windows only.
- `crosstray`: Not fully mature or widely adopted.

## Research 2: Cross-Platform Native OS Notifications

**Decision**: Use `desktop-notifier`

**Rationale**: While `plyer` and `notify-py` are simpler, `desktop-notifier` is specifically built to handle *interactive* notifications across Windows, macOS, and Linux. This is critical for our requirement (Question 2 answer) that clicking the notification itself must restore the application and navigate to the History tab. `desktop-notifier` supports callbacks when a notification is clicked, making this possible. Note: On macOS, notifications require the Python executable/bundled app to be signed, which we may need to address in the build process or document as a limitation during development.

**Alternatives considered**:
- `notify-py`: Lightweight but does not support embedding callbacks or actions on notification click.
- `plyer`: Very simple, but its notification implementation is basic "fire-and-forget" without robust click handling across all platforms.
