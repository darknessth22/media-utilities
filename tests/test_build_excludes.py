"""Verify PyInstaller output dist/Videl/ contains no excluded AI packages.

Skipped when dist/Videl/ does not exist (e.g. CI step before build, or local dev).
"""

from pathlib import Path

import pytest

EXCLUDED = {"rembg", "demucs", "torch", "tensorflow", "cv2", "numba", "onnxruntime"}

DIST_DIR = Path(__file__).resolve().parents[1] / "dist" / "Videl"


@pytest.mark.skipif(not DIST_DIR.exists(), reason="dist/Videl/ not built yet")
def test_no_excluded_ai_packages_in_dist():
    offenders = []
    for path in DIST_DIR.rglob("*"):
        rel = path.relative_to(DIST_DIR)
        for part in rel.parts:
            stem = part.lower()
            # Strip extension for files (e.g. cv2.cp312-win_amd64.pyd -> cv2)
            base = stem.split(".", 1)[0]
            if base in EXCLUDED:
                offenders.append(str(rel))
                break
    assert not offenders, (
        "Excluded AI packages leaked into dist/Videl/:\n  "
        + "\n  ".join(sorted(set(offenders)))
    )
