"""videl-pdf: Videl's PDF helper program.

Every PyMuPDF (fitz) call in Videl runs here, in a separate process, never
inside Videl itself. PyMuPDF is AGPL-3.0; keeping it in its own program keeps
that licence to this helper, whose complete source is public in this repo:
this file, core/document.py and core/pdf_toolkit.py. The built videl-pdf
program is distributed under AGPL-3.0.

Protocol: Videl writes one JSON request to stdin,
    {"call": "<name>", "args": [...], "kwargs": {...}}
and reads one JSON reply from stdout,
    {"ok": true, "result": ...}  or  {"ok": false, "error": "..."}.
Anything the PDF code prints goes to stderr, so stdout stays clean.
"""
from __future__ import annotations

import contextlib
import dataclasses
import json
import sys

# Static imports so PyInstaller bundles them into the helper.
from core import document, pdf_toolkit

CALLS = {
    "convert_document": document.convert_document,
    "compress_pdf": pdf_toolkit.compress_pdf,
    "merge_pdfs": pdf_toolkit.merge_pdfs,
    "split_pdf": pdf_toolkit.split_pdf,
    "extract_images_from_pdf": pdf_toolkit.extract_images_from_pdf,
    "render_pages_png": pdf_toolkit.render_pages_png,
    "write_searchable_pdf": pdf_toolkit.write_searchable_pdf,
}


def _jsonable(value):
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def main() -> int:
    reply_to = sys.stdout
    try:
        request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        func = CALLS[request["call"]]
        with contextlib.redirect_stdout(sys.stderr):
            result = func(*request.get("args", []), **request.get("kwargs", {}))
        reply = {"ok": True, "result": _jsonable(result)}
    except Exception as e:  # noqa: BLE001 — every failure goes back as a reply
        reply = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    reply_to.write(json.dumps(reply))
    reply_to.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
