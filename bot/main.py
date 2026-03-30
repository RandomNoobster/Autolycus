import datetime
import logging
import os
import pathlib

from dotenv import load_dotenv

load_dotenv()

import discord
import pnwkit
from discord.ext import commands

from bot.discord_utils import errors as err_embeds
from core.logging_config import setup_logging
from database.mongo import record_slash_command

intents = discord.Intents.default()
intents.members = True
# REMEMEBR: cannot import a file which is also imported by cogs

# envs
api_key = os.getenv("API_KEY")
channel_id = int(os.getenv("DEBUG_CHANNEL"))

# logging
setup_logging(process_name="bot", level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# pnwkit
kit = pnwkit.QueryKit(api_key)

# discord bot
bot = commands.Bot(intents=intents, command_prefix="!")
bot.pnw_kit = kit

# cogs
cogs_dir = pathlib.Path(__file__).resolve().parent / "cogs"
for path in sorted(cogs_dir.glob("*.py")):
    if path.name != "__init__.py":
        bot.load_extension(f"bot.cogs.{path.stem}")


@bot.event
async def on_ready():
    guilds = sorted(bot.guilds, key=lambda x: x.member_count, reverse=True)
    n = len(guilds)
    logger.info(f"I am in {n} servers:")
    for guild in guilds:
        extra = ""
        n -= 1
        logger.info(f"-> {guild.member_count} members || {guild} {extra}")
    logger.info(f"Slash commands are allowed in {n}/{len(bot.guilds)} guilds")
    await bot.change_presence(status=discord.Status.online, activity=discord.Activity(type=discord.ActivityType.watching, name="Orbis"))
    logger.info('We have logged in as {0.user}'.format(bot))


@bot.event
async def on_application_command(ctx: discord.ApplicationContext):
    channel = guild = None
    try:
        channel = {"name": ctx.channel.name, "id": ctx.channel_id}
    except Exception:
        try:
            channel = {"name": f"{ctx.author.name}'s DM's", "id": ctx.channel_id}
        except Exception:
            channel = {"name": "Unknown", "id": None}
            # it might be a PartialMessageable
    try:
        guild = {"name": ctx.guild.name, "id": ctx.guild_id}
    except Exception:
        try:
            guild = {"name": f"{ctx.author.name}'s DM's", "id": None}
        except Exception:
            guild = {"name": "Unknown", "id": None}
            # it might be a PartialMessageable

    await record_slash_command(
        {
            "command": ctx.command.name,
            "time": round(datetime.datetime.utcnow().timestamp()),
            "user": {"name": ctx.author.name, "id": ctx.author.id},
            "channel": channel,
            "guild": guild,
        }
    )


def _user_safe_permission_text(root: Exception) -> bool:
    if isinstance(
        root,
        (
            commands.MissingPermissions,
            commands.BotMissingPermissions,
            commands.MissingRole,
            commands.MissingAnyRole,
            commands.NoPrivateMessage,
        ),
    ):
        return True
    msg = str(root)
    return "You are missing" in msg and "permission" in msg.lower() and "run this command" in msg


@bot.event
async def on_application_command_error(ctx: discord.ApplicationContext, error):
    reference = err_embeds.new_error_reference()
    root = err_embeds.unwrap_command_error(error)
    err_embeds.log_command_error(logger, root, ctx=ctx, reference=reference)
    debug_channel = bot.get_channel(channel_id)

    async def _debug():
        await err_embeds.send_debug_channel_messages(debug_channel, ctx, error, reference, logger)

    # --- User-facing branches (never expose raw trace or internal repr) ---
    if _user_safe_permission_text(root):
        desc = str(root)[:4096]
        embed = err_embeds.error_embed("Cannot run command", desc, reference=reference)
        await err_embeds.safe_reply_error(ctx, embed, ephemeral=True, reference=reference, log=logger)
        await _debug()
        return

    parent = getattr(ctx.command, "full_parent_name", None) or ""
    if isinstance(root, ValueError) and str(parent) == "cost":
        embed = err_embeds.error_embed(
            "Invalid input",
            "Those cost parameters could not be processed. Check the values you entered and try again.",
            reference=reference,
        )
        await err_embeds.safe_reply_error(ctx, embed, ephemeral=True, reference=reference, log=logger)
        await _debug()
        return

    err_s = str(error)
    if "Unknown interaction" in err_s:
        embed = err_embeds.error_embed(
            "Slow response",
            f"My bad <@{ctx.author.id}>! Discord did not get a response in time. Please try again.",
            reference=reference,
        )
        await err_embeds.safe_reply_error(ctx, embed, ephemeral=False, reference=reference, log=logger)
        await _debug()
        return

    if isinstance(error, (discord.HTTPException, discord.NotFound)):
        embed = err_embeds.error_embed(
            "Discord error",
            "Something went wrong talking to Discord. Please try again in a moment.",
            reference=reference,
        )
        await err_embeds.safe_reply_error(ctx, embed, ephemeral=True, reference=reference, log=logger)
        await _debug()
        return

    embed = err_embeds.error_embed(
        "Something went wrong",
        "An unexpected error occurred. If it keeps happening, contact RandomNoobster#0093 with the reference below.",
        reference=reference,
    )
    await err_embeds.safe_reply_error(ctx, embed, ephemeral=True, reference=reference, log=logger)
    await _debug()


@bot.slash_command(name="ping", description="Pong!")
async def ping(ctx: discord.ApplicationContext):
    await ctx.respond(f'Pong! {round(bot.latency * 1000)}ms')


def run_bot():
    bot.run(os.getenv("BOT_TOKEN"))


if __name__ == "__main__":
    run_bot()
