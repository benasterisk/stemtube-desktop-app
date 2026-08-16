"""
StemTube Desktop Launcher
=========================
Opens the Flask app inside a native desktop window using pywebview.
Uses Edge WebView2 on Windows (built-in on Windows 10/11).

Usage:
    python launcher.py              # Normal launch
    python launcher.py --debug      # Launch with Flask debug + browser DevTools
    python launcher.py --no-gpu     # Force CPU mode (skip GPU detection)
"""

import os
import sys
import time
import signal
import threading
import argparse
import webbrowser

# Ensure we run from the script's directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Parse args before heavy imports
parser = argparse.ArgumentParser(description='StemTube Desktop Launcher')
parser.add_argument('--debug', action='store_true', help='Enable debug mode')
parser.add_argument('--no-gpu', action='store_true', help='Force CPU mode')
parser.add_argument('--port', type=int, default=None, help='Override server port')
parser.add_argument('--no-window', action='store_true',
                    help='Run server only (open in browser instead of native window)')
args = parser.parse_args()

if args.no_gpu:
    os.environ['_STEMTUBE_GPU_CONFIGURED'] = '1'
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    print("[LAUNCHER] GPU disabled — running in CPU mode")


def get_port():
    """Get the port from config or args."""
    if args.port:
        return args.port
    try:
        from core.config import PORT
        return PORT
    except ImportError:
        return 5011


def wait_for_server(port, timeout=60):
    """Wait until the Flask server is responding.

    Any HTTP response means the server is up — even a 404. (This is the "Friend"
    edition with auto-login on '/', so there is no '/login' route; polling it would
    404 forever. An HTTPError still proves the server answers, so we accept it.)
    """
    import urllib.request
    import urllib.error
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2)
            return True
        except urllib.error.HTTPError:
            return True  # server responded (any status) → it's up
        except Exception:
            time.sleep(0.5)
    return False


def start_flask_server(port):
    """Start Flask+SocketIO in a background thread."""
    # Import app module (triggers GPU config, bootstrap, etc.)
    from app import app, socketio

    # Bind on all interfaces so other devices on the LAN can reach the app.
    # (The native window below still opens via 127.0.0.1.)
    from core.config import HOST as _BIND_HOST
    print(f"[LAUNCHER] Starting Flask server on {_BIND_HOST}:{port}")
    socketio.run(
        app,
        host=_BIND_HOST,
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True,
        use_reloader=False,
        log_output=args.debug
    )


def launch_native_window(port):
    """Open a native desktop window with pywebview.

    Falls back to the default browser if pywebview is missing, or if no GUI
    backend is available (e.g. on a Linux box without the GTK/Qt Python
    bindings, where webview.start() raises WebViewException at runtime rather
    than failing to import).
    """
    try:
        import webview
    except ImportError:
        print("[LAUNCHER] pywebview not installed — opening in the browser instead")
        launch_browser(port)
        return

    url = f'http://127.0.0.1:{port}'

    try:
        window = webview.create_window(
            title='StemTube Desktop',
            url=url,
            width=1400,
            height=900,
            min_size=(1024, 700),
            resizable=True,
            confirm_close=True,
            text_select=True,
        )

        def on_closed():
            """Clean shutdown when window is closed."""
            print("[LAUNCHER] Window closed — shutting down server...")
            os._exit(0)

        window.events.closed += on_closed

        # Start pywebview. CRITICAL: private_mode defaults to True, which on the
        # Linux WebKitGTK backend creates an EPHEMERAL WebContext where
        # window.localStorage is null. The mixer touches localStorage during init
        # (e.g. recording-engine calibration), so in private mode a bare
        # localStorage access throws "null is not an object" and aborts mixer
        # init — the stems never load. Disable private mode and give WebKit a
        # persistent, writable storage dir so localStorage works like on Windows.
        try:
            from core.config import USER_DATA_DIR as _UDD
            _storage = os.path.join(_UDD, 'webview')
            os.makedirs(_storage, exist_ok=True)
        except Exception:
            _storage = None
        webview.start(debug=args.debug, private_mode=False, storage_path=_storage)

    except Exception as exc:
        # No usable GUI backend (no GTK 'gi' / no Qt 'qtpy'), or the window
        # failed to open. Don't crash — the Flask server is already running,
        # so just open the app in the browser.
        print(f"[LAUNCHER] Native window unavailable ({type(exc).__name__}: {exc})")
        print("[LAUNCHER] Opening StemTube in your default browser instead.")
        launch_browser(port)


def _open_in_browser(url):
    print(f"[LAUNCHER] Opening {url} in your default browser...")
    try:
        if webbrowser.open(url):
            return True
    except Exception as e:
        print(f"[LAUNCHER] webbrowser.open failed ({e}).")
    # xdg-open fallback (some minimal Linux setups have no BROWSER env)
    try:
        import subprocess
        subprocess.Popen(['xdg-open', url],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        pass
    print(f"[LAUNCHER] Open this address in your browser:  {url}")
    return False


def launch_control_window(port):
    """Small native control window (Tkinter) that manages the server on Linux.

    The GUI itself renders in the user's real browser (Firefox/Chrome…), which —
    unlike the WebKitGTK webview pywebview would use — supports localStorage and
    Web Audio correctly. This little window is just a desktop control surface:
    it opens the browser, shows the status, and quits the server cleanly (so no
    orphaned background process when the browser tab is closed). Falls back to a
    headless keep-alive loop if Tkinter is unavailable.
    """
    url = f'http://127.0.0.1:{port}'

    try:
        import tkinter as tk
        from tkinter import font as tkfont
    except Exception as e:
        print(f"[LAUNCHER] Tkinter unavailable ({e}); running headless.")
        _open_in_browser(url)
        print("[LAUNCHER] StemTube is running. Press Ctrl+C to quit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return

    # open the browser once at startup
    _open_in_browser(url)

    root = tk.Tk()
    root.title("StemTube Desktop")
    try:
        root.geometry("360x200")
        root.resizable(False, False)
    except Exception:
        pass

    title_font = tkfont.Font(size=14, weight="bold")
    tk.Label(root, text="StemTube Desktop", font=title_font).pack(pady=(18, 4))
    tk.Label(root, text="Running — open in your browser:").pack()
    link = tk.Label(root, text=url, fg="#2563eb", cursor="hand2")
    link.pack(pady=(0, 12))
    link.bind("<Button-1>", lambda _e: _open_in_browser(url))

    btns = tk.Frame(root)
    btns.pack(pady=6)
    tk.Button(btns, text="Open StemTube", width=14,
              command=lambda: _open_in_browser(url)).grid(row=0, column=0, padx=6)

    def quit_app():
        print("[LAUNCHER] Quit requested — shutting down.")
        try:
            root.destroy()
        finally:
            os._exit(0)

    tk.Button(btns, text="Quit", width=10, command=quit_app).grid(row=0, column=1, padx=6)
    tk.Label(root, text="Closing this window stops StemTube.",
             fg="#888").pack(side="bottom", pady=(0, 10))

    # closing the window (the X) quits the server too — no orphan process
    root.protocol("WM_DELETE_WINDOW", quit_app)
    root.mainloop()
    # if mainloop returns without quit_app (rare), stop the process anyway
    os._exit(0)


# Backwards-compatible alias (older call sites / --no-window path).
def launch_browser(port):
    launch_control_window(port)


def _use_native_window():
    """Whether to use the embedded native window (webview) or the default browser.

    Linux → browser (WebKitGTK webview is too buggy; see launch_browser).
    Windows/macOS → native window (WebView2 / WKWebView work well).
    Override with STEMTUBE_FORCE_WEBVIEW=1 (native) or --no-window (browser).
    """
    if args.no_window:
        return False
    if os.environ.get('STEMTUBE_FORCE_WEBVIEW') == '1':
        return True
    return not sys.platform.startswith('linux')


def run_update_with_progress():
    """Run the in-app updater at startup, showing a small progress window.

    Architecture note: the updater runs on a WORKER thread while a Tk progress
    window is pumped MANUALLY from the main thread with root.update() (NOT
    mainloop). Everything Tk stays on the main thread, and no second Tk instance
    is created here, which avoids the "Tcl_AsyncDelete: async handler deleted by
    the wrong thread" crash. The window is only shown when there is real work
    (download/install); a plain up-to-date check flashes nothing.

    If an update was applied, restart_now() (os.execv) is called from the main
    thread AFTER the Tk window is fully destroyed — so this may not return.
    Safe no-op if the updater module is missing.
    """
    try:
        from core import updater
    except Exception:
        return

    os.environ['_STEMTUBE_LAUNCHER'] = '1'  # updater requests restart, doesn't execv

    try:
        sp = updater._status_path()
        if os.path.exists(sp):
            os.remove(sp)
    except Exception:
        pass

    done = {"flag": False}

    def _work():
        try:
            updater.check_and_apply()
        except Exception as e:
            print(f"[LAUNCHER] updater error (non-fatal): {e}")
        finally:
            done["flag"] = True

    t = threading.Thread(target=_work, daemon=True)
    t.start()

    # headless: no UI, just wait then maybe restart.
    if args.no_window:
        t.join(timeout=300)
        if getattr(updater, 'RESTART_REQUESTED', False):
            updater.restart_now()
        return

    try:
        import tkinter as tk
        from tkinter import ttk, font as tkfont
        import json as _json
    except Exception:
        t.join(timeout=300)
        if getattr(updater, 'RESTART_REQUESTED', False):
            updater.restart_now()
        return

    root = None
    bar = None
    msg_var = None
    indeterminate = {"on": True}

    def read_status():
        try:
            with open(updater._status_path(), "r", encoding="utf-8") as f:
                return _json.load(f)
        except Exception:
            return None

    def ensure_window():
        nonlocal root, bar, msg_var
        if root is not None:
            return
        root = tk.Tk()
        root.title("StemTube")
        try:
            root.geometry("380x140"); root.resizable(False, False)
        except Exception:
            pass
        tk.Label(root, text="StemTube Desktop",
                 font=tkfont.Font(size=13, weight="bold")).pack(pady=(16, 2))
        msg_var = tk.StringVar(value="Checking for updates…")
        tk.Label(root, textvariable=msg_var).pack(pady=(0, 8))
        bar = ttk.Progressbar(root, orient="horizontal", length=320, mode="indeterminate")
        bar.pack(pady=4)
        bar.start(12)

    def apply_status(s):
        if root is None:
            return
        msg = s.get("message"); pct = s.get("percent")
        if msg:
            msg_var.set(msg)
        if pct is not None:
            if indeterminate["on"]:
                bar.stop(); bar.config(mode="determinate", maximum=100); indeterminate["on"] = False
            bar["value"] = pct
        else:
            if not indeterminate["on"]:
                bar.config(mode="indeterminate"); bar.start(12); indeterminate["on"] = True

    # ── manual pump loop (main thread) ──────────────────────────────────────
    import time as _t
    shown_real_work = False
    start = _t.time()
    final_phase = None
    while True:
        s = read_status()
        if s:
            phase = s.get("phase")
            # only pop the window up for actual work (download/apply/deps/error)
            if phase in ("downloading", "applying", "installing_deps", "done", "error"):
                shown_real_work = True
                ensure_window()
            if root is not None:
                apply_status(s)
            if phase in ("up_to_date", "done", "error"):
                final_phase = phase
        if root is not None:
            try:
                root.update()   # pump Tk on the main thread (no mainloop)
            except Exception:
                break
        # exit conditions
        if done["flag"] and (final_phase is not None or read_status() is None):
            break
        if _t.time() - start > 300:   # safety timeout
            break
        _t.sleep(0.1)

    # brief glimpse of the final state if we showed a window for real work
    if root is not None and shown_real_work and final_phase in ("done", "error"):
        try:
            end = _t.time() + 1.1
            while _t.time() < end:
                root.update(); _t.sleep(0.05)
        except Exception:
            pass

    if root is not None:
        try:
            root.destroy()
        except Exception:
            pass

    # restart from the main thread, after Tk is gone
    if getattr(updater, 'RESTART_REQUESTED', False):
        updater.restart_now()


def main():
    port = get_port()

    # Check for updates first, with a small progress window. If an update is
    # applied, run_update_with_progress() restarts the process from the main
    # thread (and does not return).
    run_update_with_progress()

    # Start Flask in a daemon thread
    server_thread = threading.Thread(target=start_flask_server, args=(port,), daemon=True)
    server_thread.start()

    # Wait for server to be ready
    print("[LAUNCHER] Waiting for server to start...")
    if not wait_for_server(port, timeout=120):
        print("[LAUNCHER] ERROR: Server did not start within 120 seconds")
        sys.exit(1)

    print(f"[LAUNCHER] Server ready on http://127.0.0.1:{port}")

    if args.no_window:
        # headless: just open the browser and keep the server alive (no GUI)
        _open_in_browser(f'http://127.0.0.1:{port}')
        print("[LAUNCHER] StemTube is running (headless). Press Ctrl+C to quit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    elif _use_native_window():
        launch_native_window(port)   # Windows/macOS: embedded WebView2/WKWebView
    else:
        launch_control_window(port)  # Linux: small Tk control window + real browser


if __name__ == '__main__':
    main()
