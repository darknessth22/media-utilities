#!/usr/bin/env bash
# Build Videl-x86_64.AppImage on Ubuntu 22.04+ (glibc 2.35+).
#
# Prereqs (one time):
#   - libfuse2 installed on host
#   - tools/linuxdeploy-x86_64.AppImage
#   - tools/linuxdeploy-plugin-qt-x86_64.AppImage
#   - tools/appimagetool-x86_64.AppImage          (all chmod +x)
#   - active venv with requirements-build.txt installed
#
# Output: dist/Videl-x86_64.AppImage

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

BIN_DIR="$ROOT/bin"
TOOLS_DIR="$ROOT/tools"
APPDIR="$ROOT/AppDir"
DIST="$ROOT/dist"

LINUXDEPLOY="$TOOLS_DIR/linuxdeploy-x86_64.AppImage"
LINUXDEPLOY_QT="$TOOLS_DIR/linuxdeploy-plugin-qt-x86_64.AppImage"

# Linuxdeploy must be invoked from outside an existing AppImage mount in CI
# (FUSE-less GitHub runners use --appimage-extract-and-run automatically when
# the AppImages have --no-sandbox-like behavior). We force extract-and-run.
export APPIMAGE_EXTRACT_AND_RUN=1

# ---------------------------------------------------------------------------
# 1) Resolve ffmpeg pin from build_config.json (linux.ffmpeg.*).
# ---------------------------------------------------------------------------
need_jq() {
    if ! command -v jq >/dev/null 2>&1; then
        echo "ERROR: jq required to parse build_config.json. apt-get install -y jq" >&2
        exit 1
    fi
}
need_jq

FFMPEG_URL=$(jq -r '.linux.ffmpeg.url' build_config.json)
FFMPEG_SHA=$(jq -r '.linux.ffmpeg.sha256' build_config.json)
FFMPEG_PREFIX=$(jq -r '.linux.ffmpeg.strip_prefix' build_config.json)

if [[ -z "$FFMPEG_URL" || "$FFMPEG_URL" == "null" ]]; then
    echo "ERROR: build_config.json missing linux.ffmpeg.url" >&2
    exit 1
fi
mkdir -p "$BIN_DIR"
if [[ ! -x "$BIN_DIR/ffmpeg" || ! -x "$BIN_DIR/ffprobe" ]]; then
    echo "Downloading ffmpeg static build from $FFMPEG_URL ..."
    TARBALL="$BIN_DIR/ffmpeg.tar.xz"
    curl -fSL --retry 3 -o "$TARBALL" "$FFMPEG_URL"
    if [[ -n "$FFMPEG_SHA" && "$FFMPEG_SHA" != "null" ]]; then
        echo "$FFMPEG_SHA  $TARBALL" | sha256sum -c -
    else
        echo "WARNING: sha256 not pinned — skipping integrity check." >&2
    fi
    echo "Extracting ..."
    # Auto-detect top-level directory inside the tarball if strip_prefix not set
    if [[ -z "$FFMPEG_PREFIX" || "$FFMPEG_PREFIX" == "null" ]]; then
        FFMPEG_PREFIX=$(tar -tJf "$TARBALL" | head -1 | cut -d/ -f1)/
    fi
    tar -xJf "$TARBALL" -C "$BIN_DIR"
    cp "$BIN_DIR/$FFMPEG_PREFIX/ffmpeg" "$BIN_DIR/ffmpeg"
    cp "$BIN_DIR/$FFMPEG_PREFIX/ffprobe" "$BIN_DIR/ffprobe"
    chmod +x "$BIN_DIR/ffmpeg" "$BIN_DIR/ffprobe"
    rm -f "$TARBALL"
    rm -rf "$BIN_DIR/$FFMPEG_PREFIX"
fi
echo "[OK] ffmpeg/ffprobe present in bin/"

# ---------------------------------------------------------------------------
# 2) PyInstaller one-dir build via the shared spec.
# ---------------------------------------------------------------------------
echo "Cleaning previous build/ dist/ AppDir/ ..."
rm -rf build dist "$APPDIR"

echo "Running PyInstaller ..."
pyinstaller media_util_gui.spec --clean --noconfirm

PYI_OUT="$ROOT/dist/Videl"
if [[ ! -d "$PYI_OUT" ]]; then
    echo "ERROR: PyInstaller output not found at $PYI_OUT" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 3) Stage AppDir/
# ---------------------------------------------------------------------------
echo "Staging AppDir/ ..."
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp -r "$PYI_OUT/." "$APPDIR/usr/bin/"

# The PyInstaller EXE is named "Videl"; linuxdeploy expects the Exec'd binary
# to be on PATH inside AppDir/usr/bin/. AppRun (added by linuxdeploy) will set
# LD_LIBRARY_PATH and exec it.
chmod +x "$APPDIR/usr/bin/Videl"

DESKTOP_SRC="$ROOT/assets/linux/Videl.desktop"
ICON_SRC="$ROOT/assets/linux/Videl.png"
if [[ ! -f "$DESKTOP_SRC" || ! -f "$ICON_SRC" ]]; then
    echo "ERROR: missing $DESKTOP_SRC or $ICON_SRC (see T008)." >&2
    exit 1
fi
cp "$DESKTOP_SRC" "$APPDIR/usr/share/applications/Videl.desktop"
cp "$ICON_SRC" "$APPDIR/usr/share/icons/hicolor/256x256/apps/Videl.png"
# linuxdeploy also looks at top-level AppDir/<name>.desktop + <name>.png.
cp "$DESKTOP_SRC" "$APPDIR/Videl.desktop"
cp "$ICON_SRC" "$APPDIR/Videl.png"

# ---------------------------------------------------------------------------
# 4) linuxdeploy + qt plugin → AppImage
# ---------------------------------------------------------------------------
if [[ ! -x "$LINUXDEPLOY" ]]; then
    echo "ERROR: $LINUXDEPLOY missing or not executable (see quickstart.md §A.3)." >&2
    exit 1
fi

mkdir -p "$DIST"

# NOTE: --plugin qt deliberately omitted. PyInstaller's PySide6 hook already
# bundles Qt6 libs + plugins + qml into dist/Videl/_internal/PySide6/Qt/.
# Invoking linuxdeploy-plugin-qt would deploy a *second* Qt (system qt6-base
# 6.2 on ubuntu-22.04) alongside the bundled PySide6 Qt 6.11 — version split
# breaks loading. linuxdeploy without the plugin still scans the ELF for
# NEEDED entries and bundles non-Qt deps (libxcb*, libpulse, libxkbcommon*).
echo "Running linuxdeploy (no qt plugin — PyInstaller handles Qt) ..."
"$LINUXDEPLOY" \
    --appdir "$APPDIR" \
    --desktop-file "$APPDIR/Videl.desktop" \
    --icon-file "$APPDIR/Videl.png" \
    --output appimage

# linuxdeploy writes the output to $PWD; move + rename.
OUT=$(ls -1t Videl*.AppImage 2>/dev/null | head -n1 || true)
if [[ -z "$OUT" ]]; then
    echo "ERROR: linuxdeploy did not produce a Videl*.AppImage in $PWD" >&2
    exit 1
fi
mv "$OUT" "$DIST/Videl-x86_64.AppImage"
chmod +x "$DIST/Videl-x86_64.AppImage"

echo "[OK] dist/Videl-x86_64.AppImage"
