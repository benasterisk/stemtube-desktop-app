#!/usr/bin/env bash
#
# Build stemtube-desktop_2.1.0_amd64.deb — the double-clickable Ubuntu/Debian
# installer (the .exe equivalent). Installing it adds a "StemTube Desktop" menu
# entry; first launch downloads the matching engine (CPU/GPU) and runs it.
#
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
VERSION="${VERSION:-2.1.0}"
PKG="$SRC/pkgroot"
OUT="${OUT:-$SRC/stemtube-desktop_${VERSION}_amd64.deb}"

echo "== StemTube .deb build (v$VERSION) =="
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" \
         "$PKG/usr/bin" \
         "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/512x512/apps" \
         "$PKG/usr/share/doc/stemtube-desktop"

# ── the launcher command ───────────────────────────────────────────────────
install -m 0755 "$SRC/stemtube-run.sh" "$PKG/usr/bin/stemtube"

# ── icon (look next to the script, then in ../installer) ───────────────────
ICON=""
for c in "$SRC/stemtube.png" "$SRC/installer/stemtube.png" "$SRC/../installer/stemtube.png"; do
  [ -f "$c" ] && { ICON="$c"; break; }
done
[ -n "$ICON" ] || { echo "ERROR: stemtube.png icon not found near $SRC"; exit 1; }
install -m 0644 "$ICON" "$PKG/usr/share/icons/hicolor/512x512/apps/stemtube-desktop.png"

# ── desktop entry ──────────────────────────────────────────────────────────
cat > "$PKG/usr/share/applications/stemtube-desktop.desktop" <<'DESK'
[Desktop Entry]
Type=Application
Name=StemTube Desktop
GenericName=Music stem studio
Comment=Turn any song into a multitrack studio
Exec=stemtube
Icon=stemtube-desktop
Terminal=false
Categories=AudioVideo;Audio;
Keywords=stems;music;mixer;karaoke;chords;demucs;
DESK
chmod 0644 "$PKG/usr/share/applications/stemtube-desktop.desktop"

# ── DEBIAN/control ─────────────────────────────────────────────────────────
cat > "$PKG/DEBIAN/control" <<CTRL
Package: stemtube-desktop
Version: $VERSION
Section: sound
Priority: optional
Architecture: amd64
Depends: curl, zenity
Recommends: libgl1
Maintainer: benasterisk <noreply@github.com>
Homepage: https://benasterisk.github.io/stemtube-desktop-app/
Description: StemTube Desktop — turn any song into a multitrack studio
 AI-powered stem separation, chord detection, lyrics and a full mixer, running
 locally on your own audio files. On first launch it detects your hardware and
 downloads the matching self-contained engine (CPU or NVIDIA GPU) — no Python,
 no pip, no system CUDA needed.
CTRL

# ── DEBIAN/postinst — refresh menu caches ──────────────────────────────────
cat > "$PKG/DEBIAN/postinst" <<'POST'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
echo "StemTube Desktop installed. Launch it from your applications menu."
echo "On first launch it downloads the matching engine (CPU ~560 MB / GPU ~3 GB)."
exit 0
POST
chmod 0755 "$PKG/DEBIAN/postinst"

# ── DEBIAN/postrm — remove the downloaded engine on purge ──────────────────
cat > "$PKG/DEBIAN/postrm" <<'PRM'
#!/bin/sh
set -e
if [ "$1" = "purge" ]; then
  # engines live under each user's $HOME; we can only clean the invoking user's
  [ -n "$HOME" ] && rm -rf "$HOME/.local/share/stemtube-desktop" 2>/dev/null || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
exit 0
PRM
chmod 0755 "$PKG/DEBIAN/postrm"

# ── docs ───────────────────────────────────────────────────────────────────
cat > "$PKG/usr/share/doc/stemtube-desktop/README" <<'DOC'
StemTube Desktop (Standard edition, local files only).
Launch "StemTube Desktop" from your applications menu.
First launch downloads the matching engine (CPU or NVIDIA GPU).
The engine and its data live under ~/.local/share/stemtube-desktop and
~/.stemtube-desktop. No root is used at run time.
DOC

# ── build ──────────────────────────────────────────────────────────────────
# Use fakeroot so files are owned by root:root inside the package.
if command -v fakeroot >/dev/null 2>&1; then
  fakeroot dpkg-deb --build --root-owner-group "$PKG" "$OUT"
else
  dpkg-deb --build --root-owner-group "$PKG" "$OUT"
fi

echo "== DONE =="
ls -lh "$OUT"
echo "--- lint ---"
command -v lintian >/dev/null 2>&1 && lintian "$OUT" 2>&1 | head -20 || echo "(lintian not installed — skipping)"
echo "--- contents ---"
dpkg-deb -c "$OUT"
sha256sum "$OUT"
