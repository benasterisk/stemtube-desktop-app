"""
StemTube in-app auto-updater.

Injected into an installed app by the one-shot patcher and called once at
startup (see the seam in app.py, right after the demucs sub-process guard and
before the Flask app is built). It reads a per-edition version manifest from
GitHub, downloads only the changed files, verifies each against its sha256,
applies them atomically into the *persistent* backend tree, installs any new
pure-Python pip deps into the bundled interpreter, records the new version and
offers a restart.

Design constraints (see SPEC_AUTO_UPDATER_StemTube.md):
  * The install is NOT a git checkout, so the locally-applied commit is tracked
    in USER_DATA_DIR/updater_state.json — never read from the tree.
  * The code tree to patch is the directory that CONTAINS this file's parent
    (…/<backend>/core/updater.py -> backend root = parent of core/). It is NOT
    USER_DATA_DIR (writing there would be a silent no-op).
  * Everything is staged and sha256-verified before a single file is touched;
    a failure aborts without partial application.
  * Never runs during a demucs sub-process invocation, and never twice per
    process (env sentinel), mirroring the existing GPU-restart guard.

This module has NO third-party dependencies (stdlib only) so it can run before
the app's environment is fully set up.
"""

import os
import sys
import json
import hashlib
import tempfile
import time
import urllib.request
import urllib.error

# ── constants ──────────────────────────────────────────────────────────────

# Bump when the manifest contract changes in a backward-incompatible way; an
# older updater refuses a manifest whose min_engine_version exceeds this.
UPDATER_ENGINE_VERSION = 1

# Manifest location per edition. The manifest lives on the release branch of the
# matching repo (public), fetched raw. Keyed by EDITION (see edition.py).
_MANIFEST_URLS = {
    "standard": "https://raw.githubusercontent.com/benasterisk/stemtube-desktop-app/main/update/manifest.json",
    "friend":   "https://raw.githubusercontent.com/benasterisk/stemtube-desktop-friend/main/update/manifest.json",
}

_ENV_SENTINEL = "_STEMTUBE_UPDATE_DONE"
_HTTP_TIMEOUT = 15
_DAILY_SECONDS = 24 * 60 * 60


# ── small helpers ──────────────────────────────────────────────────────────

def _backend_root():
    """Absolute path of the backend code tree (the dir that holds core/, app.py…).

    updater.py lives at <backend>/core/updater.py -> backend root = parent of core/.
    Resolved from __file__, NEVER from config.USER_DATA_DIR.
    """
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _edition():
    try:
        import edition
        return getattr(edition, "EDITION", "standard")
    except Exception:
        return "standard"


def _state_path():
    """USER_DATA_DIR/updater_state.json — where the applied commit + last-check live."""
    try:
        from core.config import USER_DATA_DIR
        base = USER_DATA_DIR
    except Exception:
        base = os.path.join(os.path.expanduser("~"), ".stemtube-desktop")
    try:
        os.makedirs(base, exist_ok=True)
    except OSError:
        pass
    return os.path.join(base, "updater_state.json")


def _load_state():
    try:
        with open(_state_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state):
    try:
        tmp = _state_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, _state_path())
    except OSError as e:
        _log(f"could not persist updater state: {e}")


def _local_commit(state):
    """The commit currently applied on this machine.

    First run has no recorded commit; fall back to the baseline stamped by the
    patcher (state['base_commit']) or, failing that, APP_VERSION-as-marker.
    """
    if state.get("applied_commit"):
        return state["applied_commit"]
    if state.get("base_commit"):
        return state["base_commit"]
    return None


def _log(msg):
    # Deliberately print (captured by the app's stdout logging); avoids importing
    # the logging stack before it is configured.
    print(f"[UPDATER] {msg}")


def _status_path():
    """USER_DATA_DIR/updater_status.json — live progress, polled by the launcher's
    Tkinter window so the user sees what the updater is doing at startup."""
    try:
        from core.config import USER_DATA_DIR
        base = USER_DATA_DIR
    except Exception:
        base = os.path.join(os.path.expanduser("~"), ".stemtube-desktop")
    return os.path.join(base, "updater_status.json")


def _progress(phase, message, percent=None, extra=None):
    """Publish the current update phase for the launcher UI.

    phase: one of 'checking' | 'up_to_date' | 'downloading' | 'installing_deps'
           | 'applying' | 'done' | 'error'
    percent: 0..100 or None (indeterminate).
    """
    payload = {"phase": phase, "message": message, "percent": percent,
               "ts": _now()}
    if extra:
        payload.update(extra)
    try:
        p = _status_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp, p)
    except Exception:
        pass


def _now():
    try:
        return time.time()
    except Exception:
        return 0


def _http_get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "StemTube-Updater"})
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as r:
        data = r.read()
    return data if binary else data.decode("utf-8")


def _sha256(data_bytes):
    return hashlib.sha256(data_bytes).hexdigest()


def _bundled_python():
    """Path to the interpreter that owns the app's site-packages, for pip installs.

    On Windows the Tauri backend runs from a real venv; on Linux from the
    persistent extracted AppDir's usr/python. In both cases sys.executable is
    that interpreter when the app is running normally.
    """
    return sys.executable


# ── the entry point called from app.py ─────────────────────────────────────

def check_and_apply():
    """Run one update check. Safe to call unconditionally at startup."""
    # 0. guards — never during a demucs child, never twice, honor the setting
    if "--demucs-separate" in sys.argv:
        return
    if os.environ.get(_ENV_SENTINEL) == "1":
        return
    try:
        from core.config import get_setting
        if get_setting("auto_check_updates", True) is False:
            return
    except Exception:
        pass  # setting unavailable -> default to checking

    os.environ[_ENV_SENTINEL] = "1"

    state = _load_state()

    # daily throttle: skip the network round-trip if we checked < 24h ago
    last = state.get("last_check_ts", 0)
    try:
        now = time.time()
        if last and (now - last) < _DAILY_SECONDS:
            return
    except Exception:
        now = None

    try:
        _run(state, now)
    except urllib.error.URLError as e:
        _log(f"offline or unreachable, skipping update check: {e}")
        _progress("error", "Offline — couldn't check for updates.", None)
    except Exception as e:
        _log(f"update check failed (non-fatal): {e}")
        _progress("error", f"Update check failed: {e}", None)


def _run(state, now):
    edition = _edition()
    url = _MANIFEST_URLS.get(edition)
    if not url:
        _log(f"no manifest URL for edition '{edition}', skipping")
        return

    _progress("checking", "Checking for updates…", None)
    manifest = json.loads(_http_get(url))

    # record that we checked (even if nothing to do) to honor the daily throttle
    if now is not None:
        state["last_check_ts"] = now
        _save_state(state)

    # ── contract & base guards ──────────────────────────────────────────────
    min_engine = int(manifest.get("min_engine_version", 1))
    if min_engine > UPDATER_ENGINE_VERSION:
        _log(f"manifest needs a newer updater (min_engine_version={min_engine} > "
             f"{UPDATER_ENGINE_VERSION}); a full reinstall is required. Skipping.")
        return

    target = manifest.get("target_commit")
    base = manifest.get("base_commit")
    local = _local_commit(state)

    if not target:
        _log("manifest has no target_commit; skipping")
        return

    if local == target:
        _progress("up_to_date", "StemTube is up to date.", 100)
        return  # already up to date

    # A partial patch is only safe if the manifest's base matches what we have.
    # First-run installs have no recorded commit: accept and trust the manifest
    # base (the patcher should have stamped it, but we allow bootstrap).
    if local is not None and base is not None and local != base:
        _log(f"local commit {local} != manifest base {base}; refusing partial patch. "
             f"A full reinstall is recommended.")
        return

    files = manifest.get("files", [])
    pip_installs = manifest.get("pip_installs", [])
    restart_required = bool(manifest.get("restart_required", True))

    if not files and not pip_installs:
        # nothing but a version bump
        state["applied_commit"] = target
        _save_state(state)
        _progress("up_to_date", "StemTube is up to date.", 100)
        return

    root = _backend_root()
    _log(f"update available: {local or '(fresh)'} -> {target} "
         f"({len(files)} file(s), {len(pip_installs)} dep(s))")

    # ── 1. download + verify EVERYTHING into a staging dir before touching root
    staging = tempfile.mkdtemp(prefix="stemtube-update-")
    staged = []  # (rel_path, staged_abs_path, status)
    try:
        # total work units = files to download + deps to install (rough but even)
        total_units = max(1, len([f for f in files if f.get("status") != "D"]) + len(pip_installs))
        done_units = 0
        for f in files:
            path = f["path"]
            status = f.get("status", "M")
            if status == "D":
                staged.append((path, None, "D"))
                continue
            pct = int(done_units * 100 / total_units)
            _progress("downloading", f"Downloading {os.path.basename(path)}…", pct,
                      {"file": path})
            data = _http_get(f["url"], binary=True)
            got = _sha256(data)
            want = f.get("sha256", "")
            if want and got != want:
                raise RuntimeError(f"sha256 mismatch for {path}: got {got}, want {want}")
            dest = os.path.join(staging, path.replace("/", os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as out:
                out.write(data)
            staged.append((path, dest, status))
            done_units += 1

        # ── 2. apply atomically into the backend tree, keeping .bak for rollback
        _progress("applying", "Applying update…", 90)
        backups = []  # (target_abs, backup_abs_or_None)
        try:
            for rel, src, status in staged:
                tgt = os.path.join(root, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(tgt), exist_ok=True)
                # backup existing file for rollback
                bak = None
                if os.path.exists(tgt):
                    bak = tgt + ".stupd.bak"
                    _replace(tgt, bak)
                backups.append((tgt, bak))
                if status == "D":
                    pass  # already moved aside to .bak (i.e. removed)
                else:
                    _replace(src, tgt)

            # ── 3. pip install new pure-Python deps into the bundled interpreter
            if pip_installs:
                _progress("installing_deps",
                          f"Installing components ({', '.join(pip_installs)})…", 95)
                _pip_install(pip_installs)

        except Exception as e:
            _log(f"apply failed ({e}); rolling back")
            _rollback(backups)
            raise

        # ── 4. success: drop backups, mark version
        for tgt, bak in backups:
            if bak and os.path.exists(bak):
                try:
                    os.remove(bak)
                except OSError:
                    pass
        state["applied_commit"] = target
        _save_state(state)
        _log(f"update applied: now at {target}")
        _progress("done", "Update installed.", 100,
                  {"restart": bool(restart_required or pip_installs)})

        # ── 5. restart to load new code
        if restart_required or pip_installs:
            _restart()

    finally:
        _rmtree(staging)


def _replace(src, dst):
    """Atomic-ish move src->dst across the same filesystem (staging is in TMP; if
    that is a different device, fall back to copy+replace)."""
    try:
        os.replace(src, dst)
    except OSError:
        import shutil
        shutil.copy2(src, dst)
        try:
            os.remove(src)
        except OSError:
            pass


def _rollback(backups):
    for tgt, bak in backups:
        try:
            if bak and os.path.exists(bak):
                os.replace(bak, tgt)  # restore original
            elif os.path.exists(tgt) and bak is None:
                # file was newly created by us and has no backup -> remove it
                os.remove(tgt)
        except OSError:
            pass


def _pip_install(deps):
    import subprocess
    py = _bundled_python()
    _log(f"installing deps into {py}: {deps}")
    proc = subprocess.run(
        [py, "-m", "pip", "install", "--no-input", *deps],
        capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pip install failed: {proc.stderr[-500:]}")


# Set True when an applied update needs a process restart. The launcher checks
# this after check_and_apply() returns and performs the restart from the MAIN
# thread (doing os.execv from the updater's worker thread crashes Tkinter:
# "Tcl_AsyncDelete: async handler deleted by the wrong thread").
RESTART_REQUESTED = False


def restart_now():
    """Replace the current process to load the new code. MUST be called from the
    main thread (the launcher does this after closing its progress window)."""
    _log("restarting to apply update…")
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        _log(f"restart failed ({e}); the update will take effect on next launch")


def _restart():
    # Don't execv here — we may be on a worker thread with a Tk loop running.
    # Just request it; the launcher restarts from the main thread. If the app was
    # started directly (python app.py, no launcher), fall back to execv here since
    # there is no Tk loop to corrupt and no one else will do it.
    global RESTART_REQUESTED
    RESTART_REQUESTED = True
    if os.environ.get('_STEMTUBE_LAUNCHER') != '1':
        restart_now()


def _rmtree(path):
    try:
        import shutil
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass
