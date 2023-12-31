from __future__ import annotations
import math
import re
from typing import Union
from warnings import WarningMessage
import aiohttp
from ....types import War, TradePrices, Nation, WarPolicyDetails, WarTypeDetails, WarTypeEnum, WarPolicyEnum, AttackType, MilitaryUnit, MilitaryUnitEnum, AttackSuccess, AttackerEnum, StatsEnum, WarAttackerFilter, WarActiveFilter
from ... import execute_query, weird_division
from .. import SOLDIERS_PER_BARRACKS, TANKS_PER_FACTORY, AIRCRAFT_PER_HANGAR, SHIPS_PER_DRYDOCK, BARRACKS_PER_CITY, FACTORY_PER_CITY, HANGAR_PER_CITY, DRYDOCK_PER_CITY, RESOURCES, infra_cost


def defender_fortified_modifier(defender_fortified: bool) -> float:
    """
    Returns the defender fortified modifier.
    """
    return 1 + 0.25 * int(defender_fortified)


def casualties_calculation_army_value(attacker_army_value: float, defender_army_value: float, attacker: AttackerEnum) -> float:   
    """
    Calculates the army value of the attacker or defender.
    """
    if attacker == AttackerEnum.ATTACKER:
        side_army_value = attacker_army_value
    elif attacker == AttackerEnum.DEFENDER:
        side_army_value = defender_army_value
    else:
        raise ValueError("Invalid value for attacker.")
    
    return (weird_division((attacker_army_value + defender_army_value) , (attacker_army_value ** (3/4) + defender_army_value ** (3/4)))) * side_army_value ** (3/4)


def get_army_value(soldiers: int = 0, resisting_population: float = 0, tanks: int = 0, aircraft: int = 0, ships: int = 0, using_munitions: bool = True, air_superiority: bool = False) -> float:
    """
    Calculates the army value.
    """
    return ((soldiers + resisting_population) * MilitaryUnit(MilitaryUnitEnum.SOLDIER, using_munitions=using_munitions).army_value
            + tanks * MilitaryUnit(MilitaryUnitEnum.TANK, air_superiority=air_superiority).army_value
            + aircraft * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT, air_superiority=air_superiority).army_value
            + ships * MilitaryUnit(MilitaryUnitEnum.SHIP, air_superiority=air_superiority).army_value)


def infrastructure_destroyed_modifier(war_type_details: WarTypeDetails, attacker: AttackerEnum, attacker_war_policy_details: WarPolicyDetails, defender_war_policy_details: WarPolicyDetails) -> float:
    """
    Modifies the amount of infrastructure destroyed according to policies and war types.
    :param func: The function to modify.
    :param only_war: Whether to only include war type modifiers, and not war policies.
    """
    if attacker == AttackerEnum.ATTACKER:
        war_modifier = war_type_details.attacker_infra_destroyed
    elif attacker == AttackerEnum.DEFENDER:
        war_modifier = war_type_details.defender_infra_destroyed
    else:
        raise ValueError("Invalid attacker")
    
    return (
        1
        * war_modifier
        * attacker_war_policy_details.infrastructure_damage_dealt if attacker_war_policy_details else 1
        * defender_war_policy_details.infrastructure_damage_received if defender_war_policy_details else 1)

    
async def infrastructure_destroyed_value(destroyed_infra: float, defender: Nation) -> float:
    """
    Calculates the value of infrastructure destroyed.
    """
    starting_infra = (await defender.highest_infra_city).infrastructure
    ending = starting_infra - destroyed_infra
    return infra_cost(starting_infra, ending, defender)


def recovered_by_military_salvage(attacker_used: float, defender_used: float, winrate: float) -> float:
    """
    Calculates the amount of resources recovered by military salvage.
    :param attacker_used: The amount of resources used by the attacker.
    :param defender_used: The amount of resources used by the defender.
    :param winrate: The winrate of the attacker.
    """
    return (attacker_used + defender_used) * (winrate ** 3) * 0.05


def resisting_population(population: float) -> float:
    """
    Calculates the amount of population resisting.
    """
    return population / 400
    

def scale_with_winrate(winrate: float) -> float: 
    """
    Returns a modifier that scales with the winrate.
    """
    rate = -0.4624 * winrate**2 + 1.06256 * winrate + 0.3999            
    if rate < 0.4:
        rate = 0.4
    return rate
    

def universal_winrate(attacker_army_value: float, defender_army_value: float):
    """
    Calculates the winrate of the attacker.
    """
    # TODO: redo this function

    attacker_army_value **= (3/4)
    defender_army_value **= (3/4)

    if attacker_army_value == 0 and defender_army_value == 0:
        return 0
    elif defender_army_value == 0:
        return 1
    x = attacker_army_value / defender_army_value

    # should be 2.5 and not 2 but the function would have to be redone
    if x > 2:
        winrate = 1
    elif x < 0.4:
        winrate = 0
    else:
        winrate = (12.832883444301027*x**(11)-171.668262561212487*x**(10)+1018.533858483560834*x**(9)-3529.694284997589875*x**(8)+7918.373606722701879*x**(7)-12042.696852729619422 *
                   x**(6)+12637.399722721022044*x**(5)-9128.535790660698694*x**(4)+4437.651655224382012*x**(3)-1378.156072477675025*x**(2)+245.439740545813436*x-18.980551645186498)
    return winrate


def beige_loot_value(loot_string: str, prices: TradePrices) -> int:
    loot_string = loot_string[loot_string.index(
        '$'):loot_string.index('Food.')]
    loot_string = re.sub(r"[^0-9-]+", "", loot_string.replace(", ", "-"))
    n = 0
    loot = {}
    for sub in loot_string.split("-"):
        loot[RESOURCES[n]] = int(sub)
        n += 1
    nation_loot = 0
    for rs in RESOURCES:
        amount = loot[rs]
        price = prices[rs]
        nation_loot += amount * price
    return nation_loot


def barracks_mmr(barracks: int, cities: int, decimal: int = 1) -> float:
    return round(barracks / cities, decimal)


def factory_mmr(factories: int, cities: int, decimal: int = 1) -> float:
    return round(factories / cities, decimal)


def hangar_mmr(hangars: int, cities: int, decimal: int = 1) -> float:
    return round(hangars / cities, decimal)


def drydock_mmr(drydocks: int, cities: int, decimal: int = 1) -> float:
    return round(drydocks / cities, decimal)


def population_soldiers_limit(population: int) -> int:
    return math.floor(population/6.67)


def population_tanks_limit(population: int) -> int:
    return math.floor(population/66.67)


def population_aircraft_limit(population: int) -> int:
    return math.floor(population/1000)


def population_ships_limit(population: int) -> int:
    return math.floor(population/10000)


def max_soldiers(barracks: int, population: int) -> int:
    return math.floor(min(SOLDIERS_PER_BARRACKS * barracks, population_soldiers_limit(population)))


def max_tanks(factories: int, population: int) -> int:
    return math.floor(min(TANKS_PER_FACTORY * factories, population_tanks_limit(population)))


def max_aircraft(hangars: int, population: int) -> int:
    return math.floor(min(AIRCRAFT_PER_HANGAR * hangars, population_aircraft_limit(population)))


def max_ships(drydocks: int, population: int) -> int:
    return math.floor(min(SHIPS_PER_DRYDOCK * drydocks, population_ships_limit(population)))


def max_spies(central_intelligence_agency: bool) -> int:
    return 60 if central_intelligence_agency else 50


def soldiers_daily(barracks: int, population: int, propaganda_bureau: int) -> int:
    return round(max_soldiers(barracks, population)/3) * (1.1 if propaganda_bureau else 1)


def tanks_daily(factories: int, population: int, propaganda_bureau: int) -> int:
    return round(max_tanks(factories, population)/5) * (1.1 if propaganda_bureau else 1)


def aircraft_daily(hangars: int, population: int, propaganda_bureau: int) -> int:
    return round(max_aircraft(hangars, population)/5) * (1.1 if propaganda_bureau else 1)


def ships_daily(drydocks: int, population: int, propaganda_bureau: int) -> int:
    return round(max_ships(drydocks, population)/5) * (1.1 if propaganda_bureau else 1)


def spies_daily(central_intelligence_agency: bool, spy_satellite: bool) -> int:
    return 1 + int(central_intelligence_agency) + int(spy_satellite)


def days_to_max_soldiers(soldiers: int, barracks: int, population: int, propaganda_bureau: int) -> int:
    return math.ceil(weird_division(max_soldiers(barracks, population) - soldiers, soldiers_daily(barracks, population, propaganda_bureau)))


def days_to_max_tanks(tanks: int, factories: int, population: int, propaganda_bureau: int) -> int:
    return math.ceil(weird_division(max_tanks(factories, population) - tanks, tanks_daily(factories, population, propaganda_bureau)))


def days_to_max_aircraft(aircraft: int, hangars: int, population: int, propaganda_bureau: int) -> int:
    return math.ceil(weird_division(max_aircraft(hangars, population) - aircraft, aircraft_daily(hangars, population, propaganda_bureau)))


def days_to_max_ships(ships: int, drydocks: int, population: int, propaganda_bureau: int) -> int:
    return math.ceil(weird_division(max_ships(drydocks, population) - ships, ships_daily(drydocks, population, propaganda_bureau)))


def days_to_max_spies(spies: int, central_intelligence_agency: bool, spy_satellite: bool) -> int:
    return math.ceil(weird_division(max_spies(central_intelligence_agency) - spies, spies_daily(central_intelligence_agency, spy_satellite)))


def soldiers_absolute_militarization(soldiers: int, cities: int) -> float:
    return soldiers / (cities * BARRACKS_PER_CITY * SOLDIERS_PER_BARRACKS)


def soldiers_relative_militarization(soldiers: int, barracks: int) -> float:
    return soldiers / (barracks * SOLDIERS_PER_BARRACKS)


def tanks_absolute_militarization(tanks: int, cities: int) -> float:
    return tanks / (cities * FACTORY_PER_CITY * TANKS_PER_FACTORY)


def tanks_relative_militarization(tanks: int, factories: int) -> float:
    return tanks / (factories * TANKS_PER_FACTORY)


def aircraft_absolute_militarization(aircraft: int, cities: int) -> float:
    return aircraft / (cities * HANGAR_PER_CITY * AIRCRAFT_PER_HANGAR)


def aircraft_relative_militarization(aircraft: int, hangars: int) -> float:
    return aircraft / (hangars * AIRCRAFT_PER_HANGAR)


def ships_absolute_militarization(ships: int, cities: int) -> float:
    return ships / (cities * DRYDOCK_PER_CITY * SHIPS_PER_DRYDOCK)


def ships_relative_militarization(ships: int, drydocks: int) -> float:
    return ships / (drydocks * SHIPS_PER_DRYDOCK)


def total_absolute_militarization(soldiers: int, tanks: int, aircraft: int, ships: int, cities: int) -> float:
    return (soldiers_absolute_militarization(soldiers, cities) + tanks_absolute_militarization(tanks, cities) + aircraft_absolute_militarization(aircraft, cities) + ships_absolute_militarization(ships, cities)) / 4


def total_relative_militarization(soldiers: int, barracks: int, tanks: int, factories: int, aircraft: int, hangars: int, ships: int, drydocks: int) -> float:
    return (soldiers_relative_militarization(soldiers, barracks) + tanks_relative_militarization(tanks, factories) + aircraft_relative_militarization(aircraft, hangars) + ships_relative_militarization(ships, drydocks)) / 4


@WarningMessage.deprecated("This function is deprecated. Use the spy field in `Nation` instead.")
async def spy_calc(nation: Nation) -> int:
    """
    Calculates the amount of spies a nation has.
    """
    async with aiohttp.ClientSession() as session:
        if nation.war_policy == WarPolicyEnum.ARCANE:
            percent = 57.5
        elif nation.war_policy == WarPolicyEnum.TACTICIAN:
            percent = 42.5
        else:
            percent = 50
        upper_lim = 60
        lower_lim = 0
        while True:
            spycount = math.floor((upper_lim + lower_lim)/2)
            async with session.get(f"https://politicsandwar.com/war/espionage_get_odds.php?id1=341326&id2={nation['id']}&id3=0&id4=1&id5={spycount}") as probability:
                probability = await probability.text()
            if "Greater than 50%" in probability:
                upper_lim = spycount
            else:
                lower_lim = spycount
            if upper_lim - 1 == lower_lim:
                break
        enemyspy = round((((100*int(spycount))/(percent-25))-2)/3)
        if enemyspy > 60:
            enemyspy = 60
        elif enemyspy > 50 and not nation._central_intelligence_agency:
            enemyspy = 50
        elif enemyspy < 2:
            enemyspy = 0
    return enemyspy
