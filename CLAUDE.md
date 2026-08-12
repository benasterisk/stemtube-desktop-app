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

## Linux distribution (AppImage)

Mirrors the Windows model. What the user installs depends on the distro
(`linux-installer/`):
- **Ubuntu/Debian → a `.deb` package** (`linux-installer/deb/`), the real `.exe`
  equivalent: double-click to install → **StemTube Desktop** apps-menu entry +
  a `stemtube` command. First launch opens a GTK window (zenity), detects the
  GPU, downloads the matching engine and runs it with
  `--appimage-extract-and-run` → **no `libfuse2`, no root at run time**.
- **Other distros → the engine AppImage directly** (run with
  `--appimage-extract-and-run`).

**Why not a double-clickable installer AppImage?** On a desktop without
`libfuse2`, double-clicking an `.AppImage` fails ("no application installed for
AppImage bundles") — the file manager can't mount it, and the extract-and-run
fallback only applies from a shell. So the *installer* is a `.deb`; only the
*engine* is an AppImage (launched from the installed `stemtube` command, which
always passes `--appimage-extract-and-run`).

Two self-contained engine AppImages (CPU + GPU) back it, built by
`.github/workflows/build-appimage.yml` (or manually — same steps).
(`stemtube-linux-launcher.sh` is an older curl|bash launcher kept as a
headless/CLI fallback.) See `linux-installer/README.md` to build the `.deb`.

**Build recipe** (per variant):
1. Fetch a relocatable CPython 3.12 from `python-build-standalone` (astral-sh),
   pinned tag `20260807`, `install_only_stripped` archive, into `AppDir/usr/`.
2. `pip install torch torchaudio` from `whl/cpu` (CPU) or `whl/cu124` (GPU),
   then the rest of the deps. `demucs==4.0.1` (4.1.0 removed
   `demucs.separate.load_track`, still imported by `stems_extractor.py`).
3. Copy the app source into `AppDir/usr/src/stemtube`, bundle `ffmpeg`/`ffprobe`
   under `AppDir/usr/bin`, write `AppRun` (sets PATH, `STEMTUBE_DATA_DIR`,
   `FLASK_SECRET_KEY`, then `exec python launcher.py`).
4. Package with `appimagetool --runtime-file runtime-x86_64` (fetch the runtime
   up front — appimagetool's mid-build download fails on any network hiccup).
5. GPU AppImage exceeds GitHub's 2 GB asset limit → `split -b 1900M` into
   `.part0`/`.part1`; the launcher reassembles with `cat`.

**Gotchas learned building this** (don't rediscover them):
- **clang required** — `python-build-standalone`'s sysconfig invokes `clang`
  (not gcc) to compile C extensions; without it madmom fails with
  `No such file: 'clang'`. Install `clang` alongside `build-essential`.
- **madmom** — the `0.16.1` pip release doesn't build under PEP 517 (its
  isolated build env can't see Cython). Use the git build
  (`madmom @ git+https://github.com/CPJKU/madmom@main`, resolves to 0.17.dev0),
  which works and is fine with numpy 2.x.
- **Read-only APP_DIR** — a mounted AppImage is read-only squashfs. Never write
  next to the code (logs, sessions, secret key, bundled dirs); everything
  writable goes under `USER_DATA_DIR`. Test with the **real mounted AppImage**,
  not `APPIMAGE_EXTRACT_AND_RUN=1` (which hides the bug).
- **AVX** — official torch x86_64 wheels require AVX. Won't run in a VM that
  masks it. Test on bare metal, WSL2, or VirtualBox with `--cpu-profile host`.
- **Build on ubuntu-22.04** (glibc 2.35) so the AppImage runs on older distros;
  AppImages run on glibc ≥ their build glibc.
- **WSL2 is the best test env** — build + test CPU + test GPU with real CUDA.
  A process started via `wsl.exe -- bash -c '... &'` dies when the wsl.exe call
  returns; use `systemd-run --unit=X --setenv=HOME=/root ...` for long builds.
