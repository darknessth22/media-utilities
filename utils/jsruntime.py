"""Deno provisioning for yt-dlp's YouTube JS challenge solver.

yt-dlp solves YouTube n-sig/sig challenges through yt-dlp-ejs, which needs a
real JavaScript runtime (Deno preferred, Node accepted) found on PATH. Without
one it falls back to the built-in Python interpreter, which upstream has
deprecated and will eventually drop — at which point YouTube extraction dies
for every user without a runtime installed.

Bundling deno.exe into the installer would cost ~110 MB against the size
budget, so instead we download a pinned Deno release into a user-writable
directory on demand (same pattern as the on-demand AI packages) and prepend
it to PATH so yt-dlp-ejs discovers it.
"""
from __future__ import annotations

import os
import shutil
import sys
import zipfile
from urllib.request import Request, urlopen

from utils.paths import user_data_dir

# Pinned so every install gets a version we have actually run. Bump alongside
# yt-dlp-ejs requirements when upstream raises its minimum.
_DENO_VERSION = "2.7.14"

_DENO_ASSETS = {
    "win32": "deno-x86_64-pc-windows-msvc.zip",
    "linux": "deno-x86_64-unknown-linux-gnu.zip",
}


def deno_dir() -> str:
    """User-writable directory holding the on-demand Deno install."""
    return os.path.join(str(user_data_dir()), "deno")


def deno_path() -> str:
    """Path of the provisioned deno executable, or '' if not installed."""
    exe = "deno.exe" if sys.platform == "win32" else "deno"
    p = os.path.join(deno_dir(), exe)
    return p if os.path.isfile(p) else ""


def has_js_runtime() -> bool:
    """True when yt-dlp-ejs can find a JS runtime (system or provisioned)."""
    return bool(shutil.which("deno") or shutil.which("node") or deno_path())


def activate_js_runtime() -> None:
    """Prepend the provisioned Deno dir to PATH so yt-dlp-ejs finds it.

    Safe to call repeatedly; no-op when Deno was never provisioned (a system
    deno/node on PATH is already discoverable without our help).
    """
    if deno_path() and deno_dir() not in os.environ.get("PATH", ""):
        os.environ["PATH"] = deno_dir() + os.pathsep + os.environ.get("PATH", "")


def ensure_deno(timeout: int = 600) -> bool:
    """Provision Deno if no JS runtime is available. Returns True when one is.

    Downloads the pinned release zip (~40 MB) into the user dir and extracts
    the single executable. Meant to run on a background thread at launch;
    failures are non-fatal — yt-dlp falls back to its built-in interpreter.
    """
    if has_js_runtime():
        activate_js_runtime()
        return True

    asset = None
    for platform_prefix, name in _DENO_ASSETS.items():
        if sys.platform.startswith(platform_prefix):
            asset = name
            break
    if asset is None:
        return False

    url = (
        f"https://github.com/denoland/deno/releases/download/"
        f"v{_DENO_VERSION}/{asset}"
    )
    d = deno_dir()
    os.makedirs(d, exist_ok=True)
    zip_path = os.path.join(d, asset)
    try:
        req = Request(url, headers={"User-Agent": "Videl"})
        with urlopen(req, timeout=timeout) as resp, open(zip_path, "wb") as out:
            shutil.copyfileobj(resp, out)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(d)
        if sys.platform != "win32":
            exe = os.path.join(d, "deno")
            os.chmod(exe, os.stat(exe).st_mode | 0o755)
        activate_js_runtime()
        return bool(deno_path())
    except Exception:
        return False
    finally:
        try:
            os.remove(zip_path)
        except OSError:
            pass
