"""Dependency checking and auto-installation helpers."""
import subprocess
import sys

from utils.ffmpeg import ffmpeg_path


def install(package: str) -> None:
    """Install a Python package via pip."""
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])


def check_dependencies() -> str | None:
    """Check all runtime dependencies.

    Returns
    -------
    'ffmpeg_missing'  if FFmpeg cannot be found, else None.
    """
    # yt-dlp
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        print("Installing yt-dlp...")
        install("yt-dlp")

    # FFmpeg (critical)
    try:
        subprocess.run([ffmpeg_path, "-version"], capture_output=True, check=True)
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

    # GUI and Document Conversion dependencies
    for package in ["ttkbootstrap", "darkdetect", "docx2pdf"]:
        try:
            __import__(package)
        except ImportError:
            print(f"Installing {package}...")
            install(package)

    # LibreOffice (for DOCX to PDF fallback)
    try:
        # On Windows, try soffice; on others, try libreoffice
        cmds = ["soffice", "libreoffice"] if sys.platform == "win32" else ["libreoffice", "soffice"]
        found_lo = False
        for cmd in cmds:
            try:
                subprocess.run([cmd, "--version"], capture_output=True, check=True)
                found_lo = True
                break
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        if not found_lo:
            pass
    except Exception:
        pass

    # spotdl (Spotify support) — optional, not available on Python 3.14+
    try:
        result = subprocess.run(
            ["spotdl", "--version"], capture_output=True, text=True, check=True
        )
        print(f"spotdl available: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("spotdl not found — Spotify downloads will be unavailable.")
        print("Install on Python <=3.13 with: pip install 'spotdl>=3.9.6'")

    return None
