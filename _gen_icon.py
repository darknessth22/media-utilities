"""Standalone helper: resize icon-new.png → icon.ico using Pillow.

Called as a subprocess by build_executable.py so it can own the icon generation.
"""
import sys
from pathlib import Path

from PIL import Image

PNG_PATH = Path("icon-new.png")
ICO_PATH = Path("icon.ico")
SIZES = [16, 24, 32, 48, 64, 128, 256]


def main() -> None:
    if not PNG_PATH.exists():
        print(f"WARNING: {PNG_PATH} not found -- skipping icon generation")
        sys.exit(0)

    src = Image.open(PNG_PATH).convert("RGBA")

    # Center-crop to square (source is landscape 2400x1497)
    w, h = src.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    src = src.crop((left, top, left + side, top + side))

    src = src.resize((256, 256), Image.LANCZOS)
    src.save(ICO_PATH, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"OK icon.ico written ({len(SIZES)} sizes)")


if __name__ == "__main__":
    main()
