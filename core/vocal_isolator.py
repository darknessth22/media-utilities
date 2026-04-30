"""AI Vocal Isolator — HTDemucs v4 (Meta) 2-stem separation."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".opus", ".wma"}
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}
SUPPORTED_EXTS = AUDIO_EXTS | VIDEO_EXTS

_PROGRESS_RE = re.compile(r"(\d+)%")


def detect_device() -> str:
    """Return 'cuda' if a CUDA-capable GPU is available, else 'cpu'."""
    try:
        import torch  # type: ignore
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def separate_vocals(
    input_path: str,
    output_dir: str,
    progress_cb: Callable[[int], None] | None = None,
    cancelled_cb: Callable[[], bool] | None = None,
) -> dict:
    """Run HTDemucs 2-stem (vocals / no_vocals) separation via subprocess.

    Returns a dict with keys: success, vocals_path, accompaniment_path, device.
    On failure: success=False, error=<message>.
    """
    device = detect_device()

    cmd = [
        sys.executable, "-m", "demucs",
        "--two-stems", "vocals",
        "-n", "htdemucs",
        "--device", device,
        "-o", output_dir,
        input_path,
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )

        last_pct = -1
        for line in proc.stdout:  # type: ignore[union-attr]
            if cancelled_cb and cancelled_cb():
                proc.kill()
                return {"success": False, "error": "Cancelled"}

            m = _PROGRESS_RE.search(line)
            if m and progress_cb:
                pct = int(m.group(1))
                if pct != last_pct:
                    last_pct = pct
                    progress_cb(pct)

        proc.wait()

        if proc.returncode != 0:
            return {
                "success": False,
                "error": f"demucs exited with code {proc.returncode}",
            }

        # Output layout: <output_dir>/htdemucs/<input_stem>/vocals.wav + no_vocals.wav
        stem_name = Path(input_path).stem
        out_dir = Path(output_dir) / "htdemucs" / stem_name

        vocals = out_dir / "vocals.wav"
        no_vocals = out_dir / "no_vocals.wav"

        missing = [str(p) for p in (vocals, no_vocals) if not p.exists()]
        if missing:
            # Demucs may use the source stem as directory name differently — scan
            found = list(out_dir.parent.rglob("vocals.wav")) if out_dir.parent.exists() else []
            if found:
                vocals = found[0]
                candidate = vocals.parent / "no_vocals.wav"
                no_vocals = candidate if candidate.exists() else no_vocals
            else:
                return {
                    "success": False,
                    "error": f"Output not found at expected path: {out_dir}",
                }

        return {
            "success": True,
            "device": device,
            "vocals_path": str(vocals),
            "accompaniment_path": str(no_vocals),
            "output_dir": str(vocals.parent),
        }

    except FileNotFoundError:
        return {
            "success": False,
            "error": "demucs not found. Install it: pip install demucs",
        }
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}
