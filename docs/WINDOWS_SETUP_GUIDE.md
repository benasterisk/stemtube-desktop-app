# StemTube Desktop — Windows 11 Development Guide

Complete guide for setting up the development environment on Windows 11.

## Prerequisites

### 1. Python 3.12+
- Download from [python.org](https://www.python.org/downloads/) (NOT Windows Store)
- During installation, check **"Add Python to PATH"**
- Verify: `python --version` → should show 3.12+

### 2. Node.js 20+
- Download LTS from [nodejs.org](https://nodejs.org/)
- Verify: `node --version` → should show 20+

### 3. Git
- Download from [git-scm.com](https://git-scm.com/download/win)
- Verify: `git --version`

### 4. NVIDIA GPU (optional)
- Install latest drivers from [nvidia.com](https://www.nvidia.com/Download/index.aspx)
- Verify: `nvidia-smi` → should show GPU name and CUDA version
- GPU gives 4-8x speedup on stem extraction and lyrics transcription

### 5. Inno Setup 6+ (for building installer)
- Download from [jrsoftware.org](https://jrsoftware.org/isinfo.php)
- Only needed if you want to build the Windows installer

## Quick Setup

```cmd
:: Navigate to the project directory
cd C:\path\to\Stemtube_Desktop

:: Run automated setup (auto-detects GPU)
python setup_desktop.py

:: Activate virtual environment
venv\Scripts\activate

:: Launch with native window
python launcher.py

:: OR launch in browser
python launcher.py --no-window
```

## Step-by-Step Manual Setup

### Step 1: Create Virtual Environment
```cmd
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
```

### Step 2: Install PyTorch
```cmd
:: CPU only (smaller, ~250 MB)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

:: OR with GPU support (larger, ~1.5 GB) — check your CUDA version with nvidia-smi
:: CUDA 12.4+
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install nvidia-cudnn-cu12

:: CUDA 11.8+
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
pip install nvidia-cudnn-cu11
```

### Step 3: Install Dependencies
```cmd
pip install flask flask-login flask-session flask-socketio eventlet
pip install requests python-dotenv Pillow
pip install librosa soundfile scipy scikit-learn
pip install yt-dlp[default] aiotube beautifulsoup4
pip install faster-whisper msaf syncedlyrics pychord
pip install pywebview werkzeug

:: Install demucs (needs torch first)
pip install demucs

:: Install madmom (needs specific numpy)
pip install Cython
pip install numpy==1.26.4
pip install madmom

:: Patch madmom for numpy compatibility
python patch_madmom.py
```

### Step 4: Setup FFmpeg
- Download from [ffmpeg.org/download.html](https://ffmpeg.org/download.html)
- Extract and place `ffmpeg.exe` and `ffprobe.exe` in `core/ffmpeg/bin/`
- Or install via Chocolatey: `choco install ffmpeg`

### Step 5: Download Guitar Chord Library
```cmd
git clone --depth 1 https://github.com/szaza/guitar-chords-db-json.git static/js/datas/guitar-chords-db-json
```

### Step 6: Launch
```cmd
python launcher.py
```

## Development Workflow

### Running the App
```cmd
:: Native window (recommended for testing)
python launcher.py

:: Browser mode (useful for DevTools)
python launcher.py --no-window

:: Debug mode (verbose logging + DevTools in native window)
python launcher.py --debug

:: CPU-only mode (skip GPU even if available)
python launcher.py --no-gpu

:: Direct Flask server (no pywebview)
python app.py
:: Then open http://127.0.0.1:5011 in your browser
```

### Project Structure

```
Stemtube_Desktop/
│
├── launcher.py              ← ENTRY POINT: pywebview + Flask
├── app.py                   ← Flask app (auto-login, localhost)
├── extensions.py            ← Shared singletons, UserSessionManager
│
├── core/                    ← Backend modules
│   ├── config.py            ← Settings (PORT, paths, defaults)
│   ├── config.json          ← User settings (via UI)
│   ├── auth_db.py           ← Single-user auth (auto-login)
│   ├── download_manager.py  ← Download queue + analysis
│   ├── stems_extractor.py   ← Demucs integration
│   ├── chord_detector.py    ← BTC chord detection
│   ├── madmom_chord_detector.py ← madmom fallback
│   ├── hybrid_chord_detector.py ← Multi-backend fallback
│   ├── lyrics_detector.py   ← faster-whisper
│   ├── lyrics_aligner.py    ← LrcLib + alignment
│   ├── structure_detector.py ← MSAF
│   ├── db/                  ← SQLite layer
│   │   ├── connection.py    ← DB path/connection
│   │   ├── schema.py        ← Table creation
│   │   ├── downloads.py     ← CRUD
│   │   ├── extractions.py   ← Extraction tracking
│   │   └── recordings.py    ← Recording takes
│   └── downloads/           ← Processed files (auto-created)
│
├── routes/                  ← Flask blueprints
│   ├── __init__.py          ← Blueprint registration
│   ├── auth.py              ← Auto-login redirect
│   ├── pages.py             ← index, mixer pages
│   ├── admin.py             ← Settings API
│   ├── admin_api.py         ← Admin REST API
│   ├── downloads.py         ← Download CRUD
│   ├── extractions.py       ← Extraction CRUD
│   ├── media.py             ← Lyrics, chords, beats
│   ├── library.py           ← User library
│   ├── files.py             ← File upload/download
│   ├── config_routes.py     ← App settings
│   ├── logging_routes.py    ← Browser logs
│   └── recordings.py        ← Recording CRUD
│
├── templates/               ← HTML (Jinja2)
│   ├── index.html           ← Main desktop UI
│   ├── mixer.html           ← Mixer iframe
│   └── login.html           ← Fallback (auto-redirect)
│
├── static/js/               ← Frontend JavaScript
│   ├── app.js               ← Module loader
│   ├── app-core.js          ← Socket.IO, globals
│   ├── app-downloads.js     ← Search/download UI
│   ├── app-utils.js         ← Settings, toast
│   ├── app-admin.js         ← Admin controls
│   ├── app-extensions.js    ← Tab management
│   └── mixer/               ← 25 mixer modules
│
├── external/BTC-ISMIR19/    ← BTC chord model
│
├── setup_desktop.py         ← Automated Windows setup
├── build_windows.py         ← Build distributable
├── installer.iss            ← Inno Setup script
└── StemTube Desktop.bat     ← Double-click launcher
```

### Key Files to Know

| File | What it does |
|------|-------------|
| `launcher.py` | Opens native window, starts Flask in background thread |
| `app.py` | Flask app with auto-login, auto-generated secret key |
| `extensions.py` | UserSessionManager, WebSocket progress, download/extraction managers |
| `core/config.py` | All paths, defaults, settings management |
| `core/auth_db.py` | `ensure_desktop_user()` creates the single user on first run |
| `routes/pages.py` | Auto-login flow: checks auth → logs in desktop user → renders index |

### Database

SQLite at `stemtubes.db` (auto-created on first run):
- `users` — Single desktop user (auto-created)
- `global_downloads` — Audio files with analysis data
- `user_downloads` — User access records
- `recordings` — Multi-track recording takes

Inspect with: `python utils/database/debug_db.py`

### Configuration

Settings stored in `core/config.json` (editable via Settings tab in UI):
```json
{
    "use_gpu_for_extraction": true,
    "default_stem_model": "htdemucs",
    "lyrics_model_size": "medium",
    "enable_youtube_features": true,
    "chords_use_madmom": true,
    "chords_use_hybrid": true,
    "downloads_directory": "C:\\path\\to\\core\\downloads"
}
```

No `.env` file needed — secret key is auto-generated in `.secret_key`.

## Building the Installer

### 1. Build Portable Package
```cmd
python build_windows.py --portable
```
This creates `dist/StemTube_Desktop_Portable/` with:
- Full source code
- Python venv with all dependencies
- `StemTube Desktop.bat` launcher

### 2. Create Windows Installer
1. Install [Inno Setup 6+](https://jrsoftware.org/isinfo.php)
2. Open `installer.iss` in Inno Setup Compiler
3. Click Build → `dist/StemTube_Desktop_Setup.exe`

The installer:
- Copies all files to `C:\Program Files\StemTube Desktop\`
- Creates Start Menu and Desktop shortcuts
- Optionally pre-downloads AI models (~4 GB)
- Creates uninstaller
- Warns if Node.js is missing

### 3. Distribute
Share `dist/StemTube_Desktop_Setup.exe` — it's a self-contained installer.

## Troubleshooting

### madmom installation fails
```cmd
:: madmom requires numpy <2.0 and Cython
pip install numpy==1.26.4 Cython
pip install madmom
python patch_madmom.py
```

### pywebview window is blank
```cmd
:: Ensure Edge WebView2 Runtime is installed (built-in on Windows 11)
:: Or install from: https://developer.microsoft.com/en-us/microsoft-edge/webview2/
:: Alternative: use browser mode
python launcher.py --no-window
```

### GPU not detected after driver update
```cmd
:: Reinstall PyTorch with correct CUDA version
pip uninstall torch torchaudio
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
```

### "Module not found" errors
```cmd
:: Make sure venv is activated
venv\Scripts\activate
:: Reinstall dependencies
python setup_desktop.py
```

### YouTube downloads fail
```cmd
:: Update yt-dlp (the app does this on startup, but you can force it)
pip install -U --pre yt-dlp[default]
:: Ensure Node.js is installed (required for JS challenge solving)
node --version
```
