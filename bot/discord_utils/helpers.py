from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict
from typing import Any, Mapping, Optional, Union

import discord

from database.mongo import get_global_user_by_any
from database.sqlite_cache import find_nation as db_find_nation
from database.sqlite_cache import search_alliances_autocomplete

_ALLIANCE_AC_TTL_SECONDS = 6.0
_ALLIANCE_AC_MAX = 128
_alliance_ac_cache: "OrderedDict[str, tuple[float, list[str]]]" = OrderedDict()

NATION_NOT_LINKED_MESSAGE = (
    "Your Discord account is not linked to a Politics & War nation yet. "
    "Use `/verify` to link your nation, then try again."
)


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


async def find_nation_plus(bot: discord.Bot, arg: Union[str, int]) -> Optional[dict[str, Any]]:
    """Find a nation by id/name/leader/discord or via global user mapping.
    Discord member list is consulted only for name matching.
    Returns ``None`` when the matched user profile has no linked nation
    (e.g. reminder-only profiles created by the website).
    """
    if isinstance(arg, str):
        arg = arg.strip()
    nation = await asyncio.to_thread(db_find_nation, arg)
    if nation is None:
        user = await get_global_user_by_any(arg)
        if not user and isinstance(arg, str):
            # Last resort: scan Discord members for matching display names
            for member in bot.get_all_members():
                if arg.lower() in member.name.lower() or arg.lower() in member.display_name.lower() or str(member).lower() == arg.lower():
                    match = await get_global_user_by_any(member.id)
                    # Skip reminder-only profiles and keep looking for a linked member.
                    if linked_nation_id(match):
                        user = match
                        break
        nation_id = linked_nation_id(user)
        if nation_id is None:
            return None
        nation = await asyncio.to_thread(db_find_nation, nation_id)
        if nation is None:
            return None
    return nation


async def yes_or_no(bot: discord.Bot, ctx: discord.ApplicationContext) -> Optional[bool]:
    try:
        msg = await bot.wait_for('message', check=lambda message: message.author == ctx.author and message.channel.id == ctx.channel.id, timeout=40)
        if msg.content.lower() in ('yes', 'y'):
            return True
        if msg.content.lower() in ('no', 'n'):
            return False
    except Exception:
        return None


async def find_user(bot: discord.Bot, arg: Union[str, int]) -> Optional[dict[str, Any]]:
    """Locate a ``global_users`` document by nation id, discord id, or name.

    The document may be a reminder-only profile without a linked nation (no ``id``).
    Callers that need a nation must use :func:`linked_nation_id` rather than ``user['id']``.
    """
    if isinstance(arg, str):
        arg = arg.strip()

    user = await get_global_user_by_any(arg)
    if user:
        return user

    if isinstance(arg, str):
        for member in bot.get_all_members():
            if (
                arg.lower() in member.name.lower()
                or arg.lower() in member.display_name.lower()
                or str(member).lower() == arg.lower()
            ):
                match = await get_global_user_by_any(member.id)
                if match:
                    return match
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
