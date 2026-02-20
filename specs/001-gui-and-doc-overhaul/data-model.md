# Data Model: GUI Redesign & Document Conversion Fidelity

**Date**: 2026-02-19 | **Branch**: `001-gui-and-doc-overhaul`

## Entities

### DocumentBlock

A structural unit extracted from a PDF page during conversion.

| Field | Type | Description |
|-------|------|-------------|
| `block_type` | `str` | One of: `"heading"`, `"paragraph"`, `"list_item"`, `"table"`, `"image"`, `"scanned_page"` |
| `text` | `str \| None` | Text content (None for images/scanned pages) |
| `spans` | `list[SpanInfo]` | Formatted text spans within this block |
| `level` | `int \| None` | Heading level (1-4) or list nesting depth; None for non-hierarchical blocks |
| `list_style` | `str \| None` | `"bullet"` or `"number"`; None for non-list blocks |
| `table_data` | `list[list[str]] \| None` | Row/column cell contents; None for non-table blocks |
| `image_bytes` | `bytes \| None` | Raw image data; None for non-image blocks |
| `image_ext` | `str \| None` | Image format (`"png"`, `"jpeg"`, etc.) |
| `bbox` | `tuple[float, float, float, float]` | Bounding box (x0, y0, x1, y1) on source page |
| `page_num` | `int` | Source page number (0-indexed) |

### SpanInfo

Formatting metadata for a text span within a DocumentBlock.

| Field | Type | Description |
|-------|------|-------------|
| `text` | `str` | Span text content |
| `bold` | `bool` | Bold flag |
| `italic` | `bool` | Italic flag |
| `font_size` | `float` | Font size in points |
| `font_name` | `str` | Font family name |
| `color` | `tuple[int, int, int]` | RGB color tuple (0-255 each) |

### ConversionSummary

A record of elements processed during a document conversion operation.

| Field | Type | Description |
|-------|------|-------------|
| `total_pages` | `int` | Total pages in source document |
| `text_blocks` | `int` | Count of text paragraphs extracted |
| `headings` | `int` | Count of headings detected |
| `tables` | `int` | Count of tables extracted |
| `images` | `int` | Count of images extracted |
| `list_items` | `int` | Count of list items detected |
| `scanned_pages` | `int` | Count of image-only pages embedded as images |
| `skipped_elements` | `list[str]` | Descriptions of elements that could not be preserved |
| `warnings` | `list[str]` | Non-fatal issues encountered during conversion |

### ThemeConfig

Application theme configuration persisted across sessions.

| Field | Type | Description |
|-------|------|-------------|
| `mode` | `str` | `"auto"`, `"light"`, or `"dark"` |
| `light_theme` | `str` | ttkbootstrap theme name for light mode (default: `"cosmo"`) |
| `dark_theme` | `str` | ttkbootstrap theme name for dark mode (default: `"darkly"`) |

**Storage**: JSON file at `~/.media_utility.json` (extends existing config).

## Relationships

```
DocumentBlock 1──* SpanInfo        (text blocks contain formatted spans)
ConversionSummary 1──* DocumentBlock  (summary aggregates block counts)
ThemeConfig ──── AppConfig           (stored within existing config file)
```

## State Transitions

### Document Conversion

```
IDLE → VALIDATING → EXTRACTING → BUILDING → COMPLETE
                                          → ERROR

VALIDATING: Check input file exists, not encrypted, format supported
EXTRACTING: Page-by-page extraction with progress (PDF→DOCX only)
BUILDING:   Assembling output document / running external converter
COMPLETE:   Output file written, summary available
ERROR:      Conversion failed, error message available
```

### Theme State

```
AUTO (OS-detected) → MANUAL_LIGHT (user override)
AUTO (OS-detected) → MANUAL_DARK  (user override)
MANUAL_LIGHT       → AUTO (user resets to auto)
MANUAL_DARK        → AUTO (user resets to auto)
```

## Validation Rules

- `DocumentBlock.block_type` must be one of the defined enum values
- `DocumentBlock.level` required when `block_type` is `"heading"` (1-4) or `"list_item"` (1-3)
- `DocumentBlock.table_data` required when `block_type` is `"table"`; must have >= 1 row
- `DocumentBlock.image_bytes` required when `block_type` is `"image"` or `"scanned_page"`
- `SpanInfo.font_size` clamped to range [6.0, 72.0] points
- `SpanInfo.color` each component clamped to [0, 255]
- `ConversionSummary` counts must be non-negative integers
- `ThemeConfig.mode` must be one of `"auto"`, `"light"`, `"dark"`
