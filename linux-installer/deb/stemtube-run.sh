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
REL_TAG="${STEMTUBE_LINUX_TAG:-v2.2.0}"
DEST="${STEMTUBE_HOME:-$HOME/.local/share/stemtube-desktop}"

ZEN="$(command -v zenity || true)"
if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && [ -n "$ZEN" ]; then GUI=1; else GUI=0; fi

# zenity follows the desktop GTK theme, which on a bare install is a glaring
# white dialog. Force the dark variant so the first-launch window is at least
# in the same family as the app's own dark control window.
zen()  { GTK_THEME="${STEMTUBE_GTK_THEME:-Adwaita:dark}" "$ZEN" "$@"; }

die()  { [ "$GUI" = 1 ] && zen --error --width=440 --title="StemTube" --text="$1" || echo "ERROR: $1" >&2; exit 1; }

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
    # Stage the parts next to the final file, not in $TMPDIR: /tmp is a small
    # tmpfs on many systems (3.8 GB under WSL2) and the GPU engine is ~4 GB, so
    # mktemp -d there fails mid-download with no useful message.
    local tmp; tmp="$(mktemp -d "$DEST/.parts.XXXXXX")" || return 1
    local i=0
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
      # A pulsating bar gives no idea whether 4 GB will take 2 minutes or 40.
      # Ask GitHub for the real size first, then report true progress.
      total=0
      if curl -fsIL "$REL_BASE/$REL_TAG/$base" >/dev/null 2>&1; then urls="$base"
      else urls=""; i=0
        while curl -fsIL "$REL_BASE/$REL_TAG/${base}.part$i" >/dev/null 2>&1; do urls="$urls ${base}.part$i"; i=$((i+1)); done
      fi
      for u in $urls; do
        n=$(curl -fsIL "$REL_BASE/$REL_TAG/$u" 2>/dev/null | tr -d '\r' | awk 'tolower($1)=="content-length:"{v=$2} END{print v+0}')
        total=$((total + n))
      done
      total_mb=$((total / 1048576))
      while kill -0 "$pid" 2>/dev/null; do
        got=$(du -scm "$APPIMAGE" "$DEST"/.parts.* 2>/dev/null | awk 'END{print $1+0}')
        if [ "$total_mb" -gt 0 ]; then
          pct=$((got * 100 / total_mb)); [ "$pct" -gt 99 ] && pct=99
          echo "$pct"
          echo "# StemTube engine — $LABEL\n\nDownloading $got of $total_mb MB ($pct%)\nOne-time download. Later launches start instantly."
        else
          echo "# StemTube engine — $LABEL\n\nDownloaded $got MB…"
        fi
        sleep 1
      done
      echo "100"
    ) | zen --progress --auto-close --no-cancel --width=520              --title="StemTube Desktop — first launch" --text="Contacting GitHub…"
    wait "$pid"; rc=$(cat "$status_file" 2>/dev/null || echo 1); rm -f "$status_file"
  else
    echo "Detected: $LABEL — downloading engine…"; download_engine; rc=$?
  fi
  [ "${rc:-1}" = 2 ] && die "Download was corrupted (checksum mismatch).\nLaunch StemTube again to retry."
  { [ "${rc:-1}" = 0 ] && [ -x "$APPIMAGE" ]; } || die "Couldn't download the StemTube engine.\nCheck your internet connection and launch again."
fi

# ── persistent app tree (this is what makes auto-updates stick) ────────────
# --appimage-extract-and-run re-extracts to a throwaway /tmp dir on EVERY
# launch, so anything the in-app updater patches is gone the moment the app
# closes: an install launched that way could never receive an update. Extract
# once to a persistent tree and run that instead. Re-extracted automatically
# when the engine is newer than the tree (i.e. after a fresh engine download).
APPTREE="$DEST/app"
extract_tree() {
  # Same reason as the download: extracting a ~4 GB engine needs real disk, and
  # staging inside $DEST also makes the final mv a rename instead of a copy
  # across filesystems.
  local tmp; tmp="$(mktemp -d "$DEST/.extract.XXXXXX")" || return 1
  ( cd "$tmp" && "$APPIMAGE" --appimage-extract >/dev/null 2>&1 ) || { rm -rf "$tmp"; return 1; }
  [ -d "$tmp/squashfs-root/usr/src/stemtube" ] || { rm -rf "$tmp"; return 1; }
  rm -rf "$APPTREE"
  mv "$tmp/squashfs-root" "$APPTREE" || { rm -rf "$tmp"; return 1; }
  rm -rf "$tmp"
  return 0
}

if [ ! -f "$APPTREE/usr/src/stemtube/app.py" ] || [ "$APPIMAGE" -nt "$APPTREE" ]; then
  if [ "$GUI" = 1 ]; then
    ( echo "# Unpacking the StemTube engine (one-time, about a minute)…"; extract_tree; echo "100" )       | zen --progress --pulsate --auto-close --no-cancel --width=520 --title="StemTube Desktop" --text="Unpacking the engine…"
  else
    echo "Preparing StemTube (one-time)…"; extract_tree
  fi
fi

# ── launch (no FUSE, no root) ──────────────────────────────────────────────
if [ -f "$APPTREE/usr/src/stemtube/app.py" ] && [ -x "$APPTREE/AppRun" ]; then
  exec "$APPTREE/AppRun" "$@"
fi
# Extraction failed (disk full, unusual layout): still start, just without
# the ability to keep updates. Better a running app than none.
exec "$APPIMAGE" --appimage-extract-and-run "$@"
