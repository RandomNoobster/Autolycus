"""
Browser Push API Routes

Endpoints for the VAPID public key, registering and removing this browser's push
subscription, and sending a test notification to every device.
"""
import logging
import re
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from api.rate_limit import rate_limit
from api.routes.reminder_views import delivery_view, device_view
from api.security import require_discord_session, require_same_origin
from database import reminders as reminder_db
from database.mongo import get_sync_db
from infra.webpush import PushOutcome, get_push_sender, notification_payload
from logic import reminders as reminder_rules
from services import reminders as reminder_service

logger = logging.getLogger(__name__)

push_bp = Blueprint('push', __name__, url_prefix='/api/push')

_DEVICE_ID = re.compile(r'^[0-9a-f]{32}$')


def _error_response(error: str, message: str, code: str, status: int) -> tuple[Any, int]:
    return jsonify({'error': error, 'message': message, 'code': code}), status


def _push_unavailable() -> tuple[Any, int]:
    return _error_response(
        'Push unavailable',
        'Browser notifications are not set up on this server.',
        'PUSH_NOT_CONFIGURED',
        503,
    )


def _db_unavailable() -> tuple[Any, int]:
    return _error_response('Database unavailable', 'MongoDB is not configured.', 'DB_UNAVAILABLE', 503)


def _session_user_id() -> int:
    return int(getattr(request, 'session_user_id'))


@push_bp.route('/vapid-public-key', methods=['GET'])
def get_vapid_public_key() -> tuple[Any, int]:
    """Public key browsers subscribe with."""
    sender = get_push_sender()
    if sender is None:
        return _push_unavailable()
    return jsonify({'publicKey': sender.public_key, 'keyId': sender.key_id}), 200


@push_bp.route('/subscriptions', methods=['GET'])
@require_discord_session
def list_push_devices() -> tuple[Any, int]:
    """Devices with browser notifications turned on for the signed-in user."""
    try:
        mongo_db = get_sync_db()
        if mongo_db is None:
            return _db_unavailable()
        sender = get_push_sender()
        devices = reminder_db.list_push_subscriptions_sync(mongo_db, _session_user_id())
        return jsonify({
            'success': True,
            'devices': [device_view(device) for device in devices],
            'configured': sender is not None,
            'keyId': sender.key_id if sender else None,
        }), 200
    except Exception as e:
        logger.error(f"Error listing push devices: {e}", exc_info=True)
        return _error_response('Internal server error', 'Failed to load devices.', 'INTERNAL_ERROR', 500)


@push_bp.route('/subscriptions', methods=['POST'])
@require_discord_session
@require_same_origin
@rate_limit(30, 60, scope='push-subscribe')
def register_push_device() -> tuple[Any, int]:
    """
    Register this browser for reminder notifications.

    Body: { "endpoint": str, "keys": {"p256dh": str, "auth": str}, "keyId"?: str,
    "label"?: str, "enableChannel"?: bool (default true) }.
    """
    try:
        sender = get_push_sender()
        if sender is None:
            return _push_unavailable()
        mongo_db = get_sync_db()
        if mongo_db is None:
            return _db_unavailable()

        uid = _session_user_id()
        data = request.get_json(silent=True) or {}
        keys = data.get('keys') if isinstance(data.get('keys'), dict) else {}
        key_id = data.get('keyId') if isinstance(data.get('keyId'), str) else sender.key_id
        error, device = reminder_service.register_push_device_sync(
            mongo_db,
            uid,
            endpoint=data.get('endpoint'),
            p256dh=keys.get('p256dh'),
            auth=keys.get('auth'),
            key_id=key_id[:32],
            label=data.get('label'),
            enable_channel=data.get('enableChannel', True) is not False,
        )
        if error == reminder_service.INVALID_SUBSCRIPTION:
            return _error_response(
                'Validation error',
                "This browser's notification subscription isn't valid. Turn notifications off and on again.",
                'INVALID_SUBSCRIPTION',
                400,
            )
        if error == reminder_service.DEVICE_LIMIT:
            return _error_response(
                'Too many devices',
                f'Notifications can be on for up to {reminder_rules.MAX_PUSH_DEVICES_PER_USER} devices. '
                'Remove one first.',
                'DEVICE_LIMIT',
                409,
            )
        profile = reminder_db.get_profile_sync(mongo_db, uid) or {}
        return jsonify({
            'success': True,
            'device': device_view(device),
            'delivery': delivery_view(mongo_db, uid, profile),
        }), 200
    except Exception as e:
        logger.error(f"Error registering push device: {e}", exc_info=True)
        return _error_response('Internal server error', 'Failed to turn on notifications.', 'INTERNAL_ERROR', 500)


@push_bp.route('/subscriptions/<device_id>', methods=['DELETE'])
@require_discord_session
@require_same_origin
def remove_push_device(device_id: str) -> tuple[Any, int]:
    """Remove one of the signed-in user's devices."""
    try:
        if not _DEVICE_ID.match(device_id or ''):
            return _error_response('Validation error', 'Unknown device.', 'VALIDATION_ERROR', 400)
        mongo_db = get_sync_db()
        if mongo_db is None:
            return _db_unavailable()
        uid = _session_user_id()
        removed = reminder_service.remove_push_device_sync(mongo_db, uid, device_id)
        profile = reminder_db.get_profile_sync(mongo_db, uid) or {}
        return jsonify({
            'success': True,
            'removed': removed,
            'delivery': delivery_view(mongo_db, uid, profile),
        }), 200
    except Exception as e:
        logger.error(f"Error removing push device: {e}", exc_info=True)
        return _error_response('Internal server error', 'Failed to remove the device.', 'INTERNAL_ERROR', 500)


@push_bp.route('/test', methods=['POST'])
@require_discord_session
@require_same_origin
@rate_limit(3, 60, scope='push-test')
def send_test_push() -> tuple[Any, int]:
    """Send a test notification to every device of the signed-in user."""
    try:
        sender = get_push_sender()
        if sender is None:
            return _push_unavailable()
        mongo_db = get_sync_db()
        if mongo_db is None:
            return _db_unavailable()

        uid = _session_user_id()
        devices = reminder_db.list_push_subscriptions_sync(mongo_db, uid)
        if not devices:
            return _error_response(
                'No devices',
                'Turn on browser notifications on this device first.',
                reminder_rules.NO_PUSH_DEVICES,
                409,
            )

        now = reminder_rules.utcnow()
        web_base = str(current_app.config.get('AUTOLYCUS_WEB_BASE_URL') or '').rstrip('/')
        payload = notification_payload(
            title='Test notification from Autolycus',
            body='Browser notifications work on this device.',
            navigate=f'{web_base}/reminders',
            tag='autolycus-test',
            kind='test',
            timestamp=now,
            require_interaction=False,
        )
        delivered: list[str] = []
        failed: list[str] = []
        gone: list[str] = []
        for device in devices:
            device_id = str(device.get('_id'))
            result = sender.send_sync(
                device, payload, ttl=300, topic='autolycus-test', urgency='normal', timeout_seconds=5.0
            )
            if result.outcome is PushOutcome.DELIVERED:
                delivered.append(device_id)
            elif result.outcome is PushOutcome.GONE:
                gone.append(device_id)
            else:
                failed.append(device_id)
                logger.warning(
                    "Test push to device %s failed (HTTP %s %s)", device_id, result.status, result.detail
                )
        reminder_db.record_push_results_sync(mongo_db, delivered=delivered, failed=failed, gone=gone, now=now)
        if gone:
            reminder_db.turn_off_push_channel_if_no_devices_sync(mongo_db, uid)
        return jsonify({
            'success': True,
            'sent': len(delivered),
            'failed': len(failed),
            'removed': len(gone),
        }), 200
    except Exception as e:
        logger.error(f"Error sending test push: {e}", exc_info=True)
        return _error_response('Internal server error', 'Failed to send a test notification.', 'INTERNAL_ERROR', 500)
