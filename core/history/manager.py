import json
import os
from pathlib import Path
from core.history.models import HistoryItem
from core.settings import SettingsManager

class HistoryManager:
    MAX_ITEMS = 10
    FILENAME = "history.json"

    def __init__(self):
        self.items = []
        self._load()

    def _get_file_path(self) -> Path:
        # Save alongside the config file
        try:
            return SettingsManager.get_config_path().parent / self.FILENAME
        except Exception:
            # Fallback
            return Path(os.path.expanduser("~")) / ".media_utilities_history.json"

    def _load(self):
        path = self._get_file_path()
        if not path.exists():
            return
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    # Sort by timestamp descending so newest is first
                    self.items = [HistoryItem.from_dict(item) for item in data]
                    self.items.sort(key=lambda x: x.timestamp, reverse=True)
        except Exception as e:
            print(f"Error loading history: {e}")

    def _save(self):
        path = self._get_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump([item.to_dict() for item in self.items], f, indent=2)
        except Exception as e:
            print(f"Error saving history: {e}")

    def add_item(self, item: HistoryItem):
        # Insert at the beginning
        self.items.insert(0, item)
        # Enforce 10-item limit
        if len(self.items) > self.MAX_ITEMS:
            self.items = self.items[:self.MAX_ITEMS]
        self._save()

    def get_items(self) -> list[HistoryItem]:
        return self.items

    def clear_all(self):
        self.items = []
        self._save()

# Global instance
_manager = None

def get_history_manager() -> HistoryManager:
    global _manager
    if _manager is None:
        _manager = HistoryManager()
    return _manager
