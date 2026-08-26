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
from utils.paths import ai_packages_dir
from utils.gpu_detect import (
    compute_capability as _gpu_capability,
    cuda_variant_supported as _cuda_variant_supported,
    detect as _gpu_detect,
)


class InsufficientDiskError(RuntimeError):
    """Raised when target volume lacks free space for an install."""


# Network settings for the pip subprocess. Components can be multi-gigabyte
# (the CUDA torch wheel alone is ~3.3 GB), so pip's stock 15 s timeout and 5
# retries are far too aggressive — one brief stall killed the whole install.
_PIP_TIMEOUT_SECONDS = 120
_PIP_RETRIES = 20


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
    return str(ai_packages_dir())


def _pip_cache_dir() -> str:
    """Persistent pip wheel cache, kept beside the installed AI packages."""
    path = os.path.join(_ai_packages_root(), "_pip_cache")
    os.makedirs(path, exist_ok=True)
    return path


def _wheel_cache_dir() -> str:
    """Where pre-downloaded wheels (and their .part files) accumulate.

    Deliberately separate from pip's own cache: these files are managed by
    `utils.wheel_prefetch` and must survive between attempts so an interrupted
    multi-gigabyte download can resume.
    """
    path = os.path.join(_ai_packages_root(), "_wheels")
    os.makedirs(path, exist_ok=True)
    return path


def _install_runner_path() -> Optional[str]:
    """Filesystem path to `utils/install_runner.py`, or None if unavailable.

    The bundled interpreter runs the runner as a plain script, so it needs a
    real path. In a frozen build `utils/` is unpacked next to the executable by
    PyInstaller; in a source checkout it sits next to this module.
    """
    candidate = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "install_runner.py")
    if os.path.isfile(candidate):
        return candidate
    base = getattr(sys, "_MEIPASS", None)
    if base:
        frozen = os.path.join(base, "utils", "install_runner.py")
        if os.path.isfile(frozen):
            return frozen
    return None


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


def _migrate_torch_to_runtime_dir() -> None:
    """One-time migration: lift torch/torchvision/torchaudio/numpy/nvidia* out
    of `vocal_isolator/` (legacy install layout) into the new shared
    `torch_runtime/` dir, then mark torch_runtime installed with the variant
    inherited from vocal_isolator. Does nothing if torch_runtime already
    exists or vocal_isolator was never installed.
    """
    if read_state("torch_runtime").status == "installed":
        return
    vocal_state = read_state("vocal_isolator")
    if vocal_state.status != "installed":
        return
    src = _component_dir("vocal_isolator")
    dst = _component_dir("torch_runtime")
    if not os.path.isdir(src):
        return

    moved_any = False
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        if name == "state.json":
            continue
        # Heuristic: torch / torchvision / torchaudio / numpy / nvidia-* / functorch
        # plus dist-info siblings for any of those.
        low = name.lower()
        if (low.startswith("torch") or low.startswith("numpy")
                or low.startswith("nvidia") or low.startswith("functorch")
                or low.startswith("triton")):
            src_p = os.path.join(src, name)
            dst_p = os.path.join(dst, name)
            if os.path.exists(dst_p):
                continue
            try:
                shutil.move(src_p, dst_p)
                moved_any = True
            except OSError:
                pass

    if moved_any:
        try:
            comp = ai_components.get("torch_runtime")
            variant = vocal_state.variant or "cpu"
            manifest = comp.manifest_cuda if (variant == "cuda" and comp.manifest_cuda) else comp.manifest_cpu
            _write_state("torch_runtime", ComponentState(
                status="installed",
                variant=variant,
                manifest_sha256=_manifest_sha256(manifest) if os.path.isfile(manifest) else None,
                installed_at=_dt.datetime.utcnow().isoformat() + "Z",
                app_version=VERSION,
            ))
            # Bless the new (slimmer) vocal_isolator manifest hash so reconcile
            # doesn't force a reinstall purely because torch lines were stripped.
            try:
                _, vocal_manifest, _ = _manifest_for("vocal_isolator", vocal_state.variant)
                if os.path.isfile(vocal_manifest):
                    _write_state("vocal_isolator", ComponentState(
                        status="installed",
                        variant=vocal_state.variant,
                        manifest_sha256=_manifest_sha256(vocal_manifest),
                        installed_at=vocal_state.installed_at,
                        last_error=None,
                        app_version=VERSION,
                    ))
            except Exception:
                pass
            # Same blessing for upscaler / ocr_easy if they were installed
            # against the old torch-in-vocal layout.
            for legacy_id in ("upscaler", "ocr_easy"):
                legacy_state = read_state(legacy_id)
                if legacy_state.status != "installed":
                    continue
                try:
                    _, legacy_manifest, _ = _manifest_for(legacy_id, legacy_state.variant)
                    if os.path.isfile(legacy_manifest):
                        _write_state(legacy_id, ComponentState(
                            status="installed",
                            variant=legacy_state.variant,
                            manifest_sha256=_manifest_sha256(legacy_manifest),
                            installed_at=legacy_state.installed_at,
                            last_error=None,
                            app_version=VERSION,
                        ))
                except Exception:
                    pass
        except Exception:
            pass


def reconcile_on_launch() -> ReconcileResult:
    _migrate_torch_to_runtime_dir()
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


_RUNTIME_DEP_IDS = ("torch_runtime",)


def ensure_ai_packages_on_path() -> None:
    """Add installed component dirs to sys.path. Runtimes (torch_runtime) go
    first so consumers (demucs/realesrgan/easyocr) import them on `import torch`.
    """
    for cid in _RUNTIME_DEP_IDS:
        if read_state(cid).status == "installed":
            d = _component_dir(cid)
            if os.path.isdir(d) and d not in sys.path:
                sys.path.insert(0, d)
    for cid in ai_components.all_ids():
        if cid in _RUNTIME_DEP_IDS:
            continue
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


def missing_requirements(component_id: str, variant: Optional[str] = None) -> list[str]:
    """Return ordered list of unmet `requires` IDs that must install first."""
    comp = ai_components.get(component_id)
    out: list[str] = []
    for req_id in comp.requires:
        if not is_installed(req_id):
            out.append(req_id)
    return out


def aggregate_install_size_mb(component_id: str, variant: Optional[str] = None) -> int:
    """Total MB to download = component itself + any missing required deps.

    Variant of each missing dep follows the requester's variant.
    """
    info = pre_install_info(component_id, variant)
    total = info.approx_size_mb
    for req_id in missing_requirements(component_id, variant):
        req_variant = info.variant if ai_components.get(req_id).manifest_cuda else "cpu"
        total += pre_install_info(req_id, req_variant).approx_size_mb
    return total


def start_install(component_id: str, on_line: Callable[[str], None],
                  variant: Optional[str] = None):
    """Launch pip install via QProcess against the bundled Python.

    If the component declares `requires` and any are missing, the FIRST
    missing requirement is installed instead. Caller's finalize handler
    must check `missing_requirements()` and re-call start_install for the
    actual component once each dep finishes. The DependencyChainInstaller
    in UI sections wraps this loop.

    Returns the running QProcess. Caller connects `finished` to call
    `finalize_install`.
    """
    missing = missing_requirements(component_id, variant)
    if missing:
        next_id = missing[0]
        # Variant for runtime deps mirrors requester (CUDA→CUDA if dep has CUDA).
        req_comp = ai_components.get(next_id)
        next_variant = variant if (variant and req_comp.manifest_cuda) else \
                       (variant if req_comp.manifest_cuda else "cpu")
        on_line(f"[deps] Installing required component: {next_id} ({next_variant})")
        proc = _start_install_single(next_id, on_line, next_variant)
        proc.setProperty("videl_component_id", next_id)
        proc.setProperty("videl_target_id", component_id)
        return proc
    proc = _start_install_single(component_id, on_line, variant)
    proc.setProperty("videl_component_id", component_id)
    proc.setProperty("videl_target_id", component_id)
    return proc


def _start_install_single(component_id: str, on_line: Callable[[str], None],
                          variant: Optional[str] = None):
    """Run pip install for ONE component (no dep chaining)."""
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

    # Run the install through install_runner: it pre-downloads big wheels with
    # resume support (so a dropped connection or a closed app no longer throws
    # away gigabytes) and then hands off to pip. If the runner can't be located
    # — an unusual frozen layout, say — fall back to invoking pip directly so
    # installing still works.
    runner = _install_runner_path()
    pip_net_args = [
        # The CUDA torch wheel is ~3.3 GB. pip's defaults (15 s read timeout,
        # 5 retries) are far too tight for that on a slow or flaky connection:
        # a stalled read aborts the whole install and the partial wheel is
        # thrown away, so users on modest links could never finish. Give the
        # transfer room to recover from short outages instead.
        "--timeout", str(_PIP_TIMEOUT_SECONDS),
        "--retries", str(_PIP_RETRIES),
    ]
    if runner:
        args = [
            "-u",  # unbuffered stdout/stderr so progress lines arrive live
            runner,
            "--manifest", info.manifest_path,
            "--target", target_dir,
            "--wheel-dir", _wheel_cache_dir(),
            "--timeout", str(_PIP_TIMEOUT_SECONDS),
            "--retries", str(_PIP_RETRIES),
        ]
        if comp.extra_pip_args:
            # Everything past "--" reaches pip verbatim, so values that look
            # like options (--no-deps) survive the runner's own parsing.
            args += ["--", *comp.extra_pip_args]
    else:
        args = [
            "-u",
            "-m", "pip", "install",
            "--no-warn-script-location",
            "--disable-pip-version-check",
            "--progress-bar", "on",
            *pip_net_args,
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
    # Keep the wheel cache next to the packages we install rather than wherever
    # the bundled interpreter would default to. Wheels that did download stay
    # cached, so retrying a failed multi-gigabyte install resumes at the wheel
    # level instead of starting over.
    env.insert("PIP_CACHE_DIR", _pip_cache_dir())
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
