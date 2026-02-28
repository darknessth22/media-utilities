# Data Model: Drag-Drop, Rich Trimmer & Global Settings

**Feature Branch**: `004-drag-trimmer-settings`
**Date**: 2026-02-28

## Entities

### UserSettings

Represents all user-configurable preferences. Persisted as JSON.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `output_folder` | `str \| None` | `None` | Default output directory for all operations. `None` = use source file directory. |
| `default_codec` | `str` | `"original"` | Video codec preference: `"h264"`, `"hevc"`, `"vp9"`, `"original"` |
| `theme_mode` | `str` | `"auto"` | Theme preference: `"light"`, `"dark"`, `"auto"` |
| `version` | `int` | `1` | Schema version for future migrations |

**JSON Schema**:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "output_folder": { "type": ["string", "null"] },
    "default_codec": {
      "type": "string",
      "enum": ["h264", "hevc", "vp9", "original"]
    },
    "theme_mode": {
      "type": "string",
      "enum": ["light", "dark", "auto"]
    },
    "version": { "type": "integer", "minimum": 1 }
  },
  "additionalProperties": false
}
```

**State Transitions**: None (static configuration)

---

### TrimSelection

Represents the user's selected trim range on the timeline. Runtime only (not persisted).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `video_path` | `str` | - | Absolute path to loaded video file |
| `duration_ms` | `int` | - | Total video duration in milliseconds |
| `start_ms` | `int` | `0` | Start point in milliseconds |
| `end_ms` | `int` | `duration_ms` | End point in milliseconds |
| `is_playing` | `bool` | `False` | Whether preview is currently playing |
| `is_muted` | `bool` | `False` | Whether audio is muted |
| `volume` | `int` | `100` | Volume level (0-100) |

**Validation Rules**:
- `start_ms >= 0`
- `end_ms <= duration_ms`
- `start_ms < end_ms`
- `volume` in range `[0, 100]`

**State Transitions**:
```
[Empty] --load_video--> [Loaded]
[Loaded] --set_start--> [Loaded] (updates start_ms)
[Loaded] --set_end--> [Loaded] (updates end_ms)
[Loaded] --play--> [Playing]
[Playing] --pause--> [Loaded]
[Playing] --reach_end--> [Loaded] (loops to start_ms)
[Loaded] --clear--> [Empty]
```

---

### DroppedFile

Represents a file received via drag-and-drop. Transient object for routing.

| Field | Type | Description |
|-------|------|-------------|
| `path` | `str` | Absolute file path |
| `extension` | `str` | Lowercase extension including dot (e.g., `.mp4`) |
| `file_type` | `str` | Detected type: `"video"`, `"audio"`, `"image"`, `"document"`, `"unknown"` |
| `target_tab` | `str \| None` | Target tab ID: `"trim"`, `"convert"`, `"batch"`, `"document"`, or `None` |
| `size_bytes` | `int` | File size in bytes |
| `is_large` | `bool` | `True` if `size_bytes > 4GB` |

**Validation Rules**:
- `path` must exist and be readable
- `extension` must be non-empty for type detection
- `target_tab` is `None` if `file_type == "unknown"`

---

### VLCPlayerState

Internal state for the VLC video player widget.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `instance` | `vlc.Instance \| None` | `None` | VLC instance |
| `player` | `vlc.MediaPlayer \| None` | `None` | Media player object |
| `media` | `vlc.Media \| None` | `None` | Currently loaded media |
| `is_available` | `bool` | `False` | Whether VLC is installed and functional |
| `error_message` | `str \| None` | `None` | Error details if VLC unavailable |

---

## Relationships

```
┌─────────────────┐
│  UserSettings   │
│  (persisted)    │
└────────┬────────┘
         │ loaded at startup
         │ applied to
         ▼
┌─────────────────┐      ┌─────────────────┐
│ MediaUtilityGUI │◄─────│   DroppedFile   │
│   (main app)    │      │   (transient)   │
└────────┬────────┘      └─────────────────┘
         │ contains
         ▼
┌─────────────────┐      ┌─────────────────┐
│  VideoTrimmer   │─────►│  TrimSelection  │
│    (widget)     │      │   (runtime)     │
└────────┬────────┘      └─────────────────┘
         │ uses
         ▼
┌─────────────────┐
│ VLCPlayerState  │
│   (internal)    │
└─────────────────┘
```

---

## File Type Mapping Table

| Extension | File Type | Target Tab | Notes |
|-----------|-----------|------------|-------|
| `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.flv` | video | trim | Visual trimmer available |
| `.mp3`, `.wav`, `.aac`, `.flac`, `.ogg`, `.m4a` | audio | trim | Text timestamps only |
| `.jpg`, `.jpeg`, `.png`, `.heic`, `.heif`, `.webp`, `.gif`, `.bmp` | image | convert | Single file conversion |
| `.pdf`, `.docx`, `.doc`, `.xlsx`, `.xls`, `.pptx`, `.ppt` | document | document | Document conversion |
| (other) | unknown | (none) | Show unsupported message |

---

## Config File Examples

### Default Config (new installation)
```json
{
  "output_folder": null,
  "default_codec": "original",
  "theme_mode": "auto",
  "version": 1
}
```

### User-Modified Config
```json
{
  "output_folder": "C:\\Users\\Alice\\Videos\\Converted",
  "default_codec": "h264",
  "theme_mode": "dark",
  "version": 1
}
```

### Merged Config (after app update adds new field)
```json
{
  "output_folder": "C:\\Users\\Alice\\Videos\\Converted",
  "default_codec": "h264",
  "theme_mode": "dark",
  "new_future_field": "default_value",
  "version": 2
}
```
