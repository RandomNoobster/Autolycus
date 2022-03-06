from dotenv import load_dotenv
import keep_alive
import pymongo
import aiohttp
import os
import ssl
from discord.commands import Option
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

bot = commands.Bot(intents=intents)

if __name__ == "__main__": 
    bot.load_extension('raids')

@bot.event
async def on_ready():
    print('Bot is ready')
    print("I am in ", len(bot.guilds), " servers:")
    for guild in bot.guilds:
        print(f"-> {guild} || {guild.member_count} members")
    await bot.change_presence(status=discord.Status.online, activity=discord.Activity(type=discord.ActivityType.watching, name="Orbis"))
    print('We have logged in as {0.user}'.format(bot))

@bot.event
async def on_application_command_error(ctx: discord.ApplicationContext, error):
    debug_channel = bot.get_channel(949609712557637662)
    print(error)
    await ctx.send("Oh no! An unknown error occurred! Contact RandomNoobster#0093, and he might be able to help you out.")
    await debug_channel.send(f'**Exception raised!**\nAuthor: {ctx.author}\nServer: {ctx.guild}\nCommand: {ctx.command}\n\nError:```{error}```')

@bot.slash_command(guild_ids=[729979781940248577], name="ping", description="Pong!")
async def ping(ctx: discord.ApplicationContext):
    await ctx.respond(f'Pong! {round(bot.latency * 1000)}ms')

@bot.slash_command(
    guild_ids=[729979781940248577],
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
            if len(res['data']['nations']['data']) == 0:
                await ctx.respond(f"I could not find the nation with an id of `{nation_id}`")
                return
            if res['data']['nations']['data'][0]['discord'] == str(ctx.author):
                mongo.global_users.insert_one({"user": ctx.author.id, "id": nation_id, "beige_alerts": []})
                await ctx.respond("You have successfully verified your nation!")
            else:
                await ctx.respond(f'1. Got to https://politicsandwar.com/nation/edit/\n2. Scroll down to where it says "Discord Username"\n3. Type `{ctx.author}` in the adjacent field.\n4. Come back to discord\n5. Write `$verify {nation_id}` again.')
   

keep_alive.keep_alive()

bot.run(os.getenv("bot_token"))