"""Helpers for reading request data in API routes."""
import logging
from typing import Any, Optional

from flask import request
from pymongo.errors import PyMongoError

from database import reminders as reminder_db
from database.mongo import get_sync_db

logger = logging.getLogger(__name__)


def optional_session_profile() -> Optional[dict[str, Any]]:
    """The signed-in user's profile (linked nation id, watch list), or None.

    None when nobody is signed in, Mongo isn't configured, or the read fails: pages
    that only use the profile for extras (the linked attacker, reminder flags) must
    still load when the database is down.
    """
    user_id = getattr(request, "session_user_id", None)
    if user_id is None:
        return None
    mongo_db = get_sync_db()
    if mongo_db is None:
        return None
    try:
        return reminder_db.get_profile_sync(mongo_db, int(user_id))
    except (TypeError, ValueError, PyMongoError) as exc:
        logger.warning("Could not load the profile for user %s: %s", user_id, exc)
        return None


def get_json_object() -> dict[str, Any]:
    """Return the request's JSON body as a dict.

    A missing, undecodable or non-object body (for example ``[1]`` or ``"x"``)
    becomes ``{}``, so the route's own field validation returns its normal 400
    instead of an exception reaching the route's catch-all 500 handler.
    """
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}
