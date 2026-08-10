#!/usr/bin/env bash
#
# StemTube Desktop — Linux installer
#
#   curl -fsSL https://raw.githubusercontent.com/benasterisk/stemtube-desktop-app/main/install.sh | bash
#
# Clones the (public) Standard edition, builds a Python venv, installs PyTorch
# (CPU or CUDA auto-detected), FFmpeg and all dependencies, then drops a
# `stemtube` launcher + desktop entry. No Tauri, no compiled binary: it runs
# the same Flask engine the Windows edition ships, and opens it in your browser
# as a local app window.
#
set -euo pipefail

REPO_URL="https://github.com/benasterisk/stemtube-desktop-app.git"
APP_DIR="${STEMTUBE_HOME:-$HOME/.local/share/stemtube-desktop}"
BIN_DIR="$HOME/.local/bin"
PYTHON_MIN="3.10"

c()  { printf '\033[1;32m%s\033[0m\n' "$*"; }   # green
cy() { printf '\033[1;33m%s\033[0m\n' "$*"; }   # yellow
ce() { printf '\033[1;31m%s\033[0m\n' "$*" >&2; }  # red

# ── 0. sanity ──────────────────────────────────────────────────────────────
if [[ "$(uname -s)" != "Linux" ]]; then
  ce "This installer is for Linux. On Windows use the .exe installer."
  exit 1
fi

command -v git   >/dev/null || { ce "git is required (sudo apt install git / sudo dnf install git)"; exit 1; }

# find a suitable python3 (>= 3.10)
PY=""
for cand in python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    ver="$("$cand" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
    if [ "$(printf '%s\n%s' "$PYTHON_MIN" "$ver" | sort -V | head -1)" = "$PYTHON_MIN" ]; then
      PY="$cand"; break
    fi
  fi
done
[ -n "$PY" ] || { ce "Python >= $PYTHON_MIN not found. Install it (e.g. sudo apt install python3 python3-venv)."; exit 1; }
c "Using $($PY --version)"

# ── 1. system deps (best-effort, needs sudo) ───────────────────────────────
install_system_deps() {
  local pkgs_apt="ffmpeg python3-venv python3-dev build-essential libsndfile1"
  local pkgs_dnf="ffmpeg python3-devel gcc gcc-c++ make libsndfile"
  local pkgs_pac="ffmpeg base-devel libsndfile"
  if command -v apt-get >/dev/null; then
    cy "Installing system packages (apt): $pkgs_apt"
    sudo apt-get update -qq && sudo apt-get install -y $pkgs_apt
  elif command -v dnf >/dev/null; then
    cy "Installing system packages (dnf): $pkgs_dnf"
    sudo dnf install -y $pkgs_dnf
  elif command -v pacman >/dev/null; then
    cy "Installing system packages (pacman): $pkgs_pac"
    sudo pacman -Sy --needed --noconfirm $pkgs_pac
  else
    cy "Unknown package manager — make sure ffmpeg, a C compiler and libsndfile are installed."
  fi
}
if ! command -v ffmpeg >/dev/null; then
  install_system_deps
else
  c "ffmpeg already present."
fi

# ── 2. clone / update the app ──────────────────────────────────────────────
if [ -d "$APP_DIR/.git" ]; then
  c "Updating existing install in $APP_DIR"
  git -C "$APP_DIR" pull --ff-only
else
  c "Cloning StemTube into $APP_DIR"
  mkdir -p "$(dirname "$APP_DIR")"
  git clone --depth 1 "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# ── 3. python venv ─────────────────────────────────────────────────────────
if [ ! -d venv ]; then
  c "Creating virtual environment"
  "$PY" -m venv venv
fi
VENV_PY="$APP_DIR/venv/bin/python"
"$VENV_PY" -m pip install --quiet --upgrade pip wheel setuptools

# ── 4. GPU detection → PyTorch CPU or CUDA ─────────────────────────────────
TORCH_INDEX="https://download.pytorch.org/whl/cpu"
GPU_LABEL="CPU"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  TORCH_INDEX="https://download.pytorch.org/whl/cu124"
  GPU_LABEL="NVIDIA GPU (CUDA 12.4)"
fi
c "Installing PyTorch for: $GPU_LABEL"
"$VENV_PY" -m pip install torch torchaudio --index-url "$TORCH_INDEX"

# ── 5. remaining Python deps ───────────────────────────────────────────────
# demucs is pinned to 4.0.1: 4.1.0 removed `demucs.separate.load_track`, which
# core/stems_extractor.py still uses.
c "Installing audio/ML dependencies (this can take a few minutes)…"
"$VENV_PY" -m pip install \
  Flask Flask-Login Flask-Session Flask-SocketIO eventlet requests python-dotenv \
  Pillow librosa soundfile scipy scikit-learn numpy psutil \
  "demucs==4.0.1" faster-whisper syncedlyrics pychord beautifulsoup4

# madmom (chord/beat detection) — needs Cython + numpy first, builds from source on Linux
c "Installing madmom (chord & beat detection)…"
"$VENV_PY" -m pip install Cython
"$VENV_PY" -m pip install "madmom @ git+https://github.com/CPJKU/madmom@main" || \
  cy "madmom failed to build — chords/beats may be limited. Install build tools and re-run."

# ── 6. launcher script ─────────────────────────────────────────────────────
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/stemtube" <<LAUNCH
#!/usr/bin/env bash
# StemTube Desktop launcher
set -e
APP_DIR="$APP_DIR"
PORT=5011
cd "\$APP_DIR"
# start the local server in the background (binds 0.0.0.0 like the desktop
# edition — LAN-trusted, no network auth; keep this machine on a trusted network)
"\$APP_DIR/venv/bin/python" app.py >/tmp/stemtube.log 2>&1 &
SRV_PID=\$!
# wait for the port, then open the browser as an app window if possible
for i in \$(seq 1 60); do
  if (exec 3<>/dev/tcp/127.0.0.1/\$PORT) 2>/dev/null; then break; fi
  sleep 1
done
URL="http://127.0.0.1:\$PORT"
if command -v chromium >/dev/null;        then chromium --app="\$URL" >/dev/null 2>&1 &
elif command -v google-chrome >/dev/null; then google-chrome --app="\$URL" >/dev/null 2>&1 &
elif command -v xdg-open >/dev/null;      then xdg-open "\$URL" >/dev/null 2>&1 &
else echo "Open \$URL in your browser."; fi
echo "StemTube running (pid \$SRV_PID). Log: /tmp/stemtube.log"
echo "Stop with: kill \$SRV_PID"
wait \$SRV_PID
LAUNCH
chmod +x "$BIN_DIR/stemtube"

# ── 7. desktop entry ───────────────────────────────────────────────────────
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
c "✅ StemTube Desktop installed."
echo
echo "  Launch it with:   stemtube"
echo "  (or from your applications menu: 'StemTube Desktop')"
echo
if ! printf '%s' ":$PATH:" | grep -q ":$BIN_DIR:"; then
  cy "Note: $BIN_DIR is not in your PATH. Add it or run: $BIN_DIR/stemtube"
fi
