"""Markdown export from DocumentBlocks — structure must survive rendering.

Asserts against rendered HTML rather than the raw text: the two real bugs found
while building this (a table absorbed into the preceding list item, and a
numbered list merging into a bulleted one) both looked fine in the raw markdown
and only showed up once rendered.
"""
from __future__ import annotations

import pytest

from core.document import DocumentBlock, SpanInfo, _build_md_from_blocks

# Smallest valid 1x1 PNG — the writer only stores the bytes, but keeping them
# real means the same fixture works if a reader is ever added.
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c63000100000500010d0a2db40000"
    "000049454e44ae426082")


def _blocks() -> list[DocumentBlock]:
    return [
        DocumentBlock("heading", text="Title", level=1,
                      spans=[SpanInfo("Title", True, False, 24.0, "", (0, 0, 0))]),
        DocumentBlock("paragraph", text="a b",
                      spans=[SpanInfo("plain ", False, False, 11.0, "", (0, 0, 0)),
                             SpanInfo("bold", True, False, 11.0, "", (0, 0, 0)),
                             SpanInfo(" and ", False, False, 11.0, "", (0, 0, 0)),
                             SpanInfo("it", False, True, 11.0, "", (0, 0, 0))]),
        DocumentBlock("list_item", text="• first", level=1, list_style="bullet"),
        DocumentBlock("list_item", text="• second", level=1, list_style="bullet"),
        DocumentBlock("list_item", text="1. one", level=1, list_style="number"),
        DocumentBlock("table", table_data=[["A", "B|pipe"], ["1", "2"]]),
        DocumentBlock("image", image_bytes=_PNG_BYTES, image_ext="png", page_num=0),
    ]


def _write(tmp_path) -> tuple[str, object]:
    out = tmp_path / "out.md"
    summary = _build_md_from_blocks(_blocks(), str(out))
    return out.read_text(encoding="utf-8"), summary


def test_markdown_renders_expected_structure(tmp_path) -> None:
    markdown = pytest.importorskip("markdown")
    text, _ = _write(tmp_path)
    html = markdown.markdown(text, extensions=["tables"])

    assert html.count("<h1>") == 1
    # A blank line alone will not split adjacent lists; without the <!-- -->
    # separator the numbered item is swallowed into the <ul>.
    assert html.count("<ul>") == 1, html
    assert html.count("<ol>") == 1, html
    # Without a blank line the table becomes part of the last list item.
    assert html.count("<table>") == 1, html
    assert "<strong>bold</strong>" in html
    assert "<em>it</em>" in html


def test_source_markers_and_escaping(tmp_path) -> None:
    text, _ = _write(tmp_path)
    # The source's own bullet/number must not survive next to ours.
    assert "- •" not in text
    assert "1. 1." not in text
    # A heading is already emphasised; no ** inside it.
    assert text.splitlines()[0] == "# Title"
    # A pipe inside a cell would otherwise break the column count.
    assert r"C\|pipe" in text or r"B\|pipe" in text


def test_images_are_written_to_a_sibling_folder(tmp_path) -> None:
    """Markdown cannot embed bytes, so pictures are written beside the .md and
    linked relatively."""
    text, summary = _write(tmp_path)
    assert "![" in text, "no image link written"
    folders = list(tmp_path.glob("*_images"))
    assert folders and list(folders[0].iterdir()), "image file not written"
    assert "_images/img001" in text.replace("\\", "/")
    assert summary.images == 1


def test_scanned_page_warns(tmp_path) -> None:
    out = tmp_path / "s.md"
    summary = _build_md_from_blocks(
        [DocumentBlock("scanned_page", image_bytes=b"x", page_num=2)], str(out))
    assert summary.scanned_pages == 1
    assert summary.warnings, "a scanned page has no text and must say so"
