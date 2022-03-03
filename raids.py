import discord
if "__name__" == "raids":
    from main import mongo
from discord.ext import commands
import aiohttp
import re
from mako.template import Template
import asyncio
import random
import pathlib
import os
from datetime import datetime, timedelta
import utils
from keep_alive import app
from flask.views import MethodView
from flask import request

api_key = os.getenv("api_key")

class TargetFinding(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['raid'])
    async def raids(self, ctx, *, arg=None):
        invoker = str(ctx.author.id)
        async with aiohttp.ClientSession() as session:
            message = await ctx.send('Finding person...')
            if arg == None:
                arg = ctx.author.id
            attacker = utils.find_nation_plus(self, arg)
            if not attacker:
                await message.edit(content='I could not find your nation, make sure that you are verified!')
                return
            async with session.post(f"https://api.politicsandwar.com/graphql?api_key={api_key}", json={'query': f"{{nations(first:1 id:{attacker['id']}){{data{{nation_name score id population soldiers tanks aircraft ships}}}}}}"}) as temp:
                atck_ntn = (await temp.json())['data']['nations']['data'][0]
            if atck_ntn == None:
                await message.edit(content='I did not find that person!')
                return
            minscore = round(atck_ntn['score'] * 0.75)
            maxscore = round(atck_ntn['score'] * 1.75)
            
            performace_filter = None
            class stage_six(discord.ui.View):
                @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal performace_filter
                    performace_filter = True
                    await i.response.pong()
                    self.stop()
                
                @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal performace_filter
                    performace_filter = False
                    await i.response.pong()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await message.edit(content=f"<@{ctx.author.id}> The command timed out!")

            beige = None
            class stage_five(discord.ui.View):
                @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal beige
                    beige = True
                    await i.response.pong()
                    self.stop()
                
                @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal beige
                    beige = False
                    await i.response.pong()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await message.edit(content=f"<@{ctx.author.id}> The command timed out!")

            inactive_limit = None
            class stage_four(discord.ui.View):
                @discord.ui.button(label="I don't care", style=discord.ButtonStyle.primary)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal inactive_limit
                    inactive_limit = 0
                    await i.response.pong()
                    self.stop()
                
                @discord.ui.button(label="7+ days inactive", style=discord.ButtonStyle.primary)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal inactive_limit
                    inactive_limit = 7
                    await i.response.pong()
                    self.stop()

                @discord.ui.button(label="14+ days inactive", style=discord.ButtonStyle.primary)
                async def tertiary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal inactive_limit
                    inactive_limit = 14
                    await i.response.pong()
                    self.stop()
                
                @discord.ui.button(label="30+ days inactive", style=discord.ButtonStyle.primary)
                async def quadrary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal inactive_limit
                    inactive_limit = 30
                    await i.response.pong()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await message.edit(content=f"<@{ctx.author.id}> The command timed out!")

            max_wars = None
            class stage_three(discord.ui.View):
                @discord.ui.button(label="0", style=discord.ButtonStyle.primary)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal max_wars
                    max_wars = 0
                    await i.response.pong()
                    self.stop()
                
                @discord.ui.button(label="1 or less", style=discord.ButtonStyle.primary)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal max_wars
                    max_wars = 1
                    await i.response.pong()
                    self.stop()

                @discord.ui.button(label="2 or less", style=discord.ButtonStyle.primary)
                async def tertiary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal max_wars
                    max_wars = 2
                    await i.response.pong()
                    self.stop()
                
                @discord.ui.button(label="3 or less", style=discord.ButtonStyle.primary)
                async def quadrary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal max_wars
                    max_wars = 3
                    await i.response.pong()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await message.edit(content=f"<@{ctx.author.id}> The command timed out!")
                    
            who = None
            class stage_two(discord.ui.View):
                @discord.ui.button(label="All nations", style=discord.ButtonStyle.primary)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal who
                    who = ""
                    await i.response.pong()
                    self.stop()
                
                @discord.ui.button(label="Applicants and nations not in alliances", style=discord.ButtonStyle.primary)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal who
                    who = " alliance_id:[0,1]"
                    await i.response.pong()
                    self.stop()

                @discord.ui.button(label="Nations not affiliated with any alliance", style=discord.ButtonStyle.primary)
                async def tertiary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal who
                    who = " alliance_id:0"
                    await i.response.pong()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await message.edit(content=f"<@{ctx.author.id}> The command timed out!")

            webpage = None
            class stage_one(discord.ui.View):
                @discord.ui.button(label="On discord", style=discord.ButtonStyle.primary)
                async def callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal webpage
                    webpage = False
                    await i.response.pong()
                    self.stop()
                
                @discord.ui.button(label="As a webpage", style=discord.ButtonStyle.primary)
                async def one_two_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal webpage
                    webpage = True
                    await i.response.pong()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await message.edit(content=f"<@{ctx.author.id}> The command timed out!")

            target_list = []
            futures = []
            tot_pages = 0
            progress = 0
            
            async def call_api(url, json):
                nonlocal progress
                async with session.post(url, json=json) as temp:
                    resp = await temp.json()
                    progress += 1
                    print(f"Getting targets... ({progress}/{tot_pages})")
                    #print("future recieved")
                    return resp
           
            async def fetch_targets():
                nonlocal tot_pages, progress
                url = f"https://api.politicsandwar.com/graphql?api_key={api_key}"
                async with session.post(url, json={'query': f"{{nations(page:1 first:50 min_score:{minscore} max_score:{maxscore} vmode:false{who}){{paginatorInfo{{lastPage}}}}}}"}) as temp1:
                    tot_pages += (await temp1.json())['data']['nations']['paginatorInfo']['lastPage']

                for n in range(1, tot_pages+1):
                    json = {'query': f"{{nations(page:{n} first:50 min_score:{minscore} max_score:{maxscore} vmode:false{who}){{data{{id flag nation_name last_active leader_name continent dompolicy population alliance_id beigeturns score color soldiers tanks aircraft ships missiles nukes bounties{{amount war_type}} treasures{{name}} alliance{{name}} wars{{date winner defid turnsleft attacks{{loot_info victor moneystolen}}}} alliance_position num_cities ironw bauxitew armss egr massirr itc recycling_initiative telecom_satellite green_tech clinical_research_center specialized_police_training uap cities{{date powered infrastructure land oilpower windpower coalpower nuclearpower coalmine oilwell uramine barracks farm policestation hospital recyclingcenter subway supermarket bank mall stadium leadmine ironmine bauxitemine gasrefinery aluminumrefinery steelmill munitionsfactory factory airforcebase drydock}}}}}}}}"}
                    futures.append(asyncio.ensure_future(call_api(url, json)))
                
            embed0 = discord.Embed(title=f"Presentation", description="How do you want to get your targets?", color=0x00ff00)
            embed1 = discord.Embed(title=f"Filters (1/5)", description="What nations do you want to include?", color=0x00ff00)
            embed2 = discord.Embed(title=f"Filters (2/5)", description="How many active defensive wars should they have?", color=0x00ff00)
            embed3 = discord.Embed(title=f"Filters (3/5)", description="How inactive should they be?", color=0x00ff00)
            embed4 = discord.Embed(title=f"Filters (4/5)", description="Do you want to include beige nations?", color=0x00ff00)
            embed5 = discord.Embed(title=f"Filters (5/5)", description='Do you want to improve performance by filtering out "bad" targets?\n\nMore specifically, this will omit nations with negative income, nations that have a stronger ground force than you, and nations that were previously beiged for $0.', color=0x00ff00)

            for embed, view in [(embed0, stage_one()), (embed1, stage_two()), (embed2, stage_three()), (embed3, stage_four()), (embed4, stage_five()), (embed5, stage_six())]:
                if embed == embed2:
                    fetching = asyncio.ensure_future(fetch_targets())
                await message.edit(content="", embed=embed, view=view)
                await view.wait()

            await message.edit(content="Getting targets...", view=None, embed=None)
            
            if progress < tot_pages - 5:
                rndm = random.choice(["", "2", "3"])
                with open (pathlib.Path.cwd() / 'data' / 'attachments' / f'waiting{rndm}.gif', 'rb') as gif:
                    gif = discord.File(gif)
                await message.edit(file=gif)

            await asyncio.gather(fetching)
            while progress < tot_pages:
                await message.edit(content=f"Getting targets... ({progress}/{tot_pages})")
                await asyncio.sleep(1)

            done_jobs = await asyncio.gather(*futures)

            await message.edit(content="Caching targets...")
            for done_job in done_jobs:
                for x in done_job['data']['nations']['data']:
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
                    if x['alliance_id'] in ["4729", "7531"]:
                        continue
                    if used_slots > max_wars:
                        continue
                    if (datetime.utcnow() - datetime.strptime(x['last_active'], "%Y-%m-%d %H:%M:%S%z").replace(tzinfo=None)).days < inactive_limit:
                        continue
                    target_list.append(x)
                    
            if len(target_list) == 0:
                await message.edit(content="No targets matched your criteria!", attachments=[])
                return

            filters = "No active filters"
            filter_list = []
            if not beige or who != "" or max_wars != 3 or performace_filter or inactive_limit != 0:
                filters = "Active filters: "
                if not beige:
                    filter_list.append("hide beige nations")
                if who != "":
                    if "1" not in who:
                        filter_list.append("hide full alliance members")
                    else:
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
                filters = filters + ", ".join(filter_list)

            temp, colors, prices, treasures, radiation, seasonal_mod = await utils.pre_revenue_calc(api_key, message, query_for_nation=False, parsed_nation=atck_ntn)

            await message.edit(content='Calculating best targets...')

            for target in target_list:
                embed = discord.Embed(title=f"{target['nation_name']}", url=f"https://politicsandwar.com/nation/id={target['id']}", description=f"{filters}\n\u200b", color=0x00ff00)
                prev_nat_loot = False
                target['infrastructure'] = 0
                target['def_slots'] = 0
                target['time_since_war'] = "14+"
                
                if target['wars'] != []:
                    for war in target['wars']:
                        if war['date'] == '-0001-11-30 00:00:00':
                            target['wars'].remove(war)
                        elif war['defid'] == target['id']:
                            if war['turnsleft'] > 0:
                                target['def_slots'] += 1
                            
                    wars = sorted(target['wars'], key=lambda k: k['date'], reverse=True)
                    war = wars[0]
                    if target['def_slots'] == 0:
                        target['time_since_war'] = (datetime.utcnow() - datetime.strptime(war['date'], "%Y-%m-%d %H:%M:%S%z").replace(tzinfo=None)).days
                    else:
                        target['time_since_war'] = "Ongoing"
                    if war['winner'] in ["0", target['id']]:
                        pass
                    else:
                        nation_loot = 0
                        prev_nat_loot = True
                        for attack in war['attacks']:
                            if attack['victor'] == target['id']:
                                continue
                            if attack['loot_info']:
                                text = attack['loot_info']
                                if "won the war and looted" in text:
                                    text = text[text.index('looted') + 7 :text.index(' Food. ')]
                                    text = re.sub(r"[^0-9-]+", "", text.replace(", ", "-"))
                                    rss = ['money', 'coal', 'oil', 'uranium', 'iron', 'bauxite', 'lead', 'gasoline', 'munitions', 'steel', 'aluminum', 'food']
                                    n = 0
                                    loot = {}
                                    for sub in text.split("-"):
                                        loot[rss[n]] = int(sub)
                                        n += 1
                                    for rs in rss:
                                        amount = loot[rs]
                                        price = int(prices[rs])
                                        nation_loot += amount * price
                                else:
                                    continue
                        target['nation_loot'] = f"{round(nation_loot):,}"
                        embed.add_field(name="Previous nation loot", value=f"${round(nation_loot):,}")

                if prev_nat_loot == False:
                    embed.add_field(name="Previous nation loot", value="NaN")
                    target['nation_loot'] = "NaN"

                rev_obj = await utils.revenue_calc(message, target, radiation, treasures, prices, colors, seasonal_mod)

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
                    days_inactive = (datetime.utcnow() - datetime.strptime(target['last_active'], "%Y-%m-%d %H:%M:%S%z").replace(tzinfo=None)).days

                for city in target['cities']:
                    target['infrastructure'] += city['infrastructure']

                embed.add_field(name="Beige", value=f"{target['beigeturns']} turns")

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
                #     if bounty['war_type'] == None:
                #         bounty['war_type'] = "NUCLEAR"
                #     bounty_info[bounty['war_type']] += bounty['amount']   
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
                    await message.edit(content="No targets matched your criteria!", attachments=[])
                    return
                
        best_targets = sorted(target_list, key=lambda k: k['monetary_net_num'], reverse=True)

        if webpage:
            endpoint = datetime.utcnow().strftime('%d%H%M%S')
            class webraid(MethodView):
                def get(raidclass):
                    beige_alerts = mongo.global_users.find_one({"user": int(invoker)})['beige_alerts']
                    with open('./data/templates/raidspage.txt', 'r') as file:
                        template = file.read()
                    result = Template(template).render(attacker=atck_ntn, targets=best_targets, endpoint=endpoint, invoker=str(invoker), beige_alerts=beige_alerts, beige=beige, datetime=datetime)
                    return str(result)

                def post(raidclass):
                    data = request.json
                    reminder = {}
                    turns = int(data['turns'])
                    time = datetime.utcnow()
                    if time.hour % 2 == 0:
                        time += timedelta(hours=turns*2)
                    else:
                        time += timedelta(hours=turns*2-1)
                    reminder['time'] = datetime(time.year, time.month, time.day, time.hour)
                    reminder['id'] = str(data['id'])
                    mongo.global_users.find_one_and_update({"user": int(data['invoker'])}, {"$push": {"beige_alerts": reminder}})
                    return "you good"

            app.add_url_rule(f"/raids/{endpoint}", view_func=webraid.as_view(str(datetime.utcnow())), methods=["GET", "POST"]) # this solution of adding a new page instead of updating an existing for the same nation is kinda dependent on the bot resetting every once in a while, bringing down all the endpoints
            await message.edit(content=f"Go to https://autolycus.politicsandwar.repl.co/raids/{endpoint}", attachments=[])
            return
        
        pages = len(target_list)
        cur_page = 1

        def get_embed(nation):
            nonlocal tot_pages, cur_page
            embed = nation['embed']
            if "*" in nation['money_txt']:
                embed.set_footer(text=f"Page {cur_page}/{pages}  |  * the income if the nation is out of food.")
            else:
                embed.set_footer(text=f"Page {cur_page}/{pages}")
            return embed

        msg_embd = get_embed(best_targets[0])

        class embed_paginator(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=900)

            def button_check(self, x):
                beige_button = [x for x in self.children if x.custom_id == "beige"][0]
                if x['beigeturns'] > 0:
                    beige_button.disabled = False
                else:
                    beige_button.disabled = True

            @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
            async def left_callback(self, b: discord.Button, i: discord.Interaction):
                nonlocal cur_page
                if cur_page > 1:
                    cur_page -= 1
                    msg_embd = get_embed(best_targets[cur_page-1])
                    self.button_check(best_targets[cur_page-1])
                    await i.response.edit_message(content="", embed=msg_embd, view=view)
                else:
                    cur_page = pages
                    msg_embd = get_embed(best_targets[cur_page-1])
                    self.button_check(best_targets[cur_page-1])
                    await i.response.edit_message(content="", embed=msg_embd, view=view)
            
            @discord.ui.button(label=">", style=discord.ButtonStyle.primary)
            async def right_callback(self, b: discord.Button, i: discord.Interaction):
                nonlocal cur_page
                if cur_page != pages:
                    cur_page += 1
                    msg_embd = get_embed(best_targets[cur_page-1])
                    self.button_check(best_targets[cur_page-1])
                    await i.response.edit_message(content="", embed=msg_embd, view=view)
                else:
                    cur_page = 1
                    msg_embd = get_embed(best_targets[cur_page-1])
                    self.button_check(best_targets[cur_page-1])
                    await i.response.edit_message(content="", embed=msg_embd, view=view)
        
            if best_targets[0]['beigeturns'] > 0:
                disabled = False
            else:
                disabled = True

            @discord.ui.button(label="Beige reminder", style=discord.ButtonStyle.primary, disabled=disabled, custom_id="beige")
            async def beige_callback(self, b: discord.Button, i: discord.Interaction):
                nonlocal cur_page
                reminder = {}
                cur_embed = best_targets[cur_page-1]
                turns = cur_embed['beigeturns']
                if turns == 0:
                    await i.response.send_message(content=f"They are not in beige!", ephemeral=True)
                    return
                time = datetime.utcnow()
                if time.hour % 2 == 0:
                    time += timedelta(hours=turns*2)
                else:
                    time += timedelta(hours=turns*2-1)
                reminder['time'] = datetime(time.year, time.month, time.day, time.hour)
                reminder['id'] = cur_embed['id']
                user = mongo.global_users.find_one({"user": ctx.author.id})
                if user == None:
                    await i.response.send_message(content=f"I didn't find you in the database! You better ping Randy I guess.", ephemeral=True)
                    return
                for entry in user['beige_alerts']:
                    if reminder['id'] == entry['id']:
                        await i.response.send_message(content=f"You already have a beige reminder for this nation!", ephemeral=True)
                        return
                mongo.global_users.find_one_and_update({"user": ctx.author.id}, {"$push": {"beige_alerts": reminder}})

            @discord.ui.button(label='Type "page <number>" to go to that page', style=discord.ButtonStyle.gray, disabled=True)
            async def info_callback(self, b: discord.Button, i: discord.Interaction):
                pass

            async def interaction_check(self, interaction) -> bool:
                if interaction.user != ctx.author:
                    await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                    return False
                else:
                    return True

        view = embed_paginator()
        await message.edit(content="", embed=msg_embd, attachments=[], view=view)

        async def message_checker():
            while True:
                try:
                    nonlocal cur_page
                    command = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author and message.channel.id == ctx.channel.id, timeout=900)
                    if "page" in command.content.lower():
                        try:
                            cur_page = int(re.sub("\D", "", command.content))
                            msg_embd = best_targets[cur_page-1]['embed']
                            msg_embd.set_footer(text=f"Page {cur_page}/{pages}")
                            await message.edit(content="", embed=msg_embd, view=view)
                            await command.delete()
                        except:
                            msg_embd = best_targets[0]['embed']
                            msg_embd.set_footer(text=f"Page {1}/{pages}")
                            await message.edit(content=f"<@{ctx.author.id}> Something went wrong with your input!", embed=msg_embd, view=view)
                except asyncio.TimeoutError:
                    await message.edit(content=f"<@{ctx.author.id}> Command timed out!")
                    break
        
        msg_task = asyncio.create_task(message_checker())
        await asyncio.gather(msg_task)

def setup(bot):
    bot.add_cog(TargetFinding(bot))