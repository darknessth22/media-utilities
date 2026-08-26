"""Resumable pre-download of large wheels into pip's local wheel dir.

Why this exists
---------------
The CUDA PyTorch wheel is ~3.3 GB. Letting pip stream it in one pass is
fragile: pip keeps no partial file between runs, so a dropped connection or a
closed app throws away everything and the next attempt restarts from zero.
Users on slow or flaky links could never finish (observed: 30-60 kB/s with
intermittent DNS failures, so a 14-31 hour ETA that never completed).

This module downloads such wheels itself using HTTP range requests into a
``.part`` file. Progress survives connection drops, app restarts and reboots —
each attempt continues where the last stopped. Once complete the wheel is moved
into a local directory that pip is pointed at with ``--find-links``, so the pip
step installs from disk and never re-downloads.

The download host must support range requests; download.pytorch.org returns
``Accept-Ranges: bytes`` and answers ranged GETs with HTTP 206. When anything
here fails the caller is expected to fall back to plain pip, which still works
— this is an optimisation, never a hard requirement.
"""
from __future__ import annotations

import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_UA = "Videl-wheel-prefetch/1.0"

# Only wheels big enough to be worth the extra machinery. Everything smaller
# installs fine through pip's own retry handling.
_MIN_PREFETCH_BYTES = 200 * 1024 ** 2

_CHUNK = 1024 * 1024

# Give up on a single attempt after this many consecutive failures; the caller
# retries later and the .part file means nothing is lost.
_MAX_ATTEMPTS = 6


def _log(msg: str) -> None:
    """Emit a progress line. Mirrors pip's stdout so the UI picks it up."""
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def _fmt_mb(n: int) -> str:
    return f"{n / 1024 ** 2:.1f} MB"


def remote_size(url: str, timeout: int = 30) -> int | None:
    """Total size in bytes from a HEAD request, or None if unavailable."""
    try:
        req = Request(url, method="HEAD", headers={"User-Agent": _UA})
        with urlopen(req, timeout=timeout) as resp:
            if resp.headers.get("Accept-Ranges", "").lower() != "bytes":
                return None
            length = resp.headers.get("Content-Length")
            return int(length) if length else None
    except (HTTPError, URLError, OSError, ValueError):
        return None


def download_resumable(
    url: str,
    dest: str,
    total: int | None = None,
    progress_cb=None,
    timeout: int = 120,
) -> bool:
    """Download *url* to *dest*, resuming a previous partial attempt.

    Bytes accumulate in ``<dest>.part`` so an interrupted transfer continues
    instead of restarting. Returns True when *dest* holds the complete file.
    """
    if os.path.isfile(dest):
        if total is None or os.path.getsize(dest) == total:
            return True
        # Wrong size — a truncated leftover. Start it over.
        os.remove(dest)

    if total is None:
        total = remote_size(url, timeout=timeout)
        if total is None:
            return False  # no length or no range support; let pip handle it

    part = dest + ".part"
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        have = os.path.getsize(part) if os.path.isfile(part) else 0
        if have > total:  # stale/corrupt partial
            os.remove(part)
            have = 0
        if have == total:
            break

        headers = {"User-Agent": _UA}
        if have:
            headers["Range"] = f"bytes={have}-"
            _log(f"Resuming download at {_fmt_mb(have)} of {_fmt_mb(total)}")
        else:
            _log(f"Downloading {_fmt_mb(total)}")

        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=timeout) as resp:
                # A server that ignores Range replies 200 and restarts the body.
                if have and resp.status != 206:
                    have = 0
                    mode = "wb"
                else:
                    mode = "ab" if have else "wb"

                last_report = 0.0
                with open(part, mode) as fh:
                    while True:
                        chunk = resp.read(_CHUNK)
                        if not chunk:
                            break
                        fh.write(chunk)
                        have += len(chunk)
                        now = time.monotonic()
                        if progress_cb and now - last_report >= 1.0:
                            progress_cb(have, total)
                            last_report = now
        except (HTTPError, URLError, OSError) as exc:
            got = os.path.getsize(part) if os.path.isfile(part) else 0
            _log(
                f"Download interrupted at {_fmt_mb(got)} of {_fmt_mb(total)} "
                f"({type(exc).__name__}); attempt {attempt}/{_MAX_ATTEMPTS}"
            )
            if attempt == _MAX_ATTEMPTS:
                return False
            time.sleep(min(2 ** attempt, 30))
            continue

        if os.path.getsize(part) >= total:
            break

    if not os.path.isfile(part) or os.path.getsize(part) != total:
        return False

    os.replace(part, dest)
    _log(f"Download complete: {os.path.basename(dest)}")
    return True


_REQ_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([^\s#]+)")
_INDEX_RE = re.compile(r"^\s*--(?:extra-)?index-url\s+(\S+)")


def parse_manifest(manifest_path: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Return ([(name, version), ...], [index_url, ...]) from a pip manifest."""
    reqs: list[tuple[str, str]] = []
    indexes: list[str] = []
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            for line in fh:
                if line.lstrip().startswith("#"):
                    continue
                m_idx = _INDEX_RE.match(line)
                if m_idx:
                    indexes.append(m_idx.group(1).rstrip("/"))
                    continue
                m_req = _REQ_RE.match(line)
                if m_req:
                    reqs.append((m_req.group(1), m_req.group(2)))
    except OSError:
        return [], []
    return reqs, indexes


def wheel_filename(name: str, version: str) -> str:
    """PEP 427 wheel name for a CPython 3.12 Windows build of *name*."""
    # Local version separators are encoded in URLs ("+" -> "%2B") but the file
    # on disk keeps the literal "+".
    return f"{name}-{version}-cp312-cp312-win_amd64.whl"


def wheel_url(index: str, name: str, version: str) -> str:
    quoted = version.replace("+", "%2B")
    return f"{index}/{wheel_filename(name, quoted).replace('+', '%2B')}"


def prefetch_manifest(manifest_path: str, wheel_dir: str,
                      min_bytes: int = _MIN_PREFETCH_BYTES) -> list[str]:
    """Pre-download the large wheels named in *manifest_path*.

    Returns the wheel filenames now sitting complete in *wheel_dir*. Anything
    that cannot be resolved or downloaded is simply skipped — pip will fetch it
    normally.
    """
    reqs, indexes = parse_manifest(manifest_path)
    if not reqs or not indexes:
        return []

    os.makedirs(wheel_dir, exist_ok=True)
    done: list[str] = []

    for name, version in reqs:
        fname = wheel_filename(name, version)
        dest = os.path.join(wheel_dir, fname)

        if os.path.isfile(dest):
            done.append(fname)
            continue

        for index in indexes:
            url = wheel_url(index, name, version)
            total = remote_size(url)
            if total is None:
                continue  # not on this index, or no range support
            if total < min_bytes:
                break  # small enough that pip handles it fine
            _log(f"[prefetch] {name} {version} — {_fmt_mb(total)}")

            def _progress(have: int, tot: int, _n=name) -> None:
                pct = have * 100 // tot if tot else 0
                _log(f"[prefetch] {_n} {pct}% ({_fmt_mb(have)}/{_fmt_mb(tot)})")

            if download_resumable(url, dest, total=total, progress_cb=_progress):
                done.append(fname)
            break

    return done
