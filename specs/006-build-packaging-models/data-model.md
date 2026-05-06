# Phase 1 Data Model

## Entity: AIComponent (registry record, in-code)

Defined in `core/ai_components.py` as immutable dataclass.

| Field | Type | Notes |
|---|---|---|
| `id` | str | snake_case, e.g. `bg_eraser` |
| `label_key` | str | i18n key for display name |
| `importable_name` | str | top-level module to probe, e.g. `rembg` |
| `manifest_cpu` | Path | `manifests/<id>.txt` |
| `manifest_cuda` | Path \| None | `manifests/<id>.cuda.txt`; None = no CUDA variant |
| `approx_size_mb_cpu` | int | shown pre-install (FR-013) |
| `approx_size_mb_cuda` | int \| None | shown pre-install when CUDA picked |

Initial registry:
- `bg_eraser` → rembg, ~200 MB CPU, no CUDA variant (rembg uses onnxruntime which auto-picks)
- `vocal_isolator` → demucs, ~250 MB CPU / ~2500 MB CUDA

## Entity: ComponentState (per-user, on-disk)

Stored at `%LOCALAPPDATA%\Videl\ai_packages\<component_id>\state.json`.

```json
{
  "status": "not_installed | installing | installed | failed",
  "variant": "cpu | cuda",
  "manifest_sha256": "<hex>",
  "installed_at": "ISO-8601 | null",
  "last_error": "string | null",
  "app_version": "1.2.3"
}
```

**State machine**:

```
not_installed --(user clicks install)--> installing
installing --(pip exit 0)--> installed
installing --(pip exit !=0 OR app close)--> failed (on next launch: -> not_installed via rollback)
installed --(manifest_sha256 mismatch on launch)--> not_installed (dir wiped, state cleared)
failed --(user clicks retry)--> installing
```

**Validation rules**:
- `status == installed` ⇒ `manifest_sha256` non-empty AND component dir contains `<importable_name>` package.
- On launch: any `status == installing` triggers rollback (FR-012).
- Variant is set at install time only; not re-detected per launch.

## Entity: SizeBudget (build-time, on-disk)

`size-budget.json` (existing, value tightened):

```json
{
  "installer_mb": 500,
  "installed_mb": 900,
  "tolerance_pct": 5,
  "generated_at": "ISO-8601"
}
```

## Entity: SizeReport (build artifact)

`dist/size-report.json` (existing format, extended):

```json
{
  "timestamp": "ISO-8601",
  "installer_mb": 0.0,
  "installed_mb": 0.0,
  "budget_verdict": "pass | fail",
  "top_contributors": [{ "path": "string", "mb": 0.0 }]
}
```

## Entity: Manifest file (per component+variant)

Plain pip requirements format under `manifests/`. Comments + blank lines allowed. Example `manifests/vocal_isolator.cuda.txt`:

```
--extra-index-url https://download.pytorch.org/whl/cu121
torch==2.4.1+cu121
torchaudio==2.4.1+cu121
demucs==4.0.1
```

Hashed by reading raw file bytes — `--extra-index-url` lines included in hash.
