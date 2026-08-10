"""
Configuration module for StemTube Desktop.
Contains application settings, paths, and constants.
Standard edition: localhost/LAN, single-user, local files only.
"""
import os
import json
import platform
from pathlib import Path
from dotenv import load_dotenv
import tempfile
import urllib.request
import zipfile
import shutil

# Load environment variables from .env file (optional in desktop mode)
load_dotenv()

# Application information
APP_NAME = "StemTube Desktop"
APP_VERSION = "1.0.0"
APP_AUTHOR = "StemTube"

# ============================================================================
# Server Configuration - SINGLE SOURCE OF TRUTH
# ============================================================================
PORT = 5011
# 0.0.0.0 = listen on all interfaces so the app is reachable from other devices
# on the LAN (e.g. http://<machine-LAN-IP>:5011). NOTE: there is no real network
# auth (desktop auto-login) — only expose this on a trusted local network.
HOST = "0.0.0.0"

# Paths
# APP_DIR = where the core/ module lives (read-only in installed mode)
# USER_DATA_DIR = writable directory for user data (config, DB, downloads, logs)
APP_DIR = os.path.dirname(os.path.abspath(__file__))

def _get_user_data_dir():
    """Get the writable user data directory.

    Detection priority (most specific first):
    1. STEMTUBE_DATA_DIR env var (Tauri shell sets this)
    2. '.dev' marker file at project root (explicit dev mode)
    3. Project root contains 'src-tauri/' (source checkout)
    4. Otherwise: %LOCALAPPDATA%/StemTube Desktop/
    """
    # Explicit env override (Tauri shell can set this to point to the right place)
    env_data = os.environ.get('STEMTUBE_DATA_DIR')
    if env_data:
        return env_data

    project_root = os.path.dirname(APP_DIR)  # parent of core/
    dev_marker = os.path.join(project_root, '.dev')

    # Dev mode heuristic: explicit marker, OR the source tree with src-tauri/
    if os.path.exists(dev_marker) or os.path.exists(os.path.join(project_root, 'src-tauri', 'Cargo.toml')):
        return os.path.join(APP_DIR)  # Dev: use core/ as before

    # Installed mode: use LOCALAPPDATA/StemTube Desktop
    if platform.system() == "Windows":
        base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        data_dir = os.path.join(base, 'StemTube Desktop')
    else:
        data_dir = os.path.expanduser('~/.stemtube-desktop')

    return data_dir

USER_DATA_DIR = _get_user_data_dir()

# Read-only paths (bundled with the app)
RESOURCES_DIR = os.path.join(APP_DIR, "resources")
FFMPEG_DIR = os.path.join(APP_DIR, "ffmpeg")

# Writable paths (user data)
DOWNLOADS_DIR = os.path.join(USER_DATA_DIR, "downloads")
MODELS_DIR = os.path.join(USER_DATA_DIR, "models")
CONFIG_FILE = os.path.join(USER_DATA_DIR, "config.json")
LOGS_DIR = os.path.join(USER_DATA_DIR, "logs")
DB_DIR = USER_DATA_DIR

# Copy default config if it doesn't exist in user data dir
_default_config = os.path.join(APP_DIR, "config.json")
if not os.path.exists(CONFIG_FILE) and os.path.exists(_default_config):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    import shutil as _shutil
    _shutil.copy2(_default_config, CONFIG_FILE)

# Create necessary directories
os.makedirs(RESOURCES_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(FFMPEG_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(DB_DIR, exist_ok=True)

# FFmpeg settings
if platform.system() == "Windows":
    FFMPEG_EXECUTABLE = os.path.join(FFMPEG_DIR, "bin", "ffmpeg.exe")
    FFPROBE_EXECUTABLE = os.path.join(FFMPEG_DIR, "bin", "ffprobe.exe")
else:
    FFMPEG_EXECUTABLE = "ffmpeg"
    FFPROBE_EXECUTABLE = "ffprobe"

# Default application settings
DEFAULT_SETTINGS = {
    "theme": "dark",
    "downloads_directory": DOWNLOADS_DIR,
    "max_concurrent_downloads": 3,
    "preferred_video_quality": "720p",
    "preferred_audio_quality": "best",
    "use_gpu_for_extraction": True,
    "default_stem_model": "htdemucs",
    "max_concurrent_extractions": 1,
    "lyrics_model_size": "medium",
    "ffmpeg_path": "",
    "auto_check_updates": True,
    "extraction_timeout_minutes": 30,
    "extraction_progress_timeout_minutes": 5,
    "enable_silent_stem_detection": True,
    "silent_stem_threshold_db": -40.0,
    "silent_stem_min_duration_ratio": 0.05,
    "browser_logging_enabled": False,
    "browser_logging_level": "error",
    "browser_logging_flush_interval": 300,
    "browser_logging_buffer_size": 50,
    "chord_backend": "btc",
    "chords_use_btc": True,
    "chords_use_madmom": True,
    "chords_use_hybrid": True,
}


def load_config():
    """Load configuration from config file or create default if not exists."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            print(f"Error loading config file. Using defaults.")
            return DEFAULT_SETTINGS.copy()
    else:
        save_config(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()


def save_config(config_data):
    """Save configuration to config file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_data, f, indent=4)
        return True
    except IOError:
        print(f"Error saving config file.")
        return False


# Load configuration
CONFIG = load_config()


def validate_and_fix_config_paths():
    """Validate and fix all paths in config on startup."""
    print("Validating configuration paths for current platform...")

    downloads_dir = get_setting("downloads_directory", DOWNLOADS_DIR)
    original_path = downloads_dir

    normalized_path = normalize_path_for_platform(downloads_dir)

    if normalized_path != original_path:
        print(f"Fixed downloads_directory path:")
        print(f"  From: {original_path}")
        print(f"  To:   {normalized_path}")
        update_setting("downloads_directory", normalized_path)

        if platform.system() != "Windows":
            invalid_dir_patterns = ["C:\\Users", "C:\\"]
            for pattern in invalid_dir_patterns:
                try:
                    for item in os.listdir('.'):
                        if item.startswith(pattern):
                            invalid_path = os.path.join('.', item)
                            if os.path.isdir(invalid_path):
                                print(f"Found invalid directory with Windows path name: {item}")
                                try:
                                    shutil.rmtree(invalid_path)
                                    print(f"Successfully removed invalid directory")
                                except Exception as e:
                                    print(f"Warning: Could not remove invalid directory: {e}")
                except Exception as e:
                    print(f"Error during directory cleanup: {e}")

    ensure_valid_downloads_directory()
    print("Configuration validation complete.")
    return True


def get_setting(key, default=None):
    """Get a setting value from config."""
    return CONFIG.get(key, default)


def update_setting(key, value):
    """Update a setting value and save config."""
    CONFIG[key] = value
    save_config(CONFIG)
    return True


def get_all_settings():
    """Get all current settings."""
    return CONFIG.copy()


def is_windows_absolute_path(path_str):
    """Check if a path string is a Windows-style absolute path."""
    if not isinstance(path_str, str):
        return False
    if len(path_str) >= 2 and path_str[1] == ':' and path_str[0].isalpha():
        return True
    return False


def normalize_path_for_platform(path_str):
    """Normalize a path string to work on the current platform."""
    if not isinstance(path_str, str):
        return DOWNLOADS_DIR

    current_platform = platform.system()

    if current_platform != "Windows" and is_windows_absolute_path(path_str):
        print(f"Warning: Detected Windows absolute path on {current_platform}: {path_str}")
        return DOWNLOADS_DIR

    if current_platform == "Windows" and path_str.startswith('/') and not is_windows_absolute_path(path_str):
        print(f"Warning: Detected Unix absolute path on Windows: {path_str}")
        return DOWNLOADS_DIR

    if not os.path.isabs(path_str):
        path_str = os.path.join(os.path.dirname(APP_DIR), path_str)

    return path_str


def ensure_valid_downloads_directory():
    """Ensures that the configured downloads directory is valid and accessible."""
    downloads_dir = get_setting("downloads_directory", DOWNLOADS_DIR)
    downloads_dir = normalize_path_for_platform(downloads_dir)

    try:
        os.makedirs(downloads_dir, exist_ok=True)
        test_file_path = os.path.join(downloads_dir, ".write_test")
        with open(test_file_path, 'w') as f:
            f.write("test")
        os.remove(test_file_path)

        configured_path = get_setting("downloads_directory", DOWNLOADS_DIR)
        if downloads_dir != configured_path:
            update_setting("downloads_directory", downloads_dir)

        return downloads_dir
    except (IOError, OSError, PermissionError) as e:
        print(f"Warning: Configured downloads directory is not accessible: {e}")
        print(f"Falling back to default downloads directory: {DOWNLOADS_DIR}")
        update_setting("downloads_directory", DOWNLOADS_DIR)
        return DOWNLOADS_DIR


# FFmpeg path management
def get_ffmpeg_path():
    """Get FFmpeg executable path."""
    custom_path = get_setting("ffmpeg_path")
    if custom_path:
        if os.path.isdir(custom_path):
            ffmpeg_path = os.path.join(custom_path, "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
            if os.path.exists(ffmpeg_path):
                return ffmpeg_path
        elif os.path.isfile(custom_path):
            return custom_path

    if os.path.exists(FFMPEG_EXECUTABLE):
        return FFMPEG_EXECUTABLE

    return "ffmpeg"


def get_ffprobe_path():
    """Get FFprobe executable path."""
    custom_path = get_setting("ffmpeg_path")
    if custom_path:
        if os.path.isdir(custom_path):
            probe_path = os.path.join(custom_path, "ffprobe.exe" if platform.system() == "Windows" else "ffprobe")
            if os.path.exists(probe_path):
                return probe_path
        elif os.path.isfile(custom_path) and "ffmpeg" in os.path.basename(custom_path).lower():
            probe_path = os.path.join(os.path.dirname(custom_path),
                                     "ffprobe.exe" if platform.system() == "Windows" else "ffprobe")
            if os.path.exists(probe_path):
                return probe_path

    if os.path.exists(FFPROBE_EXECUTABLE):
        return FFPROBE_EXECUTABLE

    return "ffprobe"


def download_ffmpeg():
    """Download and set up FFmpeg if not already available."""
    if os.path.exists(FFMPEG_EXECUTABLE) and os.path.exists(FFPROBE_EXECUTABLE):
        return True, "FFmpeg already installed"

    try:
        if platform.system() == "Windows":
            ffmpeg_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
            print(f"Downloading FFmpeg from {ffmpeg_url}...")

            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
                temp_path = temp_file.name

            urllib.request.urlretrieve(ffmpeg_url, temp_path)

            with zipfile.ZipFile(temp_path, 'r') as zip_ref:
                temp_extract_dir = tempfile.mkdtemp()
                zip_ref.extractall(temp_extract_dir)

                extracted_dirs = [d for d in os.listdir(temp_extract_dir) if os.path.isdir(os.path.join(temp_extract_dir, d))]
                if not extracted_dirs:
                    return False, "Failed to extract FFmpeg"

                extracted_dir = os.path.join(temp_extract_dir, extracted_dirs[0])
                for item in os.listdir(extracted_dir):
                    src = os.path.join(extracted_dir, item)
                    dst = os.path.join(FFMPEG_DIR, item)
                    if os.path.exists(dst):
                        if os.path.isdir(dst):
                            shutil.rmtree(dst)
                        else:
                            os.remove(dst)
                    shutil.move(src, dst)

                shutil.rmtree(temp_extract_dir)
                os.remove(temp_path)

            update_setting("ffmpeg_path", os.path.join(FFMPEG_DIR, "bin"))
            return True, "FFmpeg downloaded and installed successfully"
        else:
            return False, "Automatic FFmpeg installation is only supported on Windows. Please install FFmpeg manually."
    except Exception as e:
        return False, f"Error downloading FFmpeg: {str(e)}"


def ensure_ffmpeg_available():
    """Ensure FFmpeg is available, downloading it if necessary."""
    try:
        import subprocess

        if platform.system() == "Windows":
            result = subprocess.run(["where", "ffmpeg"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0 and result.stdout.strip():
                ffmpeg_system_path = result.stdout.strip().split('\n')[0].strip()
                ffmpeg_dir = os.path.dirname(ffmpeg_system_path)
                ffprobe_path = os.path.join(ffmpeg_dir, "ffprobe.exe")
                if os.path.exists(ffprobe_path):
                    update_setting("ffmpeg_path", ffmpeg_dir)
                    if ffmpeg_dir not in os.environ.get("PATH", ""):
                        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
                    print(f"Found system FFmpeg at: {ffmpeg_dir}")
                    return True
        else:
            result = subprocess.run(["which", "ffmpeg"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0 and result.stdout.strip():
                ffmpeg_system_path = result.stdout.strip()
                ffmpeg_dir = os.path.dirname(ffmpeg_system_path)
                ffprobe_path = os.path.join(ffmpeg_dir, "ffprobe")
                if os.path.exists(ffprobe_path):
                    update_setting("ffmpeg_path", ffmpeg_dir)
                    print(f"Found system FFmpeg at: {ffmpeg_dir}")
                    return True
    except Exception as e:
        print(f"Error checking system FFmpeg: {e}")

    if os.path.exists(FFMPEG_EXECUTABLE) and os.path.exists(FFPROBE_EXECUTABLE):
        ffmpeg_dir = os.path.dirname(FFMPEG_EXECUTABLE)
        update_setting("ffmpeg_path", ffmpeg_dir)
        # Prepend bundled ffmpeg to PATH so subprocesses (madmom, demucs) find it
        if ffmpeg_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
        print(f"Using bundled FFmpeg at: {ffmpeg_dir}")
        return True

    print("FFmpeg not found in system or bundled. Attempting to download...")
    success, message = download_ffmpeg()
    print(message)
    return success


# Check for diffq availability
def check_diffq_available():
    """Check if diffq is available for advanced models."""
    try:
        import diffq
        return True
    except ImportError:
        return False


# Stem extraction models
STEM_MODELS = {
    "htdemucs": {
        "name": "HTDemucs (4 stems)",
        "stems": ["vocals", "drums", "bass", "other"],
        "path": os.path.join(MODELS_DIR, "htdemucs"),
        "url": "https://dl.fbaipublicfiles.com/demucs/v4_htdemucs.th",
        "description": "High quality 4-stem separation (vocals, drums, bass, other)",
        "requires_diffq": False,
        "compatible": True
    },
    "htdemucs_6s": {
        "name": "HTDemucs 6-stem",
        "stems": ["vocals", "drums", "bass", "guitar", "piano", "other"],
        "path": os.path.join(MODELS_DIR, "htdemucs_6s"),
        "url": "https://dl.fbaipublicfiles.com/demucs/v4_htdemucs_6s.th",
        "description": "6-stem separation (vocals, drums, bass, guitar, piano, other)",
        "requires_diffq": False,
        "compatible": True
    },
    "htdemucs_ft": {
        "name": "HTDemucs Fine-Tuned",
        "stems": ["vocals", "drums", "bass", "other"],
        "path": os.path.join(MODELS_DIR, "htdemucs_ft"),
        "url": "https://dl.fbaipublicfiles.com/demucs/v4_htdemucs_ft.th",
        "description": "Fine-tuned 4-stem separation with better quality",
        "requires_diffq": False,
        "compatible": True
    },
    "mdx_extra": {
        "name": "MDX Extra",
        "stems": ["vocals", "drums", "bass", "other"],
        "path": os.path.join(MODELS_DIR, "mdx_extra"),
        "url": "https://dl.fbaipublicfiles.com/demucs/mdx_final/mdx_extra.th",
        "description": "MDX model with enhanced vocal separation",
        "requires_diffq": False,
        "compatible": True
    },
    "mdx_extra_q": {
        "name": "MDX Extra Q (Requires diffq)",
        "stems": ["vocals", "drums", "bass", "other"],
        "path": os.path.join(MODELS_DIR, "mdx_extra_q"),
        "url": "https://dl.fbaipublicfiles.com/demucs/mdx_final/83fc094f-4a16d450.th",
        "description": "Optimized MDX model for superior quality (requires diffq package)",
        "requires_diffq": True,
        "compatible": check_diffq_available()
    }
}


def get_compatible_models():
    """Get only models that are compatible with current system."""
    compatible = {}
    for model_id, model_info in STEM_MODELS.items():
        if model_info.get("compatible", True):
            compatible[model_id] = model_info
    return compatible


def get_fallback_model():
    """Get a reliable fallback model that works on all systems."""
    return "htdemucs"
