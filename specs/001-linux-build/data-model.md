# Phase 1 — Data Model: Linux Build + GitHub Pages Refresh

This feature ships infrastructure, not domain entities. The "data" being modeled is the shape of release artifacts, CI inputs/outputs, and the public site contract.

## E1 — Release Artifact (per platform)

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `platform` | enum {`windows`, `linux`} | CI job | One artifact per platform per release. |
| `asset_name` | string (stable) | Hardcoded in workflow | Windows: `Videl_Setup.exe`. Linux: `Videl-x86_64.AppImage`. No version in name. |
| `manifest_name` | string (stable) | Derived | `<asset_name>.sig.json`. |
| `version` | semver string | `core/version.py` → `VERSION` | Embedded in manifest; matches release tag `v<version>`. |
| `sha256` | 64-char hex | Computed in CI | Stored inside manifest, signed. |
| `size_bytes` | int | Computed in CI | Stored inside manifest, signed. |
| `signature` | base64url Ed25519 | `tools/sign_installer.py` | Over compact JSON of `{sha256, size, version}`. Same key for both platforms. |
| `release_tag` | string | Git tag trigger | `v<version>`. |
| `download_url` | URL | Derived | `https://github.com/darknessth22/media-utilities/releases/latest/download/<asset_name>`. |

**Invariants**:
- Asset name MUST NOT contain the version (FR-010, R6).
- One manifest per artifact, signed with the same Ed25519 key for cross-platform updater compatibility.
- Both platforms attach to the same release; failure of one MUST NOT block the other (FR-013).

**State transitions**: `built → signed → uploaded → published`. Linux job runs the same sequence as Windows but in parallel.

## E2 — CI Workflow (Build Videl)

| Field | Type | Notes |
|-------|------|-------|
| `triggers` | `push: branches=[master, main, phase1/security-stability], tags=['v*']` + `workflow_dispatch` | Unchanged. |
| `jobs` | map | `build-windows` (existing, renamed for clarity) + `build-linux` (new). |
| `permissions.contents` | `write` | Required to attach release assets. |
| `parallelism` | yes | Two jobs, no `needs:` between them — both publish to the same release independently. |
| `release-publish-strategy` | shared tag | Both jobs reference the same `tag_name`; `softprops/action-gh-release@v2` is idempotent on the tag. |

**`build-linux` job shape**:

| Step | Action | Notes |
|------|--------|-------|
| Checkout | `actions/checkout@v6` | Default. |
| Python | `actions/setup-python@v6` with `python-version: "3.12"` | Mirror Windows. |
| Cache pip | `actions/cache@v5`, key `${{ runner.os }}-pip-${{ hashFiles('requirements-build.txt') }}` | Linux key namespace separate from Windows automatically (`runner.os`). |
| Cache ffmpeg | `actions/cache@v5`, path `bin`, key `${{ runner.os }}-ffmpeg-${{ hashFiles('build_config.json') }}` | Same pattern. |
| Install build deps | `pip install -r requirements-build.txt` | Same file as Windows. |
| Install AppImage tooling | `linuxdeploy`, `linuxdeploy-plugin-qt`, `appimagetool` via direct download into `tools/` | Pin versions; see contracts/ci-workflow.md. |
| Build | `bash build_appimage.sh` | Wraps PyInstaller + linuxdeploy + appimagetool. |
| Read version | Parse `core/version.py` | Same regex pattern, shell-agnostic (`grep -oP`). |
| Sign manifest | `python tools/sign_installer.py …` | Reuse existing script; works cross-platform. |
| Upload artifact | `actions/upload-artifact@v5` | For traceability. |
| Publish release | `softprops/action-gh-release@v2` with `Videl-x86_64.AppImage` + `.sig.json` | Same tag as Windows. |

**Runner**: `ubuntu-22.04` (pinned, not `ubuntu-latest` — R2).

## E3 — GitHub Pages Content

| Section | Required content |
|---------|------------------|
| Hero / intro | Product name, tagline, one-sentence pitch. |
| Feature list | Every user-facing capability present on `master`: subtitle generation, transcript, media downloader, vocal isolation / AI runtime, settings, history, EN/AR with RTL, tutorial, bug reporter, smart updater. Match README features table. |
| Download buttons | TWO buttons, side-by-side on desktop, stacked on mobile. Each: platform icon + label + direct asset URL. |
| Supported platforms note | "Windows 10+ · Linux x86_64 (Ubuntu 22.04+ / glibc 2.35+)". |
| Repo / source link | Existing GitHub repo link preserved. |

**Link contract**:

| Button | Target |
|--------|--------|
| Download for Windows | `https://github.com/darknessth22/media-utilities/releases/latest/download/Videl_Setup.exe` |
| Download for Linux | `https://github.com/darknessth22/media-utilities/releases/latest/download/Videl-x86_64.AppImage` |

**Invariants**:
- Zero broken links at publish time (SC-006).
- Buttons usable on mobile (FR-009 acceptance #3).
- Feature list aligns with README (FR-008).

## E4 — In-app Updater Inputs

| Field | Type | Notes |
|-------|------|-------|
| `runtime_platform` | enum {`windows-frozen`, `linux-appimage`, `dev`} | Detect via `sys.platform` + `sys.frozen` + `os.environ.get("APPIMAGE")`. |
| `appimage_path` | path \| None | `os.environ["APPIMAGE"]` when set; otherwise fall back to storefront. |
| `download_url` | URL | Per-platform direct-asset URL. |
| `manifest_url` | URL | `<download_url>.sig.json`. |
| `replace_strategy` | enum {`inno-silent`, `appimage-replace`, `open-browser`} | Selected from `runtime_platform`. |

**Invariants**:
- Manifest verification MUST happen before any file replace (existing Ed25519 check, unchanged).
- If `appimage_path` is not writable, updater MUST surface a clear error rather than silently failing.
