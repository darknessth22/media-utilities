"""Explain a GPU probe that never answered.

The AI tools check for a GPU by starting torch in the bundled Python (see
detect_device in core/vocal_isolator.py and core/upscaler.py). When that
process crashes instead of printing "cpu" or "cuda", its Windows exit code says
why, and showed up raw in the UI ("exit=3221225478"). This turns it into a
sentence people can act on.
"""
from __future__ import annotations

from core.i18n import tr

# Windows exit codes (as unsigned numbers) of a process that died loading torch.
_CRASHES = {
    0xC0000006: "gpu_probe_disk_error",  # STATUS_IN_PAGE_ERROR: a DLL couldn't be read from the drive
}


def problem_key(returncode: int | None, stdout: str | None) -> str | None:
    """Locale key for why the probe gave no answer, or None if it answered."""
    if (stdout or "").strip() in ("cpu", "cuda"):
        return None
    return _CRASHES.get((returncode or 0) & 0xFFFFFFFF, "gpu_probe_broken")


def problem(returncode: int | None, stdout: str | None) -> str | None:
    """The same, as text in the current language."""
    key = problem_key(returncode, stdout)
    return tr(key) if key else None
