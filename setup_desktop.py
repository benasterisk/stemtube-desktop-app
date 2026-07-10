#!/usr/bin/env python3
"""
StemTube Desktop — Windows Setup Script
========================================
Automated setup for Windows 11 desktop deployment.
Creates venv, installs dependencies, downloads models, configures FFmpeg.

Usage:
    python setup_desktop.py              # Auto-detect GPU and install
    python setup_desktop.py --cpu-only   # Force CPU-only (smaller install)
    python setup_desktop.py --skip-models # Skip ML model pre-download

Requirements:
    - Python 3.12+ (python.org installer, NOT Windows Store version)
    - Node.js 20+ (for yt-dlp JS challenge solving)
    - Internet connection for downloading dependencies
    - ~4GB disk space (CPU) or ~8GB (GPU with models)
"""

import os
import sys
import platform
import subprocess
import shutil
import argparse
import urllib.request
import zipfile
import tempfile
from pathlib import Path

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

VENV_DIR = "venv"
PYTHON_MIN_VERSION = (3, 12)
FFMPEG_WIN_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

ESSENTIAL_PACKAGES = [
    "flask",
    "flask-login",
    "flask-session",
    "flask-socketio",
    "eventlet",
    "requests",
    "python-dotenv",
    "Pillow",
    "librosa",
    "soundfile",
    "scipy",
    "scikit-learn",
    "yt-dlp[default]",
    "faster-whisper",
    "syncedlyrics",
    "pychord",
    "mir_eval",           # Required by BTC chord detector
    "beautifulsoup4",
    "pywebview",
    "werkzeug",
]
# msaf is intentionally omitted: it imports scipy.inf which was removed
# in SciPy 1.13+, breaking import. Structure detection falls back gracefully
# when msaf is missing.

PYTORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"

# CUDA compatibility matrix (same as setup_dependencies.py)
CUDA_MATRIX = [
    {"min": (12, 4), "index": "https://download.pytorch.org/whl/cu124", "cudnn": "nvidia-cudnn-cu12"},
    {"min": (12, 0), "index": "https://download.pytorch.org/whl/cu121", "cudnn": "nvidia-cudnn-cu12"},
    {"min": (11, 8), "index": "https://download.pytorch.org/whl/cu118", "cudnn": "nvidia-cudnn-cu11"},
    {"min": (11, 0), "index": "https://download.pytorch.org/whl/cu117", "cudnn": "nvidia-cudnn-cu11"},
]


def log(msg, level="INFO"):
    prefix = {"INFO": "[+]", "WARN": "[!]", "ERROR": "[X]", "OK": "[v]"}
    print(f"{prefix.get(level, '[*]')} {msg}")


def check_python_version():
    """Verify Python version meets minimum requirements."""
    v = sys.version_info
    if (v.major, v.minor) < PYTHON_MIN_VERSION:
        log(f"Python {PYTHON_MIN_VERSION[0]}.{PYTHON_MIN_VERSION[1]}+ required, found {v.major}.{v.minor}", "ERROR")
        sys.exit(1)
    log(f"Python {v.major}.{v.minor}.{v.micro} OK")


def check_node():
    """Check if Node.js is available (needed by yt-dlp for JS challenges)."""
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        version = result.stdout.strip()
        log(f"Node.js {version} found")
        return True
    except FileNotFoundError:
        log("Node.js not found — YouTube downloads may fail without it", "WARN")
        log("Install from https://nodejs.org/ (LTS v20+)", "WARN")
        return False


def detect_gpu():
    """Detect NVIDIA GPU and CUDA version."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            gpu_info = result.stdout.strip()
            log(f"NVIDIA GPU detected: {gpu_info}")

            # Get CUDA version
            cuda_result = subprocess.run(
                ["nvidia-smi"],
                capture_output=True, text=True, timeout=10
            )
            import re
            match = re.search(r'CUDA Version:\s+([\d.]+)', cuda_result.stdout)
            if match:
                version_str = match.group(1)
                parts = version_str.split('.')
                return (int(parts[0]), int(parts[1]))
            return (11, 8)  # fallback
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    log("No NVIDIA GPU detected — will install CPU-only PyTorch")
    return None


def get_cuda_config(cuda_version):
    """Get PyTorch index URL and cuDNN package for detected CUDA version."""
    for entry in CUDA_MATRIX:
        if cuda_version >= entry["min"]:
            log(f"CUDA {cuda_version[0]}.{cuda_version[1]} → PyTorch index: {entry['index']}")
            return entry
    return None


def create_venv():
    """Create Python virtual environment."""
    if os.path.exists(VENV_DIR):
        log(f"Virtual environment '{VENV_DIR}' already exists — reusing")
        return

    log("Creating virtual environment...")
    subprocess.run([sys.executable, "-m", "venv", VENV_DIR], check=True)
    log("Virtual environment created", "OK")


def get_pip():
    """Get the pip executable path in the venv."""
    if platform.system() == "Windows":
        return os.path.join(VENV_DIR, "Scripts", "pip.exe")
    return os.path.join(VENV_DIR, "bin", "pip")


def get_python():
    """Get the python executable path in the venv."""
    if platform.system() == "Windows":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    return os.path.join(VENV_DIR, "bin", "python")


def pip_install(packages, extra_args=None):
    """Install packages via pip."""
    cmd = [get_pip(), "install"] + (extra_args or []) + packages
    log(f"Installing: {', '.join(packages)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"pip install failed: {result.stderr[-500:]}", "ERROR")
        return False
    return True


def install_pytorch(cuda_version=None, cpu_only=False):
    """Install PyTorch with appropriate GPU/CPU support."""
    if cpu_only or cuda_version is None:
        log("Installing PyTorch (CPU-only)...")
        pip_install(
            ["torch", "torchaudio"],
            ["--index-url", PYTORCH_CPU_INDEX]
        )
    else:
        config = get_cuda_config(cuda_version)
        if config:
            log(f"Installing PyTorch (GPU, CUDA {cuda_version[0]}.{cuda_version[1]})...")
            pip_install(
                ["torch", "torchaudio"],
                ["--index-url", config["index"]]
            )
            pip_install([config["cudnn"]])
        else:
            log(f"CUDA {cuda_version} not in compatibility matrix — falling back to CPU", "WARN")
            pip_install(
                ["torch", "torchaudio"],
                ["--index-url", PYTORCH_CPU_INDEX]
            )


def _install_madmom_windows():
    """Install madmom on Windows using MSVC Build Tools with rc.exe workaround."""
    import glob as _glob

    # Find vcvarsall.bat
    vcvarsall_patterns = [
        r"C:\Program Files (x86)\Microsoft Visual Studio\*\*\VC\Auxiliary\Build\vcvarsall.bat",
        r"C:\Program Files\Microsoft Visual Studio\*\*\VC\Auxiliary\Build\vcvarsall.bat",
    ]
    vcvarsall = None
    for pat in vcvarsall_patterns:
        found = _glob.glob(pat)
        if found:
            vcvarsall = found[0]
            break
    if not vcvarsall:
        log("MSVC Build Tools not found — cannot compile madmom", "ERROR")
        log("Install via: winget install Microsoft.VisualStudio.2022.BuildTools", "WARN")
        return

    # Find rc.exe (Windows SDK resource compiler)
    rc_patterns = [r"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\rc.exe"]
    rc_dir = None
    for pat in rc_patterns:
        found = _glob.glob(pat)
        if found:
            rc_dir = os.path.dirname(found[-1])  # Use latest version
            break

    # Copy rc.exe to venv\Scripts so link.exe can find it via PATH
    if rc_dir:
        for f in ["rc.exe", "rcdll.dll"]:
            src = os.path.join(rc_dir, f)
            dst = os.path.join(VENV_DIR, "Scripts", f)
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)

    # Build via batch file to inherit MSVC environment
    bat_path = os.path.join(os.path.dirname(__file__), "_build_madmom.bat")
    pip_exe = os.path.abspath(get_pip())
    with open(bat_path, "w") as f:
        f.write(f'@echo off\n')
        f.write(f'call "{vcvarsall}" x64\n')
        f.write(f'set DISTUTILS_USE_SDK=1\n')
        f.write(f'set MSSdk=1\n')
        f.write(f'"{pip_exe}" install --no-build-isolation madmom\n')

    result = subprocess.run(["cmd", "/C", bat_path], capture_output=True, text=True)
    os.remove(bat_path)

    if result.returncode == 0:
        log("madmom installed successfully", "OK")
    else:
        log(f"madmom build failed: {result.stderr[-300:]}", "ERROR")


def install_dependencies():
    """Install all Python dependencies."""
    log("Upgrading pip...")
    subprocess.run([get_pip(), "install", "--upgrade", "pip"], capture_output=True)

    log("Installing essential packages...")
    pip_install(ESSENTIAL_PACKAGES)

    # Install demucs separately (needs torch first)
    log("Installing demucs...")
    pip_install(["demucs"])

    # Install Cython + madmom (needs specific numpy)
    log("Installing madmom dependencies...")
    pip_install(["Cython"])
    pip_install(["numpy==1.26.4"])  # madmom requires numpy <2.0

    # madmom requires C compilation; on Windows, needs MSVC + rc.exe workaround
    if platform.system() == "Windows":
        log("Installing madmom (Windows — requires MSVC Build Tools)...")
        _install_madmom_windows()
    else:
        pip_install(["madmom"])

    # Patch madmom for numpy compatibility
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        subprocess.run([get_python(), "patch_madmom.py"], capture_output=True, text=True, env=env)
        log("madmom patched for numpy compatibility", "OK")
    except Exception:
        log("madmom patch skipped (non-critical)", "WARN")


def setup_ffmpeg():
    """Download and setup FFmpeg for Windows."""
    ffmpeg_dir = os.path.join("core", "ffmpeg")
    ffmpeg_exe = os.path.join(ffmpeg_dir, "bin", "ffmpeg.exe")

    if os.path.exists(ffmpeg_exe):
        log("FFmpeg already installed", "OK")
        return

    if platform.system() != "Windows":
        # On Linux/macOS, ffmpeg is typically installed via package manager
        if shutil.which("ffmpeg"):
            log("System FFmpeg found", "OK")
            return
        log("FFmpeg not found — install via: sudo apt install ffmpeg", "WARN")
        return

    log("Downloading FFmpeg for Windows...")
    try:
        tmp_zip = os.path.join(tempfile.gettempdir(), "ffmpeg.zip")
        urllib.request.urlretrieve(FFMPEG_WIN_URL, tmp_zip)

        log("Extracting FFmpeg...")
        with zipfile.ZipFile(tmp_zip, 'r') as z:
            # Find the inner directory name
            names = z.namelist()
            inner_dir = names[0].split('/')[0]

            z.extractall(tempfile.gettempdir())

            # Move to core/ffmpeg/
            extracted = os.path.join(tempfile.gettempdir(), inner_dir)
            if os.path.exists(ffmpeg_dir):
                shutil.rmtree(ffmpeg_dir)
            shutil.move(extracted, ffmpeg_dir)

        os.remove(tmp_zip)
        log("FFmpeg installed", "OK")

    except Exception as e:
        log(f"FFmpeg download failed: {e}", "ERROR")
        log("Download manually from https://ffmpeg.org/download.html", "WARN")


def download_chord_library():
    """Clone guitar chord diagram database."""
    chord_path = os.path.join("static", "js", "datas", "guitar-chords-db-json")
    if os.path.exists(chord_path) and os.listdir(chord_path):
        log("Guitar chord library already present", "OK")
        return

    log("Downloading guitar chord library...")
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1",
             "https://github.com/szaza/guitar-chords-db-json.git",
             chord_path],
            capture_output=True, text=True, check=True
        )
        log("Guitar chord library installed", "OK")
    except Exception as e:
        log(f"Chord library download failed: {e}", "WARN")


def predownload_models():
    """Pre-download ML models so first run is faster."""
    log("Pre-downloading ML models (this may take several minutes)...")

    # Demucs model
    log("Downloading Demucs model (htdemucs_6s)...")
    subprocess.run(
        [get_python(), "-c",
         "from demucs.pretrained import get_model; get_model('htdemucs_6s'); print('Demucs model ready')"],
        capture_output=True, text=True
    )

    # faster-whisper model
    log("Downloading faster-whisper model (medium)...")
    subprocess.run(
        [get_python(), "-c",
         "from faster_whisper import WhisperModel; m = WhisperModel('medium', device='cpu', compute_type='int8'); print('Whisper model ready')"],
        capture_output=True, text=True
    )

    log("ML models pre-downloaded", "OK")


def main():
    parser = argparse.ArgumentParser(description='StemTube Desktop Setup')
    parser.add_argument('--cpu-only', action='store_true', help='Force CPU-only installation')
    parser.add_argument('--skip-models', action='store_true', help='Skip ML model downloads')
    args = parser.parse_args()

    print("=" * 60)
    print("  StemTube Desktop — Setup")
    print("=" * 60)
    print()

    check_python_version()
    check_node()

    # GPU detection
    cuda_version = None
    if not args.cpu_only:
        cuda_version = detect_gpu()

    create_venv()
    install_pytorch(cuda_version, cpu_only=args.cpu_only)
    install_dependencies()
    setup_ffmpeg()
    download_chord_library()

    if not args.skip_models:
        predownload_models()

    # Create necessary directories
    os.makedirs("core/downloads", exist_ok=True)
    os.makedirs("core/models", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    os.makedirs("flask_session", exist_ok=True)

    print()
    print("=" * 60)
    print("  Setup complete!")
    print("=" * 60)
    print()
    print("  To launch StemTube Desktop:")
    print()
    if platform.system() == "Windows":
        print("    venv\\Scripts\\activate")
        print("    python launcher.py")
    else:
        print("    source venv/bin/activate")
        print("    python launcher.py")
    print()
    print("  Or run without native window (opens in browser):")
    print("    python launcher.py --no-window")
    print()


if __name__ == '__main__':
    main()
