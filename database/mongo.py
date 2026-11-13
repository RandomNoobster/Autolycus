from __future__ import annotations

from typing import Any, Optional, Union
import re

import motor.motor_asyncio
from motor.core import AgnosticDatabase
from pymongo import MongoClient
from pymongo.database import Database as SyncDatabase

from core.config import Config

# Only the Mongo settings are needed here. get_config() would also run the Flask
# production checks (SECRET_KEY), which the bot and scanner don't use and must not
# crash on at import time.
_config = Config
_client = motor.motor_asyncio.AsyncIOMotorClient(_config.MONGO_URI, serverSelectionTimeoutMS=5000)
_db: AgnosticDatabase = _client[_config.MONGO_DB]
_sync_client: Optional[MongoClient] = None
_sync_db: Optional[SyncDatabase] = None

# Data Access Layer: centralize Mongo queries. No discord imports.

def get_db() -> AgnosticDatabase:
    return _db


def get_sync_db() -> Optional[SyncDatabase]:
    """Get a shared synchronous Mongo database handle."""
    global _sync_client, _sync_db
    if _config.MONGO_URI is None:
        return None
    if _sync_client is None:
        _sync_client = MongoClient(_config.MONGO_URI, serverSelectionTimeoutMS=5000)
        _sync_db = _sync_client[_config.MONGO_DB]
    return _sync_db

async def listify(cursor) -> list[dict[str, Any]]:
    new_list: list[dict[str, Any]] = []
    async for x in cursor:
        new_list.append(x)
    return new_list

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

async def record_slash_command(doc: dict[str, Any]) -> None:
    """Append one slash command invocation document (analytics)."""
    await _db.commands.insert_one(doc)
