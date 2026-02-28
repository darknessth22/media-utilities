# Quickstart: Drag-Drop, Rich Trimmer & Global Settings

**Feature Branch**: `004-drag-trimmer-settings`
**Date**: 2026-02-28

## Prerequisites

### System Requirements

1. **Python 3.10+** (3.12 recommended)
2. **VLC Media Player** - Required for visual video trimmer
   - Windows: https://www.videolan.org/vlc/download-windows.html
   - macOS: https://www.videolan.org/vlc/download-macosx.html
   - Linux: `sudo apt install vlc` or equivalent

### Verify VLC Installation

```bash
# Windows (PowerShell)
vlc --version

# macOS/Linux
vlc --version
```

## Setup

### 1. Clone and checkout feature branch

```bash
git checkout 004-drag-trimmer-settings
```

### 2. Install dependencies

```bash
pip install -r requirements.txt

# New dependencies for this feature:
pip install tkinterdnd2 python-vlc
```

### 3. Verify installation

```bash
python -c "import tkinterdnd2; print('tkinterdnd2 OK')"
python -c "import vlc; vlc.Instance(); print('python-vlc OK')"
```

## Development Workflow

### Running the application

```bash
python main.py
```

### Testing drag-and-drop

1. Start the application
2. Drag any supported file from your file manager onto the app window
3. Verify the correct tab activates and file path appears

### Testing video trimmer

1. Go to "Trim Media" tab
2. Load a video file (drag or Browse)
3. Verify VLC player appears with timeline
4. Drag handles to set trim points
5. Click Play to preview selection
6. Click Trim to export

### Testing settings

1. Click gear icon in status bar
2. Change settings (output folder, codec, theme)
3. Close settings panel
4. Close and reopen app
5. Verify settings persisted

## File Structure (New/Modified)

```
core/
└── settings.py          # NEW: Settings persistence

gui/
├── app.py               # MODIFY: Add DnD, settings button
├── dnd_handler.py       # NEW: Drag-and-drop logic
├── settings_panel.py    # NEW: Settings UI
└── video_trimmer.py     # NEW: VLC player widget

utils/
└── vlc_check.py         # NEW: VLC detection
```

## Key Implementation Notes

### Drag-and-Drop (tkinterdnd2)

```python
from tkinterdnd2 import DND_FILES, TkinterDnD

# Must use TkinterDnD.Tk() as root window
root = TkinterDnD.Tk()

# Register drop target
root.drop_target_register(DND_FILES)
root.dnd_bind('<<Drop>>', on_drop)

def on_drop(event):
    files = event.data  # Space-separated paths (quoted if spaces)
```

### VLC Embedding

```python
import vlc
import sys

instance = vlc.Instance()
player = instance.media_player_new()

# Platform-specific window embedding
if sys.platform == "win32":
    player.set_hwnd(widget.winfo_id())
elif sys.platform == "darwin":
    player.set_nsobject(widget.winfo_id())
else:
    player.set_xwindow(widget.winfo_id())
```

### Settings Paths

```python
import sys
from pathlib import Path

def get_config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", "~"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config"))
    return base / "media-utilities"
```

## Testing Checklist

- [ ] Drag video file → Trim tab activates, file loads
- [ ] Drag PDF file → Document tab activates
- [ ] Drag image file → Convert tab activates
- [ ] Drag unsupported file → Error message shown
- [ ] Drag multiple same-type files → Batch tab activates
- [ ] Drag multiple mixed files → Error message shown
- [ ] Video trimmer shows timeline with handles
- [ ] Dragging handles updates timestamps
- [ ] Preview plays selected segment
- [ ] Trim exports correct segment
- [ ] Settings panel opens/closes
- [ ] Settings persist across restarts
- [ ] Reset to Defaults works
- [ ] App works without VLC (fallback mode)

## Troubleshooting

### "VLC not found" error

- Ensure VLC is installed and on system PATH
- On Windows, may need to add VLC to PATH manually
- Try: `set PATH=%PATH%;C:\Program Files\VideoLAN\VLC`

### tkinterdnd2 import error

- Ensure Python matches system architecture (64-bit Python needs 64-bit tkdnd)
- Try reinstalling: `pip uninstall tkinterdnd2 && pip install tkinterdnd2`

### Video doesn't play

- Check file format is supported by VLC
- Try playing file directly in VLC to verify it's not corrupted
- Check Python console for error messages
