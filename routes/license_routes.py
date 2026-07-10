"""License management API for StemTube Desktop."""
from flask import Blueprint, request, jsonify
from core.licensing import (
    get_hardware_id, get_license_status, save_license,
    validate_license, is_authorized
)

license_bp = Blueprint('license', __name__)

@license_bp.route('/api/license/status')
def license_status():
    return jsonify(get_license_status())

@license_bp.route('/api/license/hardware-id')
def hardware_id():
    return jsonify({'hardware_id': get_hardware_id()})

@license_bp.route('/api/license/activate', methods=['POST'])
def activate_license():
    data = request.get_json()
    key = data.get('license_key', '').strip()
    if not key:
        return jsonify({'error': 'License key required'}), 400
    if save_license(key):
        return jsonify({'success': True, 'status': get_license_status()})
    return jsonify({'error': 'Invalid license key for this machine'}), 400
