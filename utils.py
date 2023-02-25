import math
import discord
import asyncio
import json
from datetime import datetime
from typing import Union, Tuple
import aiohttp
import re
import pathlib
import os
import logging
import queries
import pymongo
import motor.motor_asyncio
import aiofiles


client = pymongo.MongoClient(os.getenv("pymongolink"))
version = os.getenv("version")
mongo = client[str(version)]
async_client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("pymongolink"), serverSelectionTimeoutMS=5000)
async_mongo = async_client[str(version)]

logging.basicConfig(filename="logs.log", filemode='a', format='%(levelname)s %(asctime)s.%(msecs)d %(name)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)
logger = logging.getLogger()

api_key = os.getenv("api_key")

RSS = ['aluminum', 'bauxite', 'coal', 'food', 'gasoline', 'iron', 'lead', 'money', 'munitions', 'oil', 'steel', 'uranium', 'credits']


async def paginate_call(data: str, path: str, key: str = api_key) -> Union[dict, aiohttp.ClientResponse]:
    """
    Paginates a call to the API. Must incude `page:page_number` in the query.
    `data` is the GraphQL query.
    `path` is the path to the information (`alliances`, `nations` etc).
    `key` is the API key.
    """
    n = 0
    has_more_pages = True
    data_to_return = []

    while has_more_pages:
        n += 1
        response = await call(data.replace("page_number", str(n), 1), key)
        data_to_return += response['data'][path]['data']
        has_more_pages = response['data'][path]['paginatorInfo']['hasMorePages']

    return data_to_return

async def call(data: str, key: str = api_key, retry_limit: int = 2, use_bot_key = False) -> Union[dict, aiohttp.ClientResponse]:
    async with aiohttp.ClientSession() as session:
        retry = 0
        while True:
            if use_bot_key:
                headers = {'X-Bot-Key': "4ba04e11ee113594", 'X-Api-Key': key}
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
                json_response = await response.json()
                if response.status == 401:
                    if "error" in json_response:
                        if "invalid api_key" in json_response["error"]["errors"][0]["message"]:
                            raise ConnectionError("Invalid API key.")
                if "data" not in json_response:
                    if retry < retry_limit:
                        retry += 1
                        await asyncio.sleep(1)
                        continue
                return json_response

def get_query(*queries: Union[dict, tuple]) -> str:
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
    #print(merged)
    query = str(merged).replace("{", "").replace("}", "").replace(",", "").replace("[", "{").replace("]","}").replace("'", "").replace(": ", "")
    return query

def merge(*queries: dict) -> dict:
    paths = []
    for query in queries:
        paths.append(list(query.keys())[0])
    if len(set(paths)) != 1:
        raise Exception(f"Paths {paths} are not the same.")
    composite_query = {} # the composite query to return
    for query in queries: # for each query
        for key, line in query.items(): # nations, cities etc
            if key not in composite_query: # the key is NOT in the composite query yet
                composite_query[key] = line 
            else: # the key is already in the composite query
                if isinstance(line, dict): # the value is a dictionary
                    composite_query[key] = merge(composite_query[key], line) # merge the two dictionaries
                elif isinstance(line, list): # the value is a list
                    for item in line: # for each item in the line
                        if item not in composite_query[key]: # if the item is not in the composite query
                            if isinstance(item, dict): # if the item is a dictionary
                                similar_item = [(x, y) for y, x in enumerate(composite_query[key]) if isinstance(x, dict) and list(item.keys())[0] in x] # find similar items
                                if len(similar_item) == 0: # if there are no similar items
                                    composite_query[key].append(item) # add the item to the composite query
                                else: # if there are similar items
                                    similar_dict = similar_item[0][0] # get the similar dictionary
                                    similar_idx = similar_item[0][1] # get the index of the similar dictionary
                                    composite_query[key][similar_idx] = (merge(similar_dict, item)) # merge the similar dictionary with the item
                            elif isinstance(item, str): # if the item is a string
                                composite_query[key].append(item) # add the item to the composite query
                            else: # the value is wrong
                                raise Exception(f"Value {item} is not a dictionary or a string.")
                else: # the value is wrong
                    raise Exception(f"Value {line} is not a dictionary or a list.")
    return composite_query

def cut_string(string: str, length: int = 2000) -> str:
    if len(string) > length:
        return string[:length-6] + "...```"
    else:
        return string

def beige_loot_value(loot_string: str, prices: dict) -> int:
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

async def get_prices() -> dict:
    prices = (await call(f"{{tradeprices(page:1 first:1){{data{get_query(queries.PRICES)}}}}}"))['data']['tradeprices']['data'][0]
    prices['money'] = 1
    return prices

async def total_value(resources: dict) -> int:
    """
    Returns the total value of a nation's resources. The parsed dict can include any fields, but only the ones that are resources will be used.
    """
    prices = await get_prices()
    x = 0
    for rs in prices:
        if rs in RSS and rs in resources: # if the resource is a resource and is in the resources dict
            x += resources[rs] * prices[rs]
    return x

async def withdraw(api_key: str, resources: dict) -> bool:
    try:
        call_string = ""
        for rs in resources:
            call_string += f"{rs}:{resources[rs]} "
        res = await call(f"mutation{{bankWithdraw({call_string}){{id}}}}", use_bot_key=True)
        print(res)
        return True
    except Exception as e:
        logger.error(f"Error withdrawing resources.\nApi key: {api_key}\nResources: {resources}", exc_info=True)
        return False
                
async def listify(cursor):
    new_list = []
    async for x in cursor:
        new_list.append(x)
    return new_list

def str_to_id_list(str_var: str) -> list:
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

def str_to_api_key_list(str_var: str) -> list:
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

async def write_web(file: str, user_id: int, template: dict) -> None:
    """
    template should always include user_id
    """
    ## write to file here 
    current_data = []
    async with aiofiles.open(pathlib.Path.cwd() / "data" / "web" / f"{file}.json", "r") as f:
        current_data = json.loads(await f.read())

    for x in current_data:
        if int(x['user_id']) == user_id:
            current_data.remove(x)
            break
    
    new_dict = {"user_id": user_id}
    for x in template:
        new_dict[x] = template[x]
    
    current_data.append(new_dict)    

    async with aiofiles.open(pathlib.Path.cwd() / "data" / "web" / f"{file}.json", "w") as f:
        await f.write(json.dumps(current_data))

async def read_web(file: str, user_id: int) -> dict:
    async with aiofiles.open(pathlib.Path.cwd() / "data" / "web" / f"{file}.json", "r") as f:
        current_data = json.loads(await f.read())
    for x in current_data:
        if int(x['user_id']) == user_id:
            return x
    return None

def embed_pager(title: str, fields: list, description: str = "", color: int = 0xff5100, inline: bool = True) -> list:
    embeds = []
    for i in range(math.ceil(len(fields)/24)):
        embeds.append(discord.Embed(title=f"{title} page {i+1}", description=description, color=color)) 
    index = 0
    n = 0
    for field in fields:
        embeds[index].add_field(name=f"{field['name']}", value=field['value'], inline=inline)
        n += 1
        if n % 24 == 0:
            index += 1
    return embeds

class yes_or_no_view(discord.ui.View):
    def __init__(self, ctx, timeout: int = 600, author_check: bool = True):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.author_check = author_check
        self.result = None

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def primary_callback(self, b: discord.Button, i: discord.Interaction):
        self.result = True
        await i.response.edit_message()
        self.stop()
    
    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
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
    """
    select_options: Needs `embeds`, `placeholder`, `min_values`, `max_values` and `options` -> list of dicts with `label`, `description`, `emoji`, `value` (index) and `default`.
    """
    def __init__(self, main_view, select_options: dict = {}):
        self.apples = main_view
        options = []
        n = 0
        for x in select_options['options']:
            options.append(discord.SelectOption(label=x['label'], description=x['description'], emoji=x['emoji'], value=n, default=x['default']))
            n += 1
        self.selectable_options = options

        # The placeholder is what will be shown when no option is selected.
        # The min and max values indicate we can only pick one of the three options.
        # The options parameter, contents shown above, define the dropdown options.
        super().__init__(
            placeholder=select_options['placeholder'] or "Select an option from the dropdown",
            min_values=select_options['min_values'] or 1,
            max_values=select_options['max_values'] or 1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.apples.embeds = sorted(self.apples.embeds, key=self.selectable_options[int(interaction.data['values'][0])]['sort_by'], reverse=True)
        await interaction.response.edit_message(embed=self.apples.embeds[0])
        print("gg")

class switch(discord.ui.View):
    """
    select_options: Needs `embeds`, `placeholder`, `min_values`, `max_values` and `options` -> list of dicts with `label`, `description`, `emoji`, `value` and `default`.
    """
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
    async def far_left_callback(self, b: discord.Button, i: discord.Interaction):
        self.cur_page = 0
        await i.response.edit_message(embed=self.embeds[0])

    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
    async def left_callback(self, b: discord.Button, i: discord.Interaction):
        if self.cur_page == 0:
            self.cur_page = self.max_page
            await i.response.edit_message(embed=self.embeds[self.cur_page])
        else:
            self.cur_page -= 1
            await i.response.edit_message(embed=self.embeds[self.cur_page])
    
    @discord.ui.button(label=">", style=discord.ButtonStyle.primary)
    async def right_callback(self, b: discord.Button, i: discord.Interaction):
        if self.cur_page == self.max_page:
            self.cur_page = 0
            await i.response.edit_message(embed=self.embeds[self.cur_page])
        else:
            self.cur_page += 1
            await i.response.edit_message(embed=self.embeds[self.cur_page])
    
    @discord.ui.button(label=">>", style=discord.ButtonStyle.primary)
    async def far_right_callback(self, b: discord.Button, i: discord.Interaction):
        self.cur_page = self.max_page
        await i.response.edit_message(embed=self.embeds[self.max_page])
    
    async def interaction_check(self, interaction) -> bool:
        if interaction.user != self.ctx.author and self.author_check:
            await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
            return False
        else:
            return True
    
    async def on_timeout(self):
        await run_timeout(self.ctx, self)
                
async def reaction_checker(self, message: discord.Message, embeds: list) -> None:
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

async def run_timeout(ctx, view):
    try:
        await ctx.edit(content=f"<@{ctx.author.id}> The command timed out!")
        if view:
            for x in view.children:
                x.disabled = True
            await ctx.edit(view=view)
    except Exception as e:
        logger.error(str(e) + "|| This error was ignored", exc_info=False)

def weird_division(a, b):
    return a / b if b else 0

async def find_user(self, arg):
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

async def find_nation(arg: Union[str, int]) -> Union[dict, None]:
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

async def find_nation_plus(self, arg: Union[str, int]) -> Union[dict, None]: # only returns a nation if it is at least 1 hour old
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
    """Returns a list of alliances that begin with the characters entered so far."""
    alliances = await listify(async_mongo.alliances.find({}))
    return [f"{aa['name']} ({aa['id']})" for aa in alliances if (ctx.value.lower()) in aa['id'] or (ctx.value.lower()) in aa['name'].lower() or (ctx.value.lower()) in aa['acronym'].lower()]
    
async def get_target_alliances(ctx: discord.AutocompleteContext):
    """Returns a list of alliances that begin with the characters entered so far."""
    config = await async_mongo.guild_configs.find_one({"guild_id": ctx.interaction.guild_id})
    if config is None:
        return []
    else:
        try:
            ids = config['targets_alliance_ids']
        except:
            return []
    alliances = await listify(async_mongo.alliances.find({"id": {"$in": ids}}))
    return [f"{aa['name']} ({aa['id']})" for aa in alliances if (ctx.value.lower()) in aa['id'] or (ctx.value.lower()) in aa['name'].lower() or (ctx.value.lower()) in aa['acronym'].lower()]

async def yes_or_no(self, ctx) -> Union[bool, None]:
    try:
        msg = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author and message.channel.id == ctx.channel.id, timeout=40)
        if msg.content.lower() in ['yes', 'y']:
            return True
        elif msg.content.lower() in ['no', 'n']:
            return False
    except asyncio.TimeoutError:
        return None

def militarization_checker(nation: dict) -> float:
    """
    Requires `cities` with `barracks`, `factory`, `airforcebase` and `drydock`. Also `soldiers`, `tanks`, `aircraft`, `ships`, `propaganda_bureau` and `population`
    """
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

def score_range(score: float) -> Tuple[float, float]:
    """
    Determines the offensive score range for a given score.
    :param score: Score to determine offensive war ranges for.
    :return: Minimum attacking range and maximum attacking range, in that order.
    """
    min_score = score * 0.75
    max_score = score * 1.75
    return min_score, max_score


def infra_cost(starting_infra: int, ending_infra: int, nation: dict = None) -> float:
    """
    Calculate the cost to purchase or sell infrastructure.
    :param starting_infra: A starting infrastructure amount.
    :param ending_infra: The desired infrastructure amount.
    :param multiplier: A multiplier to adjust the ending result by.
    :param nation: Must include `center_for_civil_engineering`, `advanced_engineering_corps`, `government_support_agency` and `domestic_policy`.
    :return: The cost to purchase or sell infrastructure.
    """
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


def land_cost(starting_land: int, ending_land: int, nation: dict = None) -> float:
    """
    Calculate the cost to purchase or sell land.
    :param starting_land: A starting land amount.
    :param ending_land: The desired land amount.
    :param multiplier: A multiplier to adjust the ending result by.
    :param nation: Must include `arable_land_agency`, `advanced_engineering_corps`, `government_support_agency` and `domestic_policy`.
    :return: The cost to purchase or sell land.
    """
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


def city_cost(city: int, nation: dict = None) -> float:
    """
    Calculate the cost to purchase a specified city.
    :param city: The city to be purchased.
    :param nation: Must include `urban_planning`, `advanced_urban_planning`, `government_support_agency` and `domestic_policy`.
    :return: The cost to purchase the specified city.
    """
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


def expansion_cost(current: int, end: int, infra: int, land: int, nation: dict = None) -> float:
    """
    Calculate the cost to purchase a specified city.
    :param current: The current city
    :param end: The final city to be purchased.
    :param infra: The amount of infra in city to be purchased.
    :param land: The amount of land in city to be purchased.
    :return: The cost to purchase the specified city.
    """
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
    """
    Converts a string to an integer.
    :param string: String to be converted.
    :return: The integer value of the string.
    """
    string = str(string)
    amount = string
    try:
        if "." in amount:
            number = re.sub("[A-z]", "", amount)
            amount = int(number.replace(".", "")) / 10**(len(number) - number.rfind(".") - 1)
    except:
        pass

    if "k" in string.lower():
        amount = int(float(re.sub("[A-z]", "", str(amount))) * 1000)
    if "m" in string.lower():
        amount = int(float(re.sub("[A-z]", "", str(amount))) * 1000000)
    if "b" in string.lower():
        amount = int(float(re.sub("[A-z]", "", str(amount))) * 1000000000)
    else:
        try:
            amount = int(amount)
        except:
            pass

    if not isinstance(amount, int):
        raise ValueError("The provided value is not a valid amount.")

    return amount

async def pre_revenue_calc(message: discord.Message, query_for_nation: bool = False, nationid: Union[int, str] = None, parsed_nation: dict = None):
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
    res = await call(f"{{colors{{color turn_bonus}} game_info{{game_date radiation{{global north_america south_america africa europe asia australia antarctica}}}} tradeprices(first:1){{data{get_query(queries.PRICES)}}} treasures{{bonus nation{{id alliance_id}}}}}}")
    res_colors = res['data']['colors']
    colors = {}
    for color in res_colors:
        colors[color['color']] = color['turn_bonus'] * 12

    prices = res['data']['tradeprices']['data'][0]
    prices['money'] = 1

    treasures = res['data']['treasures']

    game_info = res['data']['game_info']

    rad = game_info['radiation']
    radiation = {"na": 1 - (rad['north_america'] + rad['global'])/1000, "sa": 1 - (rad['south_america'] + rad['global'])/1000, "eu": (rad['europe'] + rad['global'])/1000, "as": 1 - (rad['asia'] + rad['global'])/1000, "af": 1 - (rad['africa'] + rad['global'])/1000, "au": 1 - (rad['australia'] + rad['global'])/1000, "an": 1 - (rad['antarctica'] + rad['global'])/1000}
    
    month = int(game_info['game_date'][5:7])
    seasonal_mod = {"na": 1, "sa": 1, "eu": 1, "as": 1, "af": 1, "au": 1, "an": 0.5}
    if month in [6,7,8]:
        seasonal_mod['na'] = 1.2
        seasonal_mod['as'] = 1.2
        seasonal_mod['eu'] = 1.2
        seasonal_mod['sa'] = 0.8
        seasonal_mod['af'] = 0.8
        seasonal_mod['au'] = 0.8
    elif month in [12,1,2]:
        seasonal_mod['na'] = 0.8
        seasonal_mod['as'] = 0.8
        seasonal_mod['eu'] = 0.8
        seasonal_mod['sa'] = 1.2
        seasonal_mod['af'] = 1.2
        seasonal_mod['au'] = 1.2

    return nation, colors, prices, treasures, radiation, seasonal_mod

async def revenue_calc(message: discord.Message, nation: dict, radiation: dict, treasures: dict, prices: dict, colors: dict, seasonal_mod: dict, build: str = None, single_city: bool = False, include_spies: bool = False) -> dict:
    max_commerce = 100
    base_com = 0
    hos_dis_red = 2.5
    alu_mod = 1
    mun_mod = 1
    gas_mod = 1
    manu_poll_mod = 1
    farm_poll_mod = 0.5
    subw_poll_red = 45
    rss_upkeep_mod = 1
    ste_mod = 1
    rec_poll = 70
    pol_cri_red = 2.5
    food_land_mod = 500
    uranium_mod = 1
    rss_upkeep = 0
    civil_upkeep = 0
    military_upkeep = 0
    money_income = 0
    power_upkeep = 0
    nationpop = 0 
    color_bonus = 0
    policy_bonus = 1
    new_player_bonus = 1
    mil_cost = 1
    total_infra = 0
    starve_net_text = ""
    starve_money_text = ""
    starve_exp_text = ""
    color_text = ""
    new_player_text = ""
    policy_bonus_text = ""
    treasure_text = ""
    footer = ""
    
    if nation['ironw'] == True:
        ste_mod = 1.36
    if nation['bauxitew'] == True:
        alu_mod = 1.36
    if nation['armss'] == True:
        mun_mod = 1.34
    if nation['egr'] == True:
        gas_mod = 2
    if nation['massirr'] == True:
        food_land_mod = 400
    if nation['itc'] == True:
        max_commerce = 115
    if nation['telecom_satellite'] == True:
        max_commerce = 125
        base_com = 2
    if nation['recycling_initiative'] == True:
        rec_poll = 75
    if nation['green_tech'] == True:
        manu_poll_mod = 0.75
        farm_poll_mod = 0.5
        subw_poll_red = 70
        rss_upkeep_mod = 0.9
    if nation['clinical_research_center'] == True:
        hos_dis_red = 3.5
    if nation['specialized_police_training'] == True:
        hos_dis_red = 3.5
    if nation['uap'] == True:
        uranium_mod = 2

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

    if build != None:
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
        #print(city)
    
    if nation['resource_production_center'] == True:
        modifer = min(5, math.floor(len(nation['cities'])/2)) * 12
        if nation['continent'] == "na":
            coal += 1 * modifer
            iron += 1 * modifer
            uranium += 1 * modifer
        elif nation['continent'] == "sa":
            oil += 1 * modifer
            bauxite += 1 * modifer
            lead += 1 * modifer
        elif nation['continent'] == "eu":
            coal += 1 * modifer
            iron += 1 * modifer
            lead += 1 * modifer
        elif nation['continent'] == "af":
            oil += 1 * modifer
            bauxite += 1 * modifer
            uranium += 1 * modifer
        elif nation['continent'] == "as":
            oil += 1 * modifer
            iron += 1 * modifer
            uranium += 1 * modifer
        elif nation['continent'] == "au":
            coal += 1 * modifer
            bauxite += 1 * modifer
            lead += 1 * modifer
        elif nation['continent'] == "an":
            coal += 1 * modifer
            oil += 1 * modifer
            uranium += 1 * modifer

    for city in nation['cities']:
        total_infra += city['infrastructure']
        base_pop = city['infrastructure'] * 100
        pollution = 0
        unpowered_infra = city['infrastructure']
        for wind_plant in range(city['windpower']): #can add something about wasted slots
            if unpowered_infra > 0:
                unpowered_infra -= 250
                power_upkeep += 42
        for nucl_plant in range(city['nuclearpower']): 
            power_upkeep += 10500
            for level in range(2):
                if unpowered_infra > 0:
                    unpowered_infra -= 1000
                    uranium -= 1.2
        for oil_plant in range(city['oilpower']): 
            power_upkeep += 1800 
            pollution += 6
            for level in range(5):
                if unpowered_infra > 0:
                    unpowered_infra -= 100
                    oil -= 1.2
        for coal_plant in range(city['coalpower']): 
            power_upkeep += 1200  
            pollution += 8
            for level in range(5):
                if unpowered_infra > 0:
                    unpowered_infra -= 100
                    coal -= 1.2

        rss_upkeep += 400 * city['coalmine'] * rss_upkeep_mod
        pollution += 12 * city['coalmine']
        coal += 3 * city['coalmine'] * (1 + ((0.5 * (city['coalmine'] - 1)) / (10 - 1)))

        rss_upkeep += 600 * city['oilwell'] * rss_upkeep_mod
        pollution += 12 * city['oilwell']
        oil += 3 * city['oilwell'] * (1 + ((0.5 * (city['oilwell'] - 1)) / (10 - 1)))

        rss_upkeep += 5000 * city['uramine'] * rss_upkeep_mod
        pollution += 20 * city['uramine']
        uranium += 3 * city['uramine'] * (1 + ((0.5 * (city['uramine'] - 1)) / (5 - 1))) * uranium_mod

        rss_upkeep += 1500 * city['leadmine'] * rss_upkeep_mod
        pollution += 12 * city['leadmine']
        lead += 3 * city['leadmine'] * (1 + ((0.5 * (city['leadmine'] - 1)) / (10 - 1)))

        rss_upkeep += 1600 * city['ironmine'] * rss_upkeep_mod
        pollution += 12 * city['ironmine']
        iron += 3 * city['ironmine'] * (1 + ((0.5 * (city['ironmine'] - 1)) / (10 - 1)))

        rss_upkeep += 1600 * city['bauxitemine'] * rss_upkeep_mod
        pollution += 12 * city['bauxitemine']
        bauxite += 3 * city['bauxitemine'] * (1 + ((0.5 * (city['bauxitemine'] - 1)) / (10 - 1)))

        rss_upkeep += 300 * city['farm'] * rss_upkeep_mod ## seasonal modifiers and radiation
        pollution += 2 * city['farm'] * farm_poll_mod
        food_prod = city['land']/food_land_mod * city['farm'] * (1 + ((0.5 * (city['farm'] - 1)) / (20 - 1))) * seasonal_mod[nation['continent']] * max(radiation[nation['continent']], 0.1 * int(nation['fallout_shelter'])) * 12
        if food_prod < 0:
            food += 0
        else:
            food += food_prod
        
        commerce = base_com
        if unpowered_infra <= 0 and city['powered']:
            rss_upkeep += 4000 * city['gasrefinery'] * rss_upkeep_mod
            pollution += 32 * city['gasrefinery'] * manu_poll_mod
            oil -= 3 * city['gasrefinery'] * (1 + ((0.5 * (city['gasrefinery'] - 1)) / (5 - 1))) * gas_mod
            gasoline += 6 * city['gasrefinery'] * (1 + ((0.5 * (city['gasrefinery'] - 1)) / (5 - 1))) * gas_mod

            rss_upkeep += 4000 * city['steelmill'] * rss_upkeep_mod
            pollution += 40 * city['steelmill'] * manu_poll_mod
            iron -= 3 * city['steelmill'] * (1 + ((0.5 * (city['steelmill'] - 1)) / (5 - 1))) * ste_mod
            coal -= 3 * city['steelmill'] * (1 + ((0.5 * (city['steelmill'] - 1)) / (5 - 1))) * ste_mod
            steel += 9 * city['steelmill'] * (1 + ((0.5 * (city['steelmill'] - 1)) / (5 - 1))) * ste_mod

            rss_upkeep += 2500 * city['aluminumrefinery'] * rss_upkeep_mod
            pollution += 40 * city['aluminumrefinery'] * manu_poll_mod
            bauxite -= 3 * city['aluminumrefinery'] * (1 + ((0.5 * (city['aluminumrefinery'] - 1)) / (5 - 1))) * alu_mod
            aluminum += 9 * city['aluminumrefinery'] * (1 + ((0.5 * (city['aluminumrefinery'] - 1)) / (5 - 1))) * alu_mod

            rss_upkeep += 3500 * city['munitionsfactory'] * rss_upkeep_mod
            pollution += 32 * city['munitionsfactory'] * manu_poll_mod
            lead -= 6 * city['munitionsfactory'] * (1 + ((0.5 * (city['munitionsfactory'] - 1)) / (5 - 1))) * mun_mod
            munitions += 18 * city['munitionsfactory'] * (1 + ((0.5 * (city['munitionsfactory'] - 1)) / (5 - 1))) * mun_mod
                
            civil_upkeep += city['policestation'] * 750 
            civil_upkeep += city['hospital'] * 1000 
            civil_upkeep += city['recyclingcenter'] * 2500 
            civil_upkeep += city['subway'] * 3250 
            civil_upkeep += city['supermarket'] * 600 
            civil_upkeep += city['bank'] * 1800 
            civil_upkeep += city['mall'] * 5400
            civil_upkeep += city['stadium'] * 12150 

            police_stations = city['policestation']
            hospitals = city['hospital']

            pollution += city['policestation']
            pollution += city['hospital'] * 4
            pollution -= city['recyclingcenter'] * rec_poll
            pollution -= city['subway'] * subw_poll_red
            pollution += city['mall'] * 2
            pollution += city['stadium'] * 5

            city['real_pollution'] = pollution
            if pollution < 0:
                pollution = 0
            city['pollution'] = pollution

            commerce += city['subway'] * 8
            commerce += city['supermarket'] * 3 
            commerce += city['bank'] * 5 
            commerce += city['mall'] * 9
            commerce += city['stadium'] * 12 

            city['real_commerce'] = commerce
            if commerce > max_commerce:
                commerce = max_commerce
            city['commerce'] = commerce

        else:
            police_stations = 0
            hospitals = 0

        crime_rate = ((103 - commerce)**2 + (city['infrastructure'] * 100))/(111111) - police_stations * pol_cri_red
        city['real_crime_rate'] = crime_rate
        if crime_rate < 0:
            crime_rate = 0
        city['crime_rate'] = crime_rate
        crime_deaths = ((crime_rate) / 10) * (100 * city['infrastructure']) - 25
        disease_rate = (((((base_pop / city['land'])**2) * 0.01) - 25)/100) + (base_pop/100000) + pollution * 0.05 - hospitals * hos_dis_red
        city['real_disease_rate'] = disease_rate
        if disease_rate > 100:
            disease_rate = 100
        elif disease_rate < 0:
            disease_rate = 0
        city['disease_rate'] = disease_rate
        disease_deaths = base_pop * (disease_rate/100)
        if disease_deaths < 0:
            disease_deaths = 0
        city_age = (datetime.utcnow() - datetime.strptime(city['date'], "%Y-%m-%d")).days
        if city_age == 0:
            city_age = 1
        population = ((base_pop - disease_deaths - crime_deaths) * (1 + math.log(city_age)/15))
        nationpop += population
        money_income += (((commerce / 50) * 0.725) + 0.725) * population
    
    alliance_treasures = 0
    nation_treasure_bonus = 1
    for treasure in treasures:
        if treasure['nation'] == None:
            continue
        if treasure['nation']['id'] == nation['id']:
            nation_treasure_bonus += treasure['bonus'] / 100
        if nation['alliance']:
            if treasure['nation']['alliance_id'] == nation['alliance_id']:
                alliance_treasures += 1
    if alliance_treasures > 0:
        nation_treasure_bonus += math.sqrt(alliance_treasures * 4) / 100
    if nation_treasure_bonus > 1:
        treasure_text = f"\n\nTreasure Bonus: ${round(money_income * (nation_treasure_bonus - 1)):,}"
    
    if not single_city:
        color_bonus = colors[nation['color']]
        color_text = f"\n\nColor Trade Bloc Bonus: ${round(color_bonus):,}"
    food -= nationpop / 1000

    if nation['num_cities'] < 11:
        new_player_bonus = 2.1 - 0.1 * nation['num_cities']
        new_player_text = f"\n\nNew Player Bonus: ${round((new_player_bonus - 1) * money_income):,}"
    if nation['dompolicy'] == "Open Markets":
        policy_bonus = 1.01
        policy_bonus_text = f"\n\nOpen Markets Bonus: ${round(money_income * 0.01):,}"
    
    at_war = False
    if not single_city:
        for war in nation['wars']:
            if war['turnsleft'] > 0:
                at_war = True
        if include_spies: 
            military_upkeep += await spy_calc(nation) * 2400
        if not at_war:
            military_upkeep += nation['soldiers'] * 1.25
            food -= nation['soldiers'] / 750
            military_upkeep += nation['tanks'] * 50
            military_upkeep += nation['aircraft'] * 500
            military_upkeep += nation['ships'] * 3375
            military_upkeep += nation['missiles'] * 21000
            military_upkeep += nation['nukes'] * 35000
        else:
            military_upkeep += nation['soldiers'] * 1.88
            food -= nation['soldiers'] / 500
            military_upkeep += nation['tanks'] * 75
            military_upkeep += nation['aircraft'] * 750
            military_upkeep += nation['ships'] * 5062.50
            military_upkeep += nation['missiles'] * 31500 
            military_upkeep += nation['nukes'] * 52500
    else:
        military_upkeep += int(city['barracks']) * 3000 * 1.25
        military_upkeep += int(city['factory']) * 250 * 50
        military_upkeep += int(city['airforcebase']) * 15 * 500
        military_upkeep += int(city['drydock']) * 5 * 3750

    if nation['dompolicy'] == "Imperialism":
        mil_cost = 0.95
        policy_bonus_text = f"\n\nImperialism Bonus: ${round(military_upkeep * 0.05):,}"
    if food < 0:
        starve_exp_text = f"\n\nPossible Starvation Penalty: ${round(money_income * policy_bonus * new_player_bonus * 0.33):,}*"
        starve_money_text = f" (${round(money_income * policy_bonus * new_player_bonus * 0.67 + color_bonus - power_upkeep - rss_upkeep - military_upkeep * mil_cost - civil_upkeep):,}*)"
        starve_net_text = f" (${round(money_income * policy_bonus * new_player_bonus * 0.67 + color_bonus - power_upkeep - rss_upkeep - military_upkeep * mil_cost - civil_upkeep + coal * prices['coal'] + oil * prices['oil'] + uranium * prices['uranium'] + lead * prices['lead'] + iron * prices['iron'] + bauxite * prices['bauxite'] + gasoline * prices['gasoline'] + munitions * prices['munitions'] + steel * prices['steel'] + aluminum * prices['aluminum'] + food * prices['food']):,}*)"
        footer = "* The income if the nation is suffering from a starvation penalty"
    
    max_infra = sorted(nation['cities'], key=lambda k: k['infrastructure'], reverse=True)[0]['infrastructure']

    if single_city:
        rev_obj = nation['cities'][0]
    else:
        rev_obj = {}
    rev_obj['monetary_net_num'] = round(money_income * policy_bonus * new_player_bonus * nation_treasure_bonus + color_bonus - power_upkeep - rss_upkeep - military_upkeep * mil_cost - civil_upkeep + coal * prices['coal'] + oil * prices['oil'] + uranium * prices['uranium'] + lead * prices['lead'] + iron * prices['iron'] + bauxite * prices['bauxite'] + gasoline * prices['gasoline'] + munitions * prices['munitions'] + steel * prices['steel'] + aluminum * prices['aluminum'] + food * prices['food'])
    rev_obj['net_cash_num'] = round(money_income * policy_bonus * new_player_bonus * nation_treasure_bonus + color_bonus - power_upkeep - rss_upkeep - military_upkeep * mil_cost - civil_upkeep)
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
        rev_obj['disease_rate'] = disease_rate
        rev_obj['crime_rate'] = crime_rate
        rev_obj['commerce'] = commerce
        rev_obj['pollution'] = pollution
        return rev_obj
    else:
        rev_obj['nation'] = nation
    rev_obj['footer'] = footer
    rev_obj['max_infra'] = max_infra
    rev_obj['avg_infra'] = round(total_infra / nation['num_cities'])
    rev_obj['income_txt']=f"National Tax Revenue: ${round(money_income):,}{color_text}{new_player_text}{policy_bonus_text}{treasure_text}\n\u200b"
    rev_obj['expenses_txt']=f"Power Plant Upkeep: ${round(power_upkeep):,}\n\nResource Prod. Upkeep: ${round(rss_upkeep):,}\n\nMilitary Upkeep: ${round(military_upkeep * mil_cost):,}\n\nCity Improvement Upkeep: ${round(civil_upkeep):,}{starve_exp_text}\n\u200b"
    rev_obj['net_rev_txt']=f"Coal: {round(coal):,}\nOil: {round(oil):,}\nUranium: {round(uranium):,}\nLead: {round(lead):,}\nIron: {round(iron):,}\nBauxite: {round(bauxite):,}\nGasoline: {round(gasoline):,}\nMunitions: {round(munitions):,}\nSteel: {round(steel):,}\nAluminum: {round(aluminum):,}\nFood: {round(food):,}\nMoney: ${round(money_income * policy_bonus * new_player_bonus * nation_treasure_bonus + color_bonus - power_upkeep - rss_upkeep - military_upkeep * mil_cost - civil_upkeep):,}{starve_money_text}\n\u200b"
    rev_obj['mon_net_txt']=f"${round(money_income * policy_bonus * new_player_bonus * nation_treasure_bonus + color_bonus - power_upkeep - rss_upkeep - military_upkeep * mil_cost - civil_upkeep + coal * prices['coal'] + oil * prices['oil'] + uranium * prices['uranium'] + lead * prices['lead'] + iron * prices['iron'] + bauxite * prices['bauxite'] + gasoline * prices['gasoline'] + munitions * prices['munitions'] + steel * prices['steel'] + aluminum * prices['aluminum'] + food * prices['food']):,}{starve_net_text}"
    rev_obj['money_txt']=f"${round(money_income * policy_bonus * new_player_bonus * nation_treasure_bonus + color_bonus - power_upkeep - rss_upkeep - military_upkeep * mil_cost - civil_upkeep):,}{starve_money_text}"
    return rev_obj

async def spy_calc(nation: dict) -> int:
    """
    Nation must include 'warpolicy', 'cia' and 'id'
    """
    async with aiohttp.ClientSession() as session:
        if nation['warpolicy'] == "Arcane":
            percent = 57.5
        elif nation['warpolicy'] == "Tactician":
            percent = 42.5
        else:
            percent = 50
        upper_lim = 60
        lower_lim = 0
        while True:
            spycount = math.floor((upper_lim + lower_lim)/2)
            async with session.get(f"https://politicsandwar.com/war/espionage_get_odds.php?id1=341326&id2={nation['id']}&id3=0&id4=1&id5={spycount}") as probability:
                probability = await probability.text()
            #print(probability, spycount, upper_lim, lower_lim)
            if "Greater than 50%" in probability:
                upper_lim = spycount
            else:
                lower_lim = spycount
            if upper_lim - 1 == lower_lim:
                break
        enemyspy = round((((100*int(spycount))/(percent-25))-2)/3)
        if enemyspy > 60:
            enemyspy = 60
        elif enemyspy > 50 and not nation['cia']:
            enemyspy = 50
        elif enemyspy < 2:
            enemyspy = 0
    return enemyspy

import sys
from types import ModuleType, FunctionType
from gc import get_referents

# Custom objects know their class.
# Function objects seem to know way too much, including modules.
# Exclude modules as well.
BLACKLIST = type, ModuleType, FunctionType

def getsize(obj):
    """sum size of object & members."""
    if isinstance(obj, BLACKLIST):
        raise TypeError('getsize() does not take argument of type: '+ str(type(obj)))
    seen_ids = set()
    size = 0
    objects = [obj]
    while objects:
        need_referents = []
        for obj in objects:
            if not isinstance(obj, BLACKLIST) and id(obj) not in seen_ids:
                seen_ids.add(id(obj))
                size += sys.getsizeof(obj)
                need_referents.append(obj)
        objects = get_referents(*need_referents)
    return size