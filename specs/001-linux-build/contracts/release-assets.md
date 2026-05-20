# Contract — Release Assets & Public URLs

Public, stable surface. Breaking any guarantee here breaks existing installs (in-app updater) and the GitHub Pages site simultaneously.

## Stable URLs (FR-010)

| Purpose | URL |
|---------|-----|
| Windows installer | `https://github.com/darknessth22/media-utilities/releases/latest/download/Videl_Setup.exe` |
| Windows installer manifest | `https://github.com/darknessth22/media-utilities/releases/latest/download/Videl_Setup.exe.sig.json` |
| Linux AppImage | `https://github.com/darknessth22/media-utilities/releases/latest/download/Videl-x86_64.AppImage` |
| Linux AppImage manifest | `https://github.com/darknessth22/media-utilities/releases/latest/download/Videl-x86_64.AppImage.sig.json` |
| Latest release page | `https://github.com/darknessth22/media-utilities/releases/latest` |
| GitHub Releases JSON API | `https://api.github.com/repos/darknessth22/media-utilities/releases/latest` |

Asset filenames MUST NOT include the version. The version lives in:
- the release tag (`v<x.y.z>`),
- the signed manifest's `version` field,
- `core/version.py:VERSION` embedded inside the artifact.

## Signed manifest schema (existing, unchanged)

```json
{
  "sha256": "<64-char lowercase hex>",
  "size": <integer bytes>,
  "version": "<x.y.z>",
  "sig": "<urlsafe-b64 Ed25519 signature over compact JSON of {sha256,size,version}>"
}
```

Same schema and same Ed25519 key for both platforms. The in-app updater verifies the signature using the public key baked into `core/_signing.py:PUBLIC_KEY_B64`.

## Per-release attachments

Every published release MUST include all four files when both jobs succeed:

- `Videl_Setup.exe`
- `Videl_Setup.exe.sig.json`
- `Videl-x86_64.AppImage`
- `Videl-x86_64.AppImage.sig.json`

If one platform's build fails, the release still publishes with the surviving pair (FR-013). The failing platform's button on GitHub Pages will 404 on `/releases/latest/download/…` until the next successful build — acceptable per FR-013 semantics.

## Updater client contract

The Linux build of `core/updater.py` MUST:

1. Detect AppImage runtime via `os.environ.get("APPIMAGE")`.
2. Fetch `Videl-x86_64.AppImage.sig.json`, verify Ed25519 signature, parse `sha256` + `size`.
3. Stream `Videl-x86_64.AppImage` to a temp file on the same filesystem as `$APPIMAGE`, verifying sha256 + size as it goes.
4. `chmod 0755` the temp file.
5. `os.replace(tmp, os.environ["APPIMAGE"])` for atomic swap.
6. Relaunch via `os.execv(os.environ["APPIMAGE"], [os.environ["APPIMAGE"], *sys.argv[1:]])` and exit.
7. On any failure (not writable, sig mismatch, network), fall back to opening `STOREFRONT_URL` in the browser, same as current dev-mode fallback.

The Windows path (`Videl_Setup.exe` + Inno silent install + RestartManager) is unchanged.
