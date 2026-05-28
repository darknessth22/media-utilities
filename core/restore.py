"""AI Photo Restore — chained Colorize → Face Restore → Upscale pipeline.

Same subprocess pattern as core/upscaler.py: heavy torch import lives in a child
process so the frozen GUI never pays its startup cost and ABI mismatches stay
isolated. The child script loads each model sequentially with strict VRAM
unload (`del model; gc.collect(); torch.cuda.empty_cache()`) between stages so
mid-range GPUs (8 GB) survive all three stages on a single image.

Stages:
  0. Heal        — edge-preserving smoothing + multi-orientation morphological
                   scratch detection + cv2.inpaint (NS). Runs first so scratches
                   don't get amplified into colour speckle.
  1. Colorize    — DDColor (ICCV 2023) via ONNX runtime (top quality); falls
                   back to OpenCV Zhang 2016 if onnxruntime missing or ONNX
                   download fails. Plus gray-world WB + HSV sat tune.
  2. Face restore — CodeFormer (sczhou) via codeformer-pip vendored modules.

Upscaling is intentionally NOT here — Videl has a dedicated AI Upscaler tab
([gui/tabs/upscaler_section.py]). Chain the two manually: restore → upscale.

Each stage emits "STAGE <n>/<total> <label>" to stderr; parent maps to (pct,msg).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from utils.paths import ai_packages_dir

# Toggle keys accepted by run_restore.
STAGE_KEYS = ("colorize", "restore_faces", "heal")

_PROGRESS_RE = re.compile(r"STAGE\s+(\d+)/(\d+)\s+(.+)")


def _ai_dir() -> str:
    return str(ai_packages_dir() / "photo_restore")


def _upscaler_dir() -> str:
    return str(ai_packages_dir() / "upscaler")


def _torch_host_dir() -> str:
    return str(ai_packages_dir() / "torch_runtime")


def photo_restore_installed() -> bool:
    try:
        from utils import model_manager
        return model_manager.is_installed("photo_restore")
    except Exception:
        return False


def _python_exe() -> str:
    try:
        from utils.bundled_runtime import bundled_python_path
        return bundled_python_path()
    except Exception:
        return sys.executable


def _weights_dir() -> str:
    d = os.path.join(_ai_dir(), "weights")
    os.makedirs(d, exist_ok=True)
    return d


# Weight URLs — downloaded on first run by the child process.
_WEIGHTS = {
    "codeformer": (
        "codeformer.pth",
        "https://github.com/sczhou/CodeFormer/releases/download/v0.1.0/codeformer.pth",
    ),
    # OpenCV Zhang 2016 colorization — Caffe model + cluster centres.
    "colorize_prototxt": (
        "colorization_deploy_v2.prototxt",
        "https://raw.githubusercontent.com/richzhang/colorization/caffe/colorization/models/colorization_deploy_v2.prototxt",
    ),
    "colorize_caffemodel": (
        "colorization_release_v2.caffemodel",
        "http://eecs.berkeley.edu/~rich.zhang/projects/2016_colorization/files/demo_v2/colorization_release_v2.caffemodel",
    ),
    "colorize_pts": (
        "pts_in_hull.npy",
        "https://raw.githubusercontent.com/richzhang/colorization/caffe/colorization/resources/pts_in_hull.npy",
    ),
    "realesrgan": (
        "RealESRGAN_x4plus.pth",
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
    ),
    # Face detection (used by CodeFormer's facelib via facexlib).
    "detection_retinaface": (
        "detection_Resnet50_Final.pth",
        "https://github.com/xinntao/facexlib/releases/download/v0.1.0/detection_Resnet50_Final.pth",
    ),
    "parsing_parsenet": (
        "parsing_parsenet.pth",
        "https://github.com/xinntao/facexlib/releases/download/v0.2.2/parsing_parsenet.pth",
    ),
}


# ---------------- child-process script ----------------
#
# Layout: parent sends ai_dir, torch_host, upscaler_dir, weights_dir, then args.
# torch_host first on sys.path so torch resolves from the shared runtime.

_CHILD_SCRIPT = r"""
import os, sys, argparse, gc, json, traceback, urllib.request, time

ai_dir = sys.argv[1]
torch_host = sys.argv[2]
upscaler_dir = sys.argv[3]
weights_dir = sys.argv[4]

# torch_host first → torch / torchvision resolve from shared runtime.
sys.path.insert(0, ai_dir)
sys.path.insert(0, upscaler_dir)
sys.path.insert(0, torch_host)

# basicsr shim: functional_tensor merged into functional in torchvision 0.17+.
try:
    import torchvision.transforms.functional_tensor  # noqa: F401
except ImportError:
    import types, torchvision.transforms.functional as _tvf
    _shim = types.ModuleType("torchvision.transforms.functional_tensor")
    _shim.rgb_to_grayscale = _tvf.rgb_to_grayscale
    sys.modules["torchvision.transforms.functional_tensor"] = _shim

import numpy as np
import cv2
import torch

p = argparse.ArgumentParser()
p.add_argument("--input", required=True)
p.add_argument("--output", required=True)
p.add_argument("--colorize", action="store_true")
p.add_argument("--restore-faces", action="store_true")
p.add_argument("--heal", action="store_true")
# Non-local-means denoise strength. 0 disabled; 3-7 mild grain; 10 typical
# scratch/crease pass; 15-20 aggressive (may flatten texture).
p.add_argument("--heal-strength", type=int, default=10)
p.add_argument("--device", default="cpu")
p.add_argument("--codeformer-weight", type=float, default=0.7)
# Zhang 2016 is muted by design; boost ab saturation in HSV after re-merge.
# 1.0 = raw network output (oil-paint look), 1.3 = punchier, 1.6 = vivid.
p.add_argument("--colorize-saturation", type=float, default=1.15)
# Gray-world white balance after colorize — kills Zhang 2016's yellow/sepia
# cast on skin and skies. 1.0 = full WB applied; 0.0 = off; 0.5 = half-strength.
p.add_argument("--colorize-wb", type=float, default=0.85)
# Larger inference size = sharper ab field. 224 is paper default; 384 is
# the sweet spot before quality plateaus.
p.add_argument("--colorize-size", type=int, default=512)
# DDColor variant. "natural" (= ddcolor_modelscope, photo-realistic) vs
# "vivid" (= ddcolor_artistic, bolder/cinematic for portraits).
p.add_argument("--colorize-style", choices=("natural", "vivid"), default="natural")
args = p.parse_args(sys.argv[5:])

device = torch.device(args.device)
use_half = (args.device == "cuda")

# Stage count = number of enabled toggles (min 1 so progress always advances).
stages_enabled = [k for k, v in (
    ("Healing scratches", args.heal),
    ("Colorizing",  args.colorize),
    ("Restoring faces", args.restore_faces),
) if v]
total = max(1, len(stages_enabled))
stage_idx = 0

def emit(label):
    global stage_idx
    stage_idx += 1
    sys.stderr.write(f"STAGE {stage_idx}/{total} {label}\n")
    sys.stderr.flush()

def _download(url, dst):
    # url may be a single str or a list of mirror URLs; first that works wins.
    # Sets a browser User-Agent (eecs.berkeley.edu 403s the default Python-urllib).
    if os.path.isfile(dst):
        return dst
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".part"
    urls = url if isinstance(url, (list, tuple)) else [url]
    last_err = None
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Videl/4.2"
            })
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            os.replace(tmp, dst)
            return dst
        except Exception as e:
            last_err = e
            try:
                os.remove(tmp)
            except OSError:
                pass
            sys.stderr.write(f"download failed {u}: {e}\n")
            continue
    raise last_err if last_err else RuntimeError(f"All mirrors failed for {dst}")

def _unload(*objs):
    for o in objs:
        try:
            del o
        except Exception:
            pass
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()

# Read source as BGR uint8 (cv2 convention used throughout).
img = cv2.imread(args.input, cv2.IMREAD_COLOR)
if img is None:
    sys.stderr.write(f"Failed to read image: {args.input}\n")
    sys.exit(2)

# ---------------- Stage 0: Heal — Microsoft BOPB (CVPR 2020) ----------------
# Uses zeroscratches (pip wrapper around Bringing-Old-Photos-Back-to-Life).
# Two neural networks: a scratch-detection UNet + a Pix2PixHD restoration
# network. Knows what's behind a crease because it was trained on synthetic
# damage applied to clean photos. Quality leap vs heuristic morphology.
#
# Models (~600 MB) auto-download from HuggingFace on first run; cached in
# our weights dir so subsequent runs are offline.
# Slider value -> blend with original: 0% slider value = 30% blend, max = 100%.
if args.heal:
    emit("Healing scratches")
    try:
        # Pin HuggingFace cache to our weights dir for offline reuse and to
        # avoid polluting %USERPROFILE%/.cache.
        os.environ["HF_HOME"] = weights_dir
        os.environ["HUGGINGFACE_HUB_CACHE"] = weights_dir
        os.environ["TRANSFORMERS_CACHE"] = weights_dir

        from zeroscratches import EraseScratches
        from PIL import Image

        # BGR ndarray -> PIL RGB.
        pil_in = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

        eraser = EraseScratches()
        pil_out = eraser.erase(pil_in)  # PIL RGB

        restored = cv2.cvtColor(np.array(pil_out), cv2.COLOR_RGB2BGR)
        # BOPB sometimes resizes; resize back to source dims.
        if restored.shape[:2] != img.shape[:2]:
            restored = cv2.resize(
                restored, (img.shape[1], img.shape[0]),
                interpolation=cv2.INTER_LANCZOS4,
            )

        # Slider 3..25 -> base blend weight 0.30..1.00 for non-face area.
        s = max(3, min(25, int(args.heal_strength)))
        base_blend = 0.30 + (s - 3) / 22.0 * 0.70

        # Face-aware blending — BOPB's Pix2PixHD restorer hallucinates over
        # eyes when scratches are nearby. Detect face bbox -> within bbox
        # detect eyes -> protect ONLY eye regions (small soft ellipses).
        # Rest of face still receives full BOPB cleanup so cheek / forehead
        # creases get removed. Stage 2 (CodeFormer) polishes any leftover
        # face damage.
        Hh, Ww = img.shape[:2]
        # weight = per-pixel BOPB strength (1.0 = full BOPB, lower = more original)
        weight = np.full((Hh, Ww), base_blend, dtype=np.float32)
        try:
            haarcasc = cv2.data.haarcascades
            face_cascade = cv2.CascadeClassifier(haarcasc + "haarcascade_frontalface_default.xml")
            eye_cascade  = cv2.CascadeClassifier(haarcasc + "haarcascade_eye.xml")
            det_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(
                det_gray, scaleFactor=1.1, minNeighbors=4,
                minSize=(max(30, Hh // 12), max(30, Hh // 12)),
            )
            EYE_PROTECT = 0.85  # 85% original within the small eye ellipse
            total_eyes = 0
            # Canonical eye positions inside a face bbox — robust against
            # Haar's misses on damaged eyes (the exact case we care about).
            # (cx_rel, cy_rel, ax_rel, ay_rel) — fractions of (fw, fh).
            canonical = [
                (0.32, 0.36, 0.13, 0.08),  # left eye (viewer's left)
                (0.68, 0.36, 0.13, 0.08),  # right eye
            ]
            for (fx, fy, fw, fh) in faces:
                # 1) ALWAYS place canonical protect ellipses — guaranteed
                # coverage of both eye sockets even if the photo is heavily
                # damaged and Haar finds nothing.
                eye_regions = []
                for cxr, cyr, axr, ayr in canonical:
                    cx = fx + int(fw * cxr)
                    cy = fy + int(fh * cyr)
                    ax = max(10, int(fw * axr))
                    ay = max(8,  int(fh * ayr))
                    eye_regions.append((cx, cy, ax, ay))

                # 2) Try Haar in upper-60% of bbox — adds refinement when
                # the image is clear enough for it to work.
                roi_h = int(fh * 0.6)
                roi = det_gray[fy:fy + roi_h, fx:fx + fw]
                if roi.size > 0:
                    min_eye = max(10, fw // 14)
                    haar = eye_cascade.detectMultiScale(
                        roi, scaleFactor=1.1, minNeighbors=4,
                        minSize=(min_eye, min_eye),
                    )
                    for (ex, ey, ew, eh) in haar:
                        cx = fx + ex + ew // 2
                        cy = fy + ey + eh // 2
                        ax = max(10, int(ew * 0.85))
                        ay = max(8,  int(eh * 0.80))
                        eye_regions.append((cx, cy, ax, ay))

                # 3) Apply protection — soft Gaussian-feathered ellipse per region.
                for (cx, cy, ax, ay) in eye_regions:
                    ell = np.zeros((Hh, Ww), dtype=np.float32)
                    cv2.ellipse(ell, (cx, cy), (ax, ay), 0, 0, 360, 1.0, -1)
                    feather = max(15, (min(ax, ay)) | 1)
                    ell = cv2.GaussianBlur(ell, (feather, feather), 0)
                    weight = np.minimum(weight, base_blend - ell * EYE_PROTECT * base_blend)
                    total_eyes += 1
            weight = np.clip(weight, 0.05, 1.0)
            sys.stderr.write(
                f"heal: protected {total_eyes} eye region(s) across {len(faces)} face(s) "
                f"at {int(EYE_PROTECT*100)}% (2 canonical per face + Haar refinements)\n"
            )
        except Exception as fe:
            sys.stderr.write(f"heal: face blend skipped ({fe})\n")

        # Apply per-pixel blend.
        w3 = weight[:, :, None]
        out_f = w3 * restored.astype(np.float32) + (1.0 - w3) * img.astype(np.float32)
        img = np.clip(out_f, 0, 255).astype(np.uint8)
        _unload(eraser)
    except ImportError as ie:
        sys.stderr.write(
            f"heal: zeroscratches not installed ({ie}); skipping stage.\n"
        )
    except Exception:
        traceback.print_exc()
        sys.exit(13)

# ---------------- Stage 1: Colorize ----------------
# Primary: DDColor (ICCV 2023) via ONNX runtime — top-quality colorizer.
# Fallback: Zhang 2016 Caffe via cv2.dnn (no extra pip dep) if onnxruntime
# missing or ONNX weights download fails.
def _colorize_ddcolor(img_bgr, style="natural", enc_size=512):
    # Returns colorized BGR uint8, or raises (caller falls back).
    # Matches the official DDColor inference pipeline (piddnad/DDColor
    # image_color_pipeline.py) — CRITICAL: float Lab throughout. Mixing
    # uint8 Lab (L in [0,255]) with float ab from the network yields a
    # cyan cast because the LAB2BGR conversion expects L in [0,100] for
    # float inputs.
    # style: "natural" = ddcolor_modelscope (photo-realistic, default);
    #        "vivid"   = ddcolor_artistic (bolder, cinematic on portraits).
    import onnxruntime as ort
    if style == "vivid":
        mirrors = [
            "https://huggingface.co/wanesoft/faceswap_pack/resolve/main/ddcolor_artistic.onnx",
            "https://huggingface.co/crj/dl-ws/resolve/main/ddcolor_artistic.onnx",
        ]
        local_name = "ddcolor_artistic.onnx"
    else:
        mirrors = [
            "https://huggingface.co/wanesoft/faceswap_pack/resolve/4dbed346e89a445931da6484452f773c7d8c19b8/ddcolor.onnx",
            "https://huggingface.co/crj/dl-ws/resolve/main/ddcolor.onnx",
        ]
        local_name = "ddcolor.onnx"
    onnx_path = _download(mirrors, os.path.join(weights_dir, local_name))

    sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name
    H, W = img_bgr.shape[:2]
    enc = max(256, int(enc_size) // 8 * 8)  # multiple of 8 for ConvNeXt stride

    # 1) Source -> float [0,1] BGR, extract float Lab L (range [0,100]).
    img_f = img_bgr.astype("float32") / 255.0
    orig_l = cv2.cvtColor(img_f, cv2.COLOR_BGR2LAB)[:, :, :1]  # (H,W,1) L in [0,100]

    # 2) Build the network input. DDColor expects a grayscale-as-RGB tensor:
    # build it by zeroing the ab of the resized image's Lab then converting
    # LAB->RGB (note RGB, not BGR). This matches the official preprocess.
    img_rs = cv2.resize(img_f, (enc, enc))
    img_l = cv2.cvtColor(img_rs, cv2.COLOR_BGR2LAB)[:, :, :1]
    gray_lab = np.concatenate([img_l, np.zeros_like(img_l), np.zeros_like(img_l)], axis=-1)
    gray_rgb = cv2.cvtColor(gray_lab, cv2.COLOR_LAB2RGB)  # (enc, enc, 3) float [0,1]
    inp = gray_rgb.transpose(2, 0, 1)[None].astype("float32")  # (1,3,enc,enc)

    # 3) Run network. Output is raw Lab ab (float, ~[-100, 100]).
    ab = sess.run(None, {in_name: inp})[0]  # (1, 2, enc, enc)
    ab = ab[0].transpose(1, 2, 0).astype("float32")
    ab = cv2.resize(ab, (W, H), interpolation=cv2.INTER_CUBIC)

    # 4) Concat float source L with float predicted ab, convert Lab->BGR.
    out_lab = np.concatenate([orig_l, ab], axis=-1).astype("float32")
    out_bgr = cv2.cvtColor(out_lab, cv2.COLOR_LAB2BGR)  # float [0,1]
    return (np.clip(out_bgr, 0, 1) * 255.0).round().astype("uint8")


def _colorize_zhang(img_bgr):
    # Fallback: OpenCV Zhang 2016 Caffe via cv2.dnn.
    proto = _download(
        "https://raw.githubusercontent.com/richzhang/colorization/caffe/colorization/models/colorization_deploy_v2.prototxt",
        os.path.join(weights_dir, "colorization_deploy_v2.prototxt"),
    )
    model = _download([
        "https://huggingface.co/spaces/viveknarayan/Image_Colorization/resolve/main/colorization_release_v2.caffemodel",
        "https://huggingface.co/spaces/BilalSardar/Black-N-White-To-Color/resolve/main/colorization_release_v2.caffemodel",
        "https://github.com/dath1s/colorizor/raw/main/colorization_release_v2.caffemodel",
    ], os.path.join(weights_dir, "colorization_release_v2.caffemodel"))
    pts_path = _download(
        "https://raw.githubusercontent.com/richzhang/colorization/caffe/colorization/resources/pts_in_hull.npy",
        os.path.join(weights_dir, "pts_in_hull.npy"),
    )
    net = cv2.dnn.readNetFromCaffe(proto, model)
    pts = np.load(pts_path).transpose().reshape(2, 313, 1, 1).astype("float32")
    net.getLayer(net.getLayerId("class8_ab")).blobs = [pts]
    net.getLayer(net.getLayerId("conv8_313_rh")).blobs = [
        np.full([1, 313], 2.606, dtype="float32")
    ]
    h, w = img_bgr.shape[:2]
    scaled = img_bgr.astype("float32") / 255.0
    lab = cv2.cvtColor(scaled, cv2.COLOR_BGR2LAB)
    L_orig = lab[:, :, 0]
    infer = max(64, int(args.colorize_size))
    L_rs = cv2.resize(L_orig, (infer, infer)) - 50
    net.setInput(cv2.dnn.blobFromImage(L_rs))
    ab = net.forward()[0, :, :, :].transpose((1, 2, 0))
    ab = cv2.resize(ab, (w, h))
    out_lab = np.concatenate((L_orig[:, :, np.newaxis], ab), axis=2)
    out_bgr = cv2.cvtColor(out_lab, cv2.COLOR_LAB2BGR)
    return (np.clip(out_bgr, 0, 1) * 255).astype("uint8")


if args.colorize:
    emit("Colorizing")
    try:
        out_u8 = None
        # Primary path: DDColor ONNX.
        try:
            out_u8 = _colorize_ddcolor(
                img,
                style=args.colorize_style,
                enc_size=int(args.colorize_size),
            )
        except Exception as e:
            sys.stderr.write(f"DDColor failed, falling back to Zhang 2016: {e}\n")
            out_u8 = None
        if out_u8 is None:
            out_u8 = _colorize_zhang(img)

        # Gray-world white balance — kills lingering yellow/sepia bias.
        wb = float(args.colorize_wb)
        if wb > 0.0:
            f = out_u8.astype("float32")
            avg = f.reshape(-1, 3).mean(axis=0)
            target = avg.mean()
            scale = target / np.maximum(avg, 1e-6)
            scale = 1.0 + (scale - 1.0) * wb
            out_u8 = np.clip(f * scale, 0, 255).astype("uint8")

        # Optional HSV saturation tune (DDColor is already well-saturated,
        # keep close to 1.0).
        sat_mul = float(args.colorize_saturation)
        if sat_mul != 1.0:
            hsv = cv2.cvtColor(out_u8, cv2.COLOR_BGR2HSV).astype("float32")
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * sat_mul, 0, 255)
            out_u8 = cv2.cvtColor(hsv.astype("uint8"), cv2.COLOR_HSV2BGR)
        img = out_u8
    except Exception:
        traceback.print_exc()
        sys.exit(10)

# ---------------- Stage 2: Face restoration (CodeFormer) ----------------
# Bypass codeformer.app.inference_app — it expects a path string (not ndarray)
# and writes to a hardcoded `results/` folder. We drive the CodeFormer arch
# directly through codeformer-pip's vendored basicsr + facelib so we keep our
# ndarray in/out contract and put the output where the caller asked.
if args.restore_faces:
    emit("Restoring faces")
    try:
        # Importing this module runs ARCH_REGISTRY.register("CodeFormer").
        import codeformer.basicsr.archs.codeformer_arch  # noqa: F401
        from codeformer.basicsr.utils.registry import ARCH_REGISTRY
        try:
            from codeformer.facelib.utils.face_restoration_helper import FaceRestoreHelper
        except ImportError:
            # Older codeformer-pip layouts ship facelib at top level or via facexlib.
            from facexlib.utils.face_restoration_helper import FaceRestoreHelper

        cf_weights = _download(
            "https://github.com/sczhou/CodeFormer/releases/download/v0.1.0/codeformer.pth",
            os.path.join(weights_dir, "codeformer.pth"),
        )
        net = ARCH_REGISTRY.get("CodeFormer")(
            dim_embd=512, codebook_size=1024, n_head=8, n_layers=9,
            connect_list=["32", "64", "128", "256"],
        ).to(device)
        # torch >= 2.4 defaults weights_only=True which rejects pickled ckpts.
        ck = torch.load(cf_weights, map_location=device, weights_only=False)
        net.load_state_dict(ck["params_ema"] if "params_ema" in ck else ck)
        net.eval()
        # NOTE: do NOT call net.half() — codeformer-pip's vendored vqgan_arch
        # does `min_encodings.float() @ self.embedding.weight` in the codebook
        # lookup, which raises "mat1 and mat2 dtype mismatch" when the embedding
        # is fp16 but min_encodings is fp32. CodeFormer is small (~360 MB) so
        # full-precision on CUDA is still <1s/face.
        cf_half = False

        helper = FaceRestoreHelper(
            upscale_factor=1, face_size=512, crop_ratio=(1, 1),
            det_model="retinaface_resnet50", save_ext="png",
            use_parse=True, device=device,
        )
        helper.read_image(img)
        helper.get_face_landmarks_5(only_center_face=False, resize=640, eye_dist_threshold=5)
        helper.align_warp_face()

        for cropped in helper.cropped_faces:
            t = torch.from_numpy(cropped.astype("float32") / 255.).permute(2, 0, 1).unsqueeze(0)
            t = (t - 0.5) / 0.5
            t = t.to(device)
            if cf_half:
                t = t.half()
            with torch.no_grad():
                result = net(t, w=args.codeformer_weight, adain=True)
            # codeformer-pip's forward returns (out, logits, lq_feat) — `out`
            # itself is 4D (B, C, H, W). Older versions returned a 3D tensor
            # directly. Handle both shapes.
            out = result[0] if isinstance(result, (tuple, list)) else result
            if out.dim() == 4:
                out = out[0]
            out = (out.clamp(-1, 1).float() + 1) / 2
            out = (out.permute(1, 2, 0).cpu().numpy() * 255).round().astype("uint8")
            helper.add_restored_face(out)

        helper.get_inverse_affine(None)
        img = helper.paste_faces_to_input_image(upsample_img=img)
        _unload(net, helper)
    except Exception:
        traceback.print_exc()
        sys.exit(11)

ok = cv2.imwrite(args.output, img)
sys.exit(0 if ok else 4)
"""


def run_restore(
    input_path: str,
    output_path: str,
    options: dict[str, bool],
    *,
    device: str | None = None,
    codeformer_weight: float = 0.7,
    colorize_saturation: float = 1.15,
    colorize_wb: float = 0.85,
    colorize_size: int = 512,
    colorize_style: str = "natural",
    heal_strength: int = 10,
    progress_cb: Callable[[int, str], None] | None = None,
    cancelled_cb: Callable[[], bool] | None = None,
) -> dict:
    """Run chained AI photo restoration.

    options: {"colorize": bool, "restore_faces": bool, "heal": bool}
    colorize_saturation: HSV S-channel multiplier after Zhang colorize (1.0 = raw).
    heal_strength: NL-means denoise strength (3 mild .. 20 aggressive).
    progress_cb(pct, message): emitted at each stage boundary (0..100).
    """
    if device not in ("cpu", "cuda"):
        # Re-use upscaler's prober — same shared torch_runtime.
        try:
            from core.upscaler import detect_device
            device = detect_device()
        except Exception:
            device = "cpu"

    enabled = {k: bool(options.get(k)) for k in STAGE_KEYS}
    if not any(enabled.values()):
        return {"success": False, "error": "No stages enabled"}

    python = _python_exe()
    ai_dir = _ai_dir()
    upscaler_dir = _upscaler_dir()
    torch_host = _torch_host_dir()
    weights_dir = _weights_dir()

    cmd = [
        python, "-c", _CHILD_SCRIPT,
        ai_dir, torch_host, upscaler_dir, weights_dir,
        "--input", input_path,
        "--output", output_path,
        "--device", device,
        "--codeformer-weight", str(codeformer_weight),
        "--colorize-saturation", str(colorize_saturation),
        "--colorize-wb", str(colorize_wb),
        "--colorize-size", str(colorize_size),
        "--colorize-style", str(colorize_style),
        "--heal-strength", str(heal_strength),
    ]
    if enabled["colorize"]:
        cmd.append("--colorize")
    if enabled["restore_faces"]:
        cmd.append("--restore-faces")
    if enabled["heal"]:
        cmd.append("--heal")

    total_stages = max(1, sum(enabled.values()))
    creationflags = 0x08000000 if sys.platform == "win32" else 0
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, creationflags=creationflags,
        )
        stderr_lines: list[str] = []

        def _emit(text: str) -> None:
            if not text:
                return
            stderr_lines.append(text)
            m = _PROGRESS_RE.search(text)
            if m and progress_cb:
                cur, total = int(m.group(1)), max(1, int(m.group(2)))
                label = m.group(3).strip()
                # Map: stage start -> ((cur-1)/total)*100 + small offset.
                pct = int(((cur - 1) / total) * 100) + int(100 / total / 3)
                pct = max(0, min(99, pct))
                try:
                    progress_cb(pct, label)
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
            from core.crash_log import record_crash
            record_crash("AI Photo Restore", "\n".join(stderr_lines),
                         cmd=cmd, returncode=proc.returncode)
            detail = "\n".join(stderr_lines[-15:]) if stderr_lines else ""
            msg = f"restore exited with code {proc.returncode}"
            if detail:
                msg += f"\n{detail}"
            return {"success": False, "error": msg}

        if not os.path.isfile(output_path):
            return {"success": False, "error": f"Output not written: {output_path}"}

        if progress_cb:
            try:
                progress_cb(100, "Done")
            except Exception:
                pass

        return {
            "success": True,
            "device": device,
            "output_path": output_path,
            "stages": [k for k, v in enabled.items() if v],
        }

    except FileNotFoundError:
        return {"success": False, "error":
                "Python runtime not found. Install the AI Photo Restore component first."}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}
