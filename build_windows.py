#!/usr/bin/env python3
"""
StemTube Desktop — Windows Build Script
=========================================
Creates a distributable package using PyInstaller.

Usage:
    python build_windows.py              # Build with PyInstaller
    python build_windows.py --onedir     # One directory mode (recommended for large apps)
    python build_windows.py --portable   # Create a portable zip (no installer)

Prerequisites:
    pip install pyinstaller

Output:
    dist/StemTube_Desktop/              # Application directory
    dist/StemTube_Desktop.zip           # Portable archive (if --portable)

Note: Due to the large size of PyTorch and ML models, the recommended
distribution method is the Inno Setup installer (see installer.iss)
which packages the venv directly rather than using PyInstaller bundling.
"""

import os
import sys
import shutil
import subprocess
import argparse


def create_pyinstaller_spec():
    """Generate a PyInstaller .spec file for StemTube Desktop."""
    spec_content = r'''# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect data files from packages that need them
datas = [
    ('templates', 'templates'),
    ('static', 'static'),
    ('core/config.json', 'core'),
    ('core/poc/samples', 'core/poc/samples'),   # metronome instrument one-shots (read at runtime)
    ('external/BTC-ISMIR19', 'external/BTC-ISMIR19'),
    ('patch_madmom.py', '.'),
]

# Collect hidden imports that PyInstaller misses
hidden_imports = [
    'engineio.async_drivers.threading',
    'flask_session',
    'flask_login',
    'flask_socketio',
    'eventlet',
    'eventlet.hubs.epolls',
    'eventlet.hubs.kqueue',
    'eventlet.hubs.selects',
    'dns',
    'dns.resolver',
    'librosa',
    'soundfile',
    'scipy',
    'scipy.signal',
    'sklearn',
    'sklearn.utils',
    'torch',
    'torchaudio',
    'demucs',
    'demucs.pretrained',
    'demucs.apply',
    'faster_whisper',
    'madmom',
    'msaf',
    'aiotube',
    'yt_dlp',
    'pychord',
    'syncedlyrics',
    'webview',
]

# Add all core and routes submodules
hidden_imports += collect_submodules('core')
hidden_imports += collect_submodules('routes')

a = Analysis(
    ['launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'notebook',
        'jupyterlab',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='StemTube Desktop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='static/icons/icon-512x512.png',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='StemTube_Desktop',
)
'''
    with open('stemtube_desktop.spec', 'w') as f:
        f.write(spec_content)
    print("[BUILD] Generated stemtube_desktop.spec")


def build_pyinstaller():
    """Run PyInstaller build."""
    create_pyinstaller_spec()

    print("[BUILD] Running PyInstaller...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "stemtube_desktop.spec", "--clean"],
        capture_output=False
    )

    if result.returncode == 0:
        print("[BUILD] PyInstaller build complete!")
        print("[BUILD] Output: dist/StemTube_Desktop/")
    else:
        print("[BUILD] PyInstaller build failed!")
        sys.exit(1)


def build_portable_package():
    """
    Create a portable distribution by copying the venv + source.
    This is the RECOMMENDED approach for large ML apps.
    """
    dist_dir = "dist/StemTube_Desktop_Portable"

    if os.path.exists(dist_dir):
        print(f"[BUILD] Cleaning previous build: {dist_dir}")
        shutil.rmtree(dist_dir)

    os.makedirs(dist_dir, exist_ok=True)

    # Files and directories to include
    include_items = [
        'app.py',
        'launcher.py',
        'extensions.py',
        'patch_madmom.py',
        'check_config.py',
        'core/',
        'routes/',
        'templates/',
        'static/',
        'external/',
        'utils/',
    ]

    exclude_patterns = [
        '__pycache__',
        '*.pyc',
        '.git',
        'logs/',
        'flask_session/',
        '*.db',
    ]

    print("[BUILD] Copying application files...")
    for item in include_items:
        src = item.rstrip('/')
        dst = os.path.join(dist_dir, src)

        if os.path.isdir(src):
            shutil.copytree(
                src, dst,
                ignore=shutil.ignore_patterns(*exclude_patterns)
            )
        elif os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    # Copy venv
    if os.path.exists('venv'):
        print("[BUILD] Copying virtual environment (this may take a while)...")
        shutil.copytree(
            'venv',
            os.path.join(dist_dir, 'venv'),
            ignore=shutil.ignore_patterns('__pycache__', '*.pyc')
        )

    # Create launcher batch file for Windows
    bat_content = '''@echo off
cd /d "%~dp0"
call venv\\Scripts\\activate.bat
python launcher.py %*
'''
    with open(os.path.join(dist_dir, 'StemTube Desktop.bat'), 'w') as f:
        f.write(bat_content)

    print(f"[BUILD] Portable package created: {dist_dir}/")
    print(f"[BUILD] Launch with: StemTube Desktop.bat")


def main():
    parser = argparse.ArgumentParser(description='StemTube Desktop Build')
    parser.add_argument('--portable', action='store_true',
                        help='Create portable package (venv + source copy)')
    parser.add_argument('--pyinstaller', action='store_true',
                        help='Build with PyInstaller (experimental for large ML apps)')
    args = parser.parse_args()

    if args.pyinstaller:
        build_pyinstaller()
    elif args.portable:
        build_portable_package()
    else:
        # Default: portable (most reliable for ML apps)
        print("[BUILD] Building portable package (recommended for ML apps)")
        print("[BUILD] Use --pyinstaller for PyInstaller build (experimental)")
        print()
        build_portable_package()


if __name__ == '__main__':
    main()
