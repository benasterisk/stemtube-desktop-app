#!/usr/bin/env bash
#
# StemTube — one-shot Linux patcher.
#
# A tester runs this ONCE on a machine that already has StemTube installed via
# the .deb / AppImage. It converts the install to a PERSISTENT, patchable tree
# so the in-app auto-updater (core/updater.py) can hot-patch files afterwards —
# which is impossible with the stock AppImage because `--appimage-extract-and-run`
# re-extracts a throwaway /tmp tree on every launch.
#
# What it does (idempotent — safe to re-run):
#   1. locate the installed engine AppImage (~/.local/share/stemtube-desktop)
#   2. extract it ONCE to a persistent dir (~/.local/share/stemtube-desktop/app)
#   3. ensure core/updater.py is present in that tree (ship it if the installed
#      build predates the updater)
#   4. ensure app.py calls the updater at startup (inject the hook if missing)
#   5. repoint the `stemtube` launcher + desktop entry at the persistent tree,
#      replicating AppRun's environment exports (PATH/LD_LIBRARY_PATH/GTK/WebKit/
#      STEMTUBE_DATA_DIR/FLASK_SECRET_KEY)
#
# After this, the app runs from the persistent tree, and every later fix arrives
# automatically via the manifest — no reinstall.
#
set -uo pipefail

SHARE="$HOME/.local/share/stemtube-desktop"
APPDIR="$SHARE/app"           # persistent extracted tree
BIN="$HOME/.local/bin/stemtube"
DESK="$HOME/.local/share/applications/stemtube-desktop.desktop"

c()  { printf '\033[1;32m%s\033[0m\n' "$*"; }
cy() { printf '\033[1;33m%s\033[0m\n' "$*"; }
ce() { printf '\033[1;31m%s\033[0m\n' "$*" >&2; }

c "StemTube one-shot patcher (Linux) — enabling auto-updates"

# ── 1. locate the installed engine AppImage ────────────────────────────────
APPIMAGE="$(ls "$SHARE"/StemTube-x86_64-*.AppImage 2>/dev/null | head -1)"
if [ -z "$APPIMAGE" ]; then
  ce "No installed StemTube engine found in $SHARE."
  ce "Install StemTube first (the .deb), launch it once, then re-run this patcher."
  exit 1
fi
c "Found engine: $(basename "$APPIMAGE")"

# ── 2. extract ONCE to a persistent tree ───────────────────────────────────
if [ -x "$APPDIR/usr/src/stemtube/app.py" ] || [ -f "$APPDIR/usr/src/stemtube/app.py" ]; then
  cy "Persistent app tree already present — refreshing updater bits only."
else
  c "Extracting the engine to a persistent tree (one-time)…"
  tmp="$(mktemp -d)"; cd "$tmp"
  "$APPIMAGE" --appimage-extract >/dev/null 2>&1 || { ce "extract failed"; exit 1; }
  rm -rf "$APPDIR"; mkdir -p "$(dirname "$APPDIR")"
  mv squashfs-root "$APPDIR"
  cd /; rm -rf "$tmp"
  c "Extracted to $APPDIR"
fi

SRC="$APPDIR/usr/src/stemtube"
PY="$APPDIR/usr/python/bin/python3"
[ -f "$SRC/app.py" ] || { ce "app.py not found in $SRC — unexpected layout"; exit 1; }

# ── 3. ship core/updater.py if the installed build predates it ─────────────
UPD_URL="https://raw.githubusercontent.com/benasterisk/stemtube-desktop-app/main/core/updater.py"
if [ ! -f "$SRC/core/updater.py" ]; then
  c "Installing the updater module…"
  curl -fsSL "$UPD_URL" -o "$SRC/core/updater.py" || { ce "could not fetch updater.py"; exit 1; }
fi

# ── 4. ensure app.py calls the updater at startup ──────────────────────────
if ! grep -q "core.updater import check_and_apply" "$SRC/app.py"; then
  c "Wiring the updater into app.py…"
  # insert the hook right after the stderr utf-8 reconfig block, before
  # configure_gpu_and_restart() — matched on that function's def line.
  "$PY" - "$SRC/app.py" <<'PYEOF'
import sys, io
p = sys.argv[1]
s = io.open(p, encoding="utf-8").read()
hook = (
    "\n# In-app auto-updater (injected by the one-shot patcher).\n"
    "try:\n"
    "    from core.updater import check_and_apply as _stemtube_check_updates\n"
    "    _stemtube_check_updates()\n"
    "except Exception:\n"
    "    pass\n\n"
)
marker = "def configure_gpu_and_restart():"
if "core.updater import check_and_apply" not in s and marker in s:
    s = s.replace(marker, hook + marker, 1)
    io.open(p, "w", encoding="utf-8").write(s)
    print("hook inserted")
else:
    print("hook already present or marker missing")
PYEOF
fi

# ── 5. repoint the launcher + desktop entry at the persistent tree ─────────
c "Repointing the launcher at the persistent tree…"
mkdir -p "$(dirname "$BIN")"
cat > "$BIN" <<LAUNCH
#!/usr/bin/env bash
# StemTube launcher — runs the PERSISTENT patched tree (auto-update enabled),
# replicating the AppImage AppRun environment so GTK/WebKit/GPU keep working.
HERE="$APPDIR"
export PATH="\$HERE/usr/bin:\$HERE/usr/python/bin:\$PATH"
export LD_LIBRARY_PATH="\$HERE/usr/lib:\${LD_LIBRARY_PATH:-}"
export GI_TYPELIB_PATH="\$HERE/usr/lib/girepository-1.0:\${GI_TYPELIB_PATH:-}"
if [ -f "\$HERE/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders.cache" ]; then
  export GDK_PIXBUF_MODULE_FILE="\$HERE/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders.cache"
  export GDK_PIXBUF_MODULEDIR="\$HERE/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders"
fi
[ -d "\$HERE/usr/libexec/webkit2gtk-4.0" ] && export WEBKIT_EXEC_PATH="\$HERE/usr/libexec/webkit2gtk-4.0"
export WEBKIT_DISABLE_COMPOSITING_MODE=1
export STEMTUBE_DATA_DIR="\${STEMTUBE_DATA_DIR:-\$HOME/.stemtube-desktop}"
mkdir -p "\$STEMTUBE_DATA_DIR"
export FLASK_SECRET_KEY="\${FLASK_SECRET_KEY:-\$(cat "\$STEMTUBE_DATA_DIR/.secret_key" 2>/dev/null || (head -c 32 /dev/urandom | base64 | tee "\$STEMTUBE_DATA_DIR/.secret_key"))}"
cd "\$HERE/usr/src/stemtube"
exec "\$HERE/usr/python/bin/python3" launcher.py "\$@"
LAUNCH
chmod +x "$BIN"

# desktop entry → same command
mkdir -p "$(dirname "$DESK")"
if [ -f "$DESK" ]; then
  sed -i "s|^Exec=.*|Exec=$BIN|" "$DESK" 2>/dev/null || true
fi

c ""
c "✅ Auto-updates enabled."
echo "   StemTube now runs from a persistent tree and will patch itself on start."
echo "   Launch it as usual (menu entry or:  stemtube)."
