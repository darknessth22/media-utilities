"""AI Vocal Isolator — HTDemucs 2-stem separation."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".opus", ".wma"}
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}
SUPPORTED_EXTS = AUDIO_EXTS | VIDEO_EXTS

# preset_key → (model_name, extra_flags)
PRESETS: dict[str, tuple[str, list[str]]] = {
    "fast":     ("htdemucs",    ["--no-split"]),
    "balanced": ("htdemucs",    []),
    "quality":  ("htdemucs_ft", []),
}

_PROGRESS_RE = re.compile(r"(\d+)%")


def detect_device() -> str:
    try:
        import torch  # type: ignore
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def _python_exe() -> str:
    """Return a usable Python executable (handles frozen PyInstaller exe)."""
    if getattr(sys, "frozen", False):
        for candidate in ("python", "python3"):
            try:
                r = subprocess.run([candidate, "--version"], capture_output=True, timeout=5)
                if r.returncode == 0:
                    return candidate
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        raise RuntimeError("Python not found on PATH. Install Python and ensure it is on PATH.")
    return sys.executable


def separate_vocals(
    input_path: str,
    output_dir: str,
    fmt: str = "wav",
    preset: str = "balanced",
    progress_cb: Callable[[int], None] | None = None,
    cancelled_cb: Callable[[], bool] | None = None,
) -> dict:
    """Run HTDemucs 2-stem separation.

    fmt: 'wav' | 'mp3' | 'flac'
    preset: 'fast' | 'balanced' | 'quality'
    Returns dict: success, vocals_path, accompaniment_path, device, output_dir.
    """
    device = detect_device()

    try:
        python = _python_exe()
    except RuntimeError as exc:
        return {"success": False, "error": str(exc)}

    model, extra_flags = PRESETS.get(preset, PRESETS["balanced"])

    # Format flag for demucs
    fmt_flag: list[str] = []
    if fmt == "mp3":
        fmt_flag = ["--mp3"]
    elif fmt == "flac":
        fmt_flag = ["--flac"]
    # wav is demucs default — but torchaudio 2.5+ needs torchcodec for wav;
    # fall back to flac if wav requested to avoid the torchcodec dependency.
    else:
        fmt_flag = ["--flac"]
        fmt = "flac"

    env = os.environ.copy()
    if getattr(sys, "frozen", False):
        ai_dir = os.path.join(os.path.dirname(sys.executable), "ai_packages")
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{ai_dir}{os.pathsep}{existing}" if existing else ai_dir

    cmd = [
        python, "-m", "demucs",
        "--two-stems", "vocals",
        "-n", model,
        "--device", device,
        *fmt_flag,
        *extra_flags,
        "-o", output_dir,
        input_path,
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

        stderr_lines: list[str] = []

        def _read_stderr() -> None:
            for line in proc.stderr:  # type: ignore[union-attr]
                l = line.rstrip()
                if l:
                    stderr_lines.append(l)

        t = threading.Thread(target=_read_stderr, daemon=True)
        t.start()

        last_pct = -1
        for line in proc.stdout:  # type: ignore[union-attr]
            if cancelled_cb and cancelled_cb():
                proc.kill()
                return {"success": False, "error": "Cancelled"}
            # demucs prints progress on stderr too; check both
            m = _PROGRESS_RE.search(line)
            if not m:
                m = _PROGRESS_RE.search(stderr_lines[-1]) if stderr_lines else None
            if m and progress_cb:
                pct = int(m.group(1))
                if pct != last_pct:
                    last_pct = pct
                    progress_cb(pct)

        proc.wait()
        t.join(timeout=5)

        # Also scan stderr for progress in case stdout was empty
        if last_pct < 0 and progress_cb:
            for line in stderr_lines:
                m = _PROGRESS_RE.search(line)
                if m:
                    pct = int(m.group(1))
                    if pct != last_pct:
                        last_pct = pct
                        progress_cb(pct)

        if proc.returncode != 0:
            detail = "\n".join(stderr_lines[-15:]) if stderr_lines else ""
            msg = f"demucs exited with code {proc.returncode}"
            if detail:
                msg += f"\n{detail}"
            return {"success": False, "error": msg}

        # Locate output files — demucs uses <model>/<stem_name>/vocals.{ext}
        stem_name = Path(input_path).stem
        out_dir = Path(output_dir) / model / stem_name

        def _find(name: str) -> Path | None:
            for ext in (".flac", ".mp3", ".wav"):
                p = out_dir / f"{name}{ext}"
                if p.exists():
                    return p
            # Fallback: recursive scan
            for ext in (".flac", ".mp3", ".wav"):
                hits = list(out_dir.parent.rglob(f"{name}{ext}")) if out_dir.parent.exists() else []
                if hits:
                    return hits[0]
            return None

        vocals = _find("vocals")
        no_vocals = _find("no_vocals")

        if not vocals or not no_vocals:
            return {"success": False, "error": f"Output not found at: {out_dir}"}

        return {
            "success": True,
            "device": device,
            "vocals_path": str(vocals),
            "accompaniment_path": str(no_vocals),
            "output_dir": str(vocals.parent),
        }

    except FileNotFoundError:
        return {"success": False, "error": "demucs not found. Install via the Install Model button."}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}
