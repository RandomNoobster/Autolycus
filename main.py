import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
import keep_alive
import pymongo
import aiohttp
import os
from discord.commands import Option, permissions
from discord.bot import ApplicationCommandMixin
import re
import json
import pathlib
import discord
from discord.ext import commands
load_dotenv()

client = pymongo.MongoClient(os.getenv("pymongolink"))
version = os.getenv("version")
mongo = client[str(version)]
api_key = os.getenv("api_key")
channel_id = int(os.getenv("debug_channel"))

bot = commands.Bot()

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
    await bot.change_presence(status=discord.Status.online, activity=discord.Activity(type=discord.ActivityType.watching, name="Orbis"))
    print('We have logged in as {0.user}'.format(bot))

@bot.event
async def on_application_command_error(ctx: discord.ApplicationContext, error):
    debug_channel = bot.get_channel(channel_id)
    print(error)
    print(type(error))
    if isinstance(error, (discord.HTTPException, discord.errors.NotFound, discord.ApplicationCommandInvokeError)):
        await debug_channel.send(f'**Exception __caught__!**\nAuthor: {ctx.author}\nServer: {ctx.guild}\nCommand: {ctx.command}\nType: {type(error)}\n\nError:```{error}```')
    else:
        await ctx.send("Oh no! An unknown error occurred! Contact RandomNoobster#0093, and he might be able to help you out.")
        await debug_channel.send(f'**Exception raised!**\nAuthor: {ctx.author}\nServer: {ctx.guild}\nCommand: {ctx.command}\nType: {type(error)}\n\nError:```{error}```')

@bot.slash_command(name="ping", description="Pong!")
async def ping(ctx: discord.ApplicationContext):
    await ctx.respond(f'Pong! {round(bot.latency * 1000)}ms')

@bot.slash_command(
    name="botinfo",
    description="Information about the bot"
)
async def botinfo(ctx: discord.ApplicationContext):
    await ctx.defer()
    slash_guilds = len(bot.guilds)
    total_people = 0
    for guild in bot.guilds:
        total_people += guild.member_count
        try:
            await ApplicationCommandMixin.get_desynced_commands(bot, guild.id)
        except discord.errors.Forbidden:
            slash_guilds -= 1
    content = f"I am serving {total_people} people across {len(bot.guilds)} servers.\nSlash commands are allowed in {slash_guilds}/{len(bot.guilds)} guilds."
    embed = discord.Embed(title="My guilds:", description=content, color=0xff5100)
    embed.set_footer(text="Contact RandomNoobster#0093 for help or bug reports")
    await ctx.respond(embed=embed)

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
                    await ctx.respond(f'1. Got to https://politicsandwar.com/nation/edit/\n2. Scroll down to where it says "Discord Username"\n3. Type `{ctx.author}` in the adjacent field.\n4. Come back to discord\n5. Write `/verify {nation_id}` again.')
            except KeyError:
                await ctx.respond(f"I could not find a nation with an id of `{nation_id}`")

@bot.slash_command(
    name="unverify",
    description='Unlink your nation from your discord account',
)
async def unverify(
    ctx: discord.ApplicationContext,
):
    user = mongo.global_users.find_one_and_delete({"user": ctx.author.id})
    if user == None:
        await ctx.respond("You are not verified!")
        return
    else:
        await ctx.respond("Your discord account was successfully unlinked from your nation.")

@bot.slash_command(
    name="help",
    description="Returns all commands",
)
async def help(ctx):
    help_text = ""
    for command in list(bot._application_commands.values())[1:]:
        help_text += f"`{command}` - {command.description}\n"
    embed = discord.Embed(title="Command list", description=help_text, color=0xff5100)
    embed.set_footer(text="Contact RandomNoobster#0093 for help or bug reports")
    await ctx.respond(embed=embed)

async def alert_scanner():
    await bot.wait_until_ready()
    debug_channel = bot.get_channel(channel_id)
    while True:
        minute = 50
        now = datetime.utcnow()
        future = datetime(now.year, now.month, now.day, now.hour, minute)
        if now.minute >= minute:
            future += timedelta(hours=1, seconds=1)
        await asyncio.sleep((future-now).seconds)
        try:
            alerts = list(mongo.global_users.find({"beige_alerts": {"$exists": True, "$not": {"$size": 0}}}))
            for user in alerts:
                for alert in user['beige_alerts']:
                    if datetime.utcnow() >= alert['time'] - timedelta(minutes=10):
                        disc_user = await bot.fetch_user(user['user'])
                        try:
                            await disc_user.send(f"Hey, https://politicsandwar.com/nation/id={alert['id']} is leaving beige <t:{round(alert['time'].timestamp())}:R>!")
                        except:
                            await debug_channel.send(f"**Silly person**\nI was attempting to DM {disc_user} about a beige reminder, but I was unable to message them.")
                        user['beige_alerts'].remove(alert)
                        alert_list = user['beige_alerts']
                        if not alert_list:
                            alert_list = []
                        mongo.global_users.find_one_and_update({"user": user['user']}, {"$set": {"beige_alerts": alert_list}})
        except Exception as error:
            await debug_channel.send(f'**Exception raised!**\nWhere: Scanning beige alerts\n\nError:```{error}```')

async def nation_scanner():
    await bot.wait_until_ready()
    debug_channel = bot.get_channel(channel_id)
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                more_pages = True
                n = 1
                first = 75
                new_nations = {"last_fetched": None, "nations": []}
                while more_pages:
                    try:
                        await asyncio.sleep(3)
                        async with session.post(f"https://api.politicsandwar.com/graphql?api_key={api_key}", json={'query': f"{{nations(page:{n} first:{first} vmode:false min_score:15 orderBy:{{column:DATE order:ASC}}){{paginatorInfo{{hasMorePages}} data{{id discord leader_name nation_name flag last_active alliance_position_id continent dompolicy population alliance_id beigeturns score color soldiers tanks aircraft ships missiles nukes bounties{{amount type}} treasures{{name}} alliance{{name}} wars{{date winner defid turnsleft attacks{{loot_info victor moneystolen}}}} alliance_position num_cities ironw bauxitew armss egr massirr itc recycling_initiative telecom_satellite green_tech clinical_research_center specialized_police_training uap cities{{date powered infrastructure land oilpower windpower coalpower nuclearpower coalmine oilwell uramine barracks farm policestation hospital recyclingcenter subway supermarket bank mall stadium leadmine ironmine bauxitemine gasrefinery aluminumrefinery steelmill munitionsfactory factory airforcebase drydock}}}}}}}}"}) as temp:
                            resp = await temp.json()
                            new_nations['nations'] += resp['data']['nations']['data']
                            more_pages = resp['data']['nations']['paginatorInfo']['hasMorePages']
                    except (aiohttp.client_exceptions.ContentTypeError, TypeError) as e:
                        continue
                    n += 1
                new_nations['last_fetched'] = round(datetime.utcnow().timestamp())
                with open(pathlib.Path.cwd() / 'nations.json', 'w') as json_file:
                    json.dump(new_nations, json_file)
                print("done fetching")
                #await asyncio.sleep(600)
        except Exception as error:
            await debug_channel.send(f'**Exception raised!**\nWhere: Scanning nations\n\nError:```{error}```')
            await asyncio.sleep(300)

keep_alive.run()

bot.bg_task = bot.loop.create_task(alert_scanner())
bot.bg_task = bot.loop.create_task(nation_scanner())
bot.run(os.getenv("bot_token"))