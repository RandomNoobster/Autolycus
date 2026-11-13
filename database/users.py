from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

from .mongo import get_db
from .reminders import _profile_seed, delete_user_reminder_data


def linked_nation_id(user_doc: Optional[Mapping[str, Any]]) -> Optional[str]:
    """Return the nation id linked to a ``global_users`` document, or ``None``.

    Profiles created by the website for beige reminders only store ``user`` and the
    alert settings (no ``id``), so they are not linked to a nation. Use this instead
    of ``user_doc['id']`` whenever a nation is required.
    """
    if not user_doc:
        return None
    raw_id = user_doc.get("id")
    if raw_id is None or isinstance(raw_id, bool):
        return None
    nation_id = str(raw_id).strip()
    return nation_id if nation_id.isdigit() else None


async def get_verification(user_id: int) -> Optional[dict]:
    db = get_db().global_users
    return await db.find_one({"user": user_id})

async def get_verification_by_nation_id(nation_id: str) -> Optional[dict]:
    db = get_db().global_users
    return await db.find_one({"id": str(nation_id)})

async def set_verification(user_id: int, nation_id: str) -> None:
    db = get_db().global_users
    await db.update_one(
        {"user": user_id},
        # Same seed as profiles the reminder features create, so every profile has defaults.
        {"$set": {"id": str(nation_id)}, "$setOnInsert": _profile_seed()},
        upsert=True,
    )

async def delete_verification(user_id: int) -> Optional[dict]:
    """Delete a user's profile along with their scheduled reminders and push devices."""
    db = get_db().global_users
    deleted = await db.find_one_and_delete({"user": user_id})
    if deleted is not None:
        await delete_user_reminder_data(get_db(), user_id)
    return deleted


def _global_users_sync():
    from .mongo import get_sync_db

    db = get_sync_db()
    if db is None:
        raise RuntimeError("MongoDB is not configured")
    return db.global_users


def get_verification_sync(user_id: int) -> Optional[dict]:
    return _global_users_sync().find_one({"user": user_id})


def get_verification_by_nation_id_sync(nation_id: str) -> Optional[dict]:
    return _global_users_sync().find_one({"id": str(nation_id)})


def set_verification_sync(user_id: int, nation_id: str) -> None:
    _global_users_sync().update_one(
        {"user": user_id},
        {"$set": {"id": str(nation_id)}, "$setOnInsert": _profile_seed()},
        upsert=True,
    )
