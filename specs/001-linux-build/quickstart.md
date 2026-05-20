# Quickstart — Linux Build & Smoke Test

Two audiences: maintainer building locally, and reviewer smoke-testing a release candidate AppImage.

## A. Build the AppImage locally (Ubuntu 22.04 host or container)

```bash
# 1. System packages (one time)
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv python3-pip libfuse2 libxcb-cursor0 \
    libxkbcommon0 libegl1 libgl1 libpulse0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1
# libfuse2 is required to RUN AppImages on Ubuntu 22.04+.

# 2. Project venv
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-build.txt

# 3. AppImage tooling (one time, into ./tools/)
mkdir -p tools
curl -L -o tools/linuxdeploy-x86_64.AppImage \
  https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage
curl -L -o tools/linuxdeploy-plugin-qt-x86_64.AppImage \
  https://github.com/linuxdeploy/linuxdeploy-plugin-qt/releases/download/continuous/linuxdeploy-plugin-qt-x86_64.AppImage
curl -L -o tools/appimagetool-x86_64.AppImage \
  https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x tools/*.AppImage

# 4. Build
bash build_appimage.sh
# Output: dist/Videl-x86_64.AppImage
```

Expected wall time: ~6–10 min on first run (PyInstaller cold cache + ffmpeg download), ~3–5 min on incremental runs.

## B. Smoke test the AppImage

```bash
chmod +x dist/Videl-x86_64.AppImage
./dist/Videl-x86_64.AppImage
```

Manual checklist — run one task per tab. All MUST succeed; this gates the release (SC-003).

- [ ] **Launch**: GUI opens within 5 s. No console errors. Title bar reads `Videl`.
- [ ] **Language switch**: Settings → switch to Arabic → entire UI mirrors RTL, strings render in Arabic. Switch back to English.
- [ ] **Subtitles tab**: pick a short local video → generate subtitles → output `.srt` written next to source. (AI runtime install prompt appears on first run — accept.)
- [ ] **Transcript tab**: same source → transcript produced.
- [ ] **Downloader tab**: paste a public YouTube URL → download completes → file appears in chosen output dir.
- [ ] **Vocal isolation**: short audio clip → vocals/instrumental split written.
- [ ] **Settings persistence**: change theme + output dir → quit → relaunch → settings retained. Confirm config under `~/.config/Videl/`.
- [ ] **History**: previous jobs visible in history tab.
- [ ] **Tutorial**: tutorial section opens, EN + AR copy both readable.
- [ ] **Bug reporter**: form opens (do not actually submit unless testing infra).
- [ ] **Updater**: trigger "Check for updates" → either "up to date" or download-prompt appears within 3 s timeout. Do not accept install during smoke test.

## C. Test the in-place updater swap (release candidate only)

Pre-req: a *prior* release exists with a lower version.

```bash
# Run the OLD AppImage; it should detect the new release and prompt.
chmod +x Videl-x86_64.AppImage.OLD
./Videl-x86_64.AppImage.OLD
# Click "Update", let it download + verify + replace + relaunch.
# After relaunch, About dialog MUST show the new version.
# The file at the original path MUST now have the new sha256.
sha256sum Videl-x86_64.AppImage.OLD
```

If the AppImage is in a read-only location (e.g. `/opt/videl/`), the updater MUST surface a clear error and open the storefront, not crash.

## D. Smoke-test the GitHub Pages refresh

After publishing the updated `gh-pages` branch:

```bash
# Replace with the canonical site URL once known
URL=https://darknessth22.github.io/media-utilities/
curl -ILfsS "$URL" >/dev/null && echo "site OK"
curl -ILfsS "https://github.com/darknessth22/media-utilities/releases/latest/download/Videl_Setup.exe" | head -1
curl -ILfsS "https://github.com/darknessth22/media-utilities/releases/latest/download/Videl-x86_64.AppImage" | head -1
```

Then in a browser:

- [ ] Page loads, hero visible, both download buttons visible above the fold (desktop).
- [ ] Open DevTools mobile emulation (375 px) → buttons stack, remain tappable.
- [ ] Feature list contains every item from `contracts/pages-site.md` § Features.
- [ ] Click "Download for Windows" → browser starts downloading `Videl_Setup.exe`.
- [ ] Click "Download for Linux" → browser starts downloading `Videl-x86_64.AppImage`.
- [ ] Footer repo link works.
