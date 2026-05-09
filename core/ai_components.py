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
    # Extra CLI flags appended to `pip install` (per-component). Used by the
    # upscaler to pass --no-deps so pip won't resolve torch/torchvision as
    # transitive deps when those are reused from another component's install.
    extra_pip_args: tuple[str, ...] = ()


_REGISTRY: dict[str, AIComponent] = {
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
        approx_size_mb_cpu=250,
        approx_size_mb_cuda=3500,
    ),
    "upscaler": AIComponent(
        id="upscaler",
        label_key="tool_upscaler_name",
        importable_name="realesrgan",
        # Reuses torch from vocal_isolator. torchvision lives here (vocal_isolator
        # doesn't ship it). Variant must match vocal_isolator's torch ABI — pick
        # CUDA upscaler iff vocal_isolator was installed CUDA.
        manifest_cpu=os.path.join(_MANIFESTS_DIR, "upscaler.txt"),
        manifest_cuda=os.path.join(_MANIFESTS_DIR, "upscaler.cuda.txt"),
        approx_size_mb_cpu=185,
        approx_size_mb_cuda=190,
        extra_pip_args=("--no-deps",),
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
    "ocr_easy": AIComponent(
        id="ocr_easy",
        label_key="tool_ocr_easy_name",
        importable_name="easyocr",
        # Reuses torch from vocal_isolator. torchvision lives here. Variant must
        # match vocal_isolator's torch ABI — pick CUDA iff vocal_isolator CUDA.
        manifest_cpu=os.path.join(_MANIFESTS_DIR, "ocr_easy.txt"),
        manifest_cuda=os.path.join(_MANIFESTS_DIR, "ocr_easy.cuda.txt"),
        approx_size_mb_cpu=350,
        approx_size_mb_cuda=380,
        extra_pip_args=("--no-deps",),
    ),
}


def get(component_id: str) -> AIComponent:
    return _REGISTRY[component_id]


def all_ids() -> list[str]:
    return list(_REGISTRY.keys())
