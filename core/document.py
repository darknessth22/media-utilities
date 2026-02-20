"""Document conversion engine: PDF, DOCX, XLSX, PPTX, and image → PDF."""
import contextlib
import io
import os
import tempfile
import xml.etree.ElementTree as ET

import fitz  # PyMuPDF
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt
from openpyxl import Workbook, load_workbook
from PIL import Image
from pptx import Presentation
from pptx.util import Inches as PptxInches


_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"})
_VALID_DOCS  = frozenset({".pdf", ".docx", ".xlsx", ".pptx"})
_VALID_OUTPUTS = frozenset({"pdf", "docx", "xlsx", "pptx"})


def _log(msg: str) -> None:
    print(f"[DocConvert] {msg}", flush=True)


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


def convert_document(input_path: str, output_format: str) -> bool:
    """Convert a document to output_format.

    Supports PDF, DOCX, XLSX, PPTX as input, and the same set as output.
    Images (JPG/PNG/BMP/GIF/WEBP) can be converted to PDF.

    Note: Complex layouts may not convert perfectly.
          Best results with text-heavy documents.
    """
    input_ext = os.path.splitext(input_path)[1].lower()
    base_name  = os.path.splitext(input_path)[0]
    output_path = f"{base_name}_converted.{output_format}"

    if output_format not in _VALID_OUTPUTS:
        _log(f"Unsupported output format: {output_format}")
        return False
    if input_ext not in _VALID_DOCS | _IMAGE_EXTS:
        _log(f"Unsupported input format: {input_ext}")
        return False

    _log(f"Starting: {os.path.basename(input_path)}  →  {output_format.upper()}")
    _log(f"Output will be saved to: {output_path}")

    # ------------------------------------------------------------------
    # PDF → other
    # ------------------------------------------------------------------
    if input_ext == ".pdf":
        with fitz.open(input_path) as doc:
            if doc.is_encrypted:
                _log("ERROR: PDF is encrypted/password-protected. Cannot convert.")
                return False

            page_count = len(doc)
            _log(f"PDF has {page_count} page(s)")

            if output_format == "docx":
                _log("Building DOCX…")
                word_doc = Document()

                for page_num, page in enumerate(doc):
                    _log(f"  Processing page {page_num + 1}/{page_count}…")
                    text_dict  = page.get_text("dict")
                    blocks     = [b for b in text_dict.get("blocks", []) if "lines" in b]
                    image_list = page.get_images()
                    _log(f"    Found {len(blocks)} text block(s) and {len(image_list)} image(s)")

                    image_rects = []
                    for img_index, img in enumerate(image_list):
                        data = _safe_pixmap_png(doc, img[0])
                        if data:
                            pix = fitz.Pixmap(doc, img[0])
                            image_rects.append({
                                "data": data,
                                "index": img_index,
                                "page": page_num,
                                "width": pix.width,
                                "height": pix.height,
                            })
                            pix = None

                    for block in blocks:
                        block_text = ""
                        block_font_size = 12
                        for line in block["lines"]:
                            line_text = ""
                            for span in line.get("spans", []):
                                font_size = span.get("size", 12)
                                if font_size > block_font_size:
                                    block_font_size = font_size
                                line_text += span.get("text", "")
                            if line_text.strip():
                                block_text += line_text + "\n"

                        if block_text.strip():
                            block_rect = fitz.Rect(block["bbox"])
                            page_width  = page.rect.width
                            if block_rect.x0 > page_width * 0.4 and block_rect.x1 < page_width * 0.6:
                                alignment = WD_ALIGN_PARAGRAPH.CENTER
                            elif block_rect.x0 > page_width * 0.7:
                                alignment = WD_ALIGN_PARAGRAPH.RIGHT
                            else:
                                alignment = WD_ALIGN_PARAGRAPH.LEFT
                            paragraph = word_doc.add_paragraph(block_text.strip())
                            paragraph.alignment = alignment
                            for run in paragraph.runs:
                                run.font.size = Pt(max(8, min(block_font_size, 24)))

                        if image_rects and not any(i.get("processed") for i in image_rects):
                            for img_info in image_rects:
                                if not img_info.get("processed"):
                                    try:
                                        ow, oh = img_info["width"], img_info["height"]
                                        sf = min(6.0 * 72 / ow, 1.0) if ow > 0 else 1
                                        w, h = Inches(ow * sf / 72), Inches(oh * sf / 72)
                                        with _temp_png(img_info["data"]) as tmp:
                                            p = word_doc.add_paragraph()
                                            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                                            p.add_run().add_picture(tmp, width=w, height=h)
                                        img_info["processed"] = True
                                        break
                                    except Exception as e:
                                        _log(f"    Warning: Could not inline image {img_info['index']}: {e}")
                                        break

                    for img_info in image_rects:
                        if not img_info.get("processed"):
                            try:
                                ow, oh = img_info["width"], img_info["height"]
                                sf = min(6.0 * 72 / ow, 1.0) if ow > 0 else 1
                                with _temp_png(img_info["data"]) as tmp:
                                    p = word_doc.add_paragraph()
                                    p.add_run().add_picture(
                                        tmp,
                                        width=Inches(ow * sf / 72),
                                        height=Inches(oh * sf / 72),
                                    )
                            except Exception as e:
                                _log(f"    Warning: Could not add trailing image {img_info['index']}: {e}")

                    if page_num < page_count - 1:
                        word_doc.add_page_break()

                _log(f"Saving DOCX → {output_path}")
                try:
                    word_doc.save(output_path)
                except Exception as e:
                    _log(f"ERROR saving DOCX: {e}")
                    return False

            elif output_format == "pptx":
                _log("Building PPTX…")
                prs = Presentation()
                for page_num, page in enumerate(doc):
                    _log(f"  Processing page {page_num + 1}/{page_count}…")
                    slide   = prs.slides.add_slide(prs.slide_layouts[6])
                    text    = page.get_text()
                    imgs    = page.get_images()
                    _log(f"    Text length: {len(text.strip())} chars, {len(imgs)} image(s)")

                    if text.strip():
                        txBox = slide.shapes.add_textbox(
                            PptxInches(0.5), PptxInches(0.5),
                            prs.slide_width - PptxInches(1), PptxInches(2),
                        )
                        txBox.text_frame.text = text

                    img_top = PptxInches(3)
                    for img_index, img in enumerate(imgs):
                        data = _safe_pixmap_png(doc, img[0])
                        if data:
                            try:
                                with _temp_png(data) as tmp:
                                    slide.shapes.add_picture(tmp, PptxInches(1), img_top, width=PptxInches(6))
                                img_top += PptxInches(2)
                            except Exception as e:
                                _log(f"    Warning: Could not add image {img_index} to slide: {e}")

                _log(f"Saving PPTX → {output_path}")
                try:
                    prs.save(output_path)
                except Exception as e:
                    _log(f"ERROR saving PPTX: {e}")
                    return False

            elif output_format == "xlsx":
                _log("Building XLSX (text only)…")
                wb = Workbook()
                ws = wb.active
                for i, page in enumerate(doc):
                    text = page.get_text()
                    _log(f"  Page {i + 1}/{page_count}: {len(text.strip())} chars")
                    ws.cell(row=i + 1, column=1, value=text)
                _log(f"Saving XLSX → {output_path}")
                try:
                    wb.save(output_path)
                except Exception as e:
                    _log(f"ERROR saving XLSX: {e}")
                    return False

            else:
                _log(f"PDF → {output_format} is not supported")
                return False

    # ------------------------------------------------------------------
    # DOCX → other
    # ------------------------------------------------------------------
    elif input_ext == ".docx":
        _log("Reading DOCX…")
        doc = Document(input_path)
        para_count = len(doc.paragraphs)
        _log(f"Found {para_count} paragraph(s)")

        if output_format == "pdf":
            _log("Building PDF…")
            pdf_doc = fitz.open()
            try:
                page       = pdf_doc.new_page()
                y_position = 50
                page_width = page.rect.width
                margin     = 50

                for i, paragraph in enumerate(doc.paragraphs):
                    if i % 20 == 0:
                        _log(f"  Processing paragraph {i + 1}/{para_count}…")

                    if paragraph.text.strip():
                        alignment  = paragraph.alignment
                        text_width = len(paragraph.text) * 6
                        x_position = margin
                        if alignment == 1:
                            x_position = (page_width - text_width) / 2
                        elif alignment == 2:
                            x_position = page_width - margin - text_width
                        x_position = max(margin, min(x_position, page_width - margin - 100))

                        font_size = 12
                        if paragraph.runs and paragraph.runs[0].font.size:
                            font_size = min(24, max(8, paragraph.runs[0].font.size.pt))

                        text_rect = fitz.Rect(
                            x_position, y_position,
                            page_width - margin, y_position + font_size + 5,
                        )
                        page.insert_text(text_rect.tl, paragraph.text, fontsize=font_size)
                        y_position += font_size + 8

                    for run in paragraph.runs:
                        if run.element.xml:
                            try:
                                root_elem = ET.fromstring(run.element.xml)
                                for elem in root_elem.iter():
                                    if "blip" in str(elem.tag).lower() and "embed" in elem.attrib:
                                        rel_id = elem.attrib["embed"]
                                        try:
                                            for rel in doc.part.rels.values():
                                                if rel.rId == rel_id:
                                                    img_bytes  = rel.target_part.blob
                                                    img_width, img_height = 200, 150
                                                    for extent in root_elem.iter():
                                                        if "extent" in str(extent.tag).lower():
                                                            if "cx" in extent.attrib and "cy" in extent.attrib:
                                                                img_width  = min(400, int(extent.attrib["cx"]) / 914400 * 72)
                                                                img_height = min(300, int(extent.attrib["cy"]) / 914400 * 72)
                                                                break
                                                    img_x    = (page_width - img_width) / 2
                                                    img_rect = fitz.Rect(img_x, y_position, img_x + img_width, y_position + img_height)
                                                    page.insert_image(img_rect, stream=img_bytes)
                                                    y_position += img_height + 10
                                                    break
                                        except Exception as img_e:
                                            page.insert_text((margin, y_position), "[Image - could not extract]", fontsize=10)
                                            y_position += 20
                                            _log(f"  Warning: Image extraction failed: {img_e}")
                            except Exception:
                                if "drawing" in run.element.xml.lower() or "image" in run.element.xml.lower():
                                    page.insert_text((margin, y_position), "[Image]", fontsize=10)
                                    y_position += 20

                    if y_position > page.rect.height - 100:
                        page       = pdf_doc.new_page()
                        y_position = 50

                _log(f"Saving PDF → {output_path}")
                try:
                    pdf_doc.save(output_path)
                except Exception as e:
                    _log(f"ERROR saving PDF: {e}")
                    return False
            finally:
                pdf_doc.close()

        elif output_format == "xlsx":
            _log("Building XLSX…")
            wb = Workbook()
            ws = wb.active
            for i, paragraph in enumerate(doc.paragraphs):
                ws.cell(row=i + 1, column=1, value=paragraph.text)
            _log(f"Saving XLSX → {output_path}")
            try:
                wb.save(output_path)
            except Exception as e:
                _log(f"ERROR saving XLSX: {e}")
                return False

        elif output_format == "pptx":
            _log("Building PPTX…")
            prs = Presentation()
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    slide = prs.slides.add_slide(prs.slide_layouts[5])
                    txBox = slide.shapes.add_textbox(0, 0, prs.slide_width, prs.slide_height)
                    txBox.text_frame.text = paragraph.text
            _log(f"Saving PPTX → {output_path}")
            try:
                prs.save(output_path)
            except Exception as e:
                _log(f"ERROR saving PPTX: {e}")
                return False

        else:
            _log(f"DOCX → {output_format} is not supported")
            return False

    # ------------------------------------------------------------------
    # XLSX → other
    # ------------------------------------------------------------------
    elif input_ext == ".xlsx":
        _log("Reading XLSX…")
        wb = load_workbook(input_path)
        ws = wb.active
        row_count = ws.max_row
        _log(f"Found {row_count} row(s)")

        if output_format == "pdf":
            _log("Building PDF…")
            pdf_doc = fitz.open()
            try:
                page = pdf_doc.new_page()
                text = "\n".join(str(cell.value) for row in ws.rows for cell in row if cell.value)
                _log(f"  Total text length: {len(text)} chars")
                page.insert_text((50, 50), text)
                _log(f"Saving PDF → {output_path}")
                try:
                    pdf_doc.save(output_path)
                except Exception as e:
                    _log(f"ERROR saving PDF: {e}")
                    return False
            finally:
                pdf_doc.close()

        elif output_format == "docx":
            _log("Building DOCX…")
            new_doc = Document()
            for row in ws.rows:
                text = " ".join(str(cell.value) for cell in row if cell.value)
                if text.strip():
                    new_doc.add_paragraph(text)
            _log(f"Saving DOCX → {output_path}")
            try:
                new_doc.save(output_path)
            except Exception as e:
                _log(f"ERROR saving DOCX: {e}")
                return False

        elif output_format == "pptx":
            _log("Building PPTX…")
            prs   = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[5])
            txBox = slide.shapes.add_textbox(0, 0, prs.slide_width, prs.slide_height)
            txBox.text_frame.text = "\n".join(
                str(cell.value) for row in ws.rows for cell in row if cell.value
            )
            _log(f"Saving PPTX → {output_path}")
            try:
                prs.save(output_path)
            except Exception as e:
                _log(f"ERROR saving PPTX: {e}")
                return False

        else:
            _log(f"XLSX → {output_format} is not supported")
            return False

    # ------------------------------------------------------------------
    # PPTX → other
    # ------------------------------------------------------------------
    elif input_ext == ".pptx":
        _log("Reading PPTX…")
        prs         = Presentation(input_path)
        slide_count = len(prs.slides)
        slide_width = prs.slide_width
        _log(f"Found {slide_count} slide(s)")

        if output_format == "pdf":
            _log("Building PDF…")
            pdf_doc = fitz.open()
            try:
                for slide_num, slide in enumerate(prs.slides):
                    _log(f"  Processing slide {slide_num + 1}/{slide_count}…")
                    page        = pdf_doc.new_page()
                    page_width  = page.rect.width
                    page_height = page.rect.height
                    scale       = min(page_width / prs.slide_width, page_height / prs.slide_height)

                    for shape in slide.shapes:
                        sl = shape.left   * scale
                        st = shape.top    * scale
                        sw = shape.width  * scale
                        sh = shape.height * scale

                        if hasattr(shape, "text") and shape.text.strip():
                            font_size = min(24, max(8, sh / 10))
                            text_rect = fitz.Rect(sl, st, sl + sw, st + sh)
                            page.insert_text(text_rect.tl, shape.text, fontsize=font_size)
                        elif hasattr(shape, "image"):
                            try:
                                img_rect = fitz.Rect(sl, st, sl + sw, st + sh)
                                page.insert_image(img_rect, stream=shape.image.blob)
                            except Exception as e:
                                page.insert_text((sl, st), "[Image]", fontsize=10)
                                _log(f"    Warning: Could not embed image from slide {slide_num + 1}: {e}")
                        elif shape.shape_type == 13:
                            page.insert_text((sl, st), "[Image]", fontsize=10)

                _log(f"Saving PDF → {output_path}")
                try:
                    pdf_doc.save(output_path)
                except Exception as e:
                    _log(f"ERROR saving PDF: {e}")
                    return False
            finally:
                pdf_doc.close()

        elif output_format == "docx":
            _log("Building DOCX…")
            new_doc = Document()
            for slide_num, slide in enumerate(prs.slides):
                _log(f"  Processing slide {slide_num + 1}/{slide_count}…")
                if slide_num > 0:
                    new_doc.add_page_break()
                new_doc.add_heading(f"Slide {slide_num + 1}", level=2)
                for shape in sorted(slide.shapes, key=lambda s: s.top):
                    if hasattr(shape, "text") and shape.text.strip():
                        paragraph    = new_doc.add_paragraph(shape.text)
                        shape_center = shape.left + shape.width / 2
                        if shape_center < slide_width * 0.3:
                            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                        elif shape_center > slide_width * 0.7:
                            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                        else:
                            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    elif hasattr(shape, "image"):
                        try:
                            ow           = shape.width  / 914400
                            oh           = shape.height / 914400
                            max_w        = 6.5
                            sf           = max_w / ow if ow > max_w else 1
                            shape_center = shape.left + shape.width / 2
                            with _temp_png(shape.image.blob) as tmp:
                                p = new_doc.add_paragraph()
                                p.add_run().add_picture(tmp, width=Inches(ow * sf), height=Inches(oh * sf))
                                if shape_center < slide_width * 0.3:
                                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                                elif shape_center > slide_width * 0.7:
                                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                                else:
                                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        except Exception as e:
                            new_doc.add_paragraph("[Image could not be extracted]")
                            _log(f"    Warning: Could not extract image from slide {slide_num + 1}: {e}")
                    elif shape.shape_type == 13:
                        new_doc.add_paragraph("[Image]")
            _log(f"Saving DOCX → {output_path}")
            try:
                new_doc.save(output_path)
            except Exception as e:
                _log(f"ERROR saving DOCX: {e}")
                return False

        elif output_format == "xlsx":
            _log("Building XLSX…")
            wb      = Workbook()
            ws      = wb.active
            row_num = 1
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        ws.cell(row=row_num, column=1, value=shape.text)
                        row_num += 1
            _log(f"Saving XLSX → {output_path}")
            try:
                wb.save(output_path)
            except Exception as e:
                _log(f"ERROR saving XLSX: {e}")
                return False

        else:
            _log(f"PPTX → {output_format} is not supported")
            return False

    # ------------------------------------------------------------------
    # Image → PDF
    # ------------------------------------------------------------------
    elif input_ext in _IMAGE_EXTS:
        if output_format != "pdf":
            _log(f"Image → {output_format} is not supported (only image → PDF)")
            return False
        _log("Converting image to PDF…")
        with Image.open(input_path) as image:
            _log(f"  Image size: {image.size}, mode: {image.mode}")
            img_bytes = io.BytesIO()
            image.convert("RGB").save(img_bytes, format="PNG")
        pdf_doc = fitz.open()
        try:
            page = pdf_doc.new_page()
            page.insert_image(page.rect, stream=img_bytes.getvalue())
            _log(f"Saving PDF → {output_path}")
            try:
                pdf_doc.save(output_path)
            except Exception as e:
                _log(f"ERROR saving PDF: {e}")
                return False
        finally:
            pdf_doc.close()

    else:
        _log(f"Unsupported input format: {input_ext}")
        return False

    # Verify the output file was actually created and is non-empty
    if os.path.exists(output_path):
        size_kb = os.path.getsize(output_path) / 1024
        _log(f"Done! Output file: {output_path} ({size_kb:.1f} KB)")
    else:
        _log("ERROR: Output file was not created!")
        return False

    return True
