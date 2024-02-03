import aiofiles
import discord
from discord.ext import commands
from discord.commands import slash_command, Option, SlashCommandGroup
import random
import pathlib
import json
from typing import Union
import os
from datetime import datetime, timedelta
import utils
import math
import queries
from main import async_mongo, logger

api_key = os.getenv("api_key")

class TargetFinding(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    def winrate_calc(self, attacker_value, defender_value):
        try:
            if attacker_value == 0 and defender_value == 0:
                return 0
            elif defender_value == 0:
                return 1
            
            x = attacker_value / defender_value

            # should be 2.5 and not 2 but the function would have to be redone
            if x > 2:
                winrate = 1
            elif x < 0.4:
                winrate = 0
            else:
                winrate = (12.832883444301027*x**(11)-171.668262561212487*x**(10)+1018.533858483560834*x**(9)-3529.694284997589875*x**(8)+7918.373606722701879*x**(7)-12042.696852729619422*x**(6)+12637.399722721022044*x**(5)-9128.535790660698694*x**(4)+4437.651655224382012*x**(3)-1378.156072477675025*x**(2)+245.439740545813436*x-18.980551645186498)
            return winrate
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e


    @slash_command(
        name="spy_targets",
        description="Find spy targets",
    )
    async def spy_targets(self, ctx: discord.ApplicationContext):
        try:
            await ctx.defer()

            send = False
            guild_config = await async_mongo.guild_configs.find_one({"guild_id": ctx.guild.id})

            if not guild_config:
                send = True
            elif "targets_alliance_ids" not in guild_config:
                send = True
            elif len(guild_config['targets_alliance_ids']) == 0:
                send = True
            
            if send:
                await ctx.edit(content="No target alliances have been registered. Use `/config targets` to register some.")
                return
            
            invoker = await utils.find_user(self, ctx.author.id)
            my_nation = await utils.call(f"{{nations(first:1 id:{invoker['id']}){{data{{score}}}}}}")
            my_score = my_nation['data']['nations']['data'][0]['score']

            targets = await utils.call(f"{{nations(first:500 alliance_id:[{','.join([str(x) for x in guild_config['targets_alliance_ids']])}]){{data{{nation_name id score soldiers tanks aircraft ships nukes missiles spies espionage_available}}}}}}")
            targets = targets['data']['nations']['data']
            targets = [x for x in targets if x['espionage_available'] == True and x['score'] >= my_score * 0.4 and x['score'] <= my_score * 1.50 and not(x['soldiers'] == 0 and x['tanks'] == 0 and x['aircraft'] == 0 and x['ships'] == 0 and x['nukes'] <= 1 and x['missiles'] <= 1 and x['spies'] == 0)]

            if len(targets) == 0:
                await ctx.edit(content="No spyable targets in range was found.")
                return

            desc = f"Here are some nations that you can spy on."

            for idx, target in enumerate(targets):
                if idx == 6:
                    break
                suggested_target = ""
                if target['spies'] >= 3:
                    suggested_target = ", target spies"
                elif target['nukes'] > 1:
                    suggested_target = ", target nukes"
                elif target['missiles'] > 2:
                    suggested_target = ", target missiles"
                elif target['aircraft'] > 0:
                    suggested_target = ", target aircraft"
                elif target['tanks'] > 0:
                    suggested_target = ", target tanks"
                elif target['ships'] > 0:
                    suggested_target = ", target ships"
                elif target['missiles'] > 0:
                    suggested_target = ", target missiles"
                elif target['nukes'] > 0:
                    suggested_target = ", target nukes"                

                desc += f"\n[{target['nation_name']}](https://politicsandwar.com/nation/id={target['id']})" + suggested_target
                #desc += f"\n[{target['nation_name']}](https://politicsandwar.com/nation/espionage/eid={target['id']}) `💂 {target['soldiers']:,}`, `⚙ {target['tanks']:,}`, `✈ {target['aircraft']:,}`, `🚢 {target['ships']:,}`, `🔎 {target['spies']:,}`, `🚀 {target['missiles']}`, `☢ {target['nukes']}`"
                
            embed = discord.Embed(title="Spy targets", description=desc, color=utils.EMBED_COLOR)
            await ctx.edit(embed=embed)

        except Exception as e:
            logger.error(e, exc_info=True)
            raise e


    @slash_command(
        name="raids",
        description="Find raid targets",
    )
    async def raids(self, ctx: discord.ApplicationContext):
        try:
            await ctx.defer()
            
            when_to_timeout = datetime.utcnow() + timedelta(minutes=10)

            attacker = await utils.find_nation_plus(self, ctx.author.id)
            if not attacker:
                await ctx.edit(content='I could not find your nation, make sure that you are verified by using `/verify`!')
                return
            atck_ntn = (await utils.call(f"{{nations(first:1 id:{attacker['id']}){{data{utils.get_query(queries.WINRATE_CALC, {'nations': ['nation_name', 'score', 'id', 'population']})}}}}}"))['data']['nations']['data'][0]
            if atck_ntn == None:
                await ctx.edit(content='I did not find that person!')
                return
            
            minscore = round(atck_ntn['score'] * 0.75)
            maxscore = round(atck_ntn['score'] * 2.5)
            
            use_same = None
            class stage_one(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal use_same
                    use_same = True
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal use_same
                    use_same = False
                    await i.response.edit_message()
                    self.stop()

                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await utils.run_timeout(ctx, view)

            webpage = None
            discord_embed = None
            class stage_two(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                @discord.ui.button(label="Embed on discord", style=discord.ButtonStyle.primary)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal webpage, discord_embed
                    webpage = False
                    discord_embed = True
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="Message on discord", style=discord.ButtonStyle.primary)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal webpage, discord_embed
                    webpage = False
                    discord_embed = False
                    await i.response.edit_message()
                    self.stop()

                @discord.ui.button(label="As a webpage", style=discord.ButtonStyle.primary)
                async def tertiary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal webpage, discord_embed
                    webpage = True
                    discord_embed = False
                    await i.response.edit_message()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await utils.run_timeout(ctx, view)
            
            who = None
            class stage_three(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                @discord.ui.button(label="All nations", style=discord.ButtonStyle.primary)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal who
                    who = ""
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="Applicants and nations not in alliances", style=discord.ButtonStyle.primary)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal who
                    who = " alliance_position:[0,1]"
                    await i.response.edit_message()
                    self.stop()

                @discord.ui.button(label="Nations not affiliated with any alliance", style=discord.ButtonStyle.primary)
                async def tertiary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal who
                    who = " alliance_id:0"
                    await i.response.edit_message()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await utils.run_timeout(ctx, view)               
                
            max_wars = None
            class stage_four(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                @discord.ui.button(label="0", style=discord.ButtonStyle.primary)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal max_wars
                    max_wars = 0
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="1 or less", style=discord.ButtonStyle.primary)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal max_wars
                    max_wars = 1
                    await i.response.edit_message()
                    self.stop()

                @discord.ui.button(label="2 or less", style=discord.ButtonStyle.primary)
                async def tertiary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal max_wars
                    max_wars = 2
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="3 or less", style=discord.ButtonStyle.primary)
                async def quadrary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal max_wars
                    max_wars = 3
                    await i.response.edit_message()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await utils.run_timeout(ctx, view)
        
            inactive_limit = None
            class stage_five(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                @discord.ui.button(label="I don't care", style=discord.ButtonStyle.primary)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal inactive_limit
                    inactive_limit = 0
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="7+ days inactive", style=discord.ButtonStyle.primary)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal inactive_limit
                    inactive_limit = 7
                    await i.response.edit_message()
                    self.stop()

                @discord.ui.button(label="14+ days inactive", style=discord.ButtonStyle.primary)
                async def tertiary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal inactive_limit
                    inactive_limit = 14
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="30+ days inactive", style=discord.ButtonStyle.primary)
                async def quadrary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal inactive_limit
                    inactive_limit = 30
                    await i.response.edit_message()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await utils.run_timeout(ctx, view)
            
            beige = None
            class stage_six(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal beige
                    beige = True
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal beige
                    beige = False
                    await i.response.edit_message()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await utils.run_timeout(ctx, view)
                                
            minimum_beige_loot = None
            class stage_seven(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                @discord.ui.button(label="No minimum", style=discord.ButtonStyle.primary)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal minimum_beige_loot
                    minimum_beige_loot = 0
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="$5 million", style=discord.ButtonStyle.primary)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal minimum_beige_loot
                    minimum_beige_loot = 5000000
                    await i.response.edit_message()
                    self.stop()

                @discord.ui.button(label="$10 million", style=discord.ButtonStyle.primary)
                async def tertiary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal minimum_beige_loot
                    minimum_beige_loot = 10000000
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="$20 million", style=discord.ButtonStyle.primary)
                async def quadrary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal minimum_beige_loot
                    minimum_beige_loot = 20000000
                    await i.response.edit_message()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await utils.run_timeout(ctx, view)
            
            performace_filter = None
            class stage_eight(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal performace_filter
                    performace_filter = True
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal performace_filter
                    performace_filter = False
                    await i.response.edit_message()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await utils.run_timeout(ctx, view)

            target_list = []
            
            file_content = last_fetched = None
            for i in range(3):
                try:
                    async with aiofiles.open(pathlib.Path.cwd() / 'data' / 'nations.json', 'r') as json_file:
                        file_content = json.loads(await json_file.read())
                        last_fetched = file_content['last_fetched']
                        break
                except:
                    pass
            
            if not last_fetched or not file_content:
                await ctx.send("I ran into an issue when loading nations. Please try again in a few minutes. If this is a recurring issue, please contact RandomNoobster#0093.")
                return
            new_turn: bool = datetime.fromtimestamp(last_fetched).hour % 2 != 0 and datetime.utcnow().hour % 2 == 0
                
            embed1 = discord.Embed(title=f"Configuration", description="Do you want to use the same configuration (presenatation & filters) that you used last time running this command?", color=0xff5100)
            embed2 = discord.Embed(title=f"Presentation", description="How do you want to get your targets?\n\nEmbed on discord returns a paginated embed with some information about each nation. Use this if you can't use the webpage for whatever reason.\n\nMessage on discord returns a small list of the nations with the highest recent beige loot. Use this if you are very lazy.\n\nAs a webpage returns a link to a webpage with a sortable table that has lots of important information about each nation. If used well, this gives you the best targets.", color=0xff5100)
            embed3 = discord.Embed(title=f"Filters (1/6)", description="What nations do you want to include?", color=0xff5100)
            embed4 = discord.Embed(title=f"Filters (2/6)", description="How many active defensive wars should they have?", color=0xff5100)
            embed5 = discord.Embed(title=f"Filters (3/6)", description="How inactive should they be?", color=0xff5100)
            embed6 = discord.Embed(title=f"Filters (4/6)", description="Do you want to include beige nations?", color=0xff5100)
            embed7 = discord.Embed(title=f"Filters (5/6)", description="Should there be a minimum previous beige loot?", color=0xff5100)
            embed8 = discord.Embed(title=f"Filters (6/6)", description='Do you want to improve performance by filtering out "bad" targets?\n\nMore specifically, this will omit nations with negative income, nations that have a stronger ground force than you, and nations that were previously beiged for $0.', color=0xff5100)

            option_list = [(embed1, stage_one()), (embed2, stage_two()), (embed3, stage_three()), (embed4, stage_four()), (embed5, stage_five()), (embed6, stage_six()), (embed7, stage_seven()), (embed8, stage_eight())]
            user = await async_mongo.global_users.find_one({"user": ctx.author.id})
            if "raids_config" not in user:
                option_list.pop(0)

            for embed, view in option_list:
                await ctx.edit(content="", embed=embed, view=view)
                timed_out = await view.wait()
                if timed_out:
                    return
                if use_same == True:
                    webpage = user['raids_config']['webpage']
                    discord_embed = user['raids_config']['discord_embed']
                    who = user['raids_config']['who']
                    max_wars = user['raids_config']['max_wars']
                    inactive_limit = user['raids_config']['inactive_limit']
                    beige = user['raids_config']['beige']
                    performace_filter = user['raids_config']['performace_filter']
                    # this was added later on when some people may not have it in their raid_config
                    # which makes this check necessary 
                    if "minimum_beige_loot" in user['raids_config']:
                        minimum_beige_loot = user['raids_config']['minimum_beige_loot']
                    else:
                        minimum_beige_loot = 0
                    break

            if guild_config := await async_mongo.guild_configs.find_one({"guild_id": ctx.guild.id}):
                if "dnr_alliance_ids" in guild_config:
                    dnr_alliance_ids = guild_config['dnr_alliance_ids']
                else:
                    dnr_alliance_ids = []
            else:
                dnr_alliance_ids = []
            
            view = None

            await ctx.edit(content="Getting targets...", view=view, embed=None)
            done_jobs = [{"data": {"nations": {"data": file_content['nations']}}}]

            await ctx.edit(content="Caching targets...")
            temp, colors, prices, treasures, radiation, seasonal_mod = await utils.pre_revenue_calc(ctx, query_for_nation=False, parsed_nation=atck_ntn)
            for done_job in done_jobs:
                for x in done_job['data']['nations']['data']:
                    if who == " alliance_position:[0,1]":
                        if x['alliance_position'] not in ["NOALLIANCE", "APPLICANT"]:
                            continue
                    elif who == " alliance_id:0":
                        if x['alliance_id'] != "0":
                            continue
                    if not minscore < x['score'] < maxscore:
                        continue
                    if beige:
                        pass
                    else:
                        if x['color'] == "beige":
                            continue
                        else: 
                            pass
                    used_slots = 0
                    for war in x['wars']:
                        if war['turnsleft'] > 0 and war['defid'] == x['id']:
                            used_slots += 1
                        for attack in war['attacks']:
                            if attack['loot_info']:
                                attack['loot_info'] = attack['loot_info'].replace("\r\n", "")
                    if x['alliance_id'] in ["4729", "8819"] + dnr_alliance_ids:
                        continue
                    if used_slots > max_wars:
                        continue
                    if (datetime.utcnow() - datetime.strptime(x['last_active'], "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=None)).days < inactive_limit:
                        continue

                    # minimum loot filter start
                    prev_nat_loot = False
                    x['def_slots'] = 0
                    x['time_since_war'] = "14+"
                    
                    if x['wars'] != []:
                        for war in x['wars']:
                            if war['date'] == '-0001-11-30 00:00:00':
                                x['wars'].remove(war)
                            elif war['defid'] == x['id']:
                                if war['turnsleft'] > 0:
                                    x['def_slots'] += 1
                                
                        wars = sorted(x['wars'], key=lambda k: k['date'], reverse=True)
                        war = wars[0]
                        if x['def_slots'] == 0:
                            x['time_since_war'] = (datetime.utcnow() - datetime.strptime(war['date'], "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=None)).days
                        else:
                            x['time_since_war'] = "Ongoing"
                        for war in wars:
                            if war['turnsleft'] <= 0:
                                nation_loot = 0
                                for attack in war['attacks']:
                                    if attack['victor'] == x['id']:
                                        continue
                                    if attack['loot_info']:
                                        text = attack['loot_info']
                                        if "won the war and looted" in text:
                                            nation_loot += utils.beige_loot_value(text, prices)
                                        else:
                                            continue
                                try:
                                    if war['attacker']['war_policy'] == "ATTRITION":
                                        nation_loot = nation_loot / 80 * 100
                                    elif war['attacker']['war_policy'] == "PIRATE":
                                        nation_loot = nation_loot / 140 * 100
                                    if war['attacker']['advanced_pirate_economy']:
                                        nation_loot = nation_loot / 110 * 100 
                                    if war['war_type'] == "ATTRITION":
                                        nation_loot = nation_loot * 4
                                    elif war['war_type'] == "ORDINARY":
                                        nation_loot = nation_loot * 2
                                    x['nation_loot'] = f"{round(nation_loot):,}"
                                    x['nation_loot_value'] = nation_loot
                                    prev_nat_loot = True
                                except:
                                    # if you are here, it is probably because the attacker has deleted their nation
                                    pass
                                break

                    if prev_nat_loot == False:
                        x['nation_loot'] = "NaN"
                        x['nation_loot_value'] = 0
                    
                    if x['nation_loot_value'] < minimum_beige_loot:
                        continue
                    # minimum loot filter end

                    if new_turn:
                        x['beige_turns'] -= 1
                        x['vacation_mode_turns'] -= 1
                    target_list.append(x)

                    
            if len(target_list) == 0:
                await ctx.edit(content="No targets matched your criteria!", attachments=[])
                return

            filters = f"Nation information was fetched <t:{last_fetched}:R>\n"
            filter_list = []
            if not beige or who != "" or max_wars != 3 or performace_filter or inactive_limit != 0 or minimum_beige_loot != 0 or dnr_alliance_ids != []:
                filters += "Active filters: "
                if not beige:
                    filter_list.append("hide beige nations")
                if who != "":
                    if who == " alliance_position:[0,1]":
                        filter_list.append("hide full alliance members")
                    elif who == " alliance_id:0":
                        filter_list.append("hide full alliance members and applicants")
                if max_wars != 3:
                    if max_wars == 0:
                        filter_list.append("0 active wars")
                    else:
                        filter_list.append(f"{max_wars} or less active wars")
                if performace_filter:
                    filter_list.append('omit "bad" targets')
                if inactive_limit != 0:
                    filter_list.append(f"hide nations that logged in within the last {inactive_limit} days")
                if minimum_beige_loot != 0:
                    filter_list.append(f"hide nations with less than ${minimum_beige_loot:,} previous beige loot".replace(",000,000","m"))
                if dnr_alliance_ids:
                    filter_list.append(f"hide {len(dnr_alliance_ids)} alliances marked as do not raid")
                filters = filters + ", ".join(filter_list)
            else:
                filters += "No active filters"
            
            await async_mongo.global_users.find_one_and_update({"user": ctx.author.id}, {"$set": {"raids_config": {"webpage": webpage, "discord_embed": discord_embed, "who": who, "max_wars": max_wars, "inactive_limit": inactive_limit, "beige": beige, "performace_filter": performace_filter, "minimum_beige_loot": minimum_beige_loot}}})

            await ctx.edit(content='Calculating best targets...')

            alliances = {x['id']: x for x in await utils.listify(async_mongo.alliances.find({"id": {"$in": [x['alliance_id'] for x in target_list]}}))}

            for target in target_list:
                embed = discord.Embed(title=f"{target['nation_name']}", url=f"https://politicsandwar.com/nation/id={target['id']}", description=f"{filters}\n\u200b", color=0xff5100)
                target['infrastructure'] = 0
                
                embed.add_field(name="Previous nation loot", value=target["nation_loot"])

                if target['alliance_id'] != "0":
                    try:
                        target['taxable'] = (target['color'] == alliances[target['alliance_id']]['color'])
                    except KeyError:
                        # Here we are if the alliance is not in the cache
                        target['taxable'] = True
                else: 
                    target['taxable'] = False

                rev_obj = await utils.revenue_calc(ctx, target, radiation, treasures, prices, colors, seasonal_mod)

                target['monetary_net_num'] = rev_obj['monetary_net_num']
                embed.add_field(name="Monetary Net Income", value=rev_obj['mon_net_txt'])
                
                target['net_cash_num'] = rev_obj['net_cash_num']
                target['money_txt'] = rev_obj['money_txt']
                embed.add_field(name="Net Cash Income", value=rev_obj['money_txt'])

                target['treasures'] = len(target['treasures'])
                embed.add_field(name="Treasures", value=target['treasures'])

                embed.add_field(name="Slots", value=f"{target['def_slots']}/3 used slots") 

                if target['last_active'] == '-0001-11-30 00:00:00':
                    days_inactive = 0
                else:
                    days_inactive = (datetime.utcnow() - datetime.strptime(target['last_active'], "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=None)).days

                for city in target['cities']:
                    target['infrastructure'] += city['infrastructure']

                embed.add_field(name="Beige", value=f"{target['beige_turns']} turns")

                embed.add_field(name="Inactivity", value=f"{days_inactive} days")

                if target['alliance']:
                    embed.add_field(name="Alliance", value=f"[{target['alliance']['name']}](https://politicsandwar.com/alliance/id={target['alliance_id']})\n{target['alliance_position'].lower().capitalize()}")
                else:
                    target['alliance'] = {"name": "None"}
                    embed.add_field(name="Alliance", value=f"No alliance")

                target['max_infra'] = rev_obj['max_infra']
                target['avg_infra'] = rev_obj['avg_infra']
                embed.add_field(name="Infra", value=f"Max: {rev_obj['max_infra']}\nAvg: {rev_obj['avg_infra']}")

                embed.add_field(name="Soldiers", value=f"{target['soldiers']:,} soldiers")

                embed.add_field(name="Tanks", value=f"{target['tanks']:,} tanks")

                embed.add_field(name="Aircraft", value=f"{target['aircraft']} aircraft")

                embed.add_field(name="Ships", value=f"{target['ships']:,} ships")

                embed.add_field(name="Nukes", value=f"{target['nukes']:,} nukes")

                embed.add_field(name="Missiles", value=f"{target['missiles']:,} missiles")
                
                # works perfectly fine, but the API is broken....
                # target['bounty_txt'] = "0"
                # bounty_info = {"ATTRITION": 0, "RAID": 0, "ORDINARY": 0, "NUCLEAR": 0}
                # for bounty in target['bounties']:
                #     if bounty['type'] == None:
                #         bounty['type'] = "NUCLEAR"
                #     bounty_info[bounty['type']] += bounty['amount']   
                # temp_list = []
                # for k, v in bounty_info.items():
                #     if v != 0:
                #         temp_list.append(f"{k.capitalize()}: ${v:,}")
                # target['bounty_txt'] = ", ".join(temp_list)

                ground_win_rate = self.winrate_calc((atck_ntn['soldiers'] * 1.75 + atck_ntn['tanks'] * 40), (target['soldiers'] * 1.75 + target['tanks'] * 40 + target['population'] * 0.0025))

                target['groundwin'] = ground_win_rate
                embed.add_field(name="Chance to get ground IT", value=str(round(100*ground_win_rate**3)) + "%")

                air_win_rate = self.winrate_calc((atck_ntn['aircraft'] * 3), (target['aircraft'] * 3))
                
                target['airwin'] = air_win_rate
                embed.add_field(name="Chance to get air IT", value=str(round(100*air_win_rate**3)) + "%")

                naval_win_rate = self.winrate_calc((atck_ntn['ships'] * 4), (target['ships'] * 4))
                
                target['navalwin'] = naval_win_rate
                embed.add_field(name="Chance to get naval IT", value=str(round(100*naval_win_rate**3)) + "%\n\u200b")

                target['winchance'] = round((ground_win_rate+air_win_rate+naval_win_rate)*100/3)

                if not webpage:
                    target['embed'] = embed

            if performace_filter:
                def determine(x):
                    if x['groundwin'] < .4 or x['nation_loot'] == "0" or x['net_cash_num'] < 10000:
                        return False
                    else:
                        return True
                target_list[:] = [target for target in target_list if determine(target)]
                if len(target_list) == 0:
                    await ctx.edit(content="No targets matched your criteria!", attachments=[])
                    no_timeout = True
                    return
                
            best_targets = sorted(target_list, key=lambda k: k['monetary_net_num'], reverse=True)

            if webpage:
                timestamp = round(datetime.utcnow().timestamp())
                webpage_embed = discord.Embed(title=f"Targets successfully gathered", description=f"{filters}\n\nYou can view your targets by pressing the button below.", color=0xff5100)
                class webpage_view(discord.ui.View):
                    def __init__(self):
                        super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                    @discord.ui.button(label=f"See your targets", style=discord.ButtonStyle.primary)
                    async def targets_callback(self, b: discord.Button, i: discord.Interaction):
                        await i.response.send_message(ephemeral=True, content=f"Go to http://132.145.71.195:5000/raids/{ctx.author.id}/{timestamp} to see your targets!")
                    
                    async def interaction_check(self, interaction) -> bool:
                        if interaction.user != ctx.author:
                            await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                            return False
                        else:
                            return True
                    
                    async def on_timeout(self):
                        await utils.run_timeout(ctx, view)
                
                await utils.write_web("raids", ctx.author.id, {"atck_ntn": atck_ntn, "best_targets": best_targets, "beige": beige, "user_id": ctx.author.id}, timestamp)

                view = webpage_view()
                await ctx.edit(content="", attachments=[], embed=webpage_embed, view=view)
                return

            elif discord_embed:
                pages = len(target_list)
                cur_page = 1

                def get_embed(nation):
                    nonlocal pages, cur_page
                    embed = nation['embed']
                    if "*" in nation['money_txt']:
                        embed.set_footer(text=f"Page {cur_page}/{pages}  |  * the income if the nation is out of food.")
                    else:
                        embed.set_footer(text=f"Page {cur_page}/{pages}")
                    return embed

                msg_embd = get_embed(best_targets[0])
                timed_out = False

                class embed_paginator(discord.ui.View):
                    def __init__(self):
                            super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                    async def button_check(self, x):
                        beige_button = [x for x in self.children if x.custom_id == "beige"][0]
                        user = await async_mongo.global_users.find_one({"user": ctx.author.id})
                        for entry in user['beige_alerts']:
                            if x['id'] == entry:
                                beige_button.disabled = True
                                return
                        if x['beige_turns'] > 0:
                            beige_button.disabled = False
                        else:
                            beige_button.disabled = True
                    
                    @discord.ui.button(label="<<", style=discord.ButtonStyle.primary)
                    async def far_left_callback(self, b: discord.Button, i: discord.Interaction):
                        nonlocal cur_page
                        cur_page = 1
                        msg_embd = get_embed(best_targets[cur_page-1])
                        await self.button_check(best_targets[cur_page-1])
                        await i.response.edit_message(content="", embed=msg_embd, view=view)

                    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
                    async def left_callback(self, b: discord.Button, i: discord.Interaction):
                        nonlocal cur_page
                        if cur_page > 1:
                            cur_page -= 1
                            msg_embd = get_embed(best_targets[cur_page-1])
                            await self.button_check(best_targets[cur_page-1])
                            await i.response.edit_message(content="", embed=msg_embd, view=view)
                        else:
                            cur_page = pages
                            msg_embd = get_embed(best_targets[cur_page-1])
                            await self.button_check(best_targets[cur_page-1])
                            await i.response.edit_message(content="", embed=msg_embd, view=view)
                    
                    @discord.ui.button(label=">", style=discord.ButtonStyle.primary)
                    async def right_callback(self, b: discord.Button, i: discord.Interaction):
                        nonlocal cur_page
                        if cur_page != pages:
                            cur_page += 1
                            msg_embd = get_embed(best_targets[cur_page-1])
                            await self.button_check(best_targets[cur_page-1])
                            await i.response.edit_message(content="", embed=msg_embd, view=view)
                        else:
                            cur_page = 1
                            msg_embd = get_embed(best_targets[cur_page-1])
                            await self.button_check(best_targets[cur_page-1])
                            await i.response.edit_message(content="", embed=msg_embd, view=view)

                    @discord.ui.button(label=">>", style=discord.ButtonStyle.primary)
                    async def far_right_callback(self, b: discord.Button, i: discord.Interaction):
                        nonlocal cur_page
                        cur_page = pages
                        msg_embd = get_embed(best_targets[cur_page-1])
                        await self.button_check(best_targets[cur_page-1])
                        await i.response.edit_message(content="", embed=msg_embd, view=view)
                
                    if best_targets[0]['beige_turns'] > 0:
                        disabled = False
                    else:
                        disabled = True

                    @discord.ui.button(label="Beige reminder", style=discord.ButtonStyle.primary, disabled=disabled, custom_id="beige")
                    async def beige_callback(self, b: discord.Button, i: discord.Interaction):
                        nonlocal cur_page
                        beige_button = [x for x in self.children if x.custom_id == "beige"][0]
                        cur_embed = best_targets[cur_page-1]
                        turns = cur_embed['beige_turns']
                        if turns == 0:
                            beige_button.disabled = True
                            await ctx.edit(view=view)
                            await i.response.send_message(content=f"They are not in beige!", ephemeral=True)
                            return
                        reminder = cur_embed['id']
                        user = await async_mongo.global_users.find_one({"user": ctx.author.id})
                        if user == None:
                            await i.response.send_message(content=f"I didn't find you in the database! Make sure to `/verify`!", ephemeral=True)
                            return
                        for entry in user['beige_alerts']:
                            if reminder == entry:
                                beige_button.disabled = True
                                await ctx.edit(view=view)
                                await i.response.send_message(content=f"You already have a beige reminder for this nation!", ephemeral=True)
                                return
                        await async_mongo.global_users.find_one_and_update({"user": ctx.author.id}, {"$push": {"beige_alerts": reminder}})
                        beige_button.disabled = True
                        await ctx.edit(view=view)
                        await i.response.send_message(content=f"A beige reminder for <https://politicsandwar.com/nation/id={cur_embed['id']}> was added!", ephemeral=True)

                    async def interaction_check(self, interaction) -> bool:
                        if interaction.user != ctx.author:
                            await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                            return False
                        else:
                            return True
                    
                    async def on_timeout(self):
                        await utils.run_timeout(ctx, view)
                    
                view = embed_paginator()
                await ctx.edit(content="", embed=msg_embd, attachments=[], view=view)

            else:
                targets = sorted(best_targets, key=lambda k: k['nation_loot_value'], reverse=True)
                desc = filters
                for n in range(min(20, len(targets))):
                    target = targets[n]
                    desc += f"\n\n**Last beige: ${target['nation_loot']}**\n[{target['nation_name']}](https://politicsandwar.com/nation/id={target['id']}) | Active: <t:{round(datetime.strptime(target['last_active'], '%Y-%m-%dT%H:%M:%S%z').timestamp())}:R> | Ground IT: {round(100*target['groundwin']**3)}%"
                embed = discord.Embed(title="Top nations by beige loot", description=desc, color=0xff5100)
                embed.set_footer(text="Contact RandomNoobster#0093 for help or bug reports")
                await ctx.edit(content="", embed=embed, attachments=[], view=None)

        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
    
    reminder_group = SlashCommandGroup("reminders", "Beige reminders")

    @reminder_group.command(
        name="show",
        description="Show all your beige reminders"
    )
    async def reminders(self, ctx: discord.ApplicationContext):
        try:
            await ctx.defer()
            person = await async_mongo.global_users.find_one({"user": ctx.author.id})

            if person == None:
                await ctx.respond(content=f"I didn't find you in the database! Make sure that you have verified your nation!")
                return

            if person['beige_alerts'] == []:
                insults = ['ha loser', 'what a nub', 'such a pleb', 'get gud', 'u suc lol', 'ur useless lmao']
                insult = random.choice(insults)
                await ctx.respond(content=f"You have no beige reminders!\n\n||{insult}||")
                return

            res = (await utils.call(f"{{nations(id:[{','.join(person['beige_alerts'])}]){{data{utils.get_query(queries.REMINDERS)}}}}}"))['data']['nations']['data']

            reminders = []
            for alert in person['beige_alerts']:
                for nation in res:
                    if alert == nation['id']:
                        beige_turns = int(nation['beige_turns'])
                        vacation_mode_turns = int(nation['vacation_mode_turns'])
                        turns = sorted([beige_turns, vacation_mode_turns])[1]
                        time = datetime.utcnow()
                        if time.hour % 2 == 0:
                            time += timedelta(hours=turns*2)
                        else:
                            time += timedelta(hours=turns*2-1)
                        time = datetime(time.year, time.month, time.day, time.hour)
                        reminders.append(f"\n<t:{round(time.timestamp())}> <t:{round(time.timestamp())}:R> - [{nation['nation_name']}](https://politicsandwar.com/nation/id={alert})")

            reminders = sorted(reminders)
            embeds = []

            for n in range(0, len(reminders), 20):
                embed = discord.Embed(title="Beige reminders", description="".join(reminders[n:n+30]), color=0xff5100)
                embeds.append(embed)

            if len(embeds) > 1:
                cur_page = 0
                pages = len(embeds)
                class switch(discord.ui.View):
                    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
                    async def left_callback(self, b: discord.Button, i: discord.Interaction):
                        nonlocal cur_page
                        if cur_page == 1:
                            cur_page = pages
                            await i.response.edit_message(embed=embeds[cur_page])
                        else:
                            cur_page -= 1
                            await i.response.edit_message(embed=embeds[cur_page])
                    
                    @discord.ui.button(label=">", style=discord.ButtonStyle.primary)
                    async def right_callback(self, b: discord.Button, i: discord.Interaction):
                        nonlocal cur_page
                        if cur_page == pages:
                            cur_page = 0
                            await i.response.edit_message(embed=embeds[cur_page])
                        else:
                            cur_page += 1
                            await i.response.edit_message(embed=embeds[cur_page])
                    
                    async def interaction_check(self, interaction) -> bool:
                        if interaction.user != ctx.author:
                            await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                            return False
                        else:
                            return True
                    
                    async def on_timeout(self):
                        await utils.run_timeout(ctx, view)
                
                view = switch()
            else:
                view = None

            await ctx.respond(embed=embeds[0])
            if view != None:
                await ctx.edit(view=view)

        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
        
    @reminder_group.command(
        name="delete",
        description="Delete a beige reminder"
    )
    async def delreminder(
        self,
        ctx: discord.ApplicationContext,
        nation: Option(str, "Nation name, nation link, discord username etc of the nation whose beige reminder you want to remove")
    ):
        try:
            await ctx.defer()
            person = await async_mongo.global_users.find_one({"user": ctx.author.id})
            if person == None:
                await ctx.respond(content=f"I didn't find you in the database! Make sure that you have verified your nation!")
                return
            parsed_nation = await utils.find_nation(nation)
            if parsed_nation == None:
                await ctx.respond("I could not find that nation!")
                return
            else:
                id = parsed_nation['id']

            found = False
            for alert in person['beige_alerts']:
                if alert == id:
                    person['beige_alerts'].remove(alert)
                    found = True
                    break

            if not found:
                await ctx.respond(content="I did not find a reminder for that nation!")
                return

            await async_mongo.global_users.find_one_and_update({"user": ctx.author.id}, {"$pull": {"beige_alerts": id}})
            await ctx.respond(content=f"Your beige reminder for https://politicsandwar.com/nation/id={id} was deleted.")

        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    @reminder_group.command(
        name="add",
        description="Add a beige reminder"
    )
    async def addreminder(
        self,
        ctx: discord.ApplicationContext,
        nation: Option(str, "Nation name, nation link, discord username etc of the nation you want to add a beige reminder for")
    ):
        try:
            await ctx.defer()
            nation = await utils.find_nation(nation)

            if nation == None:
                await ctx.respond(content='I could not find that nation!')
                return

            res = (await utils.call(f"{{nations(first:1 id:{nation['id']}){{data{utils.get_query(queries.REMINDERS)}}}}}"))['data']['nations']['data'][0]

            if res['beige_turns'] == 0 and res['vacation_mode_turns'] == 0:
                await ctx.respond(content="They are not in beige or vacation mode!")
                return

            reminder = nation['id']
            user = await async_mongo.global_users.find_one({"user": ctx.author.id})

            if user == None:
                await ctx.respond(content=f"I didn't find you in the database! Make sure that you have verified your nation!")
                return

            for entry in user['beige_alerts']:
                if reminder == entry:
                    await ctx.respond(content=f"You already have a beige reminder for this nation!")
                    return

            await async_mongo.global_users.find_one_and_update({"user": ctx.author.id}, {"$push": {"beige_alerts": reminder}})
            await ctx.respond(content=f"A beige reminder for https://politicsandwar.com/nation/id={nation['id']} was added.")

        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    @slash_command(
        name="battlesimulation",
        description='Simulate battles between two nations'
    )
    async def battlesim(
        self,
        ctx: discord.ApplicationContext,
        nation1: Option(str, "Nation name, leader name, nation id, nation link or discord username. Defaults to your nation.") = None,
        nation2: Option(str, "Nation name, leader name, nation id, nation link or discord username. Defaults to your nation.") = None
    ):
        try:
            await ctx.defer()

            if nation1 == None and nation2:
                nation1 = nation2
                nation2 = None

            if nation1 == None:
                nation1 = ctx.author.id
            nation1_nation = await utils.find_nation_plus(self, nation1)
            if not nation1_nation:
                if nation2 == None:
                    await ctx.respond(content='I could not find that nation!')
                    return
                else:
                    await ctx.respond(content='I could not find nation 1!')
                    return 
            nation1_id = str(nation1_nation['id'])

            done = False
            if isinstance(ctx.channel, discord.Thread) and nation2 == None:
                try:
                    chan = ctx.channel.name
                    nation2_id = str(chan[chan.index("(")+1:-1])
                    done = True
                except:
                    pass

            if not done:
                if nation2 == None:
                    nation2 = ctx.author.id
                nation2_nation = await utils.find_nation_plus(self, nation2)
                if not nation2_nation:
                    if nation2 == None:
                        await ctx.respond(content='I was able to find the nation you linked, but I could not find *your* nation!')
                        return
                    else:
                        await ctx.respond(content='I could not find nation 2!')
                        return 
                nation2_id = str(nation2_nation['id'])

            results = await self.battle_calc(nation1_id, nation2_id)

            embed = discord.Embed(title="Battle Simulator", description=f"These are the results for when [{results['nation1']['nation_name']}](https://politicsandwar.com/nation/id={results['nation1']['id']}){results['nation1_append']} attacks [{results['nation2']['nation_name']}](https://politicsandwar.com/nation/id={results['nation2']['id']}){results['nation2_append']}\nIf you want to use custom troop counts, you can use the [in-game battle simulators](https://politicsandwar.com/tools/)", color=0xff5100)
            embed1 = discord.Embed(title="Battle Simulator", description=f"These are the results for when [{results['nation2']['nation_name']}](https://politicsandwar.com/nation/id={results['nation2']['id']}){results['nation2_append']} attacks [{results['nation1']['nation_name']}](https://politicsandwar.com/nation/id={results['nation1']['id']}){results['nation1_append']}\nIf you want to use custom troop counts, you can use the [in-game battle simulators](https://politicsandwar.com/tools/)", color=0xff5100)

            if results['nation2']['soldiers'] + results['nation2']['tanks'] + results['nation1']['soldiers'] + results['nation1']['tanks'] == 0:
                embed.add_field(name="Ground Attack", value="Nobody has any forces!")
                embed1.add_field(name="Ground Attack", value="Nobody has any forces!")
            else:
                embed.add_field(name="Ground Attack", value=f"Immense Triumph: {round(results['nation1_ground_it']*100)}%\nModerate Success: {round(results['nation1_ground_mod']*100)}%\nPyrrhic Victory: {round(results['nation1_ground_pyr']*100)}%\nUtter Failure: {round(results['nation1_ground_fail']*100)}%")
                embed1.add_field(name="Ground Attack", value=f"Immense Triumph: {round(results['nation2_ground_it']*100)}%\nModerate Success: {round(results['nation2_ground_mod']*100)}%\nPyrrhic Victory: {round(results['nation2_ground_pyr']*100)}%\nUtter Failure: {round(results['nation2_ground_fail']*100)}%")
            
            if results['nation2']['aircraft'] + results['nation1']['aircraft'] != 0:
                embed.add_field(name="Airstrike", value=f"Immense Triumph: {round(results['nation1_air_it']*100)}%\nModerate Success: {round(results['nation1_air_mod']*100)}%\nPyrrhic Victory: {round(results['nation1_air_pyr']*100)}%\nUtter Failure: {round(results['nation1_air_fail']*100)}%")
                embed1.add_field(name="Airstrike", value=f"Immense Triumph: {round(results['nation1_air_fail']*100)}%\nModerate Success: {round(results['nation1_air_pyr']*100)}%\nPyrrhic Victory: {round(results['nation1_air_mod']*100)}%\nUtter Failure: {round(results['nation1_air_it']*100)}%")
            else:
                embed.add_field(name="Airstrike", value="Nobody has any forces!")
                embed1.add_field(name="Airstrike", value="Nobody has any forces!")

            if results['nation2']['ships'] + results['nation1']['ships'] != 0:
                embed.add_field(name="Naval Battle", value=f"Immense Triumph: {round(results['nation1_naval_it']*100)}%\nModerate Success: {round(results['nation1_naval_mod']*100)}%\nPyrrhic Victory: {round(results['nation1_naval_pyr']*100)}%\nUtter Failure: {round(results['nation1_naval_fail']*100)}%")
                embed1.add_field(name="Naval Battle", value=f"Immense Triumph: {round(results['nation1_naval_fail']*100)}%\nModerate Success: {round(results['nation1_naval_pyr']*100)}%\nPyrrhic Victory: {round(results['nation1_naval_mod']*100)}%\nUtter Failure: {round(results['nation1_naval_it']*100)}%")

            else:
                embed.add_field(name="Naval Battle", value="Nobody has any forces!")
                embed1.add_field(name="Naval Battle", value="Nobody has any forces!")

            embed.add_field(name="Casualties", value=f"Att. Sol.: {results['nation1_ground_nation1_avg_soldiers']:,} ± {results['nation1_ground_nation1_diff_soldiers']:,}\nAtt. Tnk.: {results['nation1_ground_nation1_avg_tanks']:,} ± {results['nation1_ground_nation1_diff_tanks']:,}\n\nDef. Sol.: {results['nation1_ground_nation2_avg_soldiers']:,} ± {results['nation1_ground_nation2_diff_soldiers']:,}\nDef. Tnk.: {results['nation1_ground_nation2_avg_tanks']:,} ± {results['nation1_ground_nation2_diff_tanks']:,}\n\n{results['nation2']['aircas']}")        
            embed1.add_field(name="Casualties", value=f"Att. Sol.: {results['nation2_ground_nation2_avg_soldiers']:,} ± {results['nation2_ground_nation2_diff_soldiers']:,}\nAtt. Tnk.: {results['nation2_ground_nation2_avg_tanks']:,} ± {results['nation2_ground_nation2_diff_tanks']:,}\n\nDef. Sol.: {results['nation2_ground_nation1_avg_soldiers']:,} ± {results['nation2_ground_nation1_diff_soldiers']:,}\nDef. Tnk.: {results['nation2_ground_nation1_avg_tanks']:,} ± {results['nation2_ground_nation1_diff_tanks']:,}\n\n{results['nation1']['aircas']}")        
            
            embed.add_field(name="Casualties", value=f"*Targeting air:*\nAtt. Plane: {results['nation1_airvair_nation1_avg']:,} ± {results['nation1_airvair_nation1_diff']:,}\nDef. Plane: {results['nation1_airvair_nation2_avg']:,} ± {results['nation1_airvair_nation2_diff']:,}\n\n*Targeting other:*\nAtt. Plane: {results['nation1_airvother_nation1_avg']:,} ± {results['nation1_airvother_nation1_diff']:,}\nDef. Plane: {results['nation1_airvother_nation2_avg']:,} ± {results['nation1_airvother_nation2_diff']:,}\n\u200b")        
            embed1.add_field(name="Casualties", value=f"*Targeting air:*\nAtt. Plane: {results['nation2_airvair_nation2_avg']:,} ± {results['nation2_airvair_nation2_diff']:,}\nDef. Plane: {results['nation2_airvair_nation1_avg']:,} ± {results['nation2_airvair_nation1_diff']:,}\n\n*Targeting other:*\nAtt. Plane: {results['nation2_airvother_nation2_avg']:,} ± {results['nation2_airvother_nation2_diff']:,}\nDef. Plane: {results['nation2_airvother_nation1_avg']:,} ± {results['nation2_airvother_nation1_diff']:,}\n\u200b")        

            embed.add_field(name="Casualties", value=f"Att. Ships: {results['nation1_naval_nation1_avg']:,} ± {results['nation1_naval_nation1_diff']:,}\nDef. Ships: {results['nation1_naval_nation2_avg']:,} ± {results['nation1_naval_nation2_diff']:,}")        
            embed1.add_field(name="Casualties", value=f"Att. Ships: {results['nation2_naval_nation2_avg']:,} ± {results['nation2_naval_nation2_diff']:,}\nDef. Ships: {results['nation2_naval_nation1_avg']:,} ± {results['nation2_naval_nation1_diff']:,}")        

            cur_page = 1

            timestamp = round(datetime.utcnow().timestamp())
            await utils.write_web("damage", ctx.author.id, {"results": results}, timestamp)
            url = f"http://132.145.71.195:5000/damage/{ctx.author.id}/{timestamp}"

            class switch(discord.ui.View):
                def __init__(self):
                    super().__init__(discord.ui.Button(label="Damage sheet", url=url))

                @discord.ui.button(label="Switch attacker/defender", style=discord.ButtonStyle.primary)
                async def callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal cur_page
                    if cur_page == 1:
                        cur_page = 2
                        await i.response.edit_message(embed=embed1)
                    else:
                        cur_page = 1
                        await i.response.edit_message(embed=embed)
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await ctx.edit(content=f"<@{ctx.author.id}> The command timed out!")
                    
            await ctx.respond(embed=embed, content="", view=switch())
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    @slash_command(
        name="counters",
        description="Find counters"
    )
    async def counters(
        self,
        ctx: discord.ApplicationContext,
        nation: Option(str, "The nation you want to counter")
    ):
        try:
            await ctx.defer()

            result = await utils.find_nation_plus(self, nation)
            if result is None:
                await ctx.respond(f"I could not find that nation!")
                return

            config = await async_mongo.guild_configs.find_one({"guild_id": ctx.guild.id})

            fail = False
            if not config:
                fail = True
            else:
                try:
                    alliance_ids = config['counters_alliance_ids']
                    if len(alliance_ids) == 0:
                        fail = True
                except:
                    fail = True
            if fail:
                await ctx.respond("This command has not been configured for this server! Someone with the `manage_server` permission must use `/config`!")
                return

            embed = discord.Embed(title="Counters", description=f"[Explore counters against {result['nation_name']} on Slotter](https://slotter.bsnk.dev/search?nation={result['id']}&alliances={','.join(alliance_ids)}&countersMode=true&threatsMode=false&vm=false&grey=true&beige=false)", color=0xff5100)
            embed.set_footer(text="Slotter was made by Bann and is not affiliated with Autolycus")
            await ctx.respond(embed=embed)
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
    
    @slash_command(
        name="targetsheet",
        description='Create a sheet to help with target assignment',
        guild_ids=[729979781940248577, 434071714893398016]
    )
    async def targetsheet(
        self,
        ctx: discord.ApplicationContext,
        allied_alliance_ids: Option(str, "The alliance id(s) to use when finding allied nations.") = [],
        enemy_alliance_ids: Option(str, "The alliance id(s) to use when finding enemy nations.") = []
    ):
        try:
            await ctx.defer()
            allied_id_list, id_str = utils.str_to_id_list(allied_alliance_ids or "")
            if id_str == "":
                try:
                    allied_id_list = await async_mongo.guild_configs.find_one({"guild_id": ctx.guild.id})['counters_alliance_ids']
                except:
                    await ctx.respond("I could not find any allied alliances for this server! Someone with the `manage_server` permission must use `/config counters`, or you must supply some id(s) when you call this command!")
                    return

            enemy_id_list, id_str = utils.str_to_id_list(enemy_alliance_ids or "")
            if id_str == "":
                try:
                    enemy_id_list = await async_mongo.guild_configs.find_one({"guild_id": ctx.guild.id})['targets_alliance_ids']
                except:
                    await ctx.respond("I could not find any enemy alliances for this server! Someone with the `manage_server` permission must use `/config targets`, or you must supply some id(s) when you call this command!")
                    return

            allied_nations = await utils.paginate_call(f"{{nations(page:page_number vmode:false alliance_position:[2,3,4,5] first:500 alliance_id:[{','.join(allied_id_list)}]) {{paginatorInfo{{hasMorePages}} data{{id discord leader_name nation_name warpolicy vacation_mode_turns flag last_active alliance_position_id continent dompolicy vds irond fallout_shelter military_salvage propaganda_bureau population alliance_id beige_turns score color soldiers tanks aircraft ships missiles nukes bounties{{amount type}} treasures{{name}} alliance{{name acronym id}} wars{{date winner attacker{{war_policy}} defender{{war_policy}} war_type attid defid groundcontrol airsuperiority navalblockade att_fortify def_fortify attpeace defpeace turnsleft attacks{{loot_info}}}} alliance_position num_cities cities{{infrastructure land barracks factory airforcebase drydock}}}}}}}}", "nations")
            enemy_nations = await utils.paginate_call(f"{{nations(page:page_number vmode:false alliance_position:[2,3,4,5] first:500 alliance_id:[{','.join(enemy_id_list)}]) {{paginatorInfo{{hasMorePages}} data{{id discord leader_name nation_name warpolicy vacation_mode_turns flag last_active alliance_position_id continent dompolicy vds irond fallout_shelter military_salvage propaganda_bureau population alliance_id beige_turns score color soldiers tanks aircraft ships missiles nukes bounties{{amount type}} treasures{{name}} alliance{{name acronym id}} wars{{date winner attacker{{war_policy}} defender{{war_policy}} war_type attid defid groundcontrol airsuperiority navalblockade att_fortify def_fortify attpeace defpeace turnsleft attacks{{loot_info}}}} alliance_position num_cities cities{{infrastructure land barracks factory airforcebase drydock}}}}}}}}", "nations")

            for enemy in enemy_nations:
                off_wars = 0
                def_wars = 0
                for war in enemy['wars']:
                    if war['turnsleft'] > 0:
                        if war['attid'] == enemy['id']:
                            off_wars += 1
                        else:
                            def_wars += 1
                enemy['off_wars'] = off_wars
                enemy['def_wars'] = def_wars
                enemy['tot_wars'] = off_wars + def_wars
                chances = []
                for ally in allied_nations:
                    minscore = round(ally['score'] * 0.75)
                    maxscore = round(ally['score'] * 2.5)
                    if enemy['score'] >= minscore and enemy['score'] <= maxscore:
                        results = await self.battle_calc(nation1 = ally, nation2 = enemy)
                        chances.append({"id": ally['id'], "winchance": (results["nation1_ground_win_rate"] + results["nation1_air_win_rate"]) / 2})
                chances = sorted(chances, key=lambda x: x['winchance'], reverse=True)
                enemy['winchance'] = chances
                enemy['milt'] = utils.militarization_checker(enemy)
                
            timestamp = round(datetime.utcnow().timestamp())
            
            await utils.write_web("attacksheet", ctx.author.id, {"allies": allied_nations, "enemies": enemy_nations}, timestamp)

            await ctx.respond(f"The sheet can be found here: http://132.145.71.195:5000/attacksheet/{ctx.author.id}/{timestamp}")
            
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
    
    @slash_command(
        name="war_status",
        description="Get an overivew of a nation's ongoing wars.",
    )
    async def war_status(
        self,
        ctx: discord.ApplicationContext,
        nation: Option(str, "The person whose war status you'd like to see") = None
    ):
        await ctx.defer()
        if not nation:
            if isinstance(ctx.channel, discord.Thread) and "(" in ctx.channel.name and ")" in ctx.channel.name:
                nation_id = ctx.channel.name[ctx.channel.name.rfind("(")+1:-1]
                int(nation_id) # throw an error if not a number
            else:
                try:
                    person = await utils.find_user(self, ctx.author.id)
                    nation_id = person['id']
                except:
                    await ctx.respond("I do not know who to find the war status of.")
                    return
        else:
            person = await utils.find_nation_plus(self, nation)
            if not person:
                await ctx.respond("I could not find that nation!")
                return
            nation_id = str(person['id'])

        nation = (await utils.call(f"{{nations(first:1 id:{nation_id}) {{data{utils.get_query(queries.WAR_STATUS)}}}}}"))['data']['nations']['data'][0]

        if nation['pirate_economy']:
            max_offense = 6
        if nation['advanced_pirate_economy']:
            max_offense = 7
        else:
            max_offense = 5

        milt = utils.militarization_checker(nation)
        max_sol = milt['max_soldiers']
        max_tnk = milt['max_tanks']
        max_pln = milt['max_aircraft']
        max_shp = milt['max_ships']  
        
        nation['offensive_wars'] = [y for y in nation['wars'] if y['turnsleft'] > 0 and y['attid'] == nation['id']]
        nation['defensive_wars'] = [y for y in nation['wars'] if y['turnsleft'] > 0 and y['defid'] == nation['id']]
        nation['wars'] = nation['offensive_wars'] + nation['defensive_wars']

        if nation['alliance']:
            alliance = f"[{nation['alliance']['name']}](https://politicsandwar.com/alliance/id={nation['alliance_id']})"
        else:
            alliance = "No alliance"

        desc = f"[{nation['nation_name']}](https://politicsandwar.com/nation/id={nation['id']}) | {alliance}\n\nLast login: <t:{round(datetime.strptime(nation['last_active'], '%Y-%m-%dT%H:%M:%S%z').timestamp())}:R>\nOffensive wars: {len(nation['offensive_wars'])}/{max_offense}\nDefensive wars: {len(nation['defensive_wars'])}/3\nDefensive range: {round(nation['score'] / 2.5)} - {round(nation['score'] / 0.75)}\nCities: {nation['num_cities']}\nBeige (turns): {nation['beigeturns']}\n\nSoldiers: **{nation['soldiers']:,}** / {max_sol:,}\nTanks: **{nation['tanks']:,}** / {max_tnk:,}\nPlanes: **{nation['aircraft']:,}** / {max_pln:,}\nShips: **{nation['ships']:,}** / {max_shp:,}"
        embed = discord.Embed(title=f"{nation['nation_name']} ({nation['id']}) & their wars", description=desc, color=0xff5100)
        embed1 = discord.Embed(title=f"{nation['nation_name']} ({nation['id']}) & their wars", description=desc, color=0xff5100)
        embed2 = discord.Embed(title=f"{nation['nation_name']} ({nation['id']}) & their wars", description=desc, color=0xff5100)
        embed.set_footer(text=f"\nThe chance to get immense triumphs is if the nation attacks {nation['nation_name']}. On average, it's worth attacking if the % is above 13%. Use /battlesimulation for more detailed predictions.")
        embed1.set_footer(text=f"\nThe chance to get immense triumphs is if the nation attacks {nation['nation_name']}. On average, it's worth attacking if the % is above 13%. Use /battlesimulation for more detailed predictions.")
        embed2.set_footer(text=f"\nThese are the average net damage per MAP predictions for the nations in question. Negative numbers means the net damage would be negative (not good). Use /damage for more detailed predictions.")
        n = 1

        for war in nation['wars']:
            n += 1
            if n % 2 == 0:
                embed.add_field(name="\u200b", value="\u200b", inline=False)
                embed1.add_field(name="\u200b", value="\u200b", inline=False)
                embed2.add_field(name="\u200b", value="\u200b", inline=False)
            else:
                embed.add_field(name="\u200b", value="\u200b", inline=True)
                embed1.add_field(name="\u200b", value="\u200b", inline=True)
                embed2.add_field(name="\u200b", value="\u200b", inline=True)

            if war in nation['offensive_wars']:
                result = await self.battle_calc(nation1=nation, nation2_id=war['defender']['id'])
                war_emoji_1 = "<:offensive_swords:1054714270547447828>"
                war_emoji_2 = "<:defensive_shield:1054714196715110411>"
                x = war['defender']
                main_enemy_res = war['att_resistance']
                main_enemy_points = war['attpoints']
                their_enemy_points = war['defpoints']
                their_enemy_res = war['def_resistance']
            else:
                result = await self.battle_calc(nation1=nation, nation2_id=war['attacker']['id'])
                war_emoji_1 = "<:defensive_shield:1054714196715110411>"
                war_emoji_2 = "<:offensive_swords:1054714270547447828>"
                x = war['attacker']
                main_enemy_res = war['def_resistance']
                main_enemy_points = war['defpoints']
                their_enemy_points = war['attpoints']
                their_enemy_res = war['att_resistance']
            
            main_enemy_bar = ""
            their_enemy_bar = ""
            for z in range(math.ceil(main_enemy_res / 10)):
                if main_enemy_res > 66:
                    main_enemy_bar += "🟩"
                elif main_enemy_res > 33:
                    main_enemy_bar += "🟨"
                else:
                    main_enemy_bar += "🟥"
            while len(main_enemy_bar) < 10:
                main_enemy_bar += "⬛"
            
            for z in range(math.ceil(their_enemy_res / 10)):
                if their_enemy_res > 66:
                    their_enemy_bar += "🟩"
                elif their_enemy_res > 33:
                    their_enemy_bar += "🟨"
                else:
                    their_enemy_bar += "🟥"
            while len(their_enemy_bar) < 10:
                their_enemy_bar += "⬛"

            if x['pirate_economy']:
                max_offense = 6
            if x['advanced_pirate_economy']:
                max_offense = 7
            else:
                max_offense = 5
            
            if x['beigeturns'] > 0:
                beige = f"\nBeige (turns): {x['beigeturns']}"
            else:
                beige = ""

            x_milt = utils.militarization_checker(x)
            max_sol = x_milt['max_soldiers']
            max_tnk = x_milt['max_tanks']
            max_pln = x_milt['max_aircraft']
            max_shp = x_milt['max_ships']          

            if x['vmode'] > 0:
                vmstart = "~~"
                vmend = "~~"
            else:
                vmstart = ""
                vmend = ""

            x['offensive_wars'] = [y for y in x['wars'] if y['turnsleft'] > 0 and y['attid'] == x['id']]
            x['defensive_wars'] = [y for y in x['wars'] if y['turnsleft'] > 0 and y['defid'] == x['id']]

            if x['alliance']:
                alliance = f"[{x['alliance']['name']}](https://politicsandwar.com/alliance/id={x['alliance_id']})"
            else:
                alliance = "No alliance"

            embed.add_field(name=f"{x['nation_name']} ({x['id']})", value=f"{vmstart}[War timeline](https://politicsandwar.com/nation/war/timeline/war={war['id']}) | {alliance}\n\n{war_emoji_1} **[{nation['nation_name']}](https://politicsandwar.com/nation/id={nation['id']})**{result['nation1_append']}\n{main_enemy_bar}\n**{main_enemy_res}/100** | MAPs: **{main_enemy_points}/12**\n\n{war_emoji_2} **[{x['nation_name']}](https://politicsandwar.com/nation/id={x['id']})**{result['nation2_append']}\n{their_enemy_bar}\n**{their_enemy_res}/100** | MAPs: **{their_enemy_points}/12**\n\nExpiration (turns): {war['turnsleft']}\nLast login: <t:{round(datetime.strptime(x['last_active'], '%Y-%m-%dT%H:%M:%S%z').timestamp())}:R>\nOngoing wars: {len(x['offensive_wars'] + x['defensive_wars'])}\n\nGround IT chance: **{round(100 * result['nation2_ground_win_rate']**3)}%**\nAir IT chance: **{round(100 * result['nation2_air_win_rate']**3)}%**\nNaval IT chance: **{round(100 * result['nation2_naval_win_rate']**3)}%**{vmend}", inline=True)
            embed1.add_field(name=f"{x['nation_name']} ({x['id']})", value=f"{vmstart}[War timeline](https://politicsandwar.com/nation/war/timeline/war={war['id']}) | {alliance}\n\n{war_emoji_1} **[{nation['nation_name']}](https://politicsandwar.com/nation/id={nation['id']})**{result['nation1_append']}\n{war_emoji_2} **[{x['nation_name']}](https://politicsandwar.com/nation/id={x['id']})**{result['nation2_append']}\n\nOffensive wars: {len(x['offensive_wars'])}/{max_offense}\nDefensive wars: {len(x['defensive_wars'])}/3{beige}\n\n Soldiers: **{x['soldiers']:,}** / {max_sol:,}\nTanks: **{x['tanks']:,}** / {max_tnk:,}\nPlanes: **{x['aircraft']:,}** / {max_pln:,}\nShips: **{x['ships']:,}** / {max_shp:,}\nMissiles: {x['missiles']}\nNukes: {x['nukes']}\n\nGround IT chance: **{round(100 * result['nation2_ground_win_rate']**3)}%**\nAir IT chance: **{round(100 * result['nation2_air_win_rate']**3)}%**\nNaval IT chance: **{round(100 * result['nation2_naval_win_rate']**3)}%**{vmend}", inline=True)
            embed2.add_field(name=f"{x['nation_name']} ({x['id']})", value=f"{vmstart}[War timeline](https://politicsandwar.com/nation/war/timeline/war={war['id']}) | {alliance}\n\n{war_emoji_1} **[{nation['nation_name']}](https://politicsandwar.com/nation/id={nation['id']})**{result['nation1_append']}\nGround: **${result['nation1_ground_net']/3:,.0f}**\nAir v air: **${result['nation1_airvair_net']/4:,.0f}**\nNaval: **${result['nation1_naval_net']/4:,.0f}**\nMissile: **${result['nation1_missile_net']/8:,.0f}**\nNuke: **${result['nation1_nuke_net']/12:,.0f}** **\n\n{war_emoji_2} [{x['nation_name']}](https://politicsandwar.com/nation/id={x['id']})**{result['nation2_append']}\nGround: **${result['nation2_ground_net']/3:,.0f}**\nAir v air: **${result['nation2_airvair_net']/4:,.0f}**\nNaval: **${result['nation2_naval_net']/4:,.0f}**\nMissile: **${result['nation2_missile_net']/8:,.0f}**\nNuke: **${result['nation2_nuke_net']/12:,.0f}**{vmend}", inline=True)

        class status_view(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)

            @discord.ui.button(label="General", style=discord.ButtonStyle.primary, custom_id="status_general", disabled=True)
            async def general_callback(self, b: discord.Button, i: discord.Interaction):
                this_button = [x for x in self.children if x.custom_id == "status_general"][0]
                other_buttons = [x for x in self.children if x.custom_id != "status_general"]
                for button in other_buttons:
                    button.disabled = False
                this_button.disabled = True
                await i.response.edit_message(content="", embed=embed, view=view)
            
            @discord.ui.button(label="Military", style=discord.ButtonStyle.primary, custom_id="status_military")
            async def military_callback(self, b: discord.Button, i: discord.Interaction):
                this_button = [x for x in self.children if x.custom_id == "status_military"][0]
                other_buttons = [x for x in self.children if x.custom_id != "status_military"]
                for button in other_buttons:
                    button.disabled = False
                this_button.disabled = True
                await i.response.edit_message(content="", embed=embed1, view=view)
            
            @discord.ui.button(label="Damage", style=discord.ButtonStyle.primary, custom_id="status_damage")
            async def damage_callback(self, b: discord.Button, i: discord.Interaction):
                this_button = [x for x in self.children if x.custom_id == "status_damage"][0]
                other_buttons = [x for x in self.children if x.custom_id != "status_damage"]
                for button in other_buttons:
                    button.disabled = False
                this_button.disabled = True
                await i.response.edit_message(content="", embed=embed2, view=view)
        
        view = status_view()
        print(embed.__sizeof__())
        print(embed1.__sizeof__())
        print(embed2.__sizeof__())
        await ctx.respond(content="", embed=embed, view=view)
    
    @slash_command(
        name="nuketargets",
        description='Find nations with juicy infra'
    )
    @commands.guild_only()
    async def nuketargets(
        self,
        ctx: discord.ApplicationContext,
        sort: Option(str, "The metric to sort the targets by", choices=["Nuke damage", "Missile damage"]) = "Nuke damage",
        include_beige: Option(bool, "Include beige nations", default=False) = False,
        include_slotted: Option(bool, "Include slotted nations", default=False) = False
    ):
        try:
            await ctx.respond("Let me think for a second...")
            
            user = await utils.find_nation_plus(self, ctx.author.id)
            if not user:
                await ctx.edit(content="Make sure that you are verified with `/verify`!")
                return
            
            config = await async_mongo.guild_configs.find_one({"guild_id": ctx.guild.id})

            fail = False
            if not config:
                fail = True
            else:
                try:
                    alliance_ids = config['targets_alliance_ids']
                    if len(alliance_ids) == 0:
                        fail = True
                except:
                    fail = True
            if fail:
                view = utils.yes_or_no_view(ctx=ctx)
                embed = discord.Embed(title="Targets not configured", description="This command has not been configured for this server. To configure targeted alliances, someone with the `manage_server` permission must use `/config`.\n\nDo you want to continue with all alliances being targeted?", color=0xff5100)
                await ctx.edit(content="", embed=embed, view=view)
                timed_out = await view.wait()
                if timed_out:
                    return
                if view.result == True:
                    await ctx.edit(content="Let me think for a second...", view=None, embed=None)
                    res = await utils.call(f"{{nations(first:1 id:{user['id']}){{data{utils.get_query(queries.NUKETARGETS)}}}}}")
                    user_nation = res['data']['nations']['data'][0]
                    async with aiofiles.open(pathlib.Path.cwd() / 'data' / 'nations.json', 'r') as json_file:
                        file_content = json.loads(await json_file.read())
                    all_nations = file_content['nations']
                elif view.result == False:
                    await ctx.edit(content="Parsing of command was cancelled <:kekw:984765354452602880>", embed=None, view=None)
                    return
                else:
                    return
            
            if not fail:
                res = await utils.call(f"{{nations(first:1 id:{user['id']}){{data{utils.get_query(queries.NUKETARGETS)}}}}}")
                user_nation = res['data']['nations']['data'][0]
                minscore = round(user_nation['score'] * 0.75)
                maxscore = round(user_nation['score'] * 2.5)
                all_nations = await utils.paginate_call(f"{{nations(first:150 page:page_number vmode:false max_score:{maxscore} min_score:{minscore} alliance_id:[{' '.join(alliance_ids)}]) {{paginatorInfo{{hasMorePages}} data{utils.get_query(queries.NUKETARGETS)}}}}}", "nations")

            minscore = round(user_nation['score'] * 0.75)
            maxscore = round(user_nation['score'] * 2.5)
            nation_list = []
            for nation in all_nations:
                try:
                    if nation['score'] < minscore or nation['score'] > maxscore:
                        continue
                    if not include_beige:
                        if nation['vacation_mode_turns'] > 0 or nation['color'] == "beige":
                            continue
                    if not include_slotted:
                        skip = False
                        for war in user_nation['wars']:
                            if (war['attid'] == nation['id'] or war['defid'] == nation['id']) and war['turnsleft'] > -12:
                                skip = True
                                break
                        if skip:
                            continue
                        def_wars = 0
                        for war in nation['wars']:
                            if war['turnsleft'] > 0 and war['defid'] == nation['id']:
                                def_wars += 1
                        if def_wars == 3:
                            continue
                    nation['max_infra'] = sorted(nation['cities'], key=lambda x: x['infrastructure'], reverse=True)[0]['infrastructure']
                    avg_infra = 0
                    for city in nation['cities']:
                        avg_infra += city['infrastructure']
                    results = await self.battle_calc(nation1=user_nation, nation2=nation)
                    # should parallelize this https://stackoverflow.com/a/56162461/14466960
                    nation['nuke_cost'] = results['nation1_nuke_nation2_total']
                    nation['missile_cost'] = results['nation1_missile_nation2_total']
                    nation["avg_infra"] = avg_infra / len(nation['cities'])
                    nation_list.append(nation)
                except IndexError:
                    # IndexError if for some reason nation['cities'] is empty
                    pass

            if len(nation_list) == 0:
                await ctx.edit(content="No eligible targets found!")
                return
            
            if sort == "Nuke damage":
                sort_key = "nuke_cost"
            elif sort == "Missile damage":
                sort_key = "missile_cost"
            nation_list = sorted(nation_list, key=lambda x: x[sort_key], reverse=True)

            embeds = []
            for n in range(0, len(nation_list), 8):
                embed = discord.Embed(title="Nuke Targets", description="The damage numbers are calculated for ordinary wars - for attrition wars the damage is doubled. War policies and projects are accounted for when calculating damage. Use /damage for more detailed information about the damage dealt.", color=0xff5100)
                for i in range(n, min(n+10, len(nation_list))):
                    if i == n:
                        pass
                    elif i % 2 == 0:
                        embed.add_field(name="\u200b", value="\u200b", inline=False)
                    else:
                        embed.add_field(name="\u200b", value="\u200b", inline=True)
                    if nation_list[i]['alliance']:
                        alliance = f"[{nation_list[i]['alliance']['name']}](https://politicsandwar.com/alliance/id={nation_list[i]['alliance']['id']}) ({nation_list[i]['alliance_position'].capitalize()})"
                    else:
                        alliance = "No alliance"
                    embed.add_field(name=f"{nation_list[i]['nation_name']}", value=f"[Nation](https://politicsandwar.com/nation/id={nation_list[i]['id']}) | {alliance}\nDamage/nuke: `${nation_list[i]['nuke_cost']:,.0f}`\nDamage/missile: `${nation_list[i]['missile_cost']:,.0f}`\nMax infra: `{nation_list[i]['max_infra']:.0f}`\nAvg. infra: `{nation_list[i]['avg_infra']:.0f}`\nVital Defense: {'✅' if nation_list[i]['vds'] else '<:redcross:862669500977905694>'}\nIron Dome: {'✅' if nation_list[i]['irond'] else '<:redcross:862669500977905694>'}")
                embed.set_footer(text=f"Page {n/8+1:.0f}/{math.ceil(len(nation_list)/8)}")
                embeds.append(embed)
            
            if len(embeds) > 1:
                view = utils.switch(ctx=ctx, embeds=embeds, max_page=len(embeds))
            else:
                view = None

            await ctx.edit(embed=embeds[0], content="", view=view)

        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
    
    @slash_command(
        name="targets",
        description="Find alliance war targets"
    )
    @commands.guild_only()
    async def targets(
        self,
        ctx: discord.ApplicationContext
    ):
        try:
            await ctx.defer()
            
            nation = await utils.find_nation_plus(self, ctx.author.id)
            if not nation:
                await ctx.respond("Make sure that you are verified with `/verify`!")
                return

            config = await async_mongo.guild_configs.find_one({"guild_id": ctx.guild.id})

            fail = False
            if not config:
                fail = True
            else:
                try:
                    alliance_ids = config['targets_alliance_ids']
                    if len(alliance_ids) == 0:
                        fail = True
                except:
                    fail = True
            if fail:
                await ctx.respond("This command has not been configured for this server! Someone with the `manage_server` permission must use `/config`!")
                return

            embed = discord.Embed(title="Targets", description=f"[Explore your targets on slotter](https://slotter.bsnk.dev/search?nation={nation['id']}&alliances={','.join(alliance_ids)}&countersMode=false&threatsMode=false&vm=false&grey=true&beige=false)", color=0xff5100)
            embed.set_footer(text="Slotter was made by Bann and is not affiliated with Autolycus")
            await ctx.respond(embed=embed)
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
    
    @slash_command(
        name="damage",
        description="Shows you how much damage each war attack would do",
    )
    async def damage(
        self,
        ctx: discord.ApplicationContext,
        nation1: Option(str, "Nation name, leader name, nation id, nation link or discord username. Defaults to your nation.") = None,
        nation2: Option(str, "Nation name, leader name, nation id, nation link or discord username. Defaults to your nation.") = None
    ):
        try:
            await ctx.defer()

            if nation1 == None and nation2:
                nation1 = nation2
                nation2 = None
                
            if nation1 == None:
                nation1 = ctx.author.id
            nation1_nation = await utils.find_nation_plus(self, nation1)
            if not nation1_nation:
                if nation2 == None:
                    await ctx.respond(content='I could not find that nation!')
                    return
                else:
                    await ctx.respond(content='I could not find nation 1!')
                    return 
            nation1_id = str(nation1_nation['id'])

            done = False
            if isinstance(ctx.channel, discord.Thread) and nation2 == None:
                try:
                    chan = ctx.channel.name
                    nation2_id = str(chan[chan.index("(")+1:-1])
                    done = True
                except:
                    pass

            if not done:
                if nation2 == None:
                    nation2 = ctx.author.id
                nation2_nation = await utils.find_nation_plus(self, nation2)
                if not nation2_nation:
                    if nation2 == None:
                        await ctx.respond(content='I was able to find the nation you linked, but I could not find *your* nation!')
                        return
                    else:
                        await ctx.respond(content='I could not find nation 2!')
                        return 
                nation2_id = str(nation2_nation['id'])
            
            results = await self.battle_calc(nation1_id, nation2_id)

            timestamp = round(datetime.utcnow().timestamp())

            await utils.write_web("damage", ctx.author.id, {"results": results}, timestamp)

            await ctx.respond(content=f"Go to http://132.145.71.195:5000/damage/{ctx.author.id}/{timestamp}")
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

        
    async def battle_calc(self, nation1_id=None, nation2_id=None, nation1=None, nation2=None):
        try:
            results = {}

            if nation1 and nation1_id or nation2 and nation2_id:
                raise Exception("You can't specify nation1 or nation2 multiple times!")
            if nation1:
                results['nation1'] = nation1
                nation1_id = nation1['id']
            if nation2:
                results['nation2'] = nation2
                nation2_id = nation2['id']
            if (nation1_id and not nation1) or (nation2_id and not nation2):
                ids = []
                if nation1_id:
                    ids.append(nation1_id)
                if nation2_id:
                    ids.append(nation2_id)
                nations = (await utils.call(f"{{nations(id:[{','.join(list(set(ids)))}]){{data{utils.get_query(queries.BATTLE_CALC)}}}}}"))['data']['nations']['data']
                nations = sorted(nations, key=lambda x: int(x['id']))
                for nation in nations:
                    if nation['id'] == nation1_id:
                        results['nation1'] = nation
                    if nation['id'] == nation2_id:
                        results['nation2'] = nation

            results['nation1_append'] = ""
            results['nation2_append'] = ""
            results['nation1_tanks'] = 1
            results['nation2_tanks'] = 1
            results['nation1_extra_cas'] = 1
            results['nation2_extra_cas'] = 1
            results['gc'] = None
            results['nation1_war_infra_mod'] = 0.5
            results['nation2_war_infra_mod'] = 0.5
            results['nation1_war_loot_mod'] = 0.5
            results['nation2_war_loot_mod'] = 0.5

            for war in results['nation1']['wars']:
                if war['attid'] == nation2_id and war['turnsleft'] > 0 and war['defid'] == nation1_id:
                    if war['groundcontrol'] == nation1_id:
                        results['gc'] = results['nation1']
                        results['nation1_append'] += "<:small_gc:924988666613489685>"
                    elif war['groundcontrol'] == nation2_id:
                        results['gc'] = results['nation2']
                        results['nation2_append'] += "<:small_gc:924988666613489685>"
                    if war['airsuperiority'] == nation1_id:
                        results['nation2_tanks'] = 0.5
                        results['nation1_append'] += "<:small_air:924988666810601552>"
                    elif war['airsuperiority'] == nation2_id:
                        results['nation1_tanks'] = 0.5
                        results['nation2_append'] += "<:small_air:924988666810601552>"
                    if war['navalblockade'] == nation1_id: #blockade is opposite than the others
                        results['nation2_append'] += "<:small_blockade:924988666814808114>"
                    elif war['navalblockade'] == nation2_id:
                        results['nation1_append'] += "<:small_blockade:924988666814808114>"
                    if war['att_fortify']:
                        results['nation2_append'] += "<:fortified:925465012955385918>"
                        results['nation1_extra_cas'] = 1.25
                    if war['def_fortify']:
                        results['nation1_append'] += "<:fortified:925465012955385918>"
                        results['nation2_extra_cas'] = 1.25
                    if war['attpeace']:
                        results['nation2_append'] += "<:peace:926855240655990836>"
                    elif war['defpeace']:
                        results['nation1_append'] += "<:peace:926855240655990836>"
                    if war['war_type'] == "RAID":
                        results['nation2_war_infra_mod'] = 0.25
                        results['nation1_war_infra_mod'] = 0.5
                        results['nation2_war_loot_mod'] = 1
                        results['nation1_war_loot_mod'] = 1
                    elif war['war_type'] == "ORDINARY":
                        results['nation2_war_infra_mod'] = 0.5
                        results['nation1_war_infra_mod'] = 0.5
                        results['nation2_war_loot_mod'] = 0.5
                        results['nation1_war_loot_mod'] = 0.5
                    elif war['war_type'] == "ATTRITION":
                        results['nation2_war_infra_mod'] = 1
                        results['nation1_war_infra_mod'] = 1
                        results['nation2_war_loot_mod'] = 0.25
                        results['nation1_war_loot_mod'] = 0.5
                elif war['defid'] == nation2_id and war['turnsleft'] > 0 and war['attid'] == nation1_id:
                    if war['groundcontrol'] == nation1_id:
                        results['gc'] = results['nation1']
                        results['nation1_append'] += "<:small_gc:924988666613489685>"
                    elif war['groundcontrol'] == nation2_id:
                        results['gc'] = results['nation2']
                        results['nation2_append'] += "<:small_gc:924988666613489685>"
                    if war['airsuperiority'] == nation1_id:
                        results['nation2_tanks'] = 0.5
                        results['nation1_append'] += "<:small_air:924988666810601552>"
                    elif war['airsuperiority'] == nation2_id:
                        results['nation1_tanks'] = 0.5
                        results['nation2_append'] += "<:small_air:924988666810601552>"
                    if war['navalblockade'] == nation1_id: #blockade is opposite than the others
                        results['nation2_append'] += "<:small_blockade:924988666814808114>"
                    elif war['navalblockade'] == nation2_id:
                        results['nation1_append'] += "<:small_blockade:924988666814808114>"
                    if war['att_fortify']:
                        results['nation1_append'] += "<:fortified:925465012955385918>"
                        results['nation2_extra_cas'] = 1.25
                    if war['def_fortify']:
                        results['nation2_append'] += "<:fortified:925465012955385918>"
                        results['nation1_extra_cas'] = 1.25
                    if war['attpeace']:
                        results['nation1_append'] += "<:peace:926855240655990836>"
                    elif war['defpeace']:
                        results['nation2_append'] += "<:peace:926855240655990836>"
                    if war['war_type'] == "RAID":
                        results['nation1_war_infra_mod'] = 0.25
                        results['nation2_war_infra_mod'] = 0.5
                        results['nation1_war_loot_mod'] = 1
                        results['nation2_war_loot_mod'] = 1
                    elif war['war_type'] == "ORDINARY":
                        results['nation1_war_infra_mod'] = 0.5
                        results['nation2_war_infra_mod'] = 0.5
                        results['nation1_war_loot_mod'] = 0.5
                        results['nation2_war_loot_mod'] = 0.5
                    elif war['war_type'] == "ATTRITION":
                        results['nation1_war_infra_mod'] = 1
                        results['nation2_war_infra_mod'] = 1
                        results['nation1_war_loot_mod'] = 0.25
                        results['nation2_war_loot_mod'] = 0.5
            
            for attacker, defender in [("nation1", "nation2"), ("nation2", "nation1")]:
                defender_tanks_value = (results[defender]['tanks'] * 40 * results[f'{defender}_tanks']) ** (3/4)
                defender_soldiers_value = (results[defender]['soldiers'] * 1.75 + results[defender]['population'] * 0.0025) ** (3/4)
                defender_army_value = (defender_soldiers_value + defender_tanks_value) ** (3/4)

                attacker_tanks_value = (results[attacker]['tanks'] * 40 * results[f'{attacker}_tanks']) ** (3/4)
                attacker_soldiers_value = (results[attacker]['soldiers'] * 1.75) ** (3/4)
                attacker_army_value = (attacker_soldiers_value + attacker_tanks_value) ** (3/4)

                results[f'{attacker}_ground_win_rate'] = self.winrate_calc(attacker_army_value, defender_army_value)
                results[f'{attacker}_ground_it'] = results[f'{attacker}_ground_win_rate']**3
                results[f'{attacker}_ground_mod'] = results[f'{attacker}_ground_win_rate']**2 * (1 - results[f'{attacker}_ground_win_rate']) * 3
                results[f'{attacker}_ground_pyr'] = results[f'{attacker}_ground_win_rate'] * (1 - results[f'{attacker}_ground_win_rate'])**2 * 3
                results[f'{attacker}_ground_fail'] = (1 - results[f'{attacker}_ground_win_rate'])**3

                attacker_aircraft_value = (results[attacker]['aircraft'] * 3) ** (3/4)
                defender_aircraft_value = (results[defender]['aircraft'] * 3) ** (3/4)
                results[f'{attacker}_air_win_rate'] = self.winrate_calc(attacker_aircraft_value, defender_aircraft_value)
                results[f'{attacker}_air_it'] = results[f'{attacker}_air_win_rate']**3
                results[f'{attacker}_air_mod'] = results[f'{attacker}_air_win_rate']**2 * (1 - results[f'{attacker}_air_win_rate']) * 3
                results[f'{attacker}_air_pyr'] = results[f'{attacker}_air_win_rate'] * (1 - results[f'{attacker}_air_win_rate'])**2 * 3
                results[f'{attacker}_air_fail'] = (1 - results[f'{attacker}_air_win_rate'])**3

                attacker_ships_value = (results[attacker]['ships'] * 4) ** (3/4)
                defender_ships_value = (results[defender]['ships'] * 4) ** (3/4)
                results[f'{attacker}_naval_win_rate'] = self.winrate_calc(attacker_ships_value, defender_ships_value)
                results[f'{attacker}_naval_it'] = results[f'{attacker}_naval_win_rate']**3
                results[f'{attacker}_naval_mod'] = results[f'{attacker}_naval_win_rate']**2 * (1 - results[f'{attacker}_naval_win_rate']) * 3
                results[f'{attacker}_naval_pyr'] = results[f'{attacker}_naval_win_rate'] * (1 - results[f'{attacker}_naval_win_rate'])**2 * 3
                results[f'{attacker}_naval_fail'] = (1 - results[f'{attacker}_naval_win_rate'])**3
                
                attacker_casualties_soldiers_value = utils.weird_division((attacker_soldiers_value**(4/3) + defender_soldiers_value**(4/3)) , (attacker_soldiers_value + defender_soldiers_value)) * attacker_soldiers_value
                defender_casualties_soldiers_value = utils.weird_division((attacker_soldiers_value**(4/3) + defender_soldiers_value**(4/3)) , (attacker_soldiers_value + defender_soldiers_value)) * defender_soldiers_value
                attacker_casualties_tanks_value = utils.weird_division((attacker_tanks_value**(4/3) + defender_tanks_value**(4/3)) , (attacker_tanks_value + defender_tanks_value)) * attacker_tanks_value
                defender_casualties_tanks_value = utils.weird_division((attacker_tanks_value**(4/3) + defender_tanks_value**(4/3)) , (attacker_tanks_value + defender_tanks_value)) * defender_tanks_value
                attacker_casualties_aircraft_value = utils.weird_division((attacker_aircraft_value**(4/3) + defender_aircraft_value**(4/3)) , (attacker_aircraft_value + defender_aircraft_value)) * attacker_aircraft_value
                defender_casualties_aircraft_value = utils.weird_division((attacker_aircraft_value**(4/3) + defender_aircraft_value**(4/3)) , (attacker_aircraft_value + defender_aircraft_value)) * defender_aircraft_value
                attacker_casualties_ships_value = utils.weird_division((attacker_ships_value**(4/3) + defender_ships_value**(4/3)) , (attacker_ships_value + defender_ships_value)) * attacker_ships_value
                defender_casualties_ships_value = utils.weird_division((attacker_ships_value**(4/3) + defender_ships_value**(4/3)) , (attacker_ships_value + defender_ships_value)) * defender_ships_value

                if results['gc'] == results[attacker]:
                    results[f'{attacker}_ground_{defender}_avg_aircraft'] = avg_air = round(min(results[attacker]['tanks'] * 0.005 * results[f'{attacker}_ground_win_rate'] ** 3, results[defender]['aircraft']))
                    results[defender]['aircas'] = f"Def. Plane: {avg_air} ± {round(results[attacker]['tanks'] * 0.005 * (1 - results[f'{attacker}_ground_win_rate'] ** 3))}"
                else:
                    results[defender]['aircas'] = ""
                    results[f'{attacker}_ground_{defender}_avg_aircraft'] = 0
                
                for type, cas_rate in [("avg", 0.7), ("diff", 0.3)]:
                    # values should be multiplied by 0.7 again? no... https://politicsandwar.fandom.com/wiki/Ground_Battles?so=search -> make a function for the average tank/soldier value roll giving success
                    results[f'{attacker}_ground_{attacker}_{type}_soldiers'] = min(round(((defender_casualties_soldiers_value * 0.0084) + (defender_casualties_tanks_value * 0.0092)) * cas_rate * 3), results[attacker]['soldiers'])
                    results[f'{attacker}_ground_{attacker}_{type}_tanks'] = min(round((((defender_casualties_soldiers_value * 0.0004060606) + (defender_casualties_tanks_value * 0.00066666666)) * results[f'{attacker}_ground_win_rate'] + ((defender_soldiers_value * 0.00043225806) + (defender_tanks_value * 0.00070967741)) * (1 - results[f'{attacker}_ground_win_rate'])) * cas_rate * 3), results[attacker]['tanks'])
                    results[f'{attacker}_ground_{defender}_{type}_soldiers'] = min(round(((attacker_casualties_soldiers_value * 0.0084) + (attacker_casualties_tanks_value * 0.0092)) * cas_rate * 3), results[defender]['soldiers'])
                    results[f'{attacker}_ground_{defender}_{type}_tanks'] = min(round((((attacker_casualties_soldiers_value * 0.00043225806) + (attacker_casualties_tanks_value * 0.00070967741)) * results[f'{attacker}_ground_win_rate'] + ((attacker_soldiers_value * 0.0004060606) + (attacker_tanks_value * 0.00066666666)) * (1 - results[f'{attacker}_ground_win_rate'])) * cas_rate * 3), results[defender]['tanks'])

                results[f'{attacker}_airvair_{attacker}_avg'] = min(round(defender_casualties_aircraft_value * 0.7 * 0.01 * 3 * results[f'{attacker}_extra_cas']), results[attacker]['aircraft'])
                results[f'{attacker}_airvair_{attacker}_diff'] = min(round(defender_casualties_aircraft_value * 0.3 * 0.01 * 3 * results[f'{attacker}_extra_cas']), results[attacker]['aircraft'])
                results[f'{attacker}_airvother_{attacker}_avg'] = min(round(defender_casualties_aircraft_value * 0.7 * 0.015385 * 3 * results[f'{attacker}_extra_cas']), results[attacker]['aircraft'])
                results[f'{attacker}_airvother_{attacker}_diff'] = min(round(defender_casualties_aircraft_value * 0.3 * 0.015385 * 3 * results[f'{attacker}_extra_cas']), results[attacker]['aircraft'])

                results[f'{attacker}_airvair_{defender}_avg'] = min(round(attacker_casualties_aircraft_value * 0.7 * 0.018337 * 3), results[defender]['aircraft'])
                results[f'{attacker}_airvair_{defender}_diff'] = min(round(attacker_casualties_aircraft_value * 0.3 * 0.018337 * 3), results[defender]['aircraft'])
                results[f'{attacker}_airvother_{defender}_avg'] = min(round(attacker_casualties_aircraft_value * 0.7 * 0.009091 * 3), results[defender]['aircraft'])
                results[f'{attacker}_airvother_{defender}_diff'] = min(round(attacker_casualties_aircraft_value * 0.3 * 0.009091 * 3), results[defender]['aircraft'])

                results[f'{attacker}_naval_{defender}_avg'] = min(round(attacker_casualties_ships_value * 0.7 * 0.01375 * 3 * results[f'{attacker}_extra_cas']), results[defender]['aircraft'])
                results[f'{attacker}_naval_{defender}_diff'] = min(round(attacker_casualties_ships_value * 0.3 * 0.01375 * 3 * results[f'{attacker}_extra_cas']), results[defender]['aircraft'])
                results[f'{attacker}_naval_{attacker}_avg'] = min(round(defender_casualties_ships_value * 0.7 * 0.01375 * 3), results[attacker]['aircraft'])
                results[f'{attacker}_naval_{attacker}_diff'] = min(round(defender_casualties_ships_value * 0.3 * 0.01375 * 3), results[attacker]['aircraft'])

            def def_rss_consumption(winrate: Union[int, float]) -> float:
                rate = -0.4624 * winrate**2 + 1.06256 * winrate + 0.3999            
                if rate < 0.4:
                    rate = 0.4
                return rate
                ## See note

            results["nation1"]['city'] = sorted(results['nation1']['cities'], key=lambda k: k['infrastructure'], reverse=True)[0]
            results["nation2"]['city'] = sorted(results['nation2']['cities'], key=lambda k: k['infrastructure'], reverse=True)[0]

            for nation in ["nation1", "nation2"]:
                results[f'{nation}_policy_infra_dealt'] = 1
                results[f'{nation}_policy_loot_stolen'] = 1
                results[f'{nation}_policy_infra_lost'] = 1
                results[f'{nation}_policy_loot_lost'] = 1
                results[f'{nation}_policy_improvements_lost'] = 1
                results[f'{nation}_policy_loot_stolen'] = 1
                results[f'{nation}_policy_improvements_destroyed'] = 1
                results[f'{nation}_vds_mod'] = 1
                results[f'{nation}_irond_mod'] = 1
                results[f'{nation}_fallout_shelter_mod'] = 1
                results[f'{nation}_military_salvage_mod'] = 0
                results[f'{nation}_pirate_econ_loot'] = 1
                results[f'{nation}_advanced_pirate_econ_loot'] = 1

                if results[f'{nation}']['warpolicy'] == "Attrition":
                    results[f'{nation}_policy_infra_dealt'] = 1.1
                    results[f'{nation}_policy_loot_stolen'] = 0.8
                elif results[f'{nation}']['warpolicy'] == "Turtle":
                    results[f'{nation}_policy_infra_lost'] = 0.9
                    results[f'{nation}_policy_loot_lost'] = 1.2
                elif results[f'{nation}']['warpolicy'] == "Moneybags":
                    results[f'{nation}_policy_infra_lost'] = 1.05
                    results[f'{nation}_policy_loot_lost'] = 0.6
                elif results[f'{nation}']['warpolicy'] == "Pirate":
                    results[f'{nation}_policy_improvements_lost'] = 2.0
                    results[f'{nation}_policy_loot_stolen'] = 1.4
                elif results[f'{nation}']['warpolicy'] == "Tactician":
                    results[f'{nation}_policy_improvements_destroyed'] = 2.0
                elif results[f'{nation}']['warpolicy'] == "Guardian":
                    results[f'{nation}_policy_improvements_lost'] = 0.5
                    results[f'{nation}_policy_loot_lost'] = 1.2
                elif results[f'{nation}']['warpolicy'] == "Covert":
                    results[f'{nation}_policy_infra_lost'] = 1.05
                elif results[f'{nation}']['warpolicy'] == "Arcane":
                    results[f'{nation}_policy_infra_lost'] = 1.05
                if results[f'{nation}']['vds']:
                    results[f'{nation}_vds_mod'] = 0.75
                if results[f'{nation}']['irond']:
                    results[f'{nation}_irond_mod'] = 0.7
                if results[f'{nation}']['fallout_shelter']:
                    results[f'{nation}_fallout_shelter_mod'] = 0.9
                if results[f'{nation}']['military_salvage']:
                    results[f'{nation}_military_salvage_mod'] = 1
                if results[f'{nation}']['pirate_economy']:
                    results[f'{nation}_pirate_econ_loot'] = 1.05
                if results[f'{nation}']['advanced_pirate_economy']:
                    results[f'{nation}_advanced_pirate_econ_loot'] = 1.05
            
            def airstrike_casualties(winrate: Union[int, float]) -> float:
                rate = -0.4624 * winrate**2 + 1.06256 * winrate + 0.3999            
                if rate < 0.4:
                    rate = 0.4
                return rate
            
            def salvage(winrate, resources) -> int:
                return resources * (results[f'{attacker}_military_salvage_mod'] * (winrate ** 3) * 0.05)

            for attacker, defender in [("nation1", "nation2"), ("nation2", "nation1")]:
                results[f'{attacker}_ground_{defender}_lost_infra_avg'] = max(min(((results[attacker]['soldiers'] - results[defender]['soldiers'] * 0.5) * 0.000606061 + (results[attacker]['tanks'] - (results[defender]['tanks'] * 0.5)) * 0.01) * 0.95 * results[f'{attacker}_ground_win_rate'], results[defender]['city']['infrastructure'] * 0.2 + 25), 0) * results[f'{attacker}_war_infra_mod'] * results[f'{attacker}_policy_infra_dealt'] * results[f'{defender}_policy_infra_lost']
                results[f'{attacker}_ground_{defender}_lost_infra_diff'] = results[f'{attacker}_ground_{defender}_lost_infra_avg'] / 0.95 * 0.15
                results[f'{attacker}_ground_loot_avg'] = (results[attacker]['soldiers'] * 1.1 + results[attacker]['tanks'] * 25.15) * (results[f'{attacker}_ground_win_rate'] ** 3) * 3 * 0.95 * results[f'{attacker}_war_loot_mod'] * results[f'{attacker}_policy_loot_stolen'] * results[f'{defender}_policy_loot_lost'] * results[f'{attacker}_pirate_econ_loot'] * results[f'{attacker}_advanced_pirate_econ_loot']
                results[f'{attacker}_ground_loot_diff'] = results[f'{attacker}_ground_loot_avg'] / 0.95 * 0.1

                results[f'{attacker}_air_{defender}_lost_infra_avg'] = max(min((results[attacker]['aircraft'] - results[defender]['aircraft'] * 0.5) * 0.35353535 * 0.95 * results[f'{attacker}_air_win_rate'], results[defender]['city']['infrastructure'] * 0.5 + 100), 0) * results[f'{attacker}_war_infra_mod'] * results[f'{attacker}_policy_infra_dealt'] * results[f'{defender}_policy_infra_lost']
                results[f'{attacker}_air_{defender}_lost_infra_diff'] = results[f'{attacker}_air_{defender}_lost_infra_avg'] / 0.95 * 0.15
                results[f'{attacker}_air_{defender}_soldiers_destroyed_avg'] = round(max(min(results[defender]['soldiers'], results[defender]['soldiers'] * 0.75 + 1000, (results[attacker]['aircraft'] - results[defender]['aircraft'] * 0.5) * 35 * 0.95), 0)) * airstrike_casualties(results[f'{attacker}_air_win_rate'])
                results[f'{attacker}_air_{defender}_soldiers_destroyed_diff'] = results[f'{attacker}_air_{defender}_soldiers_destroyed_avg'] / 0.95 * 0.1
                results[f'{attacker}_air_{defender}_tanks_destroyed_avg'] = round(max(min(results[defender]['tanks'], results[defender]['tanks'] * 0.75 + 10, (results[attacker]['aircraft'] - results[defender]['aircraft'] * 0.5) * 1.25 * 0.95), 0)) * airstrike_casualties(results[f'{attacker}_air_win_rate'])
                results[f'{attacker}_air_{defender}_tanks_destroyed_diff'] = results[f'{attacker}_air_{defender}_tanks_destroyed_avg'] / 0.95 * 0.1
                results[f'{attacker}_air_{defender}_ships_destroyed_avg'] = round(max(min(results[defender]['ships'], results[defender]['ships'] * 0.75 + 4, (results[attacker]['aircraft'] - results[defender]['aircraft'] * 0.5) * 0.0285 * 0.95), 0)) * airstrike_casualties(results[f'{attacker}_air_win_rate'])
                results[f'{attacker}_air_{defender}_ships_destroyed_diff'] = results[f'{attacker}_air_{defender}_ships_destroyed_avg'] / 0.95 * 0.1

                results[f'{attacker}_naval_{defender}_lost_infra_avg'] = max(min((results[attacker]['ships'] - results[attacker]['ships'] * 0.5) * 2.625 * 0.95 * results[f'{attacker}_naval_win_rate'], results[defender]['city']['infrastructure'] * 0.5 + 25), 0) * results[f'{attacker}_war_infra_mod'] * results[f'{attacker}_policy_infra_dealt'] * results[f'{defender}_policy_infra_lost']
                results[f'{attacker}_naval_{defender}_lost_infra_diff'] = results[f'{attacker}_naval_{defender}_lost_infra_avg'] / 0.95 * 0.15

                results[f'{attacker}_nuke_{defender}_lost_infra_avg'] = max(min((1700 + max(2000, results[defender]['city']['infrastructure'] * 100 / results[defender]['city']['land'] * 13.5)) / 2, results[defender]['city']['infrastructure'] * 0.8 + 150), 0) * results[f'{attacker}_war_infra_mod'] * results[f'{attacker}_policy_infra_dealt'] * results[f'{defender}_policy_infra_lost'] * results[f'{defender}_fallout_shelter_mod']
                results[f'{attacker}_missile_{defender}_lost_infra_avg'] = max(min((300 + max(350, results[defender]['city']['infrastructure'] * 100 / results[defender]['city']['land'] * 3)) / 2, results[defender]['city']['infrastructure'] * 0.3 + 100), 0) * results[f'{attacker}_war_infra_mod'] * results[f'{attacker}_policy_infra_dealt'] * results[f'{defender}_policy_infra_lost']
                
                for infra in [
                        f"{attacker}_ground_{defender}_lost_infra",
                        f"{attacker}_air_{defender}_lost_infra",
                        f"{attacker}_naval_{defender}_lost_infra",
                        f"{attacker}_nuke_{defender}_lost_infra",
                        f"{attacker}_missile_{defender}_lost_infra",
                    ]:
                    if "missile" in infra:
                        modifier = results[f'{defender}_irond_mod']
                    elif "nuke" in infra:
                        modifier = results[f'{defender}_vds_mod']
                    else:
                        modifier = 1
                    results[f'{infra}_avg_value'] = utils.infra_cost(results[defender]['city']['infrastructure'] - results[f'{infra}_avg'], results[defender]['city']['infrastructure']) * modifier
                
                for attack in ['airvair', 'airvsoldiers', 'airvtanks', 'airvships']:
                    results[f"{attacker}_{attack}_{defender}_lost_infra_avg_value"] = results[f"{attacker}_air_{defender}_lost_infra_avg_value"] * 1/3
                results[f"{attacker}_airvinfra_{defender}_lost_infra_avg_value"] = results[f"{attacker}_air_{defender}_lost_infra_avg_value"]


                results[f'{attacker}_ground_{attacker}_mun'] = results[attacker]['soldiers'] * 0.0002 + results[attacker]['tanks'] * 0.01
                results[f'{attacker}_ground_{attacker}_gas'] = results[attacker]['tanks'] * 0.01
                results[f'{attacker}_ground_{attacker}_alum'] = 0 #-salvage(results[f'{attacker}_ground_win_rate'], results[f'{attacker}_ground_{defender}_alum']) 
                results[f'{attacker}_ground_{attacker}_steel'] = results[f'{attacker}_ground_{attacker}_avg_tanks'] * 0.5 - salvage(results[f'{attacker}_ground_win_rate'], results[f'{attacker}_ground_{attacker}_avg_tanks'] * 0.5) - salvage(results[f'{attacker}_ground_win_rate'], results[f'{attacker}_ground_{defender}_avg_tanks'] * 0.5)
                results[f'{attacker}_ground_{attacker}_money'] = -results[f'{attacker}_ground_loot_avg'] + results[f'{attacker}_ground_{attacker}_avg_tanks'] * 50 + results[f'{attacker}_ground_{attacker}_avg_soldiers'] * 5
                results[f'{attacker}_ground_{attacker}_total'] = results[f'{attacker}_ground_{attacker}_alum'] * 2971 + results[f'{attacker}_ground_{attacker}_steel'] * 3990 + results[f'{attacker}_ground_{attacker}_gas'] * 3340 + results[f'{attacker}_ground_{attacker}_mun'] * 1960 + results[f'{attacker}_ground_{attacker}_money'] 

                base_mun = (results[defender]['soldiers'] * 0.0002 + results[defender]['population'] / 2000000 + results[defender]['tanks'] * 0.01) * def_rss_consumption(results[f'{attacker}_ground_win_rate'])
                results[f'{attacker}_ground_{defender}_mun'] = (base_mun * (1 - results[f'{attacker}_ground_fail']) + min(base_mun, results[f'{attacker}_ground_{attacker}_mun']) * results[f'{attacker}_ground_fail'])
                base_gas = results[defender]['tanks'] * 0.01 * def_rss_consumption(results[f'{attacker}_ground_win_rate'])
                results[f'{attacker}_ground_{defender}_gas'] = (base_gas * (1 - results[f'{attacker}_ground_fail']) + min(base_gas, results[f'{attacker}_ground_{attacker}_gas']) * results[f'{attacker}_ground_fail'])
                results[f'{attacker}_ground_{defender}_alum'] = results[f'{attacker}_ground_{defender}_avg_aircraft'] * 5
                results[f'{attacker}_ground_{defender}_steel'] = results[f'{attacker}_ground_{defender}_avg_tanks'] * 0.5
                results[f'{attacker}_ground_{defender}_money'] = results[f'{attacker}_ground_loot_avg'] + results[f'{attacker}_ground_{defender}_avg_aircraft'] * 4000 + results[f'{attacker}_ground_{defender}_avg_tanks'] * 50 + results[f'{attacker}_ground_{defender}_avg_soldiers'] * 5 + results[f'{attacker}_ground_{defender}_lost_infra_avg_value']
                results[f'{attacker}_ground_{defender}_total'] = results[f'{attacker}_ground_{defender}_alum'] * 2971 + results[f'{attacker}_ground_{defender}_steel'] * 3990 + results[f'{attacker}_ground_{defender}_gas'] * 3340 + results[f'{attacker}_ground_{defender}_mun'] * 1960 + results[f'{attacker}_ground_{defender}_money'] 
                results[f'{attacker}_ground_net'] = results[f'{attacker}_ground_{defender}_total'] - results[f'{attacker}_ground_{attacker}_total']
                

                for attack in ['air', 'airvair', 'airvinfra', 'airvsoldiers', 'airvtanks', 'airvships']:
                    results[f'{attacker}_{attack}_{attacker}_gas'] = results[f'{attacker}_{attack}_{attacker}_mun'] = results[attacker]['aircraft'] / 4
                    base_gas = results[defender]['aircraft'] / 4 * def_rss_consumption(results[f'{attacker}_air_win_rate'])
                    results[f'{attacker}_{attack}_{defender}_gas'] = results[f'{attacker}_{attack}_{defender}_mun'] = (base_gas * (1 - results[f'{attacker}_air_fail']) + min(base_gas, results[f'{attacker}_air_{attacker}_gas']) * results[f'{attacker}_air_fail'])

                results[f'{attacker}_airvair_{attacker}_alum'] = results[f'{attacker}_airvair_{attacker}_avg'] * 5 - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvair_{attacker}_avg'] * 5) - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvair_{defender}_avg'] * 5)
                results[f'{attacker}_airvair_{attacker}_steel'] = 0
                results[f'{attacker}_airvair_{attacker}_money'] = results[f'{attacker}_airvair_{attacker}_avg'] * 4000
                results[f'{attacker}_airvair_{attacker}_total'] = results[f'{attacker}_airvair_{attacker}_alum'] * 2971 + results[f'{attacker}_airvair_{attacker}_steel'] * 3990 + results[f'{attacker}_air_{attacker}_gas'] * 3340 + results[f'{attacker}_air_{attacker}_mun'] * 1960 + results[f'{attacker}_airvair_{attacker}_money'] 
               
                results[f'{attacker}_airvair_{defender}_alum'] = results[f'{attacker}_airvair_{defender}_avg'] * 5
                results[f'{attacker}_airvair_{defender}_steel'] = 0
                results[f'{attacker}_airvair_{defender}_money'] = results[f'{attacker}_airvair_{defender}_avg'] * 4000 + results[f'{attacker}_air_{defender}_lost_infra_avg_value'] * 1/3
                results[f'{attacker}_airvair_{defender}_total'] = results[f'{attacker}_airvair_{defender}_alum'] * 2971 + results[f'{attacker}_airvair_{defender}_steel'] * 3990 + results[f'{attacker}_air_{defender}_gas'] * 3340 + results[f'{attacker}_air_{defender}_mun'] * 1960 + results[f'{attacker}_airvair_{defender}_money'] 
                results[f'{attacker}_airvair_net'] = results[f'{attacker}_airvair_{defender}_total'] - results[f'{attacker}_airvair_{attacker}_total']


                results[f'{attacker}_airvinfra_{attacker}_alum'] = results[f'{attacker}_airvother_{attacker}_avg'] * 5 - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvother_{attacker}_avg'] * 5) - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvother_{defender}_avg'] * 5)
                results[f'{attacker}_airvinfra_{attacker}_steel'] = 0
                results[f'{attacker}_airvinfra_{attacker}_money'] = results[f'{attacker}_airvother_{attacker}_avg'] * 4000
                results[f'{attacker}_airvinfra_{attacker}_total'] = results[f'{attacker}_airvinfra_{attacker}_alum'] * 2971 + results[f'{attacker}_airvinfra_{attacker}_steel'] * 3990 + results[f'{attacker}_air_{attacker}_gas'] * 3340 + results[f'{attacker}_air_{attacker}_mun'] * 1960 + results[f'{attacker}_airvinfra_{attacker}_money'] 

                results[f'{attacker}_airvinfra_{defender}_alum'] = results[f'{attacker}_airvother_{defender}_avg'] * 5
                results[f'{attacker}_airvinfra_{defender}_steel'] = 0
                results[f'{attacker}_airvinfra_{defender}_money'] = results[f'{attacker}_airvother_{defender}_avg'] * 4000 + results[f'{attacker}_air_{defender}_lost_infra_avg_value']
                results[f'{attacker}_airvinfra_{defender}_total'] = results[f'{attacker}_airvinfra_{defender}_alum'] * 2971 + results[f'{attacker}_airvinfra_{defender}_steel'] * 3990 + results[f'{attacker}_air_{defender}_gas'] * 3340 + results[f'{attacker}_air_{defender}_mun'] * 1960 + results[f'{attacker}_airvinfra_{defender}_money'] 
                results[f'{attacker}_airvinfra_net'] = results[f'{attacker}_airvinfra_{defender}_total'] - results[f'{attacker}_airvinfra_{attacker}_total']


                results[f'{attacker}_airvsoldiers_{attacker}_alum'] = results[f'{attacker}_airvother_{attacker}_avg'] * 5 - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvother_{attacker}_avg'] * 5) - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvother_{defender}_avg'] * 5)
                results[f'{attacker}_airvsoldiers_{attacker}_steel'] = 0
                results[f'{attacker}_airvsoldiers_{attacker}_money'] = results[f'{attacker}_airvother_{attacker}_avg'] * 4000
                results[f'{attacker}_airvsoldiers_{attacker}_total'] = results[f'{attacker}_airvsoldiers_{attacker}_alum'] * 2971 + results[f'{attacker}_airvsoldiers_{attacker}_steel'] * 3990 + results[f'{attacker}_air_{attacker}_gas'] * 3340 + results[f'{attacker}_air_{attacker}_mun'] * 1960 + results[f'{attacker}_airvsoldiers_{attacker}_money'] 
                
                results[f'{attacker}_airvsoldiers_{defender}_alum'] = results[f'{attacker}_airvother_{defender}_avg'] * 5
                results[f'{attacker}_airvsoldiers_{defender}_steel'] = 0
                results[f'{attacker}_airvsoldiers_{defender}_money'] = results[f'{attacker}_airvother_{defender}_avg'] * 4000 + results[f'{attacker}_air_{defender}_lost_infra_avg_value'] * 1/3 + results[f'{attacker}_air_{defender}_soldiers_destroyed_avg'] * 5
                results[f'{attacker}_airvsoldiers_{defender}_total'] = results[f'{attacker}_airvsoldiers_{defender}_alum'] * 2971 + results[f'{attacker}_airvsoldiers_{defender}_steel'] * 3990 + results[f'{attacker}_air_{defender}_gas'] * 3340 + results[f'{attacker}_air_{defender}_mun'] * 1960 + results[f'{attacker}_airvsoldiers_{defender}_money'] 
                results[f'{attacker}_airvsoldiers_net'] = results[f'{attacker}_airvair_{defender}_total'] - results[f'{attacker}_airvsoldiers_{attacker}_total']
                

                results[f'{attacker}_airvtanks_{attacker}_alum'] = results[f'{attacker}_airvother_{attacker}_avg'] * 5 - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvother_{attacker}_avg'] * 5) - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvother_{defender}_avg'] * 5)
                results[f'{attacker}_airvtanks_{attacker}_steel'] = 0
                results[f'{attacker}_airvtanks_{attacker}_money'] = results[f'{attacker}_airvother_{attacker}_avg'] * 4000
                results[f'{attacker}_airvtanks_{attacker}_total'] = results[f'{attacker}_airvtanks_{attacker}_alum'] * 2971 + results[f'{attacker}_airvtanks_{attacker}_steel'] * 3990 + results[f'{attacker}_air_{attacker}_gas'] * 3340 + results[f'{attacker}_air_{attacker}_mun'] * 1960 + results[f'{attacker}_airvtanks_{attacker}_money'] 

                results[f'{attacker}_airvtanks_{defender}_alum'] = results[f'{attacker}_airvother_{defender}_avg'] * 5
                results[f'{attacker}_airvtanks_{defender}_steel'] = results[f'{attacker}_air_{defender}_tanks_destroyed_avg'] * 0.5
                results[f'{attacker}_airvtanks_{defender}_money'] = results[f'{attacker}_airvother_{defender}_avg'] * 4000 + results[f'{attacker}_air_{defender}_lost_infra_avg_value'] * 1/3 + results[f'{attacker}_air_{defender}_tanks_destroyed_avg'] * 60
                results[f'{attacker}_airvtanks_{defender}_total'] = results[f'{attacker}_airvtanks_{defender}_alum'] * 2971 + results[f'{attacker}_airvtanks_{defender}_steel'] * 3990 + results[f'{attacker}_air_{defender}_gas'] * 3340 + results[f'{attacker}_air_{defender}_mun'] * 1960 + results[f'{attacker}_airvtanks_{defender}_money'] 
                results[f'{attacker}_airvtanks_net'] = results[f'{attacker}_airvtanks_{defender}_total'] - results[f'{attacker}_airvtanks_{attacker}_total']


                results[f'{attacker}_airvships_{attacker}_alum'] = results[f'{attacker}_airvother_{attacker}_avg'] * 5 - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvother_{attacker}_avg'] * 5) - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvother_{defender}_avg'] * 5)
                results[f'{attacker}_airvships_{attacker}_steel'] = 0
                results[f'{attacker}_airvships_{attacker}_money'] = results[f'{attacker}_airvother_{attacker}_avg'] * 4000
                results[f'{attacker}_airvships_{attacker}_total'] = results[f'{attacker}_airvships_{attacker}_alum'] * 2971 + results[f'{attacker}_airvships_{attacker}_steel'] * 3990 + results[f'{attacker}_air_{attacker}_gas'] * 3340 + results[f'{attacker}_air_{attacker}_mun'] * 1960 + results[f'{attacker}_airvships_{attacker}_money'] 
                
                results[f'{attacker}_airvships_{defender}_alum'] = results[f'{attacker}_airvother_{defender}_avg'] * 5
                results[f'{attacker}_airvships_{defender}_steel'] = results[f'{attacker}_air_{defender}_ships_destroyed_avg'] * 30
                results[f'{attacker}_airvships_{defender}_money'] = results[f'{attacker}_airvother_{defender}_avg'] * 4000 + results[f'{attacker}_air_{defender}_lost_infra_avg_value'] * 1/3 + results[f'{attacker}_air_{defender}_ships_destroyed_avg'] * 50000
                results[f'{attacker}_airvships_{defender}_total'] = results[f'{attacker}_airvships_{defender}_alum'] * 2971 + results[f'{attacker}_airvships_{defender}_steel'] * 3990 + results[f'{attacker}_air_{defender}_gas'] * 3340 + results[f'{attacker}_air_{defender}_mun'] * 1960 + results[f'{attacker}_airvships_{defender}_money'] 
                results[f'{attacker}_airvships_net'] = results[f'{attacker}_airvships_{defender}_total'] - results[f'{attacker}_airvships_{attacker}_total']


                results[f'{attacker}_naval_{attacker}_mun'] = results[attacker]['ships'] * 2.5
                results[f'{attacker}_naval_{attacker}_gas'] = results[attacker]['ships'] * 1.5
                results[f'{attacker}_naval_{attacker}_alum'] = 0
                results[f'{attacker}_naval_{attacker}_steel'] = results[f'{attacker}_naval_{attacker}_avg'] * 30 + salvage(results[f'{attacker}_naval_win_rate'], results[f'{attacker}_naval_{attacker}_avg'] * 30) + salvage(results[f'{attacker}_naval_win_rate'], results[f'{attacker}_naval_{defender}_avg'] * 30)
                results[f'{attacker}_naval_{attacker}_money'] = results[f'{attacker}_naval_{attacker}_avg'] * 50000
                results[f'{attacker}_naval_{attacker}_total'] = results[f'{attacker}_naval_{attacker}_alum'] * 2971 + results[f'{attacker}_naval_{attacker}_steel'] * 3990 + results[f'{attacker}_naval_{attacker}_gas'] * 3340 + results[f'{attacker}_naval_{attacker}_mun'] * 1960 + results[f'{attacker}_naval_{attacker}_money'] 
            
                base_mun = results[defender]['ships'] * 2.5 * def_rss_consumption(results[f'{attacker}_naval_win_rate'])
                results[f'{attacker}_naval_{defender}_mun'] = results[f'{attacker}_naval_{defender}_mun'] = (base_mun * (1 - results[f'{attacker}_naval_fail']) + min(base_gas, results[f'{attacker}_naval_{attacker}_mun']) * results[f'{attacker}_naval_fail'])
                base_gas = results[defender]['ships'] * 1.5 * def_rss_consumption(results[f'{attacker}_naval_win_rate'])
                results[f'{attacker}_naval_{defender}_gas'] = results[f'{attacker}_naval_{defender}_gas'] = (base_gas * (1 - results[f'{attacker}_naval_fail']) + min(base_gas, results[f'{attacker}_naval_{attacker}_gas']) * results[f'{attacker}_naval_fail'])
                results[f'{attacker}_naval_{defender}_alum'] = 0
                results[f'{attacker}_naval_{defender}_steel'] = results[f'{attacker}_naval_{defender}_avg'] * 30
                results[f'{attacker}_naval_{defender}_money'] = results[f'{attacker}_naval_{defender}_lost_infra_avg_value'] + results[f'{attacker}_naval_{defender}_avg'] * 50000
                results[f'{attacker}_naval_{defender}_total'] = results[f'{attacker}_naval_{defender}_alum'] * 2971 + results[f'{attacker}_naval_{defender}_steel'] * 3990 + results[f'{attacker}_naval_{defender}_gas'] * 3340 + results[f'{attacker}_naval_{defender}_mun'] * 1960 + results[f'{attacker}_naval_{defender}_money'] 
                results[f'{attacker}_naval_net'] = results[f'{attacker}_naval_{defender}_total'] - results[f'{attacker}_naval_{attacker}_total']


                results[f'{attacker}_nuke_{attacker}_alum'] = 750
                results[f'{attacker}_nuke_{attacker}_steel'] = 0
                results[f'{attacker}_nuke_{attacker}_gas'] = 500
                results[f'{attacker}_nuke_{attacker}_mun'] = 0
                results[f'{attacker}_nuke_{attacker}_money'] = 1750000
                results[f'{attacker}_nuke_{attacker}_total'] = results[f'{attacker}_nuke_{attacker}_alum'] * 2971 + results[f'{attacker}_nuke_{attacker}_steel'] * 3990 + results[f'{attacker}_nuke_{attacker}_gas'] * 3340 + results[f'{attacker}_nuke_{attacker}_mun'] * 1960 + results[f'{attacker}_nuke_{attacker}_money'] + 250 * 3039 #price of uranium
                
                results[f'{attacker}_nuke_{defender}_alum'] = 0
                results[f'{attacker}_nuke_{defender}_steel'] = 0
                results[f'{attacker}_nuke_{defender}_gas'] = 0
                results[f'{attacker}_nuke_{defender}_mun'] = 0
                results[f'{attacker}_nuke_{defender}_money'] = results[f'{attacker}_nuke_{defender}_lost_infra_avg_value']
                results[f'{attacker}_nuke_{defender}_total'] = results[f'{attacker}_nuke_{defender}_alum'] * 2971 + results[f'{attacker}_nuke_{defender}_steel'] * 3990 + results[f'{attacker}_nuke_{defender}_gas'] * 3340 + results[f'{attacker}_nuke_{defender}_mun'] * 1960 + results[f'{attacker}_nuke_{defender}_money'] 
                results[f'{attacker}_nuke_net'] = results[f'{attacker}_nuke_{defender}_total'] - results[f'{attacker}_nuke_{attacker}_total']


                results[f'{attacker}_missile_{attacker}_alum'] = 100
                results[f'{attacker}_missile_{attacker}_steel'] = 0
                results[f'{attacker}_missile_{attacker}_gas'] = 75
                results[f'{attacker}_missile_{attacker}_mun'] = 75
                results[f'{attacker}_missile_{attacker}_money'] = 150000
                results[f'{attacker}_missile_{attacker}_total'] = results[f'{attacker}_missile_{attacker}_alum'] * 2971 + results[f'{attacker}_missile_{attacker}_steel'] * 3990 + results[f'{attacker}_missile_{attacker}_gas'] * 3340 + results[f'{attacker}_missile_{attacker}_mun'] * 1960 + results[f'{attacker}_missile_{attacker}_money']

                results[f'{attacker}_missile_{defender}_alum'] = 0
                results[f'{attacker}_missile_{defender}_steel'] = 0
                results[f'{attacker}_missile_{defender}_gas'] = 0
                results[f'{attacker}_missile_{defender}_mun'] = 0
                results[f'{attacker}_missile_{defender}_money'] = results[f'{attacker}_missile_{defender}_lost_infra_avg_value']
                results[f'{attacker}_missile_{defender}_total'] = results[f'{attacker}_missile_{defender}_alum'] * 2971 + results[f'{attacker}_missile_{defender}_steel'] * 3990 + results[f'{attacker}_missile_{defender}_gas'] * 3340 + results[f'{attacker}_missile_{defender}_mun'] * 1960 + results[f'{attacker}_missile_{defender}_money'] 
                results[f'{attacker}_missile_net'] = results[f'{attacker}_missile_{defender}_total'] - results[f'{attacker}_missile_{attacker}_total']
                
            return results
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

def setup(bot):
    bot.add_cog(TargetFinding(bot))