#!/usr/bin/env bash
#
# StemTube Desktop — graphical installer (the Linux equivalent of setup.exe).
#
# Runs inside the tiny StemTube-Installer AppImage. Double-clicked by the user,
# it shows GTK windows (via zenity), detects the GPU, downloads the matching
# self-contained engine AppImage, registers it in the applications menu and
# launches it. No terminal, no command to type, NO sudo, NO system packages:
# the engine is launched with --appimage-extract-and-run so it needs no FUSE.
#
set -uo pipefail

REL_BASE="https://github.com/benasterisk/stemtube-desktop-releases/releases/download"
REL_TAG="${STEMTUBE_LINUX_TAG:-linux-v2.0.0}"
DEST="${STEMTUBE_HOME:-$HOME/.local/share/stemtube-desktop}"
BIN_DIR="$HOME/.local/bin"
DESK_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"

# zenity is bundled in the installer AppImage; prefer a system one if present.
ZEN="$(command -v zenity || echo "$APPDIR/usr/bin/zenity")"
have_zenity() { [ -x "$ZEN" ] || command -v zenity >/dev/null 2>&1; }

# ── if there is no display or no zenity, fall back to a plain text run ──────
if [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] || ! have_zenity; then
  echo "StemTube installer (no GUI available — running in text mode)"
  GUI=0
else
  GUI=1
fi

die() {
  if [ "$GUI" = 1 ]; then "$ZEN" --error --width=420 --title="StemTube Installer" --text="$1"; else echo "ERROR: $1" >&2; fi
  exit 1
}
info() { [ "$GUI" = 1 ] && "$ZEN" --info --width=420 --title="StemTube Installer" --text="$1" || echo "$1"; }

command -v curl >/dev/null 2>&1 || die "curl is required.\nInstall it with: sudo apt install curl"

mkdir -p "$DEST" "$BIN_DIR" "$DESK_DIR" "$ICON_DIR"

# Copy the StemTube icon shipped inside this installer into the icon theme.
[ -f "$APPDIR/stemtube.png" ] && cp -f "$APPDIR/stemtube.png" "$ICON_DIR/stemtube-desktop.png" 2>/dev/null || true

# ── 1. GPU / CPU detection ─────────────────────────────────────────────────
VARIANT="cpu"; LABEL="CPU edition"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  VARIANT="gpu"; LABEL="NVIDIA GPU edition (CUDA)"
fi

base="StemTube-x86_64-${VARIANT}.AppImage"
APPIMAGE="$DEST/$base"

# ── 2. download the matching engine, with a progress bar ───────────────────
download_engine() {
  local single_ok=0
  curl -fsIL "$REL_BASE/$REL_TAG/$base" >/dev/null 2>&1 && single_ok=1

  if [ "$single_ok" = 1 ]; then
    curl -fL --retry 3 -o "$APPIMAGE" "$REL_BASE/$REL_TAG/$base" 2>/dev/null || return 1
  else
    # multi-part GPU asset — download each part, concatenate
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
  chmod +x "$APPIMAGE"
  return 0
}

# Run the download in the background and drive a zenity progress bar from the
# growing file size — honest, live feedback with no fragile percentage parsing.
run_download() {
  if [ "$GUI" = 1 ]; then
    local status_file; status_file="$(mktemp)"
    ( download_engine; echo $? > "$status_file" ) &
    local pid=$!
    (
      echo "# Detected: $LABEL"
      echo "# Downloading the StemTube engine (one-time, may take a few minutes)…"
      while kill -0 "$pid" 2>/dev/null; do
        if [ -f "$APPIMAGE" ]; then
          sz=$(du -m "$APPIMAGE" 2>/dev/null | awk '{print $1}')
          echo "# $LABEL — downloaded ${sz:-0} MB…"
        fi
        sleep 1
      done
      echo "100"
    ) | "$ZEN" --progress --pulsate --auto-close --no-cancel --width=470 \
             --title="StemTube Installer" --text="Preparing…"
    wait "$pid"
    local rc; rc=$(cat "$status_file" 2>/dev/null || echo 1); rm -f "$status_file"
    return "$rc"
  else
    echo "Detected: $LABEL — downloading engine…"
    download_engine; return $?
  fi
}

if [ ! -x "$APPIMAGE" ]; then
  run_download
  rc=$?
  [ "$rc" = 2 ] && die "Download was corrupted (checksum mismatch).\nPlease run the installer again."
  { [ "$rc" = 0 ] && [ -x "$APPIMAGE" ]; } || die "Couldn't download the StemTube engine.\nCheck your internet connection and try again."
fi

# ── 3. register `stemtube` command + menu entry ────────────────────────────
# The engine AppImage is launched with --appimage-extract-and-run so it needs
# NO libfuse2 and NO root: it self-extracts to a temp dir and runs from there.
cat > "$BIN_DIR/stemtube" <<LAUNCH
#!/usr/bin/env bash
exec "$APPIMAGE" --appimage-extract-and-run "\$@"
LAUNCH
chmod +x "$BIN_DIR/stemtube"

ICON_LINE="Icon=stemtube-desktop"
[ -f "$ICON_DIR/stemtube-desktop.png" ] || ICON_LINE="Icon=audio-x-generic"
cat > "$DESK_DIR/stemtube-desktop.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=StemTube Desktop
Comment=Turn any song into a multitrack studio
Exec=$BIN_DIR/stemtube
$ICON_LINE
Terminal=false
Categories=AudioVideo;Audio;
DESK
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DESK_DIR" 2>/dev/null || true

# ── 4. done — launch StemTube ──────────────────────────────────────────────
if [ "$GUI" = 1 ]; then
  "$ZEN" --info --width=440 --title="StemTube Installer" \
    --text="<b>StemTube Desktop is installed.</b> ($LABEL)\n\nYou'll find it in your applications menu.\n\nLaunching it now…"
fi
exec "$APPIMAGE" --appimage-extract-and-run "$@"
