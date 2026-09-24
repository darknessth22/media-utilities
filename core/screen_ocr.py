"""Recognise text in a screen region.

Wraps the existing OCR engines (``core/ocr.py``) with the bit the screen tool
needs: turning scattered detections back into readable lines.
"""
from __future__ import annotations

import io

MIN_CONFIDENCE = 0.35       # below this a reading is usually noise
UPSCALE = 2.0               # small on-screen text recognises far better enlarged
# Upscaling past this stops helping and starts hurting: a 1920x400 grab taken
# to 3840x800 returned ZERO characters, while the same region at 1x read fine.
MAX_SIDE = 2600


def available() -> bool:
    try:
        from core.ocr import installed_engines
        return bool(installed_engines())
    except Exception:
        return False


def warm_up(lang: str = "en") -> bool:
    """Construct the OCR engine NOW, on whatever thread calls this.

    RapidOCR builds its ONNX sessions on first use, and doing that inside a
    QThread hung indefinitely — no exception, the thread simply never returned.
    Constructing it on the GUI thread first puts the instance in ocr.py's
    module-level cache, so the worker only runs inference and never touches
    session setup. Costs ~1 s once, at a moment we choose.
    """
    engine = _preferred_engine()
    if engine is None:
        return False
    try:
        if engine == "rapid":
            from core.ocr import _get_rapid
            _get_rapid(lang)
        else:
            from core.ocr import _get_easy
            _get_easy(lang, False)
    except Exception:
        return False
    return True


def _preferred_engine() -> str | None:
    from core.ocr import installed_engines

    engines = installed_engines()
    if not engines:
        return None
    # RapidOCR is the lighter of the two and needs no model download.
    return "rapid" if "rapid" in engines else engines[0]


def extract(image, lang: str = "en") -> str:
    """OCR a QImage of a screen region and return its text.

    Returns "" when no engine is installed or nothing is recognised, so the
    caller can report that rather than handling exceptions.
    """
    engine = _preferred_engine()
    if engine is None or image is None or image.isNull():
        return ""

    from PySide6.QtCore import QBuffer, QByteArray, Qt

    # Screen text is small; recognition accuracy improves markedly with a
    # straight upscale before the engine sees it.
    scaled = image
    factor = UPSCALE
    longest = max(image.width(), image.height()) or 1
    if longest * factor > MAX_SIDE:
        factor = max(1.0, MAX_SIDE / longest)
    if factor != 1.0:
        scaled = image.scaled(
            int(image.width() * factor), int(image.height() * factor),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    scaled.save(buffer, "PNG")
    buffer.close()

    from core.ocr import _ocr_image_bytes

    try:
        results = _ocr_image_bytes(engine, bytes(data.data()), lang, False)
    except Exception:
        return ""
    return _to_lines(results)


def _to_lines(results) -> str:
    """Group detections into lines by vertical position, then read left to right.

    Engines return boxes in detection order, which is not reading order — a
    naive join produces scrambled text. Boxes whose vertical centres are within
    half a line height belong to the same line.
    """
    boxes = []
    for item in results or []:
        try:
            box, text, score = item[0], item[1], float(item[2])
        except Exception:
            continue
        if not text or not text.strip() or score < MIN_CONFIDENCE:
            continue
        ys = [float(p[1]) for p in box]
        xs = [float(p[0]) for p in box]
        boxes.append({
            "text": text.strip(),
            "cy": (min(ys) + max(ys)) / 2.0,
            "x": min(xs),
            "h": max(ys) - min(ys),
        })
    if not boxes:
        return ""

    boxes.sort(key=lambda b: b["cy"])
    median_h = sorted(b["h"] for b in boxes)[len(boxes) // 2] or 1.0
    tolerance = max(4.0, median_h * 0.6)

    lines: list[list[dict]] = [[boxes[0]]]
    for box in boxes[1:]:
        if abs(box["cy"] - lines[-1][-1]["cy"]) <= tolerance:
            lines[-1].append(box)
        else:
            lines.append([box])

    out = []
    for line in lines:
        line.sort(key=lambda b: b["x"])
        out.append(" ".join(b["text"] for b in line))
    return "\n".join(out)
