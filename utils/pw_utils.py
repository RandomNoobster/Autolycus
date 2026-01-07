from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import sys
from datetime import datetime, timedelta
from gc import get_referents
from types import FunctionType, ModuleType
from typing import Any, Optional, Union, List, Dict

import aiofiles
import aiohttp
import discord
import motor.motor_asyncio
import pymongo
from pathlib import Path

import queries

client = pymongo.MongoClient(os.getenv("pymongolink"))
version = os.getenv("version")
bot_key = os.getenv("bot_key")
mongo = client[str(version)]
async_client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("pymongolink"), serverSelectionTimeoutMS=5000)
async_mongo = async_client[str(version)]

logging.basicConfig(filename="logs.log", filemode='a', format='%(levelname)s %(asctime)s.%(msecs)d %(name)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)
logger = logging.getLogger()

api_key = os.getenv("api_key")

RSS = ['aluminum', 'bauxite', 'coal', 'food', 'gasoline', 'iron', 'lead', 'money', 'munitions', 'oil', 'steel', 'uranium', 'credits']
EMBED_COLOR = 0xff5100

IMPROVEMENT_FIELDS: List[str] = [
    'infrastructure', 'oilpower', 'windpower', 'coalpower', 'nuclearpower',
    'coalmine', 'oilwell', 'uramine', 'leadmine', 'ironmine', 'bauxitemine',
    'farm', 'gasrefinery', 'aluminumrefinery', 'steelmill', 'munitionsfactory',
    'policestation', 'hospital', 'recyclingcenter', 'subway', 'supermarket',
    'bank', 'mall', 'stadium', 'barracks', 'factory', 'airforcebase', 'drydock'
]

async def paginate_call(data: str, path: str, key: str = api_key) -> list[dict[str, Any]]:
    n = 0
    has_more_pages = True
    data_to_return = []

    while has_more_pages:
        n += 1
        response = await call(data.replace("page_number", str(n), 1), key)
        data_to_return += response['data'][path]['data']
        has_more_pages = response['data'][path]['paginatorInfo']['hasMorePages']

    return data_to_return

async def call(data: str, key: str = api_key, retry_limit: int = 2, use_bot_key: bool = False) -> dict[str, Any]:
    async with aiohttp.ClientSession() as session:
        retry = 0
        while True:
            if use_bot_key:
                headers = {'X-Bot-Key': bot_key, 'X-Api-Key': api_key}
            else:
                headers = {}
            async with session.post(f'https://api.politicsandwar.com/graphql?api_key={key}', json={"query": data}, headers=headers) as response:
                if "X-Ratelimit-Remaining" in response.headers:
                    if response.headers['X-Ratelimit-Remaining'] == '0':
                        await asyncio.sleep(int(response.headers['X-Ratelimit-Reset-After']))
                        continue
                elif "Retry-After" in response.headers:
                    await asyncio.sleep(int(response.headers['Retry-After']))
                    continue
                try:
                    json_response = await response.json()
                except aiohttp.ContentTypeError:
                    raise Exception("Attempt to decode JSON with unexpected mimetype: " + await response.text())
                if response.status == 401:
                    if "error" in json_response:
                        if "invalid api_key" in json_response["error"]["errors"][0]["message"]:
                            raise ConnectionError("Invalid API key.")
                if "data" not in json_response and not use_bot_key:
                    if retry < retry_limit:
                        retry += 1
                        await asyncio.sleep(1)
                        continue
                    elif "error" in json_response:
                        raise Exception(json_response["error"])
                    elif "errors" in json_response:
                        raise Exception(json_response["errors"])
                return json_response

def get_query(*queries: Union[dict[str, Any], tuple]) -> str:
    def unpack(x: tuple) -> list:
        to_return = []
        for y in x:
            if isinstance(y, tuple):
                to_return += unpack(y)
            else:
                to_return.append(y)
        return to_return

    queries = list(queries)
    for idx, query in enumerate(queries.copy()):
        if isinstance(query, tuple):
            unpacked = unpack(query)
            del queries[idx]
            queries += unpacked
    merged = list(merge(*queries).values())[0]
    query = str(merged).replace("{", "").replace("}", "").replace(",", "").replace("[", "{").replace("]","}").replace("'", "").replace(": ", "")
    return query

def merge(*queries: dict[str, Any]) -> dict[str, Any]:
    paths = []
    for query in queries:
        paths.append(list(query.keys())[0])
    if len(set(paths)) != 1:
        raise Exception(f"Paths {paths} are not the same.")
    composite_query = {}
    for query in queries:
        for key, line in query.items():
            if key not in composite_query:
                composite_query[key] = line 
            else:
                if isinstance(line, dict):
                    composite_query[key] = merge(composite_query[key], line)
                elif isinstance(line, list):
                    for item in line:
                        if item not in composite_query[key]:
                            if isinstance(item, dict):
                                similar_item = [(x, y) for y, x in enumerate(composite_query[key]) if isinstance(x, dict) and list(item.keys())[0] in x]
                                if len(similar_item) == 0:
                                    composite_query[key].append(item)
                                else:
                                    similar_dict = similar_item[0][0]
                                    similar_idx = similar_item[0][1]
                                    composite_query[key][similar_idx] = (merge(similar_dict, item))
                            elif isinstance(item, str):
                                composite_query[key].append(item)
                            else:
                                raise Exception(f"Value {item} is not a dictionary or a string.")
                else:
                    raise Exception(f"Value {line} is not a dictionary or a list.")
    return composite_query

def cut_string(string: str, length: int = 2000) -> str:
    if len(string) > length:
        return string[:length-6] + "...```"
    else:
        return string

def comma_and_list(listy: list[str]) -> str:
    if not listy:
        return ""
    if len(listy) == 1:
        return listy[0]
    return ", ".join(listy[:-1]) + " and " + listy[-1]

def get_datetime_of_turns(turns: int) -> datetime:
    now = datetime.utcnow()
    if turns == 0:
        return now
    if turns < 0:
        return (now + timedelta(hours=turns * 2 + 1 * (not bool(now.hour % 2)) + 1)).replace(minute=0, second=0, microsecond=0)
    return (now + timedelta(hours=turns * 2 - 1 * bool(now.hour % 2))).replace(minute=0, second=0, microsecond=0)

def beige_loot_value(loot_string: str, prices: dict[str, float]) -> int:
    loot_string = loot_string[loot_string.index('$'):loot_string.index('Food.')]
    loot_string = re.sub(r"[^0-9-]+", "", loot_string.replace(", ", "-"))
    rss = ['money', 'coal', 'oil', 'uranium', 'iron', 'bauxite', 'lead', 'gasoline', 'munitions', 'steel', 'aluminum', 'food']
    n = 0
    loot = {}
    for sub in loot_string.split("-"):
        loot[rss[n]] = int(sub)
        n += 1
    nation_loot = 0
    for rs in rss:
        amount = loot[rs]
        price = int(prices[rs])
        nation_loot += amount * price
    return nation_loot

async def get_prices() -> dict[str, float]:
    prices = (await call(f"{{tradeprices(page:1 first:1){{data{get_query(queries.PRICES)}}}}}"))['data']['tradeprices']['data'][0]
    prices['money'] = 1
    return prices

async def total_value(resources: dict[str, float]) -> int:
    prices = await get_prices()
    x = 0
    for rs in prices:
        if rs in RSS and rs in resources:
            x += resources[rs] * prices[rs]
    return x

async def withdraw(api_key: str, resources: dict[str, float]) -> bool:
    try:
        call_string = ""
        for rs in resources:
            call_string += f"{rs}:{resources[rs]} "
        res = await call(f"mutation{{{{bankWithdraw({call_string}){{{{id}}}}}}}}", api_key, use_bot_key=True)
        if "errors" in res:
            raise Exception(res["errors"])
        return True
    except Exception as e:
        logger.error(f"Error withdrawing resources.\nApi key: {api_key}\nResources: {resources}\nError: {e}", exc_info=True)
        return False

async def listify(cursor) -> list[dict[str, Any]]:
    new_list = []
    async for x in cursor:
        new_list.append(x)
    return new_list

def str_to_id_list(str_var: str) -> tuple[list[str], str]:
    try:
        str_var = re.sub("[^0-9]", " ", str_var)
        str_var = str_var.strip().replace(" ", ",")
        index = 0
        while True:
            try:
                if str_var[index] == str_var[index+1] and not str_var[index].isdigit():
                    str_var = str_var[:index] + str_var[index+1:]
                    index -= 1
                index += 1
            except Exception as e: 
                break
        return str_var.split(","), str_var
    except Exception as e:
        logger.error(e, exc_info=True)
        raise e

def str_to_api_key_list(str_var: str) -> list[str]:
    try:
        str_var = re.sub("[^0-9a-zA-Z]", " ", str_var)
        str_var = str_var.strip().replace(" ", ",")
        index = 0
        while True:
            try:
                if str_var[index] == str_var[index+1] and not str_var[index].isdigit():
                    str_var = str_var[:index] + str_var[index+1:]
                    index -= 1
                index += 1
            except Exception as e: 
                break
        return str_var.split(",")
    except Exception as e:
        logger.error(e, exc_info=True)
        raise e

async def write_web(file: str, user_id: int, template: dict[str, Any], timestamp: int) -> None:
    new_dict = {"user_id": user_id, **template}
    file_path = Path.cwd() / "data" / "web" / file / str(user_id)
    file_path.mkdir(parents=True, exist_ok=True)
    json_file = file_path / f"{timestamp}.json"
    async with aiofiles.open(json_file, "w") as f:
        await f.write(json.dumps(new_dict))

async def read_web(file: str, user_id: int, timestamp: int) -> dict[str, Any]:
    json_file = Path.cwd() / "data" / "web" / file / str(user_id) / f"{timestamp}.json"
    async with aiofiles.open(json_file, "r") as f:
        return json.loads(await f.read())

def embed_pager(title: str, fields: list[dict[str, str]], description: str = "", color: int = 0xff5100, inline: bool = True) -> list[discord.Embed]:
    num_pages = math.ceil(len(fields) / 24)
    embeds = [discord.Embed(title=f"{title} page {i+1}", description=description, color=color) 
              for i in range(num_pages)]
    for idx, field in enumerate(fields):
        page_idx = idx // 24
        embeds[page_idx].add_field(name=field['name'], value=field['value'], inline=inline)
    return embeds

class SimpleModal(discord.ui.Modal):
    def __init__(self, label, placeholder, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.text = ""
        self.add_item(discord.ui.InputText(label=label, placeholder=placeholder))

    async def callback(self, interaction: discord.Interaction):
        self.text = self.children[0].value
        await interaction.response.edit_message()
        self.stop()

class YesOrNoView(discord.ui.View):
    def __init__(self, ctx, positive: str = "Yes", negative: str = "No", positive_style: discord.ButtonStyle = discord.ButtonStyle.green, negative_style: discord.ButtonStyle = discord.ButtonStyle.red, timeout: int = 600, author_check: bool = True):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.author_check = author_check
        self.result = None
        self.positive = positive
        positive_button = discord.ui.Button(label=self.positive, style=positive_style)
        positive_button.callback = self.primary_callback
        self.add_item(positive_button)
        self.negative = negative
        negative_button = discord.ui.Button(label=self.negative, style=negative_style)
        negative_button.callback = self.secondary_callback
        self.add_item(negative_button)

    async def primary_callback(self, i: discord.Interaction):
        self.result = True
        await i.response.edit_message()
        self.stop()
    
    async def secondary_callback(self, i: discord.Interaction):
        self.result = False
        await i.response.edit_message()
        self.stop()

    async def interaction_check(self, interaction) -> bool:
        if interaction.user != self.ctx.author and self.author_check:
            await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
            return False
        else:
            return True
    
    async def on_timeout(self):
        await run_timeout(self.ctx, self)  

class Dropdown(discord.ui.Select):
    def __init__(self, main_view, select_options: dict = {}):
        self.apples = main_view
        options = []
        n = 0
        for x in select_options['options']:
            options.append(discord.SelectOption(label=x['label'], description=x['description'], emoji=x['emoji'], value=n, default=x['default']))
            n += 1
        self.selectable_options = options
        super().__init__(
            placeholder=select_options.get('placeholder', "Select an option from the dropdown"),
            min_values=select_options.get('min_values', 1),
            max_values=select_options.get('max_values', 1),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.apples.embeds = sorted(self.apples.embeds, key=self.selectable_options[int(interaction.data['values'][0])]['sort_by'], reverse=True)
        await interaction.response.edit_message(embed=self.apples.embeds[0])

class Switch(discord.ui.View):
    def __init__(self, ctx, max_page: int, embeds: list, timeout: int = 600, author_check: bool = True, cur_page: int = 0, select_options: dict = {}):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.author_check = author_check
        self.cur_page = cur_page
        self.max_page = max_page - 1
        self.embeds = embeds
        if select_options:
            self.add_item(Dropdown(self, select_options))

    @discord.ui.button(label="<<", style=discord.ButtonStyle.primary)
    async def far_left_callback(self, _button: discord.Button, interaction: discord.Interaction) -> None:
        self.cur_page = 0
        await interaction.response.edit_message(embed=self.embeds[0])

    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
    async def left_callback(self, _button: discord.Button, interaction: discord.Interaction) -> None:
        if self.cur_page == 0:
            self.cur_page = self.max_page
        else:
            self.cur_page -= 1
        await interaction.response.edit_message(embed=self.embeds[self.cur_page])
    
    @discord.ui.button(label=">", style=discord.ButtonStyle.primary)
    async def right_callback(self, _button: discord.Button, interaction: discord.Interaction) -> None:
        if self.cur_page == self.max_page:
            self.cur_page = 0
        else:
            self.cur_page += 1
        await interaction.response.edit_message(embed=self.embeds[self.cur_page])
    
    @discord.ui.button(label=">>", style=discord.ButtonStyle.primary)
    async def far_right_callback(self, _button: discord.Button, interaction: discord.Interaction) -> None:
        self.cur_page = self.max_page
        await interaction.response.edit_message(embed=self.embeds[self.max_page])
    
    async def interaction_check(self, interaction) -> bool:
        if interaction.user != self.ctx.author and self.author_check:
            await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
            return False
        return True
    
    async def on_timeout(self) -> None:
        await run_timeout(self.ctx, self)

async def reaction_checker(self, message: discord.Message, embeds: list[discord.Embed]) -> None:
    reactions = []
    for i in range(len(embeds)):
        reactions.append(asyncio.create_task(message.add_reaction(f"{i+1}\N{variation selector-16}\N{combining enclosing keycap}")))
    await asyncio.gather(*reactions)
    while True:
        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=600)
            if user.bot == True or reaction.message != message:
                continue
            elif "\N{variation selector-16}\N{combining enclosing keycap}" in str(reaction.emoji):
                await message.edit(embed=embeds[int(str(reaction.emoji)[0])-1])
                await message.remove_reaction(reaction, user)
        except asyncio.TimeoutError:
            await message.edit(content="**Command timed out!**")
            break

async def run_timeout(ctx, view: Optional[discord.ui.View]) -> None:
    try:
        await ctx.edit(content=f"<@{ctx.author.id}> The command timed out!")
        if view:
            for x in view.children:
                x.disabled = True
            await ctx.edit(view=view)
    except Exception as e:
        logger.error(str(e) + "|| This error was ignored", exc_info=False)

def weird_division(a: float, b: float) -> float:
    return a / b if b else 0

async def find_user(self, arg: Union[str, int]) -> dict[str, Any]:
    if isinstance(arg, str):
        arg = arg.strip()
    db = async_mongo.global_users
    if str(arg).isdigit():
        if x := await db.find_one({"id": str(arg)}):
            return x
        elif x := await db.find_one({"user": int(arg)}):
            return x
    elif "@" in arg or ".com" in arg:
        new_arg = re.sub("[^0-9]", "", arg)
        if len(new_arg) > 0:
            if x := await db.find_one({"id": new_arg}):
                return x
            elif x := await db.find_one({"user": int(new_arg)}):
                return x
    else:
        members = self.bot.get_all_members()
        for member in members:
            if arg.lower() in member.name.lower():
                if x := await db.find_one({"user": member.id}):
                    return x
            elif arg.lower() in member.display_name.lower():
                if x := await db.find_one({"user": member.id}):
                    return x
            elif str(member).lower() == arg.lower():
                if x := await db.find_one({"user": member.id}):
                    return x
    return {}

async def find_nation(arg: Union[str, int]) -> Optional[dict[str, Any]]:
    if isinstance(arg, str):
        arg = arg.strip()
    new_arg = re.sub("[^0-9]", "", str(arg))
    if result := await listify(async_mongo.world_nations.find({"id": str(new_arg)}).collation({"locale": "en", "strength": 1})):
        return result[0]
    elif result := await listify(async_mongo.world_nations.find({"nation_name": arg}).collation({"locale": "en", "strength": 1})):
        return result[0]
    elif result := await listify(async_mongo.world_nations.find({"leader_name": arg}).collation({"locale": "en", "strength": 1})):
        return result[0]
    elif result := await listify(async_mongo.world_nations.find({"discord": arg}).collation({"locale": "en", "strength": 1})):
        return result[0]
    else:
        return None

async def find_nation_plus(self, arg: Union[str, int]) -> Optional[dict[str, Any]]:
    if isinstance(arg, str):
        arg = arg.strip()
    nation = await find_nation(arg)
    if nation == None:
        nation = await find_user(self, arg)
        if not nation:
            return None
        else:
            nation = await find_nation(nation['id'])
            if nation == None:
                return None
    return nation

async def get_alliances(ctx: discord.AutocompleteContext):
    alliances = await listify(async_mongo.alliances.find({}))
    return [f"{aa['name']} ({aa['id']})" for aa in alliances if (ctx.value.lower()) in aa['id'] or (ctx.value.lower()) in aa['name'].lower() or (ctx.value.lower()) in aa['acronym'].lower()]
    
async def get_target_alliances(ctx: discord.AutocompleteContext) -> list[str]:
    config = await async_mongo.guild_configs.find_one({"guild_id": ctx.interaction.guild_id})
    if config is None:
        return []
    try:
        ids = config['targets_alliance_ids']
    except KeyError:
        return []
    alliances = await listify(async_mongo.alliances.find({"id": {"$in": ids}}))
    return [f"{aa['name']} ({aa['id']})" for aa in alliances if (ctx.value.lower()) in aa['id'] or (ctx.value.lower()) in aa['name'].lower() or (ctx.value.lower()) in aa['acronym'].lower()]

async def yes_or_no(self, ctx) -> Optional[bool]:
    try:
        msg = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author and message.channel.id == ctx.channel.id, timeout=40)
        if msg.content.lower() in ('yes', 'y'):
            return True
        if msg.content.lower() in ('no', 'n'):
            return False
    except asyncio.TimeoutError:
        return None

def militarization_checker(nation: dict[str, Any]) -> dict[str, float]:
    milt = {}
    cities = len(nation['cities'])
    barracks = 0
    factories = 0
    hangars = 0
    drydocks = 0
    for city in nation['cities']:
        barracks += city['barracks']
        factories += city['factory']
        hangars += city['airforcebase']
        drydocks += city['drydock']
    milt['barracks_mmr'] = round(barracks / cities, 1)
    milt['factory_mmr'] = round(factories / cities, 1)
    milt['hangar_mmr'] = round(hangars / cities, 1)
    milt['drydock_mmr'] = round(drydocks / cities, 1)
    milt['max_soldiers'] = math.floor(min(3000 * barracks, nation['population']/6.67))
    milt['max_tanks'] = math.floor(min(250 * factories, nation['population']/66.67))
    milt['max_aircraft'] = math.floor(min(15 * hangars, nation['population']/1000))
    milt['max_ships'] = math.floor(min(5 * drydocks, nation['population']/10000))
    pg_mod = (int(nation["propaganda_bureau"]) * 0.1 + 1) 
    milt['soldiers_daily'] = round(milt['max_soldiers']/3) * pg_mod
    milt['tanks_daily'] = round(milt['max_tanks']/5) * pg_mod
    milt['aircraft_daily'] = round(milt['max_aircraft']/5) * pg_mod
    milt['ships_daily'] = round(milt['max_ships']/5) * pg_mod
    milt['soldiers_days'] = math.ceil(weird_division(milt['max_soldiers'] - nation['soldiers'], milt['max_soldiers']/3))
    milt['tanks_days'] = math.ceil(weird_division(milt['max_tanks'] - nation['tanks'], milt['max_tanks']/5))
    milt['aircraft_days'] = math.ceil(weird_division(milt['max_aircraft'] - nation['aircraft'], milt['max_aircraft']/5))
    milt['ships_days'] = math.ceil(weird_division(milt['max_ships'] - nation['ships'], milt['max_ships']/5))
    milt['total_milt'] = (nation['soldiers'] / (cities * 5 * 3000) + nation['tanks'] / (cities * 5 * 250) + nation['aircraft'] / (cities * 5 * 15) + nation['ships'] / (cities * 3 * 5)) / 4
    milt['soldiers_milt'] = nation['soldiers'] / (cities * 5 * 3000)
    milt['tanks_milt'] = nation['tanks'] / (cities * 5 * 250)
    milt['aircraft_milt'] = nation['aircraft'] / (cities * 5 * 15)
    milt['ships_milt'] = nation['ships'] / (cities * 3 * 5)
    return milt

def score_range(score: float) -> tuple[float, float]:
    min_score = score * 0.75
    max_score = score * 2.5
    return min_score, max_score

def infra_cost(starting_infra: int, ending_infra: int, nation: Optional[dict[str, Any]] = None) -> float:
    def unit_cost(amount: int):
        return ((abs(amount - 10) ** 2.2) / 710) + 300
    difference = ending_infra - starting_infra
    cost = 0
    if difference < 0:
        return 150 * difference
    if difference > 100 and difference % 100 != 0:
        delta = difference % 100
        cost += (round(unit_cost(starting_infra), 2) * delta)
        starting_infra += delta
        difference -= delta
    for _ in range(math.floor(difference // 100)):
        cost += round(unit_cost(starting_infra), 2) * 100
        starting_infra += 100
        difference -= 100
    if difference:
        cost += (round(unit_cost(starting_infra), 2) * difference)
    multiplier = 1
    if nation:
        if nation['center_for_civil_engineering']:
            multiplier -= 0.05
        if nation['advanced_engineering_corps']:
            multiplier -= 0.05
        if nation['domestic_policy'] == "URBANIZATION":
            if nation['government_support_agency']:
                multiplier -= 0.075
            else:
                multiplier -= 0.05
    return cost * multiplier

def land_cost(starting_land: int, ending_land: int, nation: Optional[dict[str, Any]] = None) -> float:
    def unit_cost(amount: int):
        return (.002*(amount-20)*(amount-20))+50
    difference = ending_land - starting_land
    cost = 0
    if difference < 0:
        return 50 * difference
    if difference > 500 and difference % 500 != 0:
        delta = difference % 500
        cost += round(unit_cost(starting_land), 2) * delta
        starting_land += delta
        difference -= delta
    for _ in range(math.floor(difference // 500)):
        cost += round(unit_cost(starting_land), 2) * 500
        starting_land += 500
        difference -= 500
    if difference:
        cost += (round(unit_cost(starting_land), 2) * difference)
    multiplier = 1
    if nation:
        if nation['arable_land_agency']:
            multiplier -= 0.05
        if nation['advanced_engineering_corps']:
            multiplier -= 0.05
        if nation['domestic_policy'] == "RAPID_EXPANSION":
            if nation['government_support_agency']:
                multiplier -= 0.075
            else:
                multiplier -= 0.05
    return cost * multiplier

def city_cost(city: int, nation: Optional[dict[str, Any]] = None) -> float:
    if city <= 1:
        raise ValueError("The provided value cannot be less than or equal to 1.")
    city -= 1
    modifier = 0
    multiplier = 1
    if nation:
        if nation['urban_planning']:
            modifier -= 50000000
        if nation['advanced_urban_planning']:
            modifier -= 100000000
        if nation['metropolitan_planning']:
            modifier -= 100000000
        if nation['domestic_policy'] == "MANIFEST_DESTINY":
            if nation['government_support_agency']:
                multiplier -= 0.075
            else:
                multiplier -= 0.05        
    return (50000 * math.pow((city - 1), 3) + 150000 * city + 75000 + modifier) * multiplier

def expansion_cost(current: int, end: int, infra: int, land: int, nation: Optional[dict[str, Any]] = None) -> float:
    diff = end - current
    if diff < 1:
        raise ValueError("Invalid start and end input.")
    cost = 0
    while current < end:
        current += 1
        cost += city_cost(current, nation)
        cost += infra_cost(10, infra, nation)
        cost += land_cost(250, land, nation)
    return cost

def str_to_int(string: str) -> int:
    string = str(string).replace(",", "")
    amount = string
    try:
        if "." in amount:
            number = re.sub("[A-z]", "", amount)
            amount = int(number.replace(".", "")) / 10**(len(number) - number.rfind(".") - 1)
    except (ValueError, AttributeError):
        pass
    if "k" in string.lower():
        amount = int(float(re.sub("[A-z]", "", str(amount))) * 1000)
    elif "m" in string.lower():
        amount = int(float(re.sub("[A-z]", "", str(amount))) * 1000000)
    elif "b" in string.lower():
        amount = int(float(re.sub("[A-z]", "", str(amount))) * 1000000000)
    else:
        try:
            amount = int(amount)
        except (ValueError, TypeError):
            pass
    if not isinstance(amount, int):
        raise ValueError("The provided value is not a valid amount.")
    return amount

async def pre_revenue_calc(message: discord.Message, query_for_nation: bool = False, nationid: Optional[Union[int, str]] = None, parsed_nation: Optional[dict[str, Any]] = None):
    if query_for_nation:
        nation = (await call(f"{{nations(first:1 id:{nationid}){{data{get_query(queries.REVENUE)}}}}}"))['data']['nations']['data']
        if len(nation) == 0:
            print("That person was not in the API!")
            raise 
        else:
            nation = nation[0]
    else:
        nation = parsed_nation
    await message.edit(content="Getting income modifiers...")
    res = await call(
        f"{{colors{{color turn_bonus}} game_info{{game_date radiation{{global north_america south_america africa europe asia australia antarctica}}}} tradeprices(first:1){{data{get_query(queries.PRICES)}}} treasures{{bonus nation{{id alliance_id}}}}}}"
    )
    res_colors = res['data']['colors']
    colors = {}
    for color in res_colors:
        colors[color['color']] = color['turn_bonus'] * 12
    prices = res['data']['tradeprices']['data'][0]
    prices['money'] = 1
    treasures = res['data']['treasures']
    game_info = res['data']['game_info']
    rad = game_info['radiation']
    radiation = {
        "na": (rad['north_america'] + rad['global']) / -1000,
        "sa": (rad['south_america'] + rad['global']) / -1000,
        "eu": (rad['europe'] + rad['global']) / -1000,
        "as": (rad['asia'] + rad['global']) / -1000,
        "af": (rad['africa'] + rad['global']) / -1000,
        "au": (rad['australia'] + rad['global']) / -1000,
        "an": (rad['antarctica'] + rad['global']) / -1000
    }
    month = int(game_info['game_date'][5:7])
    seasonal_mod = {"na": 1, "sa": 1, "eu": 1, "as": 1, "af": 1, "au": 1, "an": 0.5}
    if month in (6, 7, 8):
        seasonal_mod.update({'na': 1.2, 'as': 1.2, 'eu': 1.2, 'sa': 0.8, 'af': 0.8, 'au': 0.8})
    elif month in (12, 1, 2):
        seasonal_mod.update({'na': 0.8, 'as': 0.8, 'eu': 0.8, 'sa': 1.2, 'af': 1.2, 'au': 1.2})
    return nation, colors, prices, treasures, radiation, seasonal_mod

def calculate_nation_modifiers(nation: dict[str, Any]) -> dict[str, float]:
    modifiers = {
        'max_commerce': 100,
        'base_com': 0,
        'hos_dis_red': 2.5,
        'alu_mod': 1,
        'mun_mod': 1,
        'gas_mod': 1,
        'manu_poll_mod': 1,
        'farm_poll_mod': 0.5,
        'subw_poll_red': 45,
        'rss_upkeep_mod': 1,
        'ste_mod': 1,
        'rec_poll': 70,
        'pol_cri_red': 2.5,
        'food_land_mod': 500,
        'food_rad_effect_mod': 1,
        'uranium_mod': 1,
        'policy_bonus': 1,
        'mil_cost': 1,
        'new_player_bonus': 1,
    }
    if nation.get('ironw'):
        modifiers['ste_mod'] = 1.36
    if nation.get('bauxitew'):
        modifiers['alu_mod'] = 1.36
    if nation.get('armss'):
        modifiers['mun_mod'] = 1.2
    if nation.get('egr'):
        modifiers['gas_mod'] = 2
    if nation.get('massirr'):
        modifiers['food_land_mod'] = 400
    if nation.get('itc'):
        modifiers['max_commerce'] = 115
        modifiers['base_com'] = 1
    if nation.get('telecom_satellite'):
        modifiers['max_commerce'] = 125
        modifiers['base_com'] += 2
    if nation.get('recycling_initiative'):
        modifiers['rec_poll'] = 75
    if nation.get('green_tech'):
        modifiers['manu_poll_mod'] = 0.75
        modifiers['farm_poll_mod'] = 0.5
        modifiers['subw_poll_red'] = 70
        modifiers['rss_upkeep_mod'] = 0.9
    if nation.get('clinical_research_center'):
        modifiers['hos_dis_red'] = 3.5
    if nation.get('specialized_police_training'):
        modifiers['pol_cri_red'] = 3.5
        modifiers['base_com'] += 4
    if nation.get('uap'):
        modifiers['uranium_mod'] = 2
    if nation.get('fallout_shelter'):
        modifiers['food_rad_effect_mod'] = 0.85
    if nation.get('num_cities', 0) < 21:
        modifiers['new_player_bonus'] = 2.05 - 0.05 * nation['num_cities']
    if nation.get('dompolicy') == "Open Markets":
        modifiers['policy_bonus'] = 1.01
        if nation.get('government_support_agency'):
            modifiers['policy_bonus'] = 1.015
        if nation.get('bureau_of_domestic_affairs'):
            modifiers['policy_bonus'] = 1.0175
    if nation.get('dompolicy') == "Imperialism":
        modifiers['mil_cost'] = 0.95
        if nation.get('government_support_agency'):
            modifiers['mil_cost'] = 0.925
        if nation.get('bureau_of_domestic_affairs'):
            modifiers['mil_cost'] = 0.9125
    return modifiers

def calculate_power_generation(city: dict[str, Any]) -> dict[str, float]:
    result = {
        'unpowered_infra': city['infrastructure'],
        'power_upkeep': 0,
        'coal': 0,
        'oil': 0,
        'uranium': 0,
        'pollution': 0,
    }
    for _ in range(city.get('windpower', 0)):
        if result['unpowered_infra'] > 0:
            result['unpowered_infra'] -= 250
            result['power_upkeep'] += 500
    for _ in range(city.get('nuclearpower', 0)):
        result['power_upkeep'] += 10500
        for _ in range(2):
            if result['unpowered_infra'] > 0:
                result['unpowered_infra'] -= 1000
                result['uranium'] -= 2.4
    for _ in range(city.get('oilpower', 0)):
        result['power_upkeep'] += 1800
        result['pollution'] += 6
        for _ in range(5):
            if result['unpowered_infra'] > 0:
                result['unpowered_infra'] -= 100
                result['oil'] -= 1.2
    for _ in range(city.get('coalpower', 0)):
        result['power_upkeep'] += 1200
        result['pollution'] += 8
        for _ in range(5):
            if result['unpowered_infra'] > 0:
                result['unpowered_infra'] -= 100
                result['coal'] -= 1.2
    return result

def calculate_resource_production(city: dict[str, Any], modifiers: dict[str, float]) -> dict[str, float]:
    result = {
        'coal': 0,
        'oil': 0,
        'uranium': 0,
        'lead': 0,
        'iron': 0,
        'bauxite': 0,
        'rss_upkeep': 0,
        'pollution': 0,
    }
    coal_mines = city.get('coalmine', 0)
    if coal_mines > 0:
        result['rss_upkeep'] += 400 * coal_mines * modifiers['rss_upkeep_mod']
        result['pollution'] += 12 * coal_mines
        result['coal'] += 3 * coal_mines * (1 + ((0.5 * (coal_mines - 1)) / (10 - 1)))
    oil_wells = city.get('oilwell', 0)
    if oil_wells > 0:
        result['rss_upkeep'] += 600 * oil_wells * modifiers['rss_upkeep_mod']
        result['pollution'] += 12 * oil_wells
        result['oil'] += 3 * oil_wells * (1 + ((0.5 * (oil_wells - 1)) / (10 - 1)))
    uranium_mines = city.get('uramine', 0)
    if uranium_mines > 0:
        result['rss_upkeep'] += 5000 * uranium_mines * modifiers['rss_upkeep_mod']
        result['pollution'] += 20 * uranium_mines
        result['uranium'] += 3 * uranium_mines * (1 + ((0.5 * (uranium_mines - 1)) / (5 - 1))) * modifiers['uranium_mod']
    lead_mines = city.get('leadmine', 0)
    if lead_mines > 0:
        result['rss_upkeep'] += 1500 * lead_mines * modifiers['rss_upkeep_mod']
        result['pollution'] += 12 * lead_mines
        result['lead'] += 3 * lead_mines * (1 + ((0.5 * (lead_mines - 1)) / (10 - 1)))
    iron_mines = city.get('ironmine', 0)
    if iron_mines > 0:
        result['rss_upkeep'] += 1600 * iron_mines * modifiers['rss_upkeep_mod']
        result['pollution'] += 12 * iron_mines
        result['iron'] += 3 * iron_mines * (1 + ((0.5 * (iron_mines - 1)) / (10 - 1)))
    bauxite_mines = city.get('bauxitemine', 0)
    if bauxite_mines > 0:
        result['rss_upkeep'] += 1600 * bauxite_mines * modifiers['rss_upkeep_mod']
        result['pollution'] += 12 * bauxite_mines
        result['bauxite'] += 3 * bauxite_mines * (1 + ((0.5 * (bauxite_mines - 1)) / (10 - 1)))
    return result

def calculate_food_production(city: dict[str, Any], nation: dict[str, Any], modifiers: dict[str, float], seasonal_mod: dict[str, float], radiation: dict[str, float]) -> float:
    farms = city.get('farm', 0)
    if farms == 0:
        return 0
    food_prod = (
        city['land'] / modifiers['food_land_mod'] 
        * farms 
        * (1 + ((0.5 * (farms - 1)) / (20 - 1))) 
        * seasonal_mod[nation['continent']] 
        * (1 + radiation[nation['continent']] * modifiers['food_rad_effect_mod']) 
        * 12
    )
    return max(food_prod, 0)

def calculate_manufacturing(city: dict[str, Any], modifiers: dict[str, float], unpowered_infra: float) -> dict[str, float]:
    result = {
        'gasoline': 0,
        'steel': 0,
        'aluminum': 0,
        'munitions': 0,
        'coal': 0,
        'oil': 0,
        'iron': 0,
        'bauxite': 0,
        'lead': 0,
        'rss_upkeep': 0,
        'pollution': 0,
    }
    if unpowered_infra > 0 or not city.get('powered', True):
        return result
    gas_refineries = city.get('gasrefinery', 0)
    if gas_refineries > 0:
        result['rss_upkeep'] += 4000 * gas_refineries * modifiers['rss_upkeep_mod']
        result['pollution'] += 32 * gas_refineries * modifiers['manu_poll_mod']
        result['oil'] -= 3 * gas_refineries * (1 + ((0.5 * (gas_refineries - 1)) / (5 - 1))) * modifiers['gas_mod']
        result['gasoline'] += 6 * gas_refineries * (1 + ((0.5 * (gas_refineries - 1)) / (5 - 1))) * modifiers['gas_mod']
    steel_mills = city.get('steelmill', 0)
    if steel_mills > 0:
        result['rss_upkeep'] += 4000 * steel_mills * modifiers['rss_upkeep_mod']
        result['pollution'] += 40 * steel_mills * modifiers['manu_poll_mod']
        result['iron'] -= 3 * steel_mills * (1 + ((0.5 * (steel_mills - 1)) / (5 - 1))) * modifiers['ste_mod']
        result['coal'] -= 3 * steel_mills * (1 + ((0.5 * (steel_mills - 1)) / (5 - 1))) * modifiers['ste_mod']
        result['steel'] += 9 * steel_mills * (1 + ((0.5 * (steel_mills - 1)) / (5 - 1))) * modifiers['ste_mod']
    aluminum_refineries = city.get('aluminumrefinery', 0)
    if aluminum_refineries > 0:
        result['rss_upkeep'] += 2500 * aluminum_refineries * modifiers['rss_upkeep_mod']
        result['pollution'] += 40 * aluminum_refineries * modifiers['manu_poll_mod']
        result['bauxite'] -= 3 * aluminum_refineries * (1 + ((0.5 * (aluminum_refineries - 1)) / (5 - 1))) * modifiers['alu_mod']
        result['aluminum'] += 9 * aluminum_refineries * (1 + ((0.5 * (aluminum_refineries - 1)) / (5 - 1))) * modifiers['alu_mod']
    munitions_factories = city.get('munitionsfactory', 0)
    if munitions_factories > 0:
        result['rss_upkeep'] += 3500 * munitions_factories * modifiers['rss_upkeep_mod']
        result['pollution'] += 32 * munitions_factories * modifiers['manu_poll_mod']
        result['lead'] -= 6 * munitions_factories * (1 + ((0.5 * (munitions_factories - 1)) / (5 - 1)))
        result['munitions'] += 18 * munitions_factories * (1 + ((0.5 * (munitions_factories - 1)) / (5 - 1))) * modifiers['mun_mod']
    return result

def calculate_civil_improvements(city: dict[str, Any], modifiers: dict[str, float], unpowered_infra: float) -> dict[str, float]:
    result = {
        'civil_upkeep': 0,
        'commerce': modifiers['base_com'],
        'pollution': 0,
        'police_stations': 0,
        'hospitals': 0,
    }
    if unpowered_infra > 0 or not city.get('powered', True):
        return result
    result['civil_upkeep'] += city.get('policestation', 0) * 750
    result['civil_upkeep'] += city.get('hospital', 0) * 1000
    result['civil_upkeep'] += city.get('recyclingcenter', 0) * 2500
    result['civil_upkeep'] += city.get('subway', 0) * 3250
    result['civil_upkeep'] += city.get('supermarket', 0) * 600
    result['civil_upkeep'] += city.get('bank', 0) * 1800
    result['civil_upkeep'] += city.get('mall', 0) * 5400
    result['civil_upkeep'] += city.get('stadium', 0) * 12150
    result['police_stations'] = city.get('policestation', 0)
    result['hospitals'] = city.get('hospital', 0)
    result['pollution'] += city.get('policestation', 0)
    result['pollution'] += city.get('hospital', 0) * 4
    result['pollution'] -= city.get('recyclingcenter', 0) * modifiers['rec_poll']
    result['pollution'] -= city.get('subway', 0) * modifiers['subw_poll_red']
    result['pollution'] += city.get('mall', 0) * 2
    result['pollution'] += city.get('stadium', 0) * 5
    result['commerce'] += city.get('subway', 0) * 8
    result['commerce'] += city.get('supermarket', 0) * 4
    result['commerce'] += city.get('bank', 0) * 6
    result['commerce'] += city.get('mall', 0) * 8
    result['commerce'] += city.get('stadium', 0) * 10
    result['commerce'] = min(result['commerce'], modifiers['max_commerce'])
    return result

def calculate_population_effects(city: dict[str, Any], modifiers: dict[str, float], base_pop: float, commerce: float, police_stations: int, hospitals: int, pollution: float) -> dict[str, float]:
    crime_rate = (math.pow(103 - commerce, 2) + base_pop) / 111111 - police_stations * modifiers['pol_cri_red']
    crime_rate = max(crime_rate, 0)
    crime_deaths = max(((crime_rate) / 10) * base_pop - 25, 0)
    population_density = base_pop / city['land']
    disease_rate = (
        (((population_density ** 2) * 0.01) - 25) / 100
        + (base_pop / 100000)
        + pollution * 0.05
        - hospitals * modifiers['hos_dis_red']
    )
    disease_rate = max(0, min(disease_rate, 100))
    disease_deaths = max(base_pop * (disease_rate / 100), 0)
    city_age = (datetime.utcnow() - datetime.strptime(city['date'], "%Y-%m-%d")).days
    if city_age == 0:
        city_age = 1
    city_age_mod = 1 + math.log(city_age) / 15
    population = (base_pop - disease_deaths - crime_deaths) * city_age_mod
    food_consumption = (base_pop ** 2 / 125000000) + ((base_pop * city_age_mod - base_pop) / 850)
    return {
        'population': population,
        'crime_rate': crime_rate,
        'disease_rate': disease_rate,
        'food_consumption': food_consumption,
        'city_age_mod': city_age_mod,
    }

def calculate_military_upkeep(nation: dict[str, Any], modifiers: dict[str, float], include_spies: bool = False) -> tuple[float, float]:
    military_upkeep = 0
    food_consumption = 0
    at_war = False
    for war in nation.get('wars', []):
        if war.get('turnsleft', 0) > 0:
            at_war = True
            break
    if include_spies:
        military_upkeep += nation.get('spies', 0) * 2400
    ground_research = nation.get('military_research', {}).get('ground_cost', 0)
    air_research = nation.get('military_research', {}).get('air_cost', 0)
    naval_research = nation.get('military_research', {}).get('naval_cost', 0)
    # Per PWPedia july-2025-update: Aircraft upkeep changed to $750 (peace) / $1000 (war)
    # Per PWPedia july-2025-update: Ships upkeep changed to $3300 (peace) / $5000 (war)
    if not at_war:
        military_upkeep += nation.get('soldiers', 0) * (1.25 - 0.04 * ground_research)
        food_consumption += nation.get('soldiers', 0) / (750 + 20 * ground_research)
        military_upkeep += nation.get('tanks', 0) * (50 - 2 * ground_research)
        military_upkeep += nation.get('aircraft', 0) * (750 - 30 * air_research)
        military_upkeep += nation.get('ships', 0) * (3300 - 60 * naval_research)
        military_upkeep += nation.get('missiles', 0) * 21000
        military_upkeep += nation.get('nukes', 0) * 35000
    else:
        military_upkeep += nation.get('soldiers', 0) * (1.88 - 0.06 * ground_research)
        food_consumption += nation.get('soldiers', 0) / (500 + 30 * ground_research)
        military_upkeep += nation.get('tanks', 0) * (75 - 3 * ground_research)
        military_upkeep += nation.get('aircraft', 0) * (1000 - 20 * air_research)
        military_upkeep += nation.get('ships', 0) * (5000 - 100 * naval_research)
        military_upkeep += nation.get('missiles', 0) * 31500
        military_upkeep += nation.get('nukes', 0) * 52500
    return military_upkeep, food_consumption

def calculate_military_upkeep_from_buildings(city: dict[str, Any]) -> float:
    military_upkeep = 0
    military_upkeep += int(city.get('barracks', 0)) * 3000 * 1.25
    military_upkeep += int(city.get('factory', 0)) * 250 * 50
    military_upkeep += int(city.get('airforcebase', 0)) * 15 * 500
    military_upkeep += int(city.get('drydock', 0)) * 5 * 3750
    return military_upkeep

def calculate_treasure_bonus(nation: dict[str, Any], treasures: list[dict[str, Any]]) -> float:
    nation_treasure_bonus = 1
    alliance_treasures = 0
    for treasure in treasures:
        if treasure.get('nation') is None:
            continue
        if treasure['nation'].get('id') == nation.get('id'):
            nation_treasure_bonus += treasure.get('bonus', 0) / 100
        if nation.get('alliance') and treasure['nation'].get('alliance_id') == nation.get('alliance_id'):
            alliance_treasures += 1
    if alliance_treasures > 0:
        nation_treasure_bonus += math.sqrt(alliance_treasures * 4) / 100
    return nation_treasure_bonus

async def revenue_calc(message: discord.Message, nation: dict[str, Any], radiation: dict[str, float], treasures: list[dict[str, Any]], prices: dict[str, float], colors: dict[str, float], seasonal_mod: dict[str, float], build: Optional[str] = None, single_city: bool = False, include_spies: bool = False) -> dict[str, Any]:
    rss_upkeep = 0
    civil_upkeep = 0
    military_upkeep = 0
    money_income = 0
    power_upkeep = 0
    nationpop = 0 
    total_infra = 0
    coal = 0
    oil = 0
    uranium = 0
    lead = 0
    iron = 0
    bauxite = 0
    gasoline = 0
    munitions = 0
    steel = 0
    aluminum = 0
    food = 0
    starve_net_text = ""
    starve_money_text = ""
    starve_exp_text = ""
    color_text = ""
    new_player_text = ""
    policy_bonus_text = ""
    treasure_text = ""
    footer = ""
    modifiers = calculate_nation_modifiers(nation)
    if build is not None:
        try:
            build = json.loads(build)
        except json.JSONDecodeError:
            await message.edit(content="Something is wrong with the build you sent!")
            return
        land = 0
        for city in nation['cities']:
            land += city['land']
        city = {}
        for key, value in build.items():
            city[key[4:]] = int(value)
        city['infrastructure'] = city.pop('a_needed')
        city['land'] = round(land/nation['num_cities'])
        city['powered'] = True
        city['date'] = nation['cities'][math.ceil(nation['num_cities']/2)]['date']
        city['airforcebase'] = city['hangars']
        nation['cities'] = [city]
    for city in nation['cities']:
        total_infra += city['infrastructure']
        base_pop = city['infrastructure'] * 100
        power_result = calculate_power_generation(city)
        power_upkeep += power_result['power_upkeep']
        coal += power_result['coal']
        oil += power_result['oil']
        uranium += power_result['uranium']
        total_pollution = power_result['pollution']
        unpowered_infra = power_result['unpowered_infra']
        resource_result = calculate_resource_production(city, modifiers)
        rss_upkeep += resource_result['rss_upkeep']
        total_pollution += resource_result['pollution']
        coal += resource_result['coal']
        oil += resource_result['oil']
        uranium += resource_result['uranium']
        lead += resource_result['lead']
        iron += resource_result['iron']
        bauxite += resource_result['bauxite']
        farms = city.get('farm', 0)
        if farms > 0:
            rss_upkeep += 300 * farms * modifiers['rss_upkeep_mod']
            total_pollution += 2 * farms * modifiers['farm_poll_mod']
            food += calculate_food_production(city, nation, modifiers, seasonal_mod, radiation)
        manufacturing_result = calculate_manufacturing(city, modifiers, unpowered_infra)
        rss_upkeep += manufacturing_result['rss_upkeep']
        total_pollution += manufacturing_result['pollution']
        coal += manufacturing_result['coal']
        oil += manufacturing_result['oil']
        iron += manufacturing_result['iron']
        bauxite += manufacturing_result['bauxite']
        lead += manufacturing_result['lead']
        gasoline += manufacturing_result['gasoline']
        steel += manufacturing_result['steel']
        aluminum += manufacturing_result['aluminum']
        munitions += manufacturing_result['munitions']
        civil_result = calculate_civil_improvements(city, modifiers, unpowered_infra)
        civil_upkeep += civil_result['civil_upkeep']
        total_pollution += civil_result['pollution']
        commerce = civil_result['commerce']
        police_stations = civil_result['police_stations']
        hospitals = civil_result['hospitals']
        city['real_pollution'] = total_pollution
        city['pollution'] = max(total_pollution, 0)
        city['real_commerce'] = civil_result['commerce']
        city['commerce'] = commerce
        pop_result = calculate_population_effects(city, modifiers, base_pop, commerce, police_stations, hospitals, city['pollution'])
        city['real_crime_rate'] = pop_result['crime_rate']
        city['crime_rate'] = pop_result['crime_rate']
        city['real_disease_rate'] = pop_result['disease_rate']
        city['disease_rate'] = pop_result['disease_rate']
        nationpop += pop_result['population']
        money_income += (((commerce / 50) * 0.725) + 0.725) * pop_result['population']
        food -= pop_result['food_consumption']
    nation_treasure_bonus = calculate_treasure_bonus(nation, treasures)
    if nation_treasure_bonus > 1:
        treasure_text = f"\n\nTreasure Bonus: ${round(money_income * (nation_treasure_bonus - 1)):,}"
    color_bonus = 0
    if not single_city:
        color_bonus = colors[nation['color']]
        color_text = f"\n\nColor Trade Bloc Bonus: ${round(color_bonus):,}"
    if modifiers['new_player_bonus'] > 1:
        new_player_text = f"\n\nNew Player Bonus: ${round((modifiers['new_player_bonus'] - 1) * money_income):,}"
    if modifiers['policy_bonus'] != 1 and nation.get('dompolicy') == "Open Markets":
        policy_bonus_text = f"\n\nOpen Markets Bonus: ${round(money_income * (1 - modifiers['policy_bonus'])):,}"
    if not single_city:
        military_upkeep, food_consumption = calculate_military_upkeep(nation, modifiers, include_spies)
        food -= food_consumption
    else:
        military_upkeep = calculate_military_upkeep_from_buildings(city)
    military_upkeep *= modifiers['mil_cost']
    if modifiers['mil_cost'] != 1 and nation.get('dompolicy') == "Imperialism":
        policy_bonus_text = f"\n\nImperialism Bonus: ${round(military_upkeep * (1 - modifiers['mil_cost'])):,}"
    if food < 0:
        starve_exp_text = f"\n\nPossible Starvation Penalty: ${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * 0.33):,}*"
        starve_money_text = f" (${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * 0.67 + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep):,}*)"
        starve_net_text = f" (${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * 0.67 + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep + coal * prices['coal'] + oil * prices['oil'] + uranium * prices['uranium'] + lead * prices['lead'] + iron * prices['iron'] + bauxite * prices['bauxite'] + gasoline * prices['gasoline'] + munitions * prices['munitions'] + steel * prices['steel'] + aluminum * prices['aluminum'] + food * prices['food']):,}*)"
        footer = "* The income if the nation is suffering from a starvation penalty"
    max_infra = sorted(nation['cities'], key=lambda k: k['infrastructure'], reverse=True)[0]['infrastructure']
    if single_city:
        rev_obj = nation['cities'][0]
    else:
        rev_obj = {}
    rev_obj['monetary_net_num'] = round(
        money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * nation_treasure_bonus 
        + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep 
        + coal * prices['coal'] + oil * prices['oil'] + uranium * prices['uranium'] 
        + lead * prices['lead'] + iron * prices['iron'] + bauxite * prices['bauxite'] 
        + gasoline * prices['gasoline'] + munitions * prices['munitions'] 
        + steel * prices['steel'] + aluminum * prices['aluminum'] + food * prices['food']
    )
    rev_obj['net_cash_num'] = round(
        money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * nation_treasure_bonus 
        + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep
    )
    rev_obj['food'] = food
    rev_obj['aluminum'] = aluminum
    rev_obj['bauxite'] = bauxite
    rev_obj['coal'] = coal
    rev_obj['gasoline'] = gasoline
    rev_obj['iron'] = iron
    rev_obj['lead'] = lead
    rev_obj['munitions'] = munitions
    rev_obj['oil'] = oil
    rev_obj['steel'] = steel
    rev_obj['uranium'] = uranium
    if single_city and not build:
        rev_obj['money'] = rev_obj['net_cash_num']
        rev_obj['net income'] = rev_obj['monetary_net_num']
        rev_obj['disease_rate'] = city['disease_rate']
        rev_obj['crime_rate'] = city['crime_rate']
        rev_obj['commerce'] = city['commerce']
        rev_obj['pollution'] = city['pollution']
        return rev_obj
    else:
        rev_obj['nation'] = nation
    rev_obj['footer'] = footer
    rev_obj['max_infra'] = max_infra
    rev_obj['avg_infra'] = round(total_infra / nation['num_cities'])
    rev_obj['income_txt'] = f"National Tax Revenue: ${round(money_income):,}{color_text}{new_player_text}{policy_bonus_text}{treasure_text}\n\u200b"
    rev_obj['expenses_txt'] = f"Power Plant Upkeep: ${round(power_upkeep):,}\n\nResource Prod. Upkeep: ${round(rss_upkeep):,}\n\nMilitary Upkeep: ${round(military_upkeep):,}\n\nCity Improvement Upkeep: ${round(civil_upkeep):,}{starve_exp_text}\n\u200b"
    rev_obj['net_rev_txt'] = f"Coal: {round(coal):,}\nOil: {round(oil):,}\nUranium: {round(uranium):,}\nLead: {round(lead):,}\nIron: {round(iron):,}\nBauxite: {round(bauxite):,}\nGasoline: {round(gasoline):,}\nMunitions: {round(munitions):,}\nSteel: {round(steel):,}\nAluminum: {round(aluminum):,}\nFood: {round(food):,}\nMoney: ${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * nation_treasure_bonus + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep):,}{starve_money_text}\n\u200b"
    rev_obj['mon_net_txt'] = f"${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * nation_treasure_bonus + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep + coal * prices['coal'] + oil * prices['oil'] + uranium * prices['uranium'] + lead * prices['lead'] + iron * prices['iron'] + bauxite * prices['bauxite'] + gasoline * prices['gasoline'] + munitions * prices['munitions'] + steel * prices['steel'] + aluminum * prices['aluminum'] + food * prices['food']):,}{starve_net_text}"
    rev_obj['money_txt'] = f"${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * nation_treasure_bonus + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep):,}{starve_money_text}"
    return rev_obj
