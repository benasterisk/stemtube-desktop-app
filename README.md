# StemTube Desktop

Standalone Windows desktop application for AI-powered music analysis of your own audio files. Extracts stems, detects chords and transcribes lyrics — all locally on your machine.

## Features

- **File Upload** — Import local audio files (MP3, WAV, FLAC, M4A, AAC, OGG, WMA)
- **Stem Extraction** — AI-powered source separation using Demucs (vocals, drums, bass, other, piano, guitar)
- **Chord Detection** — Real-time chord display with BTC Transformer (170 chords) + madmom fallback
- **Lyrics Transcription** — Word-level timestamps via faster-whisper + LrcLib synced lyrics
- **Mixer** — Full-featured audio mixer with pitch/tempo control, karaoke display, waveform visualization
- **Multi-track Recording** — Record over stems with timeline positioning
- **GPU Acceleration** — Automatic NVIDIA CUDA detection (falls back to CPU)

## Requirements

- **Windows 10/11** (64-bit)
- **Python 3.12+** — [Download from python.org](https://www.python.org/downloads/) (NOT Windows Store; only for source installs — the packaged app ships its own)
- **~4 GB disk space** (CPU mode) or **~8 GB** (GPU + pre-downloaded models)
- **NVIDIA GPU** (optional) — For faster stem extraction and lyrics transcription

## Install (recommended)

Download and run **[StemTube Desktop_2.0.0_x64-setup.exe](https://github.com/benasterisk/stemtube-desktop-releases/releases/latest)** (1.4 MB).

On first launch the app detects your hardware and downloads the matching engine automatically — **CPU** (~520 MB) or **NVIDIA GPU** (~2.9 GB, CUDA accelerated) — then repairs its Python runtime if needed. First boot can take a few minutes; later launches are instant. Everything (Python, FFmpeg) is bundled or fetched automatically.

## Quick Start (from source)

### Option 1: Double-click launcher
1. Place the `Stemtube_Desktop` folder on your Windows machine
2. Double-click `StemTube Desktop.bat`
3. First run will automatically set up the virtual environment and install dependencies

### Option 2: Manual setup
```cmd
cd Stemtube_Desktop
python setup_desktop.py
venv\Scripts\activate
python launcher.py
```

### Option 3: Browser mode (no native window)
```cmd
venv\Scripts\activate
python launcher.py --no-window
```

### Option 4: Direct Flask server
```cmd
venv\Scripts\activate
python app.py
:: Open http://127.0.0.1:5011 in your browser
```

## Setup Options

```cmd
python setup_desktop.py                  # Auto-detect GPU, install everything
python setup_desktop.py --cpu-only       # Force CPU mode (smaller install, ~2.5 GB)
python setup_desktop.py --skip-models    # Skip AI model downloads (downloaded on first use)
```

## Launcher Options

```cmd
python launcher.py                 # Normal launch (native window)
python launcher.py --no-window     # Open in default browser instead
python launcher.py --debug         # Enable debug mode + browser DevTools
python launcher.py --no-gpu        # Force CPU mode for this session
python launcher.py --port 8080     # Use custom port
```

## Building a Distributable Package

### Portable package (recommended)
```cmd
python build_windows.py --portable
:: Output: dist/StemTube_Desktop_Portable/
```

### Windows installer (requires Inno Setup 6+)
```cmd
:: 1. Build portable package first
python build_windows.py --portable

:: 2. Open installer.iss in Inno Setup Compiler
:: 3. Click Build → the installer will be created at dist/StemTube_Desktop_Setup.exe
```

## Architecture

```
Stemtube_Desktop/
├── launcher.py              # Desktop entry point (pywebview + Flask)
├── app.py                   # Flask application (auto-login, localhost only)
├── setup_desktop.py         # Windows setup script
├── build_windows.py         # Build/packaging script
├── installer.iss            # Inno Setup installer script
├── StemTube Desktop.bat     # Windows double-click launcher
│
├── core/                    # Backend processing modules
│   ├── config.py            # Application configuration
│   ├── config.json          # User settings (managed via UI)
│   ├── auth_db.py           # Single-user auto-login authentication
│   ├── audio_analysis.py    # BPM + key detection (STFT + autocorrelation)
│   ├── stems_extractor.py   # Demucs stem separation
│   ├── chord_detector.py    # BTC Transformer chord detection
│   ├── madmom_chord_detector.py  # madmom CRF fallback
│   ├── hybrid_chord_detector.py  # Multi-backend fallback
│   ├── lyrics_detector.py   # faster-whisper transcription
│   ├── lyrics_aligner.py    # LrcLib + Whisper alignment
│   ├── db/                  # SQLite database layer
│   └── downloads/           # Processed audio files
│
├── routes/                  # Flask blueprints (API endpoints)
├── templates/               # HTML templates
├── static/                  # Frontend (JS, CSS, images)
│   ├── js/
│   │   ├── app.js           # Desktop entry point
│   │   ├── app-core.js      # Socket.IO, config
│   │   ├── app-downloads.js # Upload + extraction UI
│   │   └── mixer/           # 25 modular mixer components
│   └── css/
│
├── external/                # BTC chord model
└── venv/                    # Python virtual environment (created by setup)
```

## Key Differences from StemTube Web

| Feature | Web (v1.4) | Desktop |
|---------|-----------|---------|
| Users | Multi-user with auth | Single-user, auto-login |
| Global Library | Shared across users | Personal library only |
| Jam Sessions | Real-time collaborative | Removed |
| Mobile PWA | Separate mobile interface | Desktop only |
| Server | 0.0.0.0 + ngrok | 127.0.0.1 localhost only |
| Secret Key | Required in .env | Auto-generated |
| Admin Panel | User management | Settings only |

## Configuration

Settings are managed through the application UI (Settings tab). Configuration is stored in `core/config.json`.

Key settings:
- `use_gpu_for_extraction` — Enable/disable GPU acceleration
- `default_stem_model` — Demucs model (`htdemucs`, `htdemucs_6s`, `mdx_extra`)
- `lyrics_model_size` — Whisper model size (`tiny`, `base`, `small`, `medium`, `large-v3`)

## Troubleshooting

### "Python not found"
Install Python 3.12+ from [python.org](https://www.python.org/downloads/). Check "Add to PATH" during installation.

### "FFmpeg not found"
Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html) and place `ffmpeg.exe` in `core/ffmpeg/bin/`.

### GPU not detected
- Install latest NVIDIA drivers from [nvidia.com](https://www.nvidia.com/Download/index.aspx)
- Run `nvidia-smi` in a terminal to verify CUDA is working
- Re-run `python setup_desktop.py` to reinstall PyTorch with GPU support

### Stems extraction is slow
- CPU mode: 3-8 minutes per song is normal
- GPU mode: 20-60 seconds per song
- Use `htdemucs` (4 stems) instead of `htdemucs_6s` (6 stems) for faster extraction

## License

MIT License — see [LICENSE](LICENSE) file.
