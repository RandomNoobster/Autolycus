import os
from discord.ext import commands
import discord
from datetime import datetime, timedelta
import pathlib
import math
from mako.template import Template
import re
from keep_alive import app
from flask.views import MethodView
from discord.commands import slash_command, Option
import dload
from csv import DictReader
import utils
from main import mongo

api_key = os.getenv("api_key")

class Background(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @slash_command(
        name="who",
        description="Get more information about someone's nation"
    )
    async def who(
        self,
        ctx: discord.ApplicationContext,
        person: Option(str, "") = None,
    ):
        await ctx.defer()
        if person == None:
            person = ctx.author.id
        nation = utils.find_nation_plus(self, person)
        if nation == None:
            await ctx.respond(content="I did not find that nation!")
            return

        nation = (await utils.call(f"{{nations(first:1 id:{nation['id']}){{data{{id nation_name discord leader_name num_cities cia spy_satellite warpolicy population dompolicy flag vmode color beigeturns last_active soldiers tanks aircraft ships nukes missiles mlp nrf vds irond wars{{attid turnsleft}} cities{{barracks factory airforcebase drydock}} score alliance_position alliance_seniority alliance{{name id score color nations{{id}}}}}}}}}}"))['data']['nations']['data'][0]

        embed = discord.Embed(title=nation['nation_name'], url=f"https://politicsandwar.com/nation/id={nation['id']}", color=0xff5100)
        user = utils.find_user(self, nation['id'])
        if not user:
            discord_info = "> Autolycus Verified: <:redcross:862669500977905694>"
            if nation['discord']:
                discord_info += f"\n> Discord Username: {nation['discord']}"
        else:
            username = await self.bot.fetch_user(user['user'])
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
        await ctx.respond("Let me think a bit...")

        now = datetime.now()
        yesterday = now + timedelta(days=-1)
        date = yesterday.strftime("%Y-%m-%d")
        if os.path.isfile(pathlib.Path.cwd() / 'data' / f'cities-{date}.csv'):
            #print('That file already exists')
            pass
        else:
            dload.save_unzip(f"https://politicsandwar.com/data/cities/cities-{date}.csv.zip", str(
                pathlib.Path.cwd() / 'data'), True)
        
        if person == None:
            person = ctx.author.id
        db_nation = utils.find_nation_plus(self, person)
        if not db_nation:
            await ctx.edit(content="I could not find the specified person!")
            return

        nation = (await utils.call(f"{{nations(first:1 id:{db_nation['id']}){{data{{id continent date color dompolicy alliance{{name}} alliance_id num_cities ironw bauxitew armss egr massirr itc recycling_initiative telecom_satellite green_tech clinical_research_center specialized_police_training uap}}}}}}"))['data']['nations']['data']
        if len(nation) == 0:
            await ctx.edit(content="That person was not in the API!")
            return
        else:
            nation = nation[0]
        
        infra = utils.str_to_int(infra)
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

        to_scan = []
        rss = []
        all_rss = ['net income', 'aluminum', 'bauxite', 'coal', 'food', 'gasoline', 'iron', 'lead', 'money', 'munitions', 'oil', 'steel', 'uranium']
        if nation['continent'] == "af":
            cont_rss = ['coal_mines', 'iron_mines', 'lead_mines']
            rss = [rs for rs in all_rss if rs + "_mines" not in cont_rss and rs + "_wells" not in cont_rss]
        elif nation['continent'] == "as":
            cont_rss = ['coal_mines', 'bauxite_mines', 'lead_mines']
            rss = [rs for rs in all_rss if rs + "_mines" not in cont_rss and rs + "_wells" not in cont_rss]
        elif nation['continent'] == "au":
            cont_rss = ['oil_wells', 'iron_mines', 'uranium_mines']
            rss = [rs for rs in all_rss if rs + "_mines" not in cont_rss and rs + "_wells" not in cont_rss]
        elif nation['continent'] == "eu":
            cont_rss = ['oil_wells', 'bauxite_mines', 'uranium_mines']
            rss = [rs for rs in all_rss if rs + "_mines" not in cont_rss and rs + "_wells" not in cont_rss]
        elif nation['continent'] == "na":
            cont_rss = ['oil_wells', 'bauxite_mines', 'lead_mines']
            rss = [rs for rs in all_rss if rs + "_mines" not in cont_rss and rs + "_wells" not in cont_rss]
        elif nation['continent'] == "sa":
            cont_rss = ['coal_mines', 'iron_mines', 'uranium_mines']
            rss = [rs for rs in all_rss if rs + "_mines" not in cont_rss and rs + "_wells" not in cont_rss]

        await ctx.edit(content="Scanning cities...")

        with open(pathlib.Path.cwd() / 'data' / f'cities-{date}.csv', encoding='cp437') as f1:
            csv_dict_reader = DictReader(f1)
            nation_age = nation['date'][:nation['date'].index("T")]
            for city in csv_dict_reader:
                if str(infra).lower() not in "any":
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
        
        temp, colors, prices, treasures, radiation, seasonal_mod = await utils.pre_revenue_calc(api_key, ctx, query_for_nation=False, parsed_nation=nation)

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
        for rs in rss:
            sorted_builds = sorted(unique_builds, key=lambda k: k[rs], reverse=True)
            best_builds = [city for city in sorted_builds if city[rs] == sorted_builds[0][rs]]
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

        class webbuild(MethodView):
            def get(arg):
                with open('./templates/buildspage.txt', 'r', encoding='UTF-8') as file:
                    template = file.read()
                result = Template(template).render(builds=builds, rss=rss, land=land, unique_builds=unique_builds, datetime=datetime)
                return str(result)
        endpoint = datetime.utcnow().strftime('%d%H%M%S')
        app.add_url_rule(f"/builds/{datetime.utcnow().strftime('%d%H%M%S')}", view_func=webbuild.as_view(str(datetime.utcnow())), methods=["GET", "POST"]) # this solution of adding a new page instead of updating an existing for the same nation is kinda dependent on the bot resetting every once in a while, bringing down all the endpoints
        if str(mmr).lower() in "any":
            mmr = "no military requirement"
        else:
            mmr = "a military requirement of " + '/'.join(mmr[i:i+1] for i in range(0, len(mmr), 1))
        await ctx.edit(content=f"{len(cities):,} valid cities and {len(unique_builds):,} unique builds fulfilled your criteria of {infra} infra and {mmr}.\n\nSee the best builds here (assuming you have {land} land): http://132.145.71.195:5000/builds/{endpoint}")
        return
    
    @slash_command(
        name="revenue",
        description="The revenue of a nation"
    )
    async def revenue(
        self,
        ctx: discord.ApplicationContext,
        person: Option(str, "The person you want to see the revenue of. Defaults to you.") = None
    ):
        await ctx.respond('Stay with me...')
        if person == None:
            person = ctx.author.id
        db_nation = utils.find_user(self, person)

        if db_nation == {}:
            db_nation = utils.find_nation(person)
            if not db_nation:
                await ctx.edit(content='I could not find that person!')
                return
            db_nation['nationid'] = db_nation['id']

        nation, colors, prices, treasures, radiation, seasonal_mod = await utils.pre_revenue_calc(api_key, ctx, query_for_nation=True, nationid=db_nation['id'])

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

    @slash_command(
        name="infracost",
        description="Cost to purchase infrastructure"
    )
    async def infra_cost(
        self,
        ctx: discord.ApplicationContext,
        starting_infra: Option(str, "The starting amount of infrastructure"),
        ending_infra: Option(str, "The ending amount of infrastructure"),
        person: Option(str, "The person purchasing infra. Defaults to you.") = None
    ):
        if not person:
            person = ctx.author.id
        db_person = utils.find_nation_plus(self, person)
        nation = (await utils.call(f"{{nations(first:1 id:{db_person['id']}){{data{{domestic_policy advanced_engineering_corps center_for_civil_engineering government_support_agency}}}}}}"))['data']['nations']['data'][0]

        starting_infra = utils.str_to_int(starting_infra)
        ending_infra = utils.str_to_int(ending_infra)
        
        cost = utils.infra_cost(int(starting_infra), int(ending_infra), nation)

        await ctx.respond(f"For `{db_person['leader_name']}`, going from `{starting_infra}` to `{ending_infra}` infrastructure, will cost `${cost:,}`.")
    
    @slash_command(
        name="landcost",
        description="Cost to purchase land."
    )
    async def land_cost(
        self,
        ctx: discord.ApplicationContext,
        starting_land: Option(str, "The starting amount of land."),
        ending_land: Option(str, "The ending amount of land."),
        person: Option(str, "The person purchasing land. Defaults to you.") = None
    ):
        if not person:
            person = ctx.author.id
        db_person = utils.find_nation_plus(self, person)
        nation = (await utils.call(f"{{nations(first:1 id:{db_person['id']}){{data{{domestic_policy advanced_engineering_corps arable_land_agency government_support_agency}}}}}}"))['data']['nations']['data'][0]

        starting_land = utils.str_to_int(starting_land)
        ending_land = utils.str_to_int(ending_land)

        cost = utils.land_cost(int(starting_land), int(ending_land), nation)

        await ctx.respond(f"For `{db_person['leader_name']}`, going from `{starting_land}` to `{ending_land}` land will cost `${cost:,}`.")

    @slash_command(
        name="citycost",
        description="Cost to purchase city."
    )
    async def city_cost(
        self,
        ctx: discord.ApplicationContext,
        city: Option(int, "The city to buy."),
        person: Option(str, "The person purchasing a city. Defaults to you.") = None
    ):
        if not person:
            person = ctx.author.id
        db_person = utils.find_nation_plus(self, person)
        nation = (await utils.call(f"{{nations(first:1 id:{db_person['id']}){{data{{domestic_policy urban_planning advanced_urban_planning government_support_agency}}}}}}"))['data']['nations']['data'][0]

        cost = utils.city_cost(int(city), nation)

        await ctx.respond(f"For `{db_person['leader_name']}`, purchasing city `{city}` will cost `${cost:,}`.")
    
    @slash_command(
        name="expansioncost",
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
        if not person:
            person = ctx.author.id
        db_person = utils.find_nation_plus(self, person)
        nation = (await utils.call(f"{{nations(first:1 id:{db_person['id']}){{data{{domestic_policy num_cities advanced_engineering_corps center_for_civil_engineering government_support_agency arable_land_agency urban_planning advanced_urban_planning}}}}}}"))['data']['nations']['data'][0]

        infra = utils.str_to_int(infra)
        land = utils.str_to_int(land)
        
        cost = utils.expansion_cost(nation['num_cities'], int(city), infra, land, nation)

        await ctx.respond(f"For `{db_person['leader_name']}`, going from city `{nation['num_cities']}` to city `{city}` (with `{infra}` infra and `{land}` land) will cost `${cost:,}`.")
    
    
def setup(bot):
    bot.add_cog(Background(bot))