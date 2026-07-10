#!/usr/bin/env python3
"""
StemTube Desktop — Nuitka Build Script
====================================
Compiles the StemTube Desktop Python backend into a native Windows executable
using Nuitka. The goal is to produce a standalone binary so that casual users
cannot simply read or copy .py source files.

Usage:
    python nuitka_build.py                        # Full build (GPU + CUDA)
    python nuitka_build.py --cpu-only             # CPU-only build (much smaller)
    python nuitka_build.py --with-icon icon.ico   # Custom application icon
    python nuitka_build.py --jobs 8               # Parallel compilation jobs

Prerequisites:
    pip install nuitka ordered-set zstandard

Output:
    dist/StemTube_Pro/StemTube Desktop.exe
    dist/StemTube_Pro/StemTube Desktop.bat

Note:
    Nuitka compiles Python to C and then to native machine code. This produces
    a real executable — not a frozen bytecode bundle like PyInstaller. The
    trade-off is longer build times (expect 30-90+ minutes for this project).

Python 3.12+
"""

import os
import sys
import time
import shutil
import platform
import argparse
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent
DIST_DIR = PROJECT_DIR / "dist" / "StemTube_Pro"
ENTRY_POINT = "app.py"  # Flask server only — Tauri provides the GUI window

# Packages that Nuitka must compile / follow into.
# PyTorch and its ecosystem rely heavily on dynamic imports, lazy loading,
# and dlopen() calls that Nuitka's static analysis cannot discover on its own.
INCLUDE_PACKAGES = [
    # ── Application modules ──────────────────────────────────────────
    "core",                          # All backend modules (config, extractors, detectors …)
    "routes",                        # Flask blueprints

    # ── Flask ecosystem ──────────────────────────────────────────────
    "flask",                         # Core framework
    "flask_socketio",                # WebSocket support
    "flask_login",                   # Session / auth
    "flask_session",                 # Server-side session storage
    "jinja2",                        # Template engine (Flask dependency)
    "werkzeug",                      # WSGI toolkit (Flask dependency)

    # ── Async / WebSocket drivers ────────────────────────────────────
    "eventlet",                      # Async driver for Flask-SocketIO
    "eventlet.hubs",                 # Hub implementations (epolls, kqueue, selects)
    "dns",                           # eventlet dependency (dnspython)
    "engineio",                      # python-engineio (SocketIO transport layer)
    "socketio",                      # python-socketio

    # ── AI / ML core ─────────────────────────────────────────────────
    "torch",                         # PyTorch — massive, many dynamic sub-imports
    "torchaudio",                    # Audio processing on top of PyTorch
    "demucs",                        # Stem separation models (Meta / Facebook Research)
    "faster_whisper",                # Speech-to-text (CTranslate2-based Whisper)
    "ctranslate2",                   # CTranslate2 runtime (faster-whisper backend)

    # ── Audio / music analysis ───────────────────────────────────────
    "librosa",                       # Audio feature extraction
    "soundfile",                     # Audio I/O (libsndfile wrapper)
    "madmom",                        # Beat/chord/tempo detection
    "msaf",                          # Music structure analysis
    "scipy",                         # Signal processing (used by librosa, madmom)
    "sklearn",                       # scikit-learn (used by msaf, madmom)
    "numpy",                         # Numerical computing (used everywhere)

    # ── Downloaders / metadata ───────────────────────────────────────
    "pychord",                       # Chord name parsing
    "syncedlyrics",                  # Synced lyrics fetcher

    # ── Desktop GUI ──────────────────────────────────────────────────
    # "webview" is handled by Nuitka's built-in pywebview plugin — do not include here
]

# Individual modules that must be explicitly included because they are loaded
# dynamically (e.g. via importlib, __import__, or entry-point plugins).
INCLUDE_MODULES = [
    # engineio async driver — loaded at runtime based on server config
    "engineio.async_drivers.eventlet",
    "engineio.async_drivers.threading",

    # eventlet hub back-ends — selected at runtime by OS detection
    "eventlet.hubs.epolls",
    "eventlet.hubs.kqueue",
    "eventlet.hubs.selects",
    "eventlet.hubs.poll",

    # Flask-SocketIO picks its async mode dynamically
    "flask_socketio",

    # Demucs model loading — pretrained model registry, apply logic
    "demucs.pretrained",
    "demucs.apply",
    "demucs.hdemucs",
    "demucs.htdemucs",

    # PyTorch backends loaded dynamically
    "torch.backends.cudnn",
    "torch.backends.mkl",
    "torch.backends.mkldnn",
    "torch.nn.functional",

    # SoundFile backends
    "soundfile",

    # SQLite (stdlib but sometimes missed in standalone)
    "sqlite3",

    # SSL (required for HTTPS requests to YouTube, lyrics APIs, etc.)
    "ssl",
    "_ssl",

    # Various codec / format support
    "encodings",
    "codecs",

    # bcrypt — only needed if password hashing is used (not in desktop single-user mode)
    # "bcrypt",
]

# GPU-specific packages — excluded when --cpu-only is set.
# Removing these can shrink the output by several GB.
CUDA_PACKAGES = [
    "torch.cuda",
    "torch.backends.cuda",
    "torch.backends.cudnn",
    "nvidia",                        # nvidia-* pip wheels (cudnn, cublas, etc.)
]

# Packages to exclude — saves space and avoids pulling in GUI toolkits,
# test frameworks, and notebook infrastructure that the app never uses.
EXCLUDE_PACKAGES = [
    "webview",                       # pywebview — Tauri provides the GUI
    "tkinter",                       # Tk GUI toolkit — not used
    "matplotlib",                    # Plotting library — not used at runtime
    "matplotlib.backends",
    "IPython",                       # Interactive shell
    "notebook",                      # Jupyter notebook
    "jupyterlab",                    # JupyterLab
    "nbconvert",                     # Notebook conversion
    "nbformat",                      # Notebook format
    "pytest",                        # Test runner
    "unittest",                      # Stdlib test runner (not needed in prod)
    "test",                          # CPython test suite
    "distutils",                     # Deprecated build tool
    "setuptools",                    # Build tool (not needed at runtime)
    "pip",                           # Package installer
    "ensurepip",                     # pip bootstrapper
    "pydoc",                         # Documentation generator
    "doctest",                       # Doc-test framework
    "lib2to3",                       # Python 2 → 3 conversion tool
    "xmlrpc",                        # XML-RPC (never used)
    "curses",                        # Terminal UI (not used on Windows)
    "idlelib",                       # IDLE editor
    "turtledemo",                    # Turtle graphics demos
    "tkinter.test",                  # Tk tests
    "numba",                         # JIT compiler — not used, heavy
    "numpy.random.tests",            # numpy test suite — not needed
    "scipy.tests",                   # scipy test suite
]

# Data files and directories that must be copied into the output directory.
# Nuitka compiles .py files but does NOT automatically bundle non-Python assets
# like HTML templates, CSS/JS, config files, or ML model weights.
DATA_INCLUDES = [
    # (source_relative_path, destination_relative_path)
    ("templates",                "templates"),
    ("static",                   "static"),
    ("core/config.json",         "core/config.json"),
    ("core/poc/samples",         "core/poc/samples"),   # metronome instrument one-shots
    ("external/BTC-ISMIR19",     "external/BTC-ISMIR19"),
    ("patch_madmom.py",          "patch_madmom.py"),
]


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

def check_nuitka_installed() -> bool:
    """Verify that Nuitka is importable and print its version."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "nuitka", "--version"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            version_line = result.stdout.strip().splitlines()[0]
            print(f"[BUILD] Nuitka found: {version_line}")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    print("[BUILD] ERROR: Nuitka is not installed or not working.")
    print()
    print("  Install it with:")
    print("    pip install nuitka ordered-set zstandard")
    print()
    print("  'ordered-set' speeds up compilation significantly.")
    print("  'zstandard' enables compressed standalone distributions.")
    print()
    print("  You also need a C compiler:")
    print("    - Windows: Install Visual Studio 2022 Build Tools (MSVC)")
    print("      https://visualstudio.microsoft.com/visual-cpp-build-tools/")
    print("    - Linux: sudo apt install gcc g++ (or equivalent)")
    print()
    return False


def check_platform() -> None:
    """Warn if not building on Windows (the target platform)."""
    if platform.system() != "Windows":
        print(f"[BUILD] WARNING: You are building on {platform.system()}.")
        print("  This script is designed for Windows builds.")
        print("  The resulting binary will be for the current platform,")
        print("  not Windows. Cross-compilation is not supported by Nuitka.")
        print("  For a Windows .exe, run this script on a Windows machine.")
        print()


def check_c_compiler() -> bool:
    """Check for a usable C compiler (MSVC on Windows, gcc/g++ on Linux)."""
    if platform.system() == "Windows":
        # Nuitka auto-detects MSVC; just warn if it might be missing
        vs_paths = [
            r"C:\Program Files\Microsoft Visual Studio",
            r"C:\Program Files (x86)\Microsoft Visual Studio",
        ]
        found = any(os.path.isdir(p) for p in vs_paths)
        if not found:
            print("[BUILD] WARNING: Visual Studio Build Tools not found in default locations.")
            print("  Nuitka requires MSVC to compile on Windows.")
            print("  Download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/")
            print("  (Nuitka will attempt to auto-detect; this warning may be a false positive.)")
            print()
        return True  # Let Nuitka handle the actual detection
    else:
        # Linux/macOS — check for gcc
        for compiler in ("gcc", "cc", "g++"):
            if shutil.which(compiler):
                return True
        print("[BUILD] ERROR: No C compiler found. Install gcc/g++.")
        return False


# ---------------------------------------------------------------------------
# Build command assembly
# ---------------------------------------------------------------------------

def build_nuitka_command(args: argparse.Namespace) -> list[str]:
    """
    Assemble the full Nuitka command-line invocation.

    Each flag is commented to explain why it is needed.
    """
    cmd: list[str] = [
        sys.executable, "-m", "nuitka",

        # ── Mode: standalone ─────────────────────────────────────────
        # Bundles the Python interpreter and ALL dependencies into a
        # self-contained directory. Users do not need Python installed.
        "--standalone",

        # ── Output directory ─────────────────────────────────────────
        # Place the compiled output under dist/StemTube_Desktop/
        f"--output-dir={PROJECT_DIR / 'dist'}",

        # ── Output filename ──────────────────────────────────────────
        # Name the backend executable for Tauri sidecar
        "--output-filename=stemtube-backend.exe",

        # ── Console mode ─────────────────────────────────────────────
        # Attach to parent console so Tauri can capture stdout/stderr.
        # The Tauri shell provides the GUI window, not this process.
        "--windows-console-mode=attach",

        # ── Enable Nuitka plugins ────────────────────────────────────
        # 'anti-bloat': Reduces output size by removing known bloat
        #   (e.g. test code inside numpy, scipy, etc.)
        # 'eventlet': Handles eventlet's monkey-patching and dynamic imports
        "--enable-plugin=anti-bloat",
        "--enable-plugin=eventlet",

        # ── Compilation parallelism ──────────────────────────────────
        # Use multiple CPU cores for C compilation. Drastically reduces
        # build time on multi-core machines.
        f"--jobs={args.jobs}",

        # ── Follow imports ───────────────────────────────────────────
        # By default Nuitka only compiles the entry point. We need it
        # to recursively follow and compile all imports.
        "--follow-imports",

        # ── Assume yes for download prompts ──────────────────────────
        # Nuitka may need to download helper tools (e.g. dependency
        # walker on Windows). Auto-accept to allow unattended builds.
        "--assume-yes-for-download",
    ]

    # ── Include packages ─────────────────────────────────────────────
    # Force Nuitka to compile and include these packages even if static
    # analysis does not detect them as used. This is critical for PyTorch
    # and other ML libraries that use heavy dynamic importing.
    for pkg in INCLUDE_PACKAGES:
        cmd.append(f"--include-package={pkg}")

    # ── Include individual modules ───────────────────────────────────
    # Same as above but for specific modules (not entire packages).
    # Filter out modules that conflict with CUDA exclusions in cpu-only mode.
    cuda_excluded = set(CUDA_PACKAGES) if args.cpu_only else set()
    for mod in INCLUDE_MODULES:
        if any(mod == excl or mod.startswith(excl + ".") for excl in cuda_excluded):
            continue
        cmd.append(f"--include-module={mod}")

    # ── Exclude packages ─────────────────────────────────────────────
    # Remove packages that are never used at runtime. This saves
    # significant space and avoids compilation errors from packages
    # that have C extensions we do not need.
    for pkg in EXCLUDE_PACKAGES:
        cmd.append(f"--nofollow-import-to={pkg}")

    # ── CPU-only mode ────────────────────────────────────────────────
    # When --cpu-only is set, exclude all CUDA packages. This can shrink
    # the output by 2-4 GB since PyTorch CUDA libraries are enormous.
    if args.cpu_only:
        for pkg in CUDA_PACKAGES:
            cmd.append(f"--nofollow-import-to={pkg}")
        print("[BUILD] CPU-only mode: CUDA packages will be excluded.")

    # ── Application icon ─────────────────────────────────────────────
    # Set a custom icon for the Windows executable. Must be a .ico file.
    # Falls back to the project's default icon if available.
    if args.with_icon:
        icon_path = Path(args.with_icon).resolve()
        if icon_path.exists():
            cmd.append(f"--windows-icon-from-ico={icon_path}")
            print(f"[BUILD] Using icon: {icon_path}")
        else:
            print(f"[BUILD] WARNING: Icon file not found: {icon_path}")
            print("  Continuing without custom icon.")
    else:
        # Try default project icon locations
        for candidate in [
            PROJECT_DIR / "static" / "icons" / "icon-512.png",
            PROJECT_DIR / "static" / "icons" / "icon-192.png",
        ]:
            if candidate.exists():
                cmd.append(f"--windows-icon-from-ico={candidate}")
                print(f"[BUILD] Using default icon: {candidate}")
                break

    # ── Windows metadata ─────────────────────────────────────────────
    # Embed version info and company name into the Windows executable.
    cmd.extend([
        "--windows-company-name=StemTube",
        "--windows-product-name=StemTube Desktop",
        "--windows-product-version=1.0.0.0",
        "--windows-file-description=StemTube Desktop Backend — Music Analysis & Stem Extraction",
    ])

    # ── Data file includes via Nuitka ────────────────────────────────
    # Nuitka can include data files/directories directly into the dist.
    # We use --include-data-dir for directories and --include-data-files
    # for individual files. This is the primary mechanism; we also run
    # a post-build copy step as a safety net (see copy_data_files).
    cmd.append(f"--include-data-dir={PROJECT_DIR / 'templates'}=templates")
    cmd.append(f"--include-data-dir={PROJECT_DIR / 'static'}=static")
    cmd.append(f"--include-data-dir={PROJECT_DIR / 'external' / 'BTC-ISMIR19'}=external/BTC-ISMIR19")
    cmd.append(f"--include-data-dir={PROJECT_DIR / 'core' / 'poc' / 'samples'}=core/poc/samples")
    cmd.append(f"--include-data-files={PROJECT_DIR / 'core' / 'config.json'}=core/config.json")
    cmd.append(f"--include-data-files={PROJECT_DIR / 'patch_madmom.py'}=patch_madmom.py")

    # ── Include madmom model files (.pkl) ───────────────────────────
    # madmom uses MODEL_PATH = os.path.dirname(__file__) in models/__init__.py
    # to locate .pkl files. Without these, beat/chord detection fails at runtime
    # with "No such file or directory: .../madmom/models/chords/2016/chords_cnnfeat.pkl"
    try:
        import site
        site_packages = site.getsitepackages()[0]
        madmom_models = Path(site_packages) / "madmom" / "models"
        if madmom_models.is_dir():
            cmd.append(f"--include-data-dir={madmom_models}=madmom/models")
            print(f"[BUILD] Including madmom models from: {madmom_models}")
        else:
            print(f"[BUILD] WARNING: madmom models not found at {madmom_models}")
    except Exception as e:
        print(f"[BUILD] WARNING: Could not locate madmom models: {e}")

    # ── Include ffmpeg directory if it exists ────────────────────────
    # The core/ffmpeg/ directory may contain a bundled ffmpeg binary.
    ffmpeg_dir = PROJECT_DIR / "core" / "ffmpeg"
    if ffmpeg_dir.is_dir() and any(ffmpeg_dir.iterdir()):
        cmd.append(f"--include-data-dir={ffmpeg_dir}=core/ffmpeg")
        print(f"[BUILD] Including bundled ffmpeg from: {ffmpeg_dir}")

    # ── Entry point ──────────────────────────────────────────────────
    cmd.append(str(PROJECT_DIR / ENTRY_POINT))

    return cmd


# ---------------------------------------------------------------------------
# Post-build steps
# ---------------------------------------------------------------------------

def get_output_dir() -> Path:
    """
    Determine where Nuitka placed the compiled output.

    Nuitka names the output directory based on the entry-point filename:
      launcher.py  →  launcher.dist/
    We rename it to our desired dist/StemTube_Desktop/ layout.
    """
    # Nuitka puts the standalone output in <output-dir>/<script>.dist/
    nuitka_dist = PROJECT_DIR / "dist" / "app.dist"
    return nuitka_dist


def rename_output_dir() -> Path:
    """Rename Nuitka's default output directory to StemTube_Desktop."""
    nuitka_dist = get_output_dir()

    if not nuitka_dist.exists():
        # Nuitka may have used a different name; look for it
        dist_parent = PROJECT_DIR / "dist"
        candidates = list(dist_parent.glob("*.dist"))
        if candidates:
            nuitka_dist = candidates[0]
        else:
            print(f"[BUILD] ERROR: Could not find Nuitka output directory in {dist_parent}")
            print("  Expected: launcher.dist/")
            sys.exit(1)

    if DIST_DIR.exists() and DIST_DIR != nuitka_dist:
        print(f"[BUILD] Removing previous output: {DIST_DIR}")
        shutil.rmtree(DIST_DIR)

    if nuitka_dist != DIST_DIR:
        print(f"[BUILD] Renaming {nuitka_dist.name} → {DIST_DIR.name}")
        nuitka_dist.rename(DIST_DIR)

    return DIST_DIR


def copy_data_files() -> None:
    """
    Safety-net copy of data files into the output directory.

    Nuitka's --include-data-dir/--include-data-files should handle this,
    but ML projects are notorious for missing files at runtime. This
    function ensures all critical assets are present.
    """
    print("[BUILD] Verifying data files in output directory...")

    for src_rel, dst_rel in DATA_INCLUDES:
        src = PROJECT_DIR / src_rel
        dst = DIST_DIR / dst_rel

        if not src.exists():
            print(f"  SKIP (source not found): {src_rel}")
            continue

        if src.is_dir():
            if dst.exists():
                # Check if directory has content
                if any(dst.iterdir()):
                    print(f"  OK (already present): {dst_rel}/")
                    continue
                else:
                    shutil.rmtree(dst)

            print(f"  COPY: {src_rel}/ → {dst_rel}/")
            shutil.copytree(
                src, dst,
                ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc", ".git", ".gitignore"
                )
            )
        else:
            if dst.exists():
                print(f"  OK (already present): {dst_rel}")
                continue

            dst.parent.mkdir(parents=True, exist_ok=True)
            print(f"  COPY: {src_rel} → {dst_rel}")
            shutil.copy2(src, dst)


def create_launcher_bat() -> None:
    """
    Create a .bat launcher in the output directory.

    This provides a familiar double-click entry point for Windows users
    and allows passing command-line arguments to the compiled executable.
    """
    bat_path = DIST_DIR / "StemTube Desktop.bat"
    bat_content = r"""@echo off
REM ============================================================
REM  StemTube Desktop Launcher
REM  Double-click this file to start StemTube Desktop.
REM ============================================================

cd /d "%~dp0"

REM Launch the compiled executable.
REM %* passes through any command-line arguments (e.g. --no-gpu).
start "" "StemTube Desktop.exe" %*
"""
    bat_path.write_text(bat_content, encoding="utf-8")
    print(f"[BUILD] Created launcher: {bat_path}")


def create_cpu_mode_bat() -> None:
    """
    Create a separate .bat file that forces CPU mode.

    Useful for users whose GPU drivers cause issues — they can use this
    shortcut instead of editing command-line flags.
    """
    bat_path = DIST_DIR / "StemTube Desktop (CPU Mode).bat"
    bat_content = r"""@echo off
REM ============================================================
REM  StemTube Desktop — CPU Mode
REM  Starts the app without GPU acceleration.
REM  Use this if you experience CUDA errors or crashes.
REM ============================================================

cd /d "%~dp0"
start "" "StemTube Desktop.exe" --no-gpu
"""
    bat_path.write_text(bat_content, encoding="utf-8")
    print(f"[BUILD] Created CPU-mode launcher: {bat_path}")


def print_build_summary(elapsed_seconds: float) -> None:
    """Print a summary of the build output with size estimates."""
    print()
    print("=" * 65)
    print("  BUILD COMPLETE")
    print("=" * 65)
    print()

    # Elapsed time
    minutes = int(elapsed_seconds // 60)
    seconds = int(elapsed_seconds % 60)
    print(f"  Build time:      {minutes}m {seconds}s")

    # Output size
    if DIST_DIR.exists():
        total_size = sum(
            f.stat().st_size
            for f in DIST_DIR.rglob("*")
            if f.is_file()
        )
        size_gb = total_size / (1024 ** 3)
        size_mb = total_size / (1024 ** 2)

        if size_gb >= 1.0:
            print(f"  Output size:     {size_gb:.2f} GB")
        else:
            print(f"  Output size:     {size_mb:.0f} MB")

        # Count files
        file_count = sum(1 for _ in DIST_DIR.rglob("*") if _.is_file())
        print(f"  Files:           {file_count:,}")
    else:
        print("  Output size:     (directory not found)")

    print(f"  Output path:     {DIST_DIR}")
    print()
    print("  To run the application:")
    print(f'    cd "{DIST_DIR}"')
    print('    "StemTube Desktop.exe"')
    print()
    print("  Or double-click 'StemTube Desktop.bat' in the output folder.")
    print()

    # Size expectations
    print("  Expected sizes (approximate):")
    print("    GPU build (with CUDA):  3 – 6 GB")
    print("    CPU-only build:         1 – 2 GB")
    print()


def print_build_estimate(cpu_only: bool) -> None:
    """Print estimated build time and output size before starting."""
    print()
    print("-" * 65)
    print("  BUILD ESTIMATES")
    print("-" * 65)
    if cpu_only:
        print("  Mode:            CPU-only (no CUDA)")
        print("  Expected time:   30 – 60 minutes")
        print("  Expected size:   1 – 2 GB")
    else:
        print("  Mode:            Full (GPU + CUDA)")
        print("  Expected time:   45 – 90 minutes")
        print("  Expected size:   3 – 6 GB")
    print()
    print("  Nuitka compiles Python to C, then to native machine code.")
    print("  This is significantly slower than PyInstaller but produces")
    print("  a true compiled binary (not frozen bytecode).")
    print("-" * 65)
    print()


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def clean_build_artifacts() -> None:
    """Remove intermediate Nuitka build artifacts to free disk space."""
    build_dir = PROJECT_DIR / "dist" / "launcher.build"
    if build_dir.exists():
        print(f"[BUILD] Cleaning intermediate build files: {build_dir}")
        shutil.rmtree(build_dir)

    # Nuitka may also leave a .onefile-build directory
    onefile_dir = PROJECT_DIR / "dist" / "launcher.onefile_build"
    if onefile_dir.exists():
        shutil.rmtree(onefile_dir)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build StemTube Desktop with Nuitka (Python → native executable)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python nuitka_build.py                         Full GPU build
  python nuitka_build.py --cpu-only              Smaller CPU-only build
  python nuitka_build.py --with-icon app.ico     Custom window icon
  python nuitka_build.py --jobs 12 --cpu-only    Fast CPU-only build
  python nuitka_build.py --clean                 Remove build artifacts only
        """,
    )

    parser.add_argument(
        "--cpu-only",
        action="store_true",
        help="Exclude CUDA/GPU packages for a much smaller output (~1-2 GB vs ~3-6 GB)",
    )
    parser.add_argument(
        "--with-icon",
        type=str,
        metavar="ICON_PATH",
        help="Path to a .ico file to use as the application icon",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=os.cpu_count() or 4,
        help=f"Number of parallel C compilation jobs (default: {os.cpu_count() or 4})",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove intermediate build artifacts and exit",
    )
    parser.add_argument(
        "--no-copy-data",
        action="store_true",
        help="Skip the post-build data file verification/copy step",
    )

    args = parser.parse_args()

    # ── Clean mode ───────────────────────────────────────────────────
    if args.clean:
        clean_build_artifacts()
        print("[BUILD] Cleanup complete.")
        return

    # ── Header ───────────────────────────────────────────────────────
    print()
    print("=" * 65)
    print("  StemTube Desktop — Nuitka Build")
    print("=" * 65)
    print(f"  Platform:        {platform.system()} {platform.machine()}")
    print(f"  Python:          {sys.version.split()[0]}")
    print(f"  Project dir:     {PROJECT_DIR}")
    print(f"  Entry point:     {ENTRY_POINT}")
    print(f"  Output dir:      {DIST_DIR}")
    print(f"  CPU-only:        {'Yes' if args.cpu_only else 'No'}")
    print(f"  Parallel jobs:   {args.jobs}")

    # ── Preflight ────────────────────────────────────────────────────
    check_platform()

    if not check_nuitka_installed():
        sys.exit(1)

    if not check_c_compiler():
        sys.exit(1)

    # Verify entry point exists
    entry = PROJECT_DIR / ENTRY_POINT
    if not entry.exists():
        print(f"[BUILD] ERROR: Entry point not found: {entry}")
        sys.exit(1)

    # ── Build estimates ──────────────────────────────────────────────
    print_build_estimate(args.cpu_only)

    # ── Assemble and run the Nuitka command ──────────────────────────
    cmd = build_nuitka_command(args)

    # Print the full command for debugging / reproducibility
    print("[BUILD] Nuitka command:")
    # Format nicely: one flag per line for readability
    print(f"  {cmd[0]} {cmd[1]} {cmd[2]} \\")
    for flag in cmd[3:-1]:
        print(f"    {flag} \\")
    print(f"    {cmd[-1]}")
    print()

    print("[BUILD] Starting Nuitka compilation...")
    print("  (This will take a long time. Go grab a coffee.)")
    print()

    start_time = time.time()

    result = subprocess.run(
        cmd,
        cwd=str(PROJECT_DIR),
        # Do not capture output — let Nuitka print progress in real time
    )

    elapsed = time.time() - start_time

    if result.returncode != 0:
        print()
        print(f"[BUILD] ERROR: Nuitka exited with code {result.returncode}")
        print("  Check the output above for error details.")
        print()
        print("  Common issues:")
        print("    - Missing C compiler (install Visual Studio Build Tools)")
        print("    - Insufficient disk space (need 10+ GB free)")
        print("    - Insufficient RAM (need 8+ GB free)")
        print("    - Package import errors (check --include-package flags)")
        sys.exit(1)

    # ── Post-build: rename output directory ──────────────────────────
    print()
    rename_output_dir()

    # ── Post-build: verify / copy data files ─────────────────────────
    if not args.no_copy_data:
        copy_data_files()

    # ── Post-build: create launcher scripts ──────────────────────────
    create_launcher_bat()
    create_cpu_mode_bat()

    # ── Post-build: clean intermediate files ─────────────────────────
    clean_build_artifacts()

    # ── Summary ──────────────────────────────────────────────────────
    print_build_summary(elapsed)


if __name__ == "__main__":
    main()
