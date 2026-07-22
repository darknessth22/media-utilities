"""AI Video Upscaler — Real-ESRGAN per-frame upscaling with a resumable pipeline.

Pipeline (assembly line over subprocess + ffmpeg):
  1. Probe   — ffprobe reads fps, frame count, resolution, audio presence.
  2. Disk    — estimate temp footprint, abort early if the drive can't hold it.
  3. Teardown— ffmpeg extracts every frame to PNG in a job-keyed temp dir.
  4. Inference— ONE long-lived child process loads the model once and loops the
               frame folder. Per-process model load (not per-frame) is the
               difference between minutes and hours of pure import overhead.
  5. Reconstruct — ffmpeg stitches upscaled frames, muxes original audio,
               encodes with NVENC when available.

Resumable: the temp dir is keyed off (input, scale, model). Extracted frames
and finished output frames survive a crash/quit — a re-run skips both. Output
frames are written atomically (tmp + os.replace) so a kill never leaves a
half-written PNG that resume would trust.

V1 scope: per-frame image model (Real-ESRGAN). Temporal "shimmer" is possible
on noisy live-action footage — a video-native model (RealBasicVSR) is the V2
path. V1 also assumes constant frame rate; the reassembly framerate is the
true average (frame_count / duration) so audio length self-corrects.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from core.upscaler import _ai_dir, _python_exe, _torch_host_dir, detect_device
from utils.ffmpeg import detect_hw_encoders, ffmpeg_path, ffprobe_path

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".mpg", ".mpeg"}

# Per-frame upscaling models. "x4plus" = quality (RRDBNet, 64 MB).
# "general" = light/fast (SRVGGNetCompact, ~5 MB) — best "not heavy" pick.
MODELS = {
    "x4plus": {
        "weights": "RealESRGAN_x4plus.pth",
        "url": (
            "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/"
            "RealESRGAN_x4plus.pth"
        ),
    },
    "general": {
        "weights": "realesr-general-x4v3.pth",
        "url": (
            "https://github.com/xinntao/Real-ESRGAN/releases/download/"
            "v0.2.5.0/realesr-general-x4v3.pth"
        ),
    },
}

_WIN_FLAGS = 0x08000000 if sys.platform == "win32" else 0

_FRAME_RE = re.compile(r"FRAME\s+(\d+)/(\d+)")
_TOTAL_RE = re.compile(r"FRAMES_TOTAL\s+(\d+)")


# ── Probe ────────────────────────────────────────────────────────────────────

def probe_video(path: str) -> dict:
    """Return {fps, frame_count, duration, width, height, has_audio} for *path*.

    frame_count is an estimate (nb_frames is often "N/A"); the definitive count
    comes from the extracted PNG files later.
    """
    result = subprocess.run(
        [ffprobe_path, "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", path],
        capture_output=True, text=True, timeout=60, creationflags=_WIN_FLAGS,
    )
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError("No video stream found in file.")
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    duration = 0.0
    for src in (video.get("duration"), data.get("format", {}).get("duration")):
        try:
            duration = float(src)
            if duration > 0:
                break
        except (TypeError, ValueError):
            continue

    def _ratio(value: str | None) -> float:
        if not value or "/" not in value:
            return 0.0
        num, den = value.split("/", 1)
        try:
            return float(num) / float(den) if float(den) else 0.0
        except (ValueError, ZeroDivisionError):
            return 0.0

    fps = _ratio(video.get("avg_frame_rate")) or _ratio(video.get("r_frame_rate")) or 30.0

    frame_count = 0
    try:
        frame_count = int(video.get("nb_frames"))
    except (TypeError, ValueError):
        frame_count = 0
    if frame_count <= 0:
        frame_count = int(round(duration * fps))

    return {
        "fps": fps,
        "frame_count": max(1, frame_count),
        "duration": duration,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "has_audio": has_audio,
    }


def estimate_temp_bytes(width: int, height: int, frame_count: int, scale: int) -> int:
    """Rough PNG temp footprint: input frames + upscaled output frames.

    PNG roughly halves raw RGB; the 1.2 factor is headroom. Deliberately
    generous so the disk check errs toward aborting rather than filling C:.
    """
    raw_in = width * height * 3 * 0.5
    raw_out = (width * scale) * (height * scale) * 3 * 0.5
    return int((raw_in + raw_out) * frame_count * 1.2)


def check_disk(job_dir: Path, needed_bytes: int) -> tuple[bool, int, int]:
    """Return (ok, free_bytes, needed_bytes) for the drive holding *job_dir*."""
    probe = job_dir
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    free = shutil.disk_usage(str(probe)).free
    return free >= needed_bytes, free, needed_bytes


# ── Job dir / paths ──────────────────────────────────────────────────────────

def _job_dir(input_path: str, scale: int, model: str) -> Path:
    import tempfile
    key = f"{os.path.abspath(input_path)}|{scale}|{model}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / "videl_vupscale" / digest


def _weights_arg(model: str) -> str:
    """Local weights path if present, else the download URL (RealESRGANer fetches)."""
    info = MODELS.get(model, MODELS["x4plus"])
    local = Path(_ai_dir()) / "weights" / info["weights"]
    if local.is_file():
        return str(local)
    local.parent.mkdir(parents=True, exist_ok=True)
    return info["url"]


# ── Inference child process ──────────────────────────────────────────────────
# Long-lived: loads the model once, then loops the frame folder. Output frames
# are written atomically and existing ones are skipped, so the same process
# both runs fresh and resumes an interrupted run.
_CHILD_SCRIPT = r"""
import os, sys, argparse, glob, traceback

ai_dir, torch_host = sys.argv[1], sys.argv[2]
sys.path.insert(0, ai_dir)
sys.path.insert(0, torch_host)

# basicsr shim: functional_tensor was merged into functional in torchvision 0.17.
try:
    import torchvision.transforms.functional_tensor  # noqa: F401
except ImportError:
    import types, torchvision.transforms.functional as _tvf
    _shim = types.ModuleType("torchvision.transforms.functional_tensor")
    _shim.rgb_to_grayscale = _tvf.rgb_to_grayscale
    sys.modules["torchvision.transforms.functional_tensor"] = _shim

import cv2
import torch
from realesrgan import RealESRGANer

p = argparse.ArgumentParser()
p.add_argument("--in-dir", required=True)
p.add_argument("--out-dir", required=True)
p.add_argument("--scale", type=int, default=4)
p.add_argument("--tile", type=int, default=0)
p.add_argument("--device", default="cpu")
p.add_argument("--weights", required=True)
p.add_argument("--model", default="x4plus")
args = p.parse_args(sys.argv[3:])

if args.model == "general":
    from realesrgan.archs.srvgg_arch import SRVGGNetCompact
    net = SRVGGNetCompact(num_in_ch=3, num_out_ch=3, num_feat=64,
                          num_conv=32, upscale=4, act_type="prelu")
else:
    from basicsr.archs.rrdbnet_arch import RRDBNet
    net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64,
                  num_block=23, num_grow_ch=32, scale=4)

upsampler = RealESRGANer(
    scale=4, model_path=args.weights, model=net,
    tile=args.tile, tile_pad=10, pre_pad=0,
    half=(args.device == "cuda"), device=torch.device(args.device),
)

frames = sorted(glob.glob(os.path.join(args.in_dir, "frame_*.png")))
total = len(frames)
sys.stderr.write("FRAMES_TOTAL %d\n" % total); sys.stderr.flush()

for i, src in enumerate(frames, 1):
    name = os.path.basename(src)
    dst = os.path.join(args.out_dir, name)
    if os.path.isfile(dst):
        sys.stderr.write("FRAME %d/%d\n" % (i, total)); sys.stderr.flush()
        continue
    img = cv2.imread(src, cv2.IMREAD_COLOR)
    if img is None:
        sys.stderr.write("ERR cannot read %s\n" % src)
        sys.exit(2)
    try:
        out, _ = upsampler.enhance(img, outscale=args.scale)
    except RuntimeError as e:
        # OOM or kernel failure — surface clearly for the parent.
        sys.stderr.write("ERR enhance %s: %s\n" % (name, e))
        traceback.print_exc()
        sys.exit(3)
    # Encode to PNG in memory: cv2.imwrite picks the codec from the file
    # extension, and the atomic ".tmp" name has none. imencode takes the
    # extension explicitly, so the temp file can be named anything.
    ok_enc, buf = cv2.imencode(".png", out)
    if not ok_enc:
        sys.stderr.write("ERR cannot encode %s\n" % dst)
        sys.exit(4)
    tmp = dst + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(buf.tobytes())
    os.replace(tmp, dst)
    del out
    sys.stderr.write("FRAME %d/%d\n" % (i, total)); sys.stderr.flush()
    if args.device == "cuda" and i % 50 == 0:
        torch.cuda.empty_cache()

sys.exit(0)
"""


def _fmt_eta(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


# ── Main orchestrator ────────────────────────────────────────────────────────

def upscale_video(
    input_path: str,
    output_path: str,
    scale: int = 2,
    model: str = "x4plus",
    device: str | None = None,
    tile: int = 0,
    progress_cb: Callable[[int, str], None] | None = None,
    cancelled_cb: Callable[[], bool] | None = None,
) -> dict:
    """Upscale a video by *scale* (2 or 4) with Real-ESRGAN.

    Returns {success, output_path, device, scale, frame_count} or
    {success: False, error, resumable}.

    resumable=True means temp frames were kept; re-running with the same
    arguments continues where it stopped.
    """
    if scale not in (2, 4):
        scale = 2
    if model not in MODELS:
        model = "x4plus"
    if device not in ("cpu", "cuda"):
        device = detect_device()

    def _report(pct: int, msg: str) -> None:
        if progress_cb:
            try:
                progress_cb(max(0, min(100, pct)), msg)
            except Exception:
                pass

    def _cancelled() -> bool:
        return bool(cancelled_cb and cancelled_cb())

    if not os.path.isfile(input_path):
        return {"success": False, "error": f"Input not found: {input_path}"}

    # 1. Probe ----------------------------------------------------------------
    _report(0, "Analyzing video…")
    try:
        info = probe_video(input_path)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Could not read video: {exc}"}

    job_dir = _job_dir(input_path, scale, model)
    in_dir = job_dir / "in"
    out_dir = job_dir / "out"
    extracted_marker = job_dir / ".frames_extracted"

    # 2. Disk check -----------------------------------------------------------
    needed = estimate_temp_bytes(
        info["width"], info["height"], info["frame_count"], scale,
    )
    job_dir.mkdir(parents=True, exist_ok=True)
    ok, free, needed = check_disk(job_dir, needed)
    if not ok:
        def _gb(n: int) -> str:
            return f"{n / (1024 ** 3):.1f} GB"
        return {
            "success": False,
            "error": (
                f"Not enough disk space for temporary frames. "
                f"Need ~{_gb(needed)}, only {_gb(free)} free on the temp drive. "
                f"Free up space or upscale a shorter clip."
            ),
        }

    # 3. Teardown — extract frames (skipped on resume) ------------------------
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not extracted_marker.exists():
        _report(2, "Extracting frames…")
        for stale in in_dir.glob("frame_*.png"):
            stale.unlink()
        extract_cmd = [
            ffmpeg_path, "-y", "-i", input_path,
            "-qscale:v", "1", "-qmin", "1",
            os.path.join(str(in_dir), "frame_%08d.png"),
        ]
        try:
            proc = subprocess.run(
                extract_cmd, capture_output=True, text=True,
                timeout=10800, creationflags=_WIN_FLAGS,
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Frame extraction timed out.",
                    "resumable": True}
        if proc.returncode != 0:
            tail = "\n".join((proc.stderr or "").splitlines()[-12:])
            return {"success": False,
                    "error": f"Frame extraction failed:\n{tail}"}
        extracted_marker.write_text("ok", encoding="utf-8")

    if _cancelled():
        return {"success": False, "error": "Cancelled", "resumable": True}

    frame_files = sorted(in_dir.glob("frame_*.png"))
    frame_count = len(frame_files)
    if frame_count == 0:
        return {"success": False, "error": "No frames were extracted."}

    # Clear any leftover .tmp from a previous kill mid-write.
    for tmp in out_dir.glob("frame_*.png.tmp"):
        tmp.unlink()

    # 4. Inference — one persistent child process -----------------------------
    already = len(list(out_dir.glob("frame_*.png")))
    if already:
        _report(5, f"Resuming at frame {already + 1}/{frame_count}…")
    else:
        _report(5, "Upscaling frames…")

    cmd = [
        _python_exe(), "-c", _CHILD_SCRIPT, _ai_dir(), _torch_host_dir(),
        "--in-dir", str(in_dir),
        "--out-dir", str(out_dir),
        "--scale", str(scale),
        "--tile", str(tile),
        "--device", device,
        "--weights", _weights_arg(model),
        "--model", model,
    ]
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    stderr_tail: list[str] = []
    state = {"done": 0, "total": frame_count, "start": 0.0, "first_at": 0.0}

    def _on_line(text: str) -> None:
        if not text:
            return
        m = _FRAME_RE.search(text)
        if m:
            done = int(m.group(1))
            total = max(1, int(m.group(2)))
            state["done"] = done
            state["total"] = total
            # Anchor ETA on the first *computed* frame so resumed/skipped
            # frames don't poison the rate estimate.
            if state["first_at"] == 0.0 and done > already:
                state["first_at"] = time.time()
                state["first_idx"] = done
            pct = 5 + int(done * 88 / total)  # inference occupies 5–93%
            msg = f"Frame {done}/{total}"
            if state["first_at"] and done > state.get("first_idx", done):
                elapsed = time.time() - state["first_at"]
                per = elapsed / (done - state["first_idx"])
                eta = per * (total - done)
                msg += f"  ·  ETA {_fmt_eta(eta)}"
            _report(pct, msg)
            return
        if _TOTAL_RE.search(text):
            return
        stderr_tail.append(text)
        if len(stderr_tail) > 40:
            del stderr_tail[:-40]

    def _pump(stream) -> None:
        buf = b""
        while True:
            chunk = stream.read(1)
            if not chunk:
                if buf:
                    _on_line(buf.decode("utf-8", errors="replace"))
                return
            if chunk in (b"\r", b"\n"):
                if buf:
                    _on_line(buf.decode("utf-8", errors="replace"))
                    buf = b""
            else:
                buf += chunk

    try:
        child = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, creationflags=_WIN_FLAGS,
        )
    except FileNotFoundError:
        return {"success": False,
                "error": "Python runtime not found. Install the upscaler model first."}

    t_err = threading.Thread(target=_pump, args=(child.stderr,), daemon=True)
    t_out = threading.Thread(target=_pump, args=(child.stdout,), daemon=True)
    t_err.start(); t_out.start()

    while child.poll() is None:
        if _cancelled():
            child.kill()
            return {"success": False, "error": "Cancelled", "resumable": True}
        try:
            child.wait(timeout=0.3)
        except subprocess.TimeoutExpired:
            pass
    t_err.join(timeout=5); t_out.join(timeout=5)

    if child.returncode != 0:
        from core.crash_log import record_crash
        record_crash("AI Video Upscaler (Real-ESRGAN)", "\n".join(stderr_tail),
                     cmd=cmd, returncode=child.returncode)
        detail = "\n".join(stderr_tail[-12:])
        return {
            "success": False,
            "error": f"Upscaling stopped (exit {child.returncode}).\n{detail}",
            "resumable": True,
        }

    done = len(list(out_dir.glob("frame_*.png")))
    if done < frame_count:
        return {
            "success": False,
            "error": f"Only {done}/{frame_count} frames upscaled.",
            "resumable": True,
        }

    if _cancelled():
        return {"success": False, "error": "Cancelled", "resumable": True}

    # 5. Reconstruct — stitch frames, mux audio, encode -----------------------
    _report(94, "Encoding final video…")
    # True average fps self-corrects total length to the audio track.
    out_fps = (frame_count / info["duration"]) if info["duration"] > 0 else info["fps"]
    out_fps = max(1.0, out_fps)

    hw = detect_hw_encoders()
    if "nvidia" in hw:
        vcodec = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19"]
    elif "amd" in hw:
        vcodec = ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "20", "-qp_p", "20"]
    else:
        vcodec = ["-c:v", "libx264", "-preset", "medium", "-crf", "18"]
    is_hw_codec = vcodec[1] != "libx264"

    def _build_encode_cmd(codec_args: list[str]) -> list[str]:
        return [
            ffmpeg_path, "-y",
            "-framerate", f"{out_fps:.6f}",
            "-i", os.path.join(str(out_dir), "frame_%08d.png"),
            "-i", input_path,
            "-map", "0:v:0", "-map", "1:a?",
            *codec_args,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path,
        ]

    def _run_encode(codec_args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            _build_encode_cmd(codec_args), capture_output=True, text=True,
            timeout=10800, creationflags=_WIN_FLAGS,
        )

    try:
        enc = _run_encode(vcodec)
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Final encode timed out.", "resumable": True}

    # detect_hw_encoders() only checks that ffmpeg was BUILT with nvenc/amf
    # support — it can't tell whether the GPU/driver can actually open an
    # encoder session right now. "No capable devices found" is often
    # TRANSIENT: the NVENC session slot was still held by the AI-upscale
    # stage's own CUDA subprocess a moment earlier, or another app briefly
    # had the encoder open. Retry the SAME hardware codec once after a short
    # delay before giving up on it — most transient failures clear by then.
    if is_hw_codec and (enc.returncode != 0 or not os.path.isfile(output_path)):
        _report(94, "Hardware encoder busy — retrying…")
        time.sleep(2.0)
        try:
            enc = _run_encode(vcodec)
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Final encode timed out.", "resumable": True}

    # Only fall back to the CPU encoder if the hardware retry ALSO failed —
    # keeps NVIDIA/AMD as the actual output whenever the hardware path is
    # genuinely usable, and CPU is a last resort, not the default outcome.
    if is_hw_codec and (enc.returncode != 0 or not os.path.isfile(output_path)):
        _report(94, "Hardware encoder unavailable — falling back to CPU encoder…")
        try:
            enc = _run_encode(["-c:v", "libx264", "-preset", "medium", "-crf", "18"])
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Final encode timed out.", "resumable": True}

    if enc.returncode != 0 or not os.path.isfile(output_path):
        tail = "\n".join((enc.stderr or "").splitlines()[-12:])
        return {"success": False, "error": f"Final encode failed:\n{tail}",
                "resumable": True}

    # 6. Cleanup — only on full success; resume needs the temp dir otherwise.
    _report(99, "Cleaning up…")
    shutil.rmtree(job_dir, ignore_errors=True)

    _report(100, "Done")
    return {
        "success": True,
        "output_path": output_path,
        "device": device,
        "scale": scale,
        "frame_count": frame_count,
    }
