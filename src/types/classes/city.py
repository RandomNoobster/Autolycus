from __future__ import annotations
from functools import cached_property
from async_property import async_property, async_cached_property
from typing import TYPE_CHECKING, Awaitable
from datetime import datetime
from enums import *
from ...utils import get_date_from_string, execute_query, LOGGER, SOLDIERS_PER_BARRACKS, get_prices
from ...utils.pnw.revenue import *
from . import BaseClass, Nation


__all__ = ["City"]


class City(BaseClass):
    def __init__(self, json: dict = None, **kwargs):
        BaseClass.__init__(self, json, **kwargs)

        # Ensuring types
        self.id = int(self.id)
        self.nation_id = int(self.nation_id)
        self.name = str(self.name)
        self.date = get_date_from_string(self.date)
        self.infrastructure = float(self.infrastructure)
        self.land = float(self.land)
        self.powered = bool(self.powered)
        self.oil_power = int(self.oil_power)
        self.wind_power = int(self.wind_power)
        self.coal_power = int(self.coal_power)
        self.nuclear_power = int(self.nuclear_power)
        self.coal_mine = int(self.coal_mine)
        self.oil_well = int(self.oil_well)
        self.uranium_mine = int(self.uranium_mine)
        self.barracks = int(self.barracks)
        self.farm = int(self.farm)
        self.police_station = int(self.police_station)
        self.hospital = int(self.hospital)
        self.recycling_center = int(self.recycling_center)
        self.subway = int(self.subway)
        self.supermarket = int(self.supermarket)
        self.bank = int(self.bank)
        self.shopping_mall = int(self.shopping_mall)
        self.stadium = int(self.stadium)
        self.lead_mine = int(self.lead_mine)
        self.iron_mine = int(self.iron_mine)
        self.bauxite_mine = int(self.bauxite_mine)
        self.oil_refinery = int(self.oil_refinery)
        self.aluminum_refinery = int(self.aluminum_refinery)
        self.steel_mill = int(self.steel_mill)
        self.munitions_factory = int(self.munitions_factory)
        self.factory = int(self.factory)
        self.hangar = int(self.hangar)
        self.drydock = int(self.drydock)
        self.nuke_date = get_date_from_string(self.nuke_date)

        if TYPE_CHECKING:
            # Type hinting for async properties
            self.nation: Awaitable[Nation | None]
            self.population_food_consumed: Awaitable[float]

    @async_cached_property
    async def nation(self) -> Awaitable[Nation | None]:
        nation = await execute_query(f"SELECT * FROM `nations` WHERE `id` = {self.nation_id}")
        if nation:
            return Nation(nation[0])
        else:
            return None

    async def uncapped_commerce(self, nation: Nation = None) -> int:
        """
        Calculates the uncapped commerce of the city. Nation can be specified, but the default is the city's nation_id.
        """
        if not self.powered:
            return 0
        if nation or (nation := await self.nation):
            telecom_sat = nation._telecommunications_satellite
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return uncapped_commerce(self.supermarket, self.bank, self.shopping_mall, self.stadium, self.subway, telecom_sat)

    async def capped_commerce(self, nation: Nation = None) -> int:
        """
        Calculates the capped commerce of the city. Nation can be specified, but the default is the city's nation_id.
        """
        if nation or (nation := await self.nation):
            telecom_sat = nation._telecommunications_satellite
            itc = nation._international_trade_center
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return capped_commerce(await self.uncapped_commerce(nation), itc, telecom_sat)

    async def pollution(self, nation: Nation = None) -> int:
        """
        Calculates the pollution of the city. Nation can be specified, but the default is the city's nation_id.
        """
        if nation or (nation := await self.nation):
            green_tech = nation._green_technologies
            recycling_initiative = nation._recycling_initiative
        else:
            green_tech = False
            recycling_initiative = False

        return pollution(
            self.oil_power,
            self.coal_power,
            self.coal_mine,
            self.oil_well,
            self.uranium_mine,
            self.iron_mine,
            self.bauxite_mine,
            self.lead_mine,
            self.farm,
            self.steel_mill * int(self.powered),
            self.aluminum_refinery * int(self.powered),
            self.munitions_factory * int(self.powered),
            self.oil_refinery * int(self.powered),
            self.subway * int(self.powered),
            self.police_station * int(self.powered),
            self.hospital * int(self.powered),
            self.recycling_center * int(self.powered),
            self.shopping_mall * int(self.powered),
            self.stadium * int(self.powered),
            green_tech,
            recycling_initiative
        )

    async def uncapped_crime(self, nation: Nation = None) -> float:
        """
        Calculates the uncapped crime of the city. Nation can be specified, but the default is the city's nation_id.
        """
        if nation or (nation := await self.nation):
            special_training = nation._specialized_police_training_program
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return uncapped_crime_rate(await self.capped_commerce(nation), self.infrastructure, self.police_station * int(self.powered), special_training)

    async def capped_crime(self, nation: Nation = None) -> float:
        """
        Calculates the capped crime of the city. Nation can be specified, but the default is the city's nation_id.
        """
        return capped_crime_rate(await self.uncapped_crime(nation))

    async def uncapped_disease(self, nation: Nation = None) -> float:
        """
        Calculates the uncapped disease of the city. Nation can be specified, but the default is the city's nation_id.
        """
        if nation or (nation := await self.nation):
            clinical_research = nation._clinical_research_center
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return uncapped_disease_rate(self.hospital * int(self.powered), self.infrastructure, await self.pollution(nation), clinical_research, self.land)

    async def capped_disease(self, nation: Nation = None) -> float:
        return capped_disease_rate(await self.uncapped_disease(nation))

    @property
    def age(self) -> int:
        return (datetime.utcnow() - self.date).days

    async def population(self, nation: Nation = None) -> int:
        """
        Calculates the population of the city. Nation can be specified, but the default is the city's nation_id.
        """
        return round(real_population(self.infrastructure, await self.capped_disease(nation), await self.capped_crime(nation), self.age))

    @async_property
    async def population_food_consumed(self) -> Awaitable[float]:
        """
        Calculates the food consumed by the population of the city.
        """
        return population_food_consumed(await self.population())

    async def soldiers_food_consumed(self, nation: Nation = None) -> float:
        """
        The typical use case for this is when determining revenue from city builds, not the income of a nation. 
        """
        if nation or (nation := await self.nation):
            at_war = await nation.at_war
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return soldiers_food_consumed(self.barracks * SOLDIERS_PER_BARRACKS, at_war)

    async def food_produced(self, nation: Nation = None) -> float:
        if nation or (nation := await self.nation):
            continent = nation.continent
            mass_irrigation = nation._mass_irrigation
            fallout_shelter = nation._fallout_shelter
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return food_produced(self.land, self.farm, continent, get_game_date(), mass_irrigation, fallout_shelter)

    async def net_food(self, nation: Nation = None, include_military: bool = False) -> float:
        """
        Net food revenue.
        """
        if nation or (nation := await self.nation):
            pass
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return self.food_produced(nation) - await self.population_food_consumed - await self.soldiers_food_consumed(nation) * int(include_military)

    @property
    def coal_produced(self) -> float:
        return coal_produced(self.coal_mine)

    async def coal_consumed_by_steel_mills(self, nation: Nation = None) -> float:
        if nation or (nation := await self.nation):
            ironworks = nation._ironworks
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return steel_mill_coal_consumed(self.steel_mill, ironworks)

    @property
    def coal_consumed_by_power_plants(self) -> float:
        return resource_consumed_by_power(self.infrastructure, self.wind_power, self.nuclear_power, self.oil_power, self.coal_power, ResourceEnum.COAL)

    async def coal_consumed(self, nation: Nation = None) -> float:
        return self.coal_consumed_by_power_plants + await self.coal_consumed_by_steel_mills(nation)

    async def net_coal(self, nation: Nation = None) -> float:
        return self.coal_produced - await self.coal_consumed(nation)

    @property
    def oil_produced(self) -> float:
        return oil_produced(self.oil_well)

    async def oil_consumed_by_gas_refineries(self, nation: Nation = None) -> float:
        if nation or (nation := await self.nation):
            egr = nation._emergency_gasoline_reserve
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return gasoline_refinery_oil_consumed(self.oil_refinery, egr)

    @property
    def oil_consumed_by_power_plants(self) -> float:
        return resource_consumed_by_power(self.infrastructure, self.wind_power, self.nuclear_power, self.oil_power, self.coal_power, ResourceEnum.OIL)

    async def oil_consumed(self, nation: Nation = None) -> float:
        return self.oil_consumed_by_power_plants + await self.oil_consumed_by_gas_refineries(nation)

    async def net_oil(self, nation: Nation = None) -> float:
        return self.oil_produced - await self.oil_consumed(nation)

    async def uranium_produced(self, nation: Nation = None):
        if nation or (nation := await self.nation):
            uranium_enrichment = nation._uranium_enrichment_program
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return uranium_produced(self.uranium_mine, uranium_enrichment)

    @property
    def uranium_consumed(self) -> float:
        return uranium_consumed(self.infrastructure, self.wind_power, self.nuclear_power, self.oil_power, self.coal_power)

    async def net_uranium(self, nation: Nation = None) -> float:
        return await self.uranium_produced(nation) - self.uranium_consumed

    @property
    def lead_produced(self) -> float:
        return lead_produced(self.lead_mine)

    async def lead_consumed(self, nation: Nation = None) -> float:
        if nation or (nation := await self.nation):
            arms_stockpile = nation._arms_stockpile
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return lead_consumed(self.munitions_factory, arms_stockpile)

    async def net_lead(self, nation: Nation = None) -> float:
        return self.lead_produced - await self.lead_consumed(nation)

    @property
    def iron_produced(self) -> float:
        return iron_produced(self.iron_mine)

    async def iron_consumed(self, nation: Nation = None) -> float:
        if nation or (nation := await self.nation):
            ironworks = nation._ironworks
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return iron_consumed(self.steel_mill, ironworks)

    async def net_iron(self, nation: Nation = None) -> float:
        return self.iron_produced - await self.iron_consumed(nation)

    @property
    def bauxite_produced(self) -> float:
        return bauxite_produced(self.bauxite_mine)

    async def bauxite_consumed(self, nation: Nation = None) -> float:
        if nation or (nation := await self.nation):
            bauxiteworks = nation._bauxiteworks
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return bauxite_consumed(self.aluminum_refinery, bauxiteworks)

    async def net_bauxite(self, nation: Nation = None) -> float:
        return self.bauxite_produced - await self.bauxite_consumed(nation)

    async def gasoline_produced(self, nation: Nation = None) -> float:
        if nation or (nation := await self.nation):
            egr = nation._emergency_gasoline_reserve
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return gasoline_produced(self.oil_refinery, egr) * int(self.powered)
    
    async def net_gasoline(self, nation: Nation = None) -> float:
        return await self.gasoline_produced(nation)

    async def munitions_produced(self, nation: Nation = None) -> float:
        if nation or (nation := await self.nation):
            arms_stockpile = nation._arms_stockpile
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return munitions_produced(self.munitions_factory, arms_stockpile) * int(self.powered)
    
    async def net_munitions(self, nation: Nation = None) -> float:
        return await self.munitions_produced(nation)

    async def steel_produced(self, nation: Nation = None) -> float:
        if nation or (nation := await self.nation):
            ironworks = nation._ironworks
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return steel_produced(self.steel_mill, ironworks) * int(self.powered)
    
    async def net_steel(self, nation: Nation = None) -> float:
        return await self.steel_produced(nation)

    async def aluminum_produced(self, nation: Nation = None) -> float:
        if nation or (nation := await self.nation):
            bauxiteworks = nation._bauxiteworks
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return aluminum_produced(self.aluminum_refinery, bauxiteworks) * int(self.powered)
    
    async def net_aluminum(self, nation: Nation = None) -> float:
        return await self.aluminum_produced(nation)

    async def money_from_population(self, nation: Nation = None) -> float:
        return money_from_population(await self.capped_commerce(nation), await self.population(nation))

    @property
    def power_plant_upkeep(self) -> float:
        return power_plant_upkeep(self.wind_power, self.nuclear_power, self.oil_power, self.coal_power)

    async def resource_production_upkeep(self, nation: Nation = None) -> float:
        if nation or (nation := await self.nation):
            green_tech = nation._green_technologies
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        return resource_production_upkeep(
            self.coal_mine,
            self.oil_well,
            self.uranium_mine,
            self.iron_mine,
            self.bauxite_mine,
            self.lead_mine,
            self.farm,
            self.steel_mill,
            self.aluminum_refinery,
            self.munitions_factory,
            self.oil_refinery,
            green_tech
        ) * int(self.powered)

    @property
    def civil_city_improvement_upkeep(self) -> float:
        return civil_city_improvement_upkeep(
            self.police_station,
            self.hospital,
            self.recycling_center,
            self.subway,
            self.supermarket,
            self.bank,
            self.shopping_mall,
            self.stadium
        ) * int(self.powered)

    async def military_buildings_upkeep(self, nation: Nation = None) -> float:
        """
        Context of use is when calculating revenue of city builds and not nations.
        """
        if nation or (nation := await self.nation):
            pass
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        # TODO do I pay army upkeep when my cities are not powered??
        return military_buildings_upkeep(self.barracks, self.factory, self.hangar, self.drydock, nation.at_war, nation.domestic_policy == DomesticPolicy.IMPERIALISM)

    async def net_money(self, nation: Nation = None, include_military: bool = False) -> float:
        """
        Net money revenue.
        """
        return await self.money_from_population(nation) - self.power_plant_upkeep - await self.resource_production_upkeep(nation) - self.civil_city_improvement_upkeep - await self.military_buildings_upkeep(nation) * int(include_military)

    async def converted_revenue(self, nation: Nation = None, include_military: bool = False) -> float:
        """
        Calculates the net monetary revenue of the city. Nation can be specified, but the default is the city's nation_id.
        """
        if nation or (nation := await self.nation):
            pass
        else:
            raise ValueError(
                "Nation was not specified and could not be deduced.")
        prices = await get_prices()
        return (
            self.net_money(nation, include_military)
            + self.net_coal(nation) * prices.coal
            + self.net_oil(nation) * prices.oil
            + self.net_uranium(nation) * prices.uranium
            + self.net_lead(nation) * prices.lead
            + self.net_iron(nation) * prices.iron
            + self.net_bauxite(nation) * prices.bauxite
            + self.net_gasoline(nation) * prices.gasoline
            + self.net_munitions(nation) * prices.munitions
            + self.net_steel(nation) * prices.steel
            + self.net_aluminum(nation) * prices.aluminum
            + self.net_food(nation, include_military) * prices.food
        )
