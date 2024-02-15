from __future__ import annotations
import discord
import src.env as env
import src.utils as utils


__all__ = (
    "get_alliances",
    "get_target_alliances",
)


async def get_alliances(ctx: discord.AutocompleteContext):
    """Returns a list of alliances that begin with the characters entered so far."""
    alliances = await utils.listify(env.ASYNC_MONGO.alliances.find({}))
    return [f"{aa['name']} ({aa['id']})" for aa in alliances if (ctx.value.lower()) in aa['id'] or (ctx.value.lower()) in aa['name'].lower() or (ctx.value.lower()) in aa['acronym'].lower()]


async def get_target_alliances(ctx: discord.AutocompleteContext):
    """Returns a list of alliances that begin with the characters entered so far."""
    config = await env.ASYNC_MONGO.guild_configs.find_one({"guild_id": ctx.interaction.guild_id})
    if config is None:
        return []
    else:
        try:
            ids = config['targets_alliance_ids']
        except:
            return []
    alliances = await utils.listify(env.ASYNC_MONGO.alliances.find({"id": {"$in": ids}}))
    return [f"{aa['name']} ({aa['id']})" for aa in alliances if (ctx.value.lower()) in aa['id'] or (ctx.value.lower()) in aa['name'].lower() or (ctx.value.lower()) in aa['acronym'].lower()]
