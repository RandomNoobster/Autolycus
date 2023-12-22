from __future__ import annotations

from datetime import datetime, timedelta
import math
from typing import Awaitable, Union
from cache import AsyncTTL
from functools import reduce
from operator import mul
from cachetools import TTLCache
from ...types import DomesticPolicy, Continent, ResourceEnum, Nation, ColorBloc, Color, Radiation
from .. import execute_query
from . import SHIPS_PER_DRYDOCK, AIRCRAFT_PER_HANGAR, TANKS_PER_FACTORY, SOLDIERS_PER_BARRACKS


__all__ = (
    'seasonal_food_modifier',
    'radiation_modifier',
    'food_produced',
    'population_food_consumed',
    'soldiers_food_consumed',
    'food_consumed',
    'coal_produced',
    'steel_mill_coal_consumed',
    'resource_consumed_by_power',
    'coal_consumed',
    'oil_produced',
    'gasoline_refinery_oil_consumed',
    'oil_consumed',
    'uranium_produced',
    'uranium_consumed',
    'iron_produced',
    'iron_consumed',
    'bauxite_produced',
    'bauxite_consumed',
    'lead_produced',
    'lead_consumed',
    'gasoline_produced',
    'munitions_produced',
    'steel_produced',
    'aluminum_produced',
    'power_plant_upkeep',
    'resource_production_upkeep',
    'civil_city_improvement_upkeep',
    'military_upkeep',
    'military_buildings_upkeep',
    'pollution',
    'base_population',
    'uncapped_commerce',
    'capped_commerce',
    'uncapped_crime_rate',
    'capped_crime_rate',
    'crime_deaths',
    'uncapped_disease_rate',
    'capped_disease_rate',
    'disease_deaths',
    'real_population',
    'money_from_population',
    'personal_treasure_bonus',
    'alliance_treasure_bonus',
    'total_treasure_bonus',
    'color_bonus',
    'new_player_bonus',
    'total_money_revenue',
    'get_game_date',
)


def get_game_date() -> datetime:
    """
    Returns the current game date.
    """
    real = datetime.utcnow().timestamp()
    singularity = 1498384800
    return datetime.fromtimestamp(singularity) + timedelta(days=math.floor((real - singularity) / 7200))


def seasonal_food_modifier(continent: Continent, date: datetime) -> float:
    if continent == Continent.ANTARCTICA:
        return 0.5
    month = date.month
    if month in [6, 7, 8]:
        if continent in [Continent.NORTH_AMERICA, Continent.ASIA, Continent.EUROPE]:
            return 1.2
        elif continent in [Continent.SOUTH_AMERICA, Continent.AFRICA, Continent.AUSTRALIA]:
            return 0.8
    elif month in [12, 1, 2]:
        if continent in [Continent.NORTH_AMERICA, Continent.ASIA, Continent.EUROPE]:
            return 0.8
        elif continent in [Continent.SOUTH_AMERICA, Continent.AFRICA, Continent.AUSTRALIA]:
            return 1.2
    return 1


@AsyncTTL(time_to_live=60, maxsize=8)
async def radiation_modifier(continent: Continent) -> Awaitable[float]:
    radiation = Radiation(await execute_query("SELECT * FROM radiation"))
    # TODO not sure if I have to include global here as well
    return 1 - radiation.__getattribute__(continent.value[1].lower()) / 1000


def food_produced(land: int, farms: int, continent: Continent, date: datetime, mass_irrigation: bool, fallout_shelter: bool) -> float:
    """
    Returns the amount of food produced per day.
    """
    return max(land / (500 - 100 * int(mass_irrigation)) * (1 + ((0.5 * (farms - 1)) / (20 - 1))) * seasonal_food_modifier(continent, date) * max(radiation_modifier(continent), 0.1 * int(fallout_shelter)) * 12, 0)


def population_food_consumed(population: int) -> float:
    """
    Returns the amount of food consumed per day.
    """
    return population / 1000


def soldiers_food_consumed(soldiers: int, at_war: bool) -> float:
    """
    Returns the amount of food consumed per day.
    """
    return soldiers / (750 - 250 * int(at_war))


def food_consumed(population: int, soldiers: int, at_war: bool) -> float:
    """
    Returns the amount of food consumed per day.
    """
    return population_food_consumed(population) + soldiers_food_consumed(soldiers, at_war)


def coal_produced(coal_mines: int) -> float:
    """
    Returns the amount of coal produced per day.
    """
    return coal_mines * 3 * (1 + ((0.5 * (coal_mines - 1)) / (10 - 1)))


def steel_mill_coal_consumed(steel_mills: int, ironworks: bool) -> float:
    """
    Returns the amount of coal consumed by steel mills per day.
    """
    return (steel_mills * 3 * (1 + ((0.5 * (steel_mills - 1)) / (5 - 1)))) * (1 + 0.36 * int(ironworks))


def resource_consumed_by_power(infrastructure: float, wind_power: int, nuclear_power: int, oil_power: int, coal_power: int, resource: Union[ResourceEnum.URANIUM, ResourceEnum.OIL, ResourceEnum.COAL]) -> float:
    """
    Returns the amount of infrastructure powered by resources per day.
    """
    power = {}
    for _ in range(wind_power):
        if infrastructure > 0:
            infrastructure -= 250
    for _ in range(nuclear_power):
        if infrastructure > 0:
            infrastructure -= 1000
            power[ResourceEnum.URANIUM] = power.get(
                ResourceEnum.URANIUM, 0) + 2.4
    for _ in range(oil_power):
        if infrastructure > 0:
            infrastructure -= 100
            power[ResourceEnum.OIL] = power.get(ResourceEnum.OIL, 0) + 1.2
    for _ in range(coal_power):
        if infrastructure > 0:
            infrastructure -= 100
            power[ResourceEnum.COAL] = power.get(ResourceEnum.COAL, 0) + 1.2
    return power.get(resource, 0)


def coal_consumed(steel_mills: int, ironworks: bool, infrastructure: float, wind_power: int, nuclear_power: int, oil_power: int, coal_power: int) -> float:
    """
    Returns the amount of coal consumed per day.
    """
    return steel_mill_coal_consumed(steel_mills, ironworks) + resource_consumed_by_power(infrastructure, wind_power, nuclear_power, oil_power, coal_power, ResourceEnum.COAL)


def oil_produced(oil_wells: int) -> float:
    """
    Returns the amount of oil produced per day.
    """
    return oil_wells * 3 * (1 + ((0.5 * (oil_wells - 1)) / (10 - 1)))


def gasoline_refinery_oil_consumed(gasoline_refineries: int, emergency_gasoline_reserve: bool) -> float:
    """
    Returns the amount of oil consumed by gasoline refineries per day.
    """
    return (gasoline_refineries * 3 * (1 + ((0.5 * (gasoline_refineries - 1)) / (5 - 1)))) * (1 + 1 * int(emergency_gasoline_reserve))


def oil_consumed(gasoline_refineries: int, emergency_gasoline_reserve: bool, infrastructure: float, wind_power: int, nuclear_power: int, oil_power: int, coal_power: int) -> float:
    """
    Returns the amount of oil consumed per day.
    """
    return gasoline_refinery_oil_consumed(gasoline_refineries, emergency_gasoline_reserve) + resource_consumed_by_power(infrastructure, wind_power, nuclear_power, oil_power, coal_power, ResourceEnum.OIL)


def uranium_produced(uranium_mines: int, uranium_enrichment_program: bool) -> float:
    """
    Returns the amount of uranium produced per day.
    """
    return uranium_mines * 3 * (1 + ((0.5 * (uranium_mines - 1)) / (5 - 1))) * (1 + 1 * int(uranium_enrichment_program))


def uranium_consumed(infrastructure: float, wind_power: int, nuclear_power: int, oil_power: int, coal_power: int) -> float:
    """
    Returns the amount of uranium consumed per day.
    """
    return resource_consumed_by_power(infrastructure, wind_power, nuclear_power, oil_power, coal_power, ResourceEnum.URANIUM)


def iron_produced(iron_mines: int) -> float:
    """
    Returns the amount of iron produced per day.
    """
    return iron_mines * 3 * (1 + ((0.5 * (iron_mines - 1)) / (10 - 1)))


def iron_consumed(steel_mills: int, ironworks: bool) -> float:
    """
    Returns the amount of iron consumed per day.
    """
    return steel_mills * 3 * (1 + ((0.5 * (steel_mills - 1)) / (5 - 1))) * (1 + 0.36 * int(ironworks))


def bauxite_produced(bauxite_mines: int) -> float:
    """
    Returns the amount of bauxite produced per day.
    """
    return bauxite_mines * 3 * (1 + ((0.5 * (bauxite_mines - 1)) / (10 - 1)))


def bauxite_consumed(aluminum_refineries: int, bauxiteworks: bool) -> float:
    """
    Returns the amount of bauxite consumed per day.
    """
    return aluminum_refineries * 3 * (1 + ((0.5 * (aluminum_refineries - 1)) / (5 - 1))) * (1 + 0.36 * int(bauxiteworks))


def lead_produced(lead_mines: int) -> float:
    """
    Returns the amount of lead produced per day.
    """
    return lead_mines * 3 * (1 + ((0.5 * (lead_mines - 1)) / (10 - 1)))


def lead_consumed(munitions_factories: int, arms_stockpile: bool) -> float:
    """
    Returns the amount of lead consumed per day.
    """
    return munitions_factories * 6 * (1 + ((0.5 * (munitions_factories - 1)) / (5 - 1))) * (1 + 0.36 * int(arms_stockpile))


def gasoline_produced(gasoline_refineries: int, emergency_gasoline_reserve: bool) -> float:
    """
    Returns the amount of gasoline produced per day.
    """
    return gasoline_refineries * 6 * (1 + ((0.5 * (gasoline_refineries - 1)) / (10 - 1))) * (1 + 1 * int(emergency_gasoline_reserve))


def munitions_produced(munitions_factories: int, arms_stockpile: bool) -> float:
    """
    Returns the amount of munitions produced per day.
    """
    return munitions_factories * 18 * (1 + ((0.5 * (munitions_factories - 1)) / (10 - 1))) * (1 + 1 * int(arms_stockpile))


def steel_produced(steel_mills: int, ironworks: bool) -> float:
    """
    Returns the amount of steel produced per day.
    """
    return steel_mills * 9 * (1 + ((0.5 * (steel_mills - 1)) / (10 - 1))) * (1 + 0.36 * int(ironworks))


def aluminum_produced(aluminum_refineries: int, bauxiteworks: bool) -> float:
    """
    Returns the amount of aluminum produced per day.
    """
    return aluminum_refineries * 9 * (1 + ((0.5 * (aluminum_refineries - 1)) / (10 - 1))) * (1 + 0.36 * int(bauxiteworks))


def power_plant_upkeep(wind_power: int, nuclear_power: int, oil_power: int, coal_power: int) -> float:
    """
    Returns the amount of money spent on power plant upkeep per day.
    """
    return (wind_power * 500) + (nuclear_power * 10500) + (oil_power * 1800) + (coal_power * 1200)


def resource_production_upkeep(coal_mines: int, oil_wells: int, uranium_mines: int, iron_mines: int, bauxite_mines: int, lead_mines: int, farms: int, steel_mills: int, aluminum_refineries: int, munitions_factories: int, gasoline_refineries: int, green_technologies: bool) -> float:
    """
    Returns the amount of money spent on resource production upkeep per day.
    """
    return ((coal_mines * 400) + (oil_wells * 600) + (uranium_mines * 5000) + (iron_mines * 1600) + (bauxite_mines * 1600) + (lead_mines * 1500) + (farms * 300) + (steel_mills * 4000) + (aluminum_refineries * 2500) + (munitions_factories * 3500) + (gasoline_refineries * 4000)) * (1 - 0.1 * int(green_technologies))


def civil_city_improvement_upkeep(police_station: int, hospital: int, recycling_center: int, subway: int, supermarket: int, bank: int, shopping_mall: int, stadium: int) -> float:
    """
    Returns the amount of money spent on city improvement upkeep per day.
    """
    return (police_station * 750) + (hospital * 1000) + (recycling_center * 2500) + (subway * 3250) + (supermarket * 600) + (bank * 1800) + (shopping_mall * 5400) + (stadium * 12150)


def military_upkeep(soldiers: int = 0, tanks: int = 0, aircraft: int = 0, ships: int = 0, spies: int = 0, missiles: int = 0, nukes: int = 0, imperialism: bool = False, at_war: bool = False) -> float:
    """
    Returns the amount of money spent on military upkeep per day.
    """
    if at_war:
        return ((soldiers * 1.88) + (tanks * 75) + (aircraft * 750) + (ships * 5062.5) + (spies * 2400) + (missiles * 31500) + (nukes * 52500)) * (1 - 0.05 * int(imperialism))
    else:
        return ((soldiers * 1.25) + (tanks * 50) + (aircraft * 500) + (ships * 3375) + (spies * 2400) + (missiles * 21000) + (nukes * 35000)) * (1 - 0.05 * int(imperialism))


def military_buildings_upkeep(barracks: int, factory: int, hangar: int, drydock: int, at_war: bool, imperialism: bool = False) -> float:
    """
    Returns the amount of money spent on upkeep for the units that live in certain buildings.
    """
    return military_upkeep(barracks * SOLDIERS_PER_BARRACKS, factory * TANKS_PER_FACTORY, hangar * AIRCRAFT_PER_HANGAR, drydock * SHIPS_PER_DRYDOCK, 0, 0, 0, imperialism, at_war)


# disregards nukes
def pollution(oil_power: int, coal_power: int, coal_mines: int, oil_wells: int, uranium_mines: int, iron_mines: int, bauxite_mines: int, lead_mines: int, farms: int, steel_mills: int, aluminum_refineries: int, munitions_factories: int, gasoline_refineries: int, subway: int, police_stations: int, hospitals: int, recycling_centers: int, shopping_malls: int, stadiums: int, green_technologies: bool, recycling_initiative: bool) -> float:
    """
    Returns the amount of pollution with the given improvements and national projects.
    """
    return (oil_power * 6) + (coal_power * 8) + (coal_mines * 12) + (oil_wells * 12) + (uranium_mines * 20) + (iron_mines * 12) + (bauxite_mines * 12) + (lead_mines * 12) + (farms * 4 * (1 - 0.5 * int(green_technologies))) + ((steel_mills * 40) + (aluminum_refineries * 40) + (munitions_factories * 32) + (gasoline_refineries * 32)) * (1 - 0.25 * int(green_technologies)) + (- subway * (20 + 25 * int(green_technologies))) + (police_stations * 1) + (hospitals * 4) + (- recycling_centers * (70 + 5 * int(recycling_initiative))) + (shopping_malls * 2) + (stadiums * 5)


def base_population(infrastructure: float) -> float:
    """
    Returns the base population.
    """
    return infrastructure * 100


def uncapped_commerce(supermarkets: int, banks: int, shopping_malls: int, stadiums: int, subway: int, telecommunications_satellite: bool):
    """
    Returns the amount of uncapped commerce with the given improvements and national projects.
    """
    return (supermarkets * 2) + (banks * 6) + (shopping_malls * 18) + (stadiums * 30) + (subway * 10) + (2 * int(telecommunications_satellite))


def capped_commerce(uncapped_commerce: float, international_trade_center: bool, telecommunications_satellite: bool):
    """
    Returns the amount of capped commerce with the given improvements and national projects.
    """
    if telecommunications_satellite:
        cap = 125
    elif international_trade_center:
        cap = 115
    else:
        cap = 100
    return min(uncapped_commerce, cap)


def uncapped_crime_rate(commerce: int, infrastructure: float, police_stations: int, specialized_police_training_program: bool):
    """
    Returns the uncapped crime rate. Returns a number between 0 and 100. To get the actual crime rate, divide by 100.
    """
    return ((103 - commerce)**2 + base_population(infrastructure))/(111111) - police_stations * (2.5 + 1 * int(specialized_police_training_program))


def capped_crime_rate(uncapped_crime_rate: float):
    """
    Returns the capped crime rate. Returns a number between 0 and 100. To get the actual crime rate, divide by 100.
    """
    return max(min(uncapped_crime_rate, 100), 0)


def crime_deaths(infrastructure: int, crime_rate: float):
    """
    Returns the amount of deaths due to crime. Crime rate should be between 0 and 100.
    """
    return ((crime_rate) / 10) * (100 * infrastructure) - 25


def uncapped_disease_rate(hospitals: int, infrastructure: float, pollution: float, clinical_research_center: bool, land: float) -> float:
    """
    Returns the uncapped disease rate. Returns a number between 0 and 100. To get the actual disease rate, divide by 100.
    """
    return (((((base_population(infrastructure) / land)**2) * 0.01) - 25)/100) + (base_population(infrastructure)/100000) + pollution * 0.05 - hospitals * (2.5 + 1 * int(clinical_research_center))


def capped_disease_rate(uncapped_disease_rate: float):
    """
    Returns the capped disease rate. Returns a number between 0 and 100. To get the actual disease rate, divide by 100.
    """
    return max(min(uncapped_disease_rate, 100), 0)


def disease_deaths(infrastructure: int, disease_rate: float) -> float:
    """
    Returns the amount of deaths due to disease. Disease rate should be between 0 and 100.
    """
    return base_population(infrastructure) * (disease_rate / 100)


def real_population(infrastructure: int, disease_rate: float, crime_rate: float, city_age: int) -> float:
    """
    Returns the real population. Disease rate and crime rate should be between 0 and 100.
    """
    return ((base_population(infrastructure) - disease_deaths(infrastructure, disease_rate) - crime_deaths(infrastructure, crime_rate)) * (1 + math.log(city_age)/15))


def money_from_population(commerce: int, real_population: int):
    """
    Returns the amount of money produced per day.
    """
    return (((commerce / 50) * 0.725) + 0.725) * real_population


async def personal_treasure_bonus(nation: Nation) -> Awaitable[float]:
    """
    Returns the personal treasure bonus.
    """
    treasures = await nation.treasures
    return reduce(mul, [1 + x.bonus/100 for x in treasures])


async def alliance_treasure_bonus(nation: Nation) -> Awaitable[float]:
    """
    Returns the alliance treasure bonus.
    """
    treasures = await (await nation.alliance)._treasures
    return 1 + math.sqrt(treasures * 4) / 100


async def total_treasure_bonus(nation: Nation) -> Awaitable[float]:
    """
    Returns the total treasure bonus.
    """
    return await personal_treasure_bonus(nation) * await alliance_treasure_bonus(nation)


@AsyncTTL(time_to_live=60, maxsize=16)
async def color_bonus(color: Color) -> Awaitable[float]:
    """
    Returns the color bonus.
    """
    return (await execute_query(f"SELECT turn_bonus FROM colors WHERE color = {color.value[0]}")) * 12


def new_player_bonus(cities: int) -> float:
    """
    Returns the new player bonus.
    """
    return max(2.05 - 0.05 * cities, 1)


def total_money_revenue(starving: bool, open_markets: bool, money_from_population: float, treasure_bonus: float, new_player_bonus: float, color_bonus: float, power_plant_upkeep: float, resource_production_upkeep: float, military_upkeep: float, civil_city_improvement_upkeep: float) -> float:
    """
    Returns the total money revenue.
    """
    return money_from_population * treasure_bonus * new_player_bonus * (1 - 0.33 * int(starving)) * (1 + 0.01 * int(open_markets)) + color_bonus - power_plant_upkeep - resource_production_upkeep - military_upkeep - civil_city_improvement_upkeep
