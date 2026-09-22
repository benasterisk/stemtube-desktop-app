# Changelog

All notable changes to StemTube will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] — delivered by the in-app updater

Ported from the server edition (StemTube_R2 commits `1677f8d`, `9154fb5`,
`0dee7f7`, 2026-09-22). No new installer: existing 2.2.0 installs receive it
through `update/manifest.json`. Songs extracted before this update keep their
old chords until **Réanalyser** (Chords tab) or
`python utils/analysis/reanalyze_all_chords.py [--limit N] [--video-id ID]`.

### Changed — chords are detected after extraction, on the harmonic stems

- **Chord detection moved after stem extraction.** Nothing is detected at
  import any more (chords are only shown in the mixer, which needs the stems
  anyway); the import phase keeps BPM, a provisional key, Skip Intro and
  structure. The new `core/chord_refiner.py` runs right after the madmom beat
  grid ("Detecting chords..."), on `POST /api/extractions/<id>/chords/regenerate`
  and in `utils/analysis/reanalyze_all_chords.py`: BTC on a mix of every stem
  but vocals and drums (full mix when none is on disk), boundaries snapped to
  the beat grid (half-tempo gaps subdivided internally, stored grid untouched),
  a Viterbi pass over beats on triads (a change is cheapest on a downbeat, and
  follows the bar position where changes pile up when the downbeat tracker is
  out of phase), major/minor doubts settled with the key, one-beat chords
  absorbed. The chord count roughly halves, with zero sub-beat chords;
  ~5-10 s per song on CPU.
- **Both chord names are stored**: `chords_data` is now
  `[{"timestamp": 19.705, "chord": "Em7", "simple": "Em"}, ...]` — the
  detailed name when it covers at least half of the segment, plus its triad;
  timestamps sit on beats and "N" passages are omitted. `/chords/regenerate`
  also returns `detected_key`, `key_confidence` and `source` (`stems` | `mix`).
- **The key comes from the chords**: after extraction `detected_key` is the
  best of the 24 keys scored on time spent on the key's chords, tonic time,
  dominant resolutions, first/last chord and the Krumhansl-Kessler correlation
  of the harmonic chroma; `analysis_confidence` is the margin over the
  runner-up. The import-time key is only provisional.
- **Chords are re-decoded after a beat regeneration**:
  `POST /api/extractions/<id>/beats/regenerate` re-runs the chord decoding on
  the new grid and returns the result as `chords`.
- **Fresh chords and key in the mixer metadata**: `GET /poc-mixer/meta/<id>`
  overlays `chords`, `key`, `key_tonic`, `key_mode` and `key_confidence` from
  the database on every request (the cached `meta.json` stays valid for the
  audio artifacts only), so a regeneration shows up without rebuilding the
  mixer cache.

### Added — lyrics under the chords, songbook chords, follow-scroll

- **Simple / Détaillé chord names** — a toggle in the Chords tab header
  switches between triads (`Em`) and detailed names (`Em7`, `A7`); the chord
  changes are the same either way. Stored per browser (`localStorage` key
  `stemtube_chord_detail`, default simple); the stage window follows.
- **Réanalyser button in the Chords tab** (`#regenerateChordsBtn`) — re-detects
  chords and key from the stems.
- **Lyrics under the chords are now a timeline of their own** (Chords tab,
  Stage View chord grid): one lane per chord row where each word sits where it
  is sung, on the same clock as the beat cells, instead of being dumped into
  the bar it starts in. Overlapping words move to a second row or slide right;
  the sung word is highlighted; the lane is not cut by beats or bars. The Stage
  View grid is now systems of 4 bars with the lane underneath. Words are
  positioned from the on-screen cells, so cell width and bar borders cannot
  drift them.
- **Chords above the lyrics (songbook)** in the Lyrics tab and its Stage View:
  every chord change is placed over the syllable where it happens; changes
  played in a long gap between two lines (intro, solo, outro) appear as a
  dimmed chord-only row. The songbook already existed but never showed
  anything: it read the chords from a global filled after the lyrics render.
- **Manual scrolling in the lyrics and chord views during playback** (Lyrics
  tab, both Stage Views): scrolling by hand now pauses the auto-follow instead
  of being snapped back within a second, and a "Now" button appears
  bottom-right to return to the current position (`static/js/follow-scroll.js`).

### Fixed

- **"F major" on almost every song**: the import-time key chroma was built from
  the tempo STFT (2048-point window at 44.1 kHz = 21.5 Hz bins, all multiples
  of a low F and wider than a semitone below 370 Hz) and the key was "loudest
  pitch class + compare triads". `core/audio_analysis.py` now uses a
  16384-point STFT restricted to 65–2100 Hz and Krumhansl-Kessler correlation.
  Still approximate — it is replaced by the chord-based key after extraction.
- **Volume and pan sliders clipped at low vertical zoom**: rows under 68 px now
  use a one-line compact layout (`Mixer.syncRowHeights`, `.lctrl.compact`).
- **Control blocks drifting away from their lanes after restoring a saved
  vertical zoom**: row heights are re-synced after the restore.

### Removed

- `core/chord_detector.py` (the librosa template detector and the
  `analyze_audio_file()` wrapper around BTC — no importers left),
  `utils/analysis/reanalyze_with_madmom.py` and
  `utils/analysis/reanalyze_neil_young.py`.

---

## [2.2.0] - 2026-09-20

First release published as a **single tag carrying every platform** — the
Windows `.exe`, the Ubuntu/Debian `.deb` and the Linux AppImages now ship
together under `v2.2.0` instead of the three separate tags used before.

### Added — fine separation and the chords chart

- **17-stem fine model (`mvsep_mega_fine`), NVIDIA GPU only.** A three-stage
  pipeline: `htdemucs_6s` for the coarse split, DrumSep on the drum stem
  (kick / snare / toms / cymbals), then MVSep Mega BS-RoFormer heads splitting
  what is left through Wiener masks. Output: lead and backing vocals, the kit
  split four ways, bass, electric and acoustic guitar, piano, organ, synth,
  brass, winds, strings, other. Weights (~1.5 GB) download on first use, and
  the job runs as a subprocess so all VRAM is returned when it exits. The
  standard 4- and 6-stem Demucs models are unchanged and still run on CPU.
- **A real VRAM check instead of a total-memory gate.** The server edition
  gated the model on total VRAM ≥ 6 GiB, which rejects a 6 GB card reporting
  5.997 GiB. The model now stays visible whenever a CUDA GPU is present, and
  at launch the check looks at *free* memory (`torch.cuda.mem_get_info`)
  against a 4.5 GiB usable floor (`min_usable_vram_gb`), dropping cached
  models to reclaim memory before giving up. Fine jobs are serialized so two
  cannot contend for the card.
- **Chords view rebuilt as a stage chart**, taken verbatim from the server
  edition: four bars per system (two on mobile) instead of one thin row per
  bar, lyrics under every beat, chord names scaled to their cell so longer
  spellings like `C#maj7` fit instead of spilling, a clearer "now" cue on the
  active bar and beat, and auto-scroll that parks the active system at 28%
  from the top for look-ahead.

### Changed — the app opens in your browser

- **The embedded webview is gone on every platform.** Both the Python launcher
  and the Tauri shell now start the server and open your **default browser** at
  `http://127.0.0.1:5011`, which is what the Linux build already did. The
  embedded window cost more than it gave: Stage View opened twice, and a
  browser window appeared beside the native one anyway, because WebView2 hands
  every new-window request to the system browser. What remains is a small
  control window (Tk for the Python launcher, a Tauri panel for the installed
  app) showing the URL, a button to reopen the browser and one to quit — so
  closing a tab leaves no orphaned process. `pywebview` is dropped from the
  dependency and packaging lists; `--no-window` and the headless fallback
  behave as before.
- **Every version declaration aligned on 2.2.0** — `core/config.py`,
  `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml` and `package.json`
  previously declared three different numbers, and the published tags added a
  fourth reading. The auto-updater is unaffected: it tracks commits, not these
  numbers.

### Added — backported from the server edition

- **Lyrics from LRCLIB aligned on Whisper**, replacing Musixmatch, whose
  unofficial API stopped serving anonymous clients around April 2026. LRCLIB is
  free and needs no account; faster-whisper supplies word timings and the LRCLIB
  words are placed on them. Below a 30% match rate the alignment is rejected and
  the record's own line timing (or Whisper alone) is used.
- **Language detected on voiced parts only** (VAD, three 30 s windows) instead of
  Whisper's first 30 seconds — the reason French songs with an instrumental intro
  came out transcribed as English. Whisper's credit hallucinations over
  instrumentals are dropped.
- **Mixer scrub** — drag the timeline ruler to move the playhead and hear short
  slices as you go.
- **Loop controls** — draggable edge handles, fields accepting a timecode
  (`1:23.45`) or a bar (`b17`), and a clear button. Defining a loop is now
  Shift+drag on both the ruler and the lanes, so a plain drag no longer creates
  one by accident.
- **Shared snap-to-beat toggle** for loop bounds and the Start/Stop markers, with
  Alt still overriding it for a single drag.
- **Stage-prompter lyrics popup** — real font scaling up to 3x (the text reflows
  instead of overflowing), size remembered between sessions, active line parked
  mid-screen, per-line timecodes hidden.
- **Explicit re-extraction** — a button next to Open Mixer re-runs a song with
  another model and replaces the stems.
- **`POST /api/extractions/<id>/analyze-structure`** to run MSAF on one song.
- **Mixer artifacts are pre-built after an extraction**, so the first mixer open
  is a cache hit instead of a wait.

### Fixed

- **Analysis data could be wiped**: the analysis writer overwrote every column,
  so a caller passing None for chords, structure or lyrics erased them, and
  omitting beat_offset/music_start_time reset Skip Intro and the beat offset.
  Every column is now written with COALESCE, so NULL preserves what is stored.
- **Playback died until the page was reloaded**: each stem's gain and pan nodes
  stayed connected to the master bus on stop, so every seek leaked a full chain.
- **Silence when seeking with a loop armed**: a source started past loopEnd never
  wraps, so the stems ran to the end of their buffers while the playhead kept
  looping.
- **Structure detection was dead code**: msaf 0.1.80 imports `scipy.inf` and
  `scipy.signal.gaussian`, both removed in SciPy 1.12/1.13, so it failed to
  import and `structure_data` stayed NULL for every song. Sections are now
  labelled A, B, C… by similarity cluster.
- **Downbeat detection crashed on numpy ≥ 1.24**: madmom's compiled `hmm.pyx`
  reads `np.int` at runtime, which `patch_madmom.py` cannot reach.
- **The stems ZIP 404'd** for any song not extracted in the current process —
  i.e. everything after a restart. Resolution is now database-first.
- **Tempo leaked between songs**: a session state saved before the tempo module
  had loaded stretched the next song to 120 BPM.
- **One manual scroll stuck the mixer in Manual mode**: the transient value was
  saved instead of the mode chosen with the toolbar button.
- Waveform peaks are built at the file's own sample rate and vectorized
  (2.3 s → 0.34 s for a 3-minute stem).

### Removed

- **De-bleed** (Demucs speaker-bleed removal on recordings) — it never worked,
  and the server edition dropped it.
- `musixmatch_client.py`, `syncedlyrics_client.py`, the dead `lyrics_aligner.py`
  and `vocal_onset_detector.py`, and the `syncedlyrics` dependency.

### Added — Linux support
- **`.deb` installer for Ubuntu/Debian (`linux-installer/deb/`)** — the Linux equivalent of the Windows `setup.exe`: a package users download and **double-click** to install (via the software centre), adding a **StemTube Desktop** apps-menu entry and a `stemtube` command. First launch opens a GTK window (zenity), detects the GPU, downloads the matching self-contained engine (CPU or NVIDIA GPU) with a progress bar and runs it — with `--appimage-extract-and-run`, so **no `libfuse2` and no root at run time**. (An earlier AppImage-based installer was dropped: a `.AppImage` isn't double-clickable on desktops without libfuse2. Other distros run the engine AppImage directly.)
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


## [Web 2.2.0] - 2026-01-25

> Everything from here down belongs to the earlier **StemTube Web** lineage,
> before the desktop editions were split off. Its version numbers are that
> project's, not the desktop app's — this `2.2.0` is unrelated to the desktop
> `2.2.0` at the top of the file.

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
