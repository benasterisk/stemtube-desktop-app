#!/usr/bin/env bash
#
# StemTube Desktop — Linux installer/launcher
#
#   curl -fsSL https://raw.githubusercontent.com/benasterisk/stemtube-desktop-app/main/stemtube-linux-launcher.sh | bash
#
# The Linux equivalent of the Windows installer: a tiny script that detects the
# GPU, downloads the matching self-contained AppImage (CPU or GPU) from the
# releases repo, installs the one runtime dependency (libfuse2), registers a
# `stemtube` command and a desktop-menu entry, then launches the app.
# The AppImage bundles everything else (Python, PyTorch, FFmpeg) — nothing to
# install by hand.
#
set -euo pipefail

REL_BASE="https://github.com/benasterisk/stemtube-desktop-releases/releases/download"
REL_TAG="${STEMTUBE_LINUX_TAG:-linux-v2.0.0}"
DEST="${STEMTUBE_HOME:-$HOME/.local/share/stemtube-desktop}"
BIN_DIR="$HOME/.local/bin"

c()  { printf '\033[1;32m%s\033[0m\n' "$*"; }
cy() { printf '\033[1;33m%s\033[0m\n' "$*"; }
ce() { printf '\033[1;31m%s\033[0m\n' "$*" >&2; }

[ "$(uname -s)" = "Linux" ] || { ce "This installer is for Linux."; exit 1; }
command -v curl >/dev/null || { ce "curl is required (sudo apt install curl)."; exit 1; }
mkdir -p "$DEST" "$BIN_DIR"

# ── ensure libfuse2 (needed to run an AppImage) ────────────────────────────
have_fuse() { ldconfig -p 2>/dev/null | grep -q 'libfuse\.so\.2'; }
if ! have_fuse; then
  cy "Installing the AppImage runtime dependency (libfuse2)…"
  if   command -v apt-get >/dev/null; then sudo apt-get update -qq && sudo apt-get install -y libfuse2 2>/dev/null || sudo apt-get install -y libfuse2t64
  elif command -v dnf     >/dev/null; then sudo dnf install -y fuse-libs
  elif command -v pacman  >/dev/null; then sudo pacman -Sy --needed --noconfirm fuse2
  elif command -v zypper  >/dev/null; then sudo zypper install -y libfuse2
  else cy "Couldn't auto-install libfuse2 — install it manually if the app won't start."; fi
fi

# ── GPU detection (same rule as the Windows launcher) ──────────────────────
VARIANT="cpu"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  VARIANT="gpu"
  c "NVIDIA GPU detected → GPU edition"
else
  c "No NVIDIA GPU → CPU edition"
fi

APPIMAGE="$DEST/StemTube-x86_64-${VARIANT}.AppImage"
base="StemTube-x86_64-${VARIANT}.AppImage"

dl() { cy "  ↓ $(basename "$2")"; curl -fL --retry 3 -o "$2" "$1"; }

# ── download (with split-part reassembly for the GPU build) ────────────────
if [ ! -x "$APPIMAGE" ]; then
  if curl -fsIL "$REL_BASE/$REL_TAG/$base" >/dev/null 2>&1; then
    c "Downloading the engine (this is a one-time download)…"
    dl "$REL_BASE/$REL_TAG/$base" "$APPIMAGE"
  else
    c "Downloading the engine in parts (one-time download)…"
    tmp="$(mktemp -d)"; i=0
    while :; do
      part="${base}.part$i"
      curl -fsIL "$REL_BASE/$REL_TAG/$part" >/dev/null 2>&1 || break
      dl "$REL_BASE/$REL_TAG/$part" "$tmp/$part"; i=$((i+1))
    done
    [ "$i" -gt 0 ] || { ce "No download found for $base at $REL_TAG."; exit 1; }
    c "Assembling $i parts…"
    cat "$tmp"/${base}.part* > "$APPIMAGE"; rm -rf "$tmp"
    if curl -fsL "$REL_BASE/$REL_TAG/${base}.sha256" -o "$DEST/.sum" 2>/dev/null; then
      exp=$(awk '{print $1}' "$DEST/.sum"); got=$(sha256sum "$APPIMAGE" | awk '{print $1}')
      [ "$exp" = "$got" ] && c "Checksum OK" || { ce "Checksum mismatch — re-run to retry."; rm -f "$APPIMAGE"; exit 1; }
    fi
  fi
  chmod +x "$APPIMAGE"
else
  c "Engine already installed."
fi

# ── `stemtube` command + desktop-menu entry ────────────────────────────────
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
Icon=audio-x-generic
Terminal=false
Categories=AudioVideo;Audio;
DESK

c ""
c "✅ StemTube Desktop installed."
echo "   Launch it from your applications menu, or run:  stemtube"
if ! printf '%s' ":$PATH:" | grep -q ":$BIN_DIR:"; then
  cy "   ($BIN_DIR is not on your PATH — use $BIN_DIR/stemtube, or add it to PATH.)"
fi
echo
c "Starting StemTube…"
exec "$APPIMAGE"
