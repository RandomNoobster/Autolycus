import os
import traceback
from discord.ext import commands
from datetime import datetime, timedelta, timezone
from main import async_mongo, logger, channel_id, kit, main_async_db, dependent_async_db
import utils
import discord
from typing import Union, Tuple
import asyncio
from dotenv import load_dotenv
import queries
load_dotenv()

api_key = os.getenv("api_key")
channel_id = int(os.getenv("debug_channel"))

class General(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.bot.bg_task = self.bot.loop.create_task(self.wars())
        self.bot.bg_task = self.bot.loop.create_task(self.alert_scanner())

    async def alert_scanner(self):
        await self.bot.wait_until_ready()
        unique_ids: list[str] = []
        alerts: list[dict] = []

        async def sub_handler(sub):
            nonlocal unique_ids
            async for x in sub:
                try:
                    if str(x.id) in unique_ids:
                        if int(x.vacation_mode_turns) == 0 and int(x.beige_turns) == 0:
                            await remind(str(x.id), preemptive=True, pull=True)
                except Exception as e:
                    logger.error(traceback.format_exc())
        
        async def remind(nation_id: str, preemptive: bool = False, pull: bool = False):
            nonlocal alerts
            for user in alerts:
                for alert in user['beige_alerts']:
                    if alert == nation_id:
                        # TODO
                        # disc_user = await self.bot.fetch_user(465463547200012298)
                        disc_user = await self.bot.fetch_user(user['user'])
                        if preemptive:
                            content = f"Hey, https://politicsandwar.com/nation/id={alert} has left beige prematurely!"
                        elif nation['beige_turns'] >= 1:
                            turns = int(nation['beige_turns'])
                            content = f"Hey, https://politicsandwar.com/nation/id={alert} is leaving beige <t:{round(utils.get_datetime_of_turns(turns).timestamp())}:R>!"
                        elif nation['vacation_mode_turns'] >= 1:
                            turns = int(nation['vacation_mode_turns'])
                            content = f"Hey, https://politicsandwar.com/nation/id={alert} is leaving vacation mode <t:{round(utils.get_datetime_of_turns(turns).timestamp())}:R>!"
                        else:
                            content = f"Hey, https://politicsandwar.com/nation/id={alert} left beige while I wasn't looking!"
                            print("How did we get here?")
                            logger.error(f"Something fucky with beige alerts (2)\n\nAlert: {alert}\n\nUser: {user}")
                            await debug_channel.send(utils.cut_string(f"**Exception passed**\n\nSomething fucky with beige alerts (2).\n\nAlert: {alert}\n\nUser: {user}"))

                        try:
                            await disc_user.send(content)
                        except Exception as e:
                            logger.error(e, exc_info=True)
                            await debug_channel.send(f"**Silly person**\nI was attempting to DM {disc_user} about a beige reminder, but I was unable to message them.")

                        if pull:
                            await async_mongo.global_users.find_one_and_update({"user": user['user']}, {"$pull": {"beige_alerts": alert}})
                    break


        debug_channel = self.bot.get_channel(channel_id)
        nation_updates = await kit.subscribe("nation", "update", {"include": ["beige_turns", "vacation_mode_turns", "id"]})
        asyncio.ensure_future(sub_handler(nation_updates))

        while True:
            try:
                alerts = await utils.listify(async_mongo.global_users.find({"beige_alerts": {"$exists": True, "$not": {"$size": 0}}}))
                nation_ids = []
                for user in alerts:
                    for alert in user['beige_alerts']:
                        nation_ids.append(alert)
                unique_ids = list(set(nation_ids))

                res = await utils.paginate_call(f"{{nations(page:page_number first:500 id:[{','.join(unique_ids)}]){{paginatorInfo{{hasMorePages}} data{{id vacation_mode_turns beige_turns}}}}}}", "nations")
                for user in alerts:
                    if "beige_alerts_config" in user:
                        times_to_send: list[int] = user['beige_alerts_config']
                        times_to_send.sort(reverse=True)
                    else:
                        times_to_send = [15]
                    for alert in user['beige_alerts']:
                        for nation in res:
                            if alert == nation['id']:
                                if nation['beige_turns'] >= 1:
                                    exiting_time = utils.get_datetime_of_turns(int(nation['beige_turns']))
                                elif nation['vacation_mode_turns'] >= 1:
                                    exiting_time = utils.get_datetime_of_turns(int(nation['vacation_mode_turns']))
                                else:
                                    print("How did we get here?")
                                    logger.error(f"Something fucky with beige alerts (1)\n\nNation: {nation}\n\nUser: {user}")
                                    await debug_channel.send(utils.cut_string(f"**Exception passed**\n\nSomething fucky with beige alerts (1).\n\nNation: {nation}\n\nUser: {user}"))
                                    exiting_time = utils.get_datetime_of_turns(0)
                                reminded = False
                                for sending_time in times_to_send:
                                    if datetime.utcnow() - timedelta(seconds=50) < exiting_time - timedelta(minutes=sending_time) < datetime.utcnow() + timedelta(seconds=50):
                                        if times_to_send.index(sending_time) == len(times_to_send) - 1:
                                            pull = True
                                        else:
                                            pull = False
                                        await remind(nation["id"], pull=pull)
                                        reminded = True
                                        break
                                if not reminded and nation['beige_turns'] == 0 and nation['vacation_mode_turns'] == 0:
                                    logger.info(f"Reminding {user['user']} about {nation['id']} too late!!")
                                    await remind(nation["id"], pull=True)
                                break
            except Exception as e:
                logger.error(e, exc_info=True)
                await debug_channel.send(utils.cut_string(f'**Exception __caught__!**\nWhere: Scanning beige alerts\n\nError:```{traceback.format_exc()}```'))
            await asyncio.sleep(100)

    
    async def add_to_thread(self, thread, friend_id: Union[str, int], friend: dict = None):
        person = await utils.find_user(self, friend_id)
        if not person:
            #print("tried to add, but could not find", friend_id)
            if friend:
                await thread.send(f"I was unable to add https://politicsandwar.com/nation/id={friend['id']} to the thread. Have they not verified with `/verify`?")
            else:
                await thread.send(f"I was unable to add https://politicsandwar.com/nation/id={friend_id} to the thread. Have they not verified with `/verify`?")
            return
        user = await self.bot.fetch_user(person['user'])
        try:
            await thread.add_user(user)
        except Exception as e:
            await thread.send(f"I was unable to add {user} to the thread.\n```{e}```")
    
    async def remove_from_thread(self, thread, friend_id: Union[str, int], friend: dict = None):
        person = await utils.find_user(self, friend_id)
        if not person:
            #print("tried to remove, but could not find", friend_id)
            if friend:
                await thread.send(f"I was unable to remove https://politicsandwar.com/nation/id={friend['id']} from the thread. Have they not verified with `/verify`?")
            else:
                await thread.send(f"I was unable to remove https://politicsandwar.com/nation/id={friend_id} from the thread. Have they not verified with `/verify`?")
            return
        user = await self.bot.fetch_user(person['user'])
        try:
            await thread.remove_user(user)
        except:
            await thread.send(f"I was unable to remove {user} from the thread.")
    
    async def wars(self):
        while True:
            try:
                await self.bot.wait_until_ready()
                channel = None
                guild_id = None
                debug_channel = self.bot.get_channel(channel_id)
                
                # cthread is to generate the thread when a war is declared
                # makes attack_logs
                async def cthread(war: dict, enemy: dict, friend: dict, channel: discord.TextChannel) -> Tuple[Union[dict, None], Union[discord.Thread, None]]:
                    url = f"https://politicsandwar.com/nation/war/timeline/war={war['id']}"
                    if war['att_id'] == friend['id']:
                        war_type = "Offensive"
                    else:
                        war_type = "Defensive"
                    footer = f"<t:{round((war['date']).timestamp())}:R> <t:{round((war['date']).timestamp())}>"
                    if not isinstance(war["war_type"], str):
                        type_of_war = war["war_type"].name
                    else:
                        type_of_war = war["war_type"]
                    embed = discord.Embed(title=f"New {war_type} War", url=url, description=f"[{war['attacker']['nation_name']}](https://politicsandwar.com/nation/id={war['attacker']['id']}) declared a{'n'[:(len(type_of_war)-5)^1]} {type_of_war.lower()} war on [{war['defender']['nation_name']}](https://politicsandwar.com/nation/id={war['defender']['id']}) for the reason of: ```{war['reason']}```\n{footer}", color=0x2F3136)
                    name = f"{enemy['nation_name']} ({enemy['id']})"
                    found = False

                    found, matching_thread = await find_thread(channel, enemy, friend)

                    if not found:
                        message = await channel.send(embed=embed)
                        try:
                            try:
                                thread = await channel.create_thread(name=name, message=message, auto_archive_duration=4320, type=discord.ChannelType.private_thread, reason="War declaration")
                            except:
                                thread = await channel.create_thread(name=name, message=message, auto_archive_duration=1440, type=discord.ChannelType.private_thread, reason="War declaration")
                        except discord.errors.HTTPException as e:
                            logger.error(e, exc_info=True)
                            await debug_channel.send(f"I encountered an error when creating a thread: ```{e}```")
                            return
                        if war['turnsleft'] > 0:
                            await self.add_to_thread(thread, friend['id'], friend)
                        matching_thread = thread
                    elif found:
                        if war['turnsleft'] > 0:
                            await matching_thread.send(embed=embed)
                        await self.add_to_thread(matching_thread, friend['id'], friend)
                    
                    attack_logs = {"id": war['id'], "guild_id": channel.guild.id, "attacks": [], "detected": datetime.utcnow(), "finished": False}
                    await async_mongo.war_logs.insert_one(attack_logs)
                    print(war['id'], " created ", round((datetime.utcnow().timestamp()-(war['date']).timestamp())/60), datetime.utcnow())
                    return attack_logs, matching_thread

                # find_thread is to find the thread for the enemy nation and add the friend to it
                # it is like cthread, but it doesn't send a "War declared" message
                # also does not make attack_logs
                async def find_thread(channel: discord.TextChannel, enemy: dict, friend: dict) -> Tuple[bool, Union[discord.Thread, None]]:
                    found = False
                    matching_thread = None

                    for thread in channel.threads:
                        if f"({enemy['id']})" in thread.name:
                            matching_thread = thread
                            found = True
                            break

                    if not found:
                        async for thread in channel.archived_threads(limit=None):
                            if f"({enemy['id']})" in thread.name:
                                matching_thread = thread
                                found = True
                                person = await utils.find_user(self, friend['id'])
                                if not person:
                                    print("tried to add to archived thread, but could not find", friend['id'])
                                    # await thread.send(f"I was unable to add https://politicsandwar.com/nation/id={friend['id']} to the thread. Have they not verified with `/verify`?")
                                    # dont need this since this is done by add_to_thread()
                                    break
                                user = await self.bot.fetch_user(person['user'])
                                try:
                                    await thread.add_user(user)
                                except:
                                    pass
                                break
                    return found, matching_thread

                async def smsg(attack: dict, war: dict, friend: dict, enemy: dict, guild: dict, channel: discord.TextChannel) -> None:
                    if "loot_info" not in attack:
                        attack['loot_info'] = ""
                        
                    url = f"https://politicsandwar.com/nation/war/timeline/war={war['id']}"
                    
                    found, matching_thread = await find_thread(channel, enemy, friend)
                    
                    if not found:
                        print("making thread")
                        attack_logs, matching_thread = await cthread(war, enemy, friend, channel)
                        found = True
                    # since found is not set to true, the attack is skipped and is sent in the next iteration of the wars
                        
                    if found:
                        thread = matching_thread
                        url = f"https://politicsandwar.com/nation/war/timeline/war={war['id']}"
                        footer = f"<t:{round((attack['date']).timestamp())}:R> <t:{round((attack['date']).timestamp())}>"
                        if not isinstance(attack['type'], str):
                            attack_type = attack['type'].name
                        else:
                            attack_type = attack['type']
                        if attack_type in ["GROUND", "NAVAL", "AIRVINFRA", "AIRVSOLDIERS", "AIRVTANKS", "AIRVMONEY", "AIRVSHIPS", "AIRVAIR"]:
                            for nation in [friend, enemy]:
                                if nation['id'] == attack['att_id']:
                                    attacker_nation = nation
                                elif nation['id'] == attack['def_id']:
                                    defender_nation = nation
                                else:
                                    logger.error(f"Could not find attacker or defender in attack\nFriend: {friend}\nEnemy: {enemy}\nAttack: {attack}\nWar: {war}")
                                    return

                            colors = [0xff0000, 0xffff00, 0xffff00, 0x00ff00]
                            if attacker_nation == enemy:
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

                            if attack_type == "GROUND":
                                if "aircraft_killed_by_tanks" in attack:
                                    if attack['aircraft_killed_by_tanks']:
                                        aircraft = f"\n{attack['aircraft_killed_by_tanks']:,} aircraft"
                                    else:
                                        aircraft = ""
                                else:
                                    aircraft = ""
                                title = "Ground battle"
                                att_casualties = f"{attack['attcas1']:,} soldiers\n{attack['attcas2']:,} tanks"
                                def_casualties = f"{attack['defcas1']:,} soldiers\n{attack['defcas2']:,} tanks{aircraft}"
                            elif attack_type == "NAVAL":
                                title = "Naval Battle"
                                att_casualties = f"{attack['attcas1']:,} ships"
                                def_casualties = f"{attack['defcas1']:,} ships"
                            elif attack_type == "AIRVINFRA":
                                title = "Airstrike targeting infrastructure"
                                att_casualties = f"{attack['attcas1']:,} planes"
                                def_casualties = f"{attack['defcas1']:,} planes\n{attack['infra_destroyed']} infra (${attack['infra_destroyed_value']:,})"
                            elif attack_type == "AIRVSOLDIERS":
                                title = "Airstrike targeting soldiers"
                                att_casualties = f"{attack['attcas1']:,} planes"
                                def_casualties = f"{attack['defcas1']:,} planes\n{attack['defcas2']} soldiers"
                            elif attack_type == "AIRVTANKS":
                                title = "Airstrike targeting tanks"
                                att_casualties = f"{attack['attcas1']:,} planes"
                                def_casualties = f"{attack['defcas1']:,} planes\n{attack['defcas2']} tanks"
                            elif attack_type == "AIRVMONEY":
                                title = "Airstrike targeting money"
                                att_casualties = f"{attack['attcas1']:,} planes"
                                def_casualties = f"{attack['defcas1']:,} planes\n{attack['defcas2']} money"
                            elif attack_type == "AIRVSHIPS":
                                title = "Airstrike targeting ships"
                                att_casualties = f"{attack['attcas1']:,} planes"
                                def_casualties = f"{attack['defcas1']:,} planes\n{attack['defcas2']} ships"
                            elif attack_type == "AIRVAIR":
                                title = "Airstrike targeting aircraft"
                                att_casualties = f"{attack['attcas1']:,} planes"
                                def_casualties = f"{attack['defcas1']:,} planes"
                            try:
                                aaa_link = f"[{attacker_nation['alliance']['name']}](https://politicsandwar.com/alliance/id={attacker_nation['alliance']['id']})"
                            except:
                                aaa_link = "No alliance"
                            try:
                                daa_link = f"[{defender_nation['alliance']['name']}](https://politicsandwar.com/alliance/id={defender_nation['alliance']['id']})"
                            except:
                                daa_link = "No alliance"

                            embed = discord.Embed(title=title, description=description, color=colors[attack['success']], url=url)
                            embed.add_field(name=f"Attacker", value=f"[{attacker_nation['nation_name']}](https://politicsandwar.com/nation/id={attacker_nation['id']})\n{aaa_link}\n\n**Casualties**:\n{att_casualties}")
                            embed.add_field(name=f"Defender", value=f"[{defender_nation['nation_name']}](https://politicsandwar.com/nation/id={defender_nation['id']})\n{daa_link}\n\n**Casualties**:\n{def_casualties}")
                            embed.add_field(name="\u200b", value=footer, inline=False)
                            await thread.send(embed=embed)

                        elif attack_type in ["PEACE", "VICTORY", "ALLIANCELOOT", "EXPIRATION"]:
                            if attack_type == "PEACE":
                                title = "White peace"
                                color = 0xffFFff
                                content = f"The peace offer was accepted, and [{war['attacker']['nation_name']}](https://politicsandwar.com/nation/id={war['attacker']['id']}) is no longer fighting an offensive war against [{war['defender']['nation_name']}](https://politicsandwar.com/nation/id={war['defender']['id']})."
                            elif attack_type == "VICTORY":
                                if attack['victor'] == friend['id']:
                                    title = "Victory"
                                    color = 0x00ff00
                                else:
                                    title = "Defeat"
                                    color = 0xff0000
                                try:
                                    loot = attack['loot_info'].replace('\r\n                            ', '')
                                    nation_loot = utils.beige_loot_value(loot, prices)
                                    loot += f"\n\nTotal loot value: ${nation_loot:,}"
                                except:
                                    loot = "No loot information."
                                content = f"[{war['attacker']['nation_name']}](https://politicsandwar.com/nation/id={war['attacker']['id']}) is no longer fighting an offensive war against [{war['defender']['nation_name']}](https://politicsandwar.com/nation/id={war['defender']['id']}).\n\n{loot}"
                            elif attack_type == "ALLIANCELOOT":
                                if friend['nation_name'] in attack['loot_info']:
                                    color = 0x00ff00
                                else:
                                    color = 0xff0000
                                title = "Alliance loot"
                                try:
                                    loot = attack['loot_info'].replace('\r\n                            ', '')
                                    nation_loot = utils.beige_loot_value(loot, prices)
                                    loot += f"\n\nTotal loot value: ${nation_loot:,}"
                                except:
                                    loot = "No loot information."
                                content = f"{loot}"
                            elif attack_type == "EXPIRATION":
                                title = "War expiration"
                                color = 0xffFFff
                                content = f"The war has lasted 5 days, and has consequently expired. [{war['attacker']['nation_name']}](https://politicsandwar.com/nation/id={war['attacker']['id']}) is no longer fighting an offensive war against [{war['defender']['nation_name']}](https://politicsandwar.com/nation/id={war['defender']['id']})."
                            embed = discord.Embed(title=title, url=url, description=content, color=color)
                            embed.add_field(name="\u200b", value=footer, inline=False)
                            await thread.send(embed=embed)
                            await close_thread(thread, friend, war)

                        else:
                            for nation in [friend, enemy]:
                                if nation['id'] == attack['att_id']:
                                    attacker_nation = nation
                                elif nation['id'] == attack['def_id']:
                                    defender_nation = nation
                                else:
                                    logger.error(f"Could not find attacker or defender in attack\nFriend: {friend}\nEnemy: {enemy}\nAttack: {attack}\nWar: {war}")
                                    return

                            colors = [0xff0000, 0x00ff00]
                            if attacker_nation['id'] == enemy['id']:
                                colors.reverse()

                            if attack_type == "MISSILE":
                                title = "Missile"
                                content = f"[{attacker_nation['nation_name']}](https://politicsandwar.com/nation/id={attacker_nation['id']}) launched a missile upon [{defender_nation['nation_name']}](https://politicsandwar.com/nation/id={defender_nation['id']}), destroying {attack['infra_destroyed']} infra (${attack['infra_destroyed_value']:,}) and {attack['improvements_lost']} improvement{'s'[:attack['improvements_lost']^1]}."
                            elif attack_type == "MISSILEFAIL":
                                title = "Failed missile"
                                content = f"[{attacker_nation['nation_name']}](https://politicsandwar.com/nation/id={attacker_nation['id']}) launched a missile upon [{defender_nation['nation_name']}](https://politicsandwar.com/nation/id={defender_nation['id']}), but the missile was shot down."
                            elif attack_type == "NUKE":
                                title = "Nuke"
                                content = f"[{attacker_nation['nation_name']}](https://politicsandwar.com/nation/id={attacker_nation['id']}) launched a nuclear weapon upon [{defender_nation['nation_name']}](https://politicsandwar.com/nation/id={defender_nation['id']}), destroying {attack['infra_destroyed']} infra (${attack['infra_destroyed_value']:,}) and {attack['improvements_lost']} improvement{'s'[:attack['improvements_lost']^1]}."
                            elif attack_type == "NUKEFAIL":
                                title = "Failed nuke"
                                content = f"[{attacker_nation['nation_name']}](https://politicsandwar.com/nation/id={attacker_nation['id']}) launched a nuclear weapon upon [{defender_nation['nation_name']}](https://politicsandwar.com/nation/id={defender_nation['id']}), but the nuke was shot down."
                            elif attack_type == "FORTIFY":
                                title = "Fortification"
                                content = f"[{attacker_nation['nation_name']}](https://politicsandwar.com/nation/id={attacker_nation['id']}) is now fortified in the war against [{defender_nation['nation_name']}](https://politicsandwar.com/nation/id={defender_nation['id']})."

                            embed = discord.Embed(title=title, url=url, description=content, color=colors[attack['success']])
                            embed.add_field(name="\u200b", value=footer, inline=False)
                            await thread.send(embed=embed)

                        await async_mongo.war_logs.find_one_and_update({"id": war['id'], "guild_id": channel.guild.id}, {"$push": {"attacks": attack['id']}})
                    else:
                        logger.error(f"Could not find or create thread for war {war['id']}\nFriend: {friend}\nEnemy: {enemy}\nGuild: {guild}\nWar: {war}\nAttack: {attack}")
                        print(f"Could not find or create thread for war {war['id']}\nFriend: {friend}\nEnemy: {enemy}\nGuild: {guild}\nWar: {war}\nAttack: {attack}")
                
                async def close_thread(thread: discord.Thread, friend: dict, war: dict) -> None:
                    try:
                        await self.remove_from_thread(thread, friend['id'], friend)
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
                        await async_mongo.war_logs.find_one_and_update({"id": war['id'], "guild_id": thread.guild.id}, {"$set": {"finished": True}})
                    except Exception as e:
                        logger.error(e, exc_info=True)
                        await debug_channel.send(utils.cut_string(f'**Exception caught!**\nWhere: close_thread()\n\nError:```{traceback.format_exc()}```'))

                async def ensure_nations(war: dict) -> dict:
                    if isinstance(war['date'], datetime):
                        war['date'] = war['date'].replace(tzinfo=None)

                    if not isinstance(war["war_type"], str):
                        war["war_type"] = war["war_type"].name
                    
                    if "turns_left" in war:
                        war["turnsleft"] = war["turns_left"]

                    for k,v in war.items():
                        try:
                            if "id" in k or k in ["ground_control", "air_superiority", "naval_blockade"]:
                                war[k] = str(v)
                        except:
                            pass

                    for x in ["attacker", "defender"]:
                        if not war[f"{x[:3]}_id"]:
                            war[x] = {"nation_name": "Deleted", "leader_name": "Deleted", "id": "0"}
                        else:
                            alliance = await async_mongo.alliances.find_one({"id": war[f"{x[:3]}_alliance_id"]})
                            nation = await async_mongo.world_nations.find_one({"id": war[f"{x[:3]}_id"]})
                            if not nation:
                                war[x] = {"nation_name": "Deleted", "leader_name": "Deleted", "id": "0"}
                            else:
                                war[x] = nation
                            if not alliance:
                                war[x]['alliance'] = {"id": "0", "name": "None"}
                            else:
                                war[x]['alliance'] = {"id": alliance['id'], "name": alliance['name']}

                    # may return None as attacker and defender
                    return war

                async def get_war_vars(war: dict, guild: dict) -> Tuple[discord.TextChannel, dict, dict]:
                    try:
                        if str(war['att_alliance_id']) in guild['war_threads_alliance_ids']:
                            friend = war['attacker']
                            enemy = war['defender']
                        elif str(war['def_alliance_id']) in guild['war_threads_alliance_ids']:
                            friend = war['defender']
                            enemy = war['attacker']
                        else:
                            return None, None, None
                        channel = self.bot.get_channel(guild['war_threads_channel_id']) 
                        return channel, friend, enemy
                    except:
                        return None, None, None
                
                async def scan_new_wars(subscription) -> None:
                    while True:
                        try:
                            async for war in subscription:
                                #sub_war = war
                                #print(sub_war.id, " registered ", (datetime.utcnow().replace(tzinfo=None)-sub_war.date.replace(tzinfo=None)).total_seconds()/60, datetime.utcnow())
                                #subby = vars(subscription)
                                #logger.info("New war: " + str(subby))
                                war = vars(war)
                                war = await ensure_nations(war)
                                # could instead run ensure_antions() after we know that a guild has subscrbed to this alliance
                                for guild in guilds.copy():
                                    channel, friend, enemy = await get_war_vars(war, guild)
                                    if not (channel and friend and enemy):
                                        continue
                                    attack_logs = await async_mongo.war_logs.find_one({"id": war['id'], "guild_id": channel.guild.id})
                                    if not attack_logs:
                                        await cthread(war, enemy, friend, channel)
                                #print(sub_war.id, " wrote off ", (datetime.utcnow().replace(tzinfo=None)-sub_war.date.replace(tzinfo=None)).total_seconds()/60, datetime.utcnow())
                                await dependent_async_db.wars.find_one_and_replace({"id": war['id']}, war, upsert=True)
                        except Exception as e:
                            logger.error(e, exc_info=True)
                            await debug_channel.send(utils.cut_string(f'**Exception caught!**\nWhere: Scanning wars -> scan_new_wars()\n\nError:```{traceback.format_exc()}```'))
                            await asyncio.sleep(60)

                async def scan_updated_wars(subscription) -> None:
                    while True:
                        try:
                            async for war in subscription:
                                #subby = vars(subscription)
                                #logger.info("Updated war: " + str(subby))
                                war = vars(war)
                                war = await ensure_nations(war)
                                for guild in guilds.copy():

                                    channel, friend, enemy = await get_war_vars(war, guild)

                                    if not (channel and friend and enemy):
                                        continue
                                    
                                    found, matching_thread = await find_thread(channel, enemy, friend)

                                    if found:
                                        old_record = await dependent_async_db.wars.find_one({"id": war['id']})
                                        if old_record == None:
                                            # should only break the loop when this feature is added
                                            # later on, all wars should be in the db
                                            # if not, there is an issue
                                            break

                                        await dependent_async_db.wars.find_one_and_replace({"id": war["id"]}, war, upsert=True)

                                        content = None
                                        footer = f"<t:{round((datetime.utcnow()).timestamp())}:R> <t:{round((datetime.utcnow()).timestamp())}>"
                                        if not old_record['att_peace'] and war['att_peace'] and not war['def_peace']:
                                            offerer = war['attacker']
                                            receiver = war['defender']
                                            content = f"[{offerer['nation_name']}](https://politicsandwar.com/nation/id={offerer['id']}) is offering peace to [{receiver['nation_name']}](https://politicsandwar.com/nation/id={receiver['id']}). The peace offering will be cancelled if either side performs an act of aggression."

                                        elif not old_record['def_peace'] and war['def_peace'] and not war['att_peace']:
                                            offerer = war['defender']
                                            receiver = war['attacker']
                                            content = f"[{offerer['nation_name']}](https://politicsandwar.com/nation/id={offerer['id']}) is offering peace to [{receiver['nation_name']}](https://politicsandwar.com/nation/id={receiver['id']}). The peace offering will be cancelled if either side performs an act of aggression."

                                        if old_record['att_peace'] and not war['att_peace']:
                                            content = f"The pending peace offer between [{war['attacker']['nation_name']}](https://politicsandwar.com/nation/id={war['attacker']['id']}) and [{war['defender']['nation_name']}](https://politicsandwar.com/nation/id={war['defender']['id']}) was cancelled."

                                        elif old_record['def_peace'] and not war['def_peace']:
                                            content = f"The pending peace offer between [{war['attacker']['nation_name']}](https://politicsandwar.com/nation/id={war['attacker']['id']}) and [{war['defender']['nation_name']}](https://politicsandwar.com/nation/id={war['defender']['id']}) was cancelled."

                                        if content:
                                            url = f"https://politicsandwar.com/nation/war/timeline/war={war['id']}"
                                            embed = discord.Embed(title="Peace offering", url=url, description=content, color=0xffffff)
                                            embed.add_field(name="\u200b", value=footer, inline=False)
                                            await matching_thread.send(embed=embed)

                        except Exception as e:
                            logger.error(e, exc_info=True)
                            await debug_channel.send(utils.cut_string(f'**Exception caught!**\nWhere: Scanning wars -> scan_updated_wars()\n\nError:```{traceback.format_exc()}```'))
                            await asyncio.sleep(60)

                async def scan_war_attacks(subscription):
                    while True:
                        try:
                            async for attack in subscription:
                                #subby = vars(subscription)
                                #logger.info("War attack: " + str(subby))
                                attack = vars(attack)
                                for k,v in attack.items():
                                    try:
                                        if "id" in k or k == "victor":
                                            attack[k] = str(v)
                                    except:
                                        pass
                                war = await dependent_async_db.wars.find_one({"id": attack['war_id']})
                                if not war:
                                    #print("skipping attack, war id:", attack['war_id'])
                                    continue
                                war = await ensure_nations(war)
                                #print("NOT skipping attack, war id:", attack['war_id'])

                                for guild in guilds.copy():
                                    channel, friend, enemy = await get_war_vars(war, guild)
                                    if not (channel and friend and enemy):
                                        continue
                                    attack_logs = await async_mongo.war_logs.find_one({"id": war['id'], "guild_id": channel.guild.id})
                                    if not attack_logs:
                                        continue
                                    if attack['id'] not in attack_logs['attacks']:
                                        await smsg(attack, war, friend, enemy, guild, channel)
                        except Exception as e:
                            logger.error(e, exc_info=True)
                            await debug_channel.send(utils.cut_string(f'**Exception caught!**\nWhere: Scanning wars -> scan_war_attacks()\n\nError:```{traceback.format_exc()}```'))
                            await asyncio.sleep(60)

                # prices update when the bot restarts
                prices = await utils.get_prices()

                guilds = []
                async def update_guilds():
                    nonlocal guilds, prices
                    while True:
                        guilds = await utils.listify(async_mongo.guild_configs.find({"war_threads_alliance_ids": {"$exists": True, "$not": {"$size": 0}}}))
                        for guild in guilds.copy():
                            try:
                                channel = self.bot.get_channel(guild["war_threads_channel_id"])
                                perms = channel.permissions_for(channel.guild.me)
                            except:
                                guilds.remove(guild)
                                continue
                            if not perms.send_messages or not perms.manage_threads or not perms.embed_links or not perms.read_message_history: 
                                guilds.remove(guild)
                        await asyncio.sleep(300)
                asyncio.ensure_future(update_guilds())

                try:
                    new_wars = await kit.subscribe("war", "create")
                    updated_wars = await kit.subscribe("war", "update")
                    attacks = await kit.subscribe("warattack", "create")
                    
                    asyncio.ensure_future(scan_new_wars(new_wars))
                    asyncio.ensure_future(scan_updated_wars(updated_wars))
                    asyncio.ensure_future(scan_war_attacks(attacks))
                except Exception as e:
                    logger.error(e, exc_info=True)
                    await debug_channel.send(utils.cut_string(f'**Exception caught!**\nWhere: Scanning wars\n\nError:```{traceback.format_exc()}```'))

                #may produce duplicate messages??

                while True:
                    try:
                        alliance_ids = []
                        for guild in guilds:
                            for aa in guild['war_threads_alliance_ids']:
                                if len(aa) > 5:
                                    #to avoid large integers (they are invalid alliance ids)
                                    continue
                                alliance_ids.append(aa)
                        unique_ids = list(set(alliance_ids))
                        wars = []
                        has_more_pages = True
                        n = 1
                        done_wars = []
                        all_wars = []
                        while has_more_pages:
                            temp1 = await utils.call(f"{{wars(alliance_id:[{','.join(unique_ids)}] page:{n} active:false days_ago:5 first:200) {{paginatorInfo{{hasMorePages}} data{utils.get_query(queries.WARS_SCANNER)}}}}}")
                            await asyncio.sleep(30)
                            n += 1
                            try:
                                all_wars += temp1['data']['wars']['data']
                                has_more_pages = temp1['data']['wars']['paginatorInfo']['hasMorePages']
                            except:
                                e = temp1['errors']
                                logger.error(e, exc_info=True)
                                await debug_channel.send(utils.cut_string(f'**Exception caught!**\nWhere: Scanning wars -> Fetching from API\n\nError:```{e}```'))
                                await asyncio.sleep(300)
                                continue
                        registered_war_ids = []
                        for war in all_wars:
                            if war['id'] in registered_war_ids:
                                continue
                            registered_war_ids.append(war['id'])
                            war = await ensure_nations(war)
                            declaration = datetime.strptime(war['date'], '%Y-%m-%dT%H:%M:%S%z').replace(tzinfo=None)
                            war["date"] = declaration
                            for attack in war['attacks']:
                                attack['date'] = datetime.strptime(attack['date'], '%Y-%m-%dT%H:%M:%S%z').replace(tzinfo=None)
                            if war['turnsleft'] <= 0:
                                if (datetime.utcnow() - declaration).days <= 5:
                                    done_wars.append(war)
                            else:
                                db_war = await dependent_async_db.wars.find_one({"id": war['id']})
                                if not db_war:
                                    await dependent_async_db.wars.insert_one(war)
                                wars.append(war)
                        for new_war in wars:
                            try:
                                for guild in guilds:
                                    channel, friend, enemy = await get_war_vars(new_war, guild)                                        
                                    if not (channel and friend and enemy):
                                        continue
                                    attack_logs = await async_mongo.war_logs.find_one({"id": new_war['id'], "guild_id": channel.guild.id})
                                    if not attack_logs:
                                        #logger.debug(f"NO ATTACK LOG, new_war id: '{new_war['id']}'\nguild id: '{channel.guild.id}'")
                                        attack_logs, temp = await cthread(new_war, enemy, friend, channel)
                                    for attack in new_war['attacks']:
                                        #logger.debug(f"new war attackid: {attack['id']} {type(attack['id'])}\nlogs: {attack_logs['attacks']}")
                                        if attack['id'] not in attack_logs['attacks']:
                                            await smsg(attack, new_war, friend, enemy, guild, channel)
                            except discord.errors.Forbidden:
                                pass
                            except Exception as e:
                                logger.error(e, exc_info=True)
                                await debug_channel.send(utils.cut_string(f'**Exception caught!**\nWhere: Scanning wars -> Iterating `new_wars`\n\nError:```{traceback.format_exc()}```'))
                        for done_war in done_wars:
                            try:
                                for guild in guilds:
                                    channel, friend, enemy = await get_war_vars(done_war, guild)                                        
                                    if not (channel and friend and enemy):
                                        continue
                                    attack_logs = await async_mongo.war_logs.find_one({"id": done_war['id'], "guild_id": channel.guild.id})
                                    if not attack_logs:
                                        #logger.debug(f"NO ATTACK LOG, new_war id: '{new_war['id']}'\nguild id: '{channel.guild.id}'")
                                        attack_logs, temp = await cthread(done_war, enemy, friend, channel)
                                    elif attack_logs['finished']:
                                        continue
                                    else:
                                        for attack in done_war['attacks']:
                                            #logger.debug(f"old war attackid: {attack['id']} {type(attack['id'])}\nlogs: {attack_logs['attacks']}")
                                            if attack['id'] not in attack_logs['attacks']:
                                                await smsg(attack, done_war, friend, enemy, guild, channel)
                                    attack = {"type": "EXPIRATION", "id": -1, "date": done_war['date'] + timedelta(days=5)}
                                    if len(done_war['attacks']) == 0:
                                        await smsg(attack, done_war, friend, enemy, guild, channel)
                                    elif done_war['attacks'][-1]['type'] not in ["PEACE", "VICTORY", "ALLIANCELOOT"]:
                                        await smsg(attack, done_war, friend, enemy, guild, channel)
                            except discord.errors.Forbidden:
                                pass
                            except Exception as e:
                                logger.error(e, exc_info=True)
                                await debug_channel.send(utils.cut_string(f'**Exception caught!**\nWhere: Scanning wars -> Iterating `done_wars`\n\nError:```{traceback.format_exc()}```'))
                    except Exception as e:
                        logger.error(e, exc_info=True)
                        await debug_channel.send(utils.cut_string(f"I encountered an error whilst scanning for wars:```{traceback.format_exc()}```"))
                        await asyncio.sleep(300)

            except Exception as e:
                logger.error(e, exc_info=True)
                await debug_channel.send(utils.cut_string(f'**__FATAL__ exception caught!**\nWhere: Scanning wars\n\nError:```{traceback.format_exc()}```'))
            
            await asyncio.sleep(600)

def setup(bot):
    bot.add_cog(General(bot))