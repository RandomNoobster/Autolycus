import datetime
import logging
import os
import pathlib

import discord
import pnwkit
from discord.ext import commands
from dotenv import load_dotenv

from core.logging_config import setup_logging
from database.mongo import record_slash_command

intents = discord.Intents.default()
intents.members = True
load_dotenv()
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


@bot.event
async def on_application_command_error(ctx: discord.ApplicationContext, error):
    debug_channel = bot.get_channel(channel_id)
    logger.error(error)
    print(error)
    print(type(error))
    if "MissingPermissions" in str(error):
        await ctx.respond(error.original)
    elif "You are missing" in str(error) and "permission(s) to run this command" in str(error):
        await ctx.respond(error.original)
    elif "NoPrivateMessage" in str(error) or isinstance(error, commands.errors.NoPrivateMessage):
        await ctx.respond(error)
    elif "ValueError" in str(error) and str(ctx.command.full_parent_name) == "cost":
        await ctx.respond(error.original)
    elif "Unknown interaction" in str(error):
        await ctx.respond(f"My bad <@{ctx.author.id}>! Discord claims I didn't respond fast enough, please try that again!")
        await debug_channel.send(f'**Exception __caught__!**\nAuthor: {ctx.author}\nServer: {ctx.guild}\nCommand: {ctx.command}\nType: {type(error)}\n\nError:```{error}```'[:2000])
    elif isinstance(error, (discord.HTTPException, discord.errors.NotFound)):
        await debug_channel.send(f'**Exception __caught__!**\nAuthor: {ctx.author}\nServer: {ctx.guild}\nCommand: {ctx.command}\nType: {type(error)}\n\nError:```{error}```'[:2000])
    else:
        await ctx.send("Oh no! An unknown error occurred! Contact RandomNoobster#0093, and he might be able to help you out.")
        await debug_channel.send(f'**Exception raised!**\nAuthor: {ctx.author}\nServer: {ctx.guild}\nCommand: {ctx.command}\nType: {type(error)}\n\nError:```{error}```'[:2000])


@bot.slash_command(name="ping", description="Pong!")
async def ping(ctx: discord.ApplicationContext):
    await ctx.respond(f'Pong! {round(bot.latency * 1000)}ms')


def run_bot():
    bot.run(os.getenv("BOT_TOKEN"))


if __name__ == "__main__":
    run_bot()
