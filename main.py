from datetime import datetime, timedelta
import asyncio
from dotenv import load_dotenv
import keep_alive
import pymongo
import aiohttp
import os
import ssl
import re
import discord
from discord.ext import commands
intents = discord.Intents.default()
intents.members = True
load_dotenv()

client = pymongo.MongoClient(os.getenv("pymongolink"), ssl_cert_reqs=ssl.CERT_NONE)
version = os.getenv("version")
mongo = client[str(version)]
api_key = os.getenv("api_key")

bot = commands.Bot(command_prefix='$', intents=intents)

@bot.event
async def on_ready():
    print('Bot is ready')
    print("I am in ", len(bot.guilds), " servers:")
    for guild in bot.guilds:
        print(f"-> {guild} || {guild.member_count} members")
    await bot.change_presence(status=discord.Status.online, activity=discord.Activity(type=discord.ActivityType.watching, name="Orbis"))
    print('We have logged in as {0.user}'.format(bot))

@bot.event
async def on_command_error(ctx, error):
    debug_channel = bot.get_channel(949609712557637662)
    print(error)
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.CommandOnCooldown):
        em = discord.Embed(title=f"Slow it down bro!",description=f"Try again in {round(error.retry_after/60)} minutes.")
        await ctx.send(embed=em)
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have the permission to use this command!")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Something's wrong with your arguments!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"You don't have the required arguments! Use `$help {ctx.command}` to see the required arguments.")
    elif isinstance(error, commands.PrivateMessageOnly):
        await ctx.send("This command can only be used in private messages!")
    elif isinstance(error, commands.MissingAnyRole):
        await ctx.send("You do not have the roles required to use this command!")
    elif isinstance(error, commands.DisabledCommand):
        await ctx.send(f'{ctx.command} has been disabled!')
    elif isinstance(error, aiohttp.ClientOSError):
        await ctx.send("A really f***ing annoying error occurred, and there's no real way to fix it, so I'm pretty upset. You can just try again and it should work.\n-Randy")
    else:
        await ctx.send("Oh no! An unknown error occurred! Contact RandomNoobster#0093, and he might be able to help you out.")
        await debug_channel.send(f'**Exception raised!**\nAuthor: {ctx.author}\nServer: {ctx.guild}\nCommand: {ctx.command}\nArguments: {ctx.args}\n\nError:```{error}```')

if __name__ == "__main__": 
    bot.load_extension('raids')

@bot.command(brief='Imma pong yo ass')
async def ping(ctx):
    await ctx.send(f'Pong! {round(bot.latency * 1000)}ms')

@bot.command(
    brief='Link your nation with your discord account',
    help=f'1. Got to https://politicsandwar.com/nation/edit/\n2. Scroll down to where it says "Discord Username"\n3. Type your discord username in the adjacent field\n4. Come back to discord\n5. Write "$verify your_nation_id_here"\n\nYour nation id can be found by going to "View" under "Nation" in the menus. Your nation id should be towards the top of the box titled "Basic Information".'
    )
async def verify(ctx, nation_id):
    user = mongo.global_users.find_one({"user": ctx.author.id})
    if user != None:
        await ctx.send("You are already verified!")
        return
    nation_id = re.sub("[^0-9]", "", nation_id)
    async with aiohttp.ClientSession() as session:
        async with session.post(f"https://api.politicsandwar.com/graphql?api_key={api_key}", json={'query': f'{{nations(first:1 id:{nation_id}){{data{{id nation_name leader_name discord}}}}}}'}) as temp:
            res = await temp.json()
            if len(res['data']['nations']['data']) == 0:
                await ctx.send(f"I could not find the nation with an id of `{nation_id}`")
                return
            if res['data']['nations']['data'][0]['discord'] == str(ctx.author):
                mongo.global_users.insert_one({"user": ctx.author.id, "id": nation_id, "beige_alerts": []})
                await ctx.send("You have successfully verified your nation!")
            else:
                await ctx.send(f'1. Got to https://politicsandwar.com/nation/edit/\n2. Scroll down to where it says "Discord Username"\n3. Type `{ctx.author}` in the adjacent field.\n4. Come back to discord\n5. Write `$verify {nation_id}` again.')
@verify.error
async def verify_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("You have to include your nation id or a link to your nation!")

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
                            debug_channel.send(f"**Silly person**\nI was attempting to DM {disc_user} about a beige reminder, but I was unable to message them.")
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