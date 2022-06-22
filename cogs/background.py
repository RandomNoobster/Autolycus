import os
import traceback
from discord.ext import commands
from datetime import datetime, timedelta
import pathlib
from main import mongo, logger
import utils
import aiohttp
import time
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
            await asyncio.sleep((future-now).seconds+1)
            try:
                alerts = list(mongo.global_users.find({"beige_alerts": {"$exists": True, "$not": {"$size": 0}}}))
                nation_ids = []
                for user in alerts:
                    for alert in user['beige_alerts']:
                        nation_ids.append(alert)
                unique_ids = list(set(nation_ids))

                res = (await utils.call(f"{{nations(id:[{','.join(unique_ids)}]){{data{{id beige_turns}}}}}}"))['data']['nations']['data']

                for user in alerts:
                    for alert in user['beige_alerts']:
                        for nation in res:
                            if alert == nation['id']:
                                if nation['beige_turns'] <= 1:
                                    disc_user = await self.bot.fetch_user(user['user'])
                                    if nation['beige_turns'] == 1:
                                        turns = int(nation['beige_turns'])
                                        time = datetime.utcnow()
                                        if time.hour % 2 == 0:
                                            break
                                        else:
                                            time += timedelta(hours=turns*2-1)
                                        time = datetime(time.year, time.month, time.day, time.hour)
                                        content = f"Hey, https://politicsandwar.com/nation/id={alert} is leaving beige <t:{round(time.timestamp())}:R>!"
                                    else:
                                        content = f"Hey, https://politicsandwar.com/nation/id={alert} has left beige prematurely!"
                                    try:
                                        await disc_user.send(content)
                                    except:
                                        await debug_channel.send(f"**Silly person**\nI was attempting to DM {disc_user} about a beige reminder, but I was unable to message them.")
                                    mongo.global_users.find_one_and_update({"user": user['user']}, {"$pull": {"beige_alerts": alert}})
                                break
            except Exception as e:
                await debug_channel.send(f'**Exception __caught__!**\nWhere: Scanning beige alerts\n\nError:```{traceback.format_exc()}```')
                logger.error(e, exc_info=True)

def setup(bot):
    bot.add_cog(General(bot))