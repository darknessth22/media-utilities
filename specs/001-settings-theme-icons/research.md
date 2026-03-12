# Phase 0: Research & Decisions

## Context

The feature is to replace the text-based "Settings" link and the text-based Theme toggle ("Theme: Auto/Light/Dark") with graphical icons placed in the Top-Right corner of the main GUI window.

## Unknowns Resolved

### 1. How is the Top-Right corner of the window constructed in Tkinter for this app?

- **Decision:** Place the new icons in the `status_frame` which is currently packed at the bottom but we will create a new top-level `header_frame` or similar at the top of the root window to hold these icons and the title. Or, if we strictly want them in the top-right corner of the *entire* app, we can pack a small frame at `top` with `side="right"` before the notebook.
- **Rationale:** The current theme and settings buttons are in a `status_frame` packed at the bottom (`side="bottom"`). To move them to the Top-Right, we should introduce a top bar above the notebook.
- **Alternatives considered:** Packing them inside the Notebook tabs (would require duplicating across all tabs), which is inefficient and violates DRY.

### 2. Where should the icon image files be stored and how will they be loaded?

- **Decision:** Store the icons (e.g., `settings.png`, `sun.png`, `moon.png`) in an `assets/icons/` folder at the root of the project.
- **Rationale:** Keeps static assets organized and isolated from python code.
- **Alternatives considered:** Base64 encoding the icons in Python (bloats code, harder to maintain).

### 3. How do we ensure standard Tkinter handles the images properly?

- **Decision:** Use `tkinter.PhotoImage` or `PIL.ImageTk.PhotoImage`. Since `Pillow` is already a dependency (per the Constitution), using `PIL.ImageTk.PhotoImage` is safe and allows resizing the icons dynamically if needed.
- **Rationale:** `PIL` allows handling PNG transparency cleanly across platforms.

### 4. How do we implement hover tooltips for standard Tkinter widgets?

- **Decision:** Implement a simple `ToolTip` class or utilize a lightweight tooltip approach if `ttkbootstrap` provides one. `ttkbootstrap` provides `ToolTip`. We will use `ttkbootstrap.tooltip.ToolTip(widget, text="...")`.
- **Rationale:** `ttkbootstrap` is already the primary UI framework. Reusing its tooltip component adheres to the YAGNI and consistency principles in the Constitution.

---
_All initial unknowns resolved. Proceeding to Phase 1._
