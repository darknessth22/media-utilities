# Data Model: PyQt6 GUI Migration

## 1. UserSettings

Represents the user's configured preferences.

**Fields**:
- `theme` (str): 'light', 'dark', or 'system'
- `default_download_path` (str): Absolute directory path
- `default_convert_path` (str): Absolute directory path 
- `quit_on_close` (bool): **NEW** (Migration Caveat M-1). Determines whether closing the main window exits the app or minimizes it to the system tray. Defaults to `False`.

**Relationships**: Read/written by `SettingsManager` to `settings.json`.

**State Transitions**: Modifying settings in the UI triggers immediate save and live application of visual changes (e.g., QSS reloading).

## 2. DroppedFile

Represents a local file dragged and dropped onto the application window (Migration Caveat M-3).

**Fields**:
- `file_path` (str): Absolute path to the file
- `file_type` (str): Derived from extension (e.g., 'video', 'document')

**Relationships**: Created by `QDropEvent` handler in the main window; routed to appropriate UI tabs based on `file_type`.

## 3. HistoryItem

Represents a completed or failed background task.

**Fields**:
- `id` (str): Unique identifier
- `task_type` (str): 'download', 'convert', 'trim', 'document'
- `source` (str): Original file path or URL
- `destination` (str): Output file path
- `status` (str): 'success' or 'error'
- `timestamp` (float): Unix timestamp of completion

**Relationships**: Stored in a local JSON file. Bound to UI via a `QAbstractTableModel` for display in the History tab.
