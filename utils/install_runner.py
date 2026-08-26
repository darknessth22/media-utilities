"""Entry point for the on-demand component install subprocess.

Runs two steps in one child process so the GUI keeps a single QProcess to
watch:

  1. Pre-download any large wheels from the manifest with resume support
     (`utils.wheel_prefetch`). Interrupted transfers continue on the next
     attempt instead of restarting, which is what makes the ~3.3 GB CUDA torch
     wheel reachable on slow or unreliable connections.
  2. Hand off to ``pip install``, pointed at the pre-downloaded wheels so it
     installs them from disk rather than fetching them again.

Step 1 is best-effort: if the host does not support range requests, a URL
cannot be resolved, or the download keeps failing, this still falls through to
a normal pip run. pip remains the thing that actually resolves and installs.

Invoked as::

    python -m utils.install_runner --manifest <path> --target <dir>
                                   --wheel-dir <dir> [--pip-arg ...]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--wheel-dir", required=True)
    parser.add_argument("--timeout", default="120")
    parser.add_argument("--retries", default="20")
    # Extra flags forwarded verbatim to pip (e.g. --no-deps) come after a bare
    # "--"; argparse would otherwise treat such a value as one of its options.
    argv = list(sys.argv[1:] if argv is None else argv)
    passthrough: list[str] = []
    if "--" in argv:
        split = argv.index("--")
        argv, passthrough = argv[:split], argv[split + 1:]
    args = parser.parse_args(argv)
    args.pip_arg = passthrough

    # The runner ships inside the app, but the child interpreter is the bundled
    # runtime, which does not have the app on sys.path by default.
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if here not in sys.path:
        sys.path.insert(0, here)

    try:
        from utils.wheel_prefetch import prefetch_manifest
        prefetched = prefetch_manifest(args.manifest, args.wheel_dir)
        if prefetched:
            print(f"[prefetch] ready: {', '.join(prefetched)}", flush=True)
    except Exception as exc:  # noqa: BLE001 - never block the install
        print(f"[prefetch] skipped ({type(exc).__name__}: {exc})", flush=True)

    pip_cmd = [
        sys.executable, "-u", "-m", "pip", "install",
        "--no-warn-script-location",
        "--disable-pip-version-check",
        "--progress-bar", "on",
        "--timeout", args.timeout,
        "--retries", args.retries,
        # Look in the prefetch dir first so completed wheels are used as-is.
        "--find-links", args.wheel_dir,
        "--target", args.target,
        *args.pip_arg,
        "-r", args.manifest,
    ]
    return subprocess.call(pip_cmd)


if __name__ == "__main__":
    sys.exit(main())
