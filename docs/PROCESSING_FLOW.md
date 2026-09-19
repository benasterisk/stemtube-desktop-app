> **⚠️ Historical note:** this document was written when the app still shipped YouTube search/download. That support has been removed from the Standard desktop edition — `yt-dlp`, cookies, the `HAS_YOUTUBE` flag, `core/download_manager.py`, `core/aiotube_client.py`, `core/js_runtime.py`, and the corresponding routes/UI no longer exist. Sections describing them are kept only for historical context and no longer reflect the current code.

# StemTube Desktopcessing Flow

## Overview

This document describes the complete flow from download to extraction, including all analysis operations.

---

## Phase 1: Download

**Trigger:** POST `/api/downloads`

**Operations:**
1. Check global_downloads table (multi-user deduplication)
2. Create DownloadItem, add to queue
3. yt-dlp downloads from YouTube (iOS client fallback for 403 errors)
4. Convert to MP3 (192kbps, 44.1kHz stereo)
5. Save to `/downloads/{title}/audio/{title}.mp3`

**Files Created:**
```
/downloads/{title}/audio/{title}.mp3
```

---

## Phase 2: Audio Analysis (During Download)

**Trigger:** Download complete callback (only for AUDIO downloads)

**Operations (in order):**

### 2.1 Tempo/Key Detection
- **Library:** librosa + scipy.signal STFT
- **Method:** Autocorrelation on spectral flux for BPM, chroma template matching for key
- **Output:** `detected_bpm`, `detected_key`, `analysis_confidence`

### 2.2 Chord Detection
- **Library:** BTC Transformer → madmom CRF → hybrid (fallback chain)
- **Input:** Full audio + detected BPM/key for beat grid alignment
- **Output:** `chords_data`, `beat_offset`

### 2.3 Structure Detection
- **Library:** MSAF (Music Structure Analysis Framework)
- **Algorithm:** CNMF + Foote boundaries
- **Output:** `structure_data` (sections: Intro, Verse, Chorus, etc.)

### 2.4 Lyrics Detection (LRCLIB lookup only)
- **Library:** `core/lrclib_client.py` (LRCLIB, free, no account)
- **Note:** Lookup only, NO Whisper here (the full pipeline runs after extraction)
- **Output:** `lyrics_data` (a line-timed preview when the record is line-synced)

**Database Update:** All results saved to `global_downloads` table

---

## Phase 3: Stem Extraction

**Trigger:** Manual - POST `/api/extractions` (user clicks "Extract Stems")

**Operations:**
1. Check global extraction (deduplication)
2. Reserve extraction slot (prevent race conditions)
3. Load Demucs model (auto GPU detection)
4. Separate stems: vocals, drums, bass, other (+ guitar, piano for 6-stem)
5. Detect silent stems (RMS energy analysis)
6. Copy to output directory
7. Create ZIP archive

**Files Created:**
```
/downloads/{title}/audio/stems/
├── vocals.mp3
├── drums.mp3
├── bass.mp3
├── other.mp3
├── guitar.mp3 (6-stem only)
├── piano.mp3 (6-stem only)
└── {title}_stems.zip
```

---

## Phase 4: Post-Extraction Auto-Detection

**Trigger:** Extraction complete callback

**Operations:**

### 4.1 Lyrics Detection (Full)
- **Condition:** Only if `vocals.mp3` exists
- **Library:** LRCLIB → faster-whisper, aligned by `core/lyrics_merger.py`
- **Input:** vocals.mp3 (better quality than full audio)
- **Sync:** LRCLIB words placed on Whisper word timings; below a 30% match
  rate the alignment is rejected and the line timing (or Whisper alone) wins
- **Output:** Updates `lyrics_data` in database

**Note:** This REPLACES any lyrics found during download phase (uses better source)

---

## Fallback Chains

### Chord Detection
1. BTC Transformer (professional, 170 chord vocabulary)
2. madmom CRF (works on all genres)
3. Hybrid (madmom beats + key-aware templates)

### Lyrics Detection
1. LRCLIB line-synced record aligned on Whisper word timings
2. LRCLIB line timing alone (alignment rejected below a 30% match rate)
3. faster-whisper alone (song missing from LRCLIB)

### Structure Analysis
1. CNMF + Foote boundaries
2. Spectral Clustering (scluster)
3. Online LDA (olda)

---

## Libraries Used

| Analysis | Library | Purpose |
|----------|---------|---------|
| BPM/Key | librosa, scipy | Spectral analysis, template matching |
| Chords | BTC, madmom | Chord recognition |
| Structure | MSAF | Section segmentation |
| Lyrics (sync) | LRCLIB | Free lyrics database, no account |
| Lyrics (ASR) | faster-whisper | Speech-to-text |

| Stem Separation | Demucs | Source separation |

---

## Key Files

| Component | File |
|-----------|------|
| Download Management | `core/download_manager.py` |
| Stem Extraction | `core/stems_extractor.py` |
| Chord Detection | `core/chord_detector.py`, `core/btc_chord_detector.py`, `core/madmom_chord_detector.py` |
| Lyrics Detection | `core/lyrics_detector.py`, `core/lrclib_client.py`, `core/lyrics_merger.py` |
| Media Metadata | `core/media_metadata.py` (artist/track for the lyrics lookup) |
| Structure Analysis | `core/msaf_structure_detector.py` |
| Database | `core/downloads_db.py` |
| Main Routes | `app.py` |

---

## Optimization Notes

1. **Lyrics Detection Optimized:**
   - During download: LRCLIB lookup only (fast API call)
   - After extraction: LRCLIB + Whisper alignment (using vocals.mp3)
   - Avoids redundant Whisper processing on full audio

2. **Chord Detection:**
   - Currently uses full audio
   - Could potentially use instrumental stem for better accuracy (future optimization)

3. **Structure Analysis:**
   - Only during download phase
   - Could be re-run on instrumental stems (future optimization)
