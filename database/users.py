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

async def set_verification(user_id: int, nation_id: str) -> None:
    db = get_db().global_users
    await db.insert_one({"user": user_id, "id": nation_id, "beige_alerts": []})

async def delete_verification(user_id: int) -> Optional[dict]:
    db = get_db().global_users
    return await db.find_one_and_delete({"user": user_id})
