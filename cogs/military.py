import discord
from discord.ext import commands
from discord.commands import slash_command, Option
import aiohttp
import re
from mako.template import Template
import asyncio
import random
import pathlib
from typing import Union
import os
from datetime import datetime, timedelta
import utils
from keep_alive import app
from flask.views import MethodView
from flask import request
import requests
from main import mongo

api_key = os.getenv("api_key")

class TargetFinding(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    def winrate_calc(self, attacker_value, defender_value):
        try:
            x = attacker_value / defender_value
            if x > 2:
                winrate = 1
            elif x < 0.4:
                winrate = 0
            else:
                winrate = (12.832883444301027*x**(11)-171.668262561212487*x**(10)+1018.533858483560834*x**(9)-3529.694284997589875*x**(8)+7918.373606722701879*x**(7)-12042.696852729619422*x**(6)+12637.399722721022044*x**(5)-9128.535790660698694*x**(4)+4437.651655224382012*x**(3)-1378.156072477675025*x**(2)+245.439740545813436*x-18.980551645186498)
        except ZeroDivisionError:
            winrate = 1
        return winrate

    @slash_command(
        name="raids",
        description="Find raid targets",
        )
    async def raids(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        invoker = str(ctx.author.id)
        async with aiohttp.ClientSession() as session:
            attacker = utils.find_nation_plus(self, ctx.author.id)
            if not attacker:
                await ctx.edit(content='I could not find your nation, make sure that you are verified!')
                return
            async with session.post(f"https://api.politicsandwar.com/graphql?api_key={api_key}", json={'query': f"{{nations(first:1 id:{attacker['id']}){{data{{nation_name score id population soldiers tanks aircraft ships}}}}}}"}) as temp:
                atck_ntn = (await temp.json())['data']['nations']['data'][0]
            if atck_ntn == None:
                await ctx.edit(content='I did not find that person!')
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
                    await ctx.edit(content=f"<@{ctx.author.id}> The command timed out!")

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
                    await ctx.edit(content=f"<@{ctx.author.id}> The command timed out!")

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
                    await ctx.edit(content=f"<@{ctx.author.id}> The command timed out!")

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
                    await ctx.edit(content=f"<@{ctx.author.id}> The command timed out!")
                    
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
                    await ctx.edit(content=f"<@{ctx.author.id}> The command timed out!")

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
                    await ctx.edit(content=f"<@{ctx.author.id}> The command timed out!")

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
                
            embed0 = discord.Embed(title=f"Presentation", description="How do you want to get your targets?", color=0xff5100)
            embed1 = discord.Embed(title=f"Filters (1/5)", description="What nations do you want to include?", color=0xff5100)
            embed2 = discord.Embed(title=f"Filters (2/5)", description="How many active defensive wars should they have?", color=0xff5100)
            embed3 = discord.Embed(title=f"Filters (3/5)", description="How inactive should they be?", color=0xff5100)
            embed4 = discord.Embed(title=f"Filters (4/5)", description="Do you want to include beige nations?", color=0xff5100)
            embed5 = discord.Embed(title=f"Filters (5/5)", description='Do you want to improve performance by filtering out "bad" targets?\n\nMore specifically, this will omit nations with negative income, nations that have a stronger ground force than you, and nations that were previously beiged for $0.', color=0xff5100)

            for embed, view in [(embed0, stage_one()), (embed1, stage_two()), (embed2, stage_three()), (embed3, stage_four()), (embed4, stage_five()), (embed5, stage_six())]:
                if embed == embed2:
                    fetching = asyncio.ensure_future(fetch_targets())
                await ctx.edit(content="", embed=embed, view=view)
                await view.wait()

            await ctx.edit(content="Getting targets...", view=None, embed=None)
            
            if progress < tot_pages - 5:
                rndm = random.choice(["", "2", "3"])
                with open (pathlib.Path.cwd() / 'attachments' / f'waiting{rndm}.gif', 'rb') as gif:
                    gif = discord.File(gif)
                await ctx.edit(file=gif)

            await asyncio.gather(fetching)
            while progress < tot_pages:
                await ctx.edit(content=f"Getting targets... ({progress}/{tot_pages})")
                await asyncio.sleep(1)

            done_jobs = await asyncio.gather(*futures)

            await ctx.edit(content="Caching targets...")
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
                await ctx.edit(content="No targets matched your criteria!", attachments=[])
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

            temp, colors, prices, treasures, radiation, seasonal_mod = await utils.pre_revenue_calc(api_key, ctx, query_for_nation=False, parsed_nation=atck_ntn)

            await ctx.edit(content='Calculating best targets...')

            for target in target_list:
                embed = discord.Embed(title=f"{target['nation_name']}", url=f"https://politicsandwar.com/nation/id={target['id']}", description=f"{filters}\n\u200b", color=0xff5100)
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
                    await ctx.edit(content="No targets matched your criteria!", attachments=[])
                    return
                
        best_targets = sorted(target_list, key=lambda k: k['monetary_net_num'], reverse=True)

        if webpage:
            endpoint = datetime.utcnow().strftime('%d%H%M%S')
            class webraid(MethodView):
                def get(raidclass):
                    beige_alerts = mongo.global_users.find_one({"user": int(invoker)})['beige_alerts']
                    with open(pathlib.Path.cwd() / "templates" / "raidspage.txt", "r") as file:
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
            await ctx.edit(content=f"Go to https://autolycus.politicsandwar.repl.co/raids/{endpoint}", attachments=[])
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
                super().__init__(timeout=890)

            def button_check(self, x):
                beige_button = [x for x in self.children if x.custom_id == "beige"][0]
                user = mongo.global_users.find_one({"user": ctx.author.id})
                for entry in user['beige_alerts']:
                    if x['id'] == entry['id']:
                        beige_button.disabled = True
                        return
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
                beige_button = [x for x in self.children if x.custom_id == "beige"][0]
                reminder = {}
                cur_embed = best_targets[cur_page-1]
                turns = cur_embed['beigeturns']
                if turns == 0:
                    beige_button.disabled = True
                    await ctx.edit(view=view)
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
                        beige_button.disabled = True
                        await ctx.edit(view=view)
                        await i.response.send_message(content=f"You already have a beige reminder for this nation!", ephemeral=True)
                        return
                mongo.global_users.find_one_and_update({"user": ctx.author.id}, {"$push": {"beige_alerts": reminder}})
                beige_button.disabled = True
                await ctx.edit(view=view)
                await i.response.send_message(content=f"A beige reminder for <https://politicsandwar.com/nation/id={cur_embed['id']}> was added!", ephemeral=True)

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
        await ctx.edit(content="", embed=msg_embd, attachments=[], view=view)

        async def message_checker():
            while True:
                try:
                    nonlocal cur_page
                    command = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author and message.channel.id == ctx.channel.id, timeout=890)
                    if "page" in command.content.lower():
                        try:
                            cur_page = int(re.sub("\D", "", command.content))
                            msg_embd = best_targets[cur_page-1]['embed']
                            msg_embd.set_footer(text=f"Page {cur_page}/{pages}")
                            await ctx.edit(content="", embed=msg_embd, view=view)
                            try:
                                await command.delete()
                            except:
                                if random.random() * 15 < 1:
                                    await ctx.respond(content=f"Pro tip: With the `Manage Messages` permission, I can delete the \"page x\"-messages!")
                        except:
                            msg_embd = best_targets[0]['embed']
                            msg_embd.set_footer(text=f"Page {1}/{pages}")
                            await ctx.edit(content=f"<@{ctx.author.id}> Something went wrong with your input!", embed=msg_embd, view=view)
                except asyncio.TimeoutError:
                    await ctx.edit(content=f"<@{ctx.author.id}> Command timed out!")
                    break
        
        msg_task = asyncio.create_task(message_checker())
        await asyncio.gather(msg_task)
    
    @slash_command(
        name="reminders",
        description='Show all your active beige reminders',
        )
    async def reminders(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        person = mongo.global_users.find_one({"user": ctx.author.id})
        if person == None:
            await ctx.respond(content=f"I didn't find you in the database! Make sure that you have verified your nation!")
            return
        insults = ['ha loser', 'what a nub', 'such a pleb', 'get gud', 'u suc lol']
        insult = random.choice(insults)
        if person['beige_alerts'] == []:
            await ctx.respond(content=f"You have no beige reminders!\n\n||{insult}||")
            return
        reminders = ""
        person['beige_alerts'] = sorted(person['beige_alerts'], key=lambda k: k['time'], reverse=True)
        for x in person['beige_alerts']:
            reminders += (f"\n<t:{round(x['time'].timestamp())}> (<t:{round(x['time'].timestamp())}:R>) - <https://politicsandwar.com/nation/id={x['id']}>")
        await ctx.respond(content=f"Here are your reminders:\n{reminders}")
    
    @slash_command(
        name="delreminder",
        description='Delete a beige reminder'
        )
    async def delreminder(
        self,
        ctx: discord.ApplicationContext,
        nation: Option(str, "Nation name, nation link, discord username etc of the nation whose beige reminder you want to remove")
    ):
        await ctx.defer()
        person = mongo.global_users.find_one({"user": ctx.author.id})
        if person == None:
            await ctx.respond(content=f"I didn't find you in the database! Make sure that you have verified your nation!")
            return
        parsed_nation = utils.find_nation(nation)
        if parsed_nation == None:
            await ctx.respond("I could not find that nation!")
            return
        else:
            id = parsed_nation['id']

        found = False
        for alert in person['beige_alerts']:
            if alert['id'] == id:
                alert_list = person['beige_alerts'].remove(alert)
                if not alert_list:
                    alert_list = []
                mongo.global_users.find_one_and_update({"user": person['user']}, {"$set": {"beige_alerts": alert_list}})
                found = True
        if not found:
            await ctx.respond(content="I did not find a reminder for that nation!")
            return
        await ctx.respond(content=f"Your beige reminder for https://politicsandwar.com/nation/id={id} was deleted.")

    @slash_command(
        name="addreminder",
        description='Add a reminder for when a nation exits beige'
        )
    async def addreminder(
        self,
        ctx: discord.ApplicationContext,
        arg: Option(str, "Nation name, nation link, discord username etc of the nation you want to add a beige reminder for")
    ):
        await ctx.defer()
        nation = utils.find_nation(arg)
        if nation == None:
            await ctx.respond(content='I could not find that nation!')
            return
        res = requests.post(f"https://api.politicsandwar.com/graphql?api_key={api_key}", json={'query': f"{{nations(first:1 id:{nation['id']}){{data{{beigeturns}}}}}}"}).json()['data']['nations']['data'][0]
        if res['beigeturns'] == 0:
            await ctx.respond(content="They are not beige!")
            return
        reminder = {}
        turns = int(res['beigeturns'])
        time = datetime.utcnow()
        if time.hour % 2 == 0:
            time += timedelta(hours=turns*2)
        else:
            time += timedelta(hours=turns*2-1)
        reminder['time'] = datetime(time.year, time.month, time.day, time.hour)
        reminder['id'] = nation['id']
        user = mongo.global_users.find_one({"user": ctx.author.id})
        if user == None:
            await ctx.respond(content=f"I didn't find you in the database! Make sure that you have verified your nation!")
            return
        for entry in user['beige_alerts']:
            if reminder['id'] == entry['id']:
                await ctx.respond(content=f"You already have a beige reminder for this nation!")
                return
        mongo.global_users.find_one_and_update({"user": ctx.author.id}, {"$push": {"beige_alerts": reminder}})
        await ctx.respond(content=f"A beige reminder for https://politicsandwar.com/nation/id={nation['id']} was added.")

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
        await ctx.defer()
        if nation1 == None:
            nation1 = ctx.author.id
        nation1_nation = utils.find_nation_plus(self, nation1)
        if not nation1_nation:
            if nation2 == None:
                await ctx.respond(content='I could not find that nation!')
                return
            else:
                await ctx.respond(content='I could not find nation 1!')
                return 
        nation1_id = str(nation1_nation['id'])

        if nation2 == None:
            nation2 = ctx.author.id
        nation2_nation = utils.find_nation_plus(self, nation2)
        if not nation2_nation:
            if nation2 == None:
                await ctx.respond(content='I was able to find the nation you linked, but I could not find *your* nation!')
                return
            else:
                await ctx.respond(content='I could not find nation 2!')
                return 
        nation2_id = str(nation2_nation['id'])
        
        results = await self.battle_calc(nation1_id, nation2_id)

        embed = discord.Embed(title="Battle Simulator", description=f"These are the results for when [{results['nation1']['nation_name']}](https://politicsandwar.com/nation/id={results['nation1']['id']}){results['nation1_append']} attacks [{results['nation2']['nation_name']}](https://politicsandwar.com/nation/id={results['nation2']['id']}){results['nation2_append']}\nIf you want to use custom troop counts, you can use the [in-game battle simulators](https://politicsandwar.com/tools/)", color=0x00ff00)
        embed1 = discord.Embed(title="Battle Simulator", description=f"These are the results for when [{results['nation2']['nation_name']}](https://politicsandwar.com/nation/id={results['nation2']['id']}){results['nation2_append']} attacks [{results['nation1']['nation_name']}](https://politicsandwar.com/nation/id={results['nation1']['id']}){results['nation1_append']}\nIf you want to use custom troop counts, you can use the [in-game battle simulators](https://politicsandwar.com/tools/)", color=0x00ff00)

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
        
        embed.add_field(name="Casualties", value=f"*Targeting air:*\nAtt. Plane: {results['nation1_airtoair_nation1_avg']:,} ± {results['nation1_airtoair_nation1_diff']:,}\nDef. Plane: {results['nation1_airtoair_nation2_avg']:,} ± {results['nation1_airtoair_nation2_diff']:,}\n\n*Targeting other:*\nAtt. Plane: {results['nation1_airtoother_nation1_avg']:,} ± {results['nation1_airtoother_nation1_diff']:,}\nDef. Plane: {results['nation1_airtoother_nation2_avg']:,} ± {results['nation1_airtoother_nation2_diff']:,}\n\u200b")        
        embed1.add_field(name="Casualties", value=f"*Targeting air:*\nAtt. Plane: {results['nation2_airtoair_nation2_avg']:,} ± {results['nation2_airtoair_nation2_diff']:,}\nDef. Plane: {results['nation2_airtoair_nation1_avg']:,} ± {results['nation2_airtoair_nation1_diff']:,}\n\n*Targeting other:*\nAtt. Plane: {results['nation2_airtoother_nation2_avg']:,} ± {results['nation2_airtoother_nation2_diff']:,}\nDef. Plane: {results['nation2_airtoother_nation1_avg']:,} ± {results['nation2_airtoother_nation1_diff']:,}\n\u200b")        

        embed.add_field(name="Casualties", value=f"Att. Ships: {results['nation1_naval_nation1_avg']:,} ± {results['nation1_naval_nation1_diff']:,}\nDef. Ships: {results['nation1_naval_nation2_avg']:,} ± {results['nation1_naval_nation2_diff']:,}")        
        embed1.add_field(name="Casualties", value=f"Att. Ships: {results['nation2_naval_nation2_avg']:,} ± {results['nation2_naval_nation2_diff']:,}\nDef. Ships: {results['nation2_naval_nation1_avg']:,} ± {results['nation2_naval_nation1_diff']:,}")        

        cur_page = 1

        class switch(discord.ui.View):
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
        await ctx.defer()
        if nation1 == None:
            nation1 = ctx.author.id
        nation1_nation = utils.find_nation_plus(self, nation1)
        if not nation1_nation:
            if nation2 == None:
                await ctx.respond(content='I could not find that nation!')
                return
            else:
                await ctx.respond(content='I could not find nation 1!')
                return 
        nation1_id = str(nation1_nation['id'])

        if nation2 == None:
            nation2 = ctx.author.id
        nation2_nation = utils.find_nation_plus(self, nation2)
        if not nation2_nation:
            if nation2 == None:

                await ctx.respond(content='I was able to find the nation you linked, but I could not find *your* nation!')
                return
            else:
                await ctx.respond(content='I could not find nation 2!')

                return 
        nation2_id = str(nation2_nation['id'])
        
        results = await self.battle_calc(nation1_id, nation2_id)
        endpoint = datetime.utcnow().strftime('%d%H%M%S%f')
        class webraid(MethodView):
            def get(raidclass):
                with open(pathlib.Path.cwd() / "templates" / "damage.txt", "r") as file:
                    template = file.read()
                result = Template(template).render(results=results)
                return str(result)
        app.add_url_rule(f"/damage/{endpoint}", view_func=webraid.as_view(str(datetime.utcnow())), methods=["GET", "POST"]) # this solution of adding a new page instead of updating an existing for the same nation is kinda dependent on the bot resetting every once in a while, bringing down all the endpoints
        await ctx.respond(content=f"Go to https://autolycus.politicsandwar.repl.co/damage/{endpoint}")

        
    async def battle_calc(self, nation1_id, nation2_id):
        results = {}

        async with aiohttp.ClientSession() as session:
            async with session.post(f"https://api.politicsandwar.com/graphql?api_key={api_key}", json={'query': f"{{nations(first:1 id:{nation1_id}){{data{{nation_name population warpolicy id soldiers tanks aircraft ships irond vds cities{{infrastructure land}} wars{{groundcontrol airsuperiority navalblockade attpeace defpeace attid defid att_fortify def_fortify turnsleft war_type}}}}}}}}"}) as temp:
                results['nation1'] = (await temp.json())['data']['nations']['data'][0]
            async with session.post(f"https://api.politicsandwar.com/graphql?api_key={api_key}", json={'query': f"{{nations(first:1 id:{nation2_id}){{data{{nation_name population warpolicy id soldiers tanks aircraft ships irond vds cities{{infrastructure land}}}}}}}}"}) as temp:
                results['nation2'] = (await temp.json())['data']['nations']['data'][0]

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
            defender_tanks_value = results[defender]['tanks'] * 40 * results[f'{defender}_tanks']
            defender_soldiers_value = results[defender]['soldiers'] * 1.75 + results[defender]['population'] * 0.0025
            defender_army_value = defender_soldiers_value + defender_tanks_value

            attacker_tanks_value = results[attacker]['tanks'] * 40 * results[f'{attacker}_tanks']
            attacker_soldiers_value = results[attacker]['soldiers'] * 1.75
            attacker_army_value = attacker_soldiers_value + attacker_tanks_value

            results[f'{attacker}_ground_win_rate'] = self.winrate_calc(attacker_army_value, defender_army_value)
            results[f'{attacker}_ground_it'] = results[f'{attacker}_ground_win_rate']**3
            results[f'{attacker}_ground_mod'] = results[f'{attacker}_ground_win_rate']**2 * (1 - results[f'{attacker}_ground_win_rate']) * 3
            results[f'{attacker}_ground_pyr'] = results[f'{attacker}_ground_win_rate'] * (1 - results[f'{attacker}_ground_win_rate'])**2 * 3
            results[f'{attacker}_ground_fail'] = (1 - results[f'{attacker}_ground_win_rate'])**3

            results[f'{attacker}_air_win_rate'] = self.winrate_calc((results[f'{attacker}']['aircraft'] * 3), (results[f'{defender}']['aircraft'] * 3))
            results[f'{attacker}_air_it'] = results[f'{attacker}_air_win_rate']**3
            results[f'{attacker}_air_mod'] = results[f'{attacker}_air_win_rate']**2 * (1 - results[f'{attacker}_air_win_rate']) * 3
            results[f'{attacker}_air_pyr'] = results[f'{attacker}_air_win_rate'] * (1 - results[f'{attacker}_air_win_rate'])**2 * 3
            results[f'{attacker}_air_fail'] = (1 - results[f'{attacker}_air_win_rate'])**3

            results[f'{attacker}_naval_win_rate'] = self.winrate_calc((results[f'{attacker}']['ships'] * 4), (results[f'{defender}']['ships'] * 4))
            results[f'{attacker}_naval_it'] = results[f'{attacker}_naval_win_rate']**3
            results[f'{attacker}_naval_mod'] = results[f'{attacker}_naval_win_rate']**2 * (1 - results[f'{attacker}_naval_win_rate']) * 3
            results[f'{attacker}_naval_pyr'] = results[f'{attacker}_naval_win_rate'] * (1 - results[f'{attacker}_naval_win_rate'])**2 * 3
            results[f'{attacker}_naval_fail'] = (1 - results[f'{attacker}_naval_win_rate'])**3
            
            if results['gc'] == results[attacker]:
                results[f'{attacker}_ground_{defender}_avg_aircraft'] = avg_air = min(results[f'{attacker}']['tanks'] * 0.0075 * results[f'{attacker}_ground_win_rate'] ** 3, results[defender]['aircraft'])
                results[defender]['aircas'] = f"Def. Plane: {avg_air} ± {round(results[f'{attacker}']['tanks'] * 0.0075 * (1 - results[f'{attacker}_ground_win_rate'] ** 3))}"
            else:
                results[defender]['aircas'] = ""
                results[f'{attacker}_ground_{defender}_avg_aircraft'] = 0
            
            for type, cas_rate in [("avg", 0.7), ("diff", 0.3)]:
                results[f'{attacker}_ground_{attacker}_{type}_soldiers'] = min(round(((defender_soldiers_value * 0.0084) + (defender_tanks_value * 0.0092)) * cas_rate * 3), results[attacker]['soldiers'])
                results[f'{attacker}_ground_{attacker}_{type}_tanks'] = min(round((((defender_soldiers_value * 0.0004060606) + (defender_tanks_value * 0.00066666666)) * results[f'{attacker}_ground_win_rate'] + ((defender_soldiers_value * 0.00043225806) + (defender_tanks_value * 0.00070967741)) * (1 - results[f'{attacker}_ground_win_rate'])) * cas_rate * 3), results[attacker]['tanks'])
                results[f'{attacker}_ground_{defender}_{type}_soldiers'] = min(round(((attacker_soldiers_value * 0.0084) + (attacker_tanks_value * 0.0092)) * cas_rate * 3), results[defender]['soldiers'])
                results[f'{attacker}_ground_{defender}_{type}_tanks'] = min(round((((attacker_soldiers_value * 0.00043225806) + (attacker_tanks_value * 0.00070967741)) * results[f'{attacker}_ground_win_rate'] + ((attacker_soldiers_value * 0.0004060606) + (attacker_tanks_value * 0.00066666666)) * (1 - results[f'{attacker}_ground_win_rate'])) * cas_rate * 3), results[defender]['tanks'])

            results[f'{attacker}_airtoair_{attacker}_avg'] = min(round(results[f'{defender}']['aircraft'] * 3 * 0.7 * 0.01 * 3 * results[f'{attacker}_extra_cas']), results[f'{attacker}']['aircraft'])
            results[f'{attacker}_airtoair_{attacker}_diff'] = min(round(results[f'{defender}']['aircraft'] * 3 * 0.3 * 0.01 * 3 * results[f'{attacker}_extra_cas']), results[f'{attacker}']['aircraft'])
            results[f'{attacker}_airtoother_{attacker}_avg'] = min(round(results[f'{defender}']['aircraft'] * 3 * 0.7 * 0.015385 * 3 * results[f'{attacker}_extra_cas']), results[f'{attacker}']['aircraft'])
            results[f'{attacker}_airtoother_{attacker}_diff'] = min(round(results[f'{defender}']['aircraft'] * 3 * 0.3 * 0.015385 * 3 * results[f'{attacker}_extra_cas']), results[f'{attacker}']['aircraft'])

            results[f'{attacker}_airtoair_{defender}_avg'] = min(round(results[f'{attacker}']['aircraft'] * 3 * 0.7 * 0.018337 * 3), results[f'{defender}']['aircraft'])
            results[f'{attacker}_airtoair_{defender}_diff'] = min(round(results[f'{attacker}']['aircraft'] * 3 * 0.3 * 0.018337 * 3), results[f'{defender}']['aircraft'])
            results[f'{attacker}_airtoother_{defender}_avg'] = min(round(results[f'{attacker}']['aircraft'] * 3 * 0.7 * 0.009091 * 3), results[f'{defender}']['aircraft'])
            results[f'{attacker}_airtoother_{defender}_diff'] = min(round(results[f'{attacker}']['aircraft'] * 3 * 0.3 * 0.009091 * 3), results[f'{defender}']['aircraft'])

            results[f'{attacker}_naval_{defender}_avg'] = min(round(results[f'{attacker}']['ships'] * 4 * 0.7 * 0.01375 * 3 * results[f'{attacker}_extra_cas']), results[f'{defender}']['aircraft'])
            results[f'{attacker}_naval_{defender}_diff'] = min(round(results[f'{attacker}']['ships'] * 4 * 0.3 * 0.01375 * 3 * results[f'{attacker}_extra_cas']), results[f'{defender}']['aircraft'])
            results[f'{attacker}_naval_{attacker}_avg'] = min(round(results[f'{defender}']['ships'] * 4 * 0.7 * 0.01375 * 3), results[f'{attacker}']['aircraft'])
            results[f'{attacker}_naval_{attacker}_diff'] = min(round(results[f'{defender}']['ships'] * 4 * 0.3 * 0.01375 * 3), results[f'{attacker}']['aircraft'])

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
            elif results[f'{nation}']['vds']:
                results[f'{nation}_vds_mod'] = 0.8
            elif results[f'{nation}']['irond']:
                results[f'{nation}_irond_mod'] = 0.5
        
        def airstrike_casualties(winrate: Union[int, float]) -> float:
            rate = -0.4624 * winrate**2 + 1.06256 * winrate + 0.3999            
            if rate < 0.4:
                rate = 0.4
            return rate

        for attacker, defender in [("nation1", "nation2"), ("nation2", "nation1")]:
            results[f'{attacker}_ground_{defender}_lost_infra_avg'] = max(min(((results[f'{attacker}']['soldiers'] - results[f'{defender}']['soldiers'] * 0.5) * 0.000606061 + (results[f'{attacker}']['tanks'] - (results[f'{defender}']['tanks'] * 0.5)) * 0.01) * 0.95 * results[f'{attacker}_ground_win_rate'], results[defender]['city']['infrastructure'] * 0.2 + 25), 0) * results[f'{attacker}_war_infra_mod'] * results[f'{attacker}_policy_infra_dealt'] * results[f'{defender}_policy_infra_lost']
            results[f'{attacker}_ground_{defender}_lost_infra_diff'] = results[f'{attacker}_ground_{defender}_lost_infra_avg'] / 0.95 * 0.15
            results[f'{attacker}_ground_loot_avg'] = (results[f'{attacker}']['soldiers'] * 1.1 + results[f'{attacker}']['tanks'] * 25.15) * results[f'{attacker}_ground_win_rate'] * 3 * 0.95 * results[f'{attacker}_war_loot_mod'] * results[f'{attacker}_policy_loot_stolen'] * results[f'{defender}_policy_loot_lost']
            results[f'{attacker}_ground_loot_diff'] = results[f'{attacker}_ground_loot_avg'] / 0.95 * 0.1

            results[f'{attacker}_air_{defender}_lost_infra_avg'] = max(min((results[f'{attacker}']['aircraft'] - results[f'{defender}']['aircraft'] * 0.5) * 0.35353535 * 0.95 * results[f'{attacker}_air_win_rate'], results[defender]['city']['infrastructure'] * 0.5 + 100), 0) * results[f'{attacker}_war_infra_mod'] * results[f'{attacker}_policy_infra_dealt'] * results[f'{defender}_policy_infra_lost']
            results[f'{attacker}_air_{defender}_lost_infra_diff'] = results[f'{attacker}_air_{defender}_lost_infra_avg'] / 0.95 * 0.15
            results[f'{attacker}_air_{defender}_soldiers_destroyed_avg'] = round(max(min(results[f'{defender}']['soldiers'], results[f'{defender}']['soldiers'] * 0.75 + 1000, (results[f'{attacker}']['aircraft'] - results[f'{defender}']['aircraft'] * 0.5) * 35 * 0.95), 0)) * airstrike_casualties(results[f'{attacker}_air_win_rate'])
            results[f'{attacker}_air_{defender}_soldiers_destroyed_diff'] = results[f'{attacker}_air_{defender}_soldiers_destroyed_avg'] / 0.95 * 0.1
            results[f'{attacker}_air_{defender}_tanks_destroyed_avg'] = round(max(min(results[f'{defender}']['tanks'], results[f'{defender}']['tanks'] * 0.75 + 10, (results[f'{attacker}']['aircraft'] - results[f'{defender}']['aircraft'] * 0.5) * 1.25 * 0.95), 0)) * airstrike_casualties(results[f'{attacker}_air_win_rate'])
            results[f'{attacker}_air_{defender}_tanks_destroyed_diff'] = results[f'{attacker}_air_{defender}_tanks_destroyed_avg'] / 0.95 * 0.1
            results[f'{attacker}_air_{defender}_ships_destroyed_avg'] = round(max(min(results[f'{defender}']['ships'], results[f'{defender}']['ships'] * 0.75 + 4, (results[f'{attacker}']['aircraft'] - results[f'{defender}']['aircraft'] * 0.5) * 0.0285 * 0.95), 0)) * airstrike_casualties(results[f'{attacker}_air_win_rate'])
            results[f'{attacker}_air_{defender}_ships_destroyed_diff'] = results[f'{attacker}_air_{defender}_ships_destroyed_avg'] / 0.95 * 0.1

            results[f'{attacker}_naval_{defender}_lost_infra_avg'] = max(min((results[f'{attacker}']['ships'] - results[f'{attacker}']['ships'] * 0.5) * 2.625 * 0.95 * results[f'{attacker}_naval_win_rate'], results[defender]['city']['infrastructure'] * 0.5 + 25), 0) * results[f'{attacker}_war_infra_mod'] * results[f'{attacker}_policy_infra_dealt'] * results[f'{defender}_policy_infra_lost']
            results[f'{attacker}_naval_{defender}_lost_infra_diff'] = results[f'{attacker}_naval_{defender}_lost_infra_avg'] / 0.95 * 0.15

            results[f'{attacker}_nuke_{defender}_lost_infra_avg'] = max(min((1700 + max(2000, results[defender]['city']['infrastructure'] * 100 / results[defender]['city']['land'] * 13.5)) / 2, results[defender]['city']['infrastructure'] * 0.8 + 150), 0) * results[f'{attacker}_war_infra_mod'] * results[f'{attacker}_policy_infra_dealt'] * results[f'{defender}_policy_infra_lost'] * results[f'{attacker}_vds_mod']
            results[f'{attacker}_missile_{defender}_lost_infra_avg'] = max(min((300 + max(350, results[defender]['city']['infrastructure'] * 100 / results[defender]['city']['land'] * 3)) / 2, results[defender]['city']['infrastructure'] * 0.3 + 100), 0) * results[f'{attacker}_war_infra_mod'] * results[f'{attacker}_policy_infra_dealt'] * results[f'{defender}_policy_infra_lost'] * results[f'{attacker}_irond_mod']
            
            for infra in [
                f"{attacker}_ground_{defender}_lost_infra",
                f"{attacker}_air_{defender}_lost_infra",
                f"{attacker}_naval_{defender}_lost_infra",
                f"{attacker}_nuke_{defender}_lost_infra",
                f"{attacker}_missile_{defender}_lost_infra",
                ]:
                results[f'{infra}_avg_value'] = utils.infra_cost(results[defender]['city']['infrastructure'] - results[f'{infra}_avg'], results[defender]['city']['infrastructure'])
                try:
                    results[f'{infra}_diff_value'] = utils.infra_cost(results[defender]['city']['infrastructure'] - results[f'{infra}_diff'], results[defender]['city']['infrastructure'])
                except:
                    pass
            
            for attack in ['airvair', 'airvsoldiers', 'airvtanks', 'airvships']:
                results[f"{attacker}_{attack}_{defender}_lost_infra_avg_value"] = results[f"{attacker}_air_{defender}_lost_infra_avg_value"] * 1/3
            results[f"{attacker}_airvinfra_{defender}_lost_infra_avg_value"] = results[f"{attacker}_air_{defender}_lost_infra_avg_value"]

            results[f'{attacker}_ground_{attacker}_mun'] = results[f'{attacker}']['soldiers'] * 0.0002 + results[f'{attacker}']['tanks'] * 0.01
            results[f'{attacker}_ground_{attacker}_gas'] = results[f'{attacker}']['tanks'] * 0.01
            results[f'{attacker}_ground_{attacker}_alum'] = 0
            results[f'{attacker}_ground_{attacker}_steel'] = results[f'{attacker}_ground_{attacker}_avg_tanks'] * 0.5
            results[f'{attacker}_ground_{attacker}_money'] = -results[f'{attacker}_ground_loot_avg'] + results[f'{attacker}_ground_{attacker}_avg_tanks'] * 50 + results[f'{attacker}_ground_{attacker}_avg_soldiers'] * 5
            results[f'{attacker}_ground_{attacker}_total'] = results[f'{attacker}_ground_{attacker}_alum'] * 2971 + results[f'{attacker}_ground_{attacker}_steel'] * 3990 + results[f'{attacker}_ground_{attacker}_gas'] * 3340 + results[f'{attacker}_ground_{attacker}_mun'] * 1960 + results[f'{attacker}_ground_{attacker}_money'] 

            base_mun = (results[f'{defender}']['soldiers'] * 0.0002 + results[f'{defender}']['population'] / 2000000 + results[f'{defender}']['tanks'] * 0.01) * def_rss_consumption(results[f'{attacker}_ground_win_rate'])
            results[f'{attacker}_ground_{defender}_mun'] = (base_mun * (1 - results[f'{attacker}_ground_fail']) + min(base_mun, results[f'{attacker}_ground_{attacker}_mun']) * results[f'{attacker}_ground_fail'])
            base_gas = results[f'{defender}']['tanks'] * 0.01 * def_rss_consumption(results[f'{attacker}_ground_win_rate'])
            results[f'{attacker}_ground_{defender}_gas'] = (base_gas * (1 - results[f'{attacker}_ground_fail']) + min(base_gas, results[f'{attacker}_ground_{attacker}_gas']) * results[f'{attacker}_ground_fail'])
            results[f'{attacker}_ground_{defender}_alum'] = results[f'{attacker}_ground_{defender}_avg_aircraft'] * 5
            results[f'{attacker}_ground_{defender}_steel'] = results[f'{attacker}_ground_{defender}_avg_tanks'] * 0.5
            results[f'{attacker}_ground_{defender}_money'] = results[f'{attacker}_ground_loot_avg'] + results[f'{attacker}_ground_{defender}_avg_aircraft'] * 4000 + results[f'{attacker}_ground_{defender}_avg_tanks'] * 50 + results[f'{attacker}_ground_{defender}_avg_soldiers'] * 5 + results[f'{attacker}_ground_{defender}_lost_infra_avg_value']
            results[f'{attacker}_ground_{defender}_total'] = results[f'{attacker}_ground_{defender}_alum'] * 2971 + results[f'{attacker}_ground_{defender}_steel'] * 3990 + results[f'{attacker}_ground_{defender}_gas'] * 3340 + results[f'{attacker}_ground_{defender}_mun'] * 1960 + results[f'{attacker}_ground_{defender}_money'] 
            results[f'{attacker}_ground_net'] = results[f'{attacker}_ground_{defender}_total'] - results[f'{attacker}_ground_{attacker}_total']
            

            for attack in ['air', 'airvair', 'airvinfra', 'airvsoldiers', 'airvtanks', 'airvships']:
                results[f'{attacker}_{attack}_{attacker}_gas'] = results[f'{attacker}_{attack}_{attacker}_mun'] = results[f'{attacker}']['aircraft'] / 4
                base_gas = results[f'{defender}']['aircraft'] / 4 * def_rss_consumption(results[f'{attacker}_air_win_rate'])
                results[f'{attacker}_{attack}_{defender}_gas'] = results[f'{attacker}_{attack}_{defender}_mun'] = (base_gas * (1 - results[f'{attacker}_air_fail']) + min(base_gas, results[f'{attacker}_air_{attacker}_gas']) * results[f'{attacker}_air_fail'])


            results[f'{attacker}_airvair_{attacker}_alum'] = results[f'{attacker}_airtoair_{attacker}_avg'] * 5
            results[f'{attacker}_airvair_{attacker}_steel'] = 0
            results[f'{attacker}_airvair_{attacker}_money'] = results[f'{attacker}_airtoair_{attacker}_avg'] * 4000
            results[f'{attacker}_airvair_{attacker}_total'] = results[f'{attacker}_airvair_{attacker}_alum'] * 2971 + results[f'{attacker}_airvair_{attacker}_steel'] * 3990 + results[f'{attacker}_air_{attacker}_gas'] * 3340 + results[f'{attacker}_air_{attacker}_mun'] * 1960 + results[f'{attacker}_airvair_{attacker}_money'] 
           
            results[f'{attacker}_airvair_{defender}_alum'] = results[f'{attacker}_airtoair_{defender}_avg'] * 5
            results[f'{attacker}_airvair_{defender}_steel'] = 0
            results[f'{attacker}_airvair_{defender}_money'] = results[f'{attacker}_airtoair_{defender}_avg'] * 4000 + results[f'{attacker}_air_{defender}_lost_infra_avg_value'] * 1/3
            results[f'{attacker}_airvair_{defender}_total'] = results[f'{attacker}_airvair_{defender}_alum'] * 2971 + results[f'{attacker}_airvair_{defender}_steel'] * 3990 + results[f'{attacker}_air_{defender}_gas'] * 3340 + results[f'{attacker}_air_{defender}_mun'] * 1960 + results[f'{attacker}_airvair_{defender}_money'] 
            results[f'{attacker}_airvair_net'] = results[f'{attacker}_airvair_{defender}_total'] - results[f'{attacker}_airvair_{attacker}_total']


            results[f'{attacker}_airvinfra_{attacker}_alum'] = results[f'{attacker}_airtoother_{attacker}_avg'] * 5
            results[f'{attacker}_airvinfra_{attacker}_steel'] = 0
            results[f'{attacker}_airvinfra_{attacker}_money'] = results[f'{attacker}_airtoother_{attacker}_avg'] * 4000
            results[f'{attacker}_airvinfra_{attacker}_total'] = results[f'{attacker}_airvinfra_{attacker}_alum'] * 2971 + results[f'{attacker}_airvinfra_{attacker}_steel'] * 3990 + results[f'{attacker}_air_{attacker}_gas'] * 3340 + results[f'{attacker}_air_{attacker}_mun'] * 1960 + results[f'{attacker}_airvinfra_{attacker}_money'] 

            results[f'{attacker}_airvinfra_{defender}_alum'] = results[f'{attacker}_airtoother_{defender}_avg'] * 5
            results[f'{attacker}_airvinfra_{defender}_steel'] = 0
            results[f'{attacker}_airvinfra_{defender}_money'] = results[f'{attacker}_airtoother_{defender}_avg'] * 4000 + results[f'{attacker}_air_{defender}_lost_infra_avg_value']
            results[f'{attacker}_airvinfra_{defender}_total'] = results[f'{attacker}_airvinfra_{defender}_alum'] * 2971 + results[f'{attacker}_airvinfra_{defender}_steel'] * 3990 + results[f'{attacker}_air_{defender}_gas'] * 3340 + results[f'{attacker}_air_{defender}_mun'] * 1960 + results[f'{attacker}_airvinfra_{defender}_money'] 
            results[f'{attacker}_airvinfra_net'] = results[f'{attacker}_airvinfra_{defender}_total'] - results[f'{attacker}_airvinfra_{attacker}_total']


            results[f'{attacker}_airvsoldiers_{attacker}_alum'] = results[f'{attacker}_airtoother_{attacker}_avg'] * 5
            results[f'{attacker}_airvsoldiers_{attacker}_steel'] = 0
            results[f'{attacker}_airvsoldiers_{attacker}_money'] = results[f'{attacker}_airtoother_{attacker}_avg'] * 4000
            results[f'{attacker}_airvsoldiers_{attacker}_total'] = results[f'{attacker}_airvsoldiers_{attacker}_alum'] * 2971 + results[f'{attacker}_airvsoldiers_{attacker}_steel'] * 3990 + results[f'{attacker}_air_{attacker}_gas'] * 3340 + results[f'{attacker}_air_{attacker}_mun'] * 1960 + results[f'{attacker}_airvsoldiers_{attacker}_money'] 
            
            results[f'{attacker}_airvsoldiers_{defender}_alum'] = results[f'{attacker}_airtoother_{defender}_avg'] * 5
            results[f'{attacker}_airvsoldiers_{defender}_steel'] = 0
            results[f'{attacker}_airvsoldiers_{defender}_money'] = results[f'{attacker}_airtoother_{defender}_avg'] * 4000 + results[f'{attacker}_air_{defender}_lost_infra_avg_value'] * 1/3 + results[f'{attacker}_air_{defender}_soldiers_destroyed_avg'] * 5
            results[f'{attacker}_airvsoldiers_{defender}_total'] = results[f'{attacker}_airvsoldiers_{defender}_alum'] * 2971 + results[f'{attacker}_airvsoldiers_{defender}_steel'] * 3990 + results[f'{attacker}_air_{defender}_gas'] * 3340 + results[f'{attacker}_air_{defender}_mun'] * 1960 + results[f'{attacker}_airvsoldiers_{defender}_money'] 
            results[f'{attacker}_airvsoldiers_net'] = results[f'{attacker}_airvair_{defender}_total'] - results[f'{attacker}_airvsoldiers_{attacker}_total']


            results[f'{attacker}_airvtanks_{attacker}_alum'] = results[f'{attacker}_airtoother_{attacker}_avg'] * 5
            results[f'{attacker}_airvtanks_{attacker}_steel'] = 0
            results[f'{attacker}_airvtanks_{attacker}_money'] = results[f'{attacker}_airtoother_{attacker}_avg'] * 4000
            results[f'{attacker}_airvtanks_{attacker}_total'] = results[f'{attacker}_airvtanks_{attacker}_alum'] * 2971 + results[f'{attacker}_airvtanks_{attacker}_steel'] * 3990 + results[f'{attacker}_air_{attacker}_gas'] * 3340 + results[f'{attacker}_air_{attacker}_mun'] * 1960 + results[f'{attacker}_airvtanks_{attacker}_money'] 
            
            results[f'{attacker}_airvtanks_{defender}_alum'] = results[f'{attacker}_airtoother_{defender}_avg'] * 5
            results[f'{attacker}_airvtanks_{defender}_steel'] = results[f'{attacker}_air_{defender}_tanks_destroyed_avg'] * 0.5
            results[f'{attacker}_airvtanks_{defender}_money'] = results[f'{attacker}_airtoother_{defender}_avg'] * 4000 + results[f'{attacker}_air_{defender}_lost_infra_avg_value'] * 1/3 + results[f'{attacker}_air_{defender}_tanks_destroyed_avg'] * 60
            results[f'{attacker}_airvtanks_{defender}_total'] = results[f'{attacker}_airvtanks_{defender}_alum'] * 2971 + results[f'{attacker}_airvtanks_{defender}_steel'] * 3990 + results[f'{attacker}_air_{defender}_gas'] * 3340 + results[f'{attacker}_air_{defender}_mun'] * 1960 + results[f'{attacker}_airvtanks_{defender}_money'] 
            results[f'{attacker}_airvtanks_net'] = results[f'{attacker}_airvtanks_{defender}_total'] - results[f'{attacker}_airvtanks_{attacker}_total']


            results[f'{attacker}_airvships_{attacker}_alum'] = results[f'{attacker}_airtoother_{attacker}_avg'] * 5
            results[f'{attacker}_airvships_{attacker}_steel'] = 0
            results[f'{attacker}_airvships_{attacker}_money'] = results[f'{attacker}_airtoother_{attacker}_avg'] * 4000
            results[f'{attacker}_airvships_{attacker}_total'] = results[f'{attacker}_airvships_{attacker}_alum'] * 2971 + results[f'{attacker}_airvships_{attacker}_steel'] * 3990 + results[f'{attacker}_air_{attacker}_gas'] * 3340 + results[f'{attacker}_air_{attacker}_mun'] * 1960 + results[f'{attacker}_airvships_{attacker}_money'] 
            
            results[f'{attacker}_airvships_{defender}_alum'] = results[f'{attacker}_airtoother_{defender}_avg'] * 5
            results[f'{attacker}_airvships_{defender}_steel'] = results[f'{attacker}_air_{defender}_ships_destroyed_avg'] * 30
            results[f'{attacker}_airvships_{defender}_money'] = results[f'{attacker}_airtoother_{defender}_avg'] * 4000 + results[f'{attacker}_air_{defender}_lost_infra_avg_value'] * 1/3 + results[f'{attacker}_air_{defender}_ships_destroyed_avg'] * 50000
            results[f'{attacker}_airvships_{defender}_total'] = results[f'{attacker}_airvships_{defender}_alum'] * 2971 + results[f'{attacker}_airvships_{defender}_steel'] * 3990 + results[f'{attacker}_air_{defender}_gas'] * 3340 + results[f'{attacker}_air_{defender}_mun'] * 1960 + results[f'{attacker}_airvships_{defender}_money'] 
            results[f'{attacker}_airvships_net'] = results[f'{attacker}_airvships_{defender}_total'] - results[f'{attacker}_airvships_{attacker}_total']


            results[f'{attacker}_naval_{attacker}_mun'] = results[f'{attacker}']['ships'] * 3
            results[f'{attacker}_naval_{attacker}_gas'] = results[f'{attacker}']['ships'] * 2
            results[f'{attacker}_naval_{attacker}_alum'] = 0
            results[f'{attacker}_naval_{attacker}_steel'] = results[f'{attacker}_naval_{attacker}_avg'] * 30
            results[f'{attacker}_naval_{attacker}_money'] = results[f'{attacker}_naval_{attacker}_avg'] * 50000
            results[f'{attacker}_naval_{attacker}_total'] = results[f'{attacker}_naval_{attacker}_alum'] * 2971 + results[f'{attacker}_naval_{attacker}_steel'] * 3990 + results[f'{attacker}_naval_{attacker}_gas'] * 3340 + results[f'{attacker}_naval_{attacker}_mun'] * 1960 + results[f'{attacker}_naval_{attacker}_money'] 
           
            base_mun = results[f'{defender}']['ships'] * 3 * def_rss_consumption(results[f'{attacker}_air_win_rate'])
            results[f'{attacker}_naval_{defender}_mun'] = results[f'{attacker}_naval_{defender}_mun'] = (base_mun * (1 - results[f'{attacker}_naval_fail']) + min(base_gas, results[f'{attacker}_naval_{attacker}_mun']) * results[f'{attacker}_naval_fail'])
            base_gas = results[f'{defender}']['ships'] * 2 * def_rss_consumption(results[f'{attacker}_air_win_rate'])
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

def setup(bot):
    bot.add_cog(TargetFinding(bot))