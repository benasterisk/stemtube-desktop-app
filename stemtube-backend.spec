# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('templates', 'templates'), ('static', 'static'), ('core/config.json', 'core'), ('external/BTC-ISMIR19', 'external/BTC-ISMIR19'), ('patch_madmom.py', '.'), ('core/ffmpeg', 'core/ffmpeg')]

# Include madmom model files (.pkl) — required for beat/chord detection
import os, site as _site
_sp = _site.getsitepackages()[0]
_madmom_models = os.path.join(_sp, 'madmom', 'models')
if os.path.isdir(_madmom_models):
    datas.append((_madmom_models, 'madmom/models'))
binaries = []
hiddenimports = ['engineio.async_drivers.threading', 'flask_socketio', 'flask_login', 'flask_session', 'eventlet', 'eventlet.hubs.selects', 'dns', 'demucs.pretrained', 'demucs.apply', 'demucs.hdemucs', 'demucs.htdemucs', 'soundfile', 'sqlite3', 'ssl', 'pychord', 'syncedlyrics', 'numpy.core._multiarray_umath', 'charset_normalizer']
tmp_ret = collect_all('numpy')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('torch')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('torchaudio')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('demucs')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'IPython', 'notebook', 'pytest', 'webview'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='stemtube-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['src-tauri\\icons\\icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='stemtube-backend',
)
