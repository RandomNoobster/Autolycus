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
import math
import pathlib
import utils
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
    if isinstance(error, discord.HTTPException) or isinstance(error, discord.errors.NotFound):
        await debug_channel.send(f'**Exception __caught__!**\nAuthor: {ctx.author}\nServer: {ctx.guild}\nCommand: {ctx.command}\nType: {type(error)}\n\nError:```{error}```')
    else:
        await ctx.send("Oh no! An unknown error occurred! Contact RandomNoobster#0093, and he might be able to help you out.")
        await debug_channel.send(f'**Exception raised!**\nAuthor: {ctx.author}\nServer: {ctx.guild}\nCommand: {ctx.command}\nType: {type(error)}\n\nError:```{error}```')

@bot.slash_command(name="ping", description="Pong!")
async def ping(ctx: discord.ApplicationContext):
    await ctx.respond(f'Pong! {round(bot.latency * 1000)}ms')

@bot.slash_command(
    name="status",
    description="Information about the guilds I am in"
)
@permissions.is_user(465463547200012298)
async def status(ctx: discord.ApplicationContext):
    await ctx.defer()
    content = ""
    for guild in bot.guilds:
        extra = ""
        try:
            await ApplicationCommandMixin.get_desynced_commands(bot, guild.id)
        except discord.errors.Forbidden:
            extra = f"|| Slash disallowed"
            n -= 1
        content += f"\n-> {guild} || {guild.member_count} members {extra}"
    content += f"\nSlash commands are allowed in {n}/{len(bot.guilds)} guilds"
    await ctx.respond()

@bot.slash_command(
    name="who",
    description="Get more information about someone's nation",
)
async def who(
    ctx: discord.ApplicationContext,
    person: Option(str, "") = None,
):
    await ctx.defer()
    if person == None:
        person = ctx.author.id
    nation = utils.find_nation_plus(bot, person)
    if nation == None:
        await ctx.respond(content="I did not find that nation!")
        return

    async with aiohttp.ClientSession() as session:
        async with session.post(f"https://api.politicsandwar.com/graphql?api_key={api_key}", json={"query": f"{{nations(first:1 id:{nation['id']}){{data{{id nation_name discord leader_name num_cities cia spy_satellite warpolicy population dompolicy flag vmode color beigeturns last_active soldiers tanks aircraft ships nukes missiles mlp nrf vds irond wars{{attid turnsleft}} cities{{barracks factory airforcebase drydock}} score alliance_position alliance_seniority alliance{{name id score color nations{{id}}}}}}}}}}"}) as temp:
            nation = (await temp.json())['data']['nations']['data'][0]

    embed = discord.Embed(title=nation['nation_name'], url=f"https://politicsandwar.com/nation/id={nation['id']}", color=0xff5100)
    user = utils.find_user(bot, nation['id'])
    if not user:
        discord_info = "> Autolycus Verified: <:redcross:862669500977905694>"
        if nation['discord']:
            discord_info += f"\n> Discord Username: {nation['discord']}"
    else:
        username = await bot.fetch_user(user['user'])
        discord_info = f"> Verified: ✅\n> Discord Username: {username} `({username.id})`"
    embed.add_field(name="Discord Info", value=discord_info, inline=False)

    nation_info = f"> Nation Name: [{nation['nation_name']}](https://politicsandwar.com/nation/id={nation['id']})\n> Leader Name: {nation['leader_name']}\n> Cities: [{nation['num_cities']}](https://politicsandwar.com/city/manager/n={nation['nation_name'].replace(' ', '%20')})\n> War Policy: [{nation['warpolicy']}](https://politicsandwar.com/pwpedia/war-policy/)\n> Dom. Policy: [{nation['dompolicy']}](https://politicsandwar.com/pwpedia/domestic-policy/)"
    embed.add_field(name="Nation Info", value=nation_info)

    nation_info_2 = f"> Score: `{nation['score']}`\n> Def. Range: `{round(nation['score']/1.75)}`-`{round(nation['score']/0.75)}`\n> Off. Range: `{round(nation['score']*0.75)}`-`{round(nation['score']*1.75)}`\n> Color: {nation['color'].capitalize()}\n> Turns of VM: `{nation['vmode']}`"
    embed.add_field(name="\u200b", value=nation_info_2)

    if nation['alliance']:
        alliance_info = f"> Alliance: [{nation['alliance']['name']}](https://politicsandwar.com/alliance/id={nation['alliance']['id']})\n> Position: {nation['alliance_position'].capitalize()}\n> Seniority: {nation['alliance_seniority']:,} days\n> Score: `{nation['alliance']['score']:,}`\n> Color: {nation['alliance']['color'].capitalize()}\n> Members: `{len(nation['alliance']['nations'])}`"
    else:
        alliance_info = f"> Alliance: None"
    embed.add_field(name="Alliance Info", value=alliance_info, inline=False)

    spy_count = await utils.spy_calc(nation)
    if nation['spy_satellite']:
        daily_rebuy = 3
    else:
        daily_rebuy = 2
    if nation['cia']:
        max_spies = 60
    else:
        max_spies = 50
    spies = f"`{spy_count}`/`{max_spies}`/`{math.ceil((max_spies-spy_count)/daily_rebuy)}`"

    milt = utils.militarization_checker(nation)
    military_info = f"> Format: `Current`/`Cap`/`Days`\n> Soldiers: `{nation['soldiers']:,}`/`{milt['max_soldiers']:,}`/`{milt['soldiers_days']:,}`\n> Tanks: `{nation['tanks']:,}`/`{milt['max_tanks']:,}`/`{milt['tanks_days']:,}`\n> Aircraft: `{nation['aircraft']:,}`/`{milt['max_aircraft']:,}`/`{milt['aircraft_days']:,}`\n> Ships: `{nation['ships']:,}`/`{milt['max_ships']:,}`/`{milt['ships_days']:,}`\n> Spies: {spies}\n> MMR: `{milt['barracks_mmr']}`/`{milt['factory_mmr']}`/`{milt['hangar_mmr']}`/`{milt['drydock_mmr']}`"
    embed.add_field(name="Military Info", value=military_info)

    missiles = str(nation['missiles'])
    if not nation['mlp']:
        missiles += " (No Project)"
    nukes = str(nation['nukes'])
    if not nation['nrf']:
        nukes += " (No Project)"

    o_wars = 0
    d_wars = 0
    for war in nation['wars']:
        if war['turnsleft'] > 0:
            if war['attid'] == nation['id']:
                o_wars += 1
            else:
                d_wars += 1

    if nation['irond']:
        dome = "Yes"
    else:
        dome = "No"
    if nation['vds']:
        vital = "Yes"
    else:
        vital = "No"

    military_info_2 = f"> Offensive Wars: `{o_wars}`/`5`\n> Defensive Wars: `{d_wars}`/`3`\n> Missiles: `{missiles}`\n> Nukes: `{nukes}`\n> Iron Dome: {dome}\n> Vital Defense: {vital}\n> Turns of Beige: `{nation['beigeturns']}`"
    embed.add_field(name="\u200b", value=military_info_2)

    embed.set_thumbnail(url=nation['flag'])

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
                first = 50
                new_nations = {"last_fetched": None, "nations": []}
                while more_pages:
                    try:
                        await asyncio.sleep(2)
                        async with session.post(f"https://api.politicsandwar.com/graphql?api_key={api_key}", json={'query': f"{{nations(page:{n} first:{first} vmode:false orderBy:{{column:DATE order:ASC}}){{paginatorInfo{{hasMorePages}} data{{id discord leader_name nation_name flag last_active continent dompolicy population alliance_id beigeturns score color soldiers tanks aircraft ships missiles nukes bounties{{amount war_type}} treasures{{name}} alliance{{name}} wars{{date winner defid turnsleft attacks{{loot_info victor moneystolen}}}} alliance_position num_cities ironw bauxitew armss egr massirr itc recycling_initiative telecom_satellite green_tech clinical_research_center specialized_police_training uap cities{{date powered infrastructure land oilpower windpower coalpower nuclearpower coalmine oilwell uramine barracks farm policestation hospital recyclingcenter subway supermarket bank mall stadium leadmine ironmine bauxitemine gasrefinery aluminumrefinery steelmill munitionsfactory factory airforcebase drydock}}}}}}}}"}) as temp:
                            resp = await temp.json()
                            new_nations['nations'] += resp['data']['nations']['data']
                            more_pages = resp['data']['nations']['paginatorInfo']['hasMorePages']
                    except (aiohttp.client_exceptions.ContentTypeError, TypeError) as e:
                        continue
                    n += 1
                new_nations['last_fetched'] = round(datetime.utcnow().timestamp())
                with open(pathlib.Path.cwd() / 'nations.json', 'w') as json_file:
                    json.dump(new_nations, json_file)
        except Exception as error:
            await debug_channel.send(f'**Exception raised!**\nWhere: Scanning nations\n\nError:```{error}```')

keep_alive.run()

bot.bg_task = bot.loop.create_task(alert_scanner())
bot.bg_task = bot.loop.create_task(nation_scanner())
bot.run(os.getenv("bot_token"))