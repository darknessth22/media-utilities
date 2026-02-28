import os
import sys

def is_vlc_available() -> bool:
    """
    Check if VLC is available on the system.
    Returns True if VLC is installed and the python-vlc binding can find it.
    """
    try:
        import vlc
        # Try to create a VLC instance. Failure indicates missing native libraries.
        instance = vlc.Instance('--no-xlib')
        if instance:
            instance.release()
            return True
        return False
    except (ImportError, OSError, Exception):
        return False
