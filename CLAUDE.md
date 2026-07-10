# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**See `../CLAUDE.md` for full architecture, commands, and shared patterns.**

## Edition: StemTube Desktop Friend

- `edition.py`: `EDITION="friend"`, `HAS_YOUTUBE=True`, `HAS_LICENSE=False`
- YouTube enabled via yt-dlp (search, download, cookie management)
- No licensing or trial — free to use
- 12 blueprints (no `license_bp`), auto-login single-user mode

## Friend-Specific Configuration

| Setting | Value |
|---------|-------|
| YouTube | Enabled (yt-dlp with cookie support) |
| Licensing | Disabled |
| Beat Detection | Madmom (CNN + CRF + downbeat tracking) |
| Chord Detection | BTC Transformer + madmom fallback |
| Auto-login | Yes (single desktop user) |

## Key Files

| File | Purpose |
|------|---------|
| `edition.py` | `EDITION="friend"`, `HAS_YOUTUBE=True`, `HAS_LICENSE=False` |
| `core/aiotube_client.py` | yt-dlp wrapper for YouTube search and video info |
| `routes/downloads.py` | YouTube search/download routes restored |
| `routes/admin_api.py` | Includes cookie upload/management routes |
| `core/madmom_chord_detector.py` | Beat/chord detection with compiled-mode path fix |

## Madmom Compiled-Mode Fix

When running as a compiled executable (PyInstaller/Nuitka), madmom cannot find its model files because `os.path.dirname(__file__)` resolves incorrectly. The fix in `core/madmom_chord_detector.py` detects frozen mode and patches `madmom.models.MODEL_PATH` at import time. Build scripts (`nuitka_build.py`, `stemtube-backend.spec`) include `madmom/models/` in the dist.

## Quick Start

```cmd
python setup_desktop.py
venv\Scripts\activate
python launcher.py
```
