"""Independent yt-dlp updater.

Frozen builds ship a yt-dlp pinned at build time. Sites like Facebook,
Instagram and TikTok change often and break the bundled extractor; rebuilding
all of Videl just to refresh yt-dlp is heavy. Instead we pip-install yt-dlp into
a user-writable directory and prepend it to ``sys.path`` at launch so it shadows
the bundled copy. Users can then update the extractor engine on demand from
Settings without waiting for a Videl release.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from urllib.request import Request, urlopen

from utils.paths import user_data_dir

# CREATE_NO_WINDOW — keep pip from flashing a console in the windowed build.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def ytdlp_dir() -> str:
    """User-writable pip --target dir for the on-demand yt-dlp install."""
    return os.path.join(str(user_data_dir()), "ytdlp")


def activate_user_ytdlp() -> None:
    """Prepend the user yt-dlp dir to sys.path so it shadows the bundled copy.

    Must run before the first ``import yt_dlp``. No-op when nothing is installed.
    """
    d = ytdlp_dir()
    if os.path.isdir(os.path.join(d, "yt_dlp")) and d not in sys.path:
        sys.path.insert(0, d)


def current_version() -> str:
    """Version of the yt-dlp that is currently importable (bundled or user)."""
    try:
        import yt_dlp.version as _v
        return getattr(_v, "__version__", "") or ""
    except Exception:
        try:
            import yt_dlp
            return getattr(yt_dlp, "__version__", "") or ""
        except Exception:
            return ""


def installed_target_version() -> str:
    """Version present in the user dir, read from disk (no import needed).

    The running process already imported the bundled yt-dlp, so a fresh install
    in the user dir won't be reflected by ``current_version()`` until restart.
    Parse ``version.py`` directly to report what the next launch will load.
    """
    vfile = os.path.join(ytdlp_dir(), "yt_dlp", "version.py")
    try:
        with open(vfile, encoding="utf-8") as f:
            m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", f.read())
            return m.group(1) if m else ""
    except OSError:
        return ""


def latest_version(timeout: int = 15) -> str:
    """Latest yt-dlp version string from PyPI, or '' on failure."""
    try:
        req = Request("https://pypi.org/pypi/yt-dlp/json", headers={"User-Agent": "Videl"})
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        return data.get("info", {}).get("version", "") or ""
    except Exception:
        return ""


def update(timeout: int = 300) -> tuple[int, str]:
    """pip-install the latest yt-dlp master into the user dir.

    Installs straight from the yt-dlp GitHub master branch rather than the
    PyPI stable release: extractors for Facebook/Instagram/TikTok break often
    and fixes can lag weeks behind a stable cut (e.g. the Instagram "empty
    media response" fix landed on master before any stable release had it).

    Returns (returncode, combined_output). The new version loads on next launch
    via :func:`activate_user_ytdlp`.
    """
    d = ytdlp_dir()
    os.makedirs(d, exist_ok=True)

    try:
        from utils.bundled_runtime import bundled_python_path
        py = bundled_python_path()
    except Exception:
        py = sys.executable

    base = [
        py, "-m", "pip", "install",
        "--no-warn-script-location", "--disable-pip-version-check",
        "--target", d,
    ]

    # yt-dlp master tarball has no version pip can compare against a prior
    # install, so force-reinstall it every time to guarantee the latest code.
    ytdlp_result = subprocess.run(
        base + ["--upgrade", "--force-reinstall",
                "https://github.com/yt-dlp/yt-dlp/archive/refs/heads/master.tar.gz"],
        capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW,
    )
    output = (ytdlp_result.stdout or "") + (ytdlp_result.stderr or "")
    if ytdlp_result.returncode != 0:
        return ytdlp_result.returncode, output

    # curl_cffi enables yt-dlp's browser-impersonation path, required by the
    # reworked Instagram extractor. Versioned on PyPI, so a plain --upgrade
    # skips re-downloading the compiled wheel when already current.
    curl_cffi_result = subprocess.run(
        base + ["--upgrade", "curl_cffi"],
        capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW,
    )
    output += (curl_cffi_result.stdout or "") + (curl_cffi_result.stderr or "")
    return curl_cffi_result.returncode, output
