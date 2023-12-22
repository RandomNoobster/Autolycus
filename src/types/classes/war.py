from __future__ import annotations
from datetime import datetime
from async_property import async_cached_property, async_property
from typing import TYPE_CHECKING, Awaitable, Union
from enums import *
from ...utils import get_date_from_string, execute_query, get_datetime_of_turns, get_prices
from . import Nation, City, BaseClass


__all__ = ["War", "WarAttack", "Bounty",
           "MilitaryUnit", "WarTypeDetails",

           ]


class War(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self.id = int(self.id)
        self.date = get_date_from_string(self.date)
        self.reason = str(self.reason)
        self.war_type = WarTypeEnum(self.war_type)
        self.att_id = int(self.att_id)
        self.att_alliance_id = int(self.att_alliance_id)
        self.def_id = int(self.def_id)
        self.def_alliance_id = int(self.def_alliance_id)
        self.ground_control = int(self.ground_control)
        self.air_superiority = int(self.air_superiority)
        self.naval_blockade = int(self.naval_blockade)
        self.winner_id = int(self.winner_id)
        self.turns_left = int(self.turns_left)
        self.att_points = int(self.att_points)
        self.def_points = int(self.def_points)
        self.att_peace = bool(self.att_peace)
        self.def_peace = bool(self.def_peace)
        self.att_resistance = int(self.att_resistance)
        self.def_resistance = int(self.def_resistance)
        self.att_fortify = bool(self.att_fortify)
        self.def_fortify = bool(self.def_fortify)
        self.att_gas_used = float(self.att_gas_used)
        self.def_gas_used = float(self.def_gas_used)
        self.att_mun_used = float(self.att_mun_used)
        self.def_mun_used = float(self.def_mun_used)
        self.att_alum_used = float(self.att_alum_used)
        self.def_alum_used = float(self.def_alum_used)
        self.att_steel_used = float(self.att_steel_used)
        self.def_steel_used = float(self.def_steel_used)
        self.att_infra_destroyed = float(self.att_infra_destroyed)
        self.def_infra_destroyed = float(self.def_infra_destroyed)
        self.att_money_looted = float(self.att_money_looted)
        self.def_money_looted = float(self.def_money_looted)
        self.def_soldiers_lost = int(self.def_soldiers_lost)
        self.att_soldiers_lost = int(self.att_soldiers_lost)
        self.def_tanks_lost = int(self.def_tanks_lost)
        self.att_tanks_lost = int(self.att_tanks_lost)
        self.def_aircraft_lost = int(self.def_aircraft_lost)
        self.att_aircraft_lost = int(self.att_aircraft_lost)
        self.def_ships_lost = int(self.def_ships_lost)
        self.att_ships_lost = int(self.att_ships_lost)
        self.att_missiles_used = int(self.att_missiles_used)
        self.def_missiles_used = int(self.def_missiles_used)
        self.att_nukes_used = int(self.att_nukes_used)
        self.def_nukes_used = int(self.def_nukes_used)
        self.att_infra_destroyed_value = float(self.att_infra_destroyed_value)
        self.def_infra_destroyed_value = float(self.def_infra_destroyed_value)

        self._war_type_details = WarTypeDetails(self.war_type)

        if TYPE_CHECKING:
            # Type hinting for async properties
            self.attacks: Awaitable[list[WarAttack]]
            self.attacker: Awaitable[Nation]
            self.defender: Awaitable[Nation]

    @async_cached_property
    async def attacks(self) -> Awaitable[list[WarAttack]]:
        attacks = await execute_query(f"SELECT * FROM `war_attacks` WHERE `war_id` = {self.id}")
        return [WarAttack(attack) for attack in attacks]

    @async_cached_property
    async def attacker(self) -> Awaitable[Nation]:
        nation = await execute_query(f"SELECT * FROM `nations` WHERE `id` = {self.att_id}")
        return Nation(nation[0])

    @async_cached_property
    async def defender(self) -> Awaitable[Nation]:
        nation = await execute_query(f"SELECT * FROM `nations` WHERE `id` = {self.def_id}")
        return Nation(nation[0])

    @property
    def expires(self) -> datetime:
        return get_datetime_of_turns(self.turns_left)

    @property
    def active(self) -> bool:
        return self.turns_left > 0


class WarAttack(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self.id = int(self.id)
        self.date = get_date_from_string(self.date)
        self.att_id = int(self.att_id)
        self.def_id = int(self.def_id)
        self.type = AttackType(self.type)
        self.war_id = int(self.war_id)
        self.victor = int(self.victor)
        self.success = AttackSuccess(self.success)
        self.city_id = int(self.city_id)
        self.infra_destroyed = float(self.infra_destroyed)
        self.improvements_lost = int(self.improvements_lost)
        self.money_stolen = float(self.money_stolen)
        self.resistance_lost = int(self.resistance_lost)
        self.city_infra_before = float(self.city_infra_before)
        self.infra_destroyed_value = float(self.infra_destroyed_value)
        self.att_mun_used = float(self.att_mun_used)
        self.def_mun_used = float(self.def_mun_used)
        self.att_gas_used = float(self.att_gas_used)
        self.def_gas_used = float(self.def_gas_used)
        self.money_destroyed = float(self.money_destroyed)
        self.military_salvage_aluminum = float(self.military_salvage_aluminum)
        self.military_salvage_steel = float(self.military_salvage_steel)
        self.att_soldiers_used = int(self.att_soldiers_used)
        self.att_soldiers_lost = int(self.att_soldiers_lost)
        self.def_soldiers_used = int(self.def_soldiers_used)
        self.def_soldiers_lost = int(self.def_soldiers_lost)
        self.att_tanks_used = int(self.att_tanks_used)
        self.att_tanks_lost = int(self.att_tanks_lost)
        self.def_tanks_used = int(self.def_tanks_used)
        self.def_tanks_lost = int(self.def_tanks_lost)
        self.att_aircraft_used = int(self.att_aircraft_used)
        self.att_aircraft_lost = int(self.att_aircraft_lost)
        self.def_aircraft_used = int(self.def_aircraft_used)
        self.def_aircraft_lost = int(self.def_aircraft_lost)
        self.att_ships_used = int(self.att_ships_used)
        self.att_ships_lost = int(self.att_ships_lost)
        self.def_ships_used = int(self.def_ships_used)
        self.def_ships_lost = int(self.def_ships_lost)
        self.att_missiles_lost = int(self.att_missiles_lost)
        self.def_missiles_lost = int(self.def_missiles_lost)
        self.att_nukes_lost = int(self.att_nukes_lost)
        self.def_nukes_lost = int(self.def_nukes_lost)
        self.improvements_destroyed = str(self.improvements_destroyed)
        self.infra_destroyed_percentage = float(
            self.infra_destroyed_percentage)
        self.cities_infra_before = float(self.cities_infra_before)
        self.money_looted = float(self.money_looted)
        self.coal_looted = float(self.coal_looted)
        self.oil_looted = float(self.oil_looted)
        self.uranium_looted = float(self.uranium_looted)
        self.iron_looted = float(self.iron_looted)
        self.bauxite_looted = float(self.bauxite_looted)
        self.lead_looted = float(self.lead_looted)
        self.gasoline_looted = float(self.gasoline_looted)
        self.munitions_looted = float(self.munitions_looted)
        self.steel_looted = float(self.steel_looted)
        self.aluminum_looted = float(self.aluminum_looted)
        self.food_looted = float(self.food_looted)

        if TYPE_CHECKING:
            # Type hinting for async properties
            self.city: Awaitable[City]
            self.war: Awaitable[War]
            self.attacker: Awaitable[Nation]
            self.defender: Awaitable[Nation]

    @async_cached_property
    async def city(self) -> Awaitable[City]:
        city = await execute_query(f"SELECT * FROM `cities` WHERE `id` = {self.city_id}")
        return City(city[0])

    @async_cached_property
    async def war(self) -> Awaitable[War]:
        war = await execute_query(f"SELECT * FROM `wars` WHERE `id` = {self.war_id}")
        return War(war[0])

    @async_cached_property
    async def attacker(self) -> Awaitable[Nation]:
        nation = await execute_query(f"SELECT * FROM `nations` WHERE `id` = {self.att_id}")
        return Nation(nation[0])

    @async_cached_property
    async def defender(self) -> Awaitable[Nation]:
        nation = await execute_query(f"SELECT * FROM `nations` WHERE `id` = {self.def_id}")
        return Nation(nation[0])


class Bounty(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self.id = int(self.id)
        self.date = get_date_from_string(self.date)
        self.nation_id = int(self.nation_id)
        self.amount = int(self.amount)
        self.type = BountyType(self.type)

        if TYPE_CHECKING:
            # Type hinting for async properties
            self.nation: Awaitable[Nation]

    @async_cached_property
    async def nation(self) -> Awaitable[Nation]:
        nation = await execute_query(f"SELECT * FROM `nations` WHERE `id` = {self.nation_id}")
        return Nation(nation[0])


class MilitaryUnit:
    if TYPE_CHECKING:
        money_cost: float
        uranium_cost: float
        gasoline_cost: float
        munitions_cost: float
        steel_cost: float
        aluminum_cost: float
        total_cost: Awaitable[float]
        army_value: Union[int, None]
        loot_stolen: Union[float, None]
        munitions_used: float
        gasoline_used: float

    def __init__(self, unit_type: MilitaryUnitEnum, using_munitions: bool = True, enemy_air_superiority: bool = False) -> None:
        if unit_type == MilitaryUnitEnum.SOLDIER:
            self.money_cost = 5
            self.uranium_cost = 0
            self.gasoline_cost = 0
            self.munitions_cost = 0
            self.steel_cost = 0
            self.aluminum_cost = 0
            self.army_value = 1.75 if using_munitions else 1
            self.loot_stolen = 1.1
            self.munitions_used = 0.0002 if using_munitions else 0
            self.gasoline_used = 0

        elif unit_type == MilitaryUnitEnum.TANK:
            self.money_cost = 60
            self.uranium_cost = 0
            self.gasoline_cost = 0
            self.munitions_cost = 0
            self.steel_cost = 0.5
            self.aluminum_cost = 0
            self.army_value = 20 if enemy_air_superiority else 40
            self.loot_stolen = 25.15
            self.munitions_used = 0.01
            self.gasoline_used = 0.01

        elif unit_type == MilitaryUnitEnum.AIRCRAFT:
            self.money_cost = 4000
            self.uranium_cost = 0
            self.gasoline_cost = 0
            self.munitions_cost = 0
            self.steel_cost = 0
            self.aluminum_cost = 5
            self.army_value = 3
            self.loot_stolen = None
            self.munitions_used = 0.25
            self.gasoline_used = 0.25

        elif unit_type == MilitaryUnitEnum.SHIP:
            self.money_cost = 50000
            self.uranium_cost = 0
            self.gasoline_cost = 0
            self.munitions_cost = 0
            self.steel_cost = 30
            self.aluminum_cost = 0
            self.army_value = 4
            self.loot_stolen = None
            self.munitions_used = 2.5
            self.gasoline_used = 1.5

        elif unit_type == MilitaryUnitEnum.SPY:
            self.money_cost = 50000
            self.uranium_cost = 0
            self.gasoline_cost = 0
            self.munitions_cost = 0
            self.steel_cost = 0
            self.aluminum_cost = 0
            self.army_value = None
            self.loot_stolen = None
            self.munitions_used = 0
            self.gasoline_used = 0

        elif unit_type == MilitaryUnitEnum.MISSILE:
            self.money_cost = 150000
            self.uranium_cost = 0
            self.gasoline_cost = 75
            self.munitions_cost = 75
            self.steel_cost = 0
            self.aluminum_cost = 100
            self.army_value = None
            self.loot_stolen = None
            self.munitions_used = 0
            self.gasoline_used = 0

        elif unit_type == MilitaryUnitEnum.NUKE:
            self.money_cost = 1750000
            self.uranium_cost = 250
            self.gasoline_cost = 500
            self.munitions_cost = 0
            self.steel_cost = 0
            self.aluminum_cost = 750
            self.army_value = None
            self.loot_stolen = None
            self.munitions_used = 0
            self.gasoline_used = 0

        else:
            raise ValueError("Invalid military unit type")

    @async_property
    async def total_cost(self) -> float:
        prices = await get_prices()
        return (
            self.money_cost
            + self.uranium_cost * prices.uranium
            + self.gasoline_cost * prices.gasoline
            + self.munitions_cost * prices.munitions
            + self.steel_cost * prices.steel
            + self.aluminum_cost * prices.aluminum
        )


class WarTypeDetails:
    def __init__(self, type: WarTypeEnum) -> None:
        if TYPE_CHECKING:
            self.attacker_loot: float
            self.defender_loot: float
            self.attacker_infra_destroyed: float
            self.defender_infra_destroyed: float

        if type == WarTypeEnum.ATTRITION:
            self.attacker_loot = 0.25
            self.defender_loot = 0.5
            self.attacker_infra_destroyed = 1
            self.defender_infra_destroyed = 1

        elif type == WarTypeEnum.ORDINARY:
            self.attacker_loot = 0.5
            self.defender_loot = 0.5
            self.attacker_infra_destroyed = 0.5
            self.defender_infra_destroyed = 0.5

        elif type == WarTypeEnum.RAID:
            self.attacker_loot = 1
            self.defender_loot = 1
            self.attacker_infra_destroyed = 0.25
            self.defender_infra_destroyed = 0.5

        else:
            raise ValueError("Invalid war type")
