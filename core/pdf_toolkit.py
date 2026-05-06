"""PDF Toolkit: compress, merge, split, and image extraction using PyMuPDF."""
from __future__ import annotations

import os
import io
from typing import Callable


def _log(msg: str) -> None:
    print(f"[PDFToolkit] {msg}", flush=True)


# ── Compress ──────────────────────────────────────────────────────────────────

def compress_pdf(
    input_path: str,
    output_path: str,
    image_dpi: int = 150,
    progress_cb: Callable[[int, int], None] | None = None,
) -> tuple[bool, str]:
    """Re-save a PDF with downsampled images to reduce file size.

    Returns (success, output_path_or_error_message).
    image_dpi controls the resolution images are resampled to (72/150/300).
    """
    try:
        import fitz

        doc = fitz.open(input_path)
        total = len(doc)
        out_doc = fitz.open()

        for page_num, page in enumerate(doc):
            if progress_cb:
                progress_cb(page_num + 1, total)

            # Render page to pixmap at target DPI then re-insert as image page
            mat = fitz.Matrix(image_dpi / 72, image_dpi / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, pixmap=pix)

        out_doc.save(output_path, garbage=4, deflate=True, clean=True)
        out_doc.close()
        doc.close()

        orig_size = os.path.getsize(input_path)
        new_size = os.path.getsize(output_path)
        _log(f"Compressed: {orig_size // 1024} KB → {new_size // 1024} KB")
        return True, output_path
    except Exception as e:
        _log(f"compress_pdf failed: {e}")
        return False, str(e)


# ── Merge ─────────────────────────────────────────────────────────────────────

def merge_pdfs(
    input_paths: list[str],
    output_path: str,
    progress_cb: Callable[[int, int], None] | None = None,
) -> tuple[bool, str]:
    """Merge multiple PDF files into one.

    Returns (success, output_path_or_error_message).
    """
    if not input_paths:
        return False, "No input files provided."
    try:
        import fitz

        merged = fitz.open()
        total = len(input_paths)
        for i, path in enumerate(input_paths):
            if progress_cb:
                progress_cb(i + 1, total)
            src = fitz.open(path)
            merged.insert_pdf(src)
            src.close()

        merged.save(output_path, garbage=4, deflate=True)
        merged.close()
        _log(f"Merged {total} files → {output_path}")
        return True, output_path
    except Exception as e:
        _log(f"merge_pdfs failed: {e}")
        return False, str(e)


# ── Split ─────────────────────────────────────────────────────────────────────

def split_pdf(
    input_path: str,
    output_dir: str,
    page_ranges: list[tuple[int, int]] | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
) -> tuple[bool, list[str], str]:
    """Split a PDF into individual pages (or custom ranges).

    page_ranges: list of (start, end) 1-based inclusive ranges.
    If None, splits every page into its own file.

    Returns (success, list_of_output_paths, error_message).
    """
    try:
        import fitz

        doc = fitz.open(input_path)
        total_pages = len(doc)
        base_name = os.path.splitext(os.path.basename(input_path))[0]

        if page_ranges is None:
            ranges = [(i + 1, i + 1) for i in range(total_pages)]
        else:
            ranges = page_ranges

        output_paths: list[str] = []
        total = len(ranges)

        for idx, (start, end) in enumerate(ranges):
            if progress_cb:
                progress_cb(idx + 1, total)

            start = max(1, min(start, total_pages))
            end = max(start, min(end, total_pages))

            out_doc = fitz.open()
            # insert_pdf uses 0-based pno
            out_doc.insert_pdf(doc, from_page=start - 1, to_page=end - 1)

            if start == end:
                out_name = f"{base_name}_page{start:04d}.pdf"
            else:
                out_name = f"{base_name}_pages{start}-{end}.pdf"

            out_path = os.path.join(output_dir, out_name)
            out_doc.save(out_path, garbage=4, deflate=True)
            out_doc.close()
            output_paths.append(out_path)

        doc.close()
        _log(f"Split into {len(output_paths)} files")
        return True, output_paths, ""
    except Exception as e:
        _log(f"split_pdf failed: {e}")
        return False, [], str(e)


# ── Image Extraction ──────────────────────────────────────────────────────────

def extract_images_from_pdf(
    input_path: str,
    output_dir: str,
    export_pages_as_jpeg: bool = False,
    jpeg_dpi: int = 150,
    progress_cb: Callable[[int, int], None] | None = None,
) -> tuple[bool, list[str], str]:
    """Extract embedded images from a PDF, or export each page as a JPEG.

    export_pages_as_jpeg=True renders every page at jpeg_dpi; otherwise
    embedded image xrefs are extracted directly (higher quality for photo PDFs).

    Returns (success, list_of_output_paths, error_message).
    """
    try:
        import fitz
        from PIL import Image

        doc = fitz.open(input_path)
        total_pages = len(doc)
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_paths: list[str] = []

        if export_pages_as_jpeg:
            for page_num, page in enumerate(doc):
                if progress_cb:
                    progress_cb(page_num + 1, total_pages)
                mat = fitz.Matrix(jpeg_dpi / 72, jpeg_dpi / 72)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                out_path = os.path.join(output_dir, f"{base_name}_page{page_num + 1:04d}.jpg")
                pix.save(out_path)
                output_paths.append(out_path)
        else:
            seen_xrefs: set[int] = set()
            img_index = 0
            for page_num, page in enumerate(doc):
                if progress_cb:
                    progress_cb(page_num + 1, total_pages)
                for img in page.get_images(full=True):
                    xref = img[0]
                    if xref in seen_xrefs:
                        continue
                    seen_xrefs.add(xref)
                    try:
                        pix = fitz.Pixmap(doc, xref)
                        if pix.width < 16 or pix.height < 16:
                            continue
                        if pix.n - pix.alpha >= 4:
                            pil_img = Image.frombytes("CMYK", (pix.width, pix.height), pix.samples)
                            pil_img = pil_img.convert("RGB")
                            buf = io.BytesIO()
                            pil_img.save(buf, format="JPEG", quality=92)
                            img_bytes = buf.getvalue()
                        else:
                            rgb_pix = fitz.Pixmap(fitz.csRGB, pix) if pix.alpha else pix
                            buf = io.BytesIO(rgb_pix.tobytes("jpeg"))
                            img_bytes = buf.getvalue()
                        img_index += 1
                        out_path = os.path.join(
                            output_dir, f"{base_name}_img{img_index:04d}_p{page_num + 1}.jpg"
                        )
                        with open(out_path, "wb") as fh:
                            fh.write(img_bytes)
                        output_paths.append(out_path)
                    except Exception as e:
                        _log(f"  Image xref {xref} failed: {e}")

        doc.close()
        _log(f"Extracted {len(output_paths)} images")
        return True, output_paths, ""
    except Exception as e:
        _log(f"extract_images_from_pdf failed: {e}")
        return False, [], str(e)


def get_pdf_page_count(path: str) -> int:
    """Return page count of a PDF, or -1 on error."""
    try:
        import fitz
        with fitz.open(path) as doc:
            return len(doc)
    except Exception:
        return -1
