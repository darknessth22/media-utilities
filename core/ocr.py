"""OCR engine dispatch + PDF OCR.

Two engines, both installed on demand via the AI components manager:

- "rapid" -> RapidOCR (ONNX, lightweight, EN + AR + CJK)
- "easy"  -> EasyOCR  (torch, ~80 languages, GPU optional)

Output modes:
- searchable PDF (invisible text layer over page images)
- plain text (.txt)
"""
from __future__ import annotations

import io
import os
from typing import Callable

# RapidOCR ships its own ONNX models inside the package — no separate model
# weights need to be downloaded after pip install.
# EasyOCR downloads detector+recognizer weights to ~/.EasyOCR on first call;
# we redirect that to the component dir so frozen builds remain self-contained.


# Language code maps. UI exposes neutral codes; engines need engine-specific
# tokens. Keep both engines in sync where practical (EN/AR share codes).

_RAPID_LANGS = {
    # The default rapidocr-onnxruntime pip package ships Chinese + English +
    # number recognition models only. Arabic / other RTL scripts need separate
    # ONNX weights (not bundled here) — for those, route the user to EasyOCR.
    "en": "en",
    "ch": "ch",
    "ja": "japan",
    "ko": "korean",
}

_EASY_LANGS = {
    "en": ["en"],
    "ar": ["ar"],
    "ch": ["ch_sim"],
    "ja": ["ja"],
    "ko": ["ko"],
    # Multi-pass (EasyOCR allows mixing Latin with one non-Latin):
    "en+ar": ["en", "ar"],
    "en+fr": ["en", "fr"],
    "en+es": ["en", "es"],
}


# ── Engine readiness ─────────────────────────────────────────────────────────

def installed_engines() -> list[str]:
    """Return the subset of {'rapid', 'easy'} whose import succeeds."""
    out: list[str] = []
    try:
        import rapidocr_onnxruntime  # noqa: F401
        out.append("rapid")
    except Exception:
        pass
    try:
        import easyocr  # noqa: F401
        out.append("easy")
    except Exception:
        pass
    return out


def supported_langs(engine: str) -> list[str]:
    """UI-facing language codes for the given engine."""
    if engine == "rapid":
        return list(_RAPID_LANGS.keys())
    if engine == "easy":
        return list(_EASY_LANGS.keys())
    return []


# ── Engine wrappers ──────────────────────────────────────────────────────────

_rapid_cache: dict[str, object] = {}
_easy_cache: dict[tuple, object] = {}


def _get_rapid(lang: str):
    key = lang
    if key in _rapid_cache:
        return _rapid_cache[key]
    from rapidocr_onnxruntime import RapidOCR
    # RapidOCR doesn't take a lang param at construction in current versions;
    # the bundled model handles Latin + supported scripts. Lang is informational
    # for callers and reserved for future per-language model switching.
    inst = RapidOCR()
    _rapid_cache[key] = inst
    return inst


def _get_easy(lang_code: str, use_gpu: bool):
    key = (lang_code, use_gpu)
    if key in _easy_cache:
        return _easy_cache[key]
    import easyocr
    langs = _EASY_LANGS.get(lang_code, ["en"])
    # model_storage_directory: keep weights inside the component dir so they
    # don't pollute the user's home and survive cleanly on uninstall.
    from utils import model_manager
    target = os.path.join(
        os.path.dirname(model_manager._component_dir("ocr_easy")),
        "ocr_easy", "_easyocr_models",
    )
    os.makedirs(target, exist_ok=True)
    reader = easyocr.Reader(
        langs,
        gpu=use_gpu,
        model_storage_directory=target,
        download_enabled=True,
        verbose=False,
    )
    _easy_cache[key] = reader
    return reader


def _ocr_image_bytes(engine: str, png_bytes: bytes, lang: str,
                     use_gpu: bool) -> list[tuple[list, str, float]]:
    """Run OCR on a PNG byte-string. Return [(box, text, score), ...]
    where box = [(x0,y0),(x1,y0),(x1,y1),(x0,y1)] in pixel coords.
    """
    if engine == "rapid":
        ocr = _get_rapid(lang)
        result, _ = ocr(png_bytes)
        return result or []
    if engine == "easy":
        reader = _get_easy(lang, use_gpu)
        # EasyOCR accepts numpy arrays; decode the PNG.
        import numpy as np
        from PIL import Image
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        arr = np.array(img)
        raw = reader.readtext(arr, detail=1, paragraph=False)
        # Returns list of (box, text, score). Box already as 4-point polygon.
        return [(list(box), text, float(score)) for (box, text, score) in raw]
    raise ValueError(f"Unknown OCR engine: {engine}")


# ── PDF OCR ──────────────────────────────────────────────────────────────────

def ocr_pdf(
    input_path: str,
    output_path: str,
    *,
    engine: str = "rapid",
    lang: str = "en",
    searchable: bool = True,
    dpi: int = 300,
    use_gpu: bool = False,
    progress_cb: Callable[[int, int], None] | None = None,
) -> tuple[bool, str]:
    """OCR a PDF.

    searchable=True  -> write a new PDF where each page is the original image
                        with an invisible text layer (Ctrl+F works).
    searchable=False -> write a .txt file (one paragraph block per page,
                        pages separated by a form-feed character).

    Returns (success, output_path_or_error_message).
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(input_path)
        total = len(doc)

        if searchable:
            out = fitz.open()
        text_pages: list[str] = []

        for i, page in enumerate(doc):
            if progress_cb:
                progress_cb(i + 1, total)

            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            png_bytes = pix.tobytes("png")

            results = _ocr_image_bytes(engine, png_bytes, lang, use_gpu)

            if searchable:
                w_pt = page.rect.width
                h_pt = page.rect.height
                new_page = out.new_page(width=w_pt, height=h_pt)
                new_page.insert_image(new_page.rect, pixmap=pix)

                sx = w_pt / pix.width
                sy = h_pt / pix.height

                for box, text, _score in results:
                    if not text:
                        continue
                    xs = [pt[0] for pt in box]
                    ys = [pt[1] for pt in box]
                    x0, x1 = min(xs) * sx, max(xs) * sx
                    y0, y1 = min(ys) * sy, max(ys) * sy
                    rect = fitz.Rect(x0, y0, x1, y1)
                    if rect.is_empty or rect.width <= 0 or rect.height <= 0:
                        continue
                    fontsize = max(1.0, rect.height * 0.8)
                    try:
                        new_page.insert_textbox(
                            rect, text,
                            fontsize=fontsize,
                            render_mode=3,  # invisible text
                            align=0,
                        )
                    except Exception:
                        # Fallback: place a small invisible glyph at top-left.
                        new_page.insert_text(
                            (x0, y0 + fontsize),
                            text, fontsize=fontsize, render_mode=3,
                        )
            else:
                page_text = "\n".join(t for _, t, _ in results if t)
                text_pages.append(page_text)

        if searchable:
            out.save(output_path, garbage=4, deflate=True, clean=True)
            out.close()
        else:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n\f\n".join(text_pages))

        doc.close()
        return True, output_path

    except Exception as e:  # noqa: BLE001
        return False, str(e)
