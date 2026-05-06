"""AI Image Upscaler — Real-ESRGAN x2/x4 with tiling.

Mirrors vocal_isolator's bundled-Python subprocess pattern: the heavy torch
import lives in a child process so the frozen GUI never pays its startup cost
and ABI mismatches stay isolated.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

# Real-ESRGAN x4plus weights — auto-downloaded by RealESRGANer on first run.
_WEIGHTS_URL = (
    "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/"
    "RealESRGAN_x4plus.pth"
)

_PROGRESS_RE = re.compile(r"TILE\s+(\d+)/(\d+)")


def _ai_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Videl", "ai_packages", "upscaler")


def _torch_host_dir() -> str:
    """Return the ai_packages dir that owns torch — currently vocal_isolator's."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Videl", "ai_packages", "vocal_isolator")


def torch_host_installed() -> bool:
    """True iff the component that provides torch (vocal_isolator) is installed."""
    try:
        from utils import model_manager
        return model_manager.is_installed("vocal_isolator")
    except Exception:
        return False


def _python_exe() -> str:
    try:
        from utils.bundled_runtime import bundled_python_path
        return bundled_python_path()
    except Exception:
        return sys.executable


_LAST_DETECT_DEBUG: str = ""


def last_detect_debug() -> str:
    return _LAST_DETECT_DEBUG


def detect_device() -> str:
    """Probe torch.cuda via the bundled Python (same approach as vocal_isolator)."""
    global _LAST_DETECT_DEBUG
    py = _python_exe()
    ai = _ai_dir()
    torch_host = _torch_host_dir()
    if not os.path.isdir(torch_host):
        _LAST_DETECT_DEBUG = f"torch host (vocal_isolator) missing: {torch_host}"
        return "cpu"
    # Order matters: torch_host first so torch resolves from there.
    code = (
        "import sys, traceback\n"
        f"sys.path.insert(0, r'{ai}')\n"
        f"sys.path.insert(0, r'{torch_host}')\n"
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
        creationflags = 0x08000000 if sys.platform == "win32" else 0
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


# Inline child-process script. Real-ESRGAN's RealESRGANer handles tiling and
# weight downloads. We monkey-patch basicsr's torchvision shim because
# basicsr 1.4.2 imports `torchvision.transforms.functional_tensor`, which was
# removed in torchvision 0.17+.
_CHILD_SCRIPT = r"""
import os, sys, argparse, traceback

ai_dir = sys.argv[1]
torch_host = sys.argv[2]
# torch_host first → torch/torchvision resolve from vocal_isolator's install.
sys.path.insert(0, ai_dir)
sys.path.insert(0, torch_host)

# basicsr shim: functional_tensor was merged into functional in tv 0.17.
try:
    import torchvision.transforms.functional_tensor  # noqa: F401
except ImportError:
    import types, torchvision.transforms.functional as _tvf
    _shim = types.ModuleType("torchvision.transforms.functional_tensor")
    _shim.rgb_to_grayscale = _tvf.rgb_to_grayscale
    sys.modules["torchvision.transforms.functional_tensor"] = _shim

import cv2
import torch
from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer

p = argparse.ArgumentParser()
p.add_argument("--input", required=True)
p.add_argument("--output", required=True)
p.add_argument("--scale", type=int, default=4)
p.add_argument("--tile", type=int, default=256)
p.add_argument("--device", default="cpu")
p.add_argument("--weights", required=True)
args = p.parse_args(sys.argv[3:])

img = cv2.imread(args.input, cv2.IMREAD_UNCHANGED)
if img is None:
    sys.stderr.write(f"Failed to read image: {args.input}\n")
    sys.exit(2)

model = RRDBNet(
    num_in_ch=3, num_out_ch=3,
    num_feat=64, num_block=23, num_grow_ch=32,
    scale=4,
)
upsampler = RealESRGANer(
    scale=4,
    model_path=args.weights,
    model=model,
    tile=args.tile,
    tile_pad=10,
    pre_pad=0,
    half=(args.device == "cuda"),
    device=torch.device(args.device),
)

# Emit pseudo-progress lines based on RealESRGANer's internal tile loop.
# We monkey-patch tile_process to surface "TILE i/N" markers.
_orig = upsampler.tile_process
def _patched():
    h, w = upsampler.img.shape[2], upsampler.img.shape[3]
    tiles_x = (w + args.tile - 1) // args.tile
    tiles_y = (h + args.tile - 1) // args.tile
    total = max(1, tiles_x * tiles_y)
    sys.stderr.write(f"TILES_TOTAL {total}\n"); sys.stderr.flush()
    # Run original — we still emit a single progress tick at start/end so the
    # GUI shows movement; per-tile hook would require deeper patching.
    sys.stderr.write(f"TILE 1/{total}\n"); sys.stderr.flush()
    _orig()
    sys.stderr.write(f"TILE {total}/{total}\n"); sys.stderr.flush()
upsampler.tile_process = _patched

try:
    out, _ = upsampler.enhance(img, outscale=args.scale)
except Exception as e:
    traceback.print_exc()
    sys.exit(3)

ok = cv2.imwrite(args.output, out)
sys.exit(0 if ok else 4)
"""


def upscale_image(
    input_path: str,
    output_path: str,
    scale: int = 4,
    tile: int = 256,
    progress_cb: Callable[[int], None] | None = None,
    cancelled_cb: Callable[[], bool] | None = None,
    device: str | None = None,
) -> dict:
    """Run Real-ESRGAN x{scale} upscaling.

    scale: 2 or 4
    tile: tile size in pixels (0 = no tiling, large = more VRAM)
    device: 'cpu' | 'cuda' | None (auto)
    """
    if device not in ("cpu", "cuda"):
        device = detect_device()
    if scale not in (2, 4):
        scale = 4
    if tile < 0:
        tile = 0

    python = _python_exe()
    ai_dir = _ai_dir()
    torch_host = _torch_host_dir()
    weights = os.path.join(ai_dir, "weights", "RealESRGAN_x4plus.pth")

    # Auto-download to local weights dir on first run via URL fallback.
    if not os.path.isfile(weights):
        os.makedirs(os.path.dirname(weights), exist_ok=True)
        weights_arg = _WEIGHTS_URL
    else:
        weights_arg = weights

    cmd = [
        python, "-c", _CHILD_SCRIPT, ai_dir, torch_host,
        "--input", input_path,
        "--output", output_path,
        "--scale", str(scale),
        "--tile", str(tile),
        "--device", device,
        "--weights", weights_arg,
    ]
    creationflags = 0x08000000 if sys.platform == "win32" else 0
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, creationflags=creationflags,
        )
        stderr_lines: list[str] = []
        last_pct = {"v": -1}

        def _emit(text: str) -> None:
            if not text:
                return
            stderr_lines.append(text)
            m = _PROGRESS_RE.search(text)
            if m and progress_cb:
                cur, total = int(m.group(1)), max(1, int(m.group(2)))
                pct = int(cur * 100 / total)
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
        t_err.start(); t_out.start()

        while proc.poll() is None:
            if cancelled_cb and cancelled_cb():
                proc.kill()
                return {"success": False, "error": "Cancelled"}
            try:
                proc.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                pass

        t_err.join(timeout=5); t_out.join(timeout=5)

        if proc.returncode != 0:
            detail = "\n".join(stderr_lines[-15:]) if stderr_lines else ""
            msg = f"upscaler exited with code {proc.returncode}"
            if detail:
                msg += f"\n{detail}"
            return {"success": False, "error": msg}

        if not os.path.isfile(output_path):
            return {"success": False, "error": f"Output not written: {output_path}"}

        return {
            "success": True,
            "device": device,
            "output_path": output_path,
            "scale": scale,
        }

    except FileNotFoundError:
        return {"success": False, "error": "Python runtime not found. Install via the Install Model button."}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}
