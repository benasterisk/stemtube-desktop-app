"""
Library API endpoints.

Historically this blueprint wrapped yt-dlp; the Standard desktop edition
no longer downloads from YouTube, so the routes here only expose the
user's uploaded library and its extraction status.
"""
import json

from flask import Blueprint, request, jsonify
from flask_login import current_user

from extensions import api_login_required, user_session_manager
from core.downloads_db import (
    list_for as db_list_downloads,
    list_extractions_for as db_list_extractions,
    find_any_global_extraction as db_find_any_global_extraction,
    delete_from as db_delete_download,
)
from core.logging_config import get_logger

logger = get_logger(__name__)

downloads_bp = Blueprint('downloads', __name__)


@downloads_bp.route('/api/downloads', methods=['GET'])
@api_login_required
def get_all_downloads():
    """List the user's library entries (uploads) with extraction progress."""
    try:
        se = user_session_manager.get_stems_extractor()
        active_extractions = se.get_all_extractions().get('active', [])
        queued_extractions = se.get_all_extractions().get('queued', [])

        results = []
        for db_item in db_list_downloads(current_user.id):
            if not db_item.get('file_path'):
                continue

            status = 'completed'
            progress = 100.0
            extraction_id = None

            for extraction in active_extractions + queued_extractions:
                if extraction.video_id == db_item['video_id']:
                    status = extraction.status.value if hasattr(extraction.status, 'value') else str(extraction.status)
                    progress = extraction.progress
                    extraction_id = extraction.extraction_id
                    break

            results.append({
                'download_id': db_item['id'],
                'global_download_id': db_item.get('global_download_id'),
                'video_id': db_item['video_id'],
                'title': db_item['title'],
                'thumbnail_url': db_item.get('thumbnail'),
                'type': db_item.get('media_type'),
                'quality': db_item.get('quality'),
                'status': status,
                'progress': progress,
                'extraction_id': extraction_id,
                'speed': '',
                'eta': '',
                'file_path': db_item['file_path'],
                'error_message': '',
                'created_at': db_item.get('created_at'),
                'detected_bpm': db_item.get('detected_bpm'),
                'detected_key': db_item.get('detected_key'),
                'analysis_confidence': db_item.get('analysis_confidence'),
                'extracted': db_item.get('extracted', False),
                'stems_paths': db_item.get('stems_paths'),
                'extraction_model': db_item.get('extraction_model'),
            })

        return jsonify(results)
    except Exception as e:
        logger.error(f"List downloads error: {e}")
        return jsonify({'error': str(e)}), 500


@downloads_bp.route('/api/downloads/<video_id>/extraction-status', methods=['GET'])
@api_login_required
def check_video_extraction_status(video_id):
    """Check whether any extraction exists for a given video_id."""
    try:
        global_extraction = db_find_any_global_extraction(video_id)
        if not global_extraction:
            return jsonify({'exists': False, 'user_has_access': False, 'status': 'not_extracted'})

        user_extractions = db_list_extractions(current_user.id)
        user_has_access = any(
            ext['video_id'] == video_id and ext.get('extracted') == 1
            for ext in user_extractions
        )

        response_data = {
            'exists': True,
            'user_has_access': user_has_access,
            'status': 'extracted' if user_has_access else 'extracted_no_access',
            'extraction_model': global_extraction.get('extraction_model'),
            'extracted_at': global_extraction.get('extracted_at'),
        }

        if user_has_access:
            stems_paths_json = global_extraction.get('stems_paths')
            if stems_paths_json:
                try:
                    response_data['stems_paths'] = (
                        json.loads(stems_paths_json) if isinstance(stems_paths_json, str) else stems_paths_json
                    )
                    response_data['stems_available'] = True
                except Exception:
                    response_data['stems_available'] = False
            else:
                response_data['stems_available'] = False

            if global_extraction.get('stems_zip_path'):
                response_data['zip_path'] = global_extraction.get('stems_zip_path')
            response_data['extraction_id'] = global_extraction.get('id')

        return jsonify(response_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@downloads_bp.route('/api/downloads/batch-extraction-status', methods=['POST'])
@api_login_required
def batch_check_extraction_status():
    """Check extraction status for multiple video_ids at once."""
    try:
        data = request.json or {}
        video_ids = data.get('video_ids', [])

        if not video_ids or not isinstance(video_ids, list):
            return jsonify({'error': 'video_ids array required'}), 400

        if len(video_ids) > 100:
            video_ids = video_ids[:100]

        user_extractions = db_list_extractions(current_user.id)
        user_extracted_videos = {
            ext['video_id']: ext
            for ext in user_extractions
            if ext.get('extracted') == 1
        }

        results = {}
        for video_id in video_ids:
            global_extraction = db_find_any_global_extraction(video_id)
            if not global_extraction:
                results[video_id] = {'exists': False, 'user_has_access': False, 'status': 'not_extracted'}
                continue

            user_has_access = video_id in user_extracted_videos
            response_data = {
                'exists': True,
                'user_has_access': user_has_access,
                'status': 'extracted' if user_has_access else 'extracted_no_access',
                'extraction_model': global_extraction.get('extraction_model'),
            }

            if user_has_access:
                stems_paths_json = global_extraction.get('stems_paths')
                if stems_paths_json:
                    try:
                        response_data['stems_paths'] = (
                            json.loads(stems_paths_json) if isinstance(stems_paths_json, str) else stems_paths_json
                        )
                        response_data['stems_available'] = True
                    except Exception:
                        response_data['stems_available'] = False
                else:
                    response_data['stems_available'] = False

                if global_extraction.get('stems_zip_path'):
                    response_data['zip_path'] = global_extraction.get('stems_zip_path')
                response_data['extraction_id'] = global_extraction.get('id')

            results[video_id] = response_data

        return jsonify({'statuses': results})
    except Exception as e:
        logger.error(f"Batch extraction status error: {e}")
        return jsonify({'error': str(e)}), 500


@downloads_bp.route('/api/downloads/<download_id>/delete', methods=['DELETE'])
@api_login_required
def delete_download(download_id):
    """Remove a library entry (upload) from the current user's list."""
    try:
        from core.db.connection import _conn

        if download_id.isdigit():
            with _conn() as conn:
                row = conn.execute(
                    'SELECT video_id FROM user_downloads WHERE user_id = ? AND id = ?',
                    (current_user.id, int(download_id))
                ).fetchone()
            if not row:
                return jsonify({'error': 'Download not found'}), 404
            video_id = row['video_id']
        else:
            video_id = download_id.split('_')[0]

        db_delete_download(current_user.id, video_id)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Delete download error: {e}")
        return jsonify({'error': str(e)}), 500


@downloads_bp.route('/api/downloads/clear-all', methods=['DELETE'])
@api_login_required
def clear_all_downloads():
    """Clear every library entry (and in-memory extractions) for the current user."""
    try:
        se = user_session_manager.get_stems_extractor()

        extraction_active_count = len(se.active_extractions)
        extraction_completed_count = len(se.completed_extractions)
        extraction_failed_count = len(se.failed_extractions)

        se.active_extractions.clear()
        se.completed_extractions.clear()
        se.failed_extractions.clear()

        from core.db.connection import _conn
        with _conn() as conn:
            cursor = conn.execute('DELETE FROM user_downloads WHERE user_id = ?', (current_user.id,))
            db_deleted_count = cursor.rowcount
            conn.commit()

        total_cleared = extraction_active_count + extraction_completed_count + extraction_failed_count + db_deleted_count

        return jsonify({
            'success': True,
            'cleared': {
                'extractions': {
                    'active': extraction_active_count,
                    'completed': extraction_completed_count,
                    'failed': extraction_failed_count,
                },
                'database': db_deleted_count,
                'total': total_cleared,
            }
        })
    except Exception as e:
        logger.error(f"Clear all downloads error: {e}")
        return jsonify({'error': str(e)}), 500
