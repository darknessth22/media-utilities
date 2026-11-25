"""Run PDF work in the videl-pdf helper program (pdf_helper.py).

Videl itself must never import fitz (PyMuPDF): it is AGPL, and loading it in
the same program as Videl's private code would extend that licence to it.
GUI code calls the functions below, which have the same signatures and return
shapes as core.document / core.pdf_toolkit but run in a separate process.
Progress callbacks and cancel events are not forwarded; no caller uses them.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

_CREATE_NO_WINDOW = 0x08000000


def _helper_cmd() -> list[str]:
    if getattr(sys, "frozen", False):
        exe = "videl-pdf.exe" if sys.platform == "win32" else "videl-pdf"
        return [os.path.join(os.path.dirname(sys.executable), exe)]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [sys.executable, os.path.join(root, "pdf_helper.py")]


def call(name: str, *args, **kwargs):
    """Run one helper call and return its result. Raises RuntimeError on failure."""
    for unused in ("progress_cb", "progress_callback", "cancel_event"):
        kwargs.pop(unused, None)
    request = json.dumps({"call": name, "args": list(args), "kwargs": kwargs})
    proc = subprocess.run(
        _helper_cmd(),
        input=request.encode("utf-8"),
        capture_output=True,
        creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        reply = json.loads(proc.stdout.decode("utf-8"))
    except ValueError:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-5:]
        raise RuntimeError(
            f"PDF helper failed (exit {proc.returncode}): " + " | ".join(tail)
        ) from None
    if not reply.get("ok"):
        raise RuntimeError(reply.get("error", "PDF helper failed"))
    return reply["result"]


def _forward(name: str, on_error):
    def run(*args, **kwargs):
        try:
            return tuple(call(name, *args, **kwargs))
        except Exception as e:  # noqa: BLE001 — same contract as the originals
            return on_error(str(e))
    run.__name__ = name
    return run


# Same return shapes as the functions they stand in for.
convert_document = _forward("convert_document", lambda e: (False, e, None))
compress_pdf = _forward("compress_pdf", lambda e: (False, e))
merge_pdfs = _forward("merge_pdfs", lambda e: (False, e))
split_pdf = _forward("split_pdf", lambda e: (False, [], e))
extract_images_from_pdf = _forward("extract_images_from_pdf", lambda e: (False, [], e))
