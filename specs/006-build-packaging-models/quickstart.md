# Quickstart — Build & AI Packaging Feature

## Build locally (Windows)

```bat
python build_executable.py
```

What happens:
1. Loads `build_config.json`, downloads pinned ffmpeg (cached).
2. Creates / reuses `.build_venv` from `requirements-build.txt` — no AI packages.
3. **NEW**: downloads Python 3.12 embeddable zip into `runtime/python/`, runs `get-pip.py` against it.
4. PyInstaller builds with `media_util_gui.spec` excludes (rembg, demucs, torch, ...).
5. `tests/test_build_excludes.py` runs — fails build if any excluded package leaked.
6. Inno Setup compiles `Output/Videl_Setup.exe`.
7. Size measured vs `size-budget.json` (500 MB / 900 MB / 5 % tol).
8. `dist/size-report.json` written.

Failure modes:
- Budget exceeded → exits non-zero, prints top-10 contributors.
- Excluded package leaked → `pytest` exits non-zero, prints offending paths.

## Build in CI

Push to `main` → `.github/workflows/build.yml` runs the same `build_executable.py`. Artifact uploaded: `Videl_Setup.exe` + `size-report.json`.

## End-user runtime install (manual smoke test)

1. Install `Videl_Setup.exe` on a clean Windows VM (no Python, no torch, no rembg).
2. Open Videl → click **Background Eraser** tab.
3. Expect: in-tab banner "AI components not installed — ~200 MB will install to `%LOCALAPPDATA%\Videl\ai_packages\bg_eraser\`".
4. Click **Install**. Expect: progress lines stream into the tab; main window stays movable; **no second window or splash appears**.
5. On finish, click **Erase Background** with a sample image — works without restart.
6. Close + reopen Videl → AI ready immediately.

Failure smoke tests:
- Disconnect network mid-install → clear error, retry button works.
- Kill Videl mid-install → next launch: state rolled back to "not installed", banner re-appears.

## Vocal Isolator with GPU

1. On a CUDA machine, click install → confirm pre-install dialog shows ~2.5 GB.
2. On a non-CUDA machine, same click shows ~250 MB (CPU variant auto-picked).

## Bumping pinned manifests for a release

1. Edit `manifests/<component>.txt` (and `.cuda.txt` if applicable) to new exact versions.
2. Bump `core/version.py`.
3. Ship.
4. End-user opens app → manifest sha mismatches → component dir wiped → user re-prompted to install. No code change required.
