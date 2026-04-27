"""Spatial manipulation — resize, crop, rotate, flip via FFmpeg."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from utils.ffmpeg import ffmpeg_path, ffprobe_path


def _flags() -> dict:
    return {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def get_media_dimensions(src: str) -> tuple[int, int] | None:
    """Return (width, height) of the first video stream via ffprobe, or None."""
    import json
    try:
        cmd = [
            ffprobe_path, "-v", "quiet", "-print_format", "json",
            "-show_streams", "-select_streams", "v:0", src,
        ]
        result = subprocess.run(cmd, check=True, capture_output=True, timeout=30, **_flags())
        streams = json.loads(result.stdout).get("streams", [])
        if streams:
            w = int(streams[0].get("width", 0))
            h = int(streams[0].get("height", 0))
            if w > 0 and h > 0:
                return w, h
    except Exception:
        pass
    return None


def resize_media(src: str, out_dir: str, width: int, height: int) -> dict:
    """Resize video/image to exact target resolution with letterboxing."""
    try:
        ext = os.path.splitext(src)[1].lower() or ".mp4"
        base = os.path.splitext(os.path.basename(src))[0]
        os.makedirs(out_dir, exist_ok=True)
        dest = os.path.join(out_dir, f"{base}_resized{ext}")
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
        )
        cmd = [ffmpeg_path, "-y", "-i", src, "-vf", vf, "-c:a", "copy", dest]
        subprocess.run(cmd, check=True, capture_output=True, timeout=7200, **_flags())
        return {"success": True, "file_path": dest}
    except subprocess.CalledProcessError as exc:
        return {"success": False, "error": exc.stderr.decode(errors="replace").strip()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def crop_media(src: str, out_dir: str, width: int, height: int, x: int, y: int) -> dict:
    """Crop video to rectangle starting at (x, y) with dimensions (width × height)."""
    dims = get_media_dimensions(src)
    if dims:
        vid_w, vid_h = dims
        x = max(0, min(x, vid_w - 1))
        y = max(0, min(y, vid_h - 1))
        width = max(1, min(width, vid_w - x))
        height = max(1, min(height, vid_h - y))
    try:
        ext = os.path.splitext(src)[1].lower() or ".mp4"
        base = os.path.splitext(os.path.basename(src))[0]
        os.makedirs(out_dir, exist_ok=True)
        dest = os.path.join(out_dir, f"{base}_cropped{ext}")
        vf = f"crop={width}:{height}:{x}:{y}"
        cmd = [ffmpeg_path, "-y", "-i", src, "-vf", vf, "-c:a", "copy", dest]
        subprocess.run(cmd, check=True, capture_output=True, timeout=7200, **_flags())
        return {"success": True, "file_path": dest}
    except subprocess.CalledProcessError as exc:
        return {"success": False, "error": exc.stderr.decode(errors="replace").strip()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def rotate_flip_chain(src: str, out_dir: str, ops: list[str]) -> dict:
    """Apply a sequence of rotate/flip operations in order."""
    _op_vf = {
        "cw90":   "transpose=1",
        "ccw90":  "transpose=2",
        "rot180": "vflip,hflip",
        "fliph":  "hflip",
        "flipv":  "vflip",
    }
    vf_parts = []
    for op in ops:
        v = _op_vf.get(op)
        if v:
            vf_parts.append(v)
    if not vf_parts:
        return {"success": False, "error": "No operations specified."}
    try:
        ext = os.path.splitext(src)[1].lower() or ".mp4"
        base = os.path.splitext(os.path.basename(src))[0]
        os.makedirs(out_dir, exist_ok=True)
        dest = os.path.join(out_dir, f"{base}_transformed{ext}")
        cmd = [ffmpeg_path, "-y", "-i", src, "-vf", ",".join(vf_parts), "-c:a", "copy", dest]
        subprocess.run(cmd, check=True, capture_output=True, timeout=7200, **_flags())
        return {"success": True, "file_path": dest}
    except subprocess.CalledProcessError as exc:
        return {"success": False, "error": exc.stderr.decode(errors="replace").strip()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def rotate_flip_media(src: str, out_dir: str, operation: str) -> dict:
    """Apply rotate/flip to video.

    operation: "cw90" | "ccw90" | "rot180" | "fliph" | "flipv"
    """
    _vf_map = {
        "cw90":   "transpose=1",
        "ccw90":  "transpose=2",
        "rot180": "transpose=2,transpose=2",
        "fliph":  "hflip",
        "flipv":  "vflip",
    }
    vf = _vf_map.get(operation)
    if not vf:
        return {"success": False, "error": f"Unknown operation: {operation}"}
    try:
        ext = os.path.splitext(src)[1].lower() or ".mp4"
        base = os.path.splitext(os.path.basename(src))[0]
        os.makedirs(out_dir, exist_ok=True)
        dest = os.path.join(out_dir, f"{base}_{operation}{ext}")
        cmd = [ffmpeg_path, "-y", "-i", src, "-vf", vf, "-c:a", "copy", dest]
        subprocess.run(cmd, check=True, capture_output=True, timeout=7200, **_flags())
        return {"success": True, "file_path": dest}
    except subprocess.CalledProcessError as exc:
        return {"success": False, "error": exc.stderr.decode(errors="replace").strip()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def extract_frame(src: str, time_sec: float = 1.0) -> str | None:
    """Extract one frame from *src* at *time_sec* as a temp PNG. Returns path or None."""
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp_path = tmp.name
        tmp.close()
        cmd = [
            ffmpeg_path, "-y", "-ss", str(time_sec), "-i", src,
            "-frames:v", "1", "-update", "1", tmp_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=30, **_flags())
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            return tmp_path
        return None
    except Exception:
        return None
