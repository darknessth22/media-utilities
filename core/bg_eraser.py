"""Background removal using rembg — fully offline, no cloud calls."""
from __future__ import annotations

import os

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}


def remove_background(input_path: str, output_path: str | None = None) -> dict:
    """Strip the background from *input_path* and save as PNG with alpha.

    output_path: if None, derives from input stem + '_nobg.png' in same dir.
    Returns {"success": bool, "file_path": str, "error": str}
    """
    if not os.path.isfile(input_path):
        return {"success": False, "file_path": "", "error": "Source file not found."}

    ext = os.path.splitext(input_path)[1].lower()
    if ext not in IMAGE_EXTS:
        return {
            "success": False,
            "file_path": "",
            "error": f"Unsupported format '{ext}'. Use JPG, PNG, WEBP, or BMP.",
        }

    if output_path is None:
        stem = os.path.splitext(input_path)[0]
        output_path = f"{stem}_nobg.png"

    try:
        from rembg import remove as rembg_remove
        from PIL import Image
    except (ImportError, SystemExit) as exc:
        return {
            "success": False,
            "file_path": "",
            "error": f"Background removal unavailable: {exc}",
        }

    try:
        with Image.open(input_path) as img:
            result = rembg_remove(img)
        result.save(output_path, format="PNG")
    except Exception as exc:
        return {"success": False, "file_path": "", "error": str(exc)}

    return {"success": True, "file_path": output_path, "error": ""}
