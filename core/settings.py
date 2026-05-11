import os
import json
import platform
import shutil
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

# Last-load diagnostic. Cleared on successful loads; populated when a corrupt
# or unreadable config triggered a fallback to defaults. The GUI reads this
# right after `SettingsManager.load()` to toast the user.
LAST_LOAD_ERROR: str | None = None
LAST_LOAD_BACKUP_PATH: str | None = None


@dataclass
class UserSettings:
    """Represents all user-configurable preferences."""
    output_folder: str | None = None
    default_codec: str = "original"
    theme_mode: str = "dark"
    quit_on_close: bool = True
    intercept_timeout: int = 30
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    tutorial_seen: bool = False
    cookies_browser: str = ""
    cookies_file: str = ""
    hw_accel: str = "none"
    output_name_template: str = "{name}_converted"
    presets: dict = field(default_factory=dict)
    start_with_windows: bool = False
    language: str = "en"
    extension_bridge_enabled: bool = True
    extension_bridge_port: int = 17654
    version: int = 11


class SettingsManager:
    """Manages loading, saving, and merging of user settings."""
    
    APP_NAME = "media-utilities"
    CONFIG_FILENAME = "config.json"
    
    @classmethod
    def get_config_path(cls) -> Path:
        """Get the platform-specific path for the configuration file."""
        system = platform.system()
        
        if system == "Windows":
            # %APPDATA%\media-utilities\config.json
            appdata = os.environ.get("APPDATA")
            if not appdata:
                appdata = os.path.expanduser("~\\AppData\\Roaming")
            base_dir = Path(appdata)
        elif system == "Darwin":
            # ~/Library/Application Support/media-utilities/config.json
            base_dir = Path.home() / "Library" / "Application Support"
        else:
            # ~/.config/media-utilities/config.json (Linux and others)
            config_home = os.environ.get("XDG_CONFIG_HOME")
            if not config_home:
                config_home = os.path.expanduser("~/.config")
            base_dir = Path(config_home)
            
        config_dir = base_dir / cls.APP_NAME
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / cls.CONFIG_FILENAME

    @classmethod
    def get_default_settings(cls) -> UserSettings:
        return UserSettings()

    @classmethod
    def _backup_corrupt(cls, config_path: Path, reason: str) -> str | None:
        """Move a corrupt config file aside before defaults overwrite it.

        Returns the backup path (or None if the move itself failed). Records
        diagnostic info in module globals so the GUI can show a toast.
        """
        global LAST_LOAD_ERROR, LAST_LOAD_BACKUP_PATH
        LAST_LOAD_ERROR = reason
        if not config_path.exists():
            LAST_LOAD_BACKUP_PATH = None
            return None
        ts = time.strftime("%Y%m%d-%H%M%S")
        backup = config_path.with_name(f"{config_path.name}.corrupt-{ts}")
        try:
            shutil.move(str(config_path), str(backup))
            LAST_LOAD_BACKUP_PATH = str(backup)
            return str(backup)
        except OSError:
            LAST_LOAD_BACKUP_PATH = None
            return None

    @classmethod
    def load(cls) -> UserSettings:
        """Load settings from disk and merge with defaults if necessary."""
        global LAST_LOAD_ERROR, LAST_LOAD_BACKUP_PATH
        LAST_LOAD_ERROR = None
        LAST_LOAD_BACKUP_PATH = None

        config_path = cls.get_config_path()
        default_settings = cls.get_default_settings()

        if not config_path.exists():
            return default_settings

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # Merge loaded data with defaults, keeping defaults for missing keys
            merged_data = asdict(default_settings)
            
            # Update with loaded values if they exist in the dataclass
            # This ignores unknown/obsolete keys from the file
            for key, value in data.items():
                if key in merged_data:
                    merged_data[key] = value
            
            # Migration support
            if merged_data.get("version", 1) < 2:
                merged_data["version"] = 2
            if merged_data.get("version", 1) < 3:
                merged_data.setdefault("intercept_timeout", 30)
                merged_data["version"] = 3
            if merged_data.get("version", 1) < 4:
                merged_data.setdefault("spotify_client_id", "")
                merged_data.setdefault("spotify_client_secret", "")
                merged_data["version"] = 4
            if merged_data.get("version", 1) < 5:
                merged_data.setdefault("tutorial_seen", False)
                merged_data["version"] = 5
            if merged_data.get("version", 1) < 6:
                merged_data.setdefault("cookies_browser", "")
                merged_data["version"] = 6
            if merged_data.get("version", 1) < 7:
                merged_data.setdefault("hw_accel", "none")
                merged_data["version"] = 7
            if merged_data.get("version", 1) < 8:
                merged_data.setdefault("output_name_template", "{name}_converted")
                merged_data.setdefault("presets", {})
                merged_data["version"] = 8
            if merged_data.get("version", 1) < 9:
                merged_data.setdefault("start_with_windows", False)
                merged_data["version"] = 9
            if merged_data.get("version", 1) < 10:
                merged_data.setdefault("language", "en")
                merged_data["version"] = 10
            if merged_data.get("version", 1) < 11:
                merged_data.setdefault("extension_bridge_enabled", True)
                merged_data.setdefault("extension_bridge_port", 17654)
                merged_data["version"] = 11

            return UserSettings(**merged_data)
        except json.JSONDecodeError as exc:
            cls._backup_corrupt(config_path, f"config JSON parse error: {exc}")
            return default_settings
        except TypeError as exc:
            # Schema mismatch — keys present that UserSettings can't accept.
            cls._backup_corrupt(config_path, f"config schema mismatch: {exc}")
            return default_settings
        except OSError as exc:
            # Read failure (permissions, locked file, disk error). Don't move
            # the file aside — we couldn't even read it; preserve user data.
            LAST_LOAD_ERROR = f"config read error: {exc}"
            LAST_LOAD_BACKUP_PATH = None
            return default_settings

    @classmethod
    def save(cls, settings: UserSettings) -> bool:
        """Save settings to disk using atomic write."""
        config_path = cls.get_config_path()
        temp_path = config_path.with_suffix(".temp")
        
        # Clamp intercept_timeout to valid range
        settings.intercept_timeout = max(10, min(300, settings.intercept_timeout))

        try:
            # Write to temp file first
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(asdict(settings), f, indent=2)
                # Ensure it's written to disk before renaming
                f.flush()
                os.fsync(f.fileno())
                
            # Atomic rename (on POSIX) or replacement (Windows)
            os.replace(temp_path, config_path)
            return True
        except OSError:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            return False

    @classmethod
    def reset(cls) -> UserSettings:
        """Reset settings to default and save."""
        default_settings = cls.get_default_settings()
        cls.save(default_settings)
        return default_settings
