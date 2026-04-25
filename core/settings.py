import os
import json
import platform
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class UserSettings:
    """Represents all user-configurable preferences."""
    output_folder: str | None = None
    default_codec: str = "original"
    theme_mode: str = "auto"
    quit_on_close: bool = True
    intercept_timeout: int = 30
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    version: int = 4


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
    def load(cls) -> UserSettings:
        """Load settings from disk and merge with defaults if necessary."""
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

            return UserSettings(**merged_data)
        except (json.JSONDecodeError, OSError, TypeError):
            # Fallback to defaults on error
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
