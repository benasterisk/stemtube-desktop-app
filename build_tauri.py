#!/usr/bin/env python3
"""
StemTube Desktop — Tauri Build Orchestrator
========================================
Orchestrates the full build pipeline:
  1. Nuitka compiles the Flask backend → dist/app.dist/
  2. Copies the Nuitka output to src-tauri/stemtube-backend/
  3. Runs `cargo tauri build` to produce the NSIS installer

Usage:
    python build_tauri.py                # Full build (Nuitka + Tauri)
    python build_tauri.py --cpu-only     # CPU-only (smaller, no CUDA)
    python build_tauri.py --skip-nuitka  # Skip Nuitka, just rebuild Tauri
    python build_tauri.py --prepare      # Only prepare resources (no Tauri build)
    python build_tauri.py --test         # Run post-build tests

Prerequisites:
    - Nuitka: pip install nuitka ordered-set zstandard
    - Visual Studio Build Tools 2022 (MSVC)
    - Rust + cargo: rustup install stable
    - Node.js 20+: npm install (in project root)
"""

import os
import sys
import time
import shutil
import argparse
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
NUITKA_DIST = PROJECT_DIR / "dist" / "app.dist"
TAURI_SIDECAR_DIR = PROJECT_DIR / "src-tauri" / "stemtube-backend"
TAURI_DIR = PROJECT_DIR / "src-tauri"


def get_python() -> str:
    """Find the best Python executable (venv first, then system)."""
    venv_python = PROJECT_DIR / "venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


# ---------------------------------------------------------------------------
# Step 1: Nuitka build
# ---------------------------------------------------------------------------

def run_nuitka(cpu_only: bool = True, jobs: int = 0) -> bool:
    """Run the Nuitka build script."""
    print("=" * 60)
    print("  STEP 1: Nuitka Compilation")
    print("=" * 60)

    python = get_python()
    cmd = [python, "nuitka_build.py"]
    if cpu_only:
        cmd.append("--cpu-only")
    if jobs > 0:
        cmd.extend(["--jobs", str(jobs)])

    print(f"  Command: {' '.join(cmd)}")
    print(f"  This will take 30-90 minutes...")
    print()

    result = subprocess.run(cmd, cwd=PROJECT_DIR)
    if result.returncode != 0:
        print("[ERROR] Nuitka build failed.")
        return False

    # Verify output exists
    if not NUITKA_DIST.exists():
        # Check alternate name (StemTube_Pro from rename step)
        alt = PROJECT_DIR / "dist" / "StemTube_Pro"
        if alt.exists():
            print(f"  Renaming {alt.name} → {NUITKA_DIST.name}")
            alt.rename(NUITKA_DIST)
        else:
            print(f"[ERROR] Nuitka output not found at {NUITKA_DIST}")
            return False

    exe = NUITKA_DIST / "stemtube-backend.exe"
    if not exe.exists():
        # Check alternate exe name
        for alt_name in ["StemTube Desktop.exe", "app.exe"]:
            alt_exe = NUITKA_DIST / alt_name
            if alt_exe.exists():
                print(f"  Renaming {alt_name} → stemtube-backend.exe")
                alt_exe.rename(exe)
                break

    if not exe.exists():
        print(f"[ERROR] Backend exe not found in {NUITKA_DIST}")
        print(f"  Files found: {[f.name for f in NUITKA_DIST.iterdir()][:20]}")
        return False

    size_mb = exe.stat().st_size / (1024 * 1024)
    total_files = sum(1 for _ in NUITKA_DIST.rglob("*") if _.is_file())
    print(f"  Nuitka build complete: {size_mb:.1f} MB exe, {total_files} files total")
    return True


# ---------------------------------------------------------------------------
# Step 2: Prepare Tauri resources
# ---------------------------------------------------------------------------

def prepare_resources() -> bool:
    """Copy Nuitka output to src-tauri/stemtube-backend/."""
    print()
    print("=" * 60)
    print("  STEP 2: Preparing Tauri Resources")
    print("=" * 60)

    if not NUITKA_DIST.exists():
        print(f"[ERROR] Nuitka output not found at {NUITKA_DIST}")
        print(f"  Run with --skip-nuitka only if Nuitka was already built.")
        return False

    # Clean previous resources
    if TAURI_SIDECAR_DIR.exists():
        print(f"  Cleaning previous: {TAURI_SIDECAR_DIR}")
        shutil.rmtree(TAURI_SIDECAR_DIR, ignore_errors=True)

    # Copy entire Nuitka dist to Tauri sidecar location
    print(f"  Copying {NUITKA_DIST} → {TAURI_SIDECAR_DIR}")
    start = time.time()
    shutil.copytree(NUITKA_DIST, TAURI_SIDECAR_DIR)
    elapsed = time.time() - start

    total_files = sum(1 for _ in TAURI_SIDECAR_DIR.rglob("*") if _.is_file())
    total_size = sum(f.stat().st_size for f in TAURI_SIDECAR_DIR.rglob("*") if f.is_file())
    print(f"  Copied {total_files} files ({total_size / (1024**2):.0f} MB) in {elapsed:.1f}s")

    # Verify the sidecar exe exists
    exe = TAURI_SIDECAR_DIR / "stemtube-backend.exe"
    if not exe.exists():
        print(f"[ERROR] stemtube-backend.exe not found in {TAURI_SIDECAR_DIR}")
        return False

    print(f"  Sidecar ready: {exe}")
    return True


# ---------------------------------------------------------------------------
# Step 3: Tauri build
# ---------------------------------------------------------------------------

def run_tauri_build() -> bool:
    """Run cargo tauri build to produce the NSIS installer."""
    print()
    print("=" * 60)
    print("  STEP 3: Tauri Build (Rust + NSIS Installer)")
    print("=" * 60)

    # Verify Rust toolchain
    result = subprocess.run(["cargo", "--version"], capture_output=True, text=True)
    if result.returncode != 0:
        # Try with explicit PATH
        cargo_path = os.path.expanduser("~/.cargo/bin/cargo")
        if not os.path.exists(cargo_path):
            print("[ERROR] cargo not found. Install Rust: https://rustup.rs/")
            return False
        os.environ["PATH"] = os.path.expanduser("~/.cargo/bin") + os.pathsep + os.environ["PATH"]

    # Run tauri build
    cmd = ["npx", "tauri", "build"]
    print(f"  Command: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, cwd=PROJECT_DIR)
    if result.returncode != 0:
        print("[ERROR] Tauri build failed.")
        return False

    # Find the installer output
    bundle_dir = TAURI_DIR / "target" / "release" / "bundle" / "nsis"
    if bundle_dir.exists():
        installers = list(bundle_dir.glob("*.exe"))
        if installers:
            for inst in installers:
                size_mb = inst.stat().st_size / (1024 * 1024)
                print(f"  Installer: {inst} ({size_mb:.1f} MB)")
        else:
            print(f"  Bundle dir exists but no .exe found: {bundle_dir}")
    else:
        print(f"  Bundle dir not found: {bundle_dir}")
        print(f"  Check target/release/bundle/ for output.")

    return True


# ---------------------------------------------------------------------------
# Step 4: Post-build tests
# ---------------------------------------------------------------------------

def run_tests() -> bool:
    """Run basic post-build verification tests."""
    print()
    print("=" * 60)
    print("  STEP 4: Post-Build Tests")
    print("=" * 60)

    all_pass = True

    # Test 1: Sidecar exists and is executable
    exe = TAURI_SIDECAR_DIR / "stemtube-backend.exe"
    if exe.exists():
        print(f"  [PASS] Sidecar exe exists ({exe.stat().st_size / (1024**2):.1f} MB)")
    else:
        print(f"  [FAIL] Sidecar exe not found: {exe}")
        all_pass = False

    # Test 2: Required data files present
    for data_file in ["templates/index.html", "templates/mixer.html", "static/js/mixer/core.js",
                       "core/config.json"]:
        path = TAURI_SIDECAR_DIR / data_file
        if path.exists():
            print(f"  [PASS] Data file: {data_file}")
        else:
            print(f"  [FAIL] Missing data file: {data_file}")
            all_pass = False

    # Test 3: Tauri binary exists
    tauri_exe = TAURI_DIR / "target" / "release" / "stemtube-desktop.exe"
    if tauri_exe.exists():
        print(f"  [PASS] Tauri exe ({tauri_exe.stat().st_size / (1024**2):.1f} MB)")
    else:
        # Dev build
        dev_exe = TAURI_DIR / "target" / "debug" / "stemtube-desktop.exe"
        if dev_exe.exists():
            print(f"  [PASS] Tauri dev exe ({dev_exe.stat().st_size / (1024**2):.1f} MB)")
        else:
            print(f"  [WARN] No Tauri exe found (build not run yet?)")

    # Test 4: NSIS installer exists
    bundle_dir = TAURI_DIR / "target" / "release" / "bundle" / "nsis"
    installers = list(bundle_dir.glob("*.exe")) if bundle_dir.exists() else []
    if installers:
        for inst in installers:
            print(f"  [PASS] Installer: {inst.name} ({inst.stat().st_size / (1024**2):.1f} MB)")
    else:
        print(f"  [WARN] No NSIS installer found (run full build first)")

    # Test 5: Tauri config valid
    conf = TAURI_DIR / "tauri.conf.json"
    try:
        import json
        with open(conf) as f:
            json.load(f)
        print(f"  [PASS] tauri.conf.json is valid JSON")
    except Exception as e:
        print(f"  [FAIL] tauri.conf.json error: {e}")
        all_pass = False

    print()
    if all_pass:
        print("  All tests passed!")
    else:
        print("  Some tests failed. Check the output above.")

    return all_pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="StemTube Desktop — Tauri Build Orchestrator")
    parser.add_argument("--cpu-only", action="store_true", default=True,
                       help="CPU-only Nuitka build (default: True)")
    parser.add_argument("--gpu", action="store_true",
                       help="Include CUDA/GPU support (larger build)")
    parser.add_argument("--skip-nuitka", action="store_true",
                       help="Skip Nuitka step, use existing dist/")
    parser.add_argument("--prepare", action="store_true",
                       help="Only prepare resources (no Tauri build)")
    parser.add_argument("--test", action="store_true",
                       help="Run post-build tests only")
    parser.add_argument("--jobs", type=int, default=0,
                       help="Parallel compilation jobs (0=auto)")
    args = parser.parse_args()

    if args.gpu:
        args.cpu_only = False

    start_time = time.time()

    if args.test:
        run_tests()
        return

    # Step 1: Nuitka
    if not args.skip_nuitka:
        if not run_nuitka(cpu_only=args.cpu_only, jobs=args.jobs):
            sys.exit(1)

    # Step 2: Prepare resources
    if not prepare_resources():
        sys.exit(1)

    if args.prepare:
        print()
        print(f"  Resources prepared. Run 'npm run tauri:build' to create the installer.")
        run_tests()
        return

    # Step 3: Tauri build
    if not run_tauri_build():
        sys.exit(1)

    # Step 4: Tests
    run_tests()

    elapsed = time.time() - start_time
    print()
    print(f"  Total build time: {elapsed / 60:.1f} minutes")


if __name__ == "__main__":
    main()
