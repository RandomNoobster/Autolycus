import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
import keep_alive
import pymongo
import aiohttp
import os
from discord.commands import Option
from discord.bot import ApplicationCommandMixin
import re
import discord
from discord.ext import commands
intents = discord.Intents.default()
intents.members = True
load_dotenv()

client = pymongo.MongoClient(os.getenv("pymongolink"))
version = os.getenv("version")
mongo = client[str(version)]
api_key = os.getenv("api_key")

bot = commands.Bot(intents=intents)

for filename in os.listdir('./cogs'):
    if filename.endswith('.py'):
        bot.load_extension(f'cogs.{filename[:-3]}')

@bot.event
async def on_ready():
    print("I am in ", len(bot.guilds), " servers:")
    n = len(bot.guilds)
    for guild in bot.guilds:
        extra = ""
        try:
            await ApplicationCommandMixin.get_desynced_commands(bot, guild.id)
        except discord.errors.Forbidden:
            owner = guild.owner
            extra = f"|| Slash disallowed, DM {owner}"
            n -= 1
        print(f"-> {guild} || {guild.member_count} members {extra}")
    print(f"Slash commands are allowed in {n}/{len(bot.guilds)} guilds")
    m = len(list(bot.get_all_members()))
    print(f"Serving {m} people")
    await bot.change_presence(status=discord.Status.online, activity=discord.Activity(type=discord.ActivityType.watching, name="Orbis"))
    print('We have logged in as {0.user}'.format(bot))

@bot.event
async def on_application_command_error(ctx: discord.ApplicationContext, error):
    debug_channel = bot.get_channel(949609712557637662)
    print(error)
    if isinstance(error, discord.HTTPException):
        await debug_channel.send(f'**Exception caught!**\nAuthor: {ctx.author}\nServer: {ctx.guild}\nCommand: {ctx.command}\n\nError:```{error}```')
    else:
        await ctx.send("Oh no! An unknown error occurred! Contact RandomNoobster#0093, and he might be able to help you out.")
        await debug_channel.send(f'**Exception raised!**\nAuthor: {ctx.author}\nServer: {ctx.guild}\nCommand: {ctx.command}\n\nError:```{error}```')

@bot.slash_command(name="ping", description="Pong!")
async def ping(ctx: discord.ApplicationContext):
    await ctx.respond(f'Pong! {round(bot.latency * 1000)}ms')

@bot.slash_command(
    name="verify",
    description='Link your nation with your discord account',
    )
async def verify(
    ctx: discord.ApplicationContext,
    nation_id: Option(str, "Your nation id or nation link"),
):
    user = mongo.global_users.find_one({"user": ctx.author.id})
    if user != None:
        await ctx.respond("You are already verified!")
        return
    nation_id = re.sub("[^0-9]", "", nation_id)
    async with aiohttp.ClientSession() as session:
        async with session.post(f"https://api.politicsandwar.com/graphql?api_key={api_key}", json={'query': f'{{nations(first:1 id:{nation_id}){{data{{id nation_name leader_name discord}}}}}}'}) as temp:
            res = await temp.json()
            try:
                if res['data']['nations']['data'][0]['discord'] == str(ctx.author):
                    mongo.global_users.insert_one({"user": ctx.author.id, "id": nation_id, "beige_alerts": []})
                    await ctx.respond("You have successfully verified your nation!")
                else:
                    await ctx.respond(f'1. Got to https://politicsandwar.com/nation/edit/\n2. Scroll down to where it says "Discord Username"\n3. Type `{ctx.author}` in the adjacent field.\n4. Come back to discord\n5. Write `$verify {nation_id}` again.')
            except KeyError:
                await ctx.respond(f"I could not find a nation with an id of `{nation_id}`")

async def alert_scanner():
    debug_channel = bot.get_channel(949609712557637662)
    while True:
        minute = 0
        now = datetime.utcnow()
        future = datetime(now.year, now.month, now.day, now.hour, minute)
        if now.minute >= minute:
            future += timedelta(hours=1, seconds=1)
        await asyncio.sleep((future-now).seconds)
        try:
            alerts = list(mongo.global_users.find({"beige_alerts": {"$exists": True, "$not": {"$size": 0}}}))
            for user in alerts:
                for alert in user['beige_alerts']:
                    if datetime.utcnow() >= alert['time']:
                        disc_user = await bot.fetch_user(user['user'])
                        try:
                            await disc_user.send(f"Hey, https://politicsandwar.com/nation/id={alert['id']} is out of beige!")
                        except:
                            await debug_channel.send(f"**Silly person**\nI was attempting to DM {disc_user} about a beige reminder, but I was unable to message them.")
                        user['beige_alerts'].remove(alert)
                        alert_list = user['beige_alerts']
                        if not alert_list:
                            alert_list = []
                        mongo.global_users.find_one_and_update({"user": user['user']}, {"$set": {"beige_alerts": alert_list}})
        except Exception as error:
            await debug_channel.send(f'**Exception raised!**\nWhere: Scanning beige alerts\n\nError:```{error}```')

keep_alive.keep_alive()

bot.bg_task = bot.loop.create_task(alert_scanner())
bot.run(os.getenv("bot_token"))