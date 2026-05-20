# Contract — CI Workflow (Build Videl)

Defines what `.github/workflows/build.yml` MUST produce after this feature lands. Existing Windows job remains; this contract adds the Linux peer.

## Triggers (unchanged)

```yaml
on:
  push:
    branches: [master, main, phase1/security-stability]
    tags: ['v*']
  workflow_dispatch:
```

Linux artifact attaches to release ONLY on `tags: v*` runs (mirrors Windows behavior — branch pushes build but don't publish).

## Jobs

| Job ID | Runner | Publishes Release Asset? | Depends on |
|--------|--------|--------------------------|------------|
| `build-windows` | `windows-latest` | yes (on tag) | — |
| `build-linux` | `ubuntu-22.04` | yes (on tag) | — |

Both jobs run in parallel. Neither has `needs:` on the other. `softprops/action-gh-release@v2` is idempotent against the same `tag_name`, so both jobs append their assets to the same release independently.

## `build-linux` required steps (in order)

1. **Checkout** — `actions/checkout@v6`.
2. **Setup Python 3.12** — `actions/setup-python@v6`, `python-version: "3.12"`.
3. **Cache pip** — `actions/cache@v5`, path `~/.cache/pip`, key `${{ runner.os }}-pip-${{ hashFiles('requirements-build.txt') }}`.
4. **Cache ffmpeg** — `actions/cache@v5`, path `bin`, key `${{ runner.os }}-ffmpeg-${{ hashFiles('build_config.json') }}`.
5. **Install build deps** — `pip install -r requirements-build.txt`.
6. **Install AppImage tooling** — download pinned `linuxdeploy-x86_64.AppImage`, `linuxdeploy-plugin-qt-x86_64.AppImage`, `appimagetool-x86_64.AppImage` into `tools/`; `chmod +x`.
7. **Build AppImage** — `bash build_appimage.sh`. Script MUST: (a) ensure `bin/ffmpeg` + `bin/ffprobe` present (download per `build_config.json:linux.*` if cache miss); (b) run `pyinstaller media_util_gui.spec` (one-dir); (c) stage into `AppDir/`; (d) run `linuxdeploy --plugin qt --output appimage`; (e) write final asset to `dist/Videl-x86_64.AppImage`.
8. **Read app version** — parse `core/version.py` `VERSION = "x.y.z"` (use `grep -oP` or `python -c`). Export to `$GITHUB_OUTPUT` as `version`.
9. **Sign manifest** — `python tools/sign_installer.py dist/Videl-x86_64.AppImage --version "${{ steps.version.outputs.version }}" --priv-key "$VIDEL_PRIV_KEY_PEM" --out dist/Videl-x86_64.AppImage.sig.json`. Reuses `VIDEL_PRIV_KEY_PEM` secret.
10. **Upload artifact (CI)** — `actions/upload-artifact@v5`, name `Videl-AppImage-${{ github.sha }}`, path `dist/Videl-x86_64.AppImage`, `if-no-files-found: error`, retention 30 days.
11. **Publish GitHub Release** (tag runs only) — `softprops/action-gh-release@v2`, `tag_name: v${{ steps.version.outputs.version }}`, files include `dist/Videl-x86_64.AppImage` + `dist/Videl-x86_64.AppImage.sig.json`. `fail_on_unmatched_files: true`.

## Required permissions

```yaml
permissions:
  contents: write
```

Same as Windows job.

## Required secrets

| Secret | Purpose |
|--------|---------|
| `VIDEL_PRIV_KEY_PEM` | Ed25519 PEM matching `core/_signing.py:PUBLIC_KEY_B64`. Shared with Windows job — no new key. |
| `SENDGRID_API_KEY` | Only needed at build time if bug-reporter API key is baked in like Windows; replicate Windows step exactly. |

## Failure semantics (FR-013)

- `build-linux` failure MUST NOT cancel `build-windows` and vice versa. Both jobs declared at the same level under `jobs:` with no `needs:` cross-link → GitHub Actions runs them independently by default. No `if: success()` cross-references between them.
- The release is created by whichever job runs `softprops/action-gh-release@v2` first; the second job appends. If one job fails before its publish step, the release still exists with the surviving artifact.

## Stable asset names

| Platform | Asset | Manifest |
|----------|-------|----------|
| Windows  | `Videl_Setup.exe` | `Videl_Setup.exe.sig.json` |
| Linux    | `Videl-x86_64.AppImage` | `Videl-x86_64.AppImage.sig.json` |

These names are part of the public URL contract (see `release-assets.md`). Changing them is a breaking change for existing users' in-app updater and for the GitHub Pages download buttons.

## Non-goals

- No clean-vs-polluted parity check on Linux (R7).
- No ARM64 build.
- No Flatpak / Snap / deb / rpm.
- No code signing beyond the Ed25519 manifest (no GPG, no notarization).
