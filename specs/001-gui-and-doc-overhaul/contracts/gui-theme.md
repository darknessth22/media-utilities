# Contract: Theme Management (`gui/theme.py`)

## Public API

### `ThemeManager(root)`

Manages application theme state, OS detection, and persistence.

**Constructor Parameters**:
- `root: ttkbootstrap.Window` — The main application window

**Methods**:

#### `initialize()`
Reads persisted config, detects OS preference, applies initial theme.
- If config has `mode: "auto"` → use `darkdetect.isDark()` to choose
- If config has `mode: "light"` or `"dark"` → use user override
- If `darkdetect` returns `None` → default to light theme
- Starts OS theme change listener on daemon thread (optional)

#### `toggle()`
Cycles theme: auto → light → dark → auto. Applies immediately and persists.

#### `get_current_mode() -> str`
Returns current mode: `"auto"`, `"light"`, or `"dark"`.

#### `get_current_theme_name() -> str`
Returns the active ttkbootstrap theme name (e.g., `"cosmo"`, `"darkly"`).

### Config File: `~/.media_utility.json`

Extends existing config with theme fields:

```json
{
  "dark_mode": false,
  "theme": {
    "mode": "auto",
    "light_theme": "cosmo",
    "dark_theme": "darkly"
  }
}
```

Backward compatibility: if `"theme"` key missing, migrate from legacy `"dark_mode"` boolean.

## Thread Safety

- All theme switches dispatched via `root.after(0, ...)` from background threads
- Config file writes are atomic (write to temp, then rename)
