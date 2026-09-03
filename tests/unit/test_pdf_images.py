"""PDFs containing images must convert, in every output format.

Regression for "need item of full page image list": `get_image_bbox()` requires
an entry from `get_images(full=True)`, and two call sites passed the 9-tuple
from a bare `get_images()`. Every PDF with an image failed — in PDF->DOCX too,
which long predated the MD/PPTX work.
"""
from __future__ import annotations

import os

import pytest

fitz = pytest.importorskip("fitz")
Image = pytest.importorskip("PIL.Image")

from core.document import _image_bbox, convert_document  # noqa: E402


@pytest.fixture()
def png(tmp_path):
    def make(name="i.png", size=(300, 200), mode="RGB"):
        p = tmp_path / name
        Image.new(mode, size, 128 if mode == "L" else (200, 40, 40)).save(p)
        return str(p)
    return make


def _pdf(tmp_path, name, build):
    doc = fitz.open()
    build(doc)
    path = tmp_path / name
    doc.save(str(path))
    doc.close()
    return str(path)


def test_image_bbox_needs_full_list_and_helper_absorbs_it(tmp_path, png) -> None:
    """The bare 9-tuple raises; the helper must return a bbox or None, never raise."""
    path = _pdf(tmp_path, "a.pdf", lambda d: d.new_page().insert_image(
        fitz.Rect(40, 40, 340, 240), filename=png()))
    with fitz.open(path) as doc:
        page = doc[0]
        short = page.get_images()[0]
        full = page.get_images(full=True)[0]
        with pytest.raises(Exception):
            page.get_image_bbox(short)          # the original bug
        assert _image_bbox(page, full) is not None
        assert _image_bbox(page, short) is None  # absorbed, not raised


@pytest.mark.parametrize("fmt", ["pptx", "md", "docx"])
def test_pdf_with_image_converts(tmp_path, png, fmt) -> None:
    def build(doc):
        page = doc.new_page()
        page.insert_image(fitz.Rect(40, 40, 340, 240), filename=png())
        page.insert_text((40, 300), "caption text", fontsize=12)

    path = _pdf(tmp_path, "img.pdf", build)
    ok, out, summary = convert_document(path, fmt)
    assert ok, out
    assert summary.total_pages == 1


@pytest.mark.parametrize("fmt", ["pptx", "md", "docx"])
def test_full_page_image_converts(tmp_path, png, fmt) -> None:
    """A full-page image takes the scanned-page branch, which also indexed the
    short image list."""
    path = _pdf(tmp_path, "scan.pdf", lambda d: (
        lambda pg: pg.insert_image(pg.rect, filename=png(size=(1200, 1600))))(d.new_page()))
    ok, out, _ = convert_document(path, fmt)
    assert ok, out


@pytest.mark.parametrize("fmt", ["pptx", "md", "docx"])
def test_many_images_one_page(tmp_path, png, fmt) -> None:
    def build(doc):
        page = doc.new_page()
        for i in range(12):
            x, y = 20 + (i % 4) * 140, 20 + (i // 4) * 120
            page.insert_image(fitz.Rect(x, y, x + 130, y + 110),
                              filename=png(f"m{i}.png"))
        page.insert_text((20, 420), "grid", fontsize=12)

    path = _pdf(tmp_path, "grid.pdf", build)
    ok, out, _ = convert_document(path, fmt)
    assert ok, out


def test_images_are_placed_in_every_format(tmp_path, png) -> None:
    """Images used to be dropped for PPTX/MD; they are now placed in all three."""
    def build(doc):
        page = doc.new_page()
        page.insert_image(fitz.Rect(40, 40, 340, 240), filename=png())
        page.insert_text((40, 300), "caption", fontsize=12)

    path = _pdf(tmp_path, "s.pdf", build)
    for fmt in ("pptx", "md", "docx"):
        ok, _, summary = convert_document(path, fmt)
        assert ok
        assert summary.images == 1, f"{fmt} did not place the image"
        assert not summary.skipped_elements, f"{fmt} reported a skip: {summary.skipped_elements}"


# ── vector figures ────────────────────────────────────────────────────────

def _chart_pdf(tmp_path):
    """A bar chart drawn as vector primitives, like a report figure."""
    doc = fitz.open()
    page = doc.new_page()
    shape = page.new_shape()
    shape.draw_line(fitz.Point(60, 300), fitz.Point(500, 300))
    shape.finish(color=(0, 0, 0), width=1)
    shape.draw_line(fitz.Point(60, 80), fitz.Point(60, 300))
    shape.finish(color=(0, 0, 0), width=1)
    for i, h in enumerate([80, 140, 110, 190, 160, 90]):
        x = 80 + i * 70
        shape.draw_rect(fitz.Rect(x, 300 - h, x + 45, 300))
        shape.finish(color=(0.1, 0.3, 0.7), fill=(0.3, 0.55, 0.9))
    shape.commit()
    page.insert_text((60, 340), "Figure 1: quarterly revenue", fontsize=11)
    path = tmp_path / "chart.pdf"
    doc.save(str(path))
    doc.close()
    return str(path)


def test_chart_becomes_one_figure_not_many_primitives(tmp_path) -> None:
    """A chart is ~13 drawing primitives; emitting one shape each would give a
    pile of disconnected lines, so they are clustered and rasterised once."""
    from core.document import _extract_vector_figures
    path = _chart_pdf(tmp_path)
    with fitz.open(path) as doc:
        page = doc[0]
        assert len(page.get_drawings()) > 5, "expected many primitives"
        figures = _extract_vector_figures(page, 0)
    assert len(figures) == 1, f"expected one grouped figure, got {len(figures)}"
    assert figures[0].image_bytes, "figure was not rasterised"


def test_axis_lines_are_not_dropped_from_a_figure(tmp_path) -> None:
    """A rule has zero width or height; discarding such rects broke clustering
    because the axes are what join a chart's bars together."""
    from core.document import _cluster_rects, _FIGURE_GAP
    flat = [fitz.Rect(60, 300, 500, 300), fitz.Rect(60, 80, 60, 300)]
    clusters = _cluster_rects(flat, _FIGURE_GAP)
    assert clusters, "zero-area primitives must still cluster"


@pytest.mark.parametrize("fmt", ["pptx", "md", "docx"])
def test_chart_survives_conversion(tmp_path, fmt) -> None:
    path = _chart_pdf(tmp_path)
    ok, out, summary = convert_document(path, fmt)
    assert ok, out
    assert summary.images >= 1, "the figure should be placed, not dropped"


def test_figure_and_caption_share_a_slide(tmp_path) -> None:
    """A caption stranded on its own slide reads as a bug."""
    pptx = pytest.importorskip("pptx")
    path = _chart_pdf(tmp_path)
    ok, out, _ = convert_document(path, "pptx")
    assert ok
    prs = pptx.Presentation(out)
    assert len(prs.slides) == 1, "figure and caption should not split"
    slide = prs.slides[0]
    assert any(sh.shape_type == 13 for sh in slide.shapes), "no picture"
    text = " ".join(sh.text_frame.text for sh in slide.shapes
                    if sh.has_text_frame)
    assert "quarterly revenue" in text, "caption lost"


def test_markdown_writes_images_to_sibling_folder(tmp_path, png) -> None:
    def build(doc):
        page = doc.new_page()
        page.insert_image(fitz.Rect(40, 40, 340, 240), filename=png())
        page.insert_text((40, 300), "text", fontsize=12)

    path = _pdf(tmp_path, "m.pdf", build)
    ok, out, summary = convert_document(path, "md")
    assert ok
    body = open(out, encoding="utf-8").read()
    assert "![" in body, "no image link written"
    folder = out.replace(".md", "_images")
    assert os.path.isdir(folder) and os.listdir(folder)
    # Relative, forward-slashed link so the pair stays portable.
    assert "_images/img001" in body.replace("\\", "/")
    assert summary.images == 1


def test_page_sized_vector_art_is_not_treated_as_a_figure(tmp_path) -> None:
    """A full-page border or background would otherwise raster the whole page."""
    from core.document import _extract_vector_figures
    doc = fitz.open()
    page = doc.new_page()
    shape = page.new_shape()
    shape.draw_rect(page.rect + (2, 2, -2, -2))
    shape.finish(color=(0, 0, 0), width=1)
    shape.draw_rect(page.rect + (6, 6, -6, -6))
    shape.finish(color=(0, 0, 0), width=1)
    shape.commit()
    path = tmp_path / "border.pdf"
    doc.save(str(path))
    doc.close()
    with fitz.open(str(path)) as d2:
        figures = _extract_vector_figures(d2[0], 0)
    assert figures == [], "a page-sized frame is not a figure"
