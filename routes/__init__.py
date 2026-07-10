"""
Route blueprints for StemTube Desktop Friend.
Single-user, YouTube enabled, no licensing.
"""

from edition import HAS_LICENSE

from .pages import pages_bp
from .admin_api import admin_api_bp
from .downloads import downloads_bp
from .extractions import extractions_bp
from .media import media_bp
from .library import library_bp
from .files import files_bp
from .config_routes import config_bp
from .recordings import recordings_bp
from .poc_mixer import poc_mixer_bp

ALL_BLUEPRINTS = [
    pages_bp,
    admin_api_bp,
    downloads_bp,
    extractions_bp,
    media_bp,
    library_bp,
    files_bp,
    config_bp,
    recordings_bp,
    poc_mixer_bp,
]

if HAS_LICENSE:
    from .license_routes import license_bp
    ALL_BLUEPRINTS.append(license_bp)


def register_all_blueprints(app):
    """Register every blueprint with the Flask app."""
    for bp in ALL_BLUEPRINTS:
        app.register_blueprint(bp)
    print(f"[Blueprints] {len(ALL_BLUEPRINTS)} route blueprints registered")
