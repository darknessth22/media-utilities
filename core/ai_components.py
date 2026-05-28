"""Registry of installable AI components (background eraser, vocal isolator)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MANIFESTS_DIR = os.path.join(_REPO_ROOT, "manifests")


@dataclass(frozen=True)
class AIComponent:
    id: str
    label_key: str
    importable_name: str
    manifest_cpu: str
    manifest_cuda: Optional[str]
    approx_size_mb_cpu: int
    approx_size_mb_cuda: Optional[int]
    # Extra CLI flags appended to `pip install` (per-component). Used by tools
    # that consume `torch_runtime` to pass --no-deps so pip won't redownload
    # torch/torchvision/numpy as transitive deps.
    extra_pip_args: tuple[str, ...] = ()
    # Other component IDs that must be installed before this one. The model
    # manager auto-installs them in order. Variant of a required component
    # follows the requester (CUDA requester → CUDA dep, CPU → CPU).
    requires: tuple[str, ...] = ()
    # When True, the component is treated as an internal shared runtime —
    # never shown as its own tool in Home/Tools, no standalone install button.
    hidden: bool = False


_REGISTRY: dict[str, AIComponent] = {
    "torch_runtime": AIComponent(
        id="torch_runtime",
        label_key="ai_runtime_torch",
        importable_name="torch",
        manifest_cpu=os.path.join(_MANIFESTS_DIR, "torch_runtime.txt"),
        manifest_cuda=os.path.join(_MANIFESTS_DIR, "torch_runtime.cuda.txt"),
        approx_size_mb_cpu=600,
        approx_size_mb_cuda=3000,
        hidden=True,
    ),
    "bg_eraser": AIComponent(
        id="bg_eraser",
        label_key="tool_bg_eraser_name",
        importable_name="rembg",
        manifest_cpu=os.path.join(_MANIFESTS_DIR, "bg_eraser.txt"),
        manifest_cuda=None,
        approx_size_mb_cpu=200,
        approx_size_mb_cuda=None,
    ),
    "vocal_isolator": AIComponent(
        id="vocal_isolator",
        label_key="tool_vocal_isolator_name",
        importable_name="demucs",
        manifest_cpu=os.path.join(_MANIFESTS_DIR, "vocal_isolator.txt"),
        manifest_cuda=os.path.join(_MANIFESTS_DIR, "vocal_isolator.cuda.txt"),
        approx_size_mb_cpu=50,
        approx_size_mb_cuda=50,
        extra_pip_args=("--no-deps",),
        requires=("torch_runtime",),
    ),
    "upscaler": AIComponent(
        id="upscaler",
        label_key="tool_upscaler_name",
        importable_name="realesrgan",
        manifest_cpu=os.path.join(_MANIFESTS_DIR, "upscaler.txt"),
        manifest_cuda=os.path.join(_MANIFESTS_DIR, "upscaler.cuda.txt"),
        approx_size_mb_cpu=180,
        approx_size_mb_cuda=180,
        extra_pip_args=("--no-deps",),
        requires=("torch_runtime",),
    ),
    "ocr_rapid": AIComponent(
        id="ocr_rapid",
        label_key="tool_ocr_rapid_name",
        importable_name="rapidocr_onnxruntime",
        manifest_cpu=os.path.join(_MANIFESTS_DIR, "ocr_rapid.txt"),
        manifest_cuda=None,
        approx_size_mb_cpu=120,
        approx_size_mb_cuda=None,
    ),
    "photo_restore": AIComponent(
        id="photo_restore",
        label_key="tool_photo_restore_name",
        importable_name="codeformer",
        manifest_cpu=os.path.join(_MANIFESTS_DIR, "photo_restore.txt"),
        manifest_cuda=os.path.join(_MANIFESTS_DIR, "photo_restore.cuda.txt"),
        approx_size_mb_cpu=350,
        approx_size_mb_cuda=350,
        extra_pip_args=("--no-deps",),
        # Needs torch_runtime; reuses upscaler's basicsr/facexlib/realesrgan
        # at import time (see core/restore.py child script — both component
        # dirs are on sys.path).
        requires=("torch_runtime", "upscaler"),
    ),
    "ocr_easy": AIComponent(
        id="ocr_easy",
        label_key="tool_ocr_easy_name",
        importable_name="easyocr",
        manifest_cpu=os.path.join(_MANIFESTS_DIR, "ocr_easy.txt"),
        manifest_cuda=os.path.join(_MANIFESTS_DIR, "ocr_easy.cuda.txt"),
        approx_size_mb_cpu=300,
        approx_size_mb_cuda=300,
        extra_pip_args=("--no-deps",),
        requires=("torch_runtime",),
    ),
}


def get(component_id: str) -> AIComponent:
    return _REGISTRY[component_id]


def all_ids() -> list[str]:
    return list(_REGISTRY.keys())


def visible_ids() -> list[str]:
    """Component IDs the user can install/uninstall directly (excludes shared runtimes)."""
    return [cid for cid, comp in _REGISTRY.items() if not comp.hidden]
