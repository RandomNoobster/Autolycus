from __future__ import annotations
from typing import TYPE_CHECKING, Awaitable
from async_property import async_cached_property, async_property
from enums import *
from ...utils import get_date_from_string, PROJECT_BITMAP, execute_query, total_value, get_prices
from ...utils.pnw.revenue import *
from . import Alliance, City, BaseClass, Treasure, ResourceWrapper, War


__all__ = ["Nation", "NationPrivate", "BannedNation",
           "WarPolicyDetails", "DomesticPolicyDetails"]


class Nation(BaseClass):
    def __init__(self, json: dict = None, allow_private=False, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self.allow_private = allow_private
        self.id = int(self.id)
        self.alliance_id = int(self.alliance_id)
        self.alliance_position = AlliancePositionEnum(self.alliance_position)
        self.alliance_position_id = int(self.alliance_position_id)
        self.nation_name = str(self.nation_name)
        self.leader_name = str(self.leader_name)
        self.continent = Continent(self.continent)
        self.war_policy = WarPolicyEnum(self.war_policy)
        self.domestic_policy = DomesticPolicyEnum(self.domestic_policy)
        self.color = Color(self.color)
        self.num_cities = int(self.num_cities)
        self.score = float(self.score)
        self.population = int(self.population)
        self.flag = str(self.flag)
        self.vacation_mode_turns = int(self.vacation_mode_turns)
        self.beige_turns = int(self.beige_turns)
        self.espionage_available = bool(self.espionage_available)
        self.last_active = get_date_from_string(self.last_active)
        self.date = get_date_from_string(self.date)
        self.soldiers = int(self.soldiers)
        self.tanks = int(self.tanks)
        self.aircraft = int(self.aircraft)
        self.ships = int(self.ships)
        self.missiles = int(self.missiles)
        self.nukes = int(self.nukes)
        self.spies = int(self.spies)
        self.soldiers_today = int(self.soldiers_today)
        self.tanks_today = int(self.tanks_today)
        self.aircraft_today = int(self.aircraft_today)
        self.ships_today = int(self.ships_today)
        self.missiles_today = int(self.missiles_today)
        self.nukes_today = int(self.nukes_today)
        self.spies_today = int(self.spies_today)
        self.discord = str(self.discord)
        # this is an int, but it could be text if people are dumb
        self.discord_id = str(self.discord_id)
        self.turns_since_last_city = int(self.turns_since_last_city)
        self.turns_since_last_project = int(self.turns_since_last_project)
        self.projects = int(self.projects)
        self.moon_landing_date = get_date_from_string(self.moon_landing_date)
        self.mars_landing_date = get_date_from_string(self.mars_landing_date)
        self.wars_won = int(self.wars_won)
        self.wars_lost = int(self.wars_lost)
        self.tax_id = int(self.tax_id)
        self.alliance_seniority = int(self.alliance_seniority)
        self.gross_national_income = float(self.gross_national_income)
        self.gross_domestic_product = float(self.gross_domestic_product)
        self.soldier_casualties = int(self.soldier_casualties)
        self.soldier_kills = int(self.soldier_kills)
        self.tank_casualties = int(self.tank_casualties)
        self.tank_kills = int(self.tank_kills)
        self.aircraft_casualties = int(self.aircraft_casualties)
        self.aircraft_kills = int(self.aircraft_kills)
        self.ship_casualties = int(self.ship_casualties)
        self.ship_kills = int(self.ship_kills)
        self.missile_casualties = int(self.missile_casualties)
        self.missile_kills = int(self.missile_kills)
        self.nuke_casualties = int(self.nuke_casualties)
        self.nuke_kills = int(self.nuke_kills)
        self.spy_casualties = int(self.spy_casualties)
        self.spy_kills = int(self.spy_kills)
        self.money_looted = float(self.money_looted)
        self.vip = bool(self.vip)
        self.commendations = int(self.commendations)
        self.denouncements = int(self.denouncements)
        self.economic_policy = EconomicPolicy(self.economic_policy)
        self.social_policy = SocialPolicy(self.social_policy)
        self.government_type = GovernmentType(self.government_type)
        self.credits_redeemed_this_month = int(
            self.credits_redeemed_this_month)
        self.alliance_join_date = get_date_from_string(self.alliance_join_date)
        self.project_bits = int(self.project_bits)

        self.war_policy_details = WarPolicyDetails(self.war_policy)
        self.domestic_policy_details = DomesticPolicyDetails(
            self.domestic_policy)

        for name, bit in PROJECT_BITMAP.items():
            setattr(self, "_" + name.lower(), bool(self.project_bits & bit))

        if TYPE_CHECKING:
            # Type hinting for calculated attributes
            self._ironworks: bool
            self._bauxiteworks: bool
            self._arms_stockpile: bool
            self._emergency_gasoline_reserve: bool
            self._mass_irrigation: bool
            self._international_trade_center: bool
            self._missile_launch_pad: bool
            self._nuclear_research_facility: bool
            self._iron_dome: bool
            self._vital_defense_system: bool
            self._central_intelligence_agency: bool
            self._center_for_civil_engineering: bool
            self._propaganda_bureau: bool
            self._uranium_enrichment_program: bool
            self._urban_planning: bool
            self._advanced_urban_planning: bool
            self._space_program: bool
            self._spy_satellite: bool
            self._moon_landing: bool
            self._pirate_economy: bool
            self._recycling_initiative: bool
            self._telecommunications_satellite: bool
            self._green_technologies: bool
            self._arable_land_agency: bool
            self._clinical_research_center: bool
            self._specialized_police_training_program: bool
            self._advanced_engineering_corps: bool
            self._government_support_agency: bool
            self._research_and_development_center: bool
            self._metropolitan_planning: bool
            self._military_salvage: bool
            self._fallout_shelter: bool
            self._activity_center: bool
            self._bureau_of_domestic_affairs: bool
            self._advanced_pirate_economy: bool
            self._mars_landing: bool
            self._surveillance_network: bool

            # Type hinting for async properties
            self.cities: Awaitable[list[City]]
            self.highest_infra_city: Awaitable[City]
            self.alliance: Awaitable[Alliance]
            self.private: Awaitable[NationPrivate | None]
            self.treasures: Awaitable[list[Treasure]]
            self.at_war: Awaitable[bool]


    async def get_wars(self, war_type: WarAttackerFilter, active: WarActiveFilter) -> list[War]:
        """
        Gets a list of wars that the nation is involved in.
        """
        if war_type == WarAttackerFilter.OFFENSIVE:
            war_type_filter = f"att_id = {self.id}"
        elif war_type == WarAttackerFilter.DEFENSIVE:
            war_type_filter = f"def_id = {self.id}"
        else:
            war_type_filter = f"(att_id = {self.id} OR def_id = {self.id})"

        if active == WarActiveFilter.ACTIVE:
            active_filter = "turns_left > 0"
        elif active == WarActiveFilter.INACTIVE:
            active_filter = "turns_left < 1"
        else:
            active_filter = "1 = 1"

        wars = await execute_query(f"SELECT * FROM `wars` WHERE {war_type_filter} AND {active_filter}")
        return [War(war) for war in wars]

    @async_cached_property
    async def at_war(self) -> Awaitable[bool]:
        return len(await self.get_wars(WarAttackerFilter.ALL, WarActiveFilter.ACTIVE)) > 0

    @async_cached_property
    async def cities(self) -> Awaitable[list[City]]:
        cities = await execute_query(f"SELECT * FROM cities WHERE nation_id = {self.id}")
        return [City(city) for city in cities]
    
    @async_property
    async def highest_infra_city(self) -> Awaitable[City]:
        return max([city for city in await self.cities])

    @async_cached_property
    async def alliance(self) -> Awaitable[Alliance]:
        alliance = await execute_query(f"SELECT * FROM alliances WHERE id = {self.alliance_id}")
        return Alliance(alliance[0])

    @async_cached_property
    async def private(self) -> Awaitable[NationPrivate | None]:
        if self.allow_private:
            nation = await execute_query(f"SELECT * FROM `nations_private` WHERE `id` = {self.id}")
            if not nation:
                return None
            else:
                return NationPrivate(nation[0])

    @async_cached_property
    async def treasures(self) -> Awaitable[list[Treasure]]:
        treasures = await execute_query(f"SELECT * FROM `treasures` WHERE `nation_id` = {self.id}")
        return [Treasure(treasure) for treasure in treasures]

    @async_property
    async def money_from_population(self) -> float:
        return sum([await city.money_from_population(self) for city in await self.cities])

    @async_property
    async def total_treasure_bonus(self) -> float:
        return await total_treasure_bonus(self)

    @async_property
    async def personal_treasure_bonus(self) -> float:
        return await personal_treasure_bonus(self)

    @async_property
    async def alliance_treasure_bonus(self) -> float:
        return await alliance_treasure_bonus(self)

    @property
    def new_player_bonus(self) -> float:
        return new_player_bonus(self.num_cities)

    @async_property
    async def color_bonus(self) -> float:
        return await color_bonus(self.color)

    @async_property
    async def power_plant_upkeep(self) -> float:
        return sum([city.power_plant_upkeep for city in await self.cities])

    @async_property
    async def resource_production_upkeep(self) -> float:
        return sum([await city.resource_production_upkeep(self) for city in await self.cities])

    @async_property
    async def military_upkeep(self) -> float:
        return military_upkeep(self.soldiers, self.tanks, self.aircraft, self.ships, self.spies, self.missiles, self.nukes, self.domestic_policy == DomesticPolicyEnum.IMPERIALISM, await self.at_war)

    @async_property
    async def civil_city_improvement_upkeep(self) -> float:
        return sum([city.civil_city_improvement_upkeep for city in await self.cities])

    @async_property
    async def total_money_revenue(self) -> float:
        revenue = ResourceWrapper()
        if private := (await self.private):
            starving = private.starving
        else:
            starving = False
        revenue.money = total_money_revenue(
            starving,
            self.domestic_policy == DomesticPolicyEnum.OPEN_MARKETS,
            await self.money_from_population,
            await self.total_treasure_bonus,
            self.new_player_bonus,
            await self.color_bonus,
            await self.power_plant_upkeep,
            await self.resource_production_upkeep,
            await self.military_upkeep,
            await self.civil_city_improvement_upkeep
        )

    @async_property
    async def steel_mill_coal_consumed(self) -> float:
        return sum([await city.coal_consumed_by_steel_mills(self) for city in await self.cities])

    @async_property
    async def coal_consumed_by_power_plants(self) -> float:
        return sum([city.coal_consumed_by_power_plants for city in await self.cities])

    @async_property
    async def coal_consumed(self) -> float:
        return await self.steel_mill_coal_consumed + await self.coal_consumed_by_power_plants

    @async_property
    async def coal_produced(self) -> float:
        return sum([city.coal_produced for city in await self.cities])

    @async_property
    async def net_coal(self) -> float:
        return await self.coal_produced - await self.coal_consumed

    @async_property
    async def oil_consumed_by_gas_refineries(self) -> float:
        return sum([await city.oil_consumed_by_gas_refineries(self) for city in await self.cities])

    @async_property
    async def oil_consumed_by_power_plants(self) -> float:
        return sum([city.oil_consumed_by_power_plants for city in await self.cities])

    @async_property
    async def oil_consumed(self) -> float:
        return await self.oil_consumed_by_gas_refineries + await self.oil_consumed_by_power_plants

    @async_property
    async def oil_produced(self) -> float:
        return sum([city.oil_produced for city in await self.cities])

    @async_property
    async def net_oil(self) -> float:
        return await self.oil_produced - await self.oil_consumed

    @async_property
    async def uranium_consumed(self) -> float:
        return sum([city.uranium_consumed for city in await self.cities])

    @async_property
    async def uranium_produced(self) -> float:
        return sum([await city.uranium_produced(self) for city in await self.cities])

    @async_property
    async def net_uranium(self) -> float:
        return await self.uranium_produced - await self.uranium_consumed

    @async_property
    async def lead_consumed(self) -> float:
        return sum([await city.lead_consumed(self) for city in await self.cities])

    @async_property
    async def lead_produced(self) -> float:
        return sum([city.lead_produced for city in await self.cities])

    @async_property
    async def net_lead(self) -> float:
        return await self.lead_produced - await self.lead_consumed

    @async_property
    async def iron_consumed(self) -> float:
        return sum([await city.iron_consumed(self) for city in await self.cities])

    @async_property
    async def iron_produced(self) -> float:
        return sum([city.iron_produced for city in await self.cities])

    @async_property
    async def net_iron(self) -> float:
        return await self.iron_produced - await self.iron_consumed

    @async_property
    async def bauxite_consumed(self) -> float:
        return sum([await city.bauxite_consumed(self) for city in await self.cities])

    @async_property
    async def bauxite_produced(self) -> float:
        return sum([city.bauxite_produced for city in await self.cities])

    @async_property
    async def net_bauxite(self) -> float:
        return await self.bauxite_produced - await self.bauxite_consumed

    @async_property
    async def gasoline_produced(self) -> float:
        return sum([await city.gasoline_produced(self) for city in await self.cities])

    @async_property
    async def net_gasoline(self) -> float:
        return sum([await city.net_gasoline(self) for city in await self.cities])

    @async_property
    async def munitions_produced(self) -> float:
        return sum([await city.munitions_produced(self) for city in await self.cities])

    @async_property
    async def net_munitions(self) -> float:
        return sum([await city.net_munitions(self) for city in await self.cities])

    @async_property
    async def steel_produced(self) -> float:
        return sum([await city.steel_produced(self) for city in await self.cities])

    @async_property
    async def net_steel(self) -> float:
        return sum([await city.net_steel(self) for city in await self.cities])

    @async_property
    async def aluminum_produced(self) -> float:
        return sum([await city.aluminum_produced(self) for city in await self.cities])

    @async_property
    async def net_aluminum(self) -> float:
        return sum([await city.net_aluminum(self) for city in await self.cities])

    @async_property
    async def food_produced(self) -> float:
        return sum([await city.food_produced(self) for city in await self.cities])

    @async_property
    async def soldiers_food_consumed(self) -> float:
        return soldiers_food_consumed(self.soldiers, await self.at_war)

    @async_property
    async def population_food_consumed(self) -> float:
        return population_food_consumed(self.population)

    @async_property
    async def food_consumed(self) -> float:
        return await self.soldiers_food_consumed + await self.population_food_consumed

    @async_property
    async def net_food(self) -> float:
        return await self.food_produced - await self.food_consumed

    @async_property
    async def converted_revenue(self) -> float:
        prices = await get_prices()
        return (
            await self.total_money_revenue
            + await self.net_coal * prices.coal
            + await self.net_oil * prices.oil
            + await self.net_uranium * prices.uranium
            + await self.net_lead * prices.lead
            + await self.net_iron * prices.iron
            + await self.net_bauxite * prices.bauxite
            + await self.net_gasoline * prices.gasoline
            + await self.net_munitions * prices.munitions
            + await self.net_steel * prices.steel
            + await self.net_aluminum * prices.aluminum
            + await self.net_food * prices.food
        )


class NationPrivate(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self.id = int(self.id)
        self.spy_attacks = int(self.spy_attacks)
        self.update_tz = float(self.update_tz)
        self.money = float(self.money)
        self.coal = float(self.coal)
        self.oil = float(self.oil)
        self.uranium = float(self.uranium)
        self.iron = float(self.iron)
        self.bauxite = float(self.bauxite)
        self.lead = float(self.lead)
        self.gasoline = float(self.gasoline)
        self.munitions = float(self.munitions)
        self.steel = float(self.steel)
        self.aluminum = float(self.aluminum)
        self.food = float(self.food)
        self.credits = float(self.credits)

    @property
    def starving(self) -> bool:
        return self.food == 0


class BannedNation(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self.nation_id = int(self.nation_id)
        self.reason = str(self.reason)
        self.date = get_date_from_string(self.date)
        self.days_left = int(self.days_left)


class WarPolicyDetails():
    if TYPE_CHECKING:
        policy: WarPolicyEnum
        loot_stolen: float
        loot_lost: float
        infrastructure_damage_dealt: float
        infrastructure_damage_received: float
        improvements_lost: float
        improvements_destroyed: float
        defensive_espionage_enemy_success: float
        offensive_espionage_own_success: float

    def __init__(self, policy: WarPolicyEnum):
        self.policy = policy

        if policy == WarPolicyEnum.ATTRITION:
            self.loot_stolen = 0.8
            self.loot_lost = 1
            self.infrastructure_damage_dealt = 1.1
            self.infrastructure_damage_received = 1
            self.improvements_lost = 1
            self.improvements_destroyed = 1
            self.defensive_espionage_enemy_success = 1
            self.offensive_espionage_own_success = 1

        elif policy == WarPolicyEnum.TURTLE:
            self.loot_stolen = 1
            self.loot_lost = 1.2
            self.infrastructure_damage_dealt = 1
            self.infrastructure_damage_received = 0.9
            self.improvements_lost = 1
            self.improvements_destroyed = 1
            self.defensive_espionage_enemy_success = 1
            self.offensive_espionage_own_success = 1

        elif policy == WarPolicyEnum.BLITZKRIEG:
            self.loot_stolen = 1
            self.loot_lost = 1
            # TODO 1.1 if less than 12 turns since swap
            self.infrastructure_damage_dealt = 1
            self.infrastructure_damage_received = 1
            self.improvements_lost = 1
            self.improvements_destroyed = 1
            self.defensive_espionage_enemy_success = 1
            self.offensive_espionage_own_success = 1

        elif policy == WarPolicyEnum.FORTRESS:
            self.loot_stolen = 1
            self.loot_lost = 1
            self.infrastructure_damage_dealt = 1
            self.infrastructure_damage_received = 1
            self.improvements_lost = 1
            self.improvements_destroyed = 1
            self.defensive_espionage_enemy_success = 1
            self.offensive_espionage_own_success = 1

        elif policy == WarPolicyEnum.MONEYBAGS:
            self.loot_stolen = 1
            self.loot_lost = 0.6
            self.infrastructure_damage_dealt = 1
            self.infrastructure_damage_received = 1.05
            self.improvements_lost = 1
            self.improvements_destroyed = 1
            self.defensive_espionage_enemy_success = 1
            self.offensive_espionage_own_success = 1

        elif policy == WarPolicyEnum.PIRATE:
            self.loot_stolen = 1.4
            self.loot_lost = 1
            self.infrastructure_damage_dealt = 1
            self.infrastructure_damage_received = 1
            self.improvements_lost = 2
            self.improvements_destroyed = 1
            self.defensive_espionage_enemy_success = 1
            self.offensive_espionage_own_success = 1

        elif policy == WarPolicyEnum.TACTICIAN:
            self.loot_stolen = 1
            self.loot_lost = 1
            self.infrastructure_damage_dealt = 1
            self.infrastructure_damage_received = 1
            self.improvements_lost = 1
            self.improvements_destroyed = 2
            self.defensive_espionage_enemy_success = 1.15
            self.offensive_espionage_own_success = 1

        elif policy == WarPolicyEnum.GUARDIAN:
            self.loot_stolen = 1
            self.loot_lost = 1.2
            self.infrastructure_damage_dealt = 1
            self.infrastructure_damage_received = 1
            self.improvements_lost = 0.5
            self.improvements_destroyed = 1
            self.defensive_espionage_enemy_success = 1
            self.offensive_espionage_own_success = 1

        elif policy == WarPolicyEnum.COVERT:
            self.loot_stolen = 1
            self.loot_lost = 1
            self.infrastructure_damage_dealt = 1
            self.infrastructure_damage_received = 1.05
            self.improvements_lost = 1
            self.improvements_destroyed = 1
            self.defensive_espionage_enemy_success = 1
            self.offensive_espionage_own_success = 1.15

        elif policy == WarPolicyEnum.ARCANE:
            self.loot_stolen = 1
            self.loot_lost = 1
            self.infrastructure_damage_dealt = 1
            self.infrastructure_damage_received = 1.05
            self.improvements_lost = 1
            self.improvements_destroyed = 1
            self.defensive_espionage_enemy_success = 0.85
            self.offensive_espionage_own_success = 1

        else:
            raise ValueError(f"Invalid war policy: {policy}")


class DomesticPolicyDetails():
    def __init__(self) -> None:
        # TODO
        pass
