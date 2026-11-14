from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Any, Optional, Union

import discord

from database.mongo import get_global_user_by_any
from database.sqlite_cache import find_nation as db_find_nation
from database.sqlite_cache import search_alliances_autocomplete
from database.users import linked_nation_id  # noqa: F401  (re-exported for bot callers)

logger = logging.getLogger(__name__)

_ALLIANCE_AC_TTL_SECONDS = 6.0
_ALLIANCE_AC_MAX = 128
_alliance_ac_cache: "OrderedDict[str, tuple[float, list[str]]]" = OrderedDict()
# Members fetched from the gateway when the cache has no exact match.
_MEMBER_QUERY_LIMIT = 10

NATION_NOT_LINKED_MESSAGE = (
    "Your Discord account is not linked to a Politics & War nation yet. "
    "Use `/verify` to link your nation, then try again."
)


def _member_names(member: Any) -> set[str]:
    names = {str(member)}
    for attr in ("name", "display_name", "global_name", "nick"):
        value = getattr(member, attr, None)
        if value:
            names.add(str(value))
    return {name.lower() for name in names}


async def _linked_profile_for_member_name(
    bot: discord.Bot,
    name: str,
    guild: Optional[discord.Guild],
) -> Optional[dict[str, Any]]:
    """The linked profile of a member whose Discord name is exactly ``name``.

    Exact (case-insensitive) matches only: a partial match would return someone
    else's nation. Startup skips member chunking, so the cache misses most members
    of large servers; the command's guild is then asked directly.
    """
    wanted = name.lower()
    candidates = [m for m in bot.get_all_members() if wanted in _member_names(m)]
    if not candidates and guild is not None:
        try:
            fetched = await guild.query_members(query=name, limit=_MEMBER_QUERY_LIMIT)
        except (asyncio.TimeoutError, discord.HTTPException, discord.ClientException):
            logger.debug("Member query for %r failed", name, exc_info=True)
            fetched = []
        candidates = [m for m in fetched if wanted in _member_names(m)]
    for member in candidates:
        match = await get_global_user_by_any(member.id)
        # Skip reminder-only profiles and keep looking for a linked member.
        if linked_nation_id(match):
            return match
    return None


async def find_nation_plus(
    bot: discord.Bot,
    arg: Union[str, int],
    *,
    guild: Optional[discord.Guild] = None,
) -> Optional[dict[str, Any]]:
    """Find a nation by id, link, nation or leader name, verified Discord user, or
    (last) the in-game Discord field.

    A verified link wins over the in-game Discord field, which any player can set
    to someone else's name. Returns ``None`` when the matched user profile has no
    linked nation (e.g. reminder-only profiles created by the website).
    """
    if isinstance(arg, str):
        arg = arg.strip()
    nation = await asyncio.to_thread(db_find_nation, arg, include_discord=False)
    if nation is not None:
        return nation

    user = await get_global_user_by_any(arg)
    if not user and isinstance(arg, str) and arg:
        user = await _linked_profile_for_member_name(bot, arg, guild)
    if user:
        nation_id = linked_nation_id(user)
        if nation_id is None:
            return None
        return await asyncio.to_thread(db_find_nation, nation_id)

    if isinstance(arg, str) and arg:
        return await asyncio.to_thread(db_find_nation, arg)
    return None


async def find_user(
    bot: discord.Bot,
    arg: Union[str, int],
    *,
    guild: Optional[discord.Guild] = None,
) -> Optional[dict[str, Any]]:
    """Locate a ``global_users`` document by nation id, discord id, mention or exact name.

    The document may be a reminder-only profile without a linked nation (no ``id``).
    Callers that need a nation must use :func:`linked_nation_id` rather than ``user['id']``.
    """
    if isinstance(arg, str):
        arg = arg.strip()

    user = await get_global_user_by_any(arg)
    if user:
        return user

    if isinstance(arg, str) and arg:
        return await _linked_profile_for_member_name(bot, arg, guild)
    return None


async def autocomplete_alliances(ctx: discord.AutocompleteContext) -> list[str]:
    search_value = ctx.value or ""
    key = str(search_value).strip().lower()
    now = time.monotonic()
    cached = _alliance_ac_cache.get(key)
    if cached is not None:
        ts, results = cached
        if (now - ts) <= _ALLIANCE_AC_TTL_SECONDS:
            _alliance_ac_cache.move_to_end(key)
            return list(results)
        _alliance_ac_cache.pop(key, None)

    results = await asyncio.to_thread(search_alliances_autocomplete, search_value)
    _alliance_ac_cache[key] = (now, list(results))
    _alliance_ac_cache.move_to_end(key)
    while len(_alliance_ac_cache) > _ALLIANCE_AC_MAX:
        _alliance_ac_cache.popitem(last=False)
    return results
