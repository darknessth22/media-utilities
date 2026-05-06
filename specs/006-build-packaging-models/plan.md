# Implementation Plan: Reliable Build & AI Model Packaging

**Branch**: `006-build-packaging-models` | **Date**: 2026-05-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-build-packaging-models/spec.md`

## Summary

Two coupled problems: (1) shipped builds non-deterministic and over-sized due to dev-venv leakage and broken bundling toggles; (2) runtime AI install spawns a duplicate splash + second window and downloads nothing, leaving AI tabs unusable on shipped builds.

Approach:
- **Build**: keep clean `.build_venv` + `requirements-build.txt`, harden PyInstaller spec to actively exclude heavy ML modules (`torch`, `tensorflow`, `rembg`, `demucs`, `numba`, `cv2`, etc.), ship a **bundled Python runtime** (embeddable Python zip) under `runtime/python/` so end-user installs do not depend on `sys.executable`/`pip._internal`. Tighten `size-budget.json` (≤ 500 MB installer) and add top-contributor diagnostic when budget exceeded.
- **Runtime install**: replace in-process `pip._internal` call (root cause of the second window — re-imports pulling Qt/splash) with a hidden subprocess against the bundled runtime: `runtime/python/python.exe -m pip install --target %LOCALAPPDATA%\Videl\ai_packages -r manifests/<component>.txt`. Stream stdout via `QProcess` directly into the existing in-tab progress widget. Add per-component pinned manifest, GPU autodetect (CUDA → CUDA torch index URL, else CPU), partial-install rollback marker file, disk/size disclosure pre-install.

## Technical Context

**Language/Version**: Python 3.12 (dev), Python 3.12 embeddable (shipped runtime)
**Primary Dependencies**: PySide6 (GUI), PyInstaller (build), Inno Setup 6 (installer), pip (runtime install only)
**Storage**: per-user dir `%LOCALAPPDATA%\Videl\ai_packages\<component>\` + `state.json` per component
**Testing**: pytest (unit); manual fresh-VM install matrix
**Target Platform**: Windows 10/11 x64 only for shipped installer
**Project Type**: desktop-app (single project, existing modular layout)
**Performance Goals**: install completes in ≤ 10 min on broadband (SC-004); AI ready within 3 s of launch post-install (SC-005)
**Constraints**: installer ≤ 500 MB; no admin privilege required for AI install; single window invariant (no second splash) under all install states
**Scale/Scope**: 2 AI components today (Background Eraser, Vocal Isolator), design extensible to N

## Constitution Check

| Principle | Verdict | Notes |
|---|---|---|
| I. Modular Architecture | PASS | `utils/model_manager.py` is the single domain module; GUI only consumes it. New manifest files under `manifests/`. |
| II. Cross-Platform | PASS (scoped) | Spec explicitly Windows-only for shipped installer; `model_manager` keeps dev-mode code path for macOS/Linux developers running from source. |
| III. UX First | PASS | Single-window inline progress, actionable errors, pre-install size disclosure, retry without restart. |
| IV. Quality & Testing | PASS | Pinned per-release manifests; build-time exclusion verified by a unit test that scans the dist tree. |
| V. Simplicity | PASS | One install path (bundled runtime + subprocess); the in-process pip hack is removed, not extended. |

No violations → Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/006-build-packaging-models/
├── plan.md
├── spec.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    ├── manifest-schema.json
    └── model-manager-api.md
```

### Source Code (repository root)

```text
core/
  ai_components.py           # NEW — registry: id, label, manifest path, size estimate, importable_name
utils/
  model_manager.py           # MODIFY — bundled-runtime subprocess install, rollback, GPU detect
  bundled_runtime.py         # NEW — locate runtime/python/python.exe in frozen + dev modes
  gpu_detect.py              # NEW — wmic / nvidia-smi probe, returns "cuda"|"cpu"
manifests/
  bg_eraser.txt              # NEW — pinned reqs (rembg==X.Y.Z, onnxruntime==..., ...)
  vocal_isolator.txt         # NEW — pinned reqs (demucs==..., torch==... +cpu/+cu121)
  bg_eraser.cuda.txt         # NEW — CUDA variant
  vocal_isolator.cuda.txt    # NEW
gui/tabs/
  bg_eraser_section.py       # MODIFY — use new install API, pre-install size dialog, QProcess streaming
  vocal_isolator_section.py  # MODIFY — same
build_executable.py          # MODIFY — fetch+bundle embeddable Python into runtime/python, tighten budget, fail-with-top-10 already present
media_util_gui.spec          # MODIFY — extend `excludes=[...]`; add datas for runtime/python and manifests/
installer.iss                # MODIFY — include runtime/ and manifests/; ensure %LOCALAPPDATA%\Videl created on first launch (already implicit)
size-budget.json             # MODIFY — installer_mb: 500
locales/en.json, ar.json     # MODIFY — new install UI strings
tests/
  test_build_excludes.py     # NEW — assert no rembg/demucs/torch/cv2 inside dist/Videl after build
  test_manifest_parse.py     # NEW
```

**Structure Decision**: Single-project desktop layout (existing). Feature is additive on top of `core/`, `utils/`, `gui/tabs/` — no new top-level dirs except `manifests/` and `runtime/` (runtime is build-output only, gitignored).

## Complexity Tracking

None — all gates pass.
