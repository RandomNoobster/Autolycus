import os
from discord.ext import commands
import discord
import requests
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
import pymongo

client = pymongo.MongoClient(os.getenv("pymongolink"))
version = os.getenv("version")
mongo = client[str(version)]

api_key = os.getenv("api_key")

class General(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @slash_command(
        name="builds",
        brief="Shows you the best city builds"
    )
    async def build(
        self,
        ctx: discord.ApplicationContext,
        infra: Option(int, "How much infra the builds should be for"),
        land: Option(int, "How much land the builds should be for"),
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

        nation = requests.post(f"https://api.politicsandwar.com/graphql?api_key={api_key}", json={'query': f"{{nations(first:1 id:{db_nation['id']}){{data{{id continent date color dompolicy alliance{{name}} alliance_id num_cities ironw bauxitew armss egr massirr itc recycling_initiative telecom_satellite green_tech clinical_research_center specialized_police_training uap}}}}}}"}).json()['data']['nations']['data']
        if len(nation) == 0:
            await ctx.edit(content="That person was not in the API!")
            return
        else:
            nation = nation[0]
        
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
            nation_age = nation['date'][:nation['date'].index(" ")]
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
    
def setup(bot):
    bot.add_cog(General(bot))