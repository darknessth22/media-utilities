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
    """pip-install the latest yt-dlp nightly into the user dir.

    Installs the nightly pre-release wheel from PyPI (``--pre``) rather than
    the stable release: extractors for Facebook/Instagram/TikTok break often
    and fixes can lag weeks behind a stable cut (e.g. the Instagram "empty
    media response" fix landed on master before any stable release had it).
    A wheel, not the GitHub master tarball — building the tarball needs the
    hatchling build backend, which the frozen build's bundled Python cannot
    import (BackendUnavailable), while wheels install without any build step.

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

    # Nightly wheels carry dated versions (e.g. 2026.7.9.234832.dev0), so a
    # plain --upgrade correctly replaces any older install, including ones
    # left behind by the old tarball-based updater. yt-dlp-ejs rides along:
    # it holds the YouTube n-sig solver scripts, and a new nightly may need
    # a newer solver than the one frozen into the app.
    ytdlp_result = subprocess.run(
        base + ["--upgrade", "--pre", "yt-dlp", "yt-dlp-ejs"],
        capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW,
    )
    output = (ytdlp_result.stdout or "") + (ytdlp_result.stderr or "")
    if ytdlp_result.returncode != 0:
        return ytdlp_result.returncode, output

    # curl_cffi enables yt-dlp's browser-impersonation path, required by the
    # reworked Instagram extractor. It cannot be upgraded in place: the running
    # app keeps its _wrapper.pyd loaded, and Windows locks loaded modules, so
    # pip dies with PermissionError (WinError 5). When it is already installed,
    # defer the upgrade to the next launch (see finish_pending_updates), which
    # runs before anything imports it.
    if os.path.isdir(os.path.join(d, "curl_cffi")):
        _write_marker()
        return 0, output
    curl_cffi_result = subprocess.run(
        base + ["curl_cffi"],
        capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW,
    )
    output += (curl_cffi_result.stdout or "") + (curl_cffi_result.stderr or "")
    return curl_cffi_result.returncode, output


# ── Launch-time maintenance ──────────────────────────────────────────────────

def _marker_path() -> str:
    return os.path.join(ytdlp_dir(), "curl_cffi_update_pending")


def _write_marker() -> None:
    try:
        with open(_marker_path(), "w") as f:
            f.write("upgrade curl_cffi on next launch\n")
    except OSError:
        pass


def finish_pending_updates(timeout: int = 300) -> None:
    """Upgrade curl_cffi if a previous update deferred it.

    MUST run at launch before anything imports curl_cffi or yt_dlp — once the
    .pyd is loaded, Windows locks it and the upgrade fails until next launch.
    Fast no-op (one stat call) when nothing is pending; failures keep the
    marker so the next launch retries.
    """
    if not os.path.exists(_marker_path()):
        return
    try:
        from utils.bundled_runtime import bundled_python_path
        py = bundled_python_path()
    except Exception:
        py = sys.executable
    try:
        result = subprocess.run(
            [py, "-m", "pip", "install",
             "--no-warn-script-location", "--disable-pip-version-check",
             "--target", ytdlp_dir(), "--upgrade", "curl_cffi"],
            capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW,
        )
        if result.returncode == 0:
            os.remove(_marker_path())
    except Exception:
        pass


def _version_date(version: str):
    """Parse a yt-dlp version string (stable or nightly) into a date, or None."""
    from datetime import date
    m = re.match(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", version or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def auto_update_if_stale(max_age_days: int = 7) -> bool:
    """Run :func:`update` when the effective yt-dlp is older than the cutoff.

    Extractors rot quickly; most users never find the manual update button —
    they just report the app as broken. Meant for a background thread at
    launch. Returns True when an update was run (applies on next launch).
    """
    from datetime import date, timedelta
    ver = installed_target_version() or current_version()
    d = _version_date(ver)
    if d is not None and date.today() - d <= timedelta(days=max_age_days):
        return False
    rc, _ = update()
    return rc == 0
