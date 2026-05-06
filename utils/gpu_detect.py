"""Best-effort NVIDIA GPU detection — returns 'cuda' or 'cpu'."""
from __future__ import annotations

import subprocess
import sys
from typing import Literal, Optional

_CACHED: Optional[str] = None
_CACHED_CAP: Optional[tuple[int, int]] = None
_CAP_PROBED: bool = False

# cu128 wheels ship kernels for sm_70+. Pascal (sm_60/61) and Maxwell
# (sm_50/52) hit "no kernel image" at runtime if forced onto cu128.
MIN_CUDA_CAPABILITY: tuple[int, int] = (7, 0)


def _run(cmd: list[str]) -> tuple[int, str]:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=flags,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return 1, ""


def _probe() -> Literal["cuda", "cpu"]:
    code, _ = _run(["nvidia-smi", "-L"])
    if code == 0:
        return "cuda"
    if sys.platform == "win32":
        code, out = _run(["wmic", "path", "win32_VideoController", "get", "name"])
        if code == 0 and "nvidia" in out.lower():
            return "cuda"
    return "cpu"


def _probe_capability() -> Optional[tuple[int, int]]:
    code, out = _run([
        "nvidia-smi",
        "--query-gpu=compute_cap",
        "--format=csv,noheader",
    ])
    if code != 0 or not out.strip():
        return None
    # Take the highest cap if multi-GPU; pick first valid line.
    best: Optional[tuple[int, int]] = None
    for line in out.splitlines():
        line = line.strip()
        if not line or "." not in line:
            continue
        try:
            major_s, minor_s = line.split(".", 1)
            cap = (int(major_s), int(minor_s))
        except ValueError:
            continue
        if best is None or cap > best:
            best = cap
    return best


def detect() -> Literal["cuda", "cpu"]:
    global _CACHED
    if _CACHED is None:
        _CACHED = _probe()
    return _CACHED  # type: ignore[return-value]


def compute_capability() -> Optional[tuple[int, int]]:
    """Return highest detected NVIDIA compute capability, or None if no GPU /
    nvidia-smi unavailable."""
    global _CACHED_CAP, _CAP_PROBED
    if not _CAP_PROBED:
        _CACHED_CAP = _probe_capability()
        _CAP_PROBED = True
    return _CACHED_CAP


def cuda_variant_supported() -> bool:
    """Whether the bundled cu128 torch build will run on the detected GPU.
    True if NVIDIA GPU present and compute capability >= 7.0 (Volta+).
    Conservative: when capability cannot be probed but a GPU is detected,
    assume supported — let runtime fall back if it isn't."""
    if detect() != "cuda":
        return False
    cap = compute_capability()
    if cap is None:
        return True
    return cap >= MIN_CUDA_CAPABILITY
