from dotenv import load_dotenv
import keep_alive
import pymongo
import aiohttp
import os
from discord.commands import Option
from discord.bot import ApplicationCommandMixin
import re
import asyncio
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
    if "MissingPermissions" in str(error):
        await ctx.respond(error.original)
    elif isinstance(error, (discord.HTTPException, discord.errors.NotFound)):
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
    res = await call(f'{{nations(first:1 id:{nation_id}){{data{{id nation_name leader_name discord}}}}}}')
    try:
        if res['data']['nations']['data'][0]['discord'] == str(ctx.author):
            mongo.global_users.insert_one({"user": ctx.author.id, "id": nation_id, "beige_alerts": []})
            await ctx.respond("You have successfully verified your nation!")
        else:
            await ctx.respond(f'1. Got to https://politicsandwar.com/nation/edit/\n2. Scroll down to where it says "Discord Username"\n3. Type `{ctx.author}` in the adjacent field.\n4. Come back to discord\n5. Write `/verify {nation_id}` again.')
    except (KeyError, IndexError):
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

async def call(data: dict = None, key: str = api_key):
    async with aiohttp.ClientSession() as session:
        while True:
            async with session.post(f'https://api.politicsandwar.com/graphql?api_key={key}', json={"query": data}) as response:
                try:
                    await asyncio.sleep(int(response.headers['Retry-After']))
                    continue
                except:
                    pass
                json_response = await response.json()
                try:
                    errors = json_response['errors']
                except:
                    errors = None
                return json_response


keep_alive.run()
bot.run(os.getenv("bot_token"))