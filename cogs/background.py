import os
import traceback
from discord.ext import commands
from datetime import datetime, timedelta, timezone
import pathlib
from main import mongo, logger, client
import utils
import aiohttp
import time
import discord
from typing import Union
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
        self.bot.bg_task = self.bot.loop.create_task(self.wars())

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

    async def nation_scanner(self):
        await self.bot.wait_until_ready()
        debug_channel = self.bot.get_channel(channel_id)
        while True:
            try:
                series_start = time.time()
                more_pages = True
                n = 1
                first = 75
                new_nations = {"last_fetched": None, "nations": []}
                while more_pages:
                    start = time.time()
                    try:
                        await asyncio.sleep(1)
                        resp = await utils.call(f"{{nations(page:{n} first:{first} vmode:false min_score:15 orderBy:{{column:DATE order:ASC}}){{paginatorInfo{{hasMorePages}} data{{id discord leader_name nation_name warpolicy vacation_mode_turns flag last_active alliance_position_id continent dompolicy vds irond population alliance_id beige_turns score color soldiers tanks aircraft ships missiles nukes bounties{{amount type}} treasures{{name}} alliance{{name id}} wars{{date winner attacker{{war_policy}} defender{{war_policy}} war_type defid turnsleft attacks{{loot_info victor moneystolen}}}} alliance_position num_cities ironw bauxitew armss egr massirr itc recycling_initiative telecom_satellite green_tech clinical_research_center specialized_police_training uap cities{{date powered infrastructure land oilpower windpower coalpower nuclearpower coalmine oilwell uramine barracks farm policestation hospital recyclingcenter subway supermarket bank mall stadium leadmine ironmine bauxitemine gasrefinery aluminumrefinery steelmill munitionsfactory factory airforcebase drydock}}}}}}}}")
                        new_nations['nations'] += resp['data']['nations']['data']
                        more_pages = resp['data']['nations']['paginatorInfo']['hasMorePages']
                    except (aiohttp.client_exceptions.ContentTypeError, TypeError):
                        logger.info("Retrying fetch")
                        continue
                    n += 1
                    logger.debug(f"Fetched page {n}, took {time.time() - start:.2f} seconds")
                new_nations['last_fetched'] = round(datetime.utcnow().timestamp())
                with open(pathlib.Path.cwd() / 'nations.json', 'w') as json_file:
                    json.dump(new_nations, json_file)
                logger.info(f"Done fetching nation data. {n} pages, took {(time.time() - series_start) / 60 :.2f} minutes")
            except Exception as e:
                logger.error(e, exc_info=True)
                await debug_channel.send(f'**Exception __caught__!**\nWhere: Scanning nations\n\nError:```{traceback.format_exc()}```')
                await asyncio.sleep(300)

    async def add_to_thread(self, thread, atom_id: Union[str, int], atom: dict = None):
        person = utils.find_user(self, atom_id)
        if not person:
            print("tried to add, but could not find", atom_id)
            if atom:
                await thread.send(f"I was unable to add {atom['leader_name']} of {atom['nation_name']} to the thread. Have they not verified with `/verify`?")
            else:
                await thread.send(f"I was unable to add nation {atom_id} to the thread. Have they not verified with `/verify`?")
            return
        user = await self.bot.fetch_user(person['user'])
        try:
            await thread.add_user(user)
        except Exception as e:
            await thread.send(f"I was unable to add {user} to the thread.\n```{e}```")
    
    async def remove_from_thread(self, thread, atom_id: Union[str, int], atom: dict = None):
        person = utils.find_user(self, atom_id)
        if not person:
            print("tried to remove, but could not find", atom_id)
            if atom:
                await thread.send(f"I was unable to remove {atom['leader_name']} of {atom['nation_name']} from the thread. Have they not verified with `/verify`?")
            else:
                await thread.send(f"I was unable to remove nation {atom_id} from the thread. Have they not verified with `/verify`?")
            return
        user = await self.bot.fetch_user(person['user'])
        try:
            await thread.remove_user(user)
        except:
            await thread.send(f"I was unable to remove {user} from the thread.")
    
    async def wars(self):
        try:
            await self.bot.wait_until_ready()
            channel = None
            guild_id = None
            debug_channel = self.bot.get_channel(739155202640183377)
            
            async def cthread(war, non_atom, atom):
                url = f"https://politicsandwar.com/nation/war/timeline/war={war['id']}"
                if war['att_alliance_id'] in ["4729", "7531"]:
                    war_type = "Offensive"
                else:
                    war_type = "Defensive"
                footer = f"<t:{round(datetime.strptime(war['date'], '%Y-%m-%dT%H:%M:%S%z').timestamp())}:R> <t:{round(datetime.strptime(war['date'], '%Y-%m-%dT%H:%M:%S%z').timestamp())}>"
                embed = discord.Embed(title=f"New {war_type} War", url=url, description=f"[{war['attacker']['nation_name']}](https://politicsandwar.com/nation/id={war['attacker']['id']}) declared a{'n'[:(len(war['war_type'])-5)^1]} {war['war_type'].lower()} war on [{war['defender']['nation_name']}](https://politicsandwar.com/nation/id={war['defender']['id']}) for the reason of: ```{war['reason']}```\n{footer}", color=0x2F3136)
                name = f"{non_atom['nation_name']} ({non_atom['id']})"
                found = False

                for thread in channel.threads:
                    if f"({non_atom['id']})" in thread.name:
                        found = True
                        matching_thread = thread
                        break
                if not found:
                    async for thread in channel.archived_threads(limit=None):
                        if f"({non_atom['id']})" in thread.name:
                            found = True
                            matching_thread = thread
                            break
                if not found:
                    message = await channel.send(embed=embed)
                    try:
                        try:
                            thread = await channel.create_thread(name=name, message=message, auto_archive_duration=4320, type=discord.ChannelType.private_thread, reason="War declaration")
                        except:
                            thread = await channel.create_thread(name=name, message=message, auto_archive_duration=1440, type=discord.ChannelType.private_thread, reason="War declaration")
                    except discord.errors.HTTPException as e:
                        await debug_channel.send(f"I encountered an error when creating a thread: ```{e}```")
                        return
                    await self.add_to_thread(thread, atom['id'], atom)
                elif found:
                    await matching_thread.send(embed=embed)
                    await self.add_to_thread(matching_thread, atom['id'], atom)
                
                attack_logs = {"id": war['id'], "guild_id": guild_id, "attacks": [], "detected": datetime.utcnow(), "finished": False}
                mongo.war_logs.insert_one(attack_logs)

                return attack_logs, thread

            async def smsg(attacker_id, attack, war, atom, non_atom, peace):
                url = f"https://politicsandwar.com/nation/war/timeline/war={war['id']}"
                if war['att_alliance_id'] in ["4729", "7531"]:
                    war_type = "Offensive"
                else:
                    war_type = "Defensive"
                embed = discord.Embed(title=f"New {war_type} War", url=url, description=f"[{war['attacker']['nation_name']}](https://politicsandwar.com/nation/id={war['attacker']['id']}) declared a{'n'[:(len(war['war_type'])-5)^1]} {war['war_type'].lower()} war on [{war['defender']['nation_name']}](https://politicsandwar.com/nation/id={war['defender']['id']}) for the reason of: ```{war['reason']}```", color=0x2F3136)
                
                found = False
                for thread in channel.threads:
                    if f"({non_atom['id']})" in thread.name:
                        matching_thread = thread
                        found = True
                        break
                
                if not found:
                    async for thread in channel.archived_threads(limit=None):
                        if f"({non_atom['id']})" in thread.name:
                            matching_thread = thread
                            found = True
                            person = utils.find_user(self, atom['id'])
                            if not person:
                                print("tried to add to archived thread, but could not find", atom['id'])
                                await thread.send(f"I was unable to add nation {atom['id']} to the thread. Have they not linked their nation with their discord account?")
                                break
                            user = await self.bot.fetch_user(person['user'])
                            try:
                                await thread.add_user(user)
                            except:
                                pass
                            break
                
                if not found:
                    print("making thread")
                    temp, thread = await cthread(war, non_atom, atom)
                    # since found is not set to true, the attack is skipped and is sent in the next iteration of the wars
                    
                if found:
                    thread = matching_thread
                    url = f"https://politicsandwar.com/nation/war/timeline/war={war['id']}"
                    if peace != None:
                        embed = discord.Embed(title="Peace offering", url=url, description=f"[{peace['offerer']['nation_name']}](https://politicsandwar.com/nation/id={peace['offerer']['id']}) is offering peace to [{peace['reciever']['nation_name']}](https://politicsandwar.com/nation/id={peace['reciever']['id']}). The peace offering will be canceled if either side performs an act of aggression.", color=0xffffff)
                        await thread.send(embed=embed)
                        return
                    footer = f"<t:{round(datetime.strptime(attack['date'], '%Y-%m-%dT%H:%M:%S%z').timestamp())}:R> <t:{round(datetime.strptime(attack['date'], '%Y-%m-%dT%H:%M:%S%z').timestamp())}>"
                    if attack['type'] in ["GROUND", "NAVAL", "AIRVINFRA", "AIRVSOLDIERS", "AIRVTANKS", "AIRVMONEY", "AIRVSHIPS", "AIRVAIR"]:
                        for nation in [war['attacker'], war['defender']]:
                            if nation['id'] == attacker_id:
                                attacker_nation = nation
                            elif nation['id'] != attacker_id:
                                defender_nation = nation

                        colors = [0xff0000, 0xffff00, 0xffff00, 0x00ff00]
                        if attacker_nation['id'] == non_atom['id']:
                            colors.reverse()

                        if attack['success'] == 3:
                            success = "Immense Triumph"
                        elif attack['success'] == 2:
                            success = "Moderate Success"
                        elif attack['success'] == 1:
                            success = "Pyrrhic Victory"
                        elif attack['success'] == 0:
                            success = "Utter Failure"

                        description = f"Success: {success}"

                        if attack['type'] == "GROUND":
                            if attack['aircraft_killed_by_tanks']:
                                aircraft = f"\n{attack['aircraft_killed_by_tanks']:,} aircraft"
                            else:
                                aircraft = ""
                            title = "Ground battle"
                            att_casualties = f"{attack['attcas1']:,} soldiers\n{attack['attcas2']:,} tanks"
                            def_casualties = f"{attack['defcas1']:,} soldiers\n{attack['defcas2']:,} tanks{aircraft}"
                        elif attack['type'] == "NAVAL":
                            title = "Naval Battle"
                            att_casualties = f"{attack['attcas1']:,} ships"
                            def_casualties = f"{attack['defcas1']:,} ships"
                        elif attack['type'] == "AIRVINFRA":
                            title = "Airstrike targeting infrastructure"
                            att_casualties = f"{attack['attcas1']:,} planes"
                            def_casualties = f"{attack['defcas1']:,} planes\n{attack['infradestroyed']} infra (${attack['infra_destroyed_value']:,})"
                        elif attack['type'] == "AIRVSOLDIERS":
                            title = "Airstrike targeting soldiers"
                            att_casualties = f"{attack['attcas1']:,} planes"
                            def_casualties = f"{attack['defcas1']:,} planes\n{attack['defcas2']} soldiers"
                        elif attack['type'] == "AIRVTANKS":
                            title = "Airstrike targeting tanks"
                            att_casualties = f"{attack['attcas1']:,} planes"
                            def_casualties = f"{attack['defcas1']:,} planes\n{attack['defcas2']} tanks"
                        elif attack['type'] == "AIRVMONEY":
                            title = "Airstrike targeting money"
                            att_casualties = f"{attack['attcas1']:,} planes"
                            def_casualties = f"{attack['defcas1']:,} planes\n{attack['defcas2']} money"
                        elif attack['type'] == "AIRVSHIPS":
                            title = "Airstrike targeting ships"
                            att_casualties = f"{attack['attcas1']:,} planes"
                            def_casualties = f"{attack['defcas1']:,} planes\n{attack['defcas2']} ships"
                        elif attack['type'] == "AIRVAIR":
                            title = "Airstrike targeting aircraft"
                            att_casualties = f"{attack['attcas1']:,} planes"
                            def_casualties = f"{attack['defcas1']:,} planes"
                        try:
                            aaa_link = f"[{attacker_nation['alliance']['name']}](https://politicsandwar.com/alliance/id={attacker_nation['alliance_id']})"
                        except:
                            aaa_link = "No alliance"
                        try:
                            daa_link = f"[{defender_nation['alliance']['name']}](https://politicsandwar.com/alliance/id={defender_nation['alliance_id']})"
                        except:
                            daa_link = "No alliance"

                        embed = discord.Embed(title=title, description=description, color=colors[attack['success']], url=url)
                        embed.add_field(name=f"Attacker", value=f"[{attacker_nation['nation_name']}](https://politicsandwar.com/nation/id={attacker_nation['id']})\n{aaa_link}\n\n**Casualties**:\n{att_casualties}")
                        embed.add_field(name=f"Defender", value=f"[{defender_nation['nation_name']}](https://politicsandwar.com/nation/id={defender_nation['id']})\n{daa_link}\n\n**Casualties**:\n{def_casualties}")
                        embed.add_field(name="\u200b", value=footer, inline=False)
                        await thread.send(embed=embed)
                    elif attack['type'] in ["PEACE", "VICTORY", "ALLIANCELOOT", "EXPIRATION"]:
                        if attack['type'] == "PEACE":
                            title = "White peace"
                            color = 0xffFFff
                            content = f"The peace offer was accepted, and [{war['attacker']['nation_name']}](https://politicsandwar.com/nation/id={war['attacker']['id']}) is no longer fighting an offensive war against [{war['defender']['nation_name']}](https://politicsandwar.com/nation/id={war['defender']['id']})."
                        elif attack['type'] == "VICTORY":
                            if attack['victor'] == atom['id']:
                                title = "Victory"
                                color = 0x00ff00
                            else:
                                title = "Defeat"
                                color = 0xff0000
                            loot = attack['loot_info'].replace('\r\n                            ', '')
                            content = f"[{war['attacker']['nation_name']}](https://politicsandwar.com/nation/id={war['attacker']['id']}) is no longer fighting an offensive war against [{war['defender']['nation_name']}](https://politicsandwar.com/nation/id={war['defender']['id']}).\n\n{loot}"
                        elif attack['type'] == "ALLIANCELOOT":
                            if atom['nation_name'] in attack['loot_info']:
                                color = 0x00ff00
                            else:
                                color = 0xff0000
                            title = "Alliance loot"
                            loot = attack['loot_info'].replace('\r\n                            ', '')
                            content = f"{loot}"
                        elif attack['type'] == "EXPIRATION":
                            title = "War expiration"
                            color = 0xffFFff
                            content = f"The war has lasted 5 days, and has consequently expired. [{war['attacker']['nation_name']}](https://politicsandwar.com/nation/id={war['attacker']['id']}) is no longer fighting an offensive war against [{war['defender']['nation_name']}](https://politicsandwar.com/nation/id={war['defender']['id']})."
                        embed = discord.Embed(title=title, url=url, description=content, color=color)
                        embed.add_field(name="\u200b", value=footer, inline=False)
                        await thread.send(embed=embed)
                    else:
                        for nation in [war['attacker'], war['defender']]:
                            if nation['id'] == attacker_id:
                                attacker_nation = nation
                            elif nation['id'] != attacker_id:
                                defender_nation = nation

                        colors = [0xff0000, 0x00ff00]
                        if attacker_nation['id'] == non_atom['id']:
                            colors.reverse()

                        if attack['type'] == "MISSILE":
                            title = "Missile"
                            content = f"[{attacker_nation['nation_name']}](https://politicsandwar.com/nation/id={attacker_nation['id']}) launched a missile upon [{defender_nation['nation_name']}](https://politicsandwar.com/nation/id={defender_nation['id']}), destroying {attack['infradestroyed']} infra (${attack['infra_destroyed_value']:,}) and {attack['improvementslost']} improvement{'s'[:attack['improvementslost']^1]}."
                        elif attack ['type'] == "MISSILEFAIL":
                            title = "Failed missile"
                            content = f"[{attacker_nation['nation_name']}](https://politicsandwar.com/nation/id={attacker_nation['id']}) launched a missile upon [{defender_nation['nation_name']}](https://politicsandwar.com/nation/id={defender_nation['id']}), but the missile was shot down."
                        elif attack['type'] == "NUKE":
                            title = "Nuke"
                            content = f"[{attacker_nation['nation_name']}](https://politicsandwar.com/nation/id={attacker_nation['id']}) launched a nuclear weapon upon [{defender_nation['nation_name']}](https://politicsandwar.com/nation/id={defender_nation['id']}), destroying {attack['infradestroyed']} infra (${attack['infra_destroyed_value']:,}) and {attack['improvementslost']} improvement{'s'[:attack['improvementslost']^1]}."
                        elif attack['type'] == "NUKEFAIL":
                            title = "Failed nuke"
                            content = f"[{attacker_nation['nation_name']}](https://politicsandwar.com/nation/id={attacker_nation['id']}) launched a nuclear weapon upon [{defender_nation['nation_name']}](https://politicsandwar.com/nation/id={defender_nation['id']}), but the nuke was shot down."
                        elif attack['type'] == "FORTIFY":
                            title = "Fortification"
                            content = f"[{attacker_nation['nation_name']}](https://politicsandwar.com/nation/id={attacker_nation['id']}) is now fortified in the war against [{defender_nation['nation_name']}](https://politicsandwar.com/nation/id={defender_nation['id']})."
                    
                        embed = discord.Embed(title=title, url=url, description=content, color=colors[attack['success']])
                        embed.add_field(name="\u200b", value=footer, inline=False)
                        await thread.send(embed=embed)

                    mongo.war_logs.find_one_and_update({"id": war['id'], "guild_id": guild_id}, {"$push": {"attacks": attack['id']}})
                else:
                    print("could not find or create thread", war['id'], peace, non_atom, atom)

            prev_wars = []
            while True:
                try:
                    guilds = list(mongo.guild_configs.find({"war_threads_alliance_ids": {"$exists": True, "$not": {"$size": 0}}}))
                    alliance_ids = []
                    for guild in guilds:
                        for aa in guild['war_threads_alliance_ids']:
                            alliance_ids.append(aa)
                    unique_ids = list(set(alliance_ids))
                    async with aiohttp.ClientSession() as session:
                        wars = []
                        has_more_pages = True
                        n = 1
                        done_wars = []
                        all_wars = []
                        while has_more_pages:
                            temp1 = await utils.call(f"{{wars(alliance_id:[{','.join(unique_ids)}] page:{n} active:false days_ago:5 first:200) {{paginatorInfo{{hasMorePages}} data{{id war_type attpeace defpeace turnsleft reason date att_alliance_id def_alliance_id attacker{{nation_name leader_name alliance{{name}} alliance_id id num_cities}} defender{{nation_name leader_name alliance{{name}} alliance_id id num_cities}} attacks{{type id date att_id def_id loot_info victor moneystolen success cityid resistance_eliminated infradestroyed infra_destroyed_value improvementslost aircraft_killed_by_tanks attcas1 attcas2 defcas1 defcas2}}}}}}}}")
                            n += 1
                            try:
                                all_wars += temp1['data']['wars']['data']
                                has_more_pages = temp1['data']['wars']['paginatorInfo']['hasMorePages']
                            except:
                                e = temp1['errors']
                                logger.error(e, exc_info=True)
                                await debug_channel.send(f'**Exception caught!**\nWhere: Scanning wars -> Fetching from API\n\nError:```{e}```')
                                await asyncio.sleep(60)
                                continue
                        for war in all_wars:
                            if war['turnsleft'] <= 0:
                                declaration = datetime.strptime(war['date'], '%Y-%m-%dT%H:%M:%S%z').replace(tzinfo=None)
                                if (datetime.utcnow() - declaration).days <= 5:
                                    done_wars.append(war)
                            else:
                                wars.append(war)
                        for new_war in wars:
                            try:
                                for guild in guilds:
                                    channel = None
                                    guild_id = None
                                    try:
                                        if new_war['att_alliance_id'] in guild['war_threads_alliance_ids']:
                                            atom = new_war['attacker']
                                            non_atom = new_war['defender']
                                        elif new_war['def_alliance_id'] in guild['war_threads_alliance_ids']:
                                            atom = new_war['defender']
                                            non_atom = new_war['attacker']
                                        else:
                                            continue
                                        channel = self.bot.get_channel(guild['war_threads_channel_id']) 
                                        guild_id = guild['guild_id']
                                    except:
                                        continue
                                    if not channel or not guild_id:
                                        continue
                                    attack_logs = mongo.war_logs.find_one({"id": new_war['id'], "guild_id": guild_id})
                                    if not attack_logs:
                                        attack_logs, temp = await cthread(new_war, non_atom, atom)
                                    for old_war in prev_wars:
                                        if new_war['id'] == old_war['id']:
                                            if new_war['attpeace'] and not old_war['attpeace']:
                                                peace_obj = {"offerer": new_war['attacker'], "reciever": new_war['defender']}
                                                await smsg(None, None, new_war, atom, non_atom, peace_obj)
                                            elif new_war['defpeace'] and not old_war['defpeace']:
                                                peace_obj = {"offerer": new_war['defender'], "reciever": new_war['attacker']}
                                                await smsg(None, None, new_war, atom, non_atom, peace_obj)
                                            break
                                    for attack in new_war['attacks']:
                                        if attack['id'] not in attack_logs['attacks']:
                                            await smsg(attack['att_id'], attack, new_war, atom, non_atom, None)
                            except discord.errors.Forbidden:
                                pass
                            except Exception as e:
                                logger.error(e, exc_info=True)
                                await debug_channel.send(f'**Exception caught!**\nWhere: Scanning wars -> Iterating `new_wars`\n\nError:```{traceback.format_exc()}```')
                        for done_war in done_wars:
                            try:
                                for guild in guilds:
                                    channel = None
                                    guild_id = None
                                    try:
                                        if done_war['att_alliance_id'] in guild['war_threads_alliance_ids']:
                                            atom = done_war['attacker']
                                            non_atom = done_war['defender']
                                        elif done_war['def_alliance_id'] in guild['war_threads_alliance_ids']:
                                            atom = done_war['defender']
                                            non_atom = done_war['attacker']
                                        else:
                                            continue
                                        channel = self.bot.get_channel(guild['war_threads_channel_id']) 
                                        guild_id = guild['guild_id']
                                    except:
                                        continue
                                    if not channel or not guild_id:
                                        continue
                                    attack_logs = mongo.war_logs.find_one({"id": done_war['id'], "guild_id": guild_id})
                                    if not attack_logs:
                                        attack_logs, temp = await cthread(done_war, non_atom, atom)
                                    elif attack_logs['finished']:
                                        continue
                                    for attack in done_war['attacks']:
                                        if attack['id'] not in attack_logs['attacks']:
                                            await smsg(attack['att_id'], attack, done_war, atom, non_atom, None)
                                    if len(done_war['attacks']) == 0:
                                        attack = {"type": "EXPIRATION", "id": -1, "date": datetime.strftime(datetime.utcnow().replace(tzinfo=timezone.utc), '%Y-%m-%dT%H:%M:%S%z')}
                                        await smsg(None, attack, done_war, atom, non_atom, None)
                                    elif done_war['attacks'][-1]['type'] not in ["PEACE", "VICTORY", "ALLIANCELOOT"]:
                                        attack = {"type": "EXPIRATION", "id": -1, "date": datetime.strftime(datetime.utcnow().replace(tzinfo=timezone.utc), '%Y-%m-%dT%H:%M:%S%z')}
                                        await smsg(None, attack, done_war, atom, non_atom, None)
                                    for thread in channel.threads:
                                        if f"({non_atom['id']})" in thread.name:
                                            try:
                                                await self.remove_from_thread(thread, atom['id'], atom)
                                                members = await thread.fetch_members()
                                                member_count = 0
                                                for member in members:
                                                    user = await self.bot.fetch_user(member.id)
                                                    if user.bot:
                                                        continue
                                                    else:
                                                        member_count += 1
                                                if member_count == 0:
                                                    await thread.edit(archived=True)
                                            except Exception as e:
                                                logger.error(e, exc_info=True)
                                                await debug_channel.send(f'**Exception caught!**\nWhere: Scanning wars -> Fetching members of closing thread\n\nError:```{traceback.format_exc()}```')
                                            mongo.war_logs.find_one_and_update({"id": done_war['id'], "guild_id": guild_id}, {"$set": {"finished": True}})
                                            break
                            except discord.errors.Forbidden:
                                pass
                            except Exception as e:
                                logger.error(e, exc_info=True)
                                await debug_channel.send(f'**Exception caught!**\nWhere: Scanning wars -> Iterating `done_wars`\n\nError:```{traceback.format_exc()}```')
                    await asyncio.sleep(60)
                except:
                    await debug_channel.send(f"I encountered an error whilst scanning for wars:```{traceback.format_exc()}```")
        except Exception as e:
            logger.error(e, exc_info=True)
            await debug_channel.send(f'**__FATAL__ exception caught!**\nWhere: Scanning wars\n\nError:```{traceback.format_exc()}```')

def setup(bot):
    bot.add_cog(General(bot))