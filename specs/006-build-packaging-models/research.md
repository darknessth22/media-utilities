# Phase 0 Research — Build & AI Model Packaging

## R1. Why does runtime install spawn a second splash + window?

**Decision**: Stop calling `pip._internal.cli.main` in-process. Run pip as a hidden subprocess against a bundled embeddable Python.

**Rationale**: Inside a frozen PyInstaller exe, `sys.executable` is `Videl.exe`, not Python — so the current code falls back to `pip._internal`. pip's internal API touches subprocess, importlib, and (transitively) re-imports modules already initialized in the frozen app; on Windows under PyInstaller this can re-trigger the splash bootstrap and module-level Qt init in the AI packages it tries to resolve. Running pip in a *separate* Python process with `CREATE_NO_WINDOW` and `STARTUPINFO.wShowWindow = SW_HIDE` isolates pip from the running Qt event loop — no second window can appear.

**Alternatives considered**:
- Vendor only wheels and unpack manually → re-implements pip's resolver, fragile across torch CUDA variants.
- `pip download` then `pip install --no-index` from cache → adds complexity, same subprocess requirement, no UX benefit over plain online install.
- Keep in-process pip but suppress Qt re-init → fragile, root cause not addressed.

## R2. How to ship a Python interpreter to the user without exploding installer size?

**Decision**: Bundle the official **Windows embeddable Python 3.12** zip (~12 MB compressed, ~30 MB extracted) under `runtime/python/`. Patch `python312._pth` to enable `import site` so `pip` works. Download `get-pip.py` once at build time, run `runtime/python/python.exe get-pip.py` to install pip into the embeddable runtime.

**Rationale**: Embeddable distribution is purpose-built for this case (Microsoft Store apps, frozen apps). ~30 MB is acceptable inside the 500 MB budget. No system-Python dependency on user machine.

**Alternatives considered**:
- Full CPython MSI bundled silently → 100+ MB, requires admin, rejected.
- WinPython / conda → far heavier (~200 MB+), licensing nuance.
- Shell out to `py.exe` if present → user might not have it; non-deterministic.

## R3. How to keep dist artifact size deterministic regardless of dev venv?

**Decision**: Build inside `.build_venv` (already implemented) seeded only from `requirements-build.txt`. Add explicit `excludes` to `media_util_gui.spec` for: `torch`, `torchaudio`, `torchvision`, `tensorflow`, `tensorboard`, `rembg`, `demucs`, `onnxruntime`, `onnxruntime-gpu`, `cv2`, `numba`, `llvmlite`, `scipy`, `sklearn`, `pandas`, `matplotlib`, `transformers`. Add a regression test (`tests/test_build_excludes.py`) that scans `dist/Videl` after a build and fails if any excluded module's top-level dir/file is present.

**Rationale**: PyInstaller follows imports; if dev venv has these *and* any code path imports them at module load, they leak in. Exclude list + clean venv + post-build scan is belt-and-suspenders.

**Alternatives considered**:
- Rely on clean venv alone → already in place and still leaks when conditional imports exist.
- Two-stage build (analysis + filter) → overkill.

## R4. GPU autodetect strategy

**Decision**: At install time only (not every launch), probe in this order:
1. `nvidia-smi -L` exits 0 with non-empty output → CUDA present.
2. Else CPU.

Result chosen variant is recorded in `state.json`; at launch we only validate the manifest hash matches, we do not re-probe.

**Rationale**: `nvidia-smi` ships with every NVIDIA driver, no Python deps, fast. Driver presence is a more reliable proxy than `torch.cuda.is_available()` (which would require torch already installed — chicken/egg).

**Alternatives considered**:
- WMI query for video controller name → false positives (Intel + NVIDIA hybrids), slower.
- Always install CPU then upgrade to CUDA on user opt-in → doubles user friction.
- `pip install torch` and let it pick → torch defaults to CUDA build (~2.5 GB) on PyPI; we want CPU as default fallback.

## R5. Per-release pinning + drift detection

**Decision**: One manifest file per (component, variant) under `manifests/`, e.g. `bg_eraser.cuda.txt`. Each line is `pkg==exact_version` (pip-format). At launch, `model_manager` computes SHA-256 of the manifest text and compares to `state.json["manifest_sha256"]` for that component. Mismatch → wipe component dir + clear state → user re-prompted on next AI tab open. No semver tolerance.

**Rationale**: Matches FR-010a exactly; sha256 is cheap, deterministic, version-bump-proof. Trivial code: no resolver involvement.

**Alternatives considered**:
- Compare individual installed package versions via importlib.metadata → slower, more code, same result.
- pip-tools `pip-sync` → adds dep, same outcome.

## R6. Partial install rollback

**Decision**: Write `state.json` with `{"status": "installing", ...}` *before* invoking pip. On success → `installed`. On failure or app exit before completion → on next launch, any `state.status == "installing"` triggers `shutil.rmtree(component_dir)` + delete `state.json` → user sees "not installed" again.

**Rationale**: Single source of truth, atomic enough for our needs. No need for transactional FS — pip's --target writes are idempotent and our rollback is "delete the dir."

**Alternatives considered**:
- Resume partial install → pip resume semantics unreliable across versions; spec explicitly rejects this.
- Per-package transaction log → over-engineered.

## R7. Streaming pip output into the existing window

**Decision**: Use `QProcess` (PySide6) instead of `subprocess.Popen` + Worker thread. `readyReadStandardOutput` signal posts directly to the in-tab `QTextEdit`. Hidden window flag: `setProcessChannelMode(QProcess.MergedChannels)` and on Windows pass `CREATE_NO_WINDOW` via `setCreateProcessArgumentsModifier`.

**Rationale**: Native Qt integration, no extra worker/thread, no chance of Qt re-entry from in-process pip. Keeps main window responsive (FR-008) by design.

**Alternatives considered**:
- Keep current `Worker` + `subprocess.Popen` → works but more moving parts; QProcess is the canonical Qt way.

## R8. Size budget value

**Decision**: `installer_mb: 500`, `installed_mb: 900`, `tolerance_pct: 5`. Current build (post-clean-venv) is ~250 MB installer; 500 MB ceiling gives headroom for embeddable Python (+30 MB) + manifests (negligible) without inviting drift.

**Rationale**: Spec target ≤ 500 MB (SC-001). Tolerance retained from existing budget logic.
