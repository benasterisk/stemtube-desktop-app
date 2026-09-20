"""
StemTube Desktop Launcher
=========================
Starts the Flask app locally and opens it in the user's DEFAULT BROWSER.

There is no embedded webview any more: the app is a local web app on every
platform (the same thing the server edition does, and what the Linux build
already did). A small Tkinter control window stays on the desktop so the user
can reopen the page and — above all — shut the server down cleanly, which
closing a browser tab cannot do.

Usage:
    python launcher.py              # Normal launch (browser + control window)
    python launcher.py --debug      # Launch with Flask log output
    python launcher.py --no-gpu     # Force CPU mode (skip GPU detection)
    python launcher.py --no-window  # Server + browser only, no control window
"""

import os
import sys
import time
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
                    help='Run server only (browser, no desktop control window)')
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
    # (The browser we open below still uses 127.0.0.1.)
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
    """Small native control window (Tkinter) that manages the server.

    This is the launch path on EVERY platform. The GUI itself renders in the
    user's real browser (Firefox/Chrome/Edge…), which supports localStorage,
    Web Audio and multi-window popups correctly and without surprises. This
    little window is just a desktop control surface: it opens the browser,
    shows the status, and quits the server cleanly (so closing the browser tab
    does not leave an orphaned background process). Falls back to a headless
    keep-alive loop if Tkinter is unavailable.
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

    # Same look as the Windows control window (src-tauri/splash.html): dark
    # burgundy panel, red wordmark, green "running" dot, one primary and one
    # ghost button. Tk has no gradients, so the background is the flat midpoint.
    BG, FG, RED, RED_HI = "#25101a", "#e8d0d5", "#e41b36", "#ff4757"
    MUTED, DIM, GREEN, WARN = "#8a7077", "#5c4248", "#3ddc84", "#ffb347"

    root = tk.Tk()
    root.title("StemTube Desktop")
    root.configure(bg=BG)
    try:
        root.geometry("520x340")
        root.resizable(False, False)
    except Exception:
        pass

    def _font(size, weight="normal", mono=False):
        families = set(tkfont.families())
        wanted = (("DejaVu Sans Mono", "Liberation Mono", "Consolas", "Courier New")
                  if mono else
                  ("Segoe UI", "Inter", "Ubuntu", "Cantarell", "Noto Sans", "DejaVu Sans"))
        for fam in wanted:
            if fam in families:
                return tkfont.Font(family=fam, size=size, weight=weight)
        return tkfont.Font(size=size, weight=weight)

    tk.Label(root, text="STEMTUBE DESKTOP", font=_font(22, "bold"),
             fg=RED, bg=BG).pack(pady=(34, 2))
    tk.Label(root, text="StemTube runs in your web browser", font=_font(10),
             fg=MUTED, bg=BG).pack(pady=(0, 22))

    status = tk.Frame(root, bg=BG)
    status.pack()
    dot = tk.Canvas(status, width=12, height=12, bg=BG, highlightthickness=0)
    dot.create_oval(1, 1, 11, 11, fill=GREEN, outline=GREEN)
    dot.pack(side="left", padx=(0, 8))
    tk.Label(status, text="StemTube is running", font=_font(12),
             fg=FG, bg=BG).pack(side="left")

    warn = tk.Label(root, text="", font=_font(9), fg=WARN, bg=BG)

    def open_ui(_e=None):
        if _open_in_browser(url):
            warn.config(text="")
        else:
            warn.config(text="Could not open your browser — open the address above manually.")

    link = tk.Label(root, text=url, font=_font(10, mono=True),
                    fg=RED, bg=BG, cursor="hand2")
    link.pack(pady=(6, 20))
    link.bind("<Button-1>", open_ui)

    def quit_app():
        print("[LAUNCHER] Quit requested — shutting down.")
        try:
            root.destroy()
        finally:
            os._exit(0)

    def _button(parent, text, command, primary):
        # A bordered Frame around a flat Button: the only way to get a 1px
        # coloured outline (the "ghost" style) that renders the same on every
        # Tk theme.
        border = RED if primary else DIM
        holder = tk.Frame(parent, bg=border, padx=1, pady=1)
        base, hover = (RED, RED_HI) if primary else (BG, "#32161f")
        btn = tk.Button(holder, text=text, command=command,
                        font=_font(10, "bold" if primary else "normal"),
                        fg="#ffffff" if primary else MUTED, bg=base,
                        activebackground=hover,
                        activeforeground="#ffffff" if primary else FG,
                        relief="flat", bd=0, highlightthickness=0,
                        padx=20, pady=8, cursor="hand2")
        btn.pack()
        btn.bind("<Enter>", lambda _e: btn.config(bg=hover))
        btn.bind("<Leave>", lambda _e: btn.config(bg=base))
        return holder

    btns = tk.Frame(root, bg=BG)
    btns.pack()
    _button(btns, "Open in browser", open_ui, True).grid(row=0, column=0, padx=6)
    _button(btns, "Quit StemTube", quit_app, False).grid(row=0, column=1, padx=6)

    warn.pack(pady=(12, 0))
    tk.Label(root, text="Keep this window open while you use StemTube.\n"
                        "Closing it stops the engine and ends your session.",
             font=_font(9), fg=DIM, bg=BG, justify="center").pack(side="bottom", pady=(0, 18))

    # closing the window (the X) quits the server too — no orphan process
    root.protocol("WM_DELETE_WINDOW", quit_app)
    root.mainloop()
    # if mainloop returns without quit_app (rare), stop the process anyway
    os._exit(0)


# Backwards-compatible alias (older call sites / --no-window path).
def launch_browser(port):
    launch_control_window(port)


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
        # Themed like the control window so the update step does not flash a
        # default grey dialog before the burgundy one.
        BG, FG, RED = "#25101a", "#e8d0d5", "#e41b36"
        root = tk.Tk()
        root.title("StemTube Desktop")
        root.configure(bg=BG)
        try:
            root.geometry("520x200"); root.resizable(False, False)
        except Exception:
            pass
        tk.Label(root, text="STEMTUBE DESKTOP", fg=RED, bg=BG,
                 font=tkfont.Font(size=18, weight="bold")).pack(pady=(28, 6))
        msg_var = tk.StringVar(value="Checking for updates…")
        tk.Label(root, textvariable=msg_var, fg=FG, bg=BG).pack(pady=(0, 14))
        try:
            style = ttk.Style(root)
            style.theme_use("default")
            style.configure("StemTube.Horizontal.TProgressbar", troughcolor="#3a1a24",
                            background=RED, bordercolor=BG, lightcolor=RED,
                            darkcolor=RED, thickness=8)
            bar = ttk.Progressbar(root, orient="horizontal", length=420,
                                  mode="indeterminate",
                                  style="StemTube.Horizontal.TProgressbar")
        except Exception:
            bar = ttk.Progressbar(root, orient="horizontal", length=420, mode="indeterminate")
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
    else:
        # Every platform: default browser + small Tk control window.
        launch_control_window(port)


if __name__ == '__main__':
    main()
