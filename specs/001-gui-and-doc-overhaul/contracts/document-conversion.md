# Contract: Document Conversion Module (`core/document.py`)

## Public API

### `convert_document(input_path, output_format, progress_callback=None, cancel_event=None)`

Converts a document from one format to another with format preservation.

**Parameters**:
- `input_path: str | Path` — Path to the input file
- `output_format: str` — Target format: `"pdf"`, `"docx"`, `"xlsx"`, `"pptx"`
- `progress_callback: Callable[[int, int], None] | None` — Optional callback `(current_page, total_pages)`
- `cancel_event: threading.Event | None` — If set, checked between pages (PDF→DOCX) or before subprocess launch (DOCX→PDF). When triggered, returns `(False, "Conversion cancelled by user", None)`

**Returns**: `tuple[bool, str, ConversionSummary | None]`
- `bool` — Success/failure
- `str` — Output file path on success, error message on failure
- `ConversionSummary | None` — Element counts and warnings on success, None on failure

**Behavior**:
- Determines conversion path from input extension + output format
- PDF-to-DOCX: structured extraction with heading/table/list/image detection
- DOCX-to-PDF: delegates to `docx2pdf` (Windows/macOS) or LibreOffice (Linux)
- Reports per-page progress for PDF-to-DOCX via callback
- Reports indeterminate progress for DOCX-to-PDF (no per-page granularity)
- Scanned PDF pages: embedded as full-page images in output
- Encrypted PDFs: returns failure with descriptive error message

### `detect_converter_backend()`

Checks availability of DOCX-to-PDF conversion backends.

**Returns**: `str` — One of `"word"`, `"libreoffice"`, `"none"`

**Behavior**:
- Windows/macOS: tries `docx2pdf` import and Word COM availability
- Linux: checks for `libreoffice` on PATH
- Returns `"none"` if no backend available (GUI should warn user)

## Internal Functions (not part of public API)

- `_pdf_to_docx(input_path, output_path, progress_callback)` — Structured PDF extraction
- `_docx_to_pdf(input_path, output_path)` — Platform-aware PDF generation
- `_extract_page_blocks(page, body_font_size)` — Extract DocumentBlocks from a PDF page
- `_detect_body_font_size(doc)` — Statistical analysis of font sizes across document
- `_is_scanned_page(page)` — Detect image-only pages
- `_detect_list_item(block, first_span)` — Heuristic list detection using block text and first span's font metadata
- `_build_docx_from_blocks(blocks, output_path)` — Assemble DOCX from DocumentBlocks

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Input file not found | Return `(False, "File not found: {path}", None)` |
| Encrypted PDF | Return `(False, "PDF is encrypted/password-protected", None)` |
| Unsupported format pair | Return `(False, "Conversion from {ext} to {fmt} not supported", None)` |
| Image extraction failure | Log warning, continue without image, add to `skipped_elements` |
| Table extraction failure | Log warning, extract as text fallback, add to `warnings` |
| DOCX-to-PDF backend missing | Return `(False, "No PDF converter available. Install LibreOffice or Microsoft Word.", None)` |
| Document exceeds 200 pages | Log warning, proceed with conversion, add to `warnings` |
| User cancels conversion | Stop processing, delete partial output file, return `(False, "Conversion cancelled by user", None)` |
