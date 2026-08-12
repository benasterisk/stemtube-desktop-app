#!/usr/bin/env bash
#
# /usr/bin/stemtube — installed by the StemTube .deb package.
#
# On first launch it opens a small GTK window (zenity), detects the GPU,
# downloads the matching self-contained engine (CPU or NVIDIA GPU) from the
# release with a progress bar, then launches it. Later launches start instantly.
# The engine is run with --appimage-extract-and-run: no libfuse2, no sudo.
#
set -uo pipefail

REL_BASE="https://github.com/benasterisk/stemtube-desktop-releases/releases/download"
REL_TAG="${STEMTUBE_LINUX_TAG:-linux-v2.0.0}"
DEST="${STEMTUBE_HOME:-$HOME/.local/share/stemtube-desktop}"

ZEN="$(command -v zenity || true)"
if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && [ -n "$ZEN" ]; then GUI=1; else GUI=0; fi

die()  { [ "$GUI" = 1 ] && "$ZEN" --error --width=440 --title="StemTube" --text="$1" || echo "ERROR: $1" >&2; exit 1; }

command -v curl >/dev/null 2>&1 || die "curl is required.\nInstall it with: sudo apt install curl"
mkdir -p "$DEST"

# ── GPU / CPU detection ────────────────────────────────────────────────────
VARIANT="cpu"; LABEL="CPU edition"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  VARIANT="gpu"; LABEL="NVIDIA GPU edition (CUDA)"
fi
base="StemTube-x86_64-${VARIANT}.AppImage"
APPIMAGE="$DEST/$base"

# ── download the matching engine (single or split parts) ───────────────────
download_engine() {
  if curl -fsIL "$REL_BASE/$REL_TAG/$base" >/dev/null 2>&1; then
    curl -fL --retry 3 -o "$APPIMAGE" "$REL_BASE/$REL_TAG/$base" 2>/dev/null || return 1
  else
    local tmp; tmp="$(mktemp -d)"; local i=0
    while :; do
      local part="${base}.part$i"
      curl -fsIL "$REL_BASE/$REL_TAG/$part" >/dev/null 2>&1 || break
      curl -fL --retry 3 -o "$tmp/$part" "$REL_BASE/$REL_TAG/$part" 2>/dev/null || { rm -rf "$tmp"; return 1; }
      i=$((i+1))
    done
    [ "$i" -gt 0 ] || { rm -rf "$tmp"; return 1; }
    cat "$tmp"/${base}.part* > "$APPIMAGE"; rm -rf "$tmp"
    if curl -fsL "$REL_BASE/$REL_TAG/${base}.sha256" -o "$DEST/.sum" 2>/dev/null; then
      local exp got; exp=$(awk '{print $1}' "$DEST/.sum"); got=$(sha256sum "$APPIMAGE" | awk '{print $1}')
      [ "$exp" = "$got" ] || { rm -f "$APPIMAGE"; return 2; }
    fi
  fi
  [ -s "$APPIMAGE" ] || return 1
  chmod +x "$APPIMAGE"; return 0
}

# ── first launch: download with a progress window ──────────────────────────
if [ ! -x "$APPIMAGE" ]; then
  if [ "$GUI" = 1 ]; then
    status_file="$(mktemp)"
    ( download_engine; echo $? > "$status_file" ) &
    pid=$!
    (
      echo "# Detected: $LABEL"
      echo "# Downloading the StemTube engine (one-time, may take a few minutes)…"
      while kill -0 "$pid" 2>/dev/null; do
        [ -f "$APPIMAGE" ] && echo "# $LABEL — downloaded $(du -m "$APPIMAGE" 2>/dev/null | awk '{print $1}') MB…"
        sleep 1
      done
      echo "100"
    ) | "$ZEN" --progress --pulsate --auto-close --no-cancel --width=470 \
             --title="StemTube — first launch" --text="Preparing…"
    wait "$pid"; rc=$(cat "$status_file" 2>/dev/null || echo 1); rm -f "$status_file"
  else
    echo "Detected: $LABEL — downloading engine…"; download_engine; rc=$?
  fi
  [ "${rc:-1}" = 2 ] && die "Download was corrupted (checksum mismatch).\nLaunch StemTube again to retry."
  { [ "${rc:-1}" = 0 ] && [ -x "$APPIMAGE" ]; } || die "Couldn't download the StemTube engine.\nCheck your internet connection and launch again."
fi

# ── launch (no FUSE, no root) ──────────────────────────────────────────────
exec "$APPIMAGE" --appimage-extract-and-run "$@"
