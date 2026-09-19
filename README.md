# StemTube Desktop

Version **2.2.0**. Desktop application (Windows and Linux) for AI-powered music analysis of your own audio files. Extracts stems, detects chords and transcribes lyrics — all locally on your machine.

The app runs a local server and opens in your **default browser** at `http://127.0.0.1:5011`; a small control window stays behind it to show the URL, reopen the browser and quit cleanly. There is no embedded webview.

## Features

- **File Upload** — Import local audio files (MP3, WAV, FLAC, M4A, AAC, OGG, WMA)
- **Stem Extraction** — AI-powered source separation using Demucs (vocals, drums, bass, other, piano, guitar)
- **Fine separation, up to 17 stems** — `mvsep_mega_fine`: `htdemucs_6s` + DrumSep + MVSep Mega BS-RoFormer. Lead/backing vocals, kit split into kick/snare/toms/cymbals, electric and acoustic guitar, piano, organ, synth, brass, winds, strings. **Requires an NVIDIA CUDA GPU** with ≥ 4.5 GiB of usable VRAM; the standard 4- and 6-stem models run on CPU.
- **Chord Detection** — Real-time chord display with BTC Transformer (170 chords) + madmom fallback
- **Lyrics Transcription** — Synced lyrics from LRCLIB, placed on word timings from faster-whisper
- **Mixer** — Full-featured audio mixer with pitch/tempo control, karaoke display, waveform visualization
- **Multi-track Recording** — Record over stems with timeline positioning
- **GPU Acceleration** — Automatic NVIDIA CUDA detection (falls back to CPU)

## Requirements

- **Windows 10/11** (64-bit) or a 64-bit Linux (glibc ≥ 2.35)
- **Python 3.12+** — [Download from python.org](https://www.python.org/downloads/) (NOT Windows Store; only for source installs — the packaged app ships its own)
- **~4 GB disk space** (CPU mode) or **~8 GB** (GPU + pre-downloaded models)
- **NVIDIA GPU** (optional) — For faster stem extraction and lyrics transcription

## Install

Every platform ships on a single release: **[v2.2.0](https://github.com/benasterisk/stemtube-desktop-releases/releases/tag/v2.2.0)**.

Both the `.exe` and the `.deb` are **light installers** (~1–2 MB). They contain no AI engine: on first launch they detect your hardware and download the matching self-contained engine — **CPU** or **NVIDIA GPU** (CUDA) — assemble it and start the app. You never handle the split download parts yourself; the installer does. First boot takes a few minutes, later launches are immediate. Python and FFmpeg are bundled in the engine, so nothing else is needed.

### Windows

Download and run **`StemTube_Desktop_2.2.0_x64-setup.exe`** from the release. The engine is ~570 MB (CPU) or ~2.8 GB (GPU).

### Ubuntu / Debian

Download **`stemtube-desktop_2.2.0_amd64.deb`** and double-click it (opens in your software centre → Install), or:

```bash
sudo apt install ./stemtube-desktop_2.2.0_amd64.deb
```

Then launch **StemTube Desktop** from your applications menu. The first launch opens a small progress window, detects your GPU and downloads the matching engine (CPU ~620 MB / NVIDIA GPU ~3 GB), unpacking it once — no `libfuse2`, no root at run time.

### Other distros (Fedora, Arch, openSUSE…)

No package manager step — run the engine AppImage directly:

```bash
# CPU (~620 MB) — works on any 64-bit Linux, no libfuse2 needed
wget https://github.com/benasterisk/stemtube-desktop-releases/releases/download/v2.2.0/StemTube-x86_64-cpu.AppImage
chmod +x StemTube-x86_64-cpu.AppImage
./StemTube-x86_64-cpu.AppImage --appimage-extract-and-run
```

For NVIDIA GPUs, download `StemTube-x86_64-gpu.AppImage.part0` + `.part1` (~3 GB, CUDA 12.6) and join them: `cat StemTube-x86_64-gpu.AppImage.part* > StemTube-x86_64-gpu.AppImage`. (This manual step applies only to this direct-AppImage route; the `.deb` and `.exe` do it for you.)

**Developers — from-source script.** Clones the app and builds a Python environment from source. Requires `git` and `python3` **3.10–3.13** (not 3.14 yet — PyTorch has no wheel for it).

```bash
sudo apt install git python3 python3-venv      # Debian/Ubuntu prerequisites
curl -fsSL https://raw.githubusercontent.com/benasterisk/stemtube-desktop-app/main/install.sh | bash
```

Requires a 64-bit Linux (glibc ≥ 2.35) with an AVX-capable CPU — PyTorch needs AVX, so it won't run in a VM that masks it (use `--cpu-profile host` on VirtualBox, or WSL2, or bare metal).

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

### Option 3: Server only (no control window)
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
python launcher.py                 # Normal launch (default browser + Tk control window)
python launcher.py --no-window     # Server + browser only, no control window
python launcher.py --debug         # Enable debug mode
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
├── launcher.py              # Desktop entry point (Flask + default browser)
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
│   ├── lrclib_client.py     # LRCLIB lyrics lookup
│   ├── lyrics_merger.py     # LRCLIB words placed on Whisper word timings
│   ├── msst/                # 17-stem fine separation (GPU-only subprocess)
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
- The 17-stem `mvsep_mega_fine` model is GPU-only and takes roughly 1–2 minutes per song

### The 17-stem model is missing or refuses to run
It requires an NVIDIA CUDA GPU. It is hidden entirely when no CUDA device is present, and refused at launch when free VRAM is below 4.5 GiB (`min_usable_vram_gb` in `core/config.py`). Closing other GPU applications usually frees enough.

## License

MIT License — see [LICENSE](LICENSE) file.
