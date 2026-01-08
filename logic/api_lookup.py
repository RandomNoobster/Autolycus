"""Database lookup functions for Politics & War nation data.

This module handles retrieving nation data from MongoDB databases:
- Local world_nations collection (from scanner/scraper)
- Global user verification collection
- Guild-specific configurations

These functions abstract the database layer so business logic doesn't
directly depend on MongoDB implementation details.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Optional, Union

if TYPE_CHECKING:
    import motor.motor_asyncio

# Async MongoDB clients should be passed in or initialized at module load
# This prevents circular imports and allows for cleaner testing
_async_client: Optional[Any] = None  # motor.motor_asyncio.AsyncIOMotorClient


def set_async_client(client: Any, db_version: str) -> None:  # client: motor.motor_asyncio.AsyncIOMotorClient
    """Initialize the async MongoDB client for this module.
    
    Args:
        client: AsyncIOMotorClient instance
        db_version: Database version string for collection selection
    """
    global _async_client
    _async_client = client
    _async_client.db_version = db_version  # Store version for later use


async def get_db():
    """Get the async MongoDB database client.
    
    Returns:
        The async MongoDB database for the configured version
    """
    if _async_client is None:
        raise RuntimeError("Async MongoDB client not initialized. Call set_async_client() first.")
    return _async_client[_async_client.db_version]


async def find_nation(arg: Union[str, int]) -> Optional[dict[str, Any]]:
    """Find a nation by ID, name, leader name, or Discord tag.
    
    Searches the world_nations collection with case-insensitive collation.
    
    Args:
        arg: Nation ID (int/numeric string), nation name, leader name, or Discord tag
        
    Returns:
        Nation document dict if found, None otherwise
    """
    if isinstance(arg, str):
        arg = arg.strip()
    
    db = await get_db()
    
    # Try ID search first (most specific)
    new_arg = re.sub("[^0-9]", "", str(arg))
    if result := await db.world_nations.find_one(
        {"id": str(new_arg)},
        collation={"locale": "en", "strength": 1}
    ):
        return result
    
    # Try nation name
    if result := await db.world_nations.find_one(
        {"nation_name": arg},
        collation={"locale": "en", "strength": 1}
    ):
        return result
    
    # Try leader name
    if result := await db.world_nations.find_one(
        {"leader_name": arg},
        collation={"locale": "en", "strength": 1}
    ):
        return result
    
    # Try Discord tag
    if result := await db.world_nations.find_one(
        {"discord": arg},
        collation={"locale": "en", "strength": 1}
    ):
        return result
    
    return None


async def find_user(arg: Union[str, int]) -> Optional[dict[str, Any]]:
    """Find a verified Discord user in the global_users collection.
    
    Searches by user ID (Discord snowflake) or nation ID.
    
    Args:
        arg: Discord user ID, nation ID, or mention string
        
    Returns:
        User document dict if found, None otherwise
    """
    if isinstance(arg, str):
        arg = arg.strip()
    
    db = await get_db()
    
    if str(arg).isdigit():
        # Try as nation ID first
        if x := await db.global_users.find_one({"id": str(arg)}):
            return x
        # Try as Discord user ID
        if x := await db.global_users.find_one({"user": int(arg)}):
            return x
    elif "@" in arg or ".com" in arg:
        # Extract numeric ID from mention or email-like string
        new_arg = re.sub("[^0-9]", "", arg)
        if len(new_arg) > 0:
            if x := await db.global_users.find_one({"id": new_arg}):
                return x
            if x := await db.global_users.find_one({"user": int(new_arg)}):
                return x
    
    return None


async def find_nation_plus(bot, arg: Union[str, int]) -> Optional[dict[str, Any]]:
    """Find a nation using both direct lookup and user verification data.
    
    First tries to find the nation directly, then if that fails,
    looks up as a Discord user to get their linked nation.
    
    Args:
        bot: Discord bot instance (for member lookups)
        arg: Nation ID, name, Discord user ID, or mention
        
    Returns:
        Nation document dict if found, None otherwise
    """
    if isinstance(arg, str):
        arg = arg.strip()
    
    # Try direct nation lookup first
    nation = await find_nation(arg)
    if nation:
        return nation
    
    # Try user lookup
    nation_link = await find_user(arg)
    if not nation_link:
        return None
    
    # Get the nation linked to this user
    nation = await find_nation(nation_link['id'])
    return nation


async def get_alliances(search_value: str) -> list[str]:
    """Get all alliances matching a search string.
    
    Returns formatted alliance strings like "Alliance Name (ID)".
    
    Args:
        search_value: String to search in alliance ID, name, or acronym
        
    Returns:
        List of formatted alliance strings
    """
    db = await get_db()
    
    alliances = []
    async for aa in db.alliances.find({}):
        search_lower = search_value.lower()
        if (search_lower in aa.get('id', '') or 
            search_lower in aa.get('name', '').lower() or 
            search_lower in aa.get('acronym', '').lower()):
            alliances.append(f"{aa['name']} ({aa['id']})")
    
    return alliances


async def get_target_alliances(guild_id: int, search_value: str) -> list[str]:
    """Get guild-specific target alliances matching a search string.
    
    Returns formatted alliance strings for the guild's configured targets.
    
    Args:
        guild_id: Discord guild ID
        search_value: String to search in alliance ID, name, or acronym
        
    Returns:
        List of formatted alliance strings that match search criteria
    """
    db = await get_db()
    
    config = await db.guild_configs.find_one({"guild_id": guild_id})
    if not config:
        return []
    
    try:
        target_ids = config.get('targets_alliance_ids', [])
    except (KeyError, AttributeError):
        return []
    
    alliances = []
    async for aa in db.alliances.find({"id": {"$in": target_ids}}):
        search_lower = search_value.lower()
        if (search_lower in aa.get('id', '') or 
            search_lower in aa.get('name', '').lower() or 
            search_lower in aa.get('acronym', '').lower()):
            alliances.append(f"{aa['name']} ({aa['id']})")
    
    return alliances
