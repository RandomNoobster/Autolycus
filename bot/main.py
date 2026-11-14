import datetime
import logging
import os
import pathlib

from dotenv import load_dotenv

load_dotenv()

import discord
from discord.ext import commands

from bot.discord_utils import errors as err_embeds
from bot.discord_utils import views as discord_views
from bot.discord_utils.interaction_framework import InteractionRegistry, route_interaction
from bot.reminders import notices as reminder_notices
from bot.reminders.interactions import DM_TEST_ACK_HANDLER, handle_test_dm_ack
from core.logging_config import setup_logging
from database.mongo import record_slash_command

intents = discord.Intents.default()
intents.members = True
# REMEMEBR: cannot import a file which is also imported by cogs

# logging
setup_logging(process_name="bot", level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# discord bot
# No member chunking at startup: across ~1200 servers the gateway rate limit held
# on_ready (and reminder delivery) back ~11 min. Lookups by Discord name therefore
# ask the guild for matching members (helpers.find_nation_plus) instead of relying
# on the member cache.
bot = commands.Bot(
    intents=intents,
    command_prefix="!",
    chunk_guilds_at_startup=False,
    # Replies echo user input (command names, alliance names): never let that ping
    # @everyone, @here or roles.
    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=True),
)
bot.interaction_registry = InteractionRegistry()
discord_views.register_interaction_handlers(bot.interaction_registry)
bot.interaction_registry.register_stateless(DM_TEST_ACK_HANDLER, handle_test_dm_ack)

# cogs
cogs_dir = pathlib.Path(__file__).resolve().parent / "cogs"
for path in sorted(cogs_dir.glob("*.py")):
    if path.name != "__init__.py":
        bot.load_extension(f"bot.cogs.{path.stem}")


@bot.event
async def on_ready():
    # member_count is None for a guild that is still unavailable.
    guilds = sorted(bot.guilds, key=lambda x: x.member_count or 0, reverse=True)
    logger.info(f"I am in {len(guilds)} servers:")
    for guild in guilds:
        logger.info(f"-> {guild.member_count} members || {guild}")
    await bot.change_presence(status=discord.Status.online, activity=discord.Activity(type=discord.ActivityType.watching, name="Orbis"))
    logger.info('We have logged in as {0.user}'.format(bot))


@bot.event
async def on_interaction(interaction: discord.Interaction):
    await route_interaction(bot, interaction)


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


@bot.event
async def on_application_command_completion(ctx: discord.ApplicationContext):
    # Tell users once, privately, when a reminder DM couldn't reach them.
    await reminder_notices.maybe_notify(ctx)


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
    debug_channel = err_embeds.resolve_debug_channel(bot)

    async def _debug():
        await err_embeds.send_debug_channel_messages(debug_channel, ctx, error, reference, logger)

    # --- User-facing branches (never expose raw trace or internal repr) ---
    if _user_safe_permission_text(root):
        desc = str(root)[:4096]
        embed = err_embeds.error_embed("Cannot run command", desc, reference=reference)
        await err_embeds.safe_reply_error(ctx, embed, ephemeral=True, reference=reference, log=logger)
        await _debug()
        return

    err_s = str(error)
    if "Unknown interaction" in err_s:
        # The interaction expired before it was answered, so no reply can reach the
        # user through it; just report it.
        await _debug()
        return

    # Checked on the unwrapped error: py-cord wraps exceptions raised inside a
    # command in ApplicationCommandInvokeError. Before the P&W check, whose
    # "internal server error" text a Discord 500 also contains.
    if isinstance(root, discord.HTTPException):
        embed = err_embeds.error_embed(
            "Discord error",
            "Something went wrong talking to Discord. Please try again in a moment.",
            reference=reference,
        )
        await err_embeds.safe_reply_error(ctx, embed, ephemeral=True, reference=reference, log=logger)
        await _debug()
        return
    if err_embeds.is_pnw_server_error(root):
        embed = err_embeds.error_embed(
            "PnW server issue",
            err_embeds.PNW_SERVER_USER_MESSAGE,
            reference=reference,
        )
        await err_embeds.safe_reply_error(ctx, embed, ephemeral=True, reference=reference, log=logger)
        await _debug()
        return

    embed = err_embeds.error_embed(
        "Something went wrong",
        "An unexpected error occurred. If it keeps happening, contact randomnoobster with the reference below.",
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
