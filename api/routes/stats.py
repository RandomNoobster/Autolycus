"""
Public aggregate stats (no auth).
"""
import logging
from typing import Any

from flask import Blueprint, jsonify

from database.mongo import get_sync_db

logger = logging.getLogger(__name__)

stats_bp = Blueprint('stats', __name__, url_prefix='/api/stats')


@stats_bp.route('/public', methods=['GET'])
def get_public_stats() -> tuple[Any, int]:
    """
    Public aggregate stats for marketing (e.g. home page).

    ``registered_users`` is the number of documents in MongoDB ``global_users``
    (Discord users who have interacted with the bot / have a stored profile).
    """
    try:
        mongo_db = get_sync_db()
        if mongo_db is None:
            return jsonify({'registered_users': None}), 200
        registered = int(mongo_db.global_users.count_documents({}))
        return jsonify({'registered_users': registered}), 200
    except Exception as e:
        logger.warning('get_public_stats failed: %s', e, exc_info=True)
        return jsonify({'registered_users': None}), 200
