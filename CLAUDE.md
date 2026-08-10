# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Edition: StemTube Desktop (Standard, local files only)

- `edition.py`: `EDITION="standard"`, `HAS_LICENSE=False`
- **No YouTube** — no search, no download, no cookies, no `yt-dlp` dependency
- No licensing / no trial — free desktop app
- Single-user auto-login, LAN-trusted (binds `0.0.0.0` by default)

## Configuration at a glance

| Setting | Value |
|---------|-------|
| Sources | Local file uploads only (MP3/WAV/FLAC/M4A/AAC/OGG/WMA/MP4/AVI/MKV/MOV/WEBM) |
| Licensing | Disabled |
| Beat detection | Madmom (CNN + CRF + downbeat tracking) |
| Chord detection | BTC Transformer + madmom fallback |
| Auto-login | Yes (single desktop user) |
| Blueprints | 10 (`downloads` kept as a DB-only library blueprint — no yt-dlp) |

## Key modules

| File | Purpose |
|------|---------|
| `edition.py` | `EDITION="standard"`, `HAS_LICENSE=False` |
| `core/audio_analysis.py` | Standalone BPM + key detection (STFT + autocorrelation) |
| `core/stems_extractor.py` | Demucs stem separation |
| `core/madmom_chord_detector.py` | Beat/chord detection with compiled-mode path fix |
| `routes/files.py` | Local file upload endpoint |
| `routes/downloads.py` | Library listing + extraction status (DB only) |
| `routes/extractions.py` | Stem extraction jobs |
| `routes/library.py` | User library management |

## Madmom Compiled-Mode Fix

When running as a compiled executable (PyInstaller/Nuitka), madmom cannot find its model files because `os.path.dirname(__file__)` resolves incorrectly. The fix in `core/madmom_chord_detector.py` detects frozen mode and patches `madmom.models.MODEL_PATH` at import time. Build scripts (`nuitka_build.py`, `stemtube-backend.spec`) include `madmom/models/` in the dist.

## Quick Start

```bash
python setup_desktop.py
source venv/bin/activate      # venv\Scripts\activate on Windows
python launcher.py
```
