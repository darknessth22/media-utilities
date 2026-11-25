"""PDF work runs in the videl-pdf helper; Videl itself never loads PyMuPDF (AGPL)."""
import os
import subprocess
import sys

import pytest

fitz = pytest.importorskip("fitz")

from core import pdf_bridge  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _pdf(path, pages, text="page"):
    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"{text} {i + 1}")
    doc.save(path)
    doc.close()
    return path


def test_app_never_imports_pymupdf():
    code = (
        "import sys, gui.app, core.ocr, core.pdf_bridge; "
        "print(sorted(m for m in sys.modules if m == 'fitz' or m.startswith('pymupdf')))"
    )
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == "[]"


def test_merge_through_helper(tmp_path):
    a = _pdf(str(tmp_path / "a.pdf"), 2)
    b = _pdf(str(tmp_path / "b.pdf"), 3)
    out = str(tmp_path / "merged.pdf")
    ok, result = pdf_bridge.merge_pdfs([a, b], out)
    assert ok, result
    with fitz.open(out) as doc:
        assert len(doc) == 5


def test_split_keeps_return_shape(tmp_path):
    src = _pdf(str(tmp_path / "s.pdf"), 3)
    ok, paths, err = pdf_bridge.split_pdf(src, str(tmp_path), [(1, 2), [3, 3]])
    assert ok and err == "" and len(paths) == 2


def test_failure_comes_back_as_original_shape(tmp_path):
    ok, paths, err = pdf_bridge.split_pdf(str(tmp_path / "missing.pdf"), str(tmp_path))
    assert not ok and paths == [] and err


def test_convert_document_through_helper(tmp_path):
    src = _pdf(str(tmp_path / "doc.pdf"), 1, text="hello bridge")
    ok, out, summary = pdf_bridge.convert_document(src, "md")
    assert ok, out
    assert "hello bridge" in open(out, encoding="utf-8").read()
    assert summary is None or isinstance(summary, dict)


def test_searchable_pdf_round_trip(tmp_path):
    src = _pdf(str(tmp_path / "scan.pdf"), 1)
    pages = pdf_bridge.call("render_pages_png", src, str(tmp_path), 72)
    assert len(pages) == 1 and os.path.isfile(pages[0]["png"])
    pages[0]["boxes"] = [[[[10, 10], [200, 10], [200, 40], [10, 40]], "findme"]]
    out = str(tmp_path / "searchable.pdf")
    pdf_bridge.call("write_searchable_pdf", pages, out)
    with fitz.open(out) as doc:
        assert "findme" in doc[0].get_text()
