"""
Shared extensions and objects used across all blueprints.

This module holds singleton instances (socketio, login_manager, etc.)
and the UserSessionManager class so that every blueprint can import them
without circular dependencies.
"""

import os
import uuid
from functools import wraps

from flask import session, jsonify, redirect, url_for, flash
from flask_socketio import SocketIO
from flask_login import LoginManager, current_user

from core.logging_config import get_logger, get_processing_logger, log_with_context
from core.stems_extractor import StemsExtractor, ExtractionItem, ExtractionStatus
from core.config import get_setting
from core.downloads_db import (
    find_global_extraction as db_find_global_extraction,
    add_user_extraction_access as db_add_user_extraction_access,
    mark_extraction_complete as db_mark_extraction_complete,
    list_extractions_for as db_list_extractions,
    clear_extraction_in_progress as db_clear_extraction_in_progress,
    get_user_download_id_by_video_id as db_get_user_download_id,
)

logger = get_logger(__name__)
processing_logger = get_processing_logger()

# ── Singleton instances (initialized in create_app) ──────────────────

socketio = SocketIO()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'error'

# ── Utility functions ────────────────────────────────────────────────

def get_model_display_name(model_key):
    """Convert model key to display name."""
    from core.config import STEM_MODELS
    if model_key in STEM_MODELS:
        return STEM_MODELS[model_key]["name"]
    return model_key


def is_mobile_user_agent(user_agent: str) -> bool:
    """Simple heuristic to detect mobile browsers from the user-agent string."""
    if not user_agent:
        return False

    ua = user_agent.lower()

    mobile_indicators = (
        "iphone", "android", "ipad", "ipod", "mobile",
        "blackberry", "opera mini", "opera mobi", "windows phone",
        "webos", "fennec", "kindle", "silk", "palm", "phone",
    )

    if any(indicator in ua for indicator in mobile_indicators):
        if "windows" in ua and "phone" not in ua:
            return False
        if "macintosh" in ua and "mobile" not in ua and "ipad" not in ua:
            return False
        return True

    return False


# ── Decorators ───────────────────────────────────────────────────────

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('pages.index'))
        return f(*args, **kwargs)
    return decorated_function


def api_admin_required(f):
    """Admin required decorator for API endpoints - returns JSON error instead of redirect."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({
                'error': 'Forbidden',
                'message': 'Admin access required'
            }), 403
        return f(*args, **kwargs)
    return decorated_function


def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({
                'error': 'Unauthorized',
                'message': 'Authentication required',
                'redirect': url_for('pages.index')
            }), 401
        return f(*args, **kwargs)
    return decorated_function


# ── UserSessionManager ───────────────────────────────────────────────

class UserSessionManager:
    """Stable per-user (or per-anonymous) managers keyed by a deterministic id."""

    def __init__(self):
        self.stems_extractors: dict[str, StemsExtractor] = {}

    # ---------- internal helper ----------
    def _key(self) -> str:
        """Return stable key: 'user_<id>' or consistent anonymous key."""
        from flask import has_request_context
        if has_request_context():
            if current_user.is_authenticated:
                return f"user_{current_user.id}"
            if 'anon_key' not in session:
                session['anon_key'] = str(uuid.uuid4())
            return session['anon_key']
        return "background_fallback"

    def clear_extraction_from_all_sessions(self, video_id: str):
        """Remove an extraction from all active user session extractors."""
        print(f"[CLEANUP] Clearing extraction for video_id={video_id} from {len(self.stems_extractors)} active sessions")
        for key, se in self.stems_extractors.items():
            for collection_name in ['queued_extractions', 'active_extractions', 'failed_extractions', 'completed_extractions']:
                collection = getattr(se, collection_name, {})
                keys_to_remove = [k for k, v in collection.items() if hasattr(v, 'video_id') and v.video_id == video_id]
                for item_key in keys_to_remove:
                    del collection[item_key]
                    print(f"[CLEANUP] Removed {item_key} from {collection_name} in session {key}")

    # ---------- stems extractor ----------
    def get_stems_extractor(self) -> StemsExtractor:
        key = self._key()
        if key not in self.stems_extractors:
            se = StemsExtractor()
            room_key = key
            user_id = current_user.id if current_user and current_user.is_authenticated else None
            se.on_extraction_progress = (
                lambda item_id, progress, status_msg=None, video_id=None, title=None:
                    self._emit_extraction_progress_with_room(item_id, progress, status_msg, room_key, user_id, video_id, title)
            )
            se.on_extraction_complete = (
                lambda item_id, title=None, video_id=None, item=None:
                    self._emit_extraction_complete_with_room(item_id, title, video_id, room_key, user_id, item)
            )
            se.on_extraction_error = (
                lambda item_id, error, video_id=None:
                    self._emit_extraction_error_with_room(item_id, error, room_key, video_id, user_id)
            )
            self.stems_extractors[key] = se
        return self.stems_extractors[key]

    # ---------- safe emitters with room keys ----------
    def _emit_extraction_progress_with_room(self, item_id, progress, status_msg=None, room_key=None, user_id=None, video_id=None, title=None):
        logger.info(f"[EXTRACTION PROGRESS] Emitting progress for extraction_id={item_id}, progress={progress:.1f}%")
        logger.debug(f"[EXTRACTION PROGRESS] Received data: video_id={video_id}, title={title}, user_id={user_id}")

        download_id = None
        if user_id and video_id is not None and video_id != "":
            try:
                download_id = db_get_user_download_id(user_id, video_id)
                logger.debug(f"[EXTRACTION PROGRESS] Found download_id {download_id} for user {user_id}, video {video_id}")
            except Exception as e:
                logger.warning(f"[EXTRACTION PROGRESS] Could not get download_id for user {user_id}, video {video_id}: {e}")
        else:
            logger.debug(f"[EXTRACTION PROGRESS] Skipping download_id lookup: user_id={user_id}, video_id={video_id}")

        emission_data = {
            'extraction_id': item_id,
            'video_id': video_id,
            'download_id': download_id,
            'progress': progress,
            'status_message': status_msg or "Extracting stems..."
        }

        logger.info(f"[EXTRACTION PROGRESS] Emitting WebSocket event: {emission_data}")
        socketio.emit('extraction_progress', emission_data, room=room_key or self._key())

    def _emit_extraction_error_with_room(self, item_id, error, room_key=None, video_id=None, user_id=None):
        logger.error(f"Extraction error: item_id={item_id}, error={error}, video_id={video_id}, user_id={user_id}")
        socketio.emit('extraction_error', {'extraction_id': item_id, 'error_message': error}, room=room_key or self._key())

        if video_id:
            with log_with_context(logger, video_id=video_id, user_id=user_id):
                logger.info("Clearing extracting flag for failed extraction (global and user-specific)")
            try:
                db_clear_extraction_in_progress(video_id, user_id)
                logger.debug("Successfully cleared extracting flags")
            except Exception as db_error:
                logger.error(f"Error clearing extracting flag: {db_error}")

    def _emit_extraction_complete_with_room(self, item_id, title=None, video_id=None, room_key=None, user_id=None, item=None):
        """Handle extraction completion - always emits extraction_complete event."""
        with log_with_context(processing_logger, user_id=user_id, video_id=video_id):
            processing_logger.info(f"Extraction finished: {title}")

        logger.debug(f"Extraction complete for {item_id}: video_id='{video_id}', user_id={user_id}")

        if user_id and video_id and item:
            with log_with_context(logger, user_id=user_id, video_id=video_id):
                logger.debug("Processing extraction completion context")
            with log_with_context(processing_logger, video_id=item.video_id):
                processing_logger.debug(f"Extraction details: status={item.status.value}, model={item.model_name}")
            print(f"[CALLBACK DEBUG] Stems paths: {item.output_paths}")
            print(f"[CALLBACK DEBUG] Zip path: {item.zip_path}")

            if item and item.video_id:
                print(f"[CALLBACK DEBUG] Persisting extraction to database...")
                try:
                    db_mark_extraction_complete(item.video_id, {
                        "model_name": item.model_name,
                        "stems_paths": item.output_paths or {},
                        "zip_path": item.zip_path or ""
                    })
                    print(f"[CALLBACK DEBUG] Global download marked as extracted")

                    global_download = db_find_global_extraction(item.video_id, item.model_name)
                    if global_download:
                        db_add_user_extraction_access(user_id, global_download)
                        print(f"[CALLBACK DEBUG] User access granted to extraction")

                        user_extractions = db_list_extractions(user_id)
                        print(f"[CALLBACK DEBUG] User now has {len(user_extractions)} extractions in database")
                    else:
                        print(f"[CALLBACK DEBUG] ERROR: Could not find global extraction after marking complete")
                except Exception as e:
                    print(f"[CALLBACK DEBUG] ERROR: Failed to persist extraction to database: {e}")
                    import traceback
                    traceback.print_exc()

                # AUTO-DETECT BPM/KEY/CHORDS if not already done
                _room = room_key or self._key()
                try:
                    audio_path = item.audio_path if hasattr(item, 'audio_path') else None
                    if audio_path and os.path.exists(audio_path):
                        from core.db.connection import _conn
                        with _conn() as conn:
                            row = conn.execute("SELECT detected_bpm FROM global_downloads WHERE video_id=?", (video_id,)).fetchone()
                        if not row or not row['detected_bpm']:
                            logger.info(f"[ANALYSIS] Running BPM/key/chord detection for: {audio_path}")
                            socketio.emit('extraction_progress', {
                                'extraction_id': item_id, 'progress': 49,
                                'message': 'Analyzing BPM & key...', 'video_id': video_id
                            }, room=_room)

                            # BPM & key
                            from core.audio_analysis import analyze_audio
                            analysis = analyze_audio(audio_path)
                            _bpm = analysis.get('bpm')
                            _key = analysis.get('key')
                            _confidence = analysis.get('confidence')
                            logger.info(f"[ANALYSIS] BPM={_bpm}, Key={_key}")

                            socketio.emit('extraction_progress', {
                                'extraction_id': item_id, 'progress': 52,
                                'message': 'Detecting chords...', 'video_id': video_id
                            }, room=_room)

                            # Chords
                            _chords = None
                            _chord_offset = 0.0
                            try:
                                from core.chord_detector import analyze_audio_file as _analyze_chords
                                _result = _analyze_chords(audio_path, bpm=_bpm)
                                if len(_result) == 4:
                                    _chords, _chord_offset, _, _ = _result
                                else:
                                    _chords, _chord_offset, _ = _result
                                logger.info(f"[ANALYSIS] Chords: {len(_chords) if _chords else 0} segments")
                            except Exception as ce:
                                logger.warning(f"[ANALYSIS] Chord detection error: {ce}")

                            # Structure
                            _structure = None
                            try:
                                from core.msaf_structure_detector import detect_song_structure_msaf
                                _structure = detect_song_structure_msaf(audio_path)
                            except Exception as se:
                                logger.warning(f"[ANALYSIS] Structure detection error: {se}")

                            # Music start
                            _music_start = 0.0
                            try:
                                from core.music_start_detector import detect_music_start
                                _music_start = detect_music_start(audio_path)
                            except Exception:
                                pass

                            # Save to DB
                            import json as _json
                            from core.downloads_db import update_download_analysis
                            update_download_analysis(
                                video_id, _bpm, _key, _confidence,
                                chords_data=_json.dumps(_chords) if _chords else None,
                                beat_offset=_chord_offset,
                                structure_data=_structure,
                                music_start_time=_music_start,
                            )
                            logger.info(f"[ANALYSIS] BPM/key/chords/structure saved for {video_id}")

                            socketio.emit('extraction_progress', {
                                'extraction_id': item_id, 'progress': 55,
                                'message': 'Analysis complete', 'video_id': video_id
                            }, room=_room)
                except Exception as analysis_error:
                    logger.warning(f"[ANALYSIS] Auto-analysis error (non-fatal): {analysis_error}")

                # AUTO-DETECT LYRICS after stems are ready (Whisper only — Musixmatch reserved for Regenerate)
                try:
                    vocals_path = item.output_paths.get('vocals') if item.output_paths else None
                    if vocals_path and os.path.exists(vocals_path):
                        logger.info(f"[LYRICS] Auto-detecting lyrics using vocals stem: {vocals_path}")

                        # Emit unified extraction progress at 48% for lyrics phase
                        socketio.emit('extraction_progress', {
                            'extraction_id': item_id,
                            'progress': 48,
                            'message': 'Transcribing lyrics...',
                            'video_id': video_id
                        }, room=_room)
                        socketio.emit('lyrics_progress', {
                            'extraction_id': item_id,
                            'step': 'auto_start',
                            'message': 'Transcribing lyrics...',
                            'video_id': video_id
                        }, room=_room)

                        from core.lyrics_detector import detect_lyrics_unified
                        from core.downloads_db import update_download_lyrics

                        model_size = get_setting('lyrics_model_size') or 'medium'
                        use_gpu = get_setting('use_gpu_for_extraction', False)

                        # Map lyrics steps to extraction progress (48-72% range)
                        _lyrics_step_progress = {
                            'metadata': 50, 'whisper': 55, 'whisper_done': 68,
                            'done': 72, 'failed': 72,
                        }

                        def _lyrics_progress_cb(step, msg):
                            # Emit lyrics_progress for karaoke-display.js compatibility
                            socketio.emit('lyrics_progress', {
                                'extraction_id': item_id, 'step': step,
                                'message': msg, 'video_id': video_id
                            }, room=_room)
                            # Emit extraction_progress mapped to 48-72% range
                            progress_val = _lyrics_step_progress.get(step, 55)
                            socketio.emit('extraction_progress', {
                                'extraction_id': item_id, 'progress': progress_val,
                                'message': msg, 'video_id': video_id
                            }, room=_room)

                        result = detect_lyrics_unified(
                            audio_path=vocals_path,
                            title=title,
                            model_size=model_size,
                            use_gpu=use_gpu,
                            force_whisper=True,
                            progress_callback=_lyrics_progress_cb
                        )

                        if result.get('lyrics'):
                            update_download_lyrics(video_id, result['lyrics'])
                            logger.info(f"[LYRICS] Auto-detected: {len(result['lyrics'])} segments ({result.get('source')})")
                            socketio.emit('lyrics_progress', {
                                'extraction_id': item_id,
                                'step': 'auto_complete',
                                'message': f"Lyrics ready: {len(result['lyrics'])} segments",
                                'video_id': video_id,
                                'source': result.get('source')
                            }, room=_room)
                        else:
                            logger.warning("[LYRICS] Auto-detection failed - no lyrics found")

                        # Ensure progress reaches 72% after lyrics phase
                        socketio.emit('extraction_progress', {
                            'extraction_id': item_id, 'progress': 72,
                            'message': 'Lyrics detection complete', 'video_id': video_id
                        }, room=_room)
                    else:
                        logger.debug("[LYRICS] No vocals stem available for auto-detection")
                        # Skip lyrics — jump progress to 72%
                        socketio.emit('extraction_progress', {
                            'extraction_id': item_id, 'progress': 72,
                            'message': 'No vocals for lyrics, skipping...', 'video_id': video_id
                        }, room=_room)
                except Exception as lyrics_error:
                    logger.warning(f"[LYRICS] Auto-detection error (non-fatal): {lyrics_error}")
                    socketio.emit('extraction_progress', {
                        'extraction_id': item_id, 'progress': 72,
                        'message': 'Lyrics detection skipped', 'video_id': video_id
                    }, room=_room)

                # AUTO-DETECT BEATS after stems are ready (madmom downbeat detection)
                try:
                    audio_path = item.audio_path if hasattr(item, 'audio_path') else None
                    if audio_path and os.path.exists(audio_path):
                        logger.info(f"[BEATS] Running madmom downbeat detection on {audio_path}")
                        socketio.emit('extraction_progress', {
                            'extraction_id': item_id,
                            'progress': 72,
                            'message': 'Detecting beats...',
                            'video_id': video_id
                        }, room=_room)

                        from core.madmom_chord_detector import MadmomChordDetector
                        from core.downloads_db import update_download_analysis

                        detector = MadmomChordDetector()

                        # Get existing BPM as hint from global_downloads
                        known_bpm = None
                        try:
                            from core.db.connection import _conn
                            with _conn() as conn:
                                row = conn.execute(
                                    "SELECT detected_bpm, detected_key, analysis_confidence, chords_data, structure_data, lyrics_data, music_start_time FROM global_downloads WHERE video_id=?",
                                    (video_id,)
                                ).fetchone()
                                if row:
                                    known_bpm = row['detected_bpm']
                                    existing_key = row['detected_key']
                                    existing_confidence = row['analysis_confidence']
                                    existing_chords = row['chords_data']
                                    existing_structure = row['structure_data']
                                    existing_lyrics = row['lyrics_data']
                                    existing_music_start = row['music_start_time'] or 0.0
                                else:
                                    existing_key = None
                                    existing_confidence = None
                                    existing_chords = None
                                    existing_structure = None
                                    existing_lyrics = None
                                    existing_music_start = 0.0
                        except Exception:
                            existing_key = None
                            existing_confidence = None
                            existing_chords = None
                            existing_structure = None
                            existing_lyrics = None
                            existing_music_start = 0.0

                        beat_offset, beats, beat_positions = detector._detect_beats(audio_path, known_bpm=known_bpm)
                        beat_times_list = [round(float(t), 4) for t in beats] if len(beats) > 0 else []

                        if beat_times_list:
                            # Preserve existing chords/structure/lyrics — parse JSON back since update_download_analysis re-serializes
                            import json as _json
                            _existing_structure = _json.loads(existing_structure) if existing_structure else None
                            _existing_lyrics = _json.loads(existing_lyrics) if existing_lyrics else None
                            update_download_analysis(
                                video_id,
                                detected_bpm=known_bpm,
                                detected_key=existing_key,
                                analysis_confidence=existing_confidence,
                                chords_data=existing_chords,
                                structure_data=_existing_structure,
                                lyrics_data=_existing_lyrics,
                                beat_offset=beat_offset,
                                beat_times=beat_times_list,
                                beat_positions=beat_positions,
                                music_start_time=existing_music_start
                            )
                            logger.info(f"[BEATS] Detected {len(beat_times_list)} beats, "
                                        f"{sum(1 for p in beat_positions if p == 1)} downbeats")
                        else:
                            logger.warning("[BEATS] No beats detected")

                        socketio.emit('extraction_progress', {
                            'extraction_id': item_id,
                            'progress': 97,
                            'message': 'Beat detection complete',
                            'video_id': video_id
                        }, room=_room)
                    else:
                        logger.debug("[BEATS] No audio file available for beat detection")
                        socketio.emit('extraction_progress', {
                            'extraction_id': item_id, 'progress': 97,
                            'message': 'No audio for beats, skipping...', 'video_id': video_id
                        }, room=_room)
                except Exception as beat_error:
                    logger.warning(f"[BEATS] Beat detection error (non-fatal): {beat_error}")
                    socketio.emit('extraction_progress', {
                        'extraction_id': item_id, 'progress': 97,
                        'message': 'Beat detection skipped', 'video_id': video_id
                    }, room=_room)
        else:
            print(f"[CALLBACK DEBUG] Missing user_id, video_id, or item data")

        # Mark extraction as COMPLETED now that all post-processing is done
        if item:
            item.status = ExtractionStatus.COMPLETED
            item.progress = 100.0

        # Emit final 100% progress
        socketio.emit('extraction_progress', {
            'extraction_id': item_id,
            'progress': 100,
            'message': 'Extraction completed',
            'video_id': video_id
        }, room=room_key or self._key())

        # Emit socket events (after database is updated)
        download_id = None
        if user_id and video_id:
            try:
                download_id = db_get_user_download_id(user_id, video_id)
                logger.debug(f"Found download_id {download_id} for user {user_id}, video {video_id}")
            except Exception as e:
                logger.warning(f"Could not get download_id for user {user_id}, video {video_id}: {e}")

        socketio.emit('extraction_complete', {
            'extraction_id': item_id,
            'video_id': video_id,
            'download_id': download_id,
            'title': title
        }, room=room_key or self._key())

        logger.debug("Broadcasting extraction completion to ALL connected clients")
        try:
            socketio.emit('extraction_completed_global', {
                'extraction_id': item_id,
                'video_id': video_id,
                'title': title
            }, namespace='/')
            logger.debug("Global broadcast sent to all clients")
        except Exception as e:
            logger.error(f"Error sending global broadcast: {e}")

        try:
            socketio.emit('extraction_refresh_needed', {
                'extraction_id': item_id,
                'video_id': video_id,
                'title': title,
                'message': 'New extraction available - please refresh'
            })
            logger.debug("Alternative global event sent")
        except Exception as e:
            logger.error(f"Error sending alternative event: {e}")


# ── Singleton instances ──────────────────────────────────────────────

user_session_manager = UserSessionManager()
