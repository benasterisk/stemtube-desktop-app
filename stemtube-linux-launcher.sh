#!/usr/bin/env bash
#
# StemTube Desktop — Linux launcher (AppImage edition)
#
#   curl -fsSL https://raw.githubusercontent.com/benasterisk/stemtube-desktop-app/main/stemtube-linux-launcher.sh | bash
#
# Mirrors the Windows Tauri launcher: detects the GPU, downloads the matching
# self-contained AppImage (CPU or GPU) from the releases repo, reassembles the
# split GPU parts if needed, caches it under ~/.local/share, and runs it.
# No Python, no pip, no system CUDA — the AppImage bundles everything.
#
set -euo pipefail

REL_BASE="https://github.com/benasterisk/stemtube-desktop-releases/releases/download"
REL_TAG="${STEMTUBE_LINUX_TAG:-linux-v2.0.0}"
DEST="${STEMTUBE_HOME:-$HOME/.local/share/stemtube-desktop}"
BIN_DIR="$HOME/.local/bin"

c()  { printf '\033[1;32m%s\033[0m\n' "$*"; }
cy() { printf '\033[1;33m%s\033[0m\n' "$*"; }
ce() { printf '\033[1;31m%s\033[0m\n' "$*" >&2; }

[ "$(uname -s)" = "Linux" ] || { ce "Linux only."; exit 1; }
command -v curl >/dev/null || { ce "curl is required."; exit 1; }
mkdir -p "$DEST" "$BIN_DIR"

# ── GPU detection (same rule as the Windows launcher) ──────────────────────
VARIANT="cpu"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  VARIANT="gpu"
  c "NVIDIA GPU detected → GPU build"
else
  c "No NVIDIA GPU → CPU build"
fi

APPIMAGE="$DEST/StemTube-x86_64-${VARIANT}.AppImage"

dl() { # dl <url> <out>
  cy "  ↓ $(basename "$2")"
  curl -fL --retry 3 -o "$2" "$1"
}

# ── download (with split-part reassembly for the GPU build) ────────────────
if [ ! -x "$APPIMAGE" ]; then
  base="StemTube-x86_64-${VARIANT}.AppImage"
  # A single-file asset is tried first; if absent, fall back to split parts.
  if curl -fsIL "$REL_BASE/$REL_TAG/$base" >/dev/null 2>&1; then
    c "Downloading $base…"
    dl "$REL_BASE/$REL_TAG/$base" "$APPIMAGE"
  else
    c "Downloading $base (split parts)…"
    tmp="$(mktemp -d)"
    i=0
    while :; do
      part="${base}.part$i"
      url="$REL_BASE/$REL_TAG/$part"
      curl -fsIL "$url" >/dev/null 2>&1 || break
      dl "$url" "$tmp/$part"
      i=$((i+1))
    done
    [ "$i" -gt 0 ] || { ce "No asset found for $base at $REL_TAG."; exit 1; }
    c "Reassembling $i parts…"
    cat "$tmp"/${base}.part* > "$APPIMAGE"
    rm -rf "$tmp"
    # verify checksum if published
    if curl -fsL "$REL_BASE/$REL_TAG/${base}.sha256" -o "$DEST/.sum" 2>/dev/null; then
      (cd "$DEST" && sha256sum -c <(sed "s#$base#$APPIMAGE#" .sum)) \
        && c "Checksum OK" || { ce "Checksum mismatch — re-run to retry."; rm -f "$APPIMAGE"; exit 1; }
    fi
  fi
  chmod +x "$APPIMAGE"
else
  c "Using cached AppImage: $APPIMAGE"
fi

# ── launcher shim + desktop entry ──────────────────────────────────────────
cat > "$BIN_DIR/stemtube" <<LAUNCH
#!/usr/bin/env bash
exec "$APPIMAGE" "\$@"
LAUNCH
chmod +x "$BIN_DIR/stemtube"

DESK_DIR="$HOME/.local/share/applications"
mkdir -p "$DESK_DIR"
cat > "$DESK_DIR/stemtube-desktop.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=StemTube Desktop
Comment=Turn any song into a multitrack studio
Exec=$BIN_DIR/stemtube
Terminal=false
Categories=AudioVideo;Audio;
DESK

c ""
c "✅ StemTube Desktop ready."
echo "   Launch with:  stemtube      (or from your applications menu)"
if ! printf '%s' ":$PATH:" | grep -q ":$BIN_DIR:"; then
  cy "   Note: add $BIN_DIR to your PATH, or run $BIN_DIR/stemtube"
fi
echo
c "Starting StemTube now…"
exec "$APPIMAGE"
