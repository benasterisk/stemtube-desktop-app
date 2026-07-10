"""
StemTube Desktop Friend — Desktop application for music analysis and stem extraction.
Free edition with YouTube download support. No licensing, no server deployment,
no mobile, no jam sessions.
"""
# CRITICAL: Handle demucs subprocess mode BEFORE anything else
# When PyInstaller calls this exe with --demucs-separate, run demucs and exit
import os
import sys

if '--demucs-separate' in sys.argv:
    # Strip our flag and pass remaining args to demucs.separate
    args = [a for a in sys.argv[1:] if a != '--demucs-separate']
    sys.argv = ['demucs.separate'] + args
    from demucs.separate import main as demucs_main
    demucs_main()
    sys.exit(0)

import io

# Fix Windows console encoding — cp1252 cannot handle emoji/unicode in print()
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def configure_gpu_and_restart():
    """
    Configure LD_LIBRARY_PATH for CUDA/cuDNN and restart Python if needed.
    This MUST be the very first code that runs, before ANY imports.
    On Windows, LD_LIBRARY_PATH is not used — CUDA DLLs are found via PATH.
    """
    if os.environ.get('_STEMTUBE_GPU_CONFIGURED') == '1':
        print(f"[INIT] GPU libraries configured: LD_LIBRARY_PATH={os.environ.get('LD_LIBRARY_PATH', 'NOT SET')}")
        return

    import platform
    if platform.system() == 'Windows':
        # Windows: CUDA DLLs are found via PATH, no LD_LIBRARY_PATH needed
        os.environ['_STEMTUBE_GPU_CONFIGURED'] = '1'
        try:
            import site
            site_packages = site.getsitepackages()[0]
            cudnn_bin = os.path.join(site_packages, 'nvidia', 'cudnn', 'bin')
            if os.path.exists(cudnn_bin):
                current_path = os.environ.get('PATH', '')
                if cudnn_bin not in current_path:
                    os.environ['PATH'] = f"{cudnn_bin};{current_path}"
                    print(f"[INIT] Added cuDNN to PATH: {cudnn_bin}")
        except Exception as e:
            print(f"[INIT] Could not configure GPU on Windows: {e}")
        return

    # Linux: set LD_LIBRARY_PATH and restart
    try:
        import site
        site_packages = site.getsitepackages()[0]
        cudnn_lib_path = os.path.join(site_packages, 'nvidia', 'cudnn', 'lib')

        if os.path.exists(cudnn_lib_path):
            current_ld_path = os.environ.get('LD_LIBRARY_PATH', '')
            if cudnn_lib_path not in current_ld_path:
                if current_ld_path:
                    os.environ['LD_LIBRARY_PATH'] = f"{cudnn_lib_path}:{current_ld_path}"
                else:
                    os.environ['LD_LIBRARY_PATH'] = cudnn_lib_path
                os.environ['_STEMTUBE_GPU_CONFIGURED'] = '1'
                print(f"[INIT] Restarting with GPU library path: {cudnn_lib_path}")
                os.execv(sys.executable, [sys.executable] + sys.argv)
            else:
                print(f"[INIT] GPU libraries already configured")
        else:
            print(f"[INIT] No GPU libraries found (CPU mode)")
    except Exception as e:
        print(f"[INIT] Could not configure GPU: {e}")

configure_gpu_and_restart()

# Now safe to import everything
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import secrets
import subprocess
from flask import Flask
from flask_session import Session

from core.logging_config import setup_logging, get_logger

log_config = setup_logging(app_name="stemtube_desktop", log_level="INFO")
logger = get_logger(__name__)

logger.info("StemTube Desktop application starting up...")

from core.config import (
    ensure_ffmpeg_available, ensure_valid_downloads_directory,
    validate_and_fix_config_paths,
    PORT, HOST,
)
from core.auth_db import init_db, get_user_by_id, ensure_desktop_user
from core.auth_models import User
from core.downloads_db import (
    init_table as init_downloads_table,
    init_recordings_table,
    comprehensive_cleanup,
)
from extensions import socketio, login_manager
from edition import HAS_LICENSE, HAS_YOUTUBE

if HAS_LICENSE:
    from core.licensing import is_authorized, get_license_status

# ------------------------------------------------------------------
# Bootstrap
# ------------------------------------------------------------------
logger.info("Initializing application components...")

validate_and_fix_config_paths()
ensure_ffmpeg_available()
logger.info("FFmpeg availability ensured")

init_db()
logger.info("Authentication database initialized")

# Ensure the single desktop user exists and get their ID
DESKTOP_USER_ID = ensure_desktop_user()
logger.info(f"Desktop user ready (id={DESKTOP_USER_ID})")

init_downloads_table()
logger.info("Downloads database initialized")

init_recordings_table()
logger.info("Recordings database initialized")

comprehensive_cleanup()
logger.info("Database cleanup completed")

# ------------------------------------------------------------------
# yt-dlp auto-update (Friend edition: YouTube enabled)
# ------------------------------------------------------------------
if HAS_YOUTUBE:
    def check_ytdlp_update():
        """Check and update yt-dlp nightly to avoid YouTube blocks.

        Runs in a BACKGROUND daemon thread so it NEVER delays the web server
        startup: this is a network call (pip install) that can take 25–120s,
        and doing it synchronously before socketio.run() made the server miss
        the launcher's 120s startup timeout on slower machines/connections
        (the app would fail to open). The update is best-effort; if it's still
        running when the user triggers a download, yt-dlp simply uses the
        currently-installed version.
        """
        try:
            logger.info("Checking for yt-dlp nightly updates (background)...")
            # CREATE_NO_WINDOW prevents a console flash when spawned from a
            # GUI parent (Tauri shell). Falls back to 0 on non-Windows.
            no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-U", "--pre", "--quiet", "yt-dlp[default]"],
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=no_window
            )
            if result.returncode == 0:
                import yt_dlp
                logger.info(f"yt-dlp nightly is up to date: {yt_dlp.version.__version__}")
            else:
                logger.warning(f"yt-dlp update check failed: {result.stderr}")
        except Exception as e:
            logger.warning(f"Could not check yt-dlp updates: {e}")

    # Fire-and-forget in a daemon thread so the web server binds the port
    # immediately (the launcher waits for that, with a 120s budget).
    import threading as _threading
    _threading.Thread(target=check_ytdlp_update, daemon=True).start()

    def _ensure_js_runtime():
        """Fetch the bundled Deno runtime if no JS runtime is present.

        yt-dlp needs deno or node to solve YouTube's JS challenges; without
        one, downloads fail with "Requested format is not available" on any
        machine that doesn't happen to have Node installed.
        """
        try:
            from core.js_runtime import ensure_deno_available
            if ensure_deno_available():
                logger.info("JS runtime for yt-dlp is available (deno/node)")
            else:
                logger.warning("No JS runtime (deno/node) — YouTube downloads may fail")
        except Exception as e:
            logger.warning(f"JS runtime check failed: {e}")

    _threading.Thread(target=_ensure_js_runtime, daemon=True).start()

# ------------------------------------------------------------------
# Flask & SocketIO setup
# ------------------------------------------------------------------
logger.info("Setting up Flask application and SocketIO...")
app = Flask(__name__)

# Desktop mode: auto-generate secret key if not set (no .env needed)
SECRET_KEY = os.environ.get('FLASK_SECRET_KEY')
if not SECRET_KEY:
    # Generate and persist a secret key for session stability across restarts
    secret_key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.secret_key')
    if os.path.exists(secret_key_file):
        with open(secret_key_file, 'r') as f:
            SECRET_KEY = f.read().strip()
    if not SECRET_KEY:
        SECRET_KEY = secrets.token_hex(32)
        with open(secret_key_file, 'w') as f:
            f.write(SECRET_KEY)
        logger.info("Generated new secret key for desktop mode")

app.config['SECRET_KEY'] = SECRET_KEY
logger.info("Flask SECRET_KEY configured")

app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 86400 * 365  # 1 year for desktop
app.config['SESSION_FILE_DIR'] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'flask_session')
os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)

app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
app.config['REMEMBER_COOKIE_HTTPONLY'] = True

Session(app)

login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    user_data = get_user_by_id(user_id)
    return User(user_data) if user_data else None

socketio.init_app(
    app,
    cors_allowed_origins="*",
    logger=True,
    engineio_logger=True,
    async_mode='threading',
    manage_session=False
)

from core.request_logging import setup_request_logging
setup_request_logging(app)
logger.info("Request logging middleware configured")



# ------------------------------------------------------------------
# SocketIO: auto-join user room on connect (for per-user events)
# ------------------------------------------------------------------
from flask_socketio import join_room
from flask_login import current_user as _cu

@socketio.on('connect')
def handle_connect():
    if _cu.is_authenticated:
        room = f"user_{_cu.id}"
        join_room(room)
        logger.info(f"WebSocket client joined room: {room}")

# ------------------------------------------------------------------
# Register blueprints (desktop only — no jam, no mobile)
# ------------------------------------------------------------------
from routes import register_all_blueprints
register_all_blueprints(app)

logger.info("All routes registered successfully")

# ------------------------------------------------------------------
# YouTube client initialization (Friend edition)
# ------------------------------------------------------------------
if HAS_YOUTUBE:
    from extensions import init_aiotube_client
    init_aiotube_client()
    logger.info("YouTube client (yt-dlp) initialized")

# ------------------------------------------------------------------
# License check (only for editions with licensing)
# ------------------------------------------------------------------
if HAS_LICENSE:
    license_info = get_license_status()
    if license_info['status'] == 'expired':
        logger.error("License expired — please activate a valid license")
        logger.error(f"Your Hardware ID: {license_info['hardware_id']}")
    elif license_info['status'] == 'trial':
        logger.info(f"Trial mode: {license_info['trial_days_remaining']:.1f} days remaining")
    elif license_info['status'] == 'licensed':
        logger.info("License validated successfully")

# ------------------------------------------------------------------
# Run
# ------------------------------------------------------------------
if __name__ == '__main__':
    # Bind host comes from config (HOST). 0.0.0.0 exposes the app on the LAN;
    # 127.0.0.1 keeps it local-only. (No real network auth — LAN-trusted only.)
    desktop_host = HOST
    logger.info(f"Starting StemTube Desktop on {desktop_host}:{PORT}")
    socketio.run(app, host=desktop_host, port=PORT, debug=False, allow_unsafe_werkzeug=True)
