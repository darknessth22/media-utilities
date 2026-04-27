"""Standalone helper: render assets/icons/dashboard.svg → icon.ico using PySide6 + Pillow.

Called as a subprocess by build_executable.py so it can own the QApplication lifetime.
"""
import io
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

SVG_PATH = Path("assets/icons/dashboard.svg")
ICO_PATH = Path("icon.ico")
ACCENT = "#3B82F6"
SIZES = [16, 24, 32, 48, 64, 128, 256]


def _render(svg_bytes: bytes, size: int) -> Image.Image:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg_bytes))
    painter = QPainter(img)
    renderer.render(painter)
    painter.end()

    buf = QByteArray()
    from PySide6.QtCore import QBuffer, QIODevice
    qbuf = QBuffer(buf)
    qbuf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(qbuf, "PNG")
    qbuf.close()

    return Image.open(io.BytesIO(bytes(buf))).convert("RGBA")


def main() -> None:
    if not SVG_PATH.exists():
        print(f"WARNING: {SVG_PATH} not found -- skipping icon generation")
        sys.exit(0)

    svg_text = SVG_PATH.read_text(encoding="utf-8")
    svg_text = svg_text.replace("currentColor", ACCENT)
    if "fill=" not in svg_text and "stroke=" not in svg_text:
        svg_text = svg_text.replace("<svg", f'<svg fill="{ACCENT}"', 1)
    svg_bytes = svg_text.encode("utf-8")

    app = QApplication.instance() or QApplication(sys.argv)

    frames = [_render(svg_bytes, s) for s in SIZES]
    frames[0].save(
        ICO_PATH,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=frames[1:],
    )
    print(f"OK icon.ico written ({len(SIZES)} sizes)")


if __name__ == "__main__":
    main()
