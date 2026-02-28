# Research: Drag-Drop, Rich Trimmer & Global Settings

**Feature Branch**: `004-drag-trimmer-settings`
**Date**: 2026-02-28

## Technology Decisions

### 1. Drag-and-Drop Implementation

**Decision**: Use `tkinterdnd2` library for native drag-and-drop support

**Rationale**:
- Native integration with tkinter (the project's existing GUI framework)
- Cross-platform support (Windows, macOS, Linux)
- Supports file drops from OS file managers
- Lightweight dependency (~50KB)
- Active maintenance and wide adoption

**Alternatives Considered**:
- **Native tkinter DnD**: Limited to within-app DnD only, cannot receive OS file drops
- **PyQt/PySide**: Would require full GUI framework migration
- **Platform-specific APIs**: Would violate cross-platform principle

**Implementation Notes**:
- Install: `pip install tkinterdnd2`
- Requires `TkinterDnD.Tk()` as root window instead of standard `tk.Tk()`
- Use `drop_target_register(DND_FILES)` on main window
- Parse dropped data to extract file paths

---

### 2. Video Playback Library

**Decision**: Use `python-vlc` (VLC media player bindings)

**Rationale**:
- Broad codec support (plays virtually any video format)
- Proven tkinter integration via embedding VLC window
- Cross-platform (Windows, macOS, Linux)
- Supports seeking, muting, volume control
- Handles corrupted/partial files gracefully
- Active community and stable API

**Alternatives Considered**:
- **opencv-python**: Frame extraction only, no native audio playback
- **tkinter-native (PIL frames)**: Very limited, poor performance, no audio
- **ffpyplayer**: Lighter but less mature tkinter integration
- **PyAV**: Lower-level, more complex to embed

**Implementation Notes**:
- Install: `pip install python-vlc`
- Requires VLC installed on user's system (not bundled)
- Embed using `vlc.Instance().media_player_new()`
- Set window handle: `player.set_hwnd(widget.winfo_id())` on Windows
- Use `player.set_xwindow()` on Linux, `player.set_nsobject()` on macOS

**VLC Detection Strategy**:
```python
import vlc
try:
    instance = vlc.Instance()
    if instance is None:
        raise RuntimeError("VLC not found")
except Exception:
    # Show warning dialog with installation instructions
```

---

### 3. Settings Persistence

**Decision**: JSON file in platform-specific app data directory

**Rationale**:
- Human-readable for debugging
- Native Python support (no additional dependencies)
- Easy to merge/migrate between schema versions
- Standard practice for desktop applications

**Alternatives Considered**:
- **TOML**: Requires additional dependency, no significant benefit
- **SQLite**: Overkill for simple key-value settings
- **Pickle**: Not human-readable, security concerns
- **INI files**: Less flexible for nested structures

**Storage Locations**:
| Platform | Path |
|----------|------|
| Windows | `%APPDATA%\media-utilities\config.json` |
| macOS | `~/Library/Application Support/media-utilities/config.json` |
| Linux | `~/.config/media-utilities/config.json` |

**Schema Migration Strategy**:
- Load existing config
- Merge with defaults (existing keys preserved, new keys get defaults)
- Write back merged config
- No version number needed for simple merge strategy

---

### 4. VLC Dependency Handling

**Decision**: Require as system dependency with detection and warning

**Rationale**:
- Simpler distribution (no bundling complexity)
- Smaller download size
- VLC is commonly installed by users
- Can provide graceful fallback to text-only timestamps

**Implementation Notes**:
- Check VLC availability at startup
- If missing, show non-blocking warning with:
  - Download link: https://www.videolan.org/vlc/
  - Explanation that visual trimmer requires VLC
  - Confirm text-based trimming still works

---

### 5. File Type Detection for Drag-Drop

**Decision**: Extension-based detection with predefined mapping

**Rationale**:
- Fast (no file reading required)
- Sufficient for supported formats
- Matches existing file dialog filters

**File Type Mapping**:
```python
FILE_TYPE_MAP = {
    # Video → Trim Media tab
    ".mp4": "trim", ".mkv": "trim", ".avi": "trim",
    ".mov": "trim", ".webm": "trim", ".flv": "trim",

    # Audio → Trim Media tab
    ".mp3": "trim", ".wav": "trim", ".aac": "trim",
    ".flac": "trim", ".ogg": "trim", ".m4a": "trim",

    # Image → Convert Media tab
    ".jpg": "convert", ".jpeg": "convert", ".png": "convert",
    ".heic": "convert", ".heif": "convert", ".webp": "convert",
    ".gif": "convert", ".bmp": "convert",

    # Document → Document Convert tab
    ".pdf": "document", ".docx": "document", ".doc": "document",
    ".xlsx": "document", ".xls": "document",
    ".pptx": "document", ".ppt": "document",
}
```

---

### 6. Video Size Limits

**Decision**: 4GB soft limit with performance warning

**Rationale**:
- Covers vast majority of user content
- Avoids complexity of chunked streaming
- Compatible with FAT32 filesystem limits
- Clear user expectations

**Implementation Notes**:
- Check file size before loading
- If >4GB, show warning dialog: "Large file detected. Playback may be slow."
- Proceed with loading regardless (soft limit)

---

## Dependencies Summary

### New Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `tkinterdnd2` | >=0.3 | Drag-and-drop support |
| `python-vlc` | >=3.0.18 | Video playback |

### External Requirements

| Tool | Required | Notes |
|------|----------|-------|
| VLC | Yes (for visual trimmer) | Detect at runtime, warn if missing |

### Existing Dependencies (unchanged)

- ttkbootstrap
- darkdetect
- Pillow, pillow-heif
- PyMuPDF, python-docx
- yt-dlp, spotdl

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| VLC not installed | Medium | Medium | Fallback to text timestamps, clear install instructions |
| tkinterdnd2 platform issues | Low | High | Test on all platforms, have fallback Browse button |
| VLC embedding issues on macOS | Medium | Medium | Test thoroughly, document known issues |
| Large video performance | Low | Low | Soft limit warning, async loading |
