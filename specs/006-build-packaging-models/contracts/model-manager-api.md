# Contract: `utils/model_manager` public API

All functions are sync unless noted. GUI calls them from a `QProcess`-based flow, not a worker thread (no in-process pip).

## `get_component(component_id: str) -> AIComponent`

Lookup in registry. Raises `KeyError` for unknown id.

## `read_state(component_id: str) -> ComponentState`

Read `state.json`. Missing file or invalid JSON → returns `ComponentState(status="not_installed", ...)`.

## `is_installed(component_id: str) -> bool`

Returns True iff `read_state(...).status == "installed"` AND manifest hash matches current on-disk manifest AND `importable_name` resolvable from component dir.

## `reconcile_on_launch() -> ReconcileResult`

Called once at app startup, BEFORE `ensure_ai_packages_on_path`. For each component:
- If `status == "installing"` → rollback (`rmtree` + delete `state.json`); add id to `rolled_back`.
- If `status == "installed"` AND manifest hash mismatches → rollback as above; add id to `needs_reinstall`.
- Else no-op.

Returns `ReconcileResult { rolled_back: list[str], needs_reinstall: list[str] }`.

Caller (main.py) MUST, for each id in `needs_reinstall`, invoke `start_install` headlessly
(no user prompt, per FR-010a) and surface a non-blocking toast "<label> updated for this release".
`rolled_back` ids surface as "previous install was interrupted — click to retry".

## `ensure_ai_packages_on_path() -> None`

For every `installed` component, prepend its dir to `sys.path` once.

## `pre_install_info(component_id: str) -> PreInstallInfo`

Returns `{ variant: "cpu"|"cuda", approx_size_mb: int, target_dir: str, manifest_path: str }`. Picks variant via `gpu_detect.detect()`.

## `start_install(component_id: str, on_line: Callable[[str], None]) -> QProcess`

Caller passes a line callback. Function:
1. Calls `pre_install_info` to pick variant.
2. Writes `state.json` with `status=installing`.
3. Builds command: `[bundled_python, "-m", "pip", "install", "--no-warn-script-location", "--target", component_dir, "-r", manifest_path]`.
4. Configures `QProcess` with hidden window flags (Windows: `CREATE_NO_WINDOW`).
5. Wires stdout → `on_line(...)` line by line.
6. Returns the `QProcess` (still running). Caller connects `finished` → calls `_finalize_install(...)`.

Raises `InsufficientDiskError` (FR-014) before starting if free space on target volume < `approx_size_mb * 1.5`.
Raises `BundledRuntimeMissingError` if `bundled_python` not found (dev fallback uses `sys.executable`).

## `finalize_install(component_id: str, exit_code: int, tail_output: str) -> None`

Caller invokes from `QProcess.finished`. Writes `state.json` with `installed` (exit 0) or `failed` (exit != 0) plus `last_error = tail_output[-2000:]`. On success, prepends component dir to `sys.path`.

## `uninstall(component_id: str) -> None`

`rmtree` component dir, delete `state.json`. Used for retry-after-failure and for manifest-mismatch rollback.

---

## Backward-compat shims (transitional)

`is_rembg_installed()` → `is_installed("bg_eraser")`
`is_demucs_installed()` → `is_installed("vocal_isolator")`
`install_rembg(progress_cb)` / `install_demucs(progress_cb)` are removed; callers (`bg_eraser_section.py`, `vocal_isolator_section.py`) migrate to `start_install` + `finalize_install`.
