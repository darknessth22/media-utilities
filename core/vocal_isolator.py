"""AI Vocal Isolator — HTDemucs 2-stem separation."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from utils.paths import ai_packages_dir

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


def _ai_dir() -> str:
    """Return <user-data>/Videl/ai_packages/vocal_isolator (where demucs lives)."""
    return str(ai_packages_dir() / "vocal_isolator")


def _torch_runtime_dir() -> str:
    """Dir holding torch. model_manager's one-time migration lifts torch /
    torchaudio / numpy / nvidia-* out of vocal_isolator/ into the shared
    `torch_runtime/` component — so torch no longer lives in _ai_dir()."""
    return str(ai_packages_dir() / "torch_runtime")


def _python_exe() -> str:
    """Return the bundled embeddable Python (where AI components are installed against).

    Falls back to the running interpreter in dev mode.
    """
    try:
        from utils.bundled_runtime import bundled_python_path
        return bundled_python_path()
    except Exception:
        return sys.executable


_LAST_DETECT_DEBUG: str = ""


def last_detect_debug() -> str:
    """Diagnostic output from the most recent detect_device() call."""
    return _LAST_DETECT_DEBUG


def detect_device() -> str:
    """Probe torch via the bundled Python — avoids ABI mismatches with the frozen app.

    Embeddable Python ignores PYTHONPATH (isolated via python312._pth), so we
    inject the ai_packages dir through a `-c` bootstrap that mutates sys.path.
    Captures stderr/stdout into `last_detect_debug()` for diagnostics.
    """
    global _LAST_DETECT_DEBUG
    py = _python_exe()
    ai = _ai_dir()
    torch_dir = _torch_runtime_dir()
    if not os.path.isdir(torch_dir):
        _LAST_DETECT_DEBUG = f"torch runtime missing: {torch_dir}"
        return "cpu"
    # torch_dir inserted last → resolves first; torch lives there post-migration.
    code = (
        "import sys, traceback\n"
        f"sys.path.insert(0, r'{ai}')\n"
        f"sys.path.insert(0, r'{torch_dir}')\n"
        "try:\n"
        "    import torch\n"
        "    avail = torch.cuda.is_available()\n"
        "    info = (f'torch={torch.__version__} cuda_built={torch.version.cuda} '\n"
        "            f'is_available={avail} device_count={torch.cuda.device_count()}')\n"
        "    kernel_ok = False\n"
        "    if avail:\n"
        "        try:\n"
        "            cap = torch.cuda.get_device_capability(0)\n"
        "            info += f' name={torch.cuda.get_device_name(0)} cap=sm_{cap[0]}{cap[1]}'\n"
        "            # Touch a real kernel to catch 'no kernel image' (sm mismatch).\n"
        "            x = torch.zeros(1, device='cuda')\n"
        "            (x + 1).cpu()\n"
        "            kernel_ok = True\n"
        "        except Exception as e:\n"
        "            info += f' kernel_probe_failed={type(e).__name__}: {e}'\n"
        "    sys.stdout.write('cuda' if kernel_ok else 'cpu')\n"
        "    sys.stderr.write(info)\n"
        "except Exception:\n"
        "    sys.stdout.write('cpu')\n"
        "    sys.stderr.write(traceback.format_exc())\n"
    )
    try:
        creationflags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        r = subprocess.run(
            [py, "-c", code],
            capture_output=True, text=True, timeout=30,
            creationflags=creationflags,
        )
        out = (r.stdout or "").strip()
        _LAST_DETECT_DEBUG = (r.stderr or "").strip() or f"exit={r.returncode} stdout={out!r}"
        if out in ("cpu", "cuda"):
            return out
    except Exception as exc:
        _LAST_DETECT_DEBUG = f"subprocess error: {exc}"
    return "cpu"


def separate_vocals(
    input_path: str,
    output_dir: str,
    fmt: str = "wav",
    preset: str = "balanced",
    progress_cb: Callable[[int], None] | None = None,
    cancelled_cb: Callable[[], bool] | None = None,
    device: str | None = None,
) -> dict:
    """Run HTDemucs 2-stem separation.

    fmt: 'wav' | 'mp3' | 'flac'
    preset: 'fast' | 'balanced' | 'quality'
    device: 'cpu' | 'cuda' | None (auto via detect_device)
    Returns dict: success, vocals_path, accompaniment_path, device, output_dir.
    """
    if device not in ("cpu", "cuda"):
        device = detect_device()
    python = _python_exe()

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
    ai_dir = _ai_dir()

    # Embeddable Python ignores PYTHONPATH; bootstrap sys.path via -c then run
    # demucs as __main__ via runpy so its argparse sees the expected argv[0].
    demucs_args = [
        "--two-stems", "vocals",
        "-n", model,
        "--device", device,
        *fmt_flag,
        *extra_flags,
        "-o", output_dir,
        input_path,
    ]
    bootstrap = (
        "import sys, runpy;"
        f"sys.path.insert(0, r'{ai_dir}');"
        f"sys.path.insert(0, r'{_torch_runtime_dir()}');"
        f"sys.argv = ['demucs', *{demucs_args!r}];"
        "runpy.run_module('demucs', run_name='__main__', alter_sys=True)"
    )
    cmd = [python, "-c", bootstrap]

    creationflags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    try:
        # Force unbuffered stderr so tqdm progress (which uses \r) reaches us live.
        env.setdefault("PYTHONUNBUFFERED", "1")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            creationflags=creationflags,
        )

        stderr_lines: list[str] = []
        last_pct = {"v": -1}

        def _emit(text: str) -> None:
            if not text:
                return
            stderr_lines.append(text)
            m = _PROGRESS_RE.search(text)
            if m and progress_cb:
                pct = int(m.group(1))
                if pct != last_pct["v"]:
                    last_pct["v"] = pct
                    try:
                        progress_cb(pct)
                    except Exception:
                        pass

        def _pump(stream) -> None:
            buf = b""
            while True:
                chunk = stream.read(1)
                if not chunk:
                    if buf:
                        _emit(buf.decode("utf-8", errors="replace"))
                    return
                if chunk in (b"\r", b"\n"):
                    if buf:
                        _emit(buf.decode("utf-8", errors="replace"))
                        buf = b""
                else:
                    buf += chunk

        t_err = threading.Thread(target=_pump, args=(proc.stderr,), daemon=True)
        t_out = threading.Thread(target=_pump, args=(proc.stdout,), daemon=True)
        t_err.start()
        t_out.start()

        while proc.poll() is None:
            if cancelled_cb and cancelled_cb():
                proc.kill()
                return {"success": False, "error": "Cancelled"}
            try:
                proc.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                pass

        t_err.join(timeout=5)
        t_out.join(timeout=5)

        if proc.returncode != 0:
            from core.crash_log import record_crash
            record_crash("Vocal Isolator (Demucs)", "\n".join(stderr_lines),
                         cmd=cmd, returncode=proc.returncode)
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
