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
    """Open a native desktop window with pywebview."""
    try:
        import webview

        url = f'http://127.0.0.1:{port}'

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

        # Start pywebview (blocks until window is closed)
        webview.start(debug=args.debug)

    except ImportError:
        print("[LAUNCHER] pywebview not installed — opening in default browser instead")
        print(f"[LAUNCHER] Install it with: pip install pywebview")
        webbrowser.open(f'http://127.0.0.1:{port}')
        # Keep the process alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


def launch_browser(port):
    """Fallback: open in default browser."""
    url = f'http://127.0.0.1:{port}'
    print(f"[LAUNCHER] Opening {url} in default browser...")
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


def main():
    port = get_port()

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
        launch_browser(port)
    else:
        launch_native_window(port)


if __name__ == '__main__':
    main()
