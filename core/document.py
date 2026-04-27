"""Document conversion engine: PDF, DOCX, and image → PDF."""
import contextlib
import io
import os
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from io import BytesIO

import fitz  # PyMuPDF
from docx import Document
from docx.shared import Inches, Pt
from PIL import Image



@dataclass
class SpanInfo:
    """Formatting metadata for a text span within a DocumentBlock."""
    text: str
    bold: bool
    italic: bool
    font_size: float
    font_name: str
    color: tuple[int, int, int]  # RGB color tuple (0-255 each)


@dataclass
class DocumentBlock:
    """A structural unit extracted from a PDF page during conversion."""
    block_type: str  # heading, paragraph, list_item, table, image, scanned_page
    text: str | None = None
    spans: list[SpanInfo] = field(default_factory=list)
    level: int | None = None  # Heading level (1-4) or list nesting depth
    list_style: str | None = None  # bullet or number
    table_data: list[list[str]] | None = None
    image_bytes: bytes | None = None
    image_ext: str | None = None
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)
    page_num: int = 0


@dataclass
class ConversionSummary:
    """A record of elements processed during a document conversion operation."""
    total_pages: int = 0
    text_blocks: int = 0
    headings: int = 0
    tables: int = 0
    images: int = 0
    list_items: int = 0
    scanned_pages: int = 0
    skipped_elements: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"})
_VALID_DOCS  = frozenset({".pdf", ".docx"})
_VALID_OUTPUTS = frozenset({"pdf", "docx"})


def _is_scanned_page(page) -> bool:
    """Detect image-only pages: little text and large images."""
    text_len = len(page.get_text().strip())
    if text_len > 200:
        return False
        
    page_area = page.rect.width * page.rect.height
    image_area = 0
    for img in page.get_images():
        bbox = page.get_image_bbox(img)
        image_area += (bbox.x1 - bbox.x0) * (bbox.y1 - bbox.y0)
        
    return image_area > 0.8 * page_area


def _extract_page_blocks(page, page_num: int, body_font_size: float, doc, extracted_images: set, warnings: list = None) -> list[DocumentBlock]:
    """Extract structured blocks (text, tables, images) from a PDF page."""
    blocks = []
    import re
    
    # Handle scanned page detection (T016)
    if _is_scanned_page(page):
        images = page.get_images()
        if images:
            largest_img = max(images, key=lambda x: page.get_image_bbox(x).get_area())
            xref = largest_img[0]
            img_data = _safe_pixmap_png(doc, xref)
            if img_data:
                blocks.append(DocumentBlock(
                    block_type="scanned_page",
                    image_bytes=img_data,
                    image_ext="png",
                    bbox=tuple(page.rect),
                    page_num=page_num
                ))
                extracted_images.add(xref)
                return blocks

    table_bboxes = []
    try:
        tables = page.find_tables()
        for tab in tables.tables:
            try:
                bbox = tuple(tab.bbox)
                rows = tab.extract()
                if rows:
                    blocks.append(DocumentBlock(
                        block_type="table",
                        table_data=rows,
                        bbox=bbox,
                        page_num=page_num
                    ))
                    table_bboxes.append(bbox)
            except Exception as e:
                _log(f"Table extraction failed on page {page_num+1}: {e}")
                if warnings is not None:
                    warnings.append(f"Table extraction failed on page {page_num+1} (falling back to text)")
    except Exception as e:
        _log(f"find_tables failed on page {page_num+1}: {e}")
        if warnings is not None:
            warnings.append(f"Table detection failed on page {page_num+1} (falling back to text)")

    # Image extraction pass (T016 requirement: catch all images, not just text-flow)
    for img in page.get_images(full=True):
        xref = img[0]
        if xref in extracted_images:
            continue
            
        bbox = page.get_image_bbox(img)
        # Skip very small images (likely icons or decorative elements)
        if bbox.width < 10 or bbox.height < 10:
            continue
            
        img_data = _safe_pixmap_png(doc, xref)
        if img_data:
            blocks.append(DocumentBlock(
                block_type="image",
                image_bytes=img_data,
                image_ext="png",
                bbox=tuple(bbox),
                page_num=page_num
            ))
            extracted_images.add(xref)

    # Text extraction with formatting (T014)
    text_dict = page.get_text("dict", flags=7)
    for b in text_dict.get("blocks", []):
        if "lines" not in b:
            continue
            
        block_rect = fitz.Rect(b["bbox"])
        if any(block_rect.intersects(fitz.Rect(tbb)) for tbb in table_bboxes):
            continue
            
        block_text = ""
        spans = []
        max_size = 0
        is_bold = False
        
        # Collect text and spans first
        for line in b["lines"]:
            for s in line.get("spans", []):
                span_text = s["text"]
                if not span_text: # Keep empty spans but check text
                    continue
                
                # Decompose sRGB color
                color_int = s["color"]
                rgb = ((color_int >> 16) & 0xFF, (color_int >> 8) & 0xFF, color_int & 0xFF)
                
                bold = bool(s["flags"] & 16)
                italic = bool(s["flags"] & 1)
                
                font_name = s.get("font", "").lower()
                if not bold and ("bold" in font_name or "black" in font_name):
                    bold = True
                if not italic and ("italic" in font_name or "oblique" in font_name):
                    italic = True
                
                if s["size"] > max_size:
                    max_size = s["size"]
                    is_bold = bold
                
                spans.append(SpanInfo(
                    text=span_text,
                    bold=bold,
                    italic=italic,
                    font_size=round(s["size"], 1),
                    font_name=s.get("font", "Helvetica"),
                    color=rgb
                ))
                block_text += span_text

        if not block_text.strip():
            continue
            
        block_type = "paragraph"
        level = None
        list_style = None
        
        if max_size > 1.5 * body_font_size:
            block_type = "heading"
            level = 1
        elif max_size > 1.2 * body_font_size:
            block_type = "heading"
            level = 2
        elif is_bold and max_size > 1.05 * body_font_size:
            block_type = "heading"
            level = 3
            
        if block_type == "paragraph" and spans:
            is_list, style = _detect_list_item(block_text, b["lines"][0]["spans"][0])
            if is_list:
                block_type = "list_item"
                list_style = style
                level = 1
                
                # Strip leading marker to avoid double bullets (Critical #1)
                marker_regex = r"^(\d+|[a-zA-Z]|[ivxIVX]+)[.)]\s+|^\W\s+"
                cleaned_text = re.sub(marker_regex, "", block_text, count=1)
                if cleaned_text != block_text:
                    # Update first span text to remove the marker
                    marker_len = len(block_text) - len(cleaned_text)
                    if spans and len(spans[0].text) >= marker_len:
                        spans[0].text = spans[0].text[marker_len:].lstrip()
                    block_text = cleaned_text

        blocks.append(DocumentBlock(
            block_type=block_type,
            text=block_text.strip(),
            spans=spans,
            level=level,
            list_style=list_style,
            bbox=tuple(b["bbox"]),
            page_num=page_num
        ))
        
    return sorted(blocks, key=lambda x: (x.bbox[1], x.bbox[0]))


def _log(msg: str) -> None:
    print(f"[DocConvert] {msg}", flush=True)


def _detect_body_font_size(doc) -> float:
    """Statistical analysis of font sizes across document to find the body text baseline."""
    size_counts = {}
    for page in doc:
        blocks = page.get_text("dict").get("blocks", [])
        for b in blocks:
            if "lines" not in b:
                continue
            for l in b["lines"]:
                for s in l["spans"]:
                    size = round(s["size"], 1)
                    size_counts[size] = size_counts.get(size, 0) + len(s["text"])
    
    if not size_counts:
        return 12.0
        
    # Return the most frequent font size by character count
    return max(size_counts, key=size_counts.get)


def _detect_list_item(block_text: str, first_span: dict) -> tuple[bool, str | None]:
    """Heuristic list detection using block text and font metadata."""
    import re
    text = block_text.strip()
    if not text:
        return False, None
        
    # Check for bullet symbols in font name or specific unicode characters
    font_name = first_span.get("font", "").lower()
    is_bullet_font = any(x in font_name for x in ["symbol", "zapfdingbats", "wingdings"])
    
    # Common bullet characters
    bullets = ["\u2022", "\u25E6", "\uf0b7", "\u2219", "\u2023", "\u2043"]
    if is_bullet_font or text[0] in bullets:
        return True, "bullet"
        
    # Numbered list pattern: 1. or 1) or (1)
    if re.match(r"^(\d+|[a-zA-Z]|[ivxIVX]+)[.)]\s", text) or re.match(r"^\(\d+\)\s", text):
        return True, "number"
        
    return False, None


@contextlib.contextmanager
def _temp_png(data: bytes):
    """Write *data* to a uniquely-named temp PNG, yield its path, then delete it."""
    fd, path = tempfile.mkstemp(suffix=".png")
    try:
        os.write(fd, data)
        os.close(fd)
        yield path
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _safe_pixmap_png(doc, xref: int) -> bytes | None:
    """Extract an image by xref and return PNG bytes, or None on failure.

    Handles CMYK and other colour spaces that fitz cannot encode directly as PNG
    by converting through Pillow instead.
    """
    try:
        pix = fitz.Pixmap(doc, xref)
        if pix.n - pix.alpha >= 4:
            # CMYK or other non-RGB/RGBA → convert to RGB via Pillow
            pil_img = Image.frombytes("CMYK", (pix.width, pix.height), pix.samples)
            pil_img = pil_img.convert("RGB")
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            return buf.getvalue()
        return pix.tobytes("png")
    except Exception as e:
        _log(f"  Pixmap extraction failed for xref {xref}: {e}")
        return None


def _build_docx_from_blocks(blocks: list[DocumentBlock], output_path: str) -> ConversionSummary:
    """Assemble a python-docx Document from extracted DocumentBlocks."""
    doc = Document()
    summary = ConversionSummary()
    
    current_page = 0
    for block in blocks:
        # Add page breaks if needed (handle skipped empty pages - Low #10)
        while block.page_num > current_page:
            doc.add_page_break()
            current_page += 1
            
        if block.block_type == "heading":
            level = min(block.level or 1, 9)
            doc.add_heading(block.text, level=level)
            summary.headings += 1
            
        elif block.block_type == "table":
            if not block.table_data:
                continue
            rows = len(block.table_data)
            cols = len(block.table_data[0]) if rows > 0 else 0
            if rows > 0 and cols > 0:
                table = doc.add_table(rows=rows, cols=cols)
                table.style = 'Table Grid'
                for r_idx, row_data in enumerate(block.table_data):
                    for c_idx, cell_text in enumerate(row_data):
                        if c_idx < cols:
                            table.cell(r_idx, c_idx).text = str(cell_text or "")
                summary.tables += 1
                
        elif block.block_type == "image" or block.block_type == "scanned_page":
            if block.image_bytes:
                try:
                    img_stream = BytesIO(block.image_bytes)
                    # For scanned pages, we might want to make it full width
                    width = Inches(6.5) if block.block_type == "scanned_page" else None
                    doc.add_picture(img_stream, width=width)
                    if block.block_type == "scanned_page":
                        summary.scanned_pages += 1
                    else:
                        summary.images += 1
                except Exception as e:
                    _log(f"Error adding image to docx: {e}")
                    summary.skipped_elements.append(f"Image on page {block.page_num+1}")
                    
        elif block.block_type == "list_item":
            style = 'List Bullet' if block.list_style == "bullet" else 'List Number'
            p = doc.add_paragraph(style=style)
            for span in block.spans:
                run = p.add_run(span.text)
                run.bold = span.bold
                run.italic = span.italic
                run.font.size = Pt(span.font_size)
            summary.list_items += 1
            
        else: # paragraph
            p = doc.add_paragraph()
            # Basic alignment heuristic based on bbox (FR-005)
            # This is a bit crude in docx without knowing page width, but we'll stick to styles
            for span in block.spans:
                run = p.add_run(span.text)
                run.bold = span.bold
                run.italic = span.italic
                run.font.size = Pt(span.font_size)
            summary.text_blocks += 1

    doc.save(output_path)
    return summary


def _pdf_to_docx(input_path: str, output_path: str, progress_callback=None, cancel_event=None) -> tuple[bool, str, ConversionSummary | None]:
    """Orchestrate high-fidelity PDF to DOCX conversion."""
    try:
        with fitz.open(input_path) as doc:
            if doc.is_encrypted:
                return False, "PDF is encrypted/password-protected", None
                
            total_pages = len(doc)
            body_font_size = _detect_body_font_size(doc)
            all_blocks = []
            extracted_images = set() # For deduplication (T016)
            extraction_warnings = []
            
            for page_num, page in enumerate(doc):
                # Check for cancellation (FR-014)
                if cancel_event and cancel_event.is_set():
                    if os.path.exists(output_path):
                        os.remove(output_path)
                    return False, "Conversion cancelled by user", None
                    
                if progress_callback:
                    progress_callback(page_num + 1, total_pages)
                
                page_blocks = _extract_page_blocks(page, page_num, body_font_size, doc, extracted_images, warnings=extraction_warnings)
                all_blocks.extend(page_blocks)
                
            summary = _build_docx_from_blocks(all_blocks, output_path)
            summary.total_pages = total_pages
            if extraction_warnings:
                summary.warnings.extend(extraction_warnings)
            
            return True, output_path, summary
            
    except Exception as e:
        _log(f"PDF to DOCX failed: {e}")
        return False, str(e), None


import threading
_libreoffice_lock = threading.Lock()

def detect_converter_backend() -> str:
    """Detect available DOCX to PDF converter backend."""
    import sys
    import shutil

    docx2pdf_available = False
    try:
        import docx2pdf  # noqa: F401
        docx2pdf_available = True
    except ImportError:
        pass

    if docx2pdf_available and sys.platform == "win32":
        # Check Word is installed via registry (avoids launching Word as a side-effect)
        try:
            import winreg
            winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE",
            )
            return "word"
        except Exception:
            pass
        # Fallback: try registry under Wow6432Node (32-bit Word on 64-bit OS)
        try:
            import winreg
            winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE",
            )
            return "word"
        except Exception:
            pass

    if docx2pdf_available and sys.platform == "darwin":  # type: ignore[misc]
        # macOS: docx2pdf drives Word via AppleScript
        if os.path.exists("/Applications/Microsoft Word.app"):
            return "word"

    if shutil.which("libreoffice") or shutil.which("soffice"):
        return "libreoffice"

    if sys.platform == "darwin" and os.path.exists("/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        return "libreoffice"

    return "none"

def _docx_to_pdf(input_path: str, output_path: str, progress_callback=None, cancel_event=None) -> tuple[bool, str, ConversionSummary | None]:
    """Convert DOCX to PDF using docx2pdf or LibreOffice fallback."""
    import sys
    import shutil
    import subprocess
    
    backend = detect_converter_backend()
    if backend == "none":
        return False, "No DOCX-to-PDF converter found (install Microsoft Word or LibreOffice)", None
        
    try:
        from docx import Document
        doc = Document(input_path)
        para_count = len(doc.paragraphs)
    except Exception:
        para_count = 0
    summary = ConversionSummary(total_pages=1, text_blocks=para_count)
        
    if backend == "word":
        try:
            from docx2pdf import convert
            _log("Using docx2pdf backend...")
            convert(input_path, output_path)
            if os.path.exists(output_path):
                return True, output_path, summary
        except Exception as e:
            _log(f"docx2pdf failed, falling back to LibreOffice if available: {e}")
            pass

    soffice_cmd = shutil.which("libreoffice") or shutil.which("soffice")
    if not soffice_cmd and sys.platform == "darwin":
        if os.path.exists("/Applications/LibreOffice.app/Contents/MacOS/soffice"):
            soffice_cmd = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
            
    if soffice_cmd:
        _log("Using LibreOffice backend...")
        outdir = os.path.dirname(os.path.abspath(output_path))
        abs_input = os.path.abspath(input_path)
        cmd = [
            soffice_cmd,
            "--headless",
            "--convert-to", "pdf",
            "--outdir", outdir,
            abs_input
        ]
        with _libreoffice_lock:
            try:
                kwargs = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
                
                # Check cancellation before starting subprocess
                if cancel_event and cancel_event.is_set():
                    return False, "Conversion cancelled by user", None
                    
                # We can't interrupt the subprocess cleanly cross-platform here without complex logic,
                # but we poll cancel_event in convert_document wrapper or rely on subprocess timeouts.
                result = subprocess.run(cmd, capture_output=True, timeout=300, **kwargs)
                if result.returncode == 0:
                    expected_out = os.path.join(outdir, os.path.splitext(os.path.basename(abs_input))[0] + ".pdf")
                    abs_output = os.path.abspath(output_path)
                    if expected_out != abs_output and os.path.exists(expected_out):
                        if os.path.exists(abs_output):
                            os.remove(abs_output)
                        shutil.move(expected_out, abs_output)
                    if os.path.exists(abs_output):
                        return True, output_path, summary
                return False, f"LibreOffice conversion failed: {result.stderr.decode()}", None
            except Exception as e:
                return False, f"LibreOffice failed: {e}", None
                
    return False, "Conversion failed (no backend available)", None


def convert_document(
    input_path: str, 
    output_format: str, 
    progress_callback=None, 
    cancel_event=None
) -> tuple[bool, str, ConversionSummary | None]:
    """Convert a document to output_format.

    Supports PDF and DOCX as input, and the same set as output.
    Images (JPG/PNG/BMP/GIF/WEBP) can be converted to PDF.

    Returns: (success, output_path_or_error, summary)
    """
    input_ext = os.path.splitext(input_path)[1].lower()
    base_name  = os.path.splitext(input_path)[0]
    output_path = f"{base_name}_converted.{output_format}"

    if output_format not in _VALID_OUTPUTS:
        return False, f"Unsupported output format: {output_format}", None
    if input_ext not in _VALID_DOCS | _IMAGE_EXTS:
        return False, f"Unsupported input format: {input_ext}", None

    _log(f"Starting: {os.path.basename(input_path)}  →  {output_format.upper()}")

    # ------------------------------------------------------------------
    # PDF → other
    # ------------------------------------------------------------------
    if input_ext == ".pdf":
        if output_format == "docx":
            return _pdf_to_docx(input_path, output_path, progress_callback, cancel_event)
        return False, f"PDF → {output_format} is not supported", None

    # ------------------------------------------------------------------
    # DOCX → other
    # ------------------------------------------------------------------
    elif input_ext == ".docx":
        if output_format == "pdf":
            return _docx_to_pdf(input_path, output_path, progress_callback, cancel_event)
        return False, f"DOCX → {output_format} is not supported", None

    # ------------------------------------------------------------------
    # Image → PDF
    # ------------------------------------------------------------------
    elif input_ext in _IMAGE_EXTS:
        if output_format != "pdf":
            return False, f"Image → {output_format} is not supported (only image → PDF)", None
        _log("Converting image to PDF…")
        summary = ConversionSummary(total_pages=1, images=1)
        try:
            with Image.open(input_path) as image:
                _log(f"  Image size: {image.size}, mode: {image.mode}")
                img_bytes = io.BytesIO()
                image.convert("RGB").save(img_bytes, format="PNG")
        except Exception as e:
            return False, f"Error reading image: {e}", None
            
        pdf_doc = fitz.open()
        try:
            page = pdf_doc.new_page()
            page.insert_image(page.rect, stream=img_bytes.getvalue())
            _log(f"Saving PDF → {output_path}")
            try:
                pdf_doc.save(output_path)
                return True, output_path, summary
            except Exception as e:
                return False, f"ERROR saving PDF: {e}", None
        finally:
            pdf_doc.close()
