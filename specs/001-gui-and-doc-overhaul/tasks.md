# Tasks: GUI Redesign & Document Conversion Fidelity

**Input**: Design documents from `/specs/001-gui-and-doc-overhaul/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in the feature specification. Test tasks are omitted.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add new dependencies required by all user stories

- [ ] T001 Update requirements.txt to add ttkbootstrap>=1.10.0, darkdetect>=0.8.0, and docx2pdf>=0.1.8

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared data models and dependency infrastructure that MUST be complete before ANY user story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T002 [P] Define ConversionSummary dataclass (total_pages, text_blocks, headings, tables, images, list_items, scanned_pages, skipped_elements, warnings) in core/document.py as the shared return type for convert_document()
- [ ] T003 [P] Update utils/deps.py to add dependency checks for ttkbootstrap, darkdetect, docx2pdf import availability, and LibreOffice binary on PATH

**Checkpoint**: Foundation ready — user story implementation can now begin in parallel

---

## Phase 3: User Story 1 — Modern, Visually Polished GUI (Priority: P1) 🎯 MVP

**Goal**: Migrate the GUI to ttkbootstrap with OS-aware dark/light theming, consistent widget styling, placeholder text, and enforced minimum window size

**Independent Test**: Launch the application. Verify all five tabs are clearly labeled with consistent spacing, buttons have distinct primary/secondary styling, input fields show placeholder hints, and switching between light and dark mode updates all widgets without visual artifacts.

### Implementation for User Story 1

- [ ] T004 [US1] Create ThemeManager class in gui/theme.py with: initialize() for OS detection via darkdetect.isDark(), toggle() cycling auto→light→dark→auto, get_current_mode(), get_current_theme_name(), config persistence to ~/.media_utility.json, backward compat migration from legacy dark_mode boolean, and daemon thread OS theme listener dispatching via root.after(0, ...)
- [ ] T005 [US1] Update main.py to replace tkinter.Tk() with ttkbootstrap.Window(themename=...), instantiate ThemeManager, and call initialize() before showing the main window
- [ ] T006 [US1] Migrate gui/app.py to ttkbootstrap: apply bootstyle="primary" to main action buttons (Download, Convert, Trim), bootstyle="secondary-outline" to secondary controls (Browse, Cancel), update Notebook tab styling, and ensure all five tabs have consistent spacing and font hierarchy (FR-001, FR-002)
- [ ] T007 [P] [US1] Add placeholder text with focus-in/focus-out event bindings to all text input fields across all tabs in gui/app.py — e.g., "Paste URL here...", "HH:MM:SS" (FR-003)
- [ ] T008 [US1] Add a theme toggle button (icon or text) to the toolbar/title bar area in gui/app.py that calls ThemeManager.toggle() and updates its label to reflect current mode (FR-004b)
- [ ] T009 [US1] Enforce minimum window size (900×650) via root.minsize() and verify controls reflow without clipping or overlapping when resized in gui/app.py (FR-004)
- [ ] T010 [US1] Smoke-test all five existing tabs (Download, Convert, Batch Convert, Document Convert, Trim) to verify they remain fully functional after the ttkbootstrap migration — fix any broken widget references or layout issues in gui/app.py (FR-013)

**Checkpoint**: At this point, the application should launch with a modern themed GUI, support light/dark mode toggling, and all existing features should work identically

---

## Phase 4: User Story 2 — PDF to DOCX with Format Preservation (Priority: P1)

**Goal**: Rewrite the PDF-to-DOCX pipeline to use PyMuPDF structured extraction (get_text("dict") + find_tables()) mapped to python-docx elements, preserving headings, bold/italic, tables, bullet/numbered lists, and images

**Independent Test**: Convert a multi-page PDF containing a heading, a paragraph with bold and italic text, a bulleted list, a simple table, and an embedded image. Open the resulting DOCX and verify each element is recognizable and appropriately formatted.

### Implementation for User Story 2

- [ ] T011 [US2] Define DocumentBlock dataclass (block_type, text, spans, level, list_style, table_data, image_bytes, image_ext, bbox, page_num) and SpanInfo dataclass (text, bold, italic, font_size, font_name, color) in core/document.py per data-model.md
- [ ] T012 [P] [US2] Implement _detect_body_font_size(doc) in core/document.py — iterate all pages with get_text("dict"), collect font size frequency histogram, return modal font size as body text baseline
- [ ] T013 [P] [US2] Implement _detect_list_item(block, first_span) in core/document.py — check symbol font names (ZapfDingbats, Symbol), match Unicode bullets (\u2022, \u25E6, \uf0b7), regex for numbered patterns (^\d+[.)]), return (is_list, list_style) tuple
- [ ] T014 [US2] Implement _extract_page_blocks(page, body_font_size) in core/document.py — use page.get_text("dict", flags=7) for span-level extraction, classify blocks as heading (size > 1.5× body + bold = H1, > 1.2× = H2), paragraph, or list_item using _detect_list_item(); build SpanInfo with bold (bit 4), italic (bit 1), font_size, color (sRGB decomposition) (depends on T012, T013)
- [ ] T015 [US2] Add table extraction to _extract_page_blocks() using page.find_tables() in core/document.py — extract table bounding boxes BEFORE text processing, exclude table regions from regular text blocks, use table.extract() for cell contents, create DocumentBlock(block_type="table", table_data=...) (depends on T014)
- [ ] T016 [US2] Add image extraction and scanned page detection in core/document.py — implement _is_scanned_page(page) checking empty text + images covering ≥80% area; use page.get_images(full=True) and doc.extract_image(xref) for image bytes; handle CMYK→RGB via Pixmap(csRGB, pix); track xrefs to deduplicate; get position via page.get_image_bbox() (depends on T014)
- [ ] T017 [P] [US2] Implement _build_docx_from_blocks(blocks, output_path) in core/document.py — create python-docx Document, iterate blocks: add_heading(level=N) for headings, add_paragraph with styled runs (bold, italic, Pt(font_size)) for paragraphs, add_paragraph(style='List Bullet'/'List Number') for lists, add_table(rows, cols) for tables, run.add_picture(BytesIO(image_bytes)) for images, full-page image for scanned pages (depends on T011)
- [ ] T018 [US2] Implement _pdf_to_docx(input_path, output_path, progress_callback) in core/document.py — open PDF with fitz.open(), call _detect_body_font_size(), loop pages calling _extract_page_blocks() with table/image extraction, invoke progress_callback(current_page, total_pages), collect all blocks, call _build_docx_from_blocks(), populate ConversionSummary with element counts (depends on T014, T015, T016, T017)
- [ ] T019 [US2] Update convert_document() in core/document.py to route PDF-to-DOCX conversions through _pdf_to_docx() and return (True, output_path, ConversionSummary) on success (depends on T018)

**Checkpoint**: At this point, PDF-to-DOCX conversion should produce DOCX files with preserved headings, styled text, tables, lists, and images

---

## Phase 5: User Story 3 — DOCX to PDF with Format Preservation (Priority: P2)

**Goal**: Implement cross-platform DOCX-to-PDF conversion using docx2pdf (Windows/macOS with Word) with LibreOffice headless fallback (Linux), achieving high-fidelity output with proper text wrapping, tables, and images

**Independent Test**: Convert a DOCX file containing a title, body text with bold/italic, a bulleted list, a two-column table, and an image. Open the resulting PDF and verify that the layout is readable and structurally faithful.

### Implementation for User Story 3

- [ ] T020 [US3] Implement detect_converter_backend() in core/document.py — check sys.platform, try docx2pdf import and Word COM availability on win32/darwin, check for libreoffice on PATH on linux, return "word", "libreoffice", or "none"
- [ ] T021 [US3] Implement _docx_to_pdf() with docx2pdf backend in core/document.py — try docx2pdf.convert(input_path, output_path) for Windows/macOS; catch ImportError or COM errors to fall through to LibreOffice fallback
- [ ] T022 [US3] Add LibreOffice headless subprocess fallback to _docx_to_pdf() in core/document.py — run `libreoffice --headless --convert-to pdf --outdir <dir> <input.docx>` via subprocess; serialize concurrent calls (LibreOffice is not thread-safe)
- [ ] T023 [US3] Update convert_document() in core/document.py to route DOCX-to-PDF conversions through _docx_to_pdf() with fallback chain and return (True, output_path, ConversionSummary) or (False, error_message, None) if no backend available (depends on T020, T021, T022)
- [ ] T024 [US3] Add converter backend check at GUI startup in gui/app.py — call detect_converter_backend() and show a non-blocking warning if result is "none" (install LibreOffice or Microsoft Word)

**Checkpoint**: At this point, DOCX-to-PDF conversion should work on all platforms with high-fidelity output via Word or LibreOffice

---

## Phase 6: User Story 4 — Conversion Progress and Quality Feedback (Priority: P3)

**Goal**: Show page-level progress during PDF-to-DOCX conversion, indeterminate progress during DOCX-to-PDF, and a completion summary with element counts and warnings

**Independent Test**: Convert a 20-page PDF to DOCX. Verify that the progress indicator shows page-level advancement ("Page N of M") and a summary appears upon completion listing element counts.

### Implementation for User Story 4

- [ ] T025 [US4] Add page-level progress bar update for PDF-to-DOCX in the document conversion tab of gui/app.py — wire progress_callback to update a determinate progress bar showing "Page N of M" via root.after() polling at 100ms intervals (FR-011)
- [ ] T026 [US4] Add indeterminate progress bar display for DOCX-to-PDF conversion in gui/app.py — show pulsing progress bar with "Converting..." label during the subprocess/COM call (FR-011)
- [ ] T027 [US4] Add conversion completion summary display in gui/app.py — on conversion success, show ConversionSummary data: count of text blocks, headings, tables, images, list items, scanned pages, and any skipped_elements or warnings in a status area or dialog (FR-012)
- [ ] T027a [US4] Add cancel_event parameter to _pdf_to_docx() in core/document.py — check cancel_event.is_set() at the start of each page loop iteration; if set, delete partial output file and return (False, "Conversion cancelled by user", None); pass cancel_event through convert_document() (FR-014)
- [ ] T027b [US4] Add Cancel button to the document conversion tab in gui/app.py — create a threading.Event, pass it to convert_document(), wire Cancel button to call event.set(); on cancellation, stop progress bar, show "Cancelled" status, re-enable Convert button (FR-014)
- [ ] T028 [US4] Add document size warning for files exceeding 200 pages in gui/app.py — detect page count before conversion, show a non-blocking warning about potential performance degradation, proceed with conversion (NFR-002)

**Checkpoint**: Document conversions now show meaningful progress and completion summaries with quality feedback

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Build system updates, edge case handling, and final validation

- [ ] T029 [P] Update build_executable.py to include ttkbootstrap, darkdetect, and docx2pdf in PyInstaller data/dependency configuration
- [ ] T030 [P] Update media_util_gui.spec to add hidden imports for ttkbootstrap, darkdetect, docx2pdf, and any submodules needed at runtime
- [ ] T031 Handle edge cases in core/document.py: encrypted PDF error message (preserve existing behavior), unsupported format pair error, image extraction failure fallback (log warning, add to skipped_elements), table extraction failure fallback (extract as text, add to warnings)
- [ ] T032 Run all quickstart.md manual test procedures: GUI theme test (launch, toggle, persist), PDF-to-DOCX test (headings, bold/italic, table, list, image), DOCX-to-PDF test (formatting, tables, images), progress and summary test (20+ page file)
- [ ] T033 [P] Update README.md and SETUP.md to document new dependencies (ttkbootstrap, darkdetect, docx2pdf), the theme toggle feature, LibreOffice requirement for DOCX-to-PDF on Linux, and any changed setup steps
- [ ] T034 Verify that the legacy entry point media_util_gui.py still launches the application correctly after all changes — if it imports from gui/app.py, confirm the ttkbootstrap migration does not break it; document any required updates

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **US1 (Phase 3)** and **US2 (Phase 4)**: Both P1 — can proceed **in parallel** after Phase 2
- **US3 (Phase 5)**: Depends on Phase 2 — can proceed in parallel with US1/US2 (independent conversion direction)
- **US4 (Phase 6)**: Depends on US2 (Phase 4) for progress callback infrastructure and US3 (Phase 5) for indeterminate progress
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2 — No dependencies on other stories
- **User Story 2 (P1)**: Can start after Phase 2 — No dependencies on other stories
- **User Story 3 (P2)**: Can start after Phase 2 — Independent of US1/US2 (different conversion direction)
- **User Story 4 (P3)**: Depends on US2 and US3 — adds GUI layer on top of their conversion pipelines

### Within Each User Story

- Data models/dataclasses before implementation functions
- Helper functions before orchestrator functions
- Internal pipeline before convert_document() integration
- Core implementation before GUI integration

### Parallel Opportunities

**Phase 2**: T002 and T003 can run in parallel (different files)

**Phase 3 (US1)**: T007 (placeholder text) can run in parallel with other US1 tasks (independent widget modifications)

**Phase 4 (US2)**: T012 (_detect_body_font_size) and T013 (_detect_list_item) can run in parallel (independent helper functions); T017 (_build_docx_from_blocks) can run in parallel with T015/T016 (depends only on T011 dataclasses)

**Cross-story**: US1, US2, and US3 can all proceed in parallel after Phase 2 (different files: gui/ vs core/document.py extraction vs core/document.py PDF generation)

**Phase 7**: T029 and T030 can run in parallel (different files)

---

## Parallel Example: User Story 2

```bash
# After T011 (dataclasses defined), launch helper functions in parallel:
Task: "T012 [P] [US2] Implement _detect_body_font_size(doc) in core/document.py"
Task: "T013 [P] [US2] Implement _detect_list_item(block, first_span) in core/document.py"

# After T014 (extract_page_blocks), launch DOCX builder in parallel with table/image extraction:
Task: "T015 [US2] Add table extraction to _extract_page_blocks() in core/document.py"
Task: "T016 [US2] Add image extraction and scanned page detection in core/document.py"
Task: "T017 [P] [US2] Implement _build_docx_from_blocks() in core/document.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 + User Story 2)

1. Complete Phase 1: Setup (install dependencies)
2. Complete Phase 2: Foundational (shared data models, dep checks)
3. Complete Phase 3: User Story 1 (modern GUI) — **in parallel with Phase 4**
4. Complete Phase 4: User Story 2 (PDF-to-DOCX fidelity)
5. **STOP and VALIDATE**: Test GUI independently + test PDF-to-DOCX independently
6. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 (GUI) → Test independently → Modern themed app (visual MVP!)
3. US2 (PDF→DOCX) → Test independently → Format-preserving conversion
4. US3 (DOCX→PDF) → Test independently → Bidirectional conversion
5. US4 (Progress) → Test independently → Full user feedback
6. Polish → Build system + edge cases → Release-ready

### Single Developer Strategy

1. Complete Setup + Foundational
2. **US1 first** (GUI migration) — establishes the visual foundation for testing all other stories
3. **US2 next** (PDF-to-DOCX) — the most complex implementation, benefits from GUI for manual testing
4. **US3 next** (DOCX-to-PDF) — simpler integration, delegates to external backends
5. **US4 last** (Progress) — polishes the experience on top of working conversion pipelines
6. Polish — build system, edge cases, final validation

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- No automated tests were requested — manual testing per quickstart.md
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- US1 and US2 are both P1 — can be developed in parallel if capacity allows
