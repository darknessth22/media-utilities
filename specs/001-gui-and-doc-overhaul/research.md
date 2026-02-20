# Research: GUI Redesign & Document Conversion Fidelity

**Date**: 2026-02-19 | **Branch**: `001-gui-and-doc-overhaul`

## R-001: ttkbootstrap for GUI Theming

**Decision**: Use `ttkbootstrap` with `darkdetect` for OS-aware theme switching.

**Rationale**: ttkbootstrap provides 18 built-in themes (13 light, 5 dark), Bootstrap-style `bootstyle` parameter for widget styling, and auto-styling of legacy tkinter widgets. Paired with `darkdetect` for OS dark/light mode detection, this delivers the spec's theme requirements with minimal custom code.

**Alternatives considered**:
- `sv_ttk` (Sun Valley): Lighter weight but fewer theme options; no built-in color variants for buttons.
- Custom `ttk.Style`: Maximum control but significant effort to build two complete themes from scratch.

**Key implementation details**:
- Initialize with `ttkbootstrap.Window(themename=...)` instead of `tkinter.Tk()`
- Light theme: `cosmo` or `litera`; Dark theme: `darkly`
- OS detection: `darkdetect.isDark()` at startup; `darkdetect.listener()` on daemon thread for runtime changes
- Theme switching: `root.style.theme_use("darkly")` — all widgets update automatically
- Button styling: `bootstyle="primary"` for main actions, `bootstyle="secondary-outline"` for secondary
- Placeholder text must be implemented manually (focus-in/focus-out bindings)
- Notebook tabs support `bootstyle` for inactive tab coloring
- `Style` is a singleton — only one theme active across all windows
- Thread safety: theme switches from background threads must use `root.after(0, ...)`
- Legacy tkinter widgets (Text, Listbox, Menu) are auto-styled by default

**New dependencies**: `ttkbootstrap>=1.10.0`, `darkdetect>=0.8.0`

---

## R-002: PDF-to-DOCX Conversion with Format Preservation

**Decision**: Use PyMuPDF `page.get_text("dict")` for structured extraction with font metadata, `page.find_tables()` for table detection, and `python-docx` for DOCX generation.

**Rationale**: PyMuPDF's dict extraction mode provides per-span font size, bold/italic flags, color, and font name. Combined with `find_tables()` (available since PyMuPDF 1.23.0) for table detection and `extract_image(xref)` for efficient image extraction, this enables high-fidelity mapping to python-docx elements.

**Alternatives considered**:
- `pdf2docx`: Higher-level but less control over individual element mapping; intermittent maintenance.
- `pdfplumber` + `python-docx`: Good table detection but slower than PyMuPDF; no image extraction.

**Key implementation details**:

### Text extraction
- Use `page.get_text("dict", flags=7)` — preserves ligatures, whitespace, and images
- Font flags: bit 4 = bold (value 16), bit 1 = italic (value 2)
- Color: sRGB integer — decompose with `(color >> 16) & 0xFF` for R, etc.
- Font size: `span["size"]` in points — map directly to `Pt()` in python-docx

### Heading detection (two-pass)
- Pass 1: Collect font size frequency across entire document; modal size = body text
- Pass 2: Classify spans — size > 1.5x body + bold = Heading 1; size > 1.2x body = Heading 2
- Map to `doc.add_heading(text, level=N)`

### List detection (combined heuristic)
- Check first span font name for symbol fonts (ZapfDingbats, WingDings, Symbol)
- Match Unicode bullet chars: `\u2022`, `\u2023`, `\u25E6`, `\uf0b7`
- Regex for numbered patterns: `^\d+[.)]`, `^[a-z][.)]`
- Verify consistent left indent via `bbox[0]` across consecutive blocks
- Map to `doc.add_paragraph(text, style='List Bullet')` or `'List Number'`

### Table detection
- Call `page.find_tables()` BEFORE text extraction on each page
- Extract table regions as bounding boxes; exclude from regular text processing
- Use `table.extract()` for cell content → `doc.add_table(rows, cols)`
- Strategy: `"lines"` (default) for bordered tables; fallback to `"text"` for borderless

### Image extraction
- `page.get_images(full=True)` for image references per page
- `doc.extract_image(xref)` for raw bytes — preserves original format, very fast
- Handle CMYK: check `pix.n - pix.alpha > 3`, convert via `Pixmap(csRGB, pix)`
- Track extracted xrefs to avoid duplicates across pages
- Get position via `page.get_image_bbox(img_item)`
- Add to DOCX via `run.add_picture(io.BytesIO(img_bytes), width=Inches(w))`

### Scanned page detection
- `page.get_text().strip()` empty + `page.get_images()` non-empty + image covers >= 80% of page area
- Action: render page as full-page image and embed in DOCX

### Performance
- dict extraction: ~3.93x plain text speed — well within 2s/page target
- Process sequentially (PyMuPDF not fully thread-safe for find_tables)
- Deduplicate images by xref
- Reuse TextPage objects when multiple get_text calls needed per page

---

## R-003: DOCX-to-PDF Conversion Strategy (Cross-Platform)

**Decision**: Platform-aware routing — `docx2pdf` (Windows/macOS with Word) with LibreOffice subprocess fallback (Linux and systems without Word).

**Rationale**: `docx2pdf` (v0.1.8) only supports Windows and macOS and requires Microsoft Word installed. It does NOT support Linux and does NOT use LibreOffice. For cross-platform compatibility (Constitution Principle II), we need a fallback. LibreOffice headless mode provides acceptable fidelity on all platforms.

**Alternatives considered**:
- `docx2pdf` only: Rejected — no Linux support violates cross-platform principle.
- LibreOffice only: Acceptable fidelity but requires LibreOffice on all platforms including Windows where Word is more common.
- `fpdf2`/`reportlab` manual rendering: Full control but enormous implementation effort for marginal benefit over LibreOffice.

**Key implementation details**:
- Platform detection: `sys.platform` — `win32` → docx2pdf (try), `darwin` → docx2pdf (try), `linux` → LibreOffice
- Fallback chain: try `docx2pdf` first; if ImportError or Word not available, try LibreOffice
- LibreOffice command: `libreoffice --headless --convert-to pdf --outdir <dir> <input.docx>`
- LibreOffice is not thread-safe — serialize concurrent conversions
- No per-page progress available from either backend — report as indeterminate or "converting..."
- docx2pdf has no custom progress callback API
- Runtime dependency check: validate Word or LibreOffice availability at startup; warn if neither found

**New dependencies**: `docx2pdf>=0.1.8` (optional — graceful fallback if unavailable)

**Spec update needed**: The spec states `python-docx2pdf` as the library. The actual PyPI package is `docx2pdf`. Also, it does NOT use LibreOffice — it requires Word. The plan accounts for this by adding a LibreOffice fallback for cross-platform support.

---

## R-004: OS Dark/Light Mode Detection

**Decision**: Use `darkdetect` library for cross-platform OS theme detection.

**Rationale**: `darkdetect` provides a simple API (`isDark()`, `isLight()`, `theme()`) and a real-time listener for theme changes. It uses native OS APIs on Windows 10+, macOS 10.14+, and Linux (GTK, experimental).

**Alternatives considered**:
- Windows registry reading: Windows-only; would need platform-specific code for macOS/Linux.
- Manual toggle only: Doesn't meet FR-004a (auto-detect OS preference).

**Key implementation details**:
- `darkdetect.isDark()` at startup → select `"darkly"` or `"cosmo"` theme
- Optional: `darkdetect.listener(callback)` on daemon thread for live OS theme changes
- Callback must use `root.after(0, ...)` for thread-safe tkinter updates
- User override stored in config file (`~/.media_utility.json`) takes precedence over OS detection
- If `darkdetect` returns `None` (unsupported platform), default to light theme

**New dependencies**: `darkdetect>=0.8.0`

---

## R-005: Progress Reporting for Document Conversion

**Decision**: Page-level progress callback for PDF-to-DOCX; indeterminate progress for DOCX-to-PDF.

**Rationale**: PyMuPDF provides `len(doc)` for total pages, enabling page-by-page progress. Neither `docx2pdf` nor LibreOffice subprocess expose per-page progress, so DOCX-to-PDF must use indeterminate progress with a "Converting..." message.

**Key implementation details**:
- PDF-to-DOCX: `progress_callback(current_page, total_pages)` called after each page
- DOCX-to-PDF: indeterminate progress bar during subprocess/COM call
- GUI polls progress via `root.after()` with 100ms interval
- Conversion summary collected during processing: counts of text blocks, tables, images, skipped elements
- Summary displayed in status bar or dialog upon completion
