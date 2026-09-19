"""
Media metadata for lyrics lookup: artist, track and sung language.

Metadata (`artist`, `track`, `language`, tags...) is stored as JSON in
`global_downloads.media_metadata` when a song is added to the library. This edition
imports local files only and has no metadata provider, so nothing is fetched here:
load_media_metadata() reads whatever the database holds, and when it holds nothing the
lyrics pipeline falls back to the song title and its ID3 tags (resolve_artist_track).
"""

import logging
import re
from typing import Dict, Optional, Tuple

from core.metadata_extractor import get_id3_tags, parse_artist_title

logger = logging.getLogger(__name__)

# Some stored metadata carries "(Musical Artist)" tags that name the performer.
MUSICAL_ARTIST_TAG = re.compile(r'^(.+?)\s*\(Musical Artist\)$', re.IGNORECASE)


def load_media_metadata(video_id: str) -> Dict:
    """Stored metadata for a song, or {} when none was recorded."""
    try:
        from core.downloads_db import get_media_metadata
    except ImportError:
        logger.debug("[METADATA] Media metadata storage unavailable")
        return {}
    return get_media_metadata(video_id) or {}


def _clean_uploader(name: str) -> str:
    name = re.sub(r'\s*-\s*Topic$', '', name or '', flags=re.IGNORECASE)
    name = re.sub(r'(VEVO|Official|TV)$', '', name).strip()
    return name


def resolve_artist_track(title: str = None, file_path: str = None, meta: Optional[Dict] = None,
                         override_artist: str = None, override_track: str = None) -> Tuple[str, str]:
    """
    (artist, track) for a lyrics search, best source first:
    user override > stored music metadata > "Artist - Track" title > ID3 tags
    > "(Musical Artist)" tag > uploader name.
    """
    meta = meta or {}
    if override_artist or override_track:
        return (override_artist or '').strip(), (override_track or title or '').strip()

    if meta.get('artist') and meta.get('track'):
        return meta['artist'].strip(), meta['track'].strip()

    artist, track = parse_artist_title(title) if title else (None, None)
    if artist and track:
        return artist, track

    if file_path:
        tags = get_id3_tags(file_path) or {}
        # Local imports carry the user's own tags, so the ID3 artist is trustworthy here.
        if tags.get('artist'):
            id3_track = parse_artist_title(tags.get('title') or '')[1] or track
            if id3_track:
                return tags['artist'].strip(), id3_track.strip()

    for tag in meta.get('tags') or []:
        match = MUSICAL_ARTIST_TAG.match(tag)
        if match and track:
            return match.group(1).strip(), track

    if meta.get('artist') and track:
        return meta['artist'].strip(), track
    if meta.get('uploader') and track:
        return _clean_uploader(meta['uploader']), track
    return '', (track or title or '').strip()
