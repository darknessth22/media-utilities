---
description: "Task list for Reliable Build & AI Model Packaging"
---

# Tasks: Reliable Build & AI Model Packaging

**Input**: Design documents from `/specs/006-build-packaging-models/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Two tests called out by plan.md are included (`test_build_excludes.py`, `test_manifest_parse.py`). No broader TDD requested.

**Organization**: Tasks grouped by user story (US1 P1, US2 P1, US3 P2). US1 and US2 share Phase 2 foundational work; US3 builds on US1.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffold new directories, registry stub, locale keys.

- [x] T001 Create `manifests/` directory at repo root with `.gitkeep`
- [x] T002 [P] Add `runtime/` to `.gitignore` (build-output only) at repo root `.gitignore`
- [x] T003 [P] Add new locale keys (install banner, size disclosure, retry, error) under a single `install_*` namespace in `locales/en.json`
- [x] T004 [P] Mirror new keys with Arabic translations in `locales/ar.json`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared modules every story depends on — registry, bundled-runtime locator, GPU detection, manifest parsing, state machine. No user story can land before this.

**⚠️ CRITICAL**: Blocks US1, US2, US3.

- [x] T005 [P] Create `core/ai_components.py` defining `AIComponent` dataclass and registry with `bg_eraser` and `vocal_isolator` entries per `data-model.md`
- [x] T006 [P] Create `utils/bundled_runtime.py` exposing `bundled_python_path()` resolving `runtime/python/python.exe` for both frozen (`sys._MEIPASS` / install dir) and dev (`sys.executable`) modes, plus `BundledRuntimeMissingError`
- [x] T007 [P] Create `utils/gpu_detect.py` with `detect() -> Literal["cuda","cpu"]` probing `nvidia-smi` then WMIC fallback, cached per-process
- [x] T008 [P] Create `manifests/bg_eraser.txt` with pinned `rembg==`, `onnxruntime==`, transitive pins (CPU only — no `.cuda.txt` per data-model)
- [x] T009 [P] Create `manifests/vocal_isolator.txt` (CPU torch) and `manifests/vocal_isolator.cuda.txt` (`--extra-index-url https://download.pytorch.org/whl/cu121`, `torch==…+cu121`, `torchaudio==…+cu121`, `demucs==…`)
- [x] T010 Rewrite `utils/model_manager.py` to expose the `model-manager-api.md` contract: `get_component`, `read_state`, `is_installed`, `reconcile_on_launch`, `ensure_ai_packages_on_path`, `pre_install_info`, `start_install`, `finalize_install`, `uninstall`, plus `InsufficientDiskError` and backward-compat shims `is_rembg_installed` / `is_demucs_installed` (depends on T005, T006, T007)
- [x] T011 [P] Create `tests/test_manifest_parse.py` — for each file under `manifests/`: (1) parse as pip requirements (no syntax error), (2) every non-comment, non-`--extra-index-url` line pins exact version (`==` or `==X+localtag`), (3) validate against `contracts/manifest-schema.json` using `jsonschema`. Add `jsonschema` to `requirements-build.txt`.
- [x] T012 Wire `model_manager.reconcile_on_launch()` into `main.py` before MainWindow shown. For returned `needs_reinstall` ids, kick off headless `start_install` (no prompt, FR-010a) with progress surfaced via MainWindow toast; for `rolled_back` ids surface a one-shot "interrupted install" toast with retry. Then call `ensure_ai_packages_on_path()`.

**Checkpoint**: Foundation ready — US1, US2, US3 may proceed.

---

## Phase 3: User Story 1 — Reliable runtime install of AI features (Priority: P1) 🎯 MVP

**Goal**: Single-window in-tab AI install via QProcess against bundled Python; no second splash/window; rollback + retry.

**Independent Test**: Fresh install on clean Win VM → open Background Eraser → click install → only one window throughout, progress streams in tab, feature works without restart, kill-mid-install rollback works on relaunch.

### Implementation for User Story 1

- [x] T013 [US1] Refactor `gui/tabs/bg_eraser_section.py` install flow: remove in-process `pip._internal` call; replace with `model_manager.start_install("bg_eraser", on_line=...)`, render streamed lines into existing in-tab progress widget, connect `QProcess.finished` to `model_manager.finalize_install` then enable feature without restart
- [x] T014 [US1] Refactor `gui/tabs/vocal_isolator_section.py` install flow identically against `vocal_isolator` component
- [x] T015 [P] [US1] In both tabs, add actionable error rendering (network / disk / permission / generic) reading `state.last_error`, with single Retry button calling `uninstall` then `start_install` again
- [x] T016 [US1] Ensure `QProcess` is started with `CREATE_NO_WINDOW` (Windows) inside `model_manager.start_install` so no console window flashes; verify main window stays movable/closable during install (no modal, no event-loop block)
- [x] T017 [US1] Add splash-screen guard in `main.py` / splash module so a second app instance never re-creates the splash (idempotent show; suppress when parent process already alive) — root cause of the duplicate-splash bug
- [x] T018 [US1] Modify `build_executable.py` to download Python 3.12 embeddable zip into `runtime/python/`, run `get-pip.py` against it, and cache the download (skip on rebuild)
- [x] T019 [US1] Update `media_util_gui.spec`: add `runtime/` and `manifests/` to `datas`; extend `excludes=[...]` with `torch`, `tensorflow`, `rembg`, `demucs`, `numba`, `cv2`, `onnxruntime`, `torchaudio`, `scipy`, `sklearn`
- [x] T020 [US1] Update `installer.iss` to include `runtime\*` and `manifests\*` recursively under app dir; confirm `%LOCALAPPDATA%\Videl` is created on first run (no installer-side `Dirs:` entry needed)
- [x] T021 [US1] Update `requirements-build.txt` to keep build-only deps lean (no torch/rembg/demucs); ensure `.build_venv` provisioning in `build_executable.py` reads from it exclusively

**Checkpoint**: US1 demoable — runtime AI install works end-to-end on clean machine.

---

## Phase 4: User Story 2 — Build pipeline succeeds locally and in CI with bounded size (Priority: P1)

**Goal**: Deterministic, sub-500 MB installer regardless of dev venv contents; CI parity; size-budget enforcement with top-10 contributor report on failure.

**Independent Test**: From a dev venv polluted with rembg/demucs/torch, run `python build_executable.py` → installer ≤ 500 MB and excluded packages absent from `dist/Videl/`. Push to `main` → CI produces matching artifact.

### Implementation for User Story 2

- [x] T022 [US2] Tighten `size-budget.json` to `{ "installer_mb": 500, "installed_mb": 900, "tolerance_pct": 5 }`
- [x] T023 [US2] In `build_executable.py`, on budget overrun, walk `dist/Videl/` and emit top-10 contributing files (path + MB) to stderr and into `dist/size-report.json` before exiting non-zero
- [x] T024 [US2] In `build_executable.py`, extend `dist/size-report.json` schema to `{ timestamp, installer_mb, installed_mb, budget_verdict, top_contributors[] }` per data-model
- [x] T025 [P] [US2] Create `tests/test_build_excludes.py` — walks `dist/Videl/` and asserts no path segment in `{rembg, demucs, torch, tensorflow, cv2, numba, onnxruntime}`; skipped when `dist/Videl/` absent
- [x] T026 [US2] In `build_executable.py`, after PyInstaller step, invoke `pytest tests/test_build_excludes.py` and fail the build on any leak (print offending paths)
- [x] T026a [US2] In CI, run build twice (clean venv, polluted venv with rembg/demucs/torch) and assert `dist/Videl/` path-set equality + installer size within ±5% tolerance (per SC-002). Fail on divergence.
- [x] T027 [US2] Update `.github/workflows/build.yml` to upload `Output/Videl_Setup.exe` AND `dist/size-report.json` as artifacts; ensure workflow uses `requirements-build.txt` only (no editable install of full deps)

**Checkpoint**: US2 demoable — build is deterministic, CI artifact matches local within tolerance.

---

## Phase 5: User Story 3 — Pre-install size & disk disclosure (Priority: P2)

**Goal**: Before commit, user sees variant (CPU/CUDA), approx download size, target dir; insufficient-disk path errors before any download.

**Independent Test**: Pre-install state in either AI tab shows size + path; on a volume with < required free space, install button errors clearly with no network activity.

### Implementation for User Story 3

- [x] T028 [P] [US3] Build pre-install confirmation panel inside `gui/tabs/bg_eraser_section.py` that calls `model_manager.pre_install_info("bg_eraser")` and renders `variant`, `approx_size_mb`, `target_dir` plus Confirm/Cancel
- [x] T029 [P] [US3] Mirror pre-install confirmation panel in `gui/tabs/vocal_isolator_section.py` against `vocal_isolator`, displaying CUDA size when GPU detected
- [x] T030 [US3] In `model_manager.start_install`, before launching pip, raise `InsufficientDiskError` when `shutil.disk_usage(target_volume).free < approx_size_mb * 1.5 * 1024**2`; render its message in both tabs as a non-network actionable error

**Checkpoint**: All three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting

- [x] T031 [P] Update `gui/tabs/tutorial_section.py` — add steps for runtime AI install + pre-install disclosure in both `_TUTORIAL_DATA_EN` and `_TUTORIAL_DATA_AR`
- [x] T032 [P] Update `README.md` features/install sections to document bundled runtime + per-user AI install location
- [x] T033 Refresh codebase graph: `graphify update "e:\Omniclouds\media-utilities"`
- [ ] T034 Run `specs/006-build-packaging-models/quickstart.md` end-to-end on clean Windows VM and record results

---

## Dependencies & Execution Order

### Phase Dependencies
- Phase 1 (Setup) → no deps
- Phase 2 (Foundational) → after Phase 1; blocks Phase 3+
- Phase 3 (US1) → after Phase 2
- Phase 4 (US2) → after Phase 2; independent of US1 at file level (different files), can run in parallel
- Phase 5 (US3) → after Phase 3 (extends the same tab files US1 modifies)
- Phase 6 (Polish) → after US1/US2/US3 complete

### User Story Dependencies
- **US1 (P1)**: independent of US2/US3 once foundation done
- **US2 (P1)**: independent of US1/US3 (touches build/CI files only)
- **US3 (P2)**: depends on US1 because both modify the same AI tab files (`bg_eraser_section.py`, `vocal_isolator_section.py`)

### Within Each User Story
- Models/registry before services before UI wiring
- `model_manager` (T010) before any tab refactor
- Build-spec changes (T018–T021) can land alongside tab refactors

### Parallel Opportunities
- T002, T003, T004 in parallel
- T005, T006, T007, T008, T009, T011 all parallel (distinct files)
- US1 and US2 fully parallel (disjoint files)
- T015 parallel against tab body refactor
- T028, T029 parallel
- T031, T032 parallel

---

## Parallel Example: Phase 2 Foundational

```bash
# Launch independent foundation files together:
Task: "Create core/ai_components.py registry"
Task: "Create utils/bundled_runtime.py"
Task: "Create utils/gpu_detect.py"
Task: "Create manifests/bg_eraser.txt"
Task: "Create manifests/vocal_isolator.txt + .cuda.txt"
Task: "Create tests/test_manifest_parse.py"
```

---

## Implementation Strategy

### MVP First (US1 + US2)
Both are P1 and together unblock release: US1 makes shipped AI tabs functional; US2 makes the artifact shippable. After Phase 2:
1. Complete US1 (Phase 3) — runtime install works on clean VM
2. In parallel, complete US2 (Phase 4) — bounded, deterministic build
3. Validate via quickstart.md → ship MVP

### Incremental
1. Setup + Foundational
2. US1 → smoke-test on clean VM (MVP-A: AI tabs functional)
3. US2 → CI green (MVP-B: shippable artifact)
4. US3 → pre-install disclosure
5. Polish → tutorial, README, graph refresh, full quickstart pass

---

## Notes
- US1 and US3 share tab files — sequence US3 after US1 to avoid merge churn.
- `runtime/` is build output, gitignored; never check in the embeddable Python.
- Every new UI string lands in `en.json` AND `ar.json` in the same task (per CLAUDE.md).
- After any code change touching modules, run `graphify update`.
