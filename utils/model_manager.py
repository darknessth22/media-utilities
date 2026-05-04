"""On-demand AI model package installer using bundled embeddable Python.

Implements the contract in
specs/006-build-packaging-models/contracts/model-manager-api.md.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional

from core import ai_components
from core.version import VERSION
from utils.bundled_runtime import BundledRuntimeMissingError, bundled_python_path
from utils.gpu_detect import (
    compute_capability as _gpu_capability,
    cuda_variant_supported as _cuda_variant_supported,
    detect as _gpu_detect,
)


class InsufficientDiskError(RuntimeError):
    """Raised when target volume lacks free space for an install."""


@dataclass
class ComponentState:
    status: str = "not_installed"
    variant: Optional[str] = None
    manifest_sha256: Optional[str] = None
    installed_at: Optional[str] = None
    last_error: Optional[str] = None
    app_version: str = VERSION


@dataclass
class PreInstallInfo:
    variant: str
    approx_size_mb: int
    target_dir: str
    manifest_path: str


@dataclass
class ReconcileResult:
    rolled_back: list[str] = field(default_factory=list)
    needs_reinstall: list[str] = field(default_factory=list)


# ---------- paths ----------

def _ai_packages_root() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Videl", "ai_packages")


def _component_dir(component_id: str) -> str:
    return os.path.join(_ai_packages_root(), component_id)


def _state_path(component_id: str) -> str:
    return os.path.join(_component_dir(component_id), "state.json")


def _manifest_for(component_id: str, variant: Optional[str] = None) -> tuple[str, str, int]:
    """Return (variant, manifest_path, approx_size_mb).

    `variant`: explicit "cpu"/"cuda" overrides GPU detection. When None, picks
    "cuda" if a CUDA manifest exists and a CUDA GPU is detected; else "cpu".
    """
    comp = ai_components.get(component_id)
    if variant == "cuda":
        if not comp.manifest_cuda:
            raise ValueError(f"{component_id} has no CUDA variant")
        return "cuda", comp.manifest_cuda, comp.approx_size_mb_cuda or comp.approx_size_mb_cpu
    if variant == "cpu":
        return "cpu", comp.manifest_cpu, comp.approx_size_mb_cpu
    if comp.manifest_cuda and _cuda_variant_supported():
        return "cuda", comp.manifest_cuda, comp.approx_size_mb_cuda or comp.approx_size_mb_cpu
    return "cpu", comp.manifest_cpu, comp.approx_size_mb_cpu


def available_variants(component_id: str) -> list[tuple[str, int]]:
    """Return [(variant, approx_size_mb), ...] for variants the user may pick."""
    comp = ai_components.get(component_id)
    out: list[tuple[str, int]] = [("cpu", comp.approx_size_mb_cpu)]
    if comp.manifest_cuda:
        out.append(("cuda", comp.approx_size_mb_cuda or comp.approx_size_mb_cpu))
    return out


def variant_compatibility(component_id: str, variant: str) -> tuple[bool, Optional[str]]:
    """Return (supported, reason_key) for a given variant on this machine.

    reason_key is an i18n string key explaining *why* unsupported, or None when
    supported. CPU is always supported. CUDA requires NVIDIA + sm_>=7.0.
    """
    if variant == "cpu":
        return True, None
    if variant == "cuda":
        if _gpu_detect() != "cuda":
            return False, "install_variant_cuda_no_gpu"
        cap = _gpu_capability()
        if cap is not None and cap < (7, 0):
            return False, "install_variant_cuda_old_gpu"
        return True, None
    return False, None


def detected_variant(component_id: str) -> str:
    """Variant the auto-detector would choose for this component."""
    comp = ai_components.get(component_id)
    if comp.manifest_cuda and _cuda_variant_supported():
        return "cuda"
    return "cpu"


def _manifest_sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ---------- state I/O ----------

def _write_state(component_id: str, state: ComponentState) -> None:
    os.makedirs(_component_dir(component_id), exist_ok=True)
    with open(_state_path(component_id), "w", encoding="utf-8") as f:
        json.dump(asdict(state), f, indent=2)


def read_state(component_id: str) -> ComponentState:
    try:
        with open(_state_path(component_id), encoding="utf-8") as f:
            data = json.load(f)
        return ComponentState(**{k: data.get(k) for k in ComponentState.__dataclass_fields__})
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        return ComponentState()


# ---------- public API ----------

def get_component(component_id: str):
    return ai_components.get(component_id)


def is_installed(component_id: str) -> bool:
    state = read_state(component_id)
    if state.status != "installed":
        return False
    _, manifest_path, _ = _manifest_for(component_id, state.variant)
    if not os.path.isfile(manifest_path):
        return False
    if state.manifest_sha256 != _manifest_sha256(manifest_path):
        return False
    comp = ai_components.get(component_id)
    pkg = os.path.join(_component_dir(component_id), comp.importable_name)
    return os.path.isdir(pkg) or os.path.isfile(pkg + ".py")


def reconcile_on_launch() -> ReconcileResult:
    result = ReconcileResult()
    for cid in ai_components.all_ids():
        state = read_state(cid)
        if state.status == "installing":
            uninstall(cid)
            result.rolled_back.append(cid)
            continue
        if state.status == "installed":
            try:
                _, manifest_path, _ = _manifest_for(cid, state.variant)
                if not os.path.isfile(manifest_path) or state.manifest_sha256 != _manifest_sha256(manifest_path):
                    # Manifest hash changed (often a benign whitespace/line-ending
                    # diff between builds). Flag for reinstall but DO NOT wipe —
                    # otherwise every upgrade forces users to re-download multi-GB
                    # AI packages. Reinstall path overwrites in place.
                    result.needs_reinstall.append(cid)
            except Exception:
                result.needs_reinstall.append(cid)
    return result


def ensure_ai_packages_on_path() -> None:
    for cid in ai_components.all_ids():
        if read_state(cid).status == "installed":
            d = _component_dir(cid)
            if os.path.isdir(d) and d not in sys.path:
                sys.path.insert(0, d)


def pre_install_info(component_id: str, variant: Optional[str] = None) -> PreInstallInfo:
    variant_resolved, manifest_path, size_mb = _manifest_for(component_id, variant)
    return PreInstallInfo(
        variant=variant_resolved,
        approx_size_mb=size_mb,
        target_dir=_component_dir(component_id),
        manifest_path=manifest_path,
    )


def start_install(component_id: str, on_line: Callable[[str], None],
                  variant: Optional[str] = None):
    """Launch pip install via QProcess against the bundled Python.

    Returns the running QProcess. Caller connects `finished` to call
    `finalize_install`.
    """
    info = pre_install_info(component_id, variant)
    target_dir = info.target_dir

    # Disk-space precheck (FR-014).
    os.makedirs(_ai_packages_root(), exist_ok=True)
    try:
        free = shutil.disk_usage(_ai_packages_root()).free
    except OSError:
        free = None
    needed = info.approx_size_mb * 1.5 * 1024 ** 2
    if free is not None and free < needed:
        raise InsufficientDiskError(
            f"Need ~{int(info.approx_size_mb * 1.5)} MB free; "
            f"only {int(free / 1024 ** 2)} MB available on target volume."
        )

    python_exe = bundled_python_path()  # raises BundledRuntimeMissingError when frozen+missing
    os.makedirs(target_dir, exist_ok=True)

    _write_state(component_id, ComponentState(
        status="installing",
        variant=info.variant,
        manifest_sha256=_manifest_sha256(info.manifest_path),
        app_version=VERSION,
    ))

    comp = ai_components.get(component_id)
    args = [
        "-u",  # unbuffered stdout/stderr so progress lines arrive live
        "-m", "pip", "install",
        "--no-warn-script-location",
        "--disable-pip-version-check",
        "--progress-bar", "on",
        "--target", target_dir,
        *comp.extra_pip_args,
        "-r", info.manifest_path,
    ]

    from PySide6.QtCore import QProcess, QProcessEnvironment

    proc = QProcess()
    proc.setProgram(python_exe)
    proc.setArguments(args)
    proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

    env = QProcessEnvironment.systemEnvironment()
    env.insert("PYTHONIOENCODING", "utf-8")
    env.insert("PYTHONUNBUFFERED", "1")
    env.insert("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    env.insert("PIP_PROGRESS_BAR", "on")
    proc.setProcessEnvironment(env)

    if sys.platform == "win32":
        # Hide console window on Windows (CREATE_NO_WINDOW = 0x08000000).
        try:
            proc.setCreateProcessArgumentsModifier(
                lambda a: setattr(a, "flags", a.flags | 0x08000000) or a
            )
        except Exception:
            pass

    _line_buf = {"buf": ""}

    def _emit_lines() -> None:
        chunk = bytes(proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        _line_buf["buf"] += chunk
        # Split on both \n and \r so pip's download progress bars (which use
        # carriage-return refresh, e.g. "  35%|███   | 1.2/3.5 GB") emit live.
        while True:
            buf = _line_buf["buf"]
            nl = buf.find("\n")
            cr = buf.find("\r")
            if nl < 0 and cr < 0:
                break
            if nl < 0:
                idx = cr
            elif cr < 0:
                idx = nl
            else:
                idx = min(nl, cr)
            line, _line_buf["buf"] = buf[:idx], buf[idx + 1:]
            line = line.strip()
            if line:
                try:
                    on_line(line)
                except Exception:
                    pass

    proc.readyReadStandardOutput.connect(_emit_lines)
    proc.start()
    return proc


def finalize_install(component_id: str, exit_code: int, tail_output: str) -> None:
    prev_state = read_state(component_id)
    info = pre_install_info(component_id, prev_state.variant)
    if exit_code == 0:
        state = ComponentState(
            status="installed",
            variant=info.variant,
            manifest_sha256=_manifest_sha256(info.manifest_path),
            installed_at=_dt.datetime.utcnow().isoformat() + "Z",
            last_error=None,
            app_version=VERSION,
        )
        _write_state(component_id, state)
        d = _component_dir(component_id)
        if d not in sys.path:
            sys.path.insert(0, d)
    else:
        state = ComponentState(
            status="failed",
            variant=info.variant,
            manifest_sha256=prev_state.manifest_sha256,
            installed_at=prev_state.installed_at,
            last_error=(tail_output or "")[-2000:],
            app_version=VERSION,
        )
        _write_state(component_id, state)


def uninstall(component_id: str) -> None:
    d = _component_dir(component_id)
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)


# ---------- backward-compat shims ----------

def is_rembg_installed() -> bool:
    return is_installed("bg_eraser")


def is_demucs_installed() -> bool:
    return is_installed("vocal_isolator")


def install_rembg(progress_cb=None):  # noqa: ARG001 — transitional stub
    raise RuntimeError(
        "install_rembg() is removed; use model_manager.start_install('bg_eraser', ...)."
    )


def install_demucs(progress_cb=None):  # noqa: ARG001 — transitional stub
    raise RuntimeError(
        "install_demucs() is removed; use model_manager.start_install('vocal_isolator', ...)."
    )
