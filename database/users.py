from __future__ import annotations

from typing import Optional

from .mongo import get_db

async def is_verified(user_id: int) -> bool:
    db = get_db().global_users
    doc = await db.find_one({"user": user_id})
    return doc is not None

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
        {"$set": {"id": str(nation_id)}, "$setOnInsert": {"beige_alerts": []}},
        upsert=True,
    )

async def delete_verification(user_id: int) -> Optional[dict]:
    db = get_db().global_users
    return await db.find_one_and_delete({"user": user_id})


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
        {"$set": {"id": str(nation_id)}, "$setOnInsert": {"beige_alerts": []}},
        upsert=True,
    )
