# Data Model: History Item

## Entities

### `HistoryItem`

A record of a completed task (download or conversion).

**Fields**:
- `id` (`str`): A unique identifier for the record (e.g. UUID).
- `task_type` (`str`): The type of task ("Download" or "Conversion").
- `file_name` (`str`): The name of the resulting file (e.g. "video.mp4" or "document.pdf").
- `file_path` (`str`): The absolute path to the file on disk.
- `timestamp` (`float`): Unix timestamp indicating when the task completed.
- `status` (`str`): Final status of the task ("Success", "Failed", etc.).

**Persistence**:
- Data will be persisted to a local JSON file (`history.json`) typically located in the user's application data directory, or alongside the `media_util_settings.json` file.
- The manager will ensure only a maximum of 10 items are retained. Older items will be automatically pruned when new ones are added.

## State Transitions
- **Added**: When a download or conversion successfully completes, a new `HistoryItem` is created and appended to the in-memory list and saved to disk.
- **Removed**: When the user clicks "Clear All History", the in-memory list is cleared, and the JSON file on disk is emptied.
- **Pruned**: If an 11th item is added, the oldest item (lowest timestamp) is removed from both memory and disk.
