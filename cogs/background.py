import os
import traceback
from discord.ext import commands
from datetime import datetime, timedelta
import pathlib
from main import mongo
import utils
import aiohttp
import asyncio
from dotenv import load_dotenv
import json
load_dotenv()

api_key = os.getenv("api_key")
channel_id = int(os.getenv("debug_channel"))

api_key = os.getenv("api_key")

class General(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.bot.bg_task = self.bot.loop.create_task(self.nation_scanner())
        self.bot.bg_task = self.bot.loop.create_task(self.alert_scanner())

    async def alert_scanner(self):
        await self.bot.wait_until_ready()
        debug_channel = self.bot.get_channel(channel_id)
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
                        if datetime.utcnow() >= alert['time'] - timedelta(minutes=11):
                            disc_user = await self.bot.fetch_user(user['user'])
                            try:
                                await disc_user.send(f"Hey, https://politicsandwar.com/nation/id={alert['id']} is leaving beige <t:{round(alert['time'].timestamp())}:R>!")
                            except:
                                await debug_channel.send(f"**Silly person**\nI was attempting to DM {disc_user} about a beige reminder, but I was unable to message them.")
                            user['beige_alerts'].remove(alert)
                            alert_list = user['beige_alerts']
                            if not alert_list:
                                alert_list = []
                            mongo.global_users.find_one_and_update({"user": user['user']}, {"$set": {"beige_alerts": alert_list}})
            except:
                await debug_channel.send(f'**Exception raised!**\nWhere: Scanning beige alerts\n\nError:```{traceback.format_exc()}```')

    async def nation_scanner(self):
        await self.bot.wait_until_ready()
        debug_channel = self.bot.get_channel(channel_id)
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
                            resp = await utils.call(f"{{nations(page:{n} first:{first} vmode:false min_score:15 orderBy:{{column:DATE order:ASC}}){{paginatorInfo{{hasMorePages}} data{{id discord leader_name nation_name flag last_active alliance_position_id continent dompolicy population alliance_id beigeturns score color soldiers tanks aircraft ships missiles nukes bounties{{amount type}} treasures{{name}} alliance{{name}} wars{{date winner defid turnsleft attacks{{loot_info victor moneystolen}}}} alliance_position num_cities ironw bauxitew armss egr massirr itc recycling_initiative telecom_satellite green_tech clinical_research_center specialized_police_training uap cities{{date powered infrastructure land oilpower windpower coalpower nuclearpower coalmine oilwell uramine barracks farm policestation hospital recyclingcenter subway supermarket bank mall stadium leadmine ironmine bauxitemine gasrefinery aluminumrefinery steelmill munitionsfactory factory airforcebase drydock}}}}}}}}")
                            new_nations['nations'] += resp['data']['nations']['data']
                            more_pages = resp['data']['nations']['paginatorInfo']['hasMorePages']
                        except (aiohttp.client_exceptions.ContentTypeError, TypeError):
                            continue
                        n += 1
                    new_nations['last_fetched'] = round(datetime.utcnow().timestamp())
                    with open(pathlib.Path.cwd() / 'nations.json', 'w') as json_file:
                        json.dump(new_nations, json_file)
                    print("done fetching")
                    #await asyncio.sleep(600)
            except:
                await debug_channel.send(f'**Exception raised!**\nWhere: Scanning nations\n\nError:```{traceback.format_exc()}```')
                await asyncio.sleep(300)

def setup(bot):
    bot.add_cog(General(bot))