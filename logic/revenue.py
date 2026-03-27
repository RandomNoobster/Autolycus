"""Revenue and economic calculations for nation gameplay.

This module contains core economic simulation functions that calculate
nation income, resource production, population effects, and military upkeep.
These functions work with game data and are independent of Discord or database layer.

Reference: pwpedia_data.jsonl for all game mechanics and formulas.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from typing import Any, Optional, Tuple

import discord

from api.cache import cache_game_context

from .common import weird_division

logger = logging.getLogger(__name__)


@cache_game_context(ttl=600)  # Cache for 10 minutes - game context changes slowly
async def get_cached_game_context(
    call_func,
    get_query_func,
    queries_module,
) -> Tuple[dict[str, float], dict[str, float], list[dict[str, Any]], dict[str, float], dict[str, float]]:
    """Fetch and cache shared game context data.
    
    This function caches the expensive P&W API call that fetches:
    - Color turn bonuses
    - Trade prices  
    - Treasures list
    - Radiation levels
    - Seasonal modifiers
    
    Returns:
        Tuple of (colors, prices, treasures, radiation, seasonal_mod)
        
    Note: Cache TTL is 10 minutes. This data changes slowly so caching
    significantly reduces P&W API load across multiple requests.
    """
    logger.debug("Fetching fresh game context from P&W API (cache miss or expired)")
    
    # Build the GraphQL query
    prices_query = get_query_func(queries_module.PRICES)
    query = f"{{colors{{color turn_bonus}} game_info{{game_date radiation{{global north_america south_america africa europe asia australia antarctica}}}} tradeprices(first:1){{data{prices_query}}} treasures{{bonus nation{{id alliance_id}}}}}}"
    res = await call_func(query)
    
    # Parse color turn bonuses
    res_colors = res['data']['colors']
    colors = {}
    for color in res_colors:
        colors[color['color']] = color['turn_bonus'] * 12
    
    # Parse resource prices
    prices = res['data']['tradeprices']['data'][0]
    prices['money'] = 1
    
    treasures = res['data']['treasures']
    game_info = res['data']['game_info']
    
    # Parse radiation by region
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
    
    # Calculate seasonal modifiers based on game month
    month = int(game_info['game_date'][5:7])
    seasonal_mod = {"na": 1, "sa": 1, "eu": 1, "as": 1, "af": 1, "au": 1, "an": 0.5}
    if month in (6, 7, 8):
        seasonal_mod.update({'na': 1.2, 'as': 1.2, 'eu': 1.2, 'sa': 0.8, 'af': 0.8, 'au': 0.8})
    elif month in (12, 1, 2):
        seasonal_mod.update({'na': 0.8, 'as': 0.8, 'eu': 0.8, 'sa': 1.2, 'af': 1.2, 'au': 1.2})
    
    return colors, prices, treasures, radiation, seasonal_mod


async def pre_revenue_calc(
    message: Optional[discord.Message],
    query_for_nation: bool = False,
    nationid: Optional[int | str] = None,
    parsed_nation: Optional[dict[str, Any]] = None,
    call_func=None,
    get_query_func=None,
    queries_module=None,
):
    """Fetch game data needed for revenue calculations.
    
    Retrieves color bonuses, radiation, trade prices, treasures, and game date
    to support comprehensive nation revenue analysis.
    
    Args:
        message: Discord message to edit with status updates
        query_for_nation: If True, fetch nation from P&W API by ID
        nationid: Nation ID to query (used if query_for_nation=True)
        parsed_nation: Pre-fetched nation data (alternative to query_for_nation)
        call_func: Function to call P&W GraphQL API (from api_client)
        get_query_func: Function to build GraphQL queries (from merge_utils)
        queries_module: Queries module with query definitions
        
    Returns:
        Tuple of (nation, colors, prices, treasures, radiation, seasonal_mod)
        
    Note: Game context (colors, prices, treasures, radiation, seasonal_mod) is
    cached for 10 minutes via get_cached_game_context() to reduce API calls.
    """
    if call_func is None or get_query_func is None or queries_module is None:
        raise ValueError("call_func, get_query_func, and queries_module are required")
    
    if query_for_nation:
        nation = (await call_func(
            f"{{nations(first:1 id:{nationid}){{data{get_query_func(queries_module.REVENUE)}}}}}"
        ))['data']['nations']['data']
        if len(nation) == 0:
            raise ValueError("Nation not found in API")
        nation = nation[0]
    else:
        nation = parsed_nation

    if message is not None:
        await message.edit(content="Getting income modifiers...")
    
    # Use cached game context to reduce P&W API calls
    colors, prices, treasures, radiation, seasonal_mod = await get_cached_game_context(
        call_func, get_query_func, queries_module
    )
    
    return nation, colors, prices, treasures, radiation, seasonal_mod


def calculate_nation_modifiers(nation: dict[str, Any]) -> dict[str, float]:
    """Calculate all economic and production modifiers for a nation.
    
    Per PWPedia: Policies, government projects, and infrastructure provide
    various production and cost multipliers.
    
    Args:
        nation: Nation data from P&W API
        
    Returns:
        Dict with modifier values for economics, production, costs, etc.
    """
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
    """Calculate power generation and consumption for a city.
    
    Per PWPedia: Power plants generate power to support infrastructure.
    Different plant types have different upkeeps and pollution.
    
    Args:
        city: City data from nation structure
        
    Returns:
        Dict with unpowered_infra, power_upkeep, and resource consumption
    """
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
    """Calculate raw resource production for a city.
    
    Per PWPedia: Mining operations produce coal, oil, uranium, lead, iron, bauxite.
    
    Args:
        city: City data from nation structure
        modifiers: Nation modifier dict (from calculate_nation_modifiers)
        
    Returns:
        Dict with resource production amounts and upkeep
    """
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
    """Calculate food production based on farms, land, and modifiers.
    
    Per PWPedia: Food production affected by season, radiation, and farm count.
    
    Args:
        city: City data from nation structure
        nation: Nation data (for continent/continent data)
        modifiers: Nation modifier dict
        seasonal_mod: Seasonal modifiers by region
        radiation: Radiation effects by region
        
    Returns:
        Food production amount per day
    """
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
    """Calculate manufactured goods production for a city.
    
    Per PWPedia: Refineries and factories convert raw resources into refined goods.
    
    Args:
        city: City data from nation structure
        modifiers: Nation modifier dict
        unpowered_infra: Infrastructure without power (halts manufacturing)
        
    Returns:
        Dict with manufactured resource amounts and upkeep
    """
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
    """Calculate effects of civil improvements (hospitals, police, mall, etc).
    
    Per PWPedia: Civil structures provide commerce bonuses, reduce crime/disease,
    and some reduce pollution.
    
    Args:
        city: City data from nation structure
        modifiers: Nation modifier dict
        unpowered_infra: Infrastructure without power (halts most improvements)
        
    Returns:
        Dict with commerce, pollution, upkeep, and improvement counts
    """
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
    result['raw_commerce'] = result['commerce']
    result['commerce'] = min(result['commerce'], modifiers['max_commerce'])
    return result


def calculate_population_effects(city: dict[str, Any], modifiers: dict[str, float], base_pop: float, commerce: float, police_stations: int, hospitals: int, pollution: float) -> dict[str, float]:
    """Calculate population growth, crime, and disease effects.
    
    Per PWPedia: Crime and disease rates are affected by commerce, hospitals,
    pollution, and other factors. Population grows with city age.
    
    Args:
        city: City data including date and land
        modifiers: Nation modifier dict
        base_pop: Base population (infrastructure * 100)
        commerce: Commerce level
        police_stations: Number of police stations
        hospitals: Number of hospitals
        pollution: Total pollution level
        
    Returns:
        Dict with final population, crime/disease rates, food consumption
    """
    crime_rate_raw = (math.pow(103 - commerce, 2) + base_pop) / 111111 - police_stations * modifiers['pol_cri_red']
    crime_rate = max(crime_rate_raw, 0)
    crime_deaths = max(((crime_rate) / 10) * base_pop - 25, 0)
    population_density = base_pop / city['land']
    disease_rate_raw = (
        (((population_density ** 2) * 0.01) - 25) / 100
        + (base_pop / 100000)
        + pollution * 0.05
        - hospitals * modifiers['hos_dis_red']
    )
    disease_rate = max(0, min(disease_rate_raw, 100))
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
        'crime_rate_raw': crime_rate_raw,
        'disease_rate': disease_rate,
        'disease_rate_raw': disease_rate_raw,
        'food_consumption': food_consumption,
        'city_age_mod': city_age_mod,
    }


def calculate_military_upkeep(nation: dict[str, Any], modifiers: dict[str, float], include_spies: bool = False) -> tuple[float, float]:
    """Calculate military unit upkeep and food consumption.
    
    Per PWPedia july-2025-update:
    - Peace: Soldiers $1.25, Aircraft $750, Ships $3300
    - War: Soldiers $1.88, Aircraft $1000, Ships $5000
    
    Args:
        nation: Nation data with military units and research
        modifiers: Nation modifier dict (for mil_cost policy bonus)
        include_spies: If True, add spy upkeep ($2400 per spy)
        
    Returns:
        Tuple of (military_upkeep, food_consumption)
    """
    military_upkeep = 0.0
    food_consumption = 0.0
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
    """Calculate military building maintenance costs (not unit upkeep).
    
    Args:
        city: City data with military building counts
        
    Returns:
        Total military building upkeep cost
    """
    military_upkeep = 0.0
    military_upkeep += int(city.get('barracks', 0)) * 3000 * 1.25
    military_upkeep += int(city.get('factory', 0)) * 250 * 50
    military_upkeep += int(city.get('airforcebase', 0)) * 15 * 500
    military_upkeep += int(city.get('drydock', 0)) * 5 * 3750
    return military_upkeep


def calculate_treasure_bonus(nation: dict[str, Any], treasures: list[dict[str, Any]]) -> float:
    """Calculate income multiplier from treasures.
    
    Nation treasures provide direct income bonus, alliance treasures add small bonus.
    
    Args:
        nation: Nation data (for alliance_id)
        treasures: List of all treasures in game
        
    Returns:
        Income multiplier (e.g., 1.05 = 5% bonus)
    """
    nation_treasure_bonus = 1.0
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


async def revenue_calc(
    message: Optional[discord.Message],
    nation: dict[str, Any],
    radiation: dict[str, float],
    treasures: list[dict[str, Any]],
    prices: dict[str, float],
    colors: dict[str, float],
    seasonal_mod: dict[str, float],
    build: Optional[str] = None,
    single_city: bool = False,
    include_spies: bool = False,
) -> dict[str, Any]:
    """Calculate complete nation revenue and resource production.
    
    This is the main revenue calculation function that aggregates all city-level
    calculations into nation-wide totals, including resource gains/losses,
    income/expenses, and final net revenue.
    
    Args:
        message: Discord message to edit with status (for UI feedback)
        nation: Complete nation data from P&W API
        radiation: Regional radiation modifiers
        treasures: List of all treasures in game (for bonuses)
        prices: Current market prices for all resources
        colors: Color bonus amounts (money per turn)
        seasonal_mod: Seasonal production modifiers by continent
        build: Optional custom city build as JSON string
        single_city: If True, calculate only one city; if False, all cities
        include_spies: If True, include spy upkeep in calculations
        
    Returns:
        Dict with detailed revenue breakdown including:
        - monetary_net_num: Total money + resource values
        - net_cash_num: Cash-only revenue
        - All resources (food, fuel, etc.)
        - Formatted text fields for embeds
    """
    rss_upkeep = 0.0
    civil_upkeep = 0.0
    military_upkeep = 0.0
    money_income = 0.0
    power_upkeep = 0.0
    nationpop = 0.0
    total_infra = 0
    coal = 0.0
    oil = 0.0
    uranium = 0.0
    lead = 0.0
    iron = 0.0
    bauxite = 0.0
    gasoline = 0.0
    munitions = 0.0
    steel = 0.0
    aluminum = 0.0
    food = 0.0
    
    starve_net_text = ""
    starve_money_text = ""
    starve_exp_text = ""
    color_text = ""
    new_player_text = ""
    policy_bonus_text = ""
    treasure_text = ""
    footer = ""
    
    modifiers = calculate_nation_modifiers(nation)
    
    # Handle custom build input
    if build is not None:
        try:
            build = json.loads(build)
        except json.JSONDecodeError:
            if message is not None:
                await message.edit(content="Something is wrong with the build you sent!")
            return {}
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
    
    # Calculate per-city contributions
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
        raw_commerce = civil_result.get('raw_commerce', civil_result['commerce'])
        city['real_commerce'] = raw_commerce
        city['commerce'] = commerce

        pop_result = calculate_population_effects(
            city,
            modifiers,
            base_pop,
            raw_commerce,
            police_stations,
            hospitals,
            city['pollution'],
        )
        crime_rate_raw = (
            (math.pow(103 - raw_commerce, 2) + base_pop) / 111111
            - police_stations * modifiers['pol_cri_red']
        )
        city['real_crime_rate'] = crime_rate_raw
        city['crime_rate'] = max(crime_rate_raw, 0)
        city['real_disease_rate'] = pop_result.get('disease_rate_raw', pop_result['disease_rate'])
        city['disease_rate'] = pop_result['disease_rate']
        nationpop += pop_result['population']
        money_income += (((commerce / 50) * 0.725) + 0.725) * pop_result['population']
        food -= pop_result['food_consumption']
    
    # Apply nation-level bonuses
    nation_treasure_bonus = calculate_treasure_bonus(nation, treasures)
    if nation_treasure_bonus > 1:
        treasure_text = f"\n\nTreasure Bonus: ${round(money_income * (nation_treasure_bonus - 1)):,}"
    
    color_bonus = 0.0
    if not single_city:
        color_bonus = colors[nation['color']]
        color_text = f"\n\nColor Trade Bloc Bonus: ${round(color_bonus):,}"
    
    if modifiers['new_player_bonus'] > 1:
        new_player_text = f"\n\nNew Player Bonus: ${round((modifiers['new_player_bonus'] - 1) * money_income):,}"
    
    if modifiers['policy_bonus'] != 1 and nation.get('dompolicy') == "Open Markets":
        policy_bonus_text = f"\n\nOpen Markets Bonus: ${round(money_income * (1 - modifiers['policy_bonus'])):,}"
    
    if not single_city:
        military_upkeep_calc, food_consumption = calculate_military_upkeep(nation, modifiers, include_spies)
        military_upkeep = military_upkeep_calc
        food -= food_consumption
    else:
        military_upkeep = calculate_military_upkeep_from_buildings(city)
    
    military_upkeep *= modifiers['mil_cost']
    if modifiers['mil_cost'] != 1 and nation.get('dompolicy') == "Imperialism":
        policy_bonus_text = f"\n\nImperialism Bonus: ${round(military_upkeep * (1 - modifiers['mil_cost'])):,}"
    
    # Check for starvation penalty
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
        rev_obj['population'] = pop_result['population']
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


def revenue_calc_sync(
    nation: dict[str, Any],
    radiation: dict[str, float],
    treasures: list[dict[str, Any]],
    prices: dict[str, float],
    colors: dict[str, float],
    seasonal_mod: dict[str, float],
    build: Optional[str] = None,
    single_city: bool = False,
    include_spies: bool = False,
) -> dict[str, Any]:
    """Synchronous revenue calculation for non-Discord contexts (e.g. API routes).

    Identical calculation logic to :func:`revenue_calc`, but avoids the
    async/await overhead of creating and tearing down an event loop for every
    call.  Use this in Flask routes or other synchronous code where Discord
    message editing is not needed.

    Args:
        nation: Complete nation data from P&W API
        radiation: Regional radiation modifiers
        treasures: List of all treasures in game (for bonuses)
        prices: Current market prices for all resources
        colors: Color bonus amounts (money per turn)
        seasonal_mod: Seasonal production modifiers by continent
        build: Optional custom city build as JSON string
        single_city: If True, calculate only one city; if False, all cities
        include_spies: If True, include spy upkeep in calculations

    Returns:
        Dict with detailed revenue breakdown including:
        - monetary_net_num: Total money + resource values
        - net_cash_num: Cash-only revenue
        - All resources (food, fuel, etc.)
        - Formatted text fields for embeds
    """
    rss_upkeep = 0.0
    civil_upkeep = 0.0
    military_upkeep = 0.0
    money_income = 0.0
    power_upkeep = 0.0
    nationpop = 0.0
    total_infra = 0
    coal = 0.0
    oil = 0.0
    uranium = 0.0
    lead = 0.0
    iron = 0.0
    bauxite = 0.0
    gasoline = 0.0
    munitions = 0.0
    steel = 0.0
    aluminum = 0.0
    food = 0.0

    starve_net_text = ""
    starve_money_text = ""
    starve_exp_text = ""
    color_text = ""
    new_player_text = ""
    policy_bonus_text = ""
    treasure_text = ""
    footer = ""

    modifiers = calculate_nation_modifiers(nation)

    # Handle custom build input
    if build is not None:
        try:
            build = json.loads(build)
        except json.JSONDecodeError:
            return {}
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

    # Calculate per-city contributions
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
        raw_commerce = civil_result.get('raw_commerce', civil_result['commerce'])
        city['real_commerce'] = raw_commerce
        city['commerce'] = commerce

        pop_result = calculate_population_effects(
            city,
            modifiers,
            base_pop,
            raw_commerce,
            police_stations,
            hospitals,
            city['pollution'],
        )
        crime_rate_raw = (
            (math.pow(103 - raw_commerce, 2) + base_pop) / 111111
            - police_stations * modifiers['pol_cri_red']
        )
        city['real_crime_rate'] = crime_rate_raw
        city['crime_rate'] = max(crime_rate_raw, 0)
        city['real_disease_rate'] = pop_result.get('disease_rate_raw', pop_result['disease_rate'])
        city['disease_rate'] = pop_result['disease_rate']
        nationpop += pop_result['population']
        money_income += (((commerce / 50) * 0.725) + 0.725) * pop_result['population']
        food -= pop_result['food_consumption']

    # Apply nation-level bonuses
    nation_treasure_bonus = calculate_treasure_bonus(nation, treasures)
    if nation_treasure_bonus > 1:
        treasure_text = f"\n\nTreasure Bonus: ${round(money_income * (nation_treasure_bonus - 1)):,}"

    color_bonus = 0.0
    if not single_city:
        color_bonus = colors[nation['color']]
        color_text = f"\n\nColor Trade Bloc Bonus: ${round(color_bonus):,}"

    if modifiers['new_player_bonus'] > 1:
        new_player_text = f"\n\nNew Player Bonus: ${round((modifiers['new_player_bonus'] - 1) * money_income):,}"

    if modifiers['policy_bonus'] != 1 and nation.get('dompolicy') == "Open Markets":
        policy_bonus_text = f"\n\nOpen Markets Bonus: ${round(money_income * (1 - modifiers['policy_bonus'])):,}"

    if not single_city:
        military_upkeep_calc, food_consumption = calculate_military_upkeep(nation, modifiers, include_spies)
        military_upkeep = military_upkeep_calc
        food -= food_consumption
    else:
        military_upkeep = calculate_military_upkeep_from_buildings(city)

    military_upkeep *= modifiers['mil_cost']
    if modifiers['mil_cost'] != 1 and nation.get('dompolicy') == "Imperialism":
        policy_bonus_text = f"\n\nImperialism Bonus: ${round(military_upkeep * (1 - modifiers['mil_cost'])):,}"

    # Check for starvation penalty
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
        rev_obj['population'] = pop_result['population']
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
