import os
from discord.ext import commands
import discord
from datetime import datetime, timedelta
import pathlib
import math
import json
import re
from discord.commands import slash_command, Option, SlashCommandGroup, permissions
import dload
from csv import DictReader
import utils
import queries

from main import async_mongo, logger

api_key = os.getenv("api_key")

class Background(commands.Cog):

    def __init__(self, bot):
        self.bot: discord.Bot = bot

    @slash_command(
        name="who",
        description="Get more information about someone's nation"
    )
    async def who(
        self,
        ctx: discord.ApplicationContext,
        person: Option(str, "") = None,
    ):
        try:
            await ctx.defer()
            if person == None:
                person = ctx.author.id
            nation = await utils.find_nation_plus(self, person)
            if nation == None:
                await ctx.respond(content="I did not find that nation!")
                return

            nation = (await utils.call(f"{{nations(first:1 id:{nation['id']}){{data{utils.get_query(queries.WHO)}}}}}"))['data']['nations']['data'][0]

            embed = discord.Embed(title=nation['nation_name'], url=f"https://politicsandwar.com/nation/id={nation['id']}", color=0xff5100)
            user = await utils.find_user(self, nation['id'])
            if not user:
                discord_info = "> Autolycus Verified: <:redcross:862669500977905694>"
                if nation['discord']:
                    discord_info += f"\n> Discord Username: {nation['discord']}"
            else:
                username = await self.bot.fetch_user(user['user'])
                discord_info = f"> Autolycus Verified: ✅\n> Discord Username: {username} `({username.id})`"
            embed.add_field(name="Discord Info", value=discord_info, inline=False)

            nation_info = f"> Nation Name: [{nation['nation_name']}](https://politicsandwar.com/nation/id={nation['id']})\n> Leader Name: {nation['leader_name']}\n> Cities: [{nation['num_cities']}](https://politicsandwar.com/city/manager/n={nation['nation_name'].replace(' ', '%20')})\n> War Policy: [{nation['warpolicy']}](https://politicsandwar.com/pwpedia/war-policy/)\n> Dom. Policy: [{nation['dompolicy']}](https://politicsandwar.com/pwpedia/domestic-policy/)"
            embed.add_field(name="Nation Info", value=nation_info)

            nation_info_2 = f"> Score: `{nation['score']}`\n> Def. Range: `{round(nation['score']/1.75)}`-`{round(nation['score']/0.75)}`\n> Off. Range: `{round(nation['score']*0.75)}`-`{round(nation['score']*1.75)}`\n> Color: [{nation['color'].capitalize()}](https://politicsandwar.com/leaderboards/display=color)\n> Turns of VM: `{nation['vmode']}`"
            embed.add_field(name="\u200b", value=nation_info_2)

            if nation['alliance']:
                members = len([temp for temp in nation['alliance']['nations'] if temp['alliance_position'] != "APPLICANT"])
                alliance_info = f"> Alliance: [{nation['alliance']['name']}](https://politicsandwar.com/alliance/id={nation['alliance']['id']})\n> Position: {nation['alliance_position'].capitalize()}\n> Seniority: {nation['alliance_seniority']:,} days\n> Score: `{nation['alliance']['score']:,}`\n> Color: [{nation['alliance']['color'].capitalize()}](https://politicsandwar.com/leaderboards/display=color)\n> Members: `{members}`"
            else:
                alliance_info = f"> Alliance: None"
            embed.add_field(name="Alliance Info", value=alliance_info, inline=False)

            milt = utils.militarization_checker(nation)
            military_info = "> Format: \u200b \u200b \u200b`" + "Current".center(9) + "` `" + "Cap".center(9) + "` `" + "Daily".center(7) + "`\n> Soldiers: \u200a\u200b\u200a`" + f"{nation['soldiers']:,.0f}".rjust(9) + "` `" + f"{milt['max_soldiers']:,.0f}".rjust(9) + "` `" + f"{milt['soldiers_daily']:,.0f}".rjust(7) + "`\n> Tanks: \u200a \u200a \u200a \u200a \u200b`" + f"{nation['tanks']:,.0f}".rjust(9) + "` `" + f"{milt['max_tanks']:,.0f}".rjust(9) + "` `" + f"{milt['tanks_daily']:,.0f}".rjust(7) + "`\n> Aircraft: \u200b \u200b`" + f"{nation['aircraft']:,.0f}".rjust(9) + "` `" + f"{milt['max_aircraft']:,.0f}".rjust(9) + "` `" + f"{milt['aircraft_daily']:,.0f}".rjust(7) + "`\n> Ships:\u200a \u200a \u200a \u200a \u200a \u200a`" + f"{nation['ships']:,.0f}".rjust(9) + "` `" + f"{milt['max_ships']:,.0f}".rjust(9) + "` `" + f"{milt['ships_daily']:,.0f}".rjust(7) + f"`\n> \n> MMR: `{milt['barracks_mmr']}`/`{milt['factory_mmr']}`/`{milt['hangar_mmr']}`/`{milt['drydock_mmr']}`"
            print(military_info)
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
            
            if nation['pirate_economy']:
                max_offense = 6
            if nation['advanced_pirate_economy']:
                max_offense = 7
            else:
                max_offense = 5

            military_info_2 = f"> Offensive Wars: `{o_wars}`/`{max_offense}`\n> Defensive Wars: `{d_wars}`/`3`\n> Missiles: `{missiles}`\n> Nukes: `{nukes}`\n> Iron Dome: {dome}\n> Vital Defense: {vital}\n> Turns of Beige: `{nation['beige_turns']}`"
            embed.add_field(name="\u200b", value=military_info_2, inline=True)

            embed.set_footer(text="Contact RandomNoobster#0093 for help or bug reports")

            await ctx.respond(embed=embed)
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    @slash_command(
        name="builds",
        description="Shows you the best city builds"
    )
    async def build(
        self,
        ctx: discord.ApplicationContext,
        infra: Option(str, "How much infra the builds should be for"),
        land: Option(str, "How much land the builds should be for"),
        mmr: Option(str, "The minimum military requirement for the builds. Defaults to 0/0/0/0.") = "0/0/0/0",
        person: Option(str, "The person the builds should be for. Defaults to you.") = None
    ):
        try:
            await ctx.respond("Let me think a bit...")

            now = datetime.now()
            yesterday = now + timedelta(days=-1)
            date = yesterday.strftime("%Y-%m-%d")
            if os.path.isfile(pathlib.Path.cwd() / 'data' / 'dumps' / f'cities-{date}.csv'):
                #print('That file already exists')
                pass
            else:
                dload.save_unzip(f"https://politicsandwar.com/data/cities/cities-{date}.csv.zip", str(pathlib.Path.cwd() / 'data' / 'dumps'), True)
            
            if person == None:
                person = ctx.author.id
            db_nation = await utils.find_nation_plus(self, person)
            if not db_nation:
                await ctx.edit(content="I could not find the specified person!")
                return

            nation = (await utils.call(f"{{nations(first:1 id:{db_nation['id']}){{data{utils.get_query(queries.REVENUE)}}}}}"))['data']['nations']['data']
            if len(nation) == 0:
                await ctx.edit(content="That person was not in the API!")
                return
            else:
                nation = nation[0]
            
            infra = utils.str_to_int(infra)
            
            if infra % 50 != 0:
                await ctx.edit(content="The amount of infra must be a multiple of 50!")
                return

            land = utils.str_to_int(land)
            
            try:
                if mmr.lower() == "any":
                    pass
                else:
                    mmr = re.sub("[^0-9]", "", mmr)
                    min_bar = int(mmr[0])
                    min_fac = int(mmr[1])
                    min_han = int(mmr[2])
                    min_dry = int(mmr[3])
            except:
                await ctx.edit(content="I did not understand that mmr, please try again!")
                return

            max_recycling = 3 + int(nation['recycling_initiative'])
            max_hospital = 5 + int(nation['clinical_research_center'])
            max_police = 4 + int(nation['specialized_police_training_program'])

            to_scan = []
            rss = []
            all_rss = ['net income', 'aluminum', 'bauxite', 'coal', 'food', 'gasoline', 'iron', 'lead', 'money', 'munitions', 'oil', 'steel', 'uranium']
            if nation['continent'] == "af":
                cont_rss = ['coal_mines', 'iron_mines', 'lead_mines']
                cont_rss_2 = ['coalmine', 'ironmine', 'leadmine']
                rss = [rs for rs in all_rss if rs + "_mines" not in cont_rss and rs + "_wells" not in cont_rss]
            elif nation['continent'] == "as":
                cont_rss = ['coal_mines', 'bauxite_mines', 'lead_mines']
                cont_rss_2 = ['coalmine', 'bauxitemine', 'leadmine']
                rss = [rs for rs in all_rss if rs + "_mines" not in cont_rss and rs + "_wells" not in cont_rss]
            elif nation['continent'] == "au":
                cont_rss = ['oil_wells', 'iron_mines', 'uranium_mines']
                cont_rss_2 = ['oilwell', 'ironmine', 'uramine']
                rss = [rs for rs in all_rss if rs + "_mines" not in cont_rss and rs + "_wells" not in cont_rss]
            elif nation['continent'] == "an":
                cont_rss = ['oil_wells', 'coal_mines', 'uranium_mines']
                cont_rss_2 = ['oilwell', 'coalmine', 'uramine']
                rss = [rs for rs in all_rss if rs + "_mines" not in cont_rss and rs + "_wells" not in cont_rss]
            elif nation['continent'] == "eu":
                cont_rss = ['oil_wells', 'bauxite_mines', 'uranium_mines']
                cont_rss_2 = ['oilwell', 'bauxitemine', 'uramine']
                rss = [rs for rs in all_rss if rs + "_mines" not in cont_rss and rs + "_wells" not in cont_rss]
            elif nation['continent'] == "na":
                cont_rss = ['oil_wells', 'bauxite_mines', 'lead_mines']
                cont_rss_2 = ['oilwell', 'bauxitemine', 'leadmine']
                rss = [rs for rs in all_rss if rs + "_mines" not in cont_rss and rs + "_wells" not in cont_rss]
            elif nation['continent'] == "sa":
                cont_rss = ['coal_mines', 'iron_mines', 'uranium_mines']
                cont_rss_2 = ['coalmine', 'ironmine', 'uramine']
                rss = [rs for rs in all_rss if rs + "_mines" not in cont_rss and rs + "_wells" not in cont_rss]

            await ctx.edit(content="Scanning cities...")

            with open(pathlib.Path.cwd() / 'data' / 'dumps' / f'cities-{date}.csv', encoding='cp437') as f1:
                csv_dict_reader = DictReader(f1)
                nation_age = nation['date'][:nation['date'].index("T")]
                for city in csv_dict_reader:
                    if float(city['infrastructure']) != float(infra):
                        continue
                    if int(infra) / 50 < int(city['oil_power_plants']) + int(city['nuclear_power_plants']) + int(city['wind_power_plants']) + int(city['coal_power_plants']) + int(city['coal_mines']) + int(city['oil_wells']) + int(city['uranium_mines']) + int(city['iron_mines']) + int(city['lead_mines']) + int(city['bauxite_mines']) + int(city['farms']) + int(city['police_stations']) + int(city['hospitals']) + int(city['recycling_centers']) + int(city['subway']) + int(city['supermarkets']) + int(city['banks']) + int(city['shopping_malls']) + int(city['stadiums']) + int(city['oil_refineries']) + int(city['aluminum_refineries']) + int(city['steel_mills']) + int(city['munitions_factories']) + int(city['barracks']) + int(city['factories']) + int(city['hangars']) + int(city['drydocks']):
                        continue
                    if str(mmr).lower() not in "any":
                        if int(city['barracks']) < min_bar:
                            continue
                        if int(city['factories']) < min_fac:
                            continue
                        if int(city['hangars']) < min_han:
                            continue
                        if int(city['drydocks']) < min_dry:
                            continue
                    
                    skip = False
                    for mine in cont_rss:
                        if int(city[mine]) > 0:
                            skip = True
                            break
                    if skip:
                        continue

                    if int(city['hospitals']) > max_hospital:
                        continue
                    if int(city['police_stations']) > max_police:
                        continue
                    if int(city['recycling_centers']) > max_recycling:
                        continue

                    city.pop('\u2229\u2557\u2510city_id')
                    city.pop('nation_id')
                    city.pop('date_created')
                    city.pop('name')
                    city.pop('capital')
                    city.pop('maxinfra')
                    city.pop('last_nuke_date')

                    city['powered'] = "am powered" #must be string to work when being in the webpage
                    city['land'] = land
                    city['date'] = nation_age
                    city['infrastructure'] = round(float(city['infrastructure']))
                    city['oilpower'] = int(city.pop('oil_power_plants'))
                    city['windpower'] = int(city.pop('wind_power_plants'))
                    city['coalpower'] = int(city.pop('coal_power_plants'))
                    city['nuclearpower'] = int(city.pop('nuclear_power_plants'))
                    city['coalmine'] = int(city.pop('coal_mines'))
                    city['oilwell'] = int(city.pop('oil_wells'))
                    city['uramine'] = int(city.pop('uranium_mines'))
                    city['barracks'] = int(city.pop('barracks'))
                    city['farm'] = int(city.pop('farms'))
                    city['policestation'] = int(city.pop('police_stations'))
                    city['hospital'] = int(city.pop('hospitals'))
                    city['recyclingcenter'] = int(city.pop('recycling_centers'))
                    city['subway'] = int(city.pop('subway'))
                    city['supermarket'] = int(city.pop('supermarkets'))
                    city['bank'] = int(city.pop('banks'))
                    city['mall'] = int(city.pop('shopping_malls'))
                    city['stadium'] = int(city.pop('stadiums'))
                    city['leadmine'] = int(city.pop('lead_mines'))
                    city['ironmine'] = int(city.pop('iron_mines'))
                    city['bauxitemine'] = int(city.pop('bauxite_mines'))
                    city['gasrefinery'] = int(city.pop('oil_refineries'))
                    city['aluminumrefinery'] = int(city.pop('aluminum_refineries'))
                    city['steelmill'] = int(city.pop('steel_mills'))
                    city['munitionsfactory'] = int(city.pop('munitions_factories'))
                    city['factory'] = int(city.pop('factories'))
                    city['airforcebase'] = int(city.pop('hangars'))
                    city['drydock'] = int(city.pop('drydocks'))

                    to_scan.append(city)

            try:
                with open(pathlib.Path.cwd() / 'data' / 'builds' / f'{infra}.json') as f1:
                    file_builds = json.load(f1)
                    for city in file_builds:
                        if str(mmr).lower() not in "any":
                            if city['barracks'] < min_bar:
                                continue
                            if city['factory'] < min_fac:
                                continue
                            if city['airforcebase'] < min_han:
                                continue
                            if city['drydock'] < min_dry:
                                continue
                        
                        skip = False
                        for mine in cont_rss_2:
                            if city[mine] > 0:
                                skip = True
                                break
                        if skip:
                            continue

                        if city['hospital'] > max_hospital:
                            continue
                        if city['policestation'] > max_police:
                            continue
                        if city['recyclingcenter'] > max_recycling:
                            continue
                        
                        city['powered'] = "am powered" #must be string to work when being in the webpage
                        city['land'] = land
                        city['date'] = nation_age

                        to_scan.append(city)
            except:
                pass
                
            temp, colors, prices, treasures, radiation, seasonal_mod = await utils.pre_revenue_calc(ctx, query_for_nation=False, parsed_nation=nation)

            cities = []
            for city in to_scan:
                nation['cities'] = [city]
                cities.append(await utils.revenue_calc(ctx, nation, radiation, treasures, prices, colors, seasonal_mod, single_city=True))

            if len(cities) == 0:
                await ctx.edit(content="No active builds matched your criteria <:derp:846795730210783233>")
                return

            unique_builds = [dict(t) for t in {tuple(d.items()) for d in cities}]
            unique_builds = sorted(unique_builds, key=lambda k: k['net income'], reverse=True)
                            
            builds = {}
            top_builds = []
            for rs in rss:
                sorted_builds = sorted(unique_builds, key=lambda k: k[rs], reverse=True)
                best_builds = [city for city in sorted_builds if city[rs] == sorted_builds[0][rs]]
                top_builds += best_builds[0:20]
                builds[rs] = sorted(best_builds, key=lambda k: k['net income'], reverse=True)[0]
                builds[rs]['template'] = f"""
    {{
        "infra_needed": {builds[rs]['infrastructure']},
        "imp_total": {math.floor(float(builds[rs]['infrastructure'])/50)},
        "imp_coalpower": {builds[rs]['coalpower']},
        "imp_oilpower": {builds[rs]['oilpower']},
        "imp_windpower": {builds[rs]['windpower']},
        "imp_nuclearpower": {builds[rs]['nuclearpower']},
        "imp_coalmine": {builds[rs]['coalmine']},
        "imp_oilwell": {builds[rs]['oilwell']},
        "imp_uramine": {builds[rs]['uramine']},
        "imp_leadmine": {builds[rs]['leadmine']},
        "imp_ironmine": {builds[rs]['ironmine']},
        "imp_bauxitemine": {builds[rs]['bauxitemine']},
        "imp_farm": {builds[rs]['farm']},
        "imp_gasrefinery": {builds[rs]['gasrefinery']},
        "imp_aluminumrefinery": {builds[rs]['aluminumrefinery']},
        "imp_munitionsfactory": {builds[rs]['munitionsfactory']},
        "imp_steelmill": {builds[rs]['steelmill']},
        "imp_policestation": {builds[rs]['policestation']},
        "imp_hospital": {builds[rs]['hospital']},
        "imp_recyclingcenter": {builds[rs]['recyclingcenter']},
        "imp_subway": {builds[rs]['subway']},
        "imp_supermarket": {builds[rs]['supermarket']},
        "imp_bank": {builds[rs]['bank']},
        "imp_mall": {builds[rs]['mall']},
        "imp_stadium": {builds[rs]['stadium']},
        "imp_barracks": {builds[rs]['barracks']},
        "imp_factory": {builds[rs]['factory']},
        "imp_hangars": {builds[rs]['airforcebase']},
        "imp_drydock": {builds[rs]['drydock']}
    }}"""
            top_unique_builds = [dict(t) for t in {tuple(d.items()) for d in top_builds}]

            timestamp = round(datetime.utcnow().timestamp())

            await utils.write_web("builds", ctx.author.id, {"builds": builds, "rss": rss, "land": land, "top_unique_builds": top_unique_builds}, timestamp)

            if str(mmr).lower() in "any":
                mmr = "no military requirement"
            else:
                mmr = "a military requirement of " + '/'.join(mmr[i:i+1] for i in range(0, len(mmr), 1))
            await ctx.edit(content=f"{len(cities):,} valid cities and {len(unique_builds):,} unique builds fulfilled your criteria of {infra} infra and {mmr}.\n\nSee the best builds here (assuming you have {land} land): http://132.145.71.195:5000/builds/{ctx.author.id}/{timestamp}")
            return
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    revenue_group = SlashCommandGroup("revenue", "Revenue calculators.")
    
    @revenue_group.command(
        name="nation",
        description="The revenue of a nation"
    )
    async def nation_revenue(
        self,
        ctx: discord.ApplicationContext,
        person: Option(str, "The person you want to see the revenue of. Defaults to you.") = None
    ):
        try:
            await ctx.respond('Stay with me...')
            if person == None:
                person = ctx.author.id
            db_nation = await utils.find_user(self, person)

            if not db_nation:
                db_nation = await utils.find_nation(person)
                if not db_nation:
                    await ctx.edit(content='I could not find that person!')
                    return
                db_nation['nationid'] = db_nation['id']

            nation, colors, prices, treasures, radiation, seasonal_mod = await utils.pre_revenue_calc(ctx, query_for_nation=True, nationid=db_nation['id'])

            build_txt = "daily revenue"
            single_city = False

            rev_obj = await utils.revenue_calc(ctx, nation, radiation, treasures, prices, colors, seasonal_mod, None, single_city, True)

            embed = discord.Embed(
                title=f"{nation['leader_name']}'s {build_txt}:", url=f"https://politicsandwar.com/nation/id={db_nation['id']}", description="", color=0xff5100)
            
            embed.add_field(name="Incomes", value=rev_obj['income_txt'])
            embed.add_field(name="Expenses", value=rev_obj['expenses_txt'])
            embed.add_field(name="Net Revenue", value=rev_obj['net_rev_txt'])
            embed.add_field(name="Monetary Net Income", inline=False, value=rev_obj['mon_net_txt'])
            embed.set_footer(text=rev_obj['footer'])

            await ctx.edit(content="", embed=embed)
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
    
    @revenue_group.command(
        name="alliance",
        description="The revenue of an alliance"
    )
    async def alliance_revenue(
        self,
        ctx: discord.ApplicationContext,
        alliance: Option(str, "The alliance you want to see the revenue of.", autocomplete=utils.get_alliances),
        include_grey: Option(bool, "Do you want to include gray nations? Defaults to no.") = False
    ):
        try:
            await ctx.defer()

            alliance_id = None
            for aa in await utils.listify(async_mongo.alliances.find({})):
                if alliance == f"{aa['name']} ({aa['id']})":
                    alliance_id = aa['id']
                    break
                elif alliance == aa['id']:
                    alliance_id = aa['id']
                    break
                elif alliance == aa['name']:
                    alliance_id = aa['id']
                    break
                elif alliance == aa['acronym']:
                    alliance_id = aa['id']
                    break
                                
            if alliance_id is None:
                await ctx.respond(f"I could not find a match to `{alliance}` in the database!")
                return

            await ctx.respond('Calling the API...')

            nations = await utils.paginate_call(f"{{nations(alliance_id:{alliance_id} page:page_number alliance_position:[2,3,4,5]){{paginatorInfo{{hasMorePages}} data{utils.get_query(queries.REVENUE)}}}}}", "nations")

            nation, colors, prices, treasures, radiation, seasonal_mod = await utils.pre_revenue_calc(ctx)

            income = {}
            RSS = ['coal', 'oil', 'uranium', 'iron', 'bauxite', 'lead', 'gasoline', 'munitions', 'steel', 'aluminum', 'food', 'net_cash_num', 'monetary_net_num']
            for rs in RSS:
                income[rs] = 0

            for nation in nations:
                if nation['color'] == "gray" and not include_grey:
                    continue
                rev_obj = await utils.revenue_calc(ctx, nation, radiation, treasures, prices, colors, seasonal_mod, None, False, False)
                for rs in RSS:
                    try:
                        income[rs] += rev_obj[rs]
                    except:
                        pass
            
            if len(nations) == 0:
                await ctx.respond(f"They have no valid members!")
                return
                
            embed = discord.Embed(title=f"{nations[0]['alliance']['name']}'s daily revenue:", url=f"https://politicsandwar.com/alliance/id={alliance_id}", description="", color=0xff5100)

            for rs in RSS[:-2]:
                embed.add_field(name=f"{rs.capitalize()}", value=f"{income[rs]:,.2f}\n")
            
            embed.add_field(name="Money", value=f"{income[RSS[-2]]:,.2f}\n")
            embed.add_field(name="Net income", value=f"{income[RSS[-1]]:,.2f}\n")
            
            await ctx.edit(content="", embed=embed)
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    cost_group = SlashCommandGroup("cost", "Various cost calculators.")

    @cost_group.command(
        name="infra",
        description="Cost to purchase infrastructure"
    )
    async def infra_cost(
        self,
        ctx: discord.ApplicationContext,
        starting_infra: Option(str, "The starting amount of infrastructure"),
        ending_infra: Option(str, "The ending amount of infrastructure"),
        person: Option(str, "The person purchasing infra. Defaults to you.") = None
    ):
        try:
            if not person:
                person = ctx.author.id
            db_person = await utils.find_nation_plus(self, person)
            if not db_person:
                await ctx.respond("I could not find that person!")
                return
            nation = (await utils.call(f"{{nations(first:1 id:{db_person['id']}){{data{utils.get_query(queries.INFRA_COST)}}}}}"))['data']['nations']['data'][0]

            starting_infra = utils.str_to_int(starting_infra)
            ending_infra = utils.str_to_int(ending_infra)
            
            cost = utils.infra_cost(int(starting_infra), int(ending_infra), nation)

            await ctx.respond(f"For `{db_person['leader_name']}`, going from `{starting_infra}` to `{ending_infra}` infrastructure, will cost `${cost:,.2f}`.")
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    @cost_group.command(
        name="land",
        description="Cost to purchase land."
    )
    async def land_cost(
        self,
        ctx: discord.ApplicationContext,
        starting_land: Option(str, "The starting amount of land."),
        ending_land: Option(str, "The ending amount of land."),
        person: Option(str, "The person purchasing land. Defaults to you.") = None
    ):
        try:
            if not person:
                person = ctx.author.id
            db_person = await utils.find_nation_plus(self, person)
            if not db_person:
                await ctx.respond("I could not find that person!")
                return
            nation = (await utils.call(f"{{nations(first:1 id:{db_person['id']}){{data{utils.get_query(queries.LAND_COST)}}}}}"))['data']['nations']['data'][0]

            starting_land = utils.str_to_int(starting_land)
            ending_land = utils.str_to_int(ending_land)

            cost = utils.land_cost(int(starting_land), int(ending_land), nation)

            await ctx.respond(f"For `{db_person['leader_name']}`, going from `{starting_land}` to `{ending_land}` land will cost `${cost:,.2f}`.")
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    @cost_group.command(
        name="city",
        description="Cost to purchase city."
    )
    async def city_cost(
        self,
        ctx: discord.ApplicationContext,
        city: Option(int, "The city to buy."),
        person: Option(str, "The person purchasing a city. Defaults to you.") = None
    ):
        try:
            await ctx.defer()

            if not person:
                person = ctx.author.id
            db_person = await utils.find_nation_plus(self, person)
            if not db_person:
                await ctx.edit(content="I could not find that person!")
                return

            nation = (await utils.call(f"{{nations(first:1 id:{db_person['id']}){{data{utils.get_query(queries.CITY_COST, {'nations': ['num_cities']})}}}}}"))['data']['nations']['data'][0]
            
            if city < nation["num_cities"]:
                await ctx.edit(content=f"`{db_person['leader_name']}` already has `{city}` cities!")
                return

            cost = utils.city_cost(int(city), nation)

            await ctx.edit(content=f"For `{db_person['leader_name']}`, purchasing city `{city}` will cost `${cost:,.2f}`.")
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
    
    @cost_group.command(
        name="expansion",
        description="Cost to purchase infra, land and cities"
    )
    async def expansion_cost(
        self,
        ctx: discord.ApplicationContext,
        city: Option(int, "The city to expand to."),
        infra: Option(str, "The amount of infrastructure"),
        land: Option(str, "The amount of land"),
        person: Option(str, "The person expanding. Defaults to you.") = None
    ):
        try:
            await ctx.defer()

            if not person:
                person = ctx.author.id
            db_person = await utils.find_nation_plus(self, person)
            if not db_person:
                await ctx.edit(content="I could not find that person!")
                return
            nation = (await utils.call(f"{{nations(first:1 id:{db_person['id']}){{data{utils.get_query(queries.INFRA_COST, queries.LAND_COST, queries.CITY_COST, {'nations': ['num_cities']})}}}}}"))['data']['nations']['data'][0]

            if city < nation["num_cities"]:
                await ctx.edit(content=f"`{db_person['leader_name']}` already has `{city}` cities!")
                return

            infra = utils.str_to_int(infra)
            land = utils.str_to_int(land)
            
            cost = utils.expansion_cost(nation['num_cities'], int(city), infra, land, nation)

            await ctx.edit(content=f"For `{db_person['leader_name']}`, going from city `{nation['num_cities']}` to city `{city}` (with `{infra}` infra and `{land}` land) will cost `${cost:,.2f}`.")   
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
    
    
    @slash_command(
        name="balance",
        description="See your balance with the allliance bank",
    )
    @commands.guild_only()
    async def balance(
        self,
        ctx: discord.ApplicationContext,
        person: Option(str, "The person to check the balance of. Defaults to you.") = None
    ):
        try:
            await ctx.defer()
            prices = await utils.get_prices()

            rss = utils.RSS.copy()
            rss.remove('credits')

            def total_bal(k):
                nonlocal prices
                x = 0
                for rs in rss:
                    x += k[rs] * prices[rs]
                return x
            
            if not person:
                person = await utils.find_nation_plus(self, ctx.author.id)

            elif person.lower() in ['top', 'max', 'min', 'low', 'high']:
                reverse = True
                name = 'highest'
                if person in ['min', 'low']:
                    reverse = False
                    name = 'lowest'
                
                people = await utils.listify(async_mongo.balance.find({"guild_id": ctx.guild.id}))

                people = sorted(people, key=lambda k: total_bal(k), reverse=reverse)
                embed = discord.Embed(title=f"The {name} balances:", description="", color=0xff5100)

                n = 0
                for ind in people:
                    if n == 10:
                        break
                    user = await async_mongo.world_nations.find_one({"id": ind['nation_id']})
                    if user == None:
                        continue
                    embed.add_field(name=user['leader_name'], inline=False, value=f"Cumulative balance: ${round(total_bal(ind)):,}")
                    n += 1
                await ctx.edit(embed=embed, content='')
                return
            else:
                person = await utils.find_nation_plus(self, person)

            if not person:
                await ctx.edit(content='I could not find that person, please try again.', embed=None)
                return
            
            bal = await async_mongo.balance.find_one({"guild_id": ctx.guild.id, "nation_id": person['id']})
            if not bal:
                await ctx.edit(content='I was not able to find their balance.', embed=None)
                return
            
            bal_embed = discord.Embed(title=f"{person['leader_name']}'s balance", description="", color=0xff5100)

            for rs in rss:
                amount = bal[rs]
                bal_embed.add_field(name=rs.capitalize(), value=f"{round(amount):,}")

            bal_embed.add_field(name="Converted total", value=f"{round(total_bal(bal)):,}",inline=False)
            await ctx.edit(content='', embed=bal_embed)

        except Exception as e:
            logger.error(e, exc_info=True)
            raise e


    @slash_command(
        name="request",
        description="Request resorces from the allliance bank",
    )
    @commands.guild_only()
    async def request(
        self,
        ctx: discord.ApplicationContext,
        reason: Option(str, "The reason for the request."),
        aluminum: Option(str, "The amount of aluminum you want to request.")="0",
        bauxite: Option(str, "The amount of bauxite you want to request.")="0",
        coal: Option(str, "The amount of coal you want to request.")="0",
        food: Option(str, "The amount of food you want to request.")="0",
        gasoline: Option(str, "The amount of gasoline you want to request.")="0",
        iron: Option(str, "The amount of iron you want to request.")="0",
        lead: Option(str, "The amount of lead you want to request.")="0",
        money: Option(str, "The amount of money you want to request.")="0",
        munitions: Option(str, "The amount of munitions you want to request.")="0",
        oil: Option(str, "The amount of oil you want to request.")="0",
        steel: Option(str, "The amount of steel you want to request.")="0",
        uranium: Option(str, "The amount of uranium you want to request.")="0"
    ):
        await ctx.defer()

        try:
            author = ctx.author.id
            person = await utils.find_nation_plus(self, ctx.author.id)
            if person == None:
                await ctx.edit(content="I was unable to find your nation!")
                return
            
            guild_config = await async_mongo.guild_configs.find_one({"guild_id": ctx.guild.id})

            if guild_config == None:
                await ctx.edit(content="This server does not have a transaction key set! Someone with the `Manage Server` permission can set one with `/config transactions`")
                return
            elif "transactions_api_keys" not in guild_config:
                await ctx.edit(content="This server does not have a transaction key set! Someone with the `Manage Server` permission can set one with `/config transactions`")
                return
            elif len(guild_config["transactions_api_keys"]) == 0:
                await ctx.edit(content="This server does not have a transaction key set! Someone with the `Manage Server` permission can set one with `/config transactions`")
                return
            elif not guild_config['transactions_banker_role']:
                await ctx.edit(content="This server does not have a banker role set! Someone with the `Manage Server` permission can set one with `/config transactions`")
                return
            else:
                keys = guild_config["transactions_api_keys"]
                guild = self.bot.get_guild(ctx.guild.id)
                banker_role = guild.get_role(guild_config['transactions_banker_role'])
                if not banker_role:
                    await ctx.edit(content="This server does not have a valid banker role set! Someone with the `Manage Server` permission can set one with `/config transactions`")
                    return
            
            resource_list = [(utils.str_to_int(aluminum), "aluminum"), (utils.str_to_int(bauxite), "bauxite"), (utils.str_to_int(coal), "coal"), (utils.str_to_int(food), "food"), (utils.str_to_int(gasoline), "gasoline"), (utils.str_to_int(iron), "iron"), (utils.str_to_int(lead), "lead"), (utils.str_to_int(money), "money"), (utils.str_to_int(munitions), "munitions"), (utils.str_to_int(oil), "oil"), (utils.str_to_int(steel), "steel"), (utils.str_to_int(uranium), "uranium")]
            
            something = False
            for amount, name in resource_list:
                if amount in [0, "0"]:
                    continue
                else:
                    something = True
            
            if not something:
                await ctx.edit(content="You did not request anything!")
                return

            withdraw_data = {
                "money": '0',
                "food": '0',
                "coal": '0',
                "oil": '0',
                "uranium": '0',
                "lead": '0',
                "iron": '0',
                "bauxite": '0',
                "gasoline": '0',
                "munitions": '0',
                "steel": '0',
                "aluminum": '0',
                "receiver_type": '1',
                "receiver": person['id'],
            }

            for x in withdraw_data:
                for amount, name in resource_list:
                    if name == x:
                        withdraw_data[x] = amount
            
            balance_before = await async_mongo.balance.find_one({"nation_id": person['id'], "guild_id": ctx.guild.id})
            if balance_before == None:
                balance_before = {}
                for amount, name in resource_list:
                    balance_before[name] = 0

            balance_after = balance_before.copy()
            for amount, name in resource_list:
                balance_after[name] -= amount
            
            confirmation = None
            interactor = None
            message = None
            api_key = None
            sent_from = None
            keys_info = []

            class yes_or_no(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=None)
                
                @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
                async def callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal confirmation
                    confirmation = True
                    await i.response.edit_message()
                    for x in view.children:
                        x.disabled = True
                    await i.message.edit(view=view)
                    self.stop()
                
                @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
                async def one_two_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal confirmation
                    confirmation = False
                    await i.response.edit_message()
                    for x in view.children:
                        x.disabled = True
                    await i.message.edit(view=view)
                    self.stop()
                
                async def interaction_check(self, i: discord.Interaction)-> bool:
                    if banker_role not in i.user.roles:
                        await i.response.send_message(f"Only people with the banker role ({banker_role.mention}) can approve of transactions!", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
                        return False
                    else:
                        nonlocal interactor, message
                        message = i.message
                        interactor = i.user
                        return True
            
            class Dropdown(discord.ui.Select):
                def __init__(self, bot_: discord.Bot, keys_info, parent):
                    self.bot = bot_
                    options = []
                    self.parent = parent
                    self.key_option_pairs = []
                    self.keys_info = keys_info

                    for key_info in keys_info:
                        new_option = discord.SelectOption(label=f"{key_info['nation']['alliance']['name']} ({key_info['nation']['alliance']['id']}) through {key_info['nation']['nation_name']}", value=key_info['key'], description="Send from this bank")
                        if new_option not in options:
                            options.append(new_option)

                    super().__init__(
                        placeholder="Choose the bank to send from...",
                        min_values=1,
                        max_values=1,
                        options=options,
                    )

                async def callback(self, i: discord.Interaction):
                    nonlocal api_key, sent_from
                    api_key = self.values[0]
                    for x in self.keys_info:
                        if x['key'] == api_key:
                            sent_from = x['nation']['alliance']['name']
                            break
                    await i.response.edit_message()
                    self.parent.stop()

            class DropdownView(discord.ui.View):
                def __init__(self, bot_: discord.Bot, keys_info):
                    super().__init__(timeout=None)
                    self.add_item(Dropdown(bot_, keys_info, self))
                
                @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, disabled=True)
                async def callback(self, b: discord.Button, i: discord.Interaction):
                    pass

                @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, disabled=True)
                async def one_two_callback(self, b: discord.Button, i: discord.Interaction):
                    pass
                    
                async def interaction_check(self, i: discord.Interaction)-> bool:
                    if banker_role not in i.user.roles:
                        await i.response.send_message(f"Only people with the banker role ({banker_role.mention}) can approve of transactions!", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
                        return False
                    else:
                        nonlocal interactor, message
                        message = i.message
                        interactor = i.user
                        return True
                
            bal_embed = discord.Embed(title=f"{ctx.author} made a request", description="", color=0xffb700)    

            balance_before_txt = ""
            transaction_txt = ""
            balance_after_txt = ""

            for value, name in resource_list:
                if value == 0:
                    bold_start = ""
                    bold_end = ""
                else:
                    bold_start = "**"
                    bold_end = "**"
                balance_before_txt += f"{bold_start}{name.capitalize()}: {balance_before[name]:,.0f}{bold_end}\n"
                transaction_txt += f"{bold_start}{name.capitalize()}: {value:,}{bold_end}\n"
                balance_after_txt += f"{bold_start}{name.capitalize()}: {balance_after[name]:,.0f}{bold_end}\n"

            balance_before_txt += f"\n**Total: {await utils.total_value(balance_before):,.0f}**\n\u200b"
            transaction_data = {}
            for value, name in resource_list:
                transaction_data[name] = value
            transaction_txt += f"\n**Total: {await utils.total_value(transaction_data):,.0f}**\n\u200b"
            balance_after_txt += f"\n**Total: {await utils.total_value(balance_after):,.0f}**\n\u200b"

            bal_embed.add_field(name="Balance Before", value=balance_before_txt, inline=True)
            bal_embed.add_field(name="Requested Transaction", value=transaction_txt, inline=True)
            bal_embed.add_field(name="Balance After", value=balance_after_txt, inline=True)
            bal_embed.add_field(name="Reason", value=reason, inline=False)
            bal_embed.add_field(name="Recipient", value=f"[{person['leader_name']} of {person['nation_name']}](https://politicsandwar.com/nation/id={person['id']})", inline=False)
            
            view = yes_or_no()
            await ctx.edit(content=":clock1: Pending approval...", embed=bal_embed, view=view)
            timed_out = await view.wait()
            if timed_out:
                return
            if not confirmation:
                bal_embed.color = 0xff0000
                await message.edit(content=f"<:redcross:862669500977905694> Request was denied by {interactor}", embed=bal_embed)
                return
            author_user = await self.bot.fetch_user(author)

            success = False
            msg_content = ""
            while not success:
                await message.edit(content=msg_content)
                if len(keys) > 1:
                    keys_info = []
                    for key in keys:
                        nation = (await utils.call(utils.get_query(queries.REQUEST), key))['data']['me']
                        keys_info.append(nation)
                    drop_view = DropdownView(self.bot, keys_info)
                    await message.edit(view=drop_view)
                    timed_out = await drop_view.wait()
                    if timed_out:
                        return
                    if not api_key:
                        timestamp = f"<t:{round(datetime.utcnow().timestamp())}:R>"
                        bal_embed.color = 0xff0000
                        await message.edit(content=f"<:redcross:862669500977905694> Request was denied by {interactor.mention} {timestamp}", embed=bal_embed)
                        try: 
                            await author_user.send(f"<:redcross:862669500977905694> Your request was denied by {interactor.mention} {timestamp}", embed=bal_embed)
                        except discord.errors.Forbidden:
                            await message.reply(f"{author_user.mention} I was unable to DM you, but your request was denied!")
                        return
                else:
                    api_key = keys[0]
                
                await message.edit("Performing transaction...")

                timestamp = f"<t:{round(datetime.utcnow().timestamp())}:R>"
                withdraw_data['note'] = f'"Approved by {interactor} via Discord."'
                success = await utils.withdraw(api_key, withdraw_data)  

                if sent_from:
                    sent_from = f":information_source: Sent from {sent_from}"
                else:
                    sent_from = ""
                
                msg_content += f"\n:white_check_mark: Request was approved by {interactor.mention} {timestamp}\n{sent_from}"

                if success:
                    bal_embed.color = 0x2bff00
                    await message.edit(content=msg_content, embed=bal_embed, view=view)
                    try: 
                        await author_user.send(f":white_check_mark: Your request was approved by {interactor.mention} {timestamp}", embed=bal_embed)
                    except discord.errors.Forbidden:
                        await message.reply(f"{author_user.mention} I was unable to DM you, but your request was approved!")
                    return
                else:
                    class RetryView(yes_or_no):
                        @discord.ui.button(label="Retry", style=discord.ButtonStyle.secondary, emoji="<:retry:1115666455443288075>", custom_id="retry")
                        async def retry(self, b: discord.ui.Button, i: discord.Interaction):
                            await i.response.edit_message()
                            self.stop()
                    retry_view = RetryView()
                    retry_view.disable_all_items()
                    retry_view.get_item("retry").disabled = False
                    
                    msg_content += f"\n:warning: This request might have failed. Check this page to be sure: https://politicsandwar.com/nation/id={person['id']}&display=bank"
                    await message.edit(content=msg_content, embed=bal_embed, view=retry_view)
                    
                    timed_out = await retry_view.wait()
                    if timed_out:
                        print("died")
                        return
                    msg_content += "\n\n<:retry:1115666455443288075> Retrying..."

                    try:
                        await author_user.send(f":white_check_mark: Your request was approved by {interactor.mention} {timestamp}\n:warning: This request might have failed. Check this page to be sure: https://politicsandwar.com/nation/id={person['id']}&display=bank", embed=bal_embed)
                    except discord.errors.Forbidden:
                        await message.reply(f"{author_user.mention} I was unable to DM you, but your request was approved! It seems like it failed though, so that sucks.")
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
        
    @slash_command(
        name="move_bank",
        description="Move the alliance bank contents between alliance banks",
        guild_ids=[729979781940248577, 434071714893398016],
    )
    @commands.guild_only()
    @commands.has_any_role(775428212342652938, 747167690275291268)
    async def move_bank(
        self,
        ctx: discord.ApplicationContext,
        aluminum: Option(str, "The amount of aluminum you want to request.")="0",
        bauxite: Option(str, "The amount of bauxite you want to request.")="0",
        coal: Option(str, "The amount of coal you want to request.")="0",
        food: Option(str, "The amount of food you want to request.")="0",
        gasoline: Option(str, "The amount of gasoline you want to request.")="0",
        iron: Option(str, "The amount of iron you want to request.")="0",
        lead: Option(str, "The amount of lead you want to request.")="0",
        money: Option(str, "The amount of money you want to request.")="0",
        munitions: Option(str, "The amount of munitions you want to request.")="0",
        oil: Option(str, "The amount of oil you want to request.")="0",
        steel: Option(str, "The amount of steel you want to request.")="0",
        uranium: Option(str, "The amount of uranium you want to request.")="0"
    ):
        try:
            await ctx.defer()
            guild_config = await async_mongo.guild_configs.find_one({"guild_id": ctx.guild_id})
            guild = self.bot.get_guild(ctx.guild_id)
            banker_role = guild.get_role(guild_config['transactions_banker_role'])
            keys = guild_config["transactions_api_keys"]

            resource_list = [(utils.str_to_int(aluminum), "aluminum"), (utils.str_to_int(bauxite), "bauxite"), (utils.str_to_int(coal), "coal"), (utils.str_to_int(food), "food"), (utils.str_to_int(gasoline), "gasoline"), (utils.str_to_int(iron), "iron"), (utils.str_to_int(lead), "lead"), (utils.str_to_int(money), "money"), (utils.str_to_int(munitions), "munitions"), (utils.str_to_int(oil), "oil"), (utils.str_to_int(steel), "steel"), (utils.str_to_int(uranium), "uranium")]
            
            something = False
            for amount, name in resource_list:
                if amount in [0, "0"]:
                    continue
                else:
                    something = True
            
            if not something:
                # define withdraw_data later on
                pass
            else:
                withdraw_data = {
                    "receiver_type": '2',
                }
                for amount, type in resource_list:
                    withdraw_data[type] = amount

            keys_info = []
            embeds = [discord.Embed(title="Move Alliance Bank", description="Use the dropdown menus to select two banks to send to and from.", color=0xff5100)]
            for key in keys:
                nation = (await utils.call(utils.get_query(queries.REQUEST), key))['data']['me']
                keys_info.append(nation)
                
                if not something:
                    # this is just a temporary definition, since the embed needs the amounts
                    withdraw_data = {
                        "money": nation['nation']['alliance']['money'],
                        "food": nation['nation']['alliance']['food'],
                        "coal": nation['nation']['alliance']['coal'],
                        "oil": nation['nation']['alliance']['oil'],
                        "uranium": nation['nation']['alliance']['uranium'],
                        "lead": nation['nation']['alliance']['lead'],
                        "iron": nation['nation']['alliance']['iron'],
                        "bauxite": nation['nation']['alliance']['bauxite'],
                        "gasoline": nation['nation']['alliance']['gasoline'],
                        "munitions": nation['nation']['alliance']['munitions'],
                        "steel": nation['nation']['alliance']['steel'],
                        "aluminum": nation['nation']['alliance']['aluminum'],
                    }

                embed = discord.Embed(title=f"Send from {nation['nation']['alliance']['name']} ({nation['nation']['alliance']['id']})", description=f"The banker is {nation['nation']['nation_name']}", color=0xff5100)
                n = 0
                for resource in utils.RSS:
                    if resource in nation['nation']['alliance']:
                        if withdraw_data[resource] not in [0, "0"]:
                            highlighting = "autohotkey"                            
                        else:
                            highlighting = "glsl"
                        embed.add_field(name=resource.capitalize(), value=f"```{highlighting}\nCurrent: \u200b \u200b {nation['nation']['alliance'][resource]:,}\nTransfer: \u200b {withdraw_data[resource]:,}\nRemaining: {(nation['nation']['alliance'][resource] - withdraw_data[resource]):,}```")
                        if n % 2 == 0:
                            embed.add_field(name="\u200b", value="\u200b")
                        n += 1
                embeds.append(embed)
            
            async def interaction_check(i: discord.Interaction) -> bool:
                if banker_role not in i.user.roles:
                    await i.response.send_message(f"Only people with the banker role ({banker_role.mention}) can approve of transactions!", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
                    return False
                else:
                    return True
                
            class moveBankView(discord.ui.View):
                def __init__(self):
                    super().__init__()
            
            view = moveBankView()
            view.interaction_check = interaction_check                

            local_api_key = None
            send_to = None
            send_from = None

            class sendToDropdown(discord.ui.Select):
                def __init__(self):
                    options = []
                    self.interaction_check = interaction_check

                    for key_info in keys_info:
                        new_option = discord.SelectOption(label=f"{key_info['nation']['alliance']['name']} ({key_info['nation']['alliance']['id']})", value=key_info['nation']['id'], description="Send to this bank")
                        skip = False
                        for option in options:
                            if option.label == new_option.label:
                                skip = True
                        if skip:
                            continue
                        else:
                            options.append(new_option)
                    
                    self.keys_info = keys_info

                    super().__init__(
                        placeholder="Choose the bank to send to",
                        options=options,
                    )

                async def callback(self, i: discord.Interaction):
                    nonlocal send_to
                    for x in self.keys_info:
                        if x['nation']['id'] == self.values[0]:
                            send_to = x['nation']['alliance']['id']
                            break
                    await i.response.edit_message()
                    if send_to == send_from:
                        await ctx.respond("You can't send to the same bank you're sending from!", ephemeral=True)
                    else:
                        view.stop()


            class sendFromDropdown(discord.ui.Select):
                def __init__(self):
                    options = []
                    self.interaction_check = interaction_check

                    for key_info in keys_info:
                        new_option = discord.SelectOption(label=f"{key_info['nation']['alliance']['name']} ({key_info['nation']['alliance']['id']}) through {key_info['nation']['nation_name']}", value=key_info['key'], description="Send from this bank")
                        options.append(new_option)
                    
                    self.keys_info = keys_info

                    super().__init__(
                        placeholder="Choose the bank to send from",
                        options=options,
                    )

                async def callback(self, i: discord.Interaction):
                    nonlocal send_from, withdraw_data, local_api_key
                    local_api_key = self.values[0]
                    for x in self.keys_info:
                        if x['key'] == self.values[0]:
                            send_from = x['nation']['alliance']['id']
                            if not something:
                                # this is the actual definition of withdraw_data
                                withdraw_data = {
                                    "money": x['nation']['alliance']['money'],
                                    "food": x['nation']['alliance']['food'],
                                    "coal": x['nation']['alliance']['coal'],
                                    "oil": x['nation']['alliance']['oil'],
                                    "uranium": x['nation']['alliance']['uranium'],
                                    "lead": x['nation']['alliance']['lead'],
                                    "iron": x['nation']['alliance']['iron'],
                                    "bauxite": x['nation']['alliance']['bauxite'],
                                    "gasoline": x['nation']['alliance']['gasoline'],
                                    "munitions": x['nation']['alliance']['munitions'],
                                    "steel": x['nation']['alliance']['steel'],
                                    "aluminum": x['nation']['alliance']['aluminum'],
                                    "receiver_type": '2',
                                }
                            break
                    embed = None
                    for y in embeds:
                        if x['nation']['alliance']['id'] in y.title and x['nation']['nation_name'] in y.description:
                            embed = y
                            break
                    await i.response.edit_message(embed=embed)

            view.add_item(sendFromDropdown())
            view.add_item(sendToDropdown())

            await ctx.edit(embed=embeds[0], view=view)

            timed_out = await view.wait()
            if timed_out:
                return
            
            new_view = utils.yes_or_no_view(ctx)
            new_view.interaction_check = interaction_check
            await ctx.edit(content=f"Do you want to continue with this transaction from from {send_from} to {send_to}?", view=new_view)
            await new_view.wait()

            if new_view.result == True:
                await ctx.edit(content="Performing transaction...", view=None)
                withdraw_data['receiver'] = send_to
                success = await utils.withdraw(local_api_key, withdraw_data)  
                if success:
                    extra_text = ""
                    if something:
                        extra_text = "specified "
                    else:
                        extra_text = "entirety of the "
                    await ctx.edit(content=f":white_check_mark: The {extra_text}bank contents were successfully moved from {send_from} to {send_to}!", view=None)
                else:
                    await ctx.edit(content=f":warning: Something might've gone wrong while moving the bank contents from {send_from} to {send_to}!\n\nCheck here to be sure:\n{send_to}'s bank page: <https://politicsandwar.com/alliance/id={send_to}&display=bank>\n{send_from}'s bank page: <https://politicsandwar.com/alliance/id={send_from}&display=bank>", view=None)
            else:
                await ctx.edit(content="<:redcross:862669500977905694> Transaction cancelled!", view=None)

        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    @slash_command(
        name="botinfo",
        description="Information about the bot"
    )
    async def botinfo(self, ctx: discord.ApplicationContext):
        try:
            await ctx.defer()
            content = f"{len(self.bot.users)} people across {len(self.bot.guilds)} servers have access to me, but only {len(await utils.listify(async_mongo.global_users.find({})))} have verified themselves.\n\nHere you can find the:\n> [GitHub Repository](https://github.com/RandomNoobster/Autolycus/tree/oracle)\n> [Invite Link](https://discord.com/api/oauth2/authorize?client_id=946351598223888414&permissions=326417827840&scope=applications.commands%20bot)\n> [Privacy Policy](https://docs.google.com/document/d/1SXfqzBq_UPuJpPyaXjGBE0UFSfplwMIbeSS6pO4e4f8/)\n> [Terms of Service](https://docs.google.com/document/d/1sR398ZaqVb6YId7jKIyx0laTxbA14QP0GnwmjY74yWw/)\n\u200b"
            embed = discord.Embed(title="About me", description=content, color=0xff5100)
            embed.set_footer(text="Contact RandomNoobster#0093 for help or bug reports")
            await ctx.respond(embed=embed)
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    @slash_command(
        name="verify",
        description='Link your nation with your discord account',
    )
    async def verify(
        self,
        ctx: discord.ApplicationContext,
        nation_id: Option(str, "Your nation id or nation link"),
    ):
        try:
            user = await async_mongo.global_users.find_one({"user": ctx.author.id})
            if user != None:
                await ctx.respond("You are already verified!")
                return
            nation_id = re.sub("[^0-9]", "", nation_id)
            res = await utils.call(f'{{nations(first:1 id:{nation_id}){{data{utils.get_query(queries.VERIFY)}}}}}')
            try:
                if res['data']['nations']['data'][0]['discord'] == str(ctx.author):
                    await async_mongo.global_users.insert_one({"user": ctx.author.id, "id": nation_id, "beige_alerts": []})
                    await ctx.respond("You have successfully verified your nation!")
                else:
                    await ctx.respond(f'1. Go to <https://politicsandwar.com/nation/edit/>\n2. Scroll down to where it says "Discord Username"\n3. Type `{ctx.author}` in the adjacent field\n4. Come back to discord\n5. Write `/verify {nation_id}` again')
            except (KeyError, IndexError):
                await ctx.respond(f"I could not find a nation with an id of `{nation_id}`")
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    @slash_command(
        name="unverify",
        description='Unlink your nation from your discord account',
    )
    async def unverify(
        self,
        ctx: discord.ApplicationContext,
    ):
        try:
            user = await async_mongo.global_users.find_one_and_delete({"user": ctx.author.id})
            if user == None:
                await ctx.respond("You are not verified!")
                return
            else:
                await ctx.respond("Your discord account was successfully unlinked from your nation.")
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    @slash_command(
        name="help",
        description="Returns all commands",
    )
    async def help(self, ctx):
        try:
            help_text = ""
            cmds = list(self.bot.application_commands)
            cmds.sort(key=lambda x: f"{x}")
            for command in cmds:
                if not f"`{command}`" in help_text:
                    help_text += f"`{command}` - {command.description}\n"
            help_text += "\nHere you can find the [Privacy Policy](https://docs.google.com/document/d/1SXfqzBq_UPuJpPyaXjGBE0UFSfplwMIbeSS6pO4e4f8/) and [Terms of Service](https://docs.google.com/document/d/1sR398ZaqVb6YId7jKIyx0laTxbA14QP0GnwmjY74yWw/)"
            embed = discord.Embed(title="Command list", description=help_text, color=0xff5100)
            embed.set_footer(text="Contact RandomNoobster#0093 for help or bug reports")
            await ctx.respond(embed=embed)
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

def setup(bot):
    bot.add_cog(Background(bot))