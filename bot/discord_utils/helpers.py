from __future__ import annotations

import re
from typing import Any, Optional, Union

import discord

from database.mongo import get_global_user_by_any
from database.sqlite_cache import find_nation as db_find_nation
from database.sqlite_cache import search_alliances_autocomplete


async def find_nation_plus(bot: discord.Bot, arg: Union[str, int]) -> Optional[dict[str, Any]]:
    """Find a nation by id/name/leader/discord or via global user mapping.
    Discord member list is consulted only for name matching.
    """
    if isinstance(arg, str):
        arg = arg.strip()
    nation = db_find_nation(arg)
    if nation is None:
        user = await get_global_user_by_any(arg)
        if not user and isinstance(arg, str):
            # Last resort: scan Discord members for matching display names
            for member in bot.get_all_members():
                if arg.lower() in member.name.lower() or arg.lower() in member.display_name.lower() or str(member).lower() == arg.lower():
                    user = await get_global_user_by_any(member.id)
                    if user:
                        break
        if not user:
            return None
        nation = db_find_nation(user['id'])
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
    """Locate a verified user document by nation id, discord id, or name."""
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
    return search_alliances_autocomplete(search_value)
