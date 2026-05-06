"""Dependency checking and auto-installation helpers."""
import subprocess
import sys

from utils.ffmpeg import ffmpeg_path

# Windowed (frozen) build has no console; spawning a console subprocess
# without this flag flashes a cmd window. 0x08000000 = CREATE_NO_WINDOW.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def check_playwright_installed() -> tuple[bool, str]:
    """Check if playwright package and Chromium binary are available."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return False, "Playwright not installed. Run: pip install playwright && python -m playwright install chromium"

    # Probe binary by launching a minimal context in a subprocess to avoid
    # polluting the main process on failure.
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "from playwright.sync_api import sync_playwright; "
             "p = sync_playwright().__enter__(); "
             "b = p.chromium.launch(headless=True); "
             "b.close(); "
             "p.__exit__(None,None,None)"],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=_NO_WINDOW,
        )
        if result.returncode != 0:
            return False, "Playwright Chromium not installed. Run: python -m playwright install chromium"
        return True, ""
    except Exception:
        return False, "Playwright Chromium not installed. Run: python -m playwright install chromium"


def install(package: str) -> None:
    """Install a Python package via pip."""
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])


def check_dependencies() -> str | None:
    """Check all runtime dependencies.

    Returns
    -------
    'ffmpeg_missing'  if FFmpeg cannot be found, else None.
    """
    # PySide6 (critical — without it the GUI cannot start)
    try:
        import PySide6  # noqa: F401
    except ImportError:
        print("Installing PySide6...")
        install("PySide6>=6.6.0")

    # yt-dlp
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        print("Installing yt-dlp...")
        install("yt-dlp")

    # FFmpeg (critical)
    try:
        subprocess.run([ffmpeg_path, "-version"], capture_output=True, check=True, creationflags=_NO_WINDOW)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("\nFFmpeg not found! Media conversion features will be unavailable.")
        return "ffmpeg_missing"

    # pillow-heif (HEIC image support)
    try:
        import pillow_heif  # noqa: F401
    except ImportError:
        print("\nInstalling pillow-heif for HEIC support...")
        install("pillow-heif")
        import pillow_heif
        pillow_heif.register_heif_opener()

    # docx2pdf (DOCX → PDF on Windows/macOS)
    try:
        import docx2pdf  # noqa: F401
    except ImportError:
        print("Installing docx2pdf...")
        install("docx2pdf")

    # LibreOffice (for DOCX to PDF fallback on Linux)
    try:
        cmds = ["soffice", "libreoffice"] if sys.platform == "win32" else ["libreoffice", "soffice"]
        for cmd in cmds:
            try:
                subprocess.run([cmd, "--version"], capture_output=True, check=True, creationflags=_NO_WINDOW)
                break
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
    except Exception:
        pass

    # spotdl (Spotify support) — optional, not available on Python 3.14+
    try:
        result = subprocess.run(
            ["spotdl", "--version"], capture_output=True, text=True, check=True,
            creationflags=_NO_WINDOW,
        )
        print(f"spotdl available: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("spotdl not found — Spotify downloads will be unavailable.")
        print("Install on Python <=3.13 with: pip install 'spotdl>=3.9.6'")

    return None
