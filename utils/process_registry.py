"""Global registry for tracking FFmpeg/yt-dlp subprocesses.

Guarantees that all tracked processes are killed when:
  - A job is explicitly cancelled via cancel_job()
  - The application exits (atexit handler)
"""
from __future__ import annotations

import atexit
import subprocess
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

_lock = threading.Lock()
# job_id -> list of Popen objects
_registry: dict[str, list[subprocess.Popen]] = {}


def register(job_id: str, proc: "subprocess.Popen") -> None:
    """Register *proc* under *job_id*."""
    with _lock:
        _registry.setdefault(job_id, []).append(proc)


def cancel_job(job_id: str) -> int:
    """Kill all processes for *job_id*. Returns number of processes killed."""
    with _lock:
        procs = _registry.pop(job_id, [])

    killed = 0
    for proc in procs:
        try:
            proc.kill()
            proc.wait(timeout=5)
            killed += 1
        except (ProcessLookupError, OSError):
            pass
    return killed


def unregister(job_id: str, proc: "subprocess.Popen") -> None:
    """Remove a finished *proc* from *job_id* to avoid accumulating dead handles."""
    with _lock:
        procs = _registry.get(job_id, [])
        try:
            procs.remove(proc)
        except ValueError:
            pass
        if not procs:
            _registry.pop(job_id, None)


def kill_all() -> int:
    """Kill every tracked process. Called at application exit."""
    with _lock:
        all_procs = [p for procs in _registry.values() for p in procs]
        _registry.clear()

    killed = 0
    for proc in all_procs:
        try:
            proc.kill()
            proc.wait(timeout=5)
            killed += 1
        except (ProcessLookupError, OSError):
            pass
    return killed


def tracked_run(
    cmd: list[str],
    job_id: str,
    **kwargs,
) -> subprocess.CompletedProcess:
    """subprocess.run wrapper that registers the process for lifecycle management.

    Passes all extra kwargs to Popen; returns CompletedProcess.
    Raises subprocess.CalledProcessError if check=True and returncode != 0.
    """
    check = kwargs.pop("check", False)
    timeout = kwargs.pop("timeout", None)

    # capture_output=True is a subprocess.run shorthand not understood by Popen
    if kwargs.pop("capture_output", False):
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE

    with subprocess.Popen(cmd, **kwargs) as proc:
        register(job_id, proc)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            raise
        except Exception:
            proc.kill()
            raise
        finally:
            unregister(job_id, proc)

    completed = subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    if check:
        completed.check_returncode()
    return completed


# Kill all processes at interpreter exit
atexit.register(kill_all)
