"""
POC-mixer bridge routes.

The mixer UI was replaced by the cleaner POC engine. That engine expects a POC-shaped
`meta.json` (stems map, metronome resolutions, snapped beats+positions, duration,
median_bpm, start_time, key, chords, waveforms) and serves stems/metronome WAVs from
its own endpoints. Friend stores extractions differently: stems on disk (mp3) + analysis
in the DB (beat_times, chords_data, detected_key…). This blueprint bridges the two:

  POST /poc-mixer/prepare/<extraction_id>   build & cache a POC meta.json for an extraction
  GET  /poc-mixer/progress/<extraction_id>  preparation progress (mirrors POC /api/progress)
  GET  /poc-mixer/meta/<extraction_id>      return the cached POC meta.json
  GET  /poc-mixer/audio/<extraction_id>/<stem>   stream a stem or metronome WAV
  POST /poc-mixer/detect_intro/<extraction_id>   bake a count-in (precount) into metro WAVs

Key facts that shape this bridge (verified against real extractions):
  * Friend extractions already ship metronome_{0.5,1,2}.wav next to the mp3 stems, all
    sample-locked (same sr / frame count). So for already-extracted songs we REUSE them
    and only compute waveform peaks. The POC pipeline (core/poc) is the FALLBACK that
    regenerates groove-snapped metronomes for older extractions that lack them.
  * Naming: POC asks for stem id "metronome" (the 1x track) and "metronome_0.5"/"_2";
    on disk friend names the 1x one "metronome_1.wav". We map that here.
  * Stems are mp3 but the engine decodes via Web Audio (format-agnostic); only sr/length
    matter, and they already match.
"""
import os
import json
import shutil
import threading
import traceback

from flask import Blueprint, request, jsonify, send_from_directory, send_file
from flask_login import current_user

from extensions import api_login_required, user_session_manager
from core.config import ensure_valid_downloads_directory
from core.logging_config import get_logger

logger = get_logger(__name__)

poc_mixer_bp = Blueprint('poc_mixer', __name__)

# In-memory preparation progress, mirroring the POC server's PROGRESS dict.
_PREP = {}          # extraction_id -> {"stage":str,"pct":int,"done":bool,"error":str|None}
_PREP_LOCK = threading.Lock()

# Export delivery: a POST renders the file and returns a download URL; a GET then
# streams it with Content-Disposition so WebView2's native download handler fires
# (a programmatic blob: download from inside the mixer iframe is silently dropped).
# token -> {"path": abs_file, "name": download_name, "ts": epoch_seconds}
_EXPORTS = {}
_EXPORTS_LOCK = threading.Lock()
_EXPORT_TTL = 2 * 3600   # seconds; stale exports are GC'd on the next download hit


def _register_export(path, name):
    import uuid
    import time as _time
    token = uuid.uuid4().hex
    with _EXPORTS_LOCK:
        _EXPORTS[token] = {"path": path, "name": name, "ts": _time.time()}
    return token


def _gc_exports():
    """Drop export entries older than the TTL and remove their temp dirs."""
    import time as _time
    now = _time.time()
    with _EXPORTS_LOCK:
        stale = [t for t, e in _EXPORTS.items() if now - e["ts"] > _EXPORT_TTL]
        for t in stale:
            e = _EXPORTS.pop(t, None)
            if e:
                shutil.rmtree(os.path.dirname(e["path"]), ignore_errors=True)

# Stem display order the POC engine expects (metronome first). guitar/piano appear in
# some demucs models; they're tolerated as extra stems.
STEM_ORDER = ["metronome", "drums", "bass", "vocals", "other", "guitar", "piano"]
_REAL_STEMS = ["drums", "bass", "vocals", "other", "guitar", "piano"]


def _set_prep(eid, stage, pct, done=False, error=None):
    with _PREP_LOCK:
        _PREP[eid] = {"stage": stage, "pct": pct, "done": done, "error": error}


# ─────────────────────────────────────────────────────────────────────────────
# Extraction → on-disk stems resolution (mirrors files.py serve_extracted_stem)
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_download_row(extraction_id, user_id):
    """Return the friend DB row (dict) for an extraction_id, or None.

    Mirrors the resolution chain used by files.serve_extracted_stem: session
    extractor first (for the path map), then the downloads DB by download_<id>,
    video_id, or filename prefix.

    user_id must be passed in explicitly: this runs in a background thread for
    prepare(), where Flask's `current_user` proxy is unbound.

    IMPORTANT: resolve via list_extractions_for + the SAME matching as
    pages.mixer (`download_<row.id>` == extraction_id, where id is the
    user_downloads row id), so the bridge and the /mixer page always agree on
    which song an extraction_id refers to. (get_download_by_id keys differently
    and could disagree.)
    """
    from core.downloads_db import list_extractions_for

    rows = list_extractions_for(user_id)
    # 1) exact download_<id> match (primary, mirrors pages.mixer)
    for row in rows:
        if f"download_{row['id']}" == extraction_id:
            return row
    # 2) fall back to video_id or filename prefix (also mirrors pages.mixer)
    for row in rows:
        video_id = row.get('video_id', '')
        file_path = row.get('file_path', '') or ''
        filename = os.path.basename(file_path).replace('.mp3', '') if file_path else ''
        if video_id == extraction_id or (filename and extraction_id.startswith(filename)):
            return row
    return None


def _stems_map_from_row(row):
    """Parse and path-resolve the stems_paths JSON from a DB row → {stem: abs_path}."""
    from core.downloads_db import resolve_file_path
    raw = row.get('stems_paths')
    if not raw:
        return {}
    paths = json.loads(raw) if isinstance(raw, str) else raw
    out = {}
    for name, p in (paths or {}).items():
        if not p:
            continue
        rp = resolve_file_path(p)
        if rp:
            out[name] = os.path.abspath(rp)
    return out


def _safe_in_downloads(abs_path):
    """Security: confirm abs_path is inside the configured downloads directory."""
    downloads_dir = os.path.abspath(ensure_valid_downloads_directory())
    return os.path.abspath(abs_path).startswith(downloads_dir)


def _resolve_context(extraction_id, user_id):
    """Resolve an extraction to (row, stems_map, stems_dir).

    stems_dir is where the mp3 stems and metronome WAVs live (their common parent).
    Raises ValueError(message) with an HTTP-friendly message on failure.
    """
    row = _resolve_download_row(extraction_id, user_id)
    if not row:
        raise ValueError("extraction not found in your records")
    if not (row.get('extracted') and row.get('stems_paths')):
        raise ValueError("extraction has no stems")
    stems_map = _stems_map_from_row(row)
    if not stems_map:
        raise ValueError("no resolvable stem paths")
    # all stems share a directory; derive it from the first real stem we can find
    ref = None
    for n in _REAL_STEMS:
        if n in stems_map and os.path.exists(stems_map[n]):
            ref = stems_map[n]
            break
    if not ref:
        raise ValueError("no stem files exist on disk")
    if not _safe_in_downloads(ref):
        raise ValueError("stem path outside downloads directory")
    stems_dir = os.path.dirname(ref)
    return row, stems_map, stems_dir


# ─────────────────────────────────────────────────────────────────────────────
# Cache dir + POC meta assembly
# ─────────────────────────────────────────────────────────────────────────────
def _cache_dir(stems_dir, extraction_id):
    """Per-extraction cache for generated artifacts (metronome fallback, precount, meta)."""
    downloads_dir = os.path.abspath(ensure_valid_downloads_directory())
    safe = "".join(c for c in extraction_id if c.isalnum() or c in "._-") or "job"
    d = os.path.join(downloads_dir, ".poc_cache", safe)
    os.makedirs(d, exist_ok=True)
    return d


def _stems_signature(stems_map):
    """A cheap cache key: sorted (name, mtime, size) of the resolved stem files."""
    sig = []
    for name in sorted(stems_map):
        p = stems_map[name]
        try:
            st = os.stat(p)
            sig.append(f"{name}:{int(st.st_mtime)}:{st.st_size}")
        except OSError:
            sig.append(f"{name}:0:0")
    return "|".join(sig)


def _existing_metronomes(stems_dir):
    """Map POC resolution → on-disk WAV path for friend's pre-baked metronomes.

    Friend names the 1x file metronome_1.wav; POC calls that resolution "1".
    Returns {} if none present (→ fallback regeneration needed).
    """
    candidates = {"0.5": "metronome_0.5.wav", "1": "metronome_1.wav", "2": "metronome_2.wav"}
    found = {}
    for res, fn in candidates.items():
        p = os.path.join(stems_dir, fn)
        if os.path.exists(p):
            found[res] = p
    return found


# ── Metronome instrument (timbre) ────────────────────────────────────────────
# The default timbre ("click") reuses friend's pre-shipped metronome_*.wav as-is.
# Any OTHER instrument is rendered into <cache>/metro_<instrument>/metronome_*.wav
# from the beats, and the engine/precount/export are pointed there. Keeping the
# instrument WAVs in a per-instrument subdir means switching back to a previously
# used instrument is instant (no re-render) and never touches the on-disk originals.

def _read_meta(cache):
    p = os.path.join(cache, "meta.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _meta_instrument(meta):
    """The instrument id currently selected for this song (default 'click')."""
    from core.poc import click_kit
    return click_kit.normalize((meta or {}).get("metro_instrument") or "click")


def _instrument_metro_dir(cache, instrument):
    return os.path.join(cache, f"metro_{instrument}")


def _instrument_source_mtime(instrument):
    """Newest mtime among the instrument's source one-shot WAVs (samples dir). Used
    to invalidate cached renders when the samples are regenerated/refetched."""
    from core.poc import click_kit
    newest = 0.0
    for suffix in ("", "_accent"):
        p = os.path.join(click_kit.SAMPLES_DIR, f"{instrument}{suffix}.wav")
        try:
            newest = max(newest, os.path.getmtime(p))
        except OSError:
            pass
    return newest


def _ensure_instrument_metros(meta, drums, cache, instrument):
    """Make sure metronome_{0.5,1,2}.wav for `instrument` exist in the cache AND are
    not stale (older than the source sample WAVs); render them from the song beats
    otherwise. Returns {res: abs_path} or {} for the default 'click' (which uses the
    on-disk/fallback originals, not this dir)."""
    from core.poc import click_kit, metronome as M_metro
    instrument = click_kit.normalize(instrument)
    if instrument == "click":
        return {}
    if not (drums and os.path.exists(drums)) or not (meta and meta.get("beats")):
        raise ValueError("cannot render metronome instrument: no drums/beats")
    out_dir = _instrument_metro_dir(cache, instrument)
    os.makedirs(out_dir, exist_ok=True)
    want = {"0.5": "metronome_0.5.wav", "1": "metronome.wav", "2": "metronome_2.wav"}
    paths = {res: os.path.join(out_dir, fn) for res, fn in want.items()}
    # (re)render if any file is missing OR older than the source sample (stale render
    # from before the samples changed → would play the old timbre).
    src_mtime = _instrument_source_mtime(instrument)
    fresh = all(os.path.exists(p) for p in paths.values()) and \
        all(os.path.getmtime(p) >= src_mtime for p in paths.values())
    if not fresh:
        M_metro.render_all(meta["beats"], meta["positions"], drums, out_dir,
                           instrument=instrument)
    return paths


def _db_beats(row):
    """Pull (beats, positions) from the DB row if present, else (None, None)."""
    bt = row.get('beat_times')
    bp = row.get('beat_positions')
    if isinstance(bt, str):
        try:
            bt = json.loads(bt)
        except (json.JSONDecodeError, TypeError):
            bt = None
    if isinstance(bp, str):
        try:
            bp = json.loads(bp)
        except (json.JSONDecodeError, TypeError):
            bp = None
    if bt and bp and len(bt) == len(bp):
        return list(bt), list(bp)
    return None, None


def _db_chords(row):
    c = row.get('chords_data')
    if isinstance(c, str):
        try:
            c = json.loads(c)
        except (json.JSONDecodeError, TypeError):
            c = []
    return c or []


def _build_meta(extraction_id, row, stems_map, stems_dir, cache):
    """Assemble a POC-shaped meta dict and persist it to cache/meta.json.

    Reuses friend's analysis (beats from DB, chords/key/bpm) and on-disk metronome
    WAVs when present; falls back to core/poc to regenerate beats/snap/metronome.
    Always computes waveform peaks (POC timeline needs them, friend has no equivalent).
    """
    import soundfile as sf
    import statistics as _st
    from core.poc import waveform as M_wave

    def step(stage, pct):
        _set_prep(extraction_id, stage, pct)

    # ── beats + positions: prefer the DB, fall back to madmom ──
    step("Reading beats…", 10)
    beats, positions = _db_beats(row)

    drums = stems_map.get("drums")
    metro_map = _existing_metronomes(stems_dir)

    if not metro_map:
        # Fallback: regenerate groove-snapped metronomes into the cache dir.
        from core.poc import beats as M_beats, groove as M_groove, metronome as M_metro
        if not (drums and os.path.exists(drums)):
            raise ValueError("cannot regenerate metronome: no drums stem")
        if not beats:
            step("Detecting beats (madmom)…", 25)
            beats, positions = M_beats.detect(drums)
        step("Snapping to groove…", 55)
        beats, _snap_stats = M_groove.snap(beats, drums)
        step("Rendering metronome…", 70)
        # render_all writes into <cache>/stems/, returns {"0.5":"stems/..","1":"stems/metronome.wav",..}
        # soundfile.write can't create dirs → ensure the target exists first.
        os.makedirs(os.path.join(cache, "stems"), exist_ok=True)
        rel = M_metro.render_all(beats, positions, drums, os.path.join(cache, "stems"))
        metro_map = {}
        for res, relpath in rel.items():
            metro_map[res] = os.path.join(cache, relpath)
    elif not beats:
        # Have metronomes but no DB beats (rare) → detect for chord-grid use only.
        from core.poc import beats as M_beats, groove as M_groove
        if drums and os.path.exists(drums):
            step("Detecting beats (madmom)…", 30)
            beats, positions = M_beats.detect(drums)
            beats, _ = M_groove.snap(beats, drums)
        else:
            beats, positions = [], []

    # ── duration / median bpm / start ──
    step("Measuring…", 80)
    ref = drums or next((stems_map[n] for n in _REAL_STEMS if n in stems_map), None)
    dur = round(sf.info(ref).duration, 3) if ref else 0.0

    median_bpm = row.get('detected_bpm') or 0
    if not median_bpm and beats and len(beats) > 1:
        ibis = [beats[i + 1] - beats[i] for i in range(len(beats) - 1)]
        ibis = [x for x in ibis if 0 < x < 3]
        if ibis:
            median_bpm = round(60.0 / _st.median(ibis))
    median_bpm = int(median_bpm or 120)

    start_time = row.get('music_start_time') or 0.0
    start_index = 0
    try:
        from core.poc import startpoint as M_start
        if beats and positions:
            start_index, st_detected = M_start.detect_start(beats, positions)
            if not start_time:
                start_time = st_detected
    except Exception as e:
        logger.warning(f"[poc-mixer] startpoint detection failed: {e}")

    # ── key (from DB detected_key like "B major") ──
    key = row.get('detected_key') or ""
    key_tonic, key_mode = "", ""
    if key:
        parts = str(key).split()
        if parts:
            key_tonic = parts[0]
        if len(parts) > 1:
            key_mode = parts[1].lower()

    # ── waveforms for every served stem + the 1x metronome ──
    step("Building waveforms…", 88)
    served = {n: stems_map[n] for n in _REAL_STEMS if n in stems_map and os.path.exists(stems_map[n])}
    waveforms = {}
    for name, p in served.items():
        try:
            waveforms[name] = M_wave.peaks(p)
        except Exception as e:
            logger.warning(f"[poc-mixer] waveform failed for {name}: {e}")
    if "1" in metro_map and os.path.exists(metro_map["1"]):
        try:
            waveforms["metronome"] = M_wave.peaks(metro_map["1"])
        except Exception as e:
            logger.warning(f"[poc-mixer] waveform failed for metronome: {e}")

    # stems map the engine reads (names → relative-ish marker; the engine only checks truthiness)
    stems_meta = {name: f"stems/{name}" for name in served}
    if metro_map:
        stems_meta["metronome"] = "stems/metronome"

    # metronome_resolutions: the keys drive which buffers the engine fetches
    metronome_resolutions = {res: f"stems/metronome_{res}" for res in metro_map}

    # Preserve a previously-chosen metronome instrument across re-prepares. We're here
    # because the stems signature changed (beats may differ), so any previously-rendered
    # per-instrument WAVs are now stale → purge them; they re-render lazily on demand.
    prev_meta = _read_meta(cache)
    metro_instrument = _meta_instrument(prev_meta)
    import glob as _glob
    for _d in _glob.glob(os.path.join(cache, "metro_*")):
        if os.path.isdir(_d):
            shutil.rmtree(_d, ignore_errors=True)

    meta = {
        "job": extraction_id,
        "extraction_id": extraction_id,
        "duration": dur,
        "sr": 44100,
        "beats": beats or [],
        "positions": positions or [],
        "stems": stems_meta,
        "metronome_resolutions": metronome_resolutions,
        "metro_instrument": metro_instrument,    # selected timbre (see core.poc.click_kit)
        "start_index": start_index,
        "start_time": round(float(start_time or 0.0), 3),
        "median_bpm": median_bpm,
        "chords": _db_chords(row),
        "key": key,
        "key_tonic": key_tonic,
        "key_mode": key_mode,
        "key_confidence": row.get('analysis_confidence') or 0.0,
        "waveforms": waveforms,
        # cache bookkeeping (not read by the engine)
        "_sig": _stems_signature(stems_map),
    }
    with open(os.path.join(cache, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    return meta


def _prepare_worker(extraction_id, user_id):
    try:
        _set_prep(extraction_id, "starting", 0)
        row, stems_map, stems_dir = _resolve_context(extraction_id, user_id)
        cache = _cache_dir(stems_dir, extraction_id)
        # Reuse cached meta if the stem signature is unchanged.
        meta_path = os.path.join(cache, "meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    cached = json.load(f)
                if cached.get("_sig") == _stems_signature(stems_map):
                    _set_prep(extraction_id, "done", 100, done=True)
                    return
            except (json.JSONDecodeError, OSError):
                pass
        _build_meta(extraction_id, row, stems_map, stems_dir, cache)
        _set_prep(extraction_id, "done", 100, done=True)
    except ValueError as e:
        _set_prep(extraction_id, "error", 0, done=True, error=str(e))
    except Exception as e:
        traceback.print_exc()
        _set_prep(extraction_id, "error", 0, done=True, error=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────
@poc_mixer_bp.route('/poc-mixer/prepare/<path:extraction_id>', methods=['POST'])
@api_login_required
def prepare(extraction_id):
    """Kick off (or reuse) preparation of the POC artifacts for an extraction."""
    with _PREP_LOCK:
        cur = _PREP.get(extraction_id)
    if cur and not cur.get("done"):
        return jsonify({"job": extraction_id, "cached": False})  # already running
    _set_prep(extraction_id, "starting", 0)
    # current_user is a request-context proxy; resolve the id HERE and hand the
    # plain value to the worker thread (the proxy is unbound off-request).
    uid = current_user.id
    threading.Thread(target=_prepare_worker, args=(extraction_id, uid), daemon=True).start()
    return jsonify({"job": extraction_id, "cached": False})


@poc_mixer_bp.route('/poc-mixer/progress/<path:extraction_id>', methods=['GET'])
@api_login_required
def progress(extraction_id):
    with _PREP_LOCK:
        p = _PREP.get(extraction_id)
    if not p:
        return jsonify({"stage": "unknown", "pct": 0, "done": False, "error": None})
    return jsonify(p)


@poc_mixer_bp.route('/poc-mixer/meta/<path:extraction_id>', methods=['GET'])
@api_login_required
def meta(extraction_id):
    try:
        _row, stems_map, stems_dir = _resolve_context(extraction_id, current_user.id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    cache = _cache_dir(stems_dir, extraction_id)
    meta_path = os.path.join(cache, "meta.json")
    if not os.path.exists(meta_path):
        return jsonify({"error": "not prepared"}), 404
    with open(meta_path, encoding="utf-8") as f:
        return jsonify(json.load(f))


def _resolve_stem_file(extraction_id, stem, user_id):
    """Map a POC stem id to an on-disk file path (real stem, metronome, or precount)."""
    _row, stems_map, stems_dir = _resolve_context(extraction_id, user_id)
    cache = _cache_dir(stems_dir, extraction_id)

    # metronome variants
    if stem == "metronome" or stem.startswith("metronome_"):
        res = "1" if stem == "metronome" else stem.split("metronome_", 1)[1]
        # baked variants (count-in OR stop-cutoff) live only in the cache. These are
        # already rendered with the selected instrument by detect_intro/export, so
        # they need no instrument redirection here.
        if res.startswith("precount") or res.startswith("stop"):
            # e.g. metronome_precount_1 / metronome_stop_0.5 → cache/stems
            fn = f"{stem}.wav"
            p = os.path.join(cache, "stems", fn)
            return p if os.path.exists(p) else None
        # A non-default instrument? Serve its rendered WAV from the per-instrument
        # cache dir (rendering it on demand if missing). Default 'click' falls
        # through to the on-disk / fallback originals below.
        meta = _read_meta(cache)
        instrument = _meta_instrument(meta)
        if instrument != "click":
            try:
                paths = _ensure_instrument_metros(meta, stems_map.get("drums"), cache, instrument)
                p = paths.get(res)
                if p and os.path.exists(p):
                    return p
            except ValueError:
                pass   # fall back to the default click below
        # on-disk friend metronome first (1x is metronome_1.wav)
        disk = os.path.join(stems_dir, f"metronome_{res}.wav")
        if os.path.exists(disk):
            return disk
        # fallback cache (regenerated): "1" written as metronome.wav
        cfn = "metronome.wav" if res == "1" else f"metronome_{res}.wav"
        cpath = os.path.join(cache, "stems", cfn)
        return cpath if os.path.exists(cpath) else None

    # a real stem
    p = stems_map.get(stem)
    if p and os.path.exists(p) and _safe_in_downloads(p):
        return p
    return None


@poc_mixer_bp.route('/poc-mixer/audio/<path:extraction_id>/<stem>', methods=['GET', 'HEAD'])
@api_login_required
def audio(extraction_id, stem):
    import mimetypes
    try:
        path = _resolve_stem_file(extraction_id, stem, current_user.id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    if not path or not os.path.exists(path):
        return jsonify({"error": f"not found: {stem}"}), 404
    if request.method == 'HEAD':
        return '', 200
    directory = os.path.dirname(os.path.abspath(path))
    filename = os.path.basename(path)
    mt, _ = mimetypes.guess_type(filename)
    resp = send_from_directory(directory, filename, mimetype=mt or 'audio/wav', conditional=True)
    # real stems are immutable; metronome may be regenerated → don't hard-cache
    if stem == "metronome" or stem.startswith("metronome_"):
        resp.headers['Cache-Control'] = 'no-store'
    else:
        resp.headers['Cache-Control'] = 'public, max-age=604800, immutable'
    return resp


@poc_mixer_bp.route('/poc-mixer/detect_intro/<path:extraction_id>', methods=['POST'])
@api_login_required
def detect_intro(extraction_id):
    """Bake a count-in into the metronome WAVs (port of the POC api_detect_intro).

    Writes metronome_precount_{res}.wav into the cache and records the precount plan
    in the cached meta.json.
    """
    from core.poc import precount as M_precount
    try:
        _row, stems_map, stems_dir = _resolve_context(extraction_id, current_user.id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    cache = _cache_dir(stems_dir, extraction_id)
    meta_path = os.path.join(cache, "meta.json")
    if not os.path.exists(meta_path):
        return jsonify({"error": "not prepared"}), 404
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    body = request.get_json(silent=True) or {}
    start_time = body.get("start_time")
    count = body.get("precount_count", M_precount.PRECOUNT_COUNT)
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = M_precount.PRECOUNT_COUNT
    count = max(1, min(16, count))

    # stop_time (seconds, original timeline): metronome click stops after this
    # point; None / missing = click runs to the end. Sent on the same body as a
    # re-bake so moving the End flag (like the Start flag) re-renders the WAVs.
    stop_time = body.get("stop_time", None)
    if stop_time is not None:
        try:
            stop_time = float(stop_time)
        except (TypeError, ValueError):
            stop_time = None

    drums = stems_map.get("drums")
    if not (drums and os.path.exists(drums)):
        return jsonify({"error": "no drums stem for precount"}), 400

    try:
        out_stems = os.path.join(cache, "stems")
        os.makedirs(out_stems, exist_ok=True)
        plan = M_precount.render_precount(
            meta["beats"], meta["positions"], drums, out_stems,
            start_time=start_time, precount_count=count, stop_time=stop_time,
            instrument=_meta_instrument(meta),   # count-in uses the selected timbre
        )
        meta["start_index"] = plan["start_index"]
        meta["start_time"] = plan["start_time"]
        meta["precount"] = {
            "bpm": plan["precount_bpm"],
            "ibi": plan["precount_ibi"],
            "count": plan["precount_count"],
            "times": plan["precount_times"],
            "lead_silence": plan["lead_silence"],
            "stop_time": plan["stop_time"],
            "files": plan["files"],
            "stop_files": plan.get("stop_files") or {},
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        return jsonify(plan)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@poc_mixer_bp.route('/poc-mixer/metro_instruments', methods=['GET'])
@api_login_required
def metro_instruments():
    """Catalogue of available metronome timbres: [{id, label}, …] (click first)."""
    from core.poc import click_kit
    items = [{"id": k, "label": v} for k, v in click_kit.INSTRUMENTS.items()]
    return jsonify({"instruments": items, "default": click_kit.DEFAULT_INSTRUMENT})


@poc_mixer_bp.route('/poc-mixer/set_metro_instrument/<path:extraction_id>', methods=['POST'])
@api_login_required
def set_metro_instrument(extraction_id):
    """Switch the metronome timbre for a song.

    Renders the 3 resolution WAVs for the chosen instrument into the cache (no-op
    for 'click', which reuses the originals), records it in meta.json, and—because
    any baked count-in/stop WAVs were rendered with the OLD timbre—re-bakes them
    with the new instrument when a precount/stop is currently active, so the
    count-in and the live metronome always match. Returns the (possibly updated)
    precount block so the client can reload its baked buffers.
    """
    from core.poc import click_kit, precount as M_precount
    try:
        _row, stems_map, stems_dir = _resolve_context(extraction_id, current_user.id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    cache = _cache_dir(stems_dir, extraction_id)
    meta_path = os.path.join(cache, "meta.json")
    meta = _read_meta(cache)
    if not meta:
        return jsonify({"error": "not prepared"}), 404

    body = request.get_json(silent=True) or {}
    instrument = click_kit.normalize(body.get("instrument"))
    drums = stems_map.get("drums")

    try:
        # 1) render the base resolution WAVs for the new instrument (no-op for click)
        _ensure_instrument_metros(meta, drums, cache, instrument)
        meta["metro_instrument"] = instrument

        # 2) re-bake any active count-in/stop so it uses the new timbre. The previous
        # plan tells us the markers; we re-render with the same start/count/stop.
        precount = meta.get("precount")
        had_baked = bool(precount and (precount.get("files") or precount.get("stop_files")))
        if had_baked and drums and os.path.exists(drums) and meta.get("beats"):
            out_stems = os.path.join(cache, "stems")
            os.makedirs(out_stems, exist_ok=True)
            plan = M_precount.render_precount(
                meta["beats"], meta["positions"], drums, out_stems,
                start_time=meta.get("start_time"),
                precount_count=int(precount.get("count") or M_precount.PRECOUNT_COUNT),
                stop_time=precount.get("stop_time"),
                instrument=instrument,
            )
            meta["start_index"] = plan["start_index"]
            meta["start_time"] = plan["start_time"]
            meta["precount"] = {
                "bpm": plan["precount_bpm"], "ibi": plan["precount_ibi"],
                "count": plan["precount_count"], "times": plan["precount_times"],
                "lead_silence": plan["lead_silence"], "stop_time": plan["stop_time"],
                "files": plan["files"], "stop_files": plan.get("stop_files") or {},
            }

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        return jsonify({
            "instrument": instrument,
            "metronome_resolutions": meta.get("metronome_resolutions"),
            "precount": meta.get("precount"),
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def _safe_filename(name, default="mix"):
    """A filesystem-safe base name for the exported file."""
    base = "".join(c for c in (name or "") if c.isalnum() or c in " ._-").strip()
    return (base or default)[:80]


@poc_mixer_bp.route('/poc-mixer/export/<path:extraction_id>', methods=['POST'])
@api_login_required
def export(extraction_id):
    """Render the current mix (stems + optional baked metronome) to a file.

    Body JSON:
      tracks: {stem: {vol, pan, muted, solo}}   — per-stem mixer state
      include_metronome: bool
      metro_resolution: "0.5" | "1" | "2"
      precount_beats: 0|2|4|8                    — count-in beats HEARD (0 = none)
      stop_time: float | null                    — metronome END (original timeline)
      start_time: float | null                   — metronome START / count-in target
      metro_gain: float                          — metronome track volume
      format: "mp3" | "wav"
      title: optional download base name

    The metronome is baked ON THE FLY from start_time/stop_time/precount_beats into a
    temp dir, so the export always matches the current markers regardless of whether
    a Detect-Intro bake ran before. Tempo/pitch are NOT applied (original tempo).
    """
    from core.poc import export_mix as M_export
    from core.poc import precount as M_precount
    try:
        _row, stems_map, stems_dir = _resolve_context(extraction_id, current_user.id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    cache = _cache_dir(stems_dir, extraction_id)
    meta_path = os.path.join(cache, "meta.json")
    if not os.path.exists(meta_path):
        return jsonify({"error": "not prepared"}), 404
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    body = request.get_json(silent=True) or {}
    raw_tracks = body.get("tracks") or {}
    include_metro = bool(body.get("include_metronome"))
    res = str(body.get("metro_resolution") or "1")
    if res not in ("0.5", "1", "2"):
        res = "1"
    try:
        precount_beats = int(body.get("precount_beats") or 0)
    except (TypeError, ValueError):
        precount_beats = 0
    try:
        metro_gain = float(body.get("metro_gain", 1.0))
    except (TypeError, ValueError):
        metro_gain = 1.0

    def _opt_float(v):
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    stop_time = _opt_float(body.get("stop_time"))
    start_time = _opt_float(body.get("start_time"))
    fmt = "wav" if str(body.get("format")).lower() == "wav" else "mp3"

    # sanitize tracks: keep only known real stems with numeric controls
    tracks = {}
    for name in _REAL_STEMS:
        t = raw_tracks.get(name)
        if not isinstance(t, dict):
            continue
        tracks[name] = {
            "vol": float(t.get("vol", 1.0)),
            "pan": float(t.get("pan", 0.0)),
            "muted": bool(t.get("muted")),
            "solo": bool(t.get("solo")),
        }

    import tempfile
    out_dir = tempfile.mkdtemp(prefix="poc_export_")
    out_base = os.path.join(out_dir, _safe_filename(body.get("title")))

    # ── bake the metronome on the fly so it mirrors the mixer EXACTLY: a click that
    # runs from `start_time` to `stop_time`, with an optional count-in in front. No
    # "from_start"/"whole song" mode — the export reflects the markers, full stop. ──
    #   precount_beats > 0 → count-in heard before the song (output opens with it)
    #   the song click is always [start_time .. stop_time]; the count-in is immune.
    # The whole song is always kept (intro included) so the export matches the
    # timeline the user sees; the click simply starts/stops at the markers.
    metro_wav = None
    lead_silence = 0.0
    first_offset = 0.0
    lead_pad = 0.0
    can_bake = include_metro and stems_map.get("drums") \
        and os.path.exists(stems_map["drums"]) and meta.get("beats")
    try:
        if include_metro and can_bake:
            drums = stems_map["drums"]
            bake_dir = os.path.join(out_dir, "metro")
            os.makedirs(bake_dir, exist_ok=True)
            heard = precount_beats if precount_beats > 0 else 0
            plan = M_precount.render_precount(
                meta["beats"], meta["positions"], drums, bake_dir,
                start_time=start_time, precount_count=max(heard, 1),
                stop_time=stop_time, instrument=_meta_instrument(meta),
            )
            eff_start = float(plan["start_time"])
            ibi = float(plan["precount_ibi"])
            if heard > 0:
                # count-in heard: the precount track has the count-in + the song click
                # from start_time to stop_time. It's prefixed by lead_silence.
                metro_wav = os.path.join(bake_dir, f"metronome_precount_{res}.wav")
                lead_silence = float(plan["lead_silence"])
                gap = eff_start - heard * ibi   # song-time where the heard count-in begins
                if gap < 0:
                    # intro too short → insert that much silence in front (matches the
                    # timeline's visible lead pad); stems pushed right, count-in in it.
                    lead_pad = -gap
                    first_offset = 0.0
                else:
                    # enough room: the count-in sits in the intro, no inserted silence.
                    first_offset = gap
            else:
                # no count-in: full-song click cut at stop_time (intro included, starts
                # at t=0). first_offset stays 0 so the whole song is exported.
                stop_path = os.path.join(bake_dir, f"metronome_stop_{res}.wav")
                if stop_time is not None and os.path.exists(stop_path):
                    metro_wav = stop_path
                else:
                    metro_wav = _resolve_stem_file(
                        extraction_id, "metronome" if res == "1" else f"metronome_{res}",
                        current_user.id)
        elif include_metro:
            # no drums / no beats → cannot bake. Use the on-disk full-song metronome
            # as-is (no count-in / cutoff possible without a bake).
            metro_wav = _resolve_stem_file(
                extraction_id, "metronome" if res == "1" else f"metronome_{res}",
                current_user.id)

        written = M_export.render_mix(
            stems_map, tracks, out_base,
            metro_wav=metro_wav, lead_silence=lead_silence, first_offset=first_offset,
            metro_gain=metro_gain, lead_pad=lead_pad,
            sr=int(meta.get("sr") or 44100), fmt=fmt,
        )
    except ValueError as e:
        shutil.rmtree(out_dir, ignore_errors=True)
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        shutil.rmtree(out_dir, ignore_errors=True)
        return jsonify({"error": str(e)}), 500

    dl_name = _safe_filename(body.get("title")) + os.path.splitext(written)[1]

    # Guaranteed-findable fallback: also drop a copy in the user's Downloads folder,
    # so the file is always somewhere obvious even if the browser download misbehaves.
    saved_to = None
    try:
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.isdir(downloads):
            target = os.path.join(downloads, dl_name)
            # avoid clobbering: add " (n)" if it already exists
            stem, ext = os.path.splitext(dl_name)
            i = 1
            while os.path.exists(target):
                target = os.path.join(downloads, f"{stem} ({i}){ext}")
                i += 1
            shutil.copy2(written, target)
            saved_to = target
    except OSError as e:
        logger.warning(f"[poc-mixer] could not copy export to Downloads: {e}")

    # Register the rendered file for a real GET navigation download (WebView2-native).
    _gc_exports()
    token = _register_export(written, dl_name)
    return jsonify({
        "download_url": f"/poc-mixer/download/{token}/{dl_name}",
        "filename": dl_name,
        "saved_to": saved_to,
    })


@poc_mixer_bp.route('/poc-mixer/download/<token>/<path:filename>', methods=['GET'])
@api_login_required
def download_export(token, filename):
    """Stream a previously-rendered export as a real attachment download.

    Triggered by a genuine top-level navigation (not a blob: anchor), which is what
    WebView2's download machinery actually handles. The temp dir is cleaned once the
    response is sent; stale exports are GC'd by TTL.
    """
    _gc_exports()
    with _EXPORTS_LOCK:
        entry = _EXPORTS.get(token)
    if not entry or not os.path.exists(entry["path"]):
        return jsonify({"error": "export expired or not found"}), 404

    resp = send_file(entry["path"], as_attachment=True, download_name=entry["name"])

    @resp.call_on_close
    def _cleanup():
        with _EXPORTS_LOCK:
            e = _EXPORTS.pop(token, None)
        if e:
            shutil.rmtree(os.path.dirname(e["path"]), ignore_errors=True)

    return resp
