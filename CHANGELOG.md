# Changelog

All notable changes to StemTube will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added — Linux support
- **Self-contained AppImages (CPU + GPU)** — a Linux distribution mirroring the Windows model. Each AppImage bundles a relocatable CPython 3.12, PyTorch (CPU or CUDA 12.4), Demucs, madmom, faster-whisper and FFmpeg, so end users need no Python, no pip and no system CUDA. Published on the `linux-v2.0.0` release; the GPU build (~3 GB) ships split in two parts under GitHub's 2 GB asset limit. CPU build validated in a VM, GPU build validated with real CUDA on an NVIDIA RTX 4050 via WSL2.
- **`stemtube-linux-launcher.sh`** — a lightweight launcher that detects the GPU (`nvidia-smi`), downloads the matching AppImage from the release, reassembles + checksum-verifies it, installs a `stemtube` command and a desktop entry, then runs it.
- **`.github/workflows/build-appimage.yml`** — GitHub Actions workflow that builds both AppImages on `ubuntu-22.04` (glibc 2.35 floor for broad compatibility) using `python-build-standalone` 3.12 + appimagetool, and attaches them to a release.

### Fixed — Linux / AppImage
- **Read-only filesystem crashes at startup** — when run from a mounted AppImage, `APP_DIR` is a read-only squashfs, so the app crashed with `OSError(Errno 30)` trying to create dirs and write session/secret/log files next to the code. `core/config.py`, `app.py` and `core/logging_config.py` now keep all writes (logs, `flask_session/`, `.secret_key`) in the writable user-data dir (`~/.stemtube-desktop`) and only touch bundled dirs when their parent is writable. Only observable with a real mounted AppImage — not with `APPIMAGE_EXTRACT_AND_RUN`.
- **`install.sh` rejected too-new Python** — Ubuntu Studio 26.04 ships Python 3.14 as the default, which has no PyTorch wheel yet; the installer now enforces the 3.10–3.13 range with a clear fix message instead of a cryptic pip failure.

### Removed
- **YouTube support fully deleted** — the Standard desktop edition no longer imports `yt_dlp` at any point, so the package no longer requires it. Deleted `core/download_manager.py`, `core/aiotube_client.py`, `core/js_runtime.py`, `core/youtube_cookies.txt`, the old YouTube search/download endpoints in `routes/downloads.py`, all cookie management routes in `routes/admin_api.py`, the admin "Reload from YouTube" button, the `HAS_YOUTUBE` edition flag, the per-user `youtube_enabled` column plumbing, and all matching UI (search bar, cookies section, download modal, JS handlers).
- **`js_runtime` module** — Deno/Node bootstrapping was only needed to solve YouTube JS challenges.

### Added
- **`core/audio_analysis.py`** — standalone BPM + key detection function (STFT + autocorrelation), extracted from the deleted `DownloadManager` so the extraction and upload pipelines no longer depend on a YouTube-oriented class.

### Changed
- `routes/downloads.py` recreated as a minimal DB-only blueprint (5 endpoints: list library, extraction-status lookup, batch extraction-status, delete, clear-all).
- `edition.py` no longer exports `HAS_YOUTUBE`.
- `install.sh` no longer needs to install `yt-dlp` or a JS runtime.

## [Desktop Standard 2.0.0] - 2026-07-09

### Added
- **Standard edition finalized** - Same engine and auto-install experience as Friend 1.0.1, without YouTube search/download and without licensing: local file upload is the default (and only) input
- **Tauri launcher** - 1.4 MB installer; detects NVIDIA GPU and downloads the matching backend (CPU ~524 MB / GPU ~2.8 GB) from GitHub Releases on first launch, with venv self-repair via portable CPython and 300 s cold-boot budget
- Inherits every Friend 1.0.1 fix: madmom 0.17.dev0 (mixer beat analysis), seamless A/B loop, metronome instruments, count-in, chord-tab word-level lyrics


## [2.2.0] - 2026-01-25

### Added
- **Deno JavaScript runtime** - Integration for YouTube challenge solving (replaces aiotube dependency)
- **yt-dlp automatic updates** - Nightly update check at startup ensures latest YouTube compatibility
- **Cookie.txt browser export** - Admin system for YouTube authentication via browser cookies
- **LRCLIB synchronized lyrics** - Primary lyrics source with faster-whisper fallback for alignment
- **PWA support** - Installable mobile app with offline mode and audio caching
- **Mobile Settings tab** - Cache management and offline audio controls
- **Mobile admin menu** - Full admin access on mobile devices
- **YouTube search toggle** - Admin interface toggle for YouTube search functionality
- **Desktop Settings/Admin separation** - Cleaner UI with distinct settings and admin panels

### Changed
- **Admin panel reorganization** - Now organized into 4 tabs: Users, Logs, Settings, Cleanup
- **YouTube download backend** - Replaced aiotube dependency with pure yt-dlp + Deno runtime

---

## [2.1.2] - 2026-01-13

### Fixed
- **Admin cleanup session sync** - Downloads deleted via admin cleanup now immediately disappear from all active user sessions without requiring logout/login
- **Bulk delete session sync** - Bulk delete operations now also clear downloads from active user sessions
- **Mixer stems loading after extraction** - Fixed race condition where stems wouldn't load on first click after extraction completion
  - Database persistence now happens BEFORE socket events are emitted
  - Mixer route now properly parses `stems_paths` JSON from database into `output_paths`

### Added
- `remove_download_by_video_id()` method to DownloadManager for clearing specific downloads from session
- `clear_download_from_all_sessions()` method to UserSessionManager for admin cleanup operations
- Debug logging for cleanup operations to track session clearing

---

## [2.1.1] - 2026-01-11

### Added
- **GridView2 chord transposition** - Chords now update in real-time when pitch changes via `updateGridView2Chords()` method
- **Fullscreen Lyrics chord transposition** - Chords update when pitch changes via `updateFullscreenLyricsChords()` method

### Fixed
- **GridView2 Play button** - Fixed play button not working in Grid View popup by moving `initGridView2Controls()` to main initialization
- **Duplicate event listeners** - Added guards to prevent multiple event listener registration in GridView2 popup

### Changed
- **Tempo/Pitch popup style** - Converted from full-screen overlay to floating popup at bottom of screen
- **Popup backdrop** - Reduced opacity from 80% to 30% for better content visibility while adjusting tempo/pitch

---

## [2.1.0] - 2025-12-31

### Added
- **Songbook chord display** - Chords displayed above lyrics in karaoke view (desktop)
- **Pitch shift event listener** - Lyrics popup now updates chord transpositions when pitch changes
- **setPitchShift() method** - Direct semitone control (-12 to +12) for full octave range

### Fixed
- **Grid View scroll interruption** - Changed from smooth to auto scroll behavior to prevent jitter
- **Pitch slider range** - Extended from ±6 to ±12 semitones for full octave transposition
- **Pitch slider snap-back** - Fixed slider resetting to center when exceeding ±6
- **Pitch value display** - Now updates correctly when moving popup sliders
- **Lyrics popup text size** - Size slider now works using CSS transform scale
- **Lyrics popup scroll focus** - Fixed lyrics scrolling out of view in popup mode
- **Nested scroll containers** - Removed conflicting overflow-y on popup karaoke-lyrics

### Changed
- **Popup sizes increased** - Both Lyrics Focus and Grid View popups now use 98vw × 98vh
- **Lyrics popup element refresh** - Now dynamically finds lyrics element when opening popup

---

## [2.0.0] - 2025-12-28

### Added
- **BTC Transformer chord detection** (170 chord vocabulary) - Most accurate backend
- **3 chord detection backends** with automatic fallback (BTC → madmom → hybrid)
- **Complete documentation overhaul** - Reorganized into user/admin/developer/feature guides
- **French comment translation** - All ~600 French comments translated to English
- **CONTRIBUTING.md** - Comprehensive contribution guidelines
- **CHANGELOG.md** - Project history tracking

### Changed
- **Documentation structure** - Reorganized into logical categories (user-guides/, admin-guides/, developer-guides/, feature-guides/)
- **README.md** - Modernized with badges, concise quick start, correct port (5011)
- **ARCHITECTURE.md** - Updated endpoint count (69), added BTC chord detector, removed stale notes

### Fixed
- **Port references** - Corrected from 5012 to 5011 throughout documentation
- **Endpoint count** - Updated from 78 to accurate 69 endpoints

### Documentation
- Created new documentation structure with 7 categories
- Archived 12+ outdated mobile documentation files
- Updated all internal cross-references
- Added feature-specific guides for BTC, GPU setup, mobile architecture

---

## [1.2.0] - 2025-11-24

### Added
- **Automated GPU setup** - `os.execv()` in app.py for cuDNN configuration
- **Dependency conflict resolution** - Individual package installation
- **madmom auto-patching** - Numpy compatibility automatic
- Professional chord detection with madmom CRF
- Music structure analysis via MSAF
- Lyrics/karaoke system with faster-whisper
- Chord transposition in mixer
- Structure timeline visualization
- File upload system
- Silent stem detection
- Admin interface integration
- Global library system

### Changed
- Documentation consolidation - README.md comprehensive, CLAUDE.md technical-only
- Codebase cleanup - 16 obsolete files removed

### Fixed
- GPU library path configuration
- Dependency installation conflicts
- madmom numpy compatibility issues

---

## [1.1.0] - 2025-10-15

### Added
- **Mobile-optimized interface** (`/mobile` route)
  - iOS audio unlock mechanism
  - Touch-optimized controls
  - 9 mobile-specific JavaScript modules
  - Responsive timeline and chord display
  - SVG chord diagrams with guitar-chords-db-json
- **Pitch/tempo control** - SoundTouch integration
  - Independent pitch shifting (-12 to +12 semitones)
  - Tempo control (0.5x to 2.0x)
  - Hybrid SoundTouch/playbackRate engine
- **Real-time chord display** - Synchronized with playback
- **Karaoke lyrics display** - Word-level highlighting
- **Structure timeline** - Visual song section markers

### Changed
- Frontend architecture - Modular JavaScript design (11 mixer modules)
- Audio processing - Web Audio API with AudioWorklet
- State persistence - LocalStorage for mixer settings

### Fixed
- iOS audio playback restrictions
- Android touch responsiveness
- Mobile waveform rendering
- Cross-platform audio synchronization

---

## [1.0.0] - 2025-09-01

### Added
- **Core Features**
  - Audio source retrieval (yt-dlp)
  - AI stem separation with Demucs (4-stem and 6-stem models)
  - GPU acceleration support (CUDA 11.x-13.x)
  - Multi-user authentication system
  - Global file deduplication
  - Interactive web-based mixer
- **Audio Analysis**
  - BPM detection (custom autocorrelation algorithm)
  - Musical key detection
  - madmom chord recognition (24 chord types)
  - MSAF structure analysis
- **Database**
  - SQLite with 3-table design
  - Global downloads tracking
  - User access management
  - Download/extraction metadata
- **Admin Features**
  - User management interface
  - Storage statistics
  - Download cleanup tools
  - System configuration
- **API**
  - 69 REST endpoints
  - WebSocket real-time updates
  - File upload/download
  - Extraction management

### Technical Stack
- **Backend**: Flask 3.x, SocketIO, PyTorch 2.x, Demucs 4.x
- **Frontend**: Vanilla JavaScript ES6+, Web Audio API, SoundTouchJS
- **Audio**: madmom, librosa, scipy, faster-whisper, MSAF
- **Database**: SQLite3
- **Dependencies**: ~120 packages (18 essential)

---

## Version History

- **[2.2.0]** - January 2026 - PWA support, LRCLIB lyrics, Deno/yt-dlp migration, admin panel redesign
- **[2.0.0]** - December 2025 - Documentation overhaul, BTC chord detector, French translation
- **[1.2.0]** - November 2025 - GPU automation, dependency fixes, feature additions
- **[1.1.0]** - October 2025 - Mobile interface, pitch/tempo control, karaoke
- **[1.0.0]** - September 2025 - Initial release with core features

---

## Upgrade Notes

### 2.0.0 → Current
- Documentation paths updated - Update any hardcoded references to docs
- No breaking changes to code or database

### 1.2.0 → 2.0.0
- No database migrations required
- GPU setup now fully automatic
- All French comments translated (for contributors)

### 1.1.0 → 1.2.0
- Recommended: Clear browser cache for updated mixer interface
- Optional: Re-run `setup_dependencies.py` for GPU improvements

### 1.0.0 → 1.1.0
- **CRITICAL**: HTTPS now required for pitch/tempo features
- Database schema unchanged (backward compatible)
- New dependencies installed via `setup_dependencies.py`

---

## Deprecation Notices

### Removed in 2.0.0
- Old scattered mobile documentation (archived in `docs/archive/`)
- SESSION_NOTES*.md files (archived)
- Obsolete migration guides (archived)

### Removed in 1.2.0
- 16 obsolete development files
- Redundant setup scripts
- Old dependency management approach

---

## Contributors

Special thanks to all contributors who have helped improve StemTube!

**Major Contributors:**
- Core development and architecture
- GPU acceleration implementation
- Mobile interface development
- Documentation overhaul
- French translation efforts

---

## Links

- **Repository**: https://github.com/Benasterisk/StemTube_R2
- **Documentation**: [docs/](docs/)
- **Issues**: https://github.com/Benasterisk/StemTube_R2/issues
- **Contributing**: [CONTRIBUTING.md](CONTRIBUTING.md)

---

**Last Updated**: January 25, 2026
