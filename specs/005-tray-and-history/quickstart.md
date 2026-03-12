# Quickstart

This document provides a quick overview of how the System Tray and History features will be integrated into the existing `media-utilities` application.

## 1. System Tray Integration (`core/tray.py`)

The application will use the `pystray` library to create a lightweight system tray icon.

```python
import pystray
from PIL import Image

def on_quit(icon, item):
    icon.stop()
    # Trigger application exit

def on_restore(icon, item):
    # Trigger application restore
    pass

def setup_tray(icon_path):
    image = Image.open(icon_path)
    menu = pystray.Menu(
        pystray.MenuItem("Restore", on_restore, default=True),
        pystray.MenuItem("Settings", lambda: None),
        pystray.MenuItem("Quit/Exit", on_quit)
    )
    icon = pystray.Icon("Media Utilities", image, "Media Utilities", menu)
    return icon
```

The system tray component needs to run in a way that doesn't block the main `tkinter` event loop, or vice versa, typically by running the tray icon in a separate thread.

## 2. Interactive Notifications (`core/notifications.py`)

We use `desktop-notifier` to send cross-platform notifications and handle click events.

```python
import asyncio
from desktop_notifier import DesktopNotifier, Notification, Button

notifier = DesktopNotifier(app_name="Media Utilities")

async def notify_completion(title, message, hit_history_callback):
    n = Notification(
        title=title,
        message=message,
        on_clicked=hit_history_callback
    )
    await notifier.send(n)
```
Because `desktop-notifier` is asynchronous, integration with `tkinter` requires managing an `asyncio` event loop alongside the GUI.

## 3. History Management (`core/history/`)

The history manager handles creating, storing, and pruning history items.

```python
# models.py
from dataclasses import dataclass
import time

@dataclass
class HistoryItem:
    id: str
    task_type: str
    file_name: str
    file_path: str
    timestamp: float
    status: str

# manager.py
import json

class HistoryManager:
    def __init__(self, persistence_path, limit=10):
        self.path = persistence_path
        self.limit = limit
        self.items = self._load()

    def add_item(self, item: HistoryItem):
        self.items.insert(0, item)
        if len(self.items) > self.limit:
            self.items = self.items[:self.limit]
        self._save()
        
    def clear_all(self):
        self.items = []
        self._save()
```

## 4. Main Window Modifications (`gui/main_window.py`)

- **Minimizing to Tray**: The `WM_DELETE_WINDOW` protocol needs to be overridden so closing the window hides it instead of destroying the application.
- **History Tab**: A new `ttk.Frame` will be added to the main notebook to display the history items dynamically.

```python
# Hiding instead of closing
root.protocol('WM_DELETE_WINDOW', lambda: root.withdraw())
```
