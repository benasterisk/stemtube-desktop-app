"""
Core page routes for StemTube Desktop Friend.
Desktop-only: no mobile redirect, no service worker, auto-login.
YouTube enabled in Friend edition.
"""

import os
import json
import time

from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required, current_user, login_user

from core.config import get_setting
from extensions import user_session_manager, get_model_display_name
from core.logging_config import get_logger
from edition import HAS_YOUTUBE, HAS_LICENSE

logger = get_logger(__name__)

pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/')
def index():
    """Desktop main page with auto-login for single-user mode."""
    # Auto-login: if not authenticated, log in as the desktop user
    if not current_user.is_authenticated:
        from core.auth_db import get_desktop_user
        from core.auth_models import User
        desktop_user = get_desktop_user()
        if desktop_user:
            login_user(User(desktop_user), remember=True)
        else:
            return "Desktop user not found. Please restart the application.", 500

    enable_youtube = HAS_YOUTUBE
    cache_buster = int(time.time())
    return render_template(
        'index.html',
        current_username=current_user.username,
        current_user=current_user,
        enable_youtube=enable_youtube,
        has_license=HAS_LICENSE,
        cache_buster=cache_buster
    )


@pages_bp.route('/mixer')
@login_required
def mixer():
    extraction_id = request.args.get('extraction_id', '')

    extraction_info = None
    se = user_session_manager.get_stems_extractor()
    extraction = se.get_extraction_status(extraction_id)

    if extraction:
        # In-memory ExtractionItem has stems but NOT analysis data (BPM, chords, etc.)
        # Fetch those from the database using the video_id
        db_data = {}
        video_id = getattr(extraction, 'video_id', '')
        if video_id:
            try:
                from core.db.connection import _conn
                with _conn() as conn:
                    row = conn.execute(
                        "SELECT detected_bpm, detected_key, analysis_confidence, chords_data, "
                        "beat_offset, beat_times, beat_positions, music_start_time, lyrics_data, structure_data, "
                        "metronome_offset_ms "
                        "FROM global_downloads WHERE video_id=?", (video_id,)
                    ).fetchone()
                    if row:
                        db_data = dict(row)
            except Exception as e:
                print(f"[MIXER] Error fetching DB analysis data: {e}")

        # Parse chords_data from JSON string if needed
        chords = db_data.get('chords_data')
        if chords and isinstance(chords, str):
            try:
                chords = json.loads(chords)
            except (json.JSONDecodeError, TypeError):
                pass

        # Parse other JSON fields
        beat_times = db_data.get('beat_times')
        if beat_times and isinstance(beat_times, str):
            try:
                beat_times = json.loads(beat_times)
            except (json.JSONDecodeError, TypeError):
                pass

        beat_positions = db_data.get('beat_positions')
        if beat_positions and isinstance(beat_positions, str):
            try:
                beat_positions = json.loads(beat_positions)
            except (json.JSONDecodeError, TypeError):
                pass

        lyrics_data = db_data.get('lyrics_data')
        if lyrics_data and isinstance(lyrics_data, str):
            try:
                lyrics_data = json.loads(lyrics_data)
            except (json.JSONDecodeError, TypeError):
                pass

        structure_data = db_data.get('structure_data')
        if structure_data and isinstance(structure_data, str):
            try:
                structure_data = json.loads(structure_data)
            except (json.JSONDecodeError, TypeError):
                pass

        extraction_info = {
            'extraction_id': extraction.extraction_id,
            'video_id': video_id,
            'status': extraction.status.value,
            'output_paths': extraction.output_paths or {},
            'audio_path': extraction.audio_path,
            'title': getattr(extraction, 'title', None),
            'extraction_model': get_model_display_name(getattr(extraction, 'model_name', 'htdemucs')),
            'detected_bpm': db_data.get('detected_bpm'),
            'detected_key': db_data.get('detected_key'),
            'analysis_confidence': db_data.get('analysis_confidence'),
            'chords_data': chords,
            'beat_offset': db_data.get('beat_offset', 0.0),
            'beat_times': beat_times,
            'beat_positions': beat_positions,
            'music_start_time': db_data.get('music_start_time', 0.0),
            'metronome_offset_ms': db_data.get('metronome_offset_ms', 0.0) or 0.0,
            'lyrics_data': lyrics_data,
            'structure_data': structure_data,
        }
    else:
        try:
            from core.downloads_db import list_extractions_for
            db_extractions = list_extractions_for(current_user.id)

            for db_extraction in db_extractions:
                db_id = f"download_{db_extraction['id']}"
                video_id = db_extraction.get('video_id', '')
                file_path = db_extraction.get('file_path', '')
                filename = os.path.basename(file_path).replace('.mp3', '') if file_path else ''

                matches = (
                    db_id == extraction_id or
                    video_id == extraction_id or
                    (filename and extraction_id.startswith(filename))
                )

                if matches:
                    output_paths = {}
                    stems_paths_json = db_extraction.get('stems_paths')
                    if stems_paths_json:
                        try:
                            output_paths = json.loads(stems_paths_json)
                        except (json.JSONDecodeError, TypeError):
                            pass

                    # Parse JSON string fields from DB
                    def _parse_json_field(val):
                        if val and isinstance(val, str):
                            try:
                                return json.loads(val)
                            except (json.JSONDecodeError, TypeError):
                                pass
                        return val

                    extraction_info = {
                        'extraction_id': extraction_id,
                        'video_id': video_id,
                        'status': 'completed',
                        'output_paths': output_paths,
                        'audio_path': db_extraction['file_path'],
                        'title': db_extraction.get('title'),
                        'extraction_model': get_model_display_name(db_extraction.get('extraction_model', 'htdemucs')),
                        'detected_bpm': db_extraction.get('detected_bpm'),
                        'detected_key': db_extraction.get('detected_key'),
                        'analysis_confidence': db_extraction.get('analysis_confidence'),
                        'chords_data': _parse_json_field(db_extraction.get('chords_data')),
                        'beat_offset': db_extraction.get('beat_offset', 0.0),
                        'beat_times': _parse_json_field(db_extraction.get('beat_times')),
                        'beat_positions': _parse_json_field(db_extraction.get('beat_positions')),
                        'music_start_time': db_extraction.get('music_start_time', 0.0),
                        'metronome_offset_ms': db_extraction.get('metronome_offset_ms', 0.0) or 0.0,
                        'lyrics_data': _parse_json_field(db_extraction.get('lyrics_data')),
                        'structure_data': _parse_json_field(db_extraction.get('structure_data')),
                    }
                    break
        except Exception as e:
            print(f"[MIXER] Error loading historical extraction data: {e}")

    cache_buster = int(time.time())
    return render_template('mixer.html', extraction_id=extraction_id, extraction_info=extraction_info, cache_buster=cache_buster)
