from __future__ import annotations

from typing import Any, Optional, Union, List
import re

import motor.motor_asyncio
from motor.core import AgnosticDatabase

from api.config import get_config

_config = get_config()
_client = motor.motor_asyncio.AsyncIOMotorClient(_config.MONGO_URI, serverSelectionTimeoutMS=5000)
_db: AgnosticDatabase = _client[_config.MONGO_DB]

# Data Access Layer: centralize Mongo queries. No discord imports.

def get_db() -> AgnosticDatabase:
    return _db

async def listify(cursor) -> list[dict[str, Any]]:
    new_list: list[dict[str, Any]] = []
    async for x in cursor:
        new_list.append(x)
    return new_list

async def find_nation(arg: Union[str, int]) -> Optional[dict[str, Any]]:
    """Find a nation by id, name, leader, or discord field."""
    if isinstance(arg, str):
        arg = arg.strip()
    new_arg = re.sub("[^0-9]", "", str(arg))
    if result := await listify(_db.world_nations.find({"id": str(new_arg)}).collation({"locale": "en", "strength": 1})):
        return result[0]
    elif result := await listify(_db.world_nations.find({"nation_name": arg}).collation({"locale": "en", "strength": 1})):
        return result[0]
    elif result := await listify(_db.world_nations.find({"leader_name": arg}).collation({"locale": "en", "strength": 1})):
        return result[0]
    elif result := await listify(_db.world_nations.find({"discord": arg}).collation({"locale": "en", "strength": 1})):
        return result[0]
    else:
        return None

async def get_global_user_by_any(arg: Union[str, int]) -> Optional[dict[str, Any]]:
    """Lookup in global_users by 'id' (nation id) or 'user' (discord id)."""
    if isinstance(arg, str):
        arg = arg.strip()
    db = _db.global_users
    if str(arg).isdigit():
        if x := await db.find_one({"id": str(arg)}):
            return x
        elif x := await db.find_one({"user": int(arg)}):
            return x
    elif "@" in str(arg) or ".com" in str(arg):
        new_arg = re.sub("[^0-9]", "", str(arg))
        if len(new_arg) > 0:
            if x := await db.find_one({"id": new_arg}):
                return x
            elif x := await db.find_one({"user": int(new_arg)}):
                return x
    return None

async def get_all_alliances() -> list[dict[str, Any]]:
    return await listify(_db.alliances.find({}))

async def get_guild_config(guild_id: int) -> Optional[dict[str, Any]]:
    return await _db.guild_configs.find_one({"guild_id": guild_id})

async def get_target_alliances(guild_id: int, filter_value: str) -> list[str]:
    config = await get_guild_config(guild_id)
    if config is None:
        return []
    ids = config.get('targets_alliance_ids', [])
    alliances = await listify(_db.alliances.find({"id": {"$in": ids}}))
    return [f"{aa['name']} ({aa['id']})" for aa in alliances if (filter_value.lower()) in aa['id'] or (filter_value.lower()) in aa['name'].lower() or (filter_value.lower()) in aa['acronym'].lower()]
