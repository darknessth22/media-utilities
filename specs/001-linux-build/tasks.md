# Tasks: Linux Build + GitHub Pages Refresh

**Input**: Design documents from `/specs/001-linux-build/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/{ci-workflow.md, release-assets.md, pages-site.md}, quickstart.md

**Tests**: Manual smoke tests per `quickstart.md` only — no new automated tests requested in spec. No pytest tasks added beyond ensuring existing suite still passes.

**Organization**: Tasks grouped by user story from spec.md. US1 (Linux artifact runs end-to-end on user machine) and US2 (CI pipeline produces+publishes that artifact) are both P1 and partially overlap: US2 produces what US1 validates. Treated as separate phases for traceability; US1 packaging tasks (build script, spec edits, path/updater code) are prerequisites US2's CI job invokes.

## Format: `[ID] [P?] [Story] Description with file path`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project-level scaffolding shared by every story.

- [x] T001 [P] Add `linux` block to `build_config.json` with `ffmpeg.url`, `ffmpeg.sha256` (or `sha256_url`), and `strip_prefix` matching the johnvansickle static linux-x64 ffmpeg+ffprobe build — mirrors the existing Windows `gyan.dev` entry. File: `build_config.json`.
- [x] T002 [P] Create `tools/` placeholder via `.gitkeep` and add `tools/*.AppImage` to `.gitignore` so locally downloaded `linuxdeploy*`, `appimagetool*` binaries are not committed. Files: `tools/.gitkeep`, `.gitignore`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Cross-platform path/runtime fixes every downstream story depends on. Must land before US1 packaging or US2 CI work can produce a runnable artifact.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T003 Audit and fix user-data directory resolution to branch on `sys.platform`: use `${XDG_CONFIG_HOME:-$HOME/.config}/Videl/` for settings + history and `${XDG_DATA_HOME:-$HOME/.local/share}/Videl/ai_packages/` for the AI package cache on Linux (Windows path unchanged). File: `utils/paths.py` (or wherever `%APPDATA%` is currently resolved — locate via Grep on `APPDATA`/`LOCALAPPDATA`).
- [x] T004 [P] Grep the repo for hardcoded `\\`, drive letters, and `os.name == 'nt'` shortcuts in resource lookups (`gui/`, `core/`); replace with `pathlib.Path` + `sys.platform` branches as needed so all resource paths resolve on case-sensitive filesystems (FR-006). Files: any offending modules under `core/` and `gui/`.
- [x] T005 [P] Confirm `core/version.py:VERSION` is the single source of truth and is shell-parseable on both bash and PowerShell (e.g. matches `^VERSION\s*=\s*"<x.y.z>"`). Adjust spacing/quoting if a regex collision exists; do NOT bump the version here. File: `core/version.py`.

**Checkpoint**: Foundation ready — both P1 stories (US1 packaging, US2 CI) can now proceed in parallel.

---

## Phase 3: User Story 1 — Linux user installs Videl from official download (Priority: P1) 🎯 MVP

**Goal**: A user on Ubuntu 22.04+ downloads `Videl-x86_64.AppImage` from a GitHub release, launches it, and every tab works end-to-end.

**Independent Test**: Build the AppImage locally per `quickstart.md` §A, then run `quickstart.md` §B smoke checklist on a clean Ubuntu 22.04 (or container/VM). All boxes tick green.

### Implementation for User Story 1

- [x] T006 [US1] Split `media_util_gui.spec` so Windows-only `datas`/`binaries` (Inno-related, Windows-specific DLLs) are guarded behind `sys.platform == 'win32'` and a `linux` branch collects `bin/ffmpeg`+`bin/ffprobe` plus any Linux-specific Qt plugin data; keep `hiddenimports` cross-platform. File: `media_util_gui.spec`.
- [x] T007 [US1] Create `build_appimage.sh` that: (a) sources `build_config.json` for the Linux ffmpeg URL+sha256, (b) downloads + verifies ffmpeg/ffprobe into `bin/` if missing, (c) runs `pyinstaller media_util_gui.spec` (one-dir mode), (d) stages output into `AppDir/usr/bin` + writes `AppDir/Videl.desktop` and `AppDir/Videl.png`, (e) invokes `tools/linuxdeploy-x86_64.AppImage --plugin qt --output appimage --appdir AppDir`, (f) renames the result to `dist/Videl-x86_64.AppImage`. Script MUST `set -euo pipefail`. File: `build_appimage.sh`.
- [x] T008 [P] [US1] Add minimal AppImage desktop integration assets: `assets/linux/Videl.desktop` (Categories=AudioVideo;Utility; Exec=Videl; Icon=Videl) and `assets/linux/Videl.png` (256×256, derived from existing app icon). Referenced by `build_appimage.sh` when staging `AppDir/`. Files: `assets/linux/Videl.desktop`, `assets/linux/Videl.png`.
- [x] T009 [US1] Extend `build_executable.py` so `python build_executable.py` on Linux dispatches to `build_appimage.sh` (subprocess) and on Windows preserves the existing PyInstaller+Inno flow; do not duplicate logic. File: `build_executable.py`.
- [x] T010 [US1] Extend `core/updater.py` to detect the runtime platform (`sys.platform == 'linux'` + `os.environ.get('APPIMAGE')`) and select the Linux replace strategy: fetch `Videl-x86_64.AppImage.sig.json`, verify Ed25519, stream-download `Videl-x86_64.AppImage` to a temp file on the same filesystem as `$APPIMAGE`, verify sha256+size, `chmod 0755`, `os.replace()` over `$APPIMAGE`, then `os.execv()` to relaunch. On read-only or sig-mismatch failure fall back to the existing storefront-browser open path. File: `core/updater.py`.
- [x] T011 [P] [US1] Update README to document the Linux build: prerequisites (`libfuse2`, glibc 2.35+), the `build_appimage.sh` flow, and the user-facing supported-distro line `Windows 10+ · Linux x86_64 (Ubuntu 22.04+ / glibc 2.35+)`. File: `README.md`.
- [x] T012 [P] [US1] Add Linux build instructions and supported-distros note to the in-app tutorial. Update `_TUTORIAL_DATA_EN` AND `_TUTORIAL_DATA_AR` in the same edit so the two lists stay aligned entry-for-entry. File: `gui/tabs/tutorial_section.py`.
- [x] T013 [P] [US1] Add any new UI strings introduced by T010/T012 (e.g. "Update failed — AppImage location not writable") to `locales/en.json` AND `locales/ar.json` in the same change. Files: `locales/en.json`, `locales/ar.json`.
- [ ] T014 [US1] Run `quickstart.md` §A locally on Ubuntu 22.04 (or container) and confirm `dist/Videl-x86_64.AppImage` produced; then walk `quickstart.md` §B smoke checklist and tick every box (gates SC-003).

**Checkpoint**: User Story 1 complete — a hand-built AppImage runs on a clean Linux machine with every tab functional.

---

## Phase 4: User Story 2 — Automated Linux build pipeline on every release (Priority: P1)

**Goal**: Pushing `v<x.y.z>` triggers a `build-linux` job in parallel with `build-windows`; both attach signed artifacts to the same release. Failure of one MUST NOT block the other.

**Independent Test**: Push a throwaway `v0.0.0-test` tag on a sandbox branch (or use `workflow_dispatch`); confirm both jobs run in parallel and both assets+manifests appear on the release. Delete the test release after.

### Implementation for User Story 2

- [x] T015 [US2] Rename the existing Windows job inside `.github/workflows/build.yml` from its current id to `build-windows` (if not already), keeping all current steps intact. File: `.github/workflows/build.yml`.
- [x] T016 [US2] Add the `build-linux` job to `.github/workflows/build.yml` per `contracts/ci-workflow.md` step list: `runs-on: ubuntu-22.04`; checkout v6 → setup-python v6 (3.12) → cache pip + cache `bin` ffmpeg keyed on `${{ runner.os }}-…` → `pip install -r requirements-build.txt` → download+chmod pinned `linuxdeploy-x86_64.AppImage`, `linuxdeploy-plugin-qt-x86_64.AppImage`, `appimagetool-x86_64.AppImage` into `tools/` → `bash build_appimage.sh` → parse `core/version.py` into `steps.version.outputs.version` → run `python tools/sign_installer.py dist/Videl-x86_64.AppImage --version "${{ steps.version.outputs.version }}" --priv-key "$VIDEL_PRIV_KEY_PEM" --out dist/Videl-x86_64.AppImage.sig.json` → `actions/upload-artifact@v5` (`Videl-AppImage-${{ github.sha }}`) → on `startsWith(github.ref, 'refs/tags/v')`, `softprops/action-gh-release@v2` with `tag_name: v${{ steps.version.outputs.version }}`, files `dist/Videl-x86_64.AppImage` + `dist/Videl-x86_64.AppImage.sig.json`, `fail_on_unmatched_files: true`. No `needs:` linking it to `build-windows`. File: `.github/workflows/build.yml`.
- [x] T017 [US2] Set `permissions: contents: write` at the workflow or job level for `build-linux` (match the Windows job). Verify there is NO `if: success()` cross-reference between the two jobs that would couple their failures (FR-013). File: `.github/workflows/build.yml`.
- [x] T018 [US2] Confirm `tools/sign_installer.py` works on Linux as-is (cryptography + Ed25519 PEM input). If a Windows-only path call sneaks in (e.g. `\\` in default paths), fix it. File: `tools/sign_installer.py` (read first — likely already cross-platform per `requirements-build.txt:cryptography`).
- [ ] T019 [US2] Trigger a sandbox tag (or `workflow_dispatch`) to validate the pipeline end-to-end: both jobs run in parallel, both assets + `.sig.json` files appear on the release, total wall time within 1.5× the prior Windows-only baseline (SC-005). Then delete the throwaway release+tag.

**Checkpoint**: User Story 2 complete — every `v*` tag now ships both Windows installer and Linux AppImage automatically.

---

## Phase 5: User Story 3 — GitHub Pages site reflects new features and offers Linux download (Priority: P2)

**Goal**: Visitors to the Pages site see the current feature set and can download either platform via stable URLs.

**Independent Test**: Visit the published site in desktop + mobile (375 px) viewports, run the `curl -ILfsS` link sweep from `quickstart.md` §D, click both download buttons.

### Implementation for User Story 3

- [x] T020 [US3] On a `gh-pages` worktree (`git worktree add ../media-utilities-pages gh-pages`), update `index.html` to include the required sections from `contracts/pages-site.md` in order: head meta + OpenGraph, hero + tagline, download section with two side-by-side buttons (Windows + Linux) stacking on ≤375 px, supported-platforms line `Windows 10+ · Linux x86_64 (Ubuntu 22.04+ / glibc 2.35+)`, features section listing every capability on `master` (subtitle generation, transcript, media downloader, vocal isolation/AI runtime, settings+history, EN/AR with full RTL, in-app tutorial, bug reporter, smart updater), footer with repo link. File (on `gh-pages` branch): `index.html`.
- [x] T021 [US3] Wire the two download buttons to the stable URLs verbatim from `contracts/release-assets.md`: Windows → `https://github.com/darknessth22/media-utilities/releases/latest/download/Videl_Setup.exe`, Linux → `https://github.com/darknessth22/media-utilities/releases/latest/download/Videl-x86_64.AppImage`. Both buttons MUST have ≥44 px tap height on mobile (FR-009). File (on `gh-pages` branch): `index.html`.
- [x] T022 [P] [US3] Add `<meta http-equiv="Cache-Control" content="no-cache">` to `<head>` and append `?v=<YYYY-MM-DD>` cache-buster query strings to any CSS/JS hrefs to mitigate stale-`index.html` caching. File (on `gh-pages` branch): `index.html`.
- [x] T023 [P] [US3] Update or add any platform icons used by the buttons under `assets/` on the `gh-pages` branch (Windows logo + Tux/penguin or generic Linux glyph). Inlined Tux SVG path in button markup — no separate asset file required. Files (on `gh-pages` branch): `index.html` (inline SVGs).
- [ ] T024 [US3] Run the link-verification sweep from `quickstart.md` §D: `curl -ILfsS` against both download URLs, the repo link, and any in-page anchors. All MUST return 200 (or redirect chain to 200). Resolve any broken link before merging the `gh-pages` update (gates SC-006). **Partial sweep done 2026-05-18:** repo/releases/issues/Windows installer → 200; AppImage URL → 404 (expected — no Linux release tagged yet; re-run after Phase 4 T019).

**Checkpoint**: User Story 3 complete — site current, both platforms downloadable, mobile-friendly, zero broken links.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final cleanup once all stories land.

- [x] T025 [P] Refresh `.wolf/anatomy.md` with entries for new files (`build_appimage.sh`, `assets/linux/Videl.desktop`, `assets/linux/Videl.png`, updated `core/updater.py`, `media_util_gui.spec`, `.github/workflows/build.yml`). File: `.wolf/anatomy.md`.
- [x] T026 [P] Append a Linux-build memory entry (decisions: AppImage, ubuntu-22.04, in-place updater, stable asset name) to `.wolf/cerebrum.md` under Key Learnings. File: `.wolf/cerebrum.md`.
- [x] T027 Verify each task in this `tasks.md` is checked off; flip remaining `- [ ]` to `- [x]` per the project's task-checklist rule. File: `specs/001-linux-build/tasks.md`.
- [x] T028 Bump `APP_VERSION` in `main.py` / `core/version.py` and stage the Deployment Protocol command sequence (`git add . && git commit && git tag v<x.y.z>`) ready for the user to push, per the Videl CI/CD Deployment Protocol. Files: `main.py`, `core/version.py`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** — no dependencies.
- **Foundational (Phase 2)** — depends on Setup; BLOCKS US1 and US2.
- **US1 (Phase 3)** — depends on Foundational; produces the build script + spec changes + updater code that the US2 CI job invokes. T014 (smoke) gates story complete.
- **US2 (Phase 4)** — depends on Foundational; T016 invokes `build_appimage.sh` from T007 and the spec edits from T006, so US2's green pipeline run (T019) requires US1's T006+T007+T008+T009 to be merged first. The updater work (T010) and docs (T011–T013) can run truly in parallel to US2.
- **US3 (Phase 5)** — depends on Foundational only; lives on a separate branch (`gh-pages`) so it can be authored in parallel with US1/US2. T024 link sweep is most meaningful AFTER US2's first green tag run actually publishes a Linux asset, but the page can ship earlier (the link will 404 until the first release).
- **Polish (Phase 6)** — depends on US1+US2+US3 landed.

### User Story Dependencies

- **US1 → US2** (soft): US2's CI job calls into US1's packaging script. Practically, T006–T009 must merge before T019 will pass green.
- **US3** is independent of US1/US2 code-wise; only the published link target depends on US2's first successful tag run.

### Within Each User Story

- US1: spec edits (T006) before build script (T007); build script before `build_executable.py` dispatch (T009); local smoke (T014) gates story exit.
- US2: existing-job rename (T015) before adding peer job (T016); permissions (T017) before sandbox run (T019).
- US3: HTML content (T020) before link wiring (T021); link sweep (T024) gates story exit.

### Parallel Opportunities

- **Phase 1**: T001 and T002 are independent files → parallel.
- **Phase 2**: T004 and T005 touch different concerns from T003 → can run in parallel after T003 lands.
- **US1**: T008 (assets), T011 (README), T012 (tutorial), T013 (locales) are file-disjoint and can land in parallel once T006/T007/T010 are in flight.
- **US3**: T022 (cache meta) and T023 (icons) are independent of T020/T021 content.
- **US1 ↔ US3**: fully parallelizable (different branches).

---

## Parallel Example: User Story 1 documentation tasks

```bash
# After T006/T007/T010 land, these can run concurrently:
Task: "Update README.md with Linux build instructions + supported-distros line"
Task: "Add Linux build steps to gui/tabs/tutorial_section.py (_TUTORIAL_DATA_EN + _TUTORIAL_DATA_AR)"
Task: "Add new updater error strings to locales/en.json AND locales/ar.json"
Task: "Add assets/linux/Videl.desktop + Videl.png"
```

---

## Implementation Strategy

### MVP First (US1 + US2 — both P1)

1. Phase 1 Setup.
2. Phase 2 Foundational (CRITICAL — blocks all stories).
3. Phase 3 US1 packaging + updater + local smoke (T006–T014).
4. Phase 4 US2 CI pipeline (T015–T019) — produces the first signed AppImage on a real release.
5. **STOP and VALIDATE**: download the published AppImage on a clean Ubuntu 22.04 machine, run `quickstart.md` §B again.
6. Ship.

### Incremental Delivery

1. Setup + Foundational → land first.
2. US1 packaging code → AppImage buildable locally; ship internal RC builds.
3. US2 CI → next tag publishes Linux asset automatically; users can now install.
4. US3 site refresh → discovery; users actually find the download.
5. Polish.

### Parallel Team Strategy

- Dev A: US1 (Phase 3 — packaging + updater).
- Dev B: US2 (Phase 4 — CI wiring) — blocked on Dev A's T006/T007 merge before sandbox run; can author the YAML in parallel.
- Dev C: US3 (Phase 5 — `gh-pages` content) — fully independent until publish.

---

## Notes

- `[P]` tasks touch disjoint files and have no dependency on incomplete tasks in the same phase.
- `[Story]` label maps task to a spec.md user story for traceability.
- Per project rule: every UI string added in en.json MUST have a matching ar.json entry in the same change (T013, T012).
- Per project rule: tutorial + README + Arabic translation are part of feature definition of done (T011, T012, T013).
- Per project deployment protocol: T028 reminds to bump `APP_VERSION` and produces the `git tag v<x.y.z>` sequence — do NOT skip; that is the CI trigger that ships the artifact users see.
- Per OpenWolf rules: refresh `.wolf/anatomy.md` after new files land (T025); log learnings to `.wolf/cerebrum.md` (T026).
- Commit after each task or logical group; stop at checkpoints to validate each story independently.
