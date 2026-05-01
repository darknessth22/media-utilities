"""On-demand AI model package installer — works both in dev and frozen PyInstaller exe."""
from __future__ import annotations

import os
import subprocess
import sys


def _ai_packages_dir() -> str:
    """Return the directory where AI packages are installed at runtime.

    In a frozen exe, packages can't go into the bundled Python; they go into
    an 'ai_packages' folder next to the executable so they persist across runs.
    In dev mode, normal pip install into the active venv is used instead.
    """
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "ai_packages")
    return ""  # empty = normal pip install, no --target


def ensure_ai_packages_on_path() -> None:
    """Call once at startup so any previously installed AI packages are importable."""
    pkg_dir = _ai_packages_dir()
    if pkg_dir and os.path.isdir(pkg_dir) and pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)


def is_rembg_installed() -> bool:
    ensure_ai_packages_on_path()
    try:
        import rembg  # noqa: F401
        return True
    except ImportError:
        return False


def is_demucs_installed() -> bool:
    ensure_ai_packages_on_path()
    try:
        import demucs  # noqa: F401
        return True
    except ImportError:
        return False


def install_rembg(progress_cb=None) -> None:
    _pip_install("rembg[cli]", progress_cb)


def install_demucs(progress_cb=None) -> None:
    _pip_install("demucs", progress_cb)


def _pip_install(package: str, progress_cb=None) -> None:
    pkg_dir = _ai_packages_dir()

    if pkg_dir:
        # Frozen exe: install to local ai_packages/ folder next to exe.
        # Use the Python interpreter embedded by PyInstaller via -c bootstrap.
        os.makedirs(pkg_dir, exist_ok=True)
        cmd = [
            sys.executable, "-c",
            "import runpy, sys; sys.argv=['pip','install','--target',"
            f"r'{pkg_dir}','--upgrade','{package}']; runpy.run_module('pip',run_name='__main__')",
        ]
    else:
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", package]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    lines = []
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            lines.append(line)
            if progress_cb:
                progress_cb(line)
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(
            f"pip install {package} failed:\n" + "\n".join(lines[-20:])
        )

    # Make newly installed packages importable immediately.
    ensure_ai_packages_on_path()
