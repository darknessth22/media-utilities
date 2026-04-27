"""Windows startup registry helper — set/clear/check the Run key."""
import sys

_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_REG_VALUE = "MediaUtility"


def _get_launch_command() -> str:
    """Return the command to register — exe path when frozen, otherwise python + script."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    import os
    script = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "main.py")
    )
    return f'"{sys.executable}" "{script}"'


def is_startup_enabled() -> bool:
    """Return True if the app's startup entry exists in the registry."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY) as key:
            winreg.QueryValueEx(key, _REG_VALUE)
            return True
    except (OSError, FileNotFoundError):
        return False


def set_startup(enabled: bool) -> bool:
    """Add or remove the startup registry entry. Returns True on success."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, _REG_VALUE, 0, winreg.REG_SZ, _get_launch_command())
            else:
                try:
                    winreg.DeleteValue(key, _REG_VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
