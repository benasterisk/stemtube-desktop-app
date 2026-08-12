#!/usr/bin/env bash
#
# Build the tiny StemTube graphical installer AppImage.
# Run inside WSL2 / a Linux box. Output: StemTube-Installer-x86_64.AppImage
#
# The installer bundles zenity (for GTK dialogs) and is packaged with the
# modern type2 runtime, which self-extracts when FUSE is absent — so the
# installer itself needs no libfuse2 either. End to end: no FUSE, no sudo.
#
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
WORK="${WORK:-/tmp/stemtube-installer-build}"
OUT="${OUT:-$SRC/StemTube-Installer-x86_64.AppImage}"
APPDIR="$WORK/AppDir"

echo "== StemTube installer build =="
rm -rf "$WORK"; mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib"

# ── bundle zenity if it's available on the build box (optional) ─────────────
ZEN_BIN="$(command -v zenity || true)"
if [ -n "$ZEN_BIN" ]; then
  echo "Bundling zenity from $ZEN_BIN"
  cp "$ZEN_BIN" "$APPDIR/usr/bin/zenity"
  SKIP='libc\.|libm\.|libdl\.|libpthread\.|librt\.|ld-linux|libgtk-3|libgdk-3|libglib-2|libgobject|libgio|libpango|libcairo|libgdk_pixbuf|libX11|libatk|libharfbuzz|libfreetype|libfontconfig|libz\.'
  ldd "$ZEN_BIN" | awk '/=> \// {print $3}' | while read -r lib; do
    base="$(basename "$lib")"
    echo "$base" | grep -Eq "$SKIP" && continue
    cp -Lu "$lib" "$APPDIR/usr/lib/" 2>/dev/null || true
  done
else
  echo "NOTE: zenity not on the build box — the installer will use the system"
  echo "      zenity at run time (present on virtually every desktop Linux)."
fi

# ── installer payload ──────────────────────────────────────────────────────
cp "$SRC/AppRun"                     "$APPDIR/AppRun"
cp "$SRC/install-gui.sh"             "$APPDIR/install-gui.sh"
cp "$SRC/stemtube-installer.desktop" "$APPDIR/stemtube-installer.desktop"
cp "$SRC/stemtube-installer.png"     "$APPDIR/stemtube-installer.png"
cp "$SRC/stemtube.png"               "$APPDIR/stemtube.png"
chmod +x "$APPDIR/AppRun" "$APPDIR/install-gui.sh"

# ── appimagetool + runtime (fetch up front to avoid mid-build download) ─────
cd "$WORK"
if [ ! -x ./appimagetool ]; then
  echo "Fetching appimagetool…"
  curl -fL -o appimagetool "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x appimagetool
fi
if [ ! -f runtime-x86_64 ]; then
  echo "Fetching AppImage type2 runtime (FUSE-optional)…"
  curl -fL -o runtime-x86_64 "https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64"
fi

echo "Packaging…"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 ./appimagetool \
  --runtime-file "$WORK/runtime-x86_64" \
  "$APPDIR" "$OUT"

chmod +x "$OUT"
echo "== DONE =="
ls -lh "$OUT"
sha256sum "$OUT"
