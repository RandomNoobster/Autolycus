from __future__ import annotations
import math
import re
from typing import Union
from warnings import WarningMessage
import numpy as np

import aiohttp
from ....types import TradePrices, Nation, WarPolicyDetails, WarTypeDetails, WarTypeEnum, WarPolicyEnum, AttackType, MilitaryUnit, MilitaryUnitEnum, AttackSuccess, AttackerEnum, StatsEnum, WarAttackerFilter, WarActiveFilter
from ... import execute_query, weird_division
from .. import SOLDIERS_PER_BARRACKS, TANKS_PER_FACTORY, AIRCRAFT_PER_HANGAR, SHIPS_PER_DRYDOCK, BARRACKS_PER_CITY, FACTORY_PER_CITY, HANGAR_PER_CITY, DRYDOCK_PER_CITY, RESOURCES, infra_cost
from . import *


class BattleCalc:
    async def __init__(self, attacker: Nation, defender: Nation) -> None:
        self.attacker = attacker
        self.defender = defender
        
        self.war = None
        for war in await attacker.get_wars(WarAttackerFilter.ALL, WarActiveFilter.ACTIVE):
            if war.defender == defender:
                self.war = war
                break

        self.attacker_using_munitions = True
        self.defender_using_munitions = True

        self.attacker_air_superiority = self.war.air_superiority == self.attacker.id if self.war else False
        self.defender_air_superiority = self.war.air_superiority == self.defender.id if self.war else False

        self.attacker_fortified = self.war.att_fortify if self.war else False
        self.defender_fortified = self.war.def_fortify if self.war else False

        self.attacker_air_value = self.attacker.aircraft * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT).army_value
        self.defender_air_value = self.defender.aircraft * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT).army_value

        self.attacker_naval_value = self.attacker.ships * MilitaryUnit(MilitaryUnitEnum.SHIP).army_value
        self.defender_naval_value = self.defender.ships * MilitaryUnit(MilitaryUnitEnum.SHIP).army_value

        self.attacker_casualties_aircraft_value = weird_division((self.attacker_air_value + self.defender_air_value) , (self.attacker_air_value ** (3/4) + self.defender_air_value ** (3/4))) * self.attacker_air_value ** (3/4)
        self.defender_casualties_aircraft_value = weird_division((self.attacker_air_value + self.defender_air_value) , (self.attacker_air_value ** (3/4) + self.defender_air_value ** (3/4))) * self.defender_air_value ** (3/4)

        self.attacker_casualties_ships_value = weird_division((self.attacker_naval_value + self.defender_naval_value) , (self.attacker_naval_value ** (3/4) + self.defender_naval_value ** (3/4))) * self.attacker_naval_value ** (3/4)
        self.defender_casualties_ships_value = weird_division((self.attacker_naval_value + self.defender_naval_value) , (self.attacker_naval_value ** (3/4) + self.defender_naval_value ** (3/4))) * self.defender_naval_value ** (3/4)

    @property
    def attacker_ground_army_value(self) -> float:
        return get_army_value(soldiers=self.attacker.soldiers, tanks=self.attacker.tanks, using_munitions=self.attacker_using_munitions, air_superiority=self.attacker_air_superiority)
    
    @property
    def attacker_soldiers_value(self) -> float:
        return get_army_value(soldiers=self.attacker.soldiers, using_munitions=self.attacker_using_munitions)

    @property
    def attacker_tanks_value(self) -> float:
        return get_army_value(tanks=self.attacker.tanks, air_superiority=self.attacker_air_superiority)

    @property
    def defender_ground_army_value(self) -> float:
        return get_army_value(soldiers=self.defender.soldiers, resisting_population=resisting_population(self.defender.population), tanks=self.defender.tanks, using_munitions=self.defender_using_munitions, air_superiority=self.defender_air_superiority)
    
    @property
    def defender_soldiers_value(self) -> float:
        return get_army_value(soldiers=self.defender.soldiers, using_munitions=self.defender_using_munitions)
    
    @property
    def defender_tanks_value(self) -> float:
        return get_army_value(tanks=self.defender.tanks, air_superiority=self.defender_air_superiority)
    
    @property
    def defender_population_value(self) -> float:
        return get_army_value(resisting_population=resisting_population(self.defender.population), using_munitions=self.defender_using_munitions)
    
    @property
    def ground_winrate(self) -> float:
        """
        Calculates the ground winrate of the attacker.
        """
        return universal_winrate(self.attacker_ground_army_value, self.defender_ground_army_value)
    
    @property
    def air_winrate(self) -> float:
        """
        Calculates the air winrate of the attacker.
        """
        return universal_winrate(self.attacker.aircraft, self.defender.aircraft)
    
    @property
    def naval_winrate(self) -> float:
        """
        Calculates the naval winrate of the attacker.
        """
        return universal_winrate(self.attacker.ships, self.defender.ships)
    
    @property
    def total_winrate(self) -> float:
        """
        Calculates the total winrate of the attacker. Average of ground, air and naval winrates.
        """
        return (self.ground_winrate() + self.air_winrate() + self.naval_winrate()) / 3
    
    def attack_result_type_odds(self, attack_type: AttackType, result_type: AttackSuccess) -> float:
        """
        Calculates the odds of a specific attack result.
        """
        if attack_type == AttackType.GROUND:
            winrate_func = self.ground_winrate
        elif attack_type in [AttackType.AIRVAIR, AttackType.AIRVINFRA, AttackType.AIRVMONEY, AttackType.AIRVSHIPS, AttackType.AIRVSOLDIERS, AttackType.AIRVTANKS]:
            winrate_func = self.air_winrate
        elif attack_type == AttackType.NAVAL:
            winrate_func = self.naval_winrate
        else:
            raise Exception("Invalid attack type.")

        if result_type == AttackSuccess.IMMENSE_TRIUMPH:
            return winrate_func ** 3
        elif result_type == AttackSuccess.MODERATE_SUCCESS:
            return (winrate_func ** 2) * (1 - winrate_func)
        elif result_type == AttackSuccess.PYRRHIC_VICTORY:
            return winrate_func * ((1 - winrate_func) ** 2)
        elif result_type == AttackSuccess.UTTER_FAILURE:
            return (1 - winrate_func) ** 3
    
    def attack_result_all_types_odds(self, attack_type: AttackType) -> dict[AttackSuccess, float]:
        """
        Calculates the odds of all attack results.
        """
        return {
            result_type: self.attack_result_type_odds(attack_type, result_type)
            for result_type in AttackSuccess
        }

    @property
    def attacker_casualties_soldiers_value(self):    
        return casualties_calculation_army_value(self.attacker_soldiers_value, self.defender_soldiers_value, AttackerEnum.ATTACKER)

    @property
    def attacker_casualties_tanks_value(self):    
        return casualties_calculation_army_value(self.attacker_tanks_value, self.defender_tanks_value, AttackerEnum.ATTACKER)

    @property
    def defender_casualties_soldiers_value(self):    
        return casualties_calculation_army_value(self.defender_soldiers_value, self.attacker_soldiers_value, AttackerEnum.DEFENDER)

    @property
    def defender_casualties_tanks_value(self):    
        return casualties_calculation_army_value(self.defender_tanks_value, self.attacker_tanks_value, AttackerEnum.DEFENDER)

    # TODO how does population come into play?
    # defender_casualties_population_value = (self.defender.population / 400) ** (3/4)

    def __stat_type_to_normal_casualties_modifier(self, stat_type: StatsEnum) -> float:
        """
        Converts a stat type to a normal casualties modifier. Average is 0.7 and difference is 0.3.
        """
        if stat_type == StatsEnum.AVERAGE:
            return 0.7
        elif stat_type == StatsEnum.DIFFERENCE:
            return 0.3
        else:
            raise ValueError("Invalid stat type")

    def ground_attack_attacker_soldiers_casualties(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of soldiers the attacker will lose in a ground attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(stat_type)
        return ground_attack_attacker_soldiers_casualties(self.defender_casualties_soldiers_value, self.defender_casualties_tanks_value, self.attacker.soldiers, self.defender_fortified, random_modifier)
    
    def ground_attack_attacker_tanks_casualties(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of tanks the attacker will lose in a ground attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(stat_type)
        return ground_attack_attacker_tanks_casualties(self.defender_casualties_soldiers_value, self.defender_casualties_tanks_value, self.attacker.tanks, self.ground_winrate, self.defender_fortified, random_modifier)

    def ground_attack_defender_soldiers_casualties(self, stat_type: StatsEnum) ->  float:
        """
        Calculates the amount of soldiers the defender will lose in a ground attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(stat_type)
        return ground_attack_defender_soldiers_casualties(self.attacker_casualties_soldiers_value, self.attacker_casualties_tanks_value, self.defender.soldiers, random_modifier)
    
    def ground_attack_defender_tanks_casualties(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of tanks the defender will lose in a ground attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(stat_type)
        return ground_attack_defender_tanks_casualties(self.attacker_casualties_soldiers_value, self.attacker_casualties_tanks_value, self.defender.tanks, self.ground_winrate, random_modifier)
    
    def ground_attack_defender_aircraft_casualties(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of aircraft the defender will lose in a ground attack.
        """
        # TODO what are the casualty ratios?
        return ground_attack_defender_aircraft_casualties(self.attacker.tanks, self.defender.aircraft, self.ground_winrate)
    
    def air_v_air_attacker_aircraft_casualties(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of aircraft the attacker will lose in an air v air attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(stat_type)
        return air_v_air_attacker_aircraft_casualties(self.defender_casualties_aircraft_value, random_modifier, self.defender_fortified)
    
    def air_v_air_defender_aircraft_casualties(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of aircraft the defender will lose in an air v air attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(stat_type)
        return air_v_air_defender_aircraft_casualties(self.attacker_casualties_aircraft_value, random_modifier)
    
    def air_v_other_attacker_aircraft_casualties(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of aircraft the attacker will lose in an air v other attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(stat_type)
        return air_v_other_attacker_aircraft_casualties(self.defender_casualties_aircraft_value, random_modifier, self.defender_fortified)
    
    def air_v_other_defender_aircraft_casualties(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of aircraft the defender will lose in an air v other attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(stat_type)
        return air_v_other_defender_aircraft_casualties(self.attacker_casualties_aircraft_value, random_modifier)
    
    def __stat_type_to_airstrike_casualties_modifier(self, stat_type: StatsEnum) -> float:
        if stat_type == StatsEnum.AVERAGE:
            return 0.95
        elif stat_type == StatsEnum.DIFFERENCE:
            return 0.1
        else:
            raise ValueError("Invalid stat type")
    
    def air_v_money_defender_money_lost(self) -> float:
        # TODO
        return 0
    
    def air_v_ships_defender_ships_casualties(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of ships the defender will lose in an air v ships attack.
        """
        # TODO is it correct to use the random_modifier here?
        random_modifier = self.__stat_type_to_airstrike_casualties_modifier(stat_type)
        return air_v_ships_defender_ships_casualties(self.defender.ships, self.attacker.aircraft, self.defender.aircraft, random_modifier, self.air_winrate)
    
    def air_v_soldiers_defender_soldiers_casualties(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of soldiers the defender will lose in an air v soldiers attack.
        """
        # TODO is it correct to use the random_modifier here?
        random_modifier = self.__stat_type_to_airstrike_casualties_modifier(stat_type)
        return air_v_soldiers_defender_soldiers_casualties(self.defender.soldiers, self.attacker.aircraft, self.defender.aircraft, random_modifier, self.air_winrate)
    
    def air_v_tanks_defender_tanks_casualties(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of tanks the defender will lose in an air v tanks attack.
        """
        # TODO is it correct to use the random_modifier here?
        random_modifier = self.__stat_type_to_airstrike_casualties_modifier(stat_type)
        return air_v_tanks_defender_tanks_casualties(self.defender.tanks, self.attacker.aircraft, self.defender.aircraft, random_modifier, self.air_winrate)
    
    def naval_attack_attacker_ships_casualties(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of ships the attacker will lose in a naval attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(stat_type)
        return naval_attack_attacker_ships_casualties(self.defender_casualties_ships_value, self.defender_fortified, random_modifier)  
    
    def naval_attack_defender_ships_casualties(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of ships the defender will lose in a naval attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(stat_type)
        return naval_attack_defender_ships_casualties(self.attacker_casualties_ships_value, random_modifier)
    
    def ground_attack_loot(self, stat_type: StatsEnum, attacker: AttackerEnum) -> float:
        """
        Calculates the amount of loot the attacker will get in a ground attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(stat_type)
        return ground_attack_loot(self.attacker_soldiers_value, self.attacker_tanks_value, self.ground_winrate, self.attacker.war_policy_details, self.defender.war_policy_details, attacker, random_modifier, self.war._war_type_details if self.war else WarTypeDetails(WarTypeEnum.ORDINARY), self.attacker._pirate_economy, self.attacker._advanced_pirate_economy)
    
    async def ground_attack_infrastructure_destroyed(self, stat_type: StatsEnum, attacker: AttackerEnum) -> float:
        random_modifier = self.__stat_type_to_airstrike_casualties_modifier(stat_type)
        return ground_attack_infrastructure_destroyed(self.attacker_soldiers_value, self.attacker_tanks_value, self.defender_soldiers_value, self.defender_tanks_value, self.ground_winrate, (await self.defender.highest_infra_city).infrastructure, self.attacker.war_policy_details, self.defender.war_policy_details, AttackerEnum.ATTACKER, random_modifier, self.war._war_type_details if self.war else WarTypeDetails(WarTypeEnum.ORDINARY))
    
    async def air_v_infra_infrastructure_destroyed(self, stat_type: StatsEnum, attacker: AttackerEnum) -> float:
        random_modifier = self.__stat_type_to_airstrike_casualties_modifier(stat_type)
        return air_v_infra_infrastructure_destroyed(self.attacker.aircraft, self.defender.aircraft, (await self.defender.highest_infra_city).infrastructure, random_modifier, self.air_winrate, attacker, self.attacker.war_policy_details, self.defender.war_policy_details, self.war._war_type_details if self.war else WarTypeDetails(WarTypeEnum.ORDINARY))
    
    async def air_v_other_infrastructure_destroyed(self, stat_type: StatsEnum, attacker: AttackerEnum) -> float:
        random_modifier = self.__stat_type_to_airstrike_casualties_modifier(stat_type)
        return air_v_other_infrastructure_destroyed(self.attacker.aircraft, self.defender.aircraft, (await self.defender.highest_infra_city).infrastructure, random_modifier, self.air_winrate, attacker, self.attacker.war_policy_details, self.defender.war_policy_details, self.war._war_type_details if self.war else WarTypeDetails(WarTypeEnum.ORDINARY))
    
    async def naval_attack_infrastructure_destroyed(self, stat_type: StatsEnum, attacker: AttackerEnum) -> float:
        random_modifier = self.__stat_type_to_airstrike_casualties_modifier(stat_type)
        return naval_attack_infrastructure_destroyed(self.attacker.ships, self.defender.ships, (await self.defender.highest_infra_city).infrastructure, random_modifier, self.naval_winrate, attacker, self.attacker.war_policy_details, self.defender.war_policy_details, self.war._war_type_details if self.war else WarTypeDetails(WarTypeEnum.ORDINARY))
    
    @__infrastructure_destroyed(only_war = True)
    async def missile_strike_infrastructure_destroyed(self, stat_type: StatsEnum) -> float:
        city = await self.defender.highest_infra_city
        
        avg = (300 + max(350, city.infrastructure * 100 / city.land * 3)) / 2
        diff = max(350, city.infrastructure * 100 / city.land * 3) - avg

        if stat_type == StatsEnum.AVERAGE:
            x = avg
        elif stat_type == StatsEnum.DIFFERENCE:
            x = diff
        else:
            raise ValueError("Invalid stat type")
        
        return (max(min(x, city.infrastructure * 0.8 + 150), 0))

    @__infrastructure_destroyed(only_war = True)
    async def nuclear_attack_infrastructure_destroyed(self, stat_type: StatsEnum) -> float:
        city = await self.defender.highest_infra_city

        avg = (1700 + max(2000, city.infrastructure * 100 / city.land * 13.5)) / 2
        diff = max(2000, city.infrastructure * 100 / city.land * 13.5) - avg

        if stat_type == StatsEnum.AVERAGE:
            x = avg
        elif stat_type == StatsEnum.DIFFERENCE:
            x = diff
        else:
            raise ValueError("Invalid stat type")
        
        return (max(min(x, city.infrastructure * 0.8 + 150), 0))
    
    async def __infrastructure_destroyed_value(self, func) -> float:
        """
        Calculates the value of infrastructure destroyed.
        """
        async def wrapper(*args, **kwargs):
            starting = (await self.defender.highest_infra_city).infrastructure
            ending = starting - await func(*args, **kwargs)
            return infra_cost(starting, ending, self.defender)
        return wrapper
    
    @__infrastructure_destroyed_value
    async def ground_attack_infrastructure_destroyed_value(self, stat_type: StatsEnum) -> float:
        """
        Calculates the value of infrastructure destroyed in a ground attack.
        """
        return await self.ground_attack_infrastructure_destroyed(stat_type)
    
    @__infrastructure_destroyed_value
    async def air_v_infra_infrastructure_destroyed_value(self, stat_type: StatsEnum) -> float:
        """
        Calculates the value of infrastructure destroyed in an air v infra attack.
        """
        return await self.air_v_infra_infrastructure_destroyed(stat_type)
    
    @__infrastructure_destroyed_value
    async def air_v_other_infrastructure_destroyed_value(self, stat_type: StatsEnum) -> float:
        """
        Calculates the value of infrastructure destroyed in an air v other (than infra) attack.
        """
        return await self.air_v_other_infrastructure_destroyed(stat_type)
    
    @__infrastructure_destroyed_value
    async def naval_attack_infrastructure_destroyed_value(self, stat_type: StatsEnum) -> float:
        """
        Calculates the value of infrastructure destroyed in a naval attack.
        """
        return await self.naval_attack_infrastructure_destroyed(stat_type)
    
    @__infrastructure_destroyed_value
    async def missile_strike_infrastructure_destroyed_value(self, stat_type: StatsEnum) -> float:
        """
        Calculates the value of infrastructure destroyed in a missile strike.
        """
        return await self.missile_strike_infrastructure_destroyed(stat_type)
    
    @__infrastructure_destroyed_value
    async def nuclear_attack_infrastructure_destroyed_value(self, stat_type: StatsEnum) -> float:
        """
        Calculates the value of infrastructure destroyed in a nuclear attack.
        """
        return await self.nuclear_attack_infrastructure_destroyed(stat_type)
    
    def __recovered_by_military_salvage(self, attacker_used: float, defender_used: float, winrate: float) -> float:
        """
        Calculates the amount of resources recovered by military salvage.
        :param attacker_used: The amount of resources used by the attacker.
        :param defender_used: The amount of resources used by the defender.
        :param winrate: The winrate of the attacker.
        """
        return (attacker_used + defender_used) * (int(self.attacker._military_salvage) * (winrate ** 3) * 0.05)

    def ground_attack_defender_aluminum_used(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of aluminum used by the defender in a ground attack.
        """
        return self.ground_attack_defender_aircraft_casualties(stat_type) * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT).aluminum_cost
    
    def ground_attack_attacker_aluminum_used(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of aluminum used by the attacker in a ground attack.
        """
        # TODO is aluminum from enemy planes recovered?
        return self.__recovered_by_military_salvage(0, self.ground_attack_defender_aircraft_casualties(stat_type), self.ground_winrate)
    
    def ground_attack_defender_gasoline_used(self) -> float:
        """
        Calculates the amount of gasoline used by the defender in a ground attack.
        """
        return self.defender.tanks * MilitaryUnit(MilitaryUnitEnum.TANK).gasoline_used * scale_with_winrate(self.ground_winrate)
    
    def ground_attack_attacker_gasoline_used(self) -> float:
        """
        Calculates the amount of gasoline used by the attacker in a ground attack.
        """
        return self.attacker.tanks * MilitaryUnit(MilitaryUnitEnum.TANK).gasoline_used
    
    def ground_attack_defender_munitions_used(self) -> float:
        """
        Calculates the amount of munitions used by the defender in a ground attack.
        """
        return ((self.defender.soldiers + self.defender.population) * MilitaryUnit(MilitaryUnitEnum.SOLDIER).munitions_used * scale_with_winrate(self.ground_winrate) * int(self.defender_using_munitions)
                + self.defender.tanks * MilitaryUnit(MilitaryUnitEnum.TANK).munitions_used * scale_with_winrate(self.ground_winrate))
    
    def ground_attack_attacker_munitions_used(self) -> float:
        """
        Calculates the amount of munitions used by the attacker in a ground attack.
        """
        return (self.attacker.soldiers * MilitaryUnit(MilitaryUnitEnum.SOLDIER).munitions_used * int(self.attacker_using_munitions)
                + self.attacker.tanks * MilitaryUnit(MilitaryUnitEnum.TANK).munitions_used)
    
    def ground_attack_defender_steel_used(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of steel used by the defender in a ground attack.
        """
        return self.ground_attack_defender_tanks_casualties(stat_type) * MilitaryUnit(MilitaryUnitEnum.TANK).steel_cost
    
    def ground_attack_attacker_steel_used(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of steel used by the attacker in a ground attack.
        """
        return self.__recovered_by_military_salvage(self.ground_attack_attacker_tanks_casualties(stat_type) * MilitaryUnit(MilitaryUnitEnum.TANK).steel_cost, self.ground_attack_defender_steel_used, self.ground_winrate)
    
    def ground_attack_defender_money_used(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of money used by the defender in a ground attack.
        """
        return (self.defender.soldiers * MilitaryUnit(MilitaryUnitEnum.SOLDIER).money_cost
                + self.defender.tanks * MilitaryUnit(MilitaryUnitEnum.TANK).money_cost
                + self.ground_attack_infrastructure_destroyed_value(stat_type))
    
    def ground_attack_attacker_money_used(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of money used by the attacker in a ground attack.
        """
        return (self.attacker.soldiers * MilitaryUnit(MilitaryUnitEnum.SOLDIER).money_cost
                + self.attacker.tanks * MilitaryUnit(MilitaryUnitEnum.TANK).money_cost
                - self.ground_attack_loot(stat_type))
    

    def air_v_air_defender_aluminum_used(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of aluminum used by the defender in an air v air attack.
        """
        return self.air_v_air_defender_aircraft_casualties(stat_type) * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT).aluminum_cost
    
    def air_v_air_attacker_aluminum_used(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of aluminum used by the attacker in an air v air attack.
        """
        return self.__recovered_by_military_salvage(self.air_v_air_attacker_aircraft_casualties * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT).aluminum_cost, self.air_v_air_defender_aluminum_used(stat_type), self.air_winrate)
    
    def air_v_air_defender_gasoline_used(self) -> float:
        """
        Calculates the amount of gasoline used by the defender in an air v air attack.
        """
        return self.defender.aircraft * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT).gasoline_used * scale_with_winrate(self.air_winrate)
    
    def air_v_air_attacker_gasoline_used(self) -> float:
        """
        Calculates the amount of gasoline used by the attacker in an air v air attack.
        """
        return self.attacker.aircraft * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT).gasoline_used
    
    def air_v_air_defender_munitions_used(self) -> float:
        """
        Calculates the amount of munitions used by the defender in an air v air attack.
        """
        return self.defender.aircraft * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT).munitions_used * scale_with_winrate(self.air_winrate)
    
    def air_v_air_attacker_munitions_used(self) -> float:
        """
        Calculates the amount of munitions used by the attacker in an air v air attack.
        """
        return self.attacker.aircraft * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT).munitions_used
    
    def air_v_air_defender_steel_used(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of steel used by the defender in an air v air attack.
        """
        return 0
    
    def air_v_air_attacker_steel_used(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of steel used by the attacker in an air v air attack.
        """
        return 0
    
    def air_v_air_defender_money_used(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of money used by the defender in an air v air attack.
        """
        return (self.air_v_air_defender_aircraft_casualties(stat_type) * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT).money_cost
                + self.air_v_other_infrastructure_destroyed_value(stat_type))
    
    def air_v_air_attacker_money_used(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of money used by the attacker in an air v air attack.
        """
        return self.air_v_air_attacker_aircraft_casualties(stat_type) * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT).money_cost
    
    def air_v_other_defender_aluminum_used(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of aluminum used by the defender in an air v other attack.
        """
        return self.air_v_other_defender_aircraft_casualties(stat_type) * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT).aluminum_cost
    
    def air_v_other_attacker_aluminum_used(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of aluminum used by the attacker in an air v other attack.
        """
        return self.__recovered_by_military_salvage(self.air_v_other_attacker_aircraft_casualties * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT).aluminum_cost, self.air_v_other_defender_aluminum_used(stat_type), self.air_winrate)
    
    def air_v_all_defender_gasoline_used(self) -> float:
        """
        Calculates the amount of gasoline used by the defender in an air v other attack.
        """
        return self.defender.aircraft * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT).gasoline_used * scale_with_winrate(self.air_winrate)

    def air_v_all_attacker_gasoline_used(self) -> float:
        """
        Calculates the amount of gasoline used by the attacker in an air v other attack.
        """
        return self.attacker.aircraft * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT).gasoline_used

    def air_v_all_defender_munitions_used(self) -> float:
        """
        Calculates the amount of munitions used by the defender in an air v other attack.
        """
        return self.defender.aircraft * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT).munitions_used * scale_with_winrate(self.air_winrate)

    def air_v_all_attacker_munitions_used(self) -> float:
        """
        Calculates the amount of munitions used by the attacker in an air v other attack.
        """
        return self.attacker.aircraft * MilitaryUnit(MilitaryUnitEnum.AIRCRAFT).munitions_used

    def air_v_tanks_defender_steel_used(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of steel used by the defender in an air v tanks attack.
        """
        return self.air_v_tanks_defender_tanks_casualties(stat_type) * MilitaryUnit(MilitaryUnitEnum.TANK).steel_cost
    
    def air_v_tanks_attacker_steel_used(self, stat_type: StatsEnum) -> float:   
        """
        Calculates the amount of steel used by the attacker in an air v tanks attack.
        """
        return self.__recovered_by_military_salvage(0, self.air_v_tanks_defender_steel_used(stat_type), self.air_winrate)
    
    def air_v_ships_defender_steel_used(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of steel used by the defender in an air v ships attack.
        """
        return self.air_v_ships_defender_ships_casualties(stat_type) * MilitaryUnit(MilitaryUnitEnum.SHIP).steel_cost
    
    def air_v_ships_attacker_steel_used(self, stat_type: StatsEnum) -> float:
        """
        Calculates the amount of steel used by the attacker in an air v ships attack.
        """
        return self.__recovered_by_military_salvage(0, self.air_v_ships_defender_steel_used(stat_type), self.air_winrate)
    


async def battle_calc(self, nation1_id=None, nation2_id=None, nation1=None, nation2=None):
            def hide():
                results = {}

                if nation1 and nation1_id or nation2 and nation2_id:
                    raise Exception("You can't specify nation1 or nation2 multiple times!")
                if nation1:
                    results['nation1'] = nation1
                    nation1_id = nation1['id']
                if nation2:
                    results['nation2'] = nation2
                    nation2_id = nation2['id']
                if (nation1_id and not nation1) or (nation2_id and not nation2):
                    ids = []
                    if nation1_id:
                        ids.append(nation1_id)
                    if nation2_id:
                        ids.append(nation2_id)
                    nations = (await utils.call(f"{{nations(id:[{','.join(list(set(ids)))}]){{data{utils.get_query(queries.BATTLE_CALC)}}}}}"))['data']['nations']['data']
                    nations = sorted(nations, key=lambda x: int(x['id']))
                    for nation in nations:
                        if nation['id'] == nation1_id:
                            results['nation1'] = nation
                        if nation['id'] == nation2_id:
                            results['nation2'] = nation

                results['nation1_append'] = ""
                results['nation2_append'] = ""
                results['nation1_tanks'] = 1
                results['nation2_tanks'] = 1
                results['nation1_extra_cas'] = 1
                results['nation2_extra_cas'] = 1
                results['gc'] = None
                results['nation1_war_infra_mod'] = 0.5
                results['nation2_war_infra_mod'] = 0.5
                results['nation1_war_loot_mod'] = 0.5
                results['nation2_war_loot_mod'] = 0.5

                for war in results['nation1']['wars']:
                    if war['attid'] == nation2_id and war['turnsleft'] > 0 and war['defid'] == nation1_id:
                        if war['groundcontrol'] == nation1_id:
                            results['gc'] = results['nation1']
                            results['nation1_append'] += "<:small_gc:924988666613489685>"
                        elif war['groundcontrol'] == nation2_id:
                            results['gc'] = results['nation2']
                            results['nation2_append'] += "<:small_gc:924988666613489685>"
                        if war['airsuperiority'] == nation1_id:
                            results['nation2_tanks'] = 0.5
                            results['nation1_append'] += "<:small_air:924988666810601552>"
                        elif war['airsuperiority'] == nation2_id:
                            results['nation1_tanks'] = 0.5
                            results['nation2_append'] += "<:small_air:924988666810601552>"
                        if war['navalblockade'] == nation1_id: #blockade is opposite than the others
                            results['nation2_append'] += "<:small_blockade:924988666814808114>"
                        elif war['navalblockade'] == nation2_id:
                            results['nation1_append'] += "<:small_blockade:924988666814808114>"
                        if war['att_fortify']:
                            results['nation2_append'] += "<:fortified:925465012955385918>"
                            results['nation1_extra_cas'] = 1.25
                        if war['def_fortify']:
                            results['nation1_append'] += "<:fortified:925465012955385918>"
                            results['nation2_extra_cas'] = 1.25
                        if war['attpeace']:
                            results['nation2_append'] += "<:peace:926855240655990836>"
                        elif war['defpeace']:
                            results['nation1_append'] += "<:peace:926855240655990836>"
                        if war['war_type'] == "RAID":
                            results['nation2_war_infra_mod'] = 0.25
                            results['nation1_war_infra_mod'] = 0.5
                            results['nation2_war_loot_mod'] = 1
                            results['nation1_war_loot_mod'] = 1
                        elif war['war_type'] == "ORDINARY":
                            results['nation2_war_infra_mod'] = 0.5
                            results['nation1_war_infra_mod'] = 0.5
                            results['nation2_war_loot_mod'] = 0.5
                            results['nation1_war_loot_mod'] = 0.5
                        elif war['war_type'] == "ATTRITION":
                            results['nation2_war_infra_mod'] = 1
                            results['nation1_war_infra_mod'] = 1
                            results['nation2_war_loot_mod'] = 0.25
                            results['nation1_war_loot_mod'] = 0.5
                    elif war['defid'] == nation2_id and war['turnsleft'] > 0 and war['attid'] == nation1_id:
                        if war['groundcontrol'] == nation1_id:
                            results['gc'] = results['nation1']
                            results['nation1_append'] += "<:small_gc:924988666613489685>"
                        elif war['groundcontrol'] == nation2_id:
                            results['gc'] = results['nation2']
                            results['nation2_append'] += "<:small_gc:924988666613489685>"
                        if war['airsuperiority'] == nation1_id:
                            results['nation2_tanks'] = 0.5
                            results['nation1_append'] += "<:small_air:924988666810601552>"
                        elif war['airsuperiority'] == nation2_id:
                            results['nation1_tanks'] = 0.5
                            results['nation2_append'] += "<:small_air:924988666810601552>"
                        if war['navalblockade'] == nation1_id: #blockade is opposite than the others
                            results['nation2_append'] += "<:small_blockade:924988666814808114>"
                        elif war['navalblockade'] == nation2_id:
                            results['nation1_append'] += "<:small_blockade:924988666814808114>"
                        if war['att_fortify']:
                            results['nation1_append'] += "<:fortified:925465012955385918>"
                            results['nation2_extra_cas'] = 1.25
                        if war['def_fortify']:
                            results['nation2_append'] += "<:fortified:925465012955385918>"
                            results['nation1_extra_cas'] = 1.25
                        if war['attpeace']:
                            results['nation1_append'] += "<:peace:926855240655990836>"
                        elif war['defpeace']:
                            results['nation2_append'] += "<:peace:926855240655990836>"
                        if war['war_type'] == "RAID":
                            results['nation1_war_infra_mod'] = 0.25
                            results['nation2_war_infra_mod'] = 0.5
                            results['nation1_war_loot_mod'] = 1
                            results['nation2_war_loot_mod'] = 1
                        elif war['war_type'] == "ORDINARY":
                            results['nation1_war_infra_mod'] = 0.5
                            results['nation2_war_infra_mod'] = 0.5
                            results['nation1_war_loot_mod'] = 0.5
                            results['nation2_war_loot_mod'] = 0.5
                        elif war['war_type'] == "ATTRITION":
                            results['nation1_war_infra_mod'] = 1
                            results['nation2_war_infra_mod'] = 1
                            results['nation1_war_loot_mod'] = 0.25
                            results['nation2_war_loot_mod'] = 0.5
                
            for attacker, defender in [("nation1", "nation2"), ("nation2", "nation1")]:
                defender_tanks_value = (results[defender]['tanks'] * 40 * results[f'{defender}_tanks']) ** (3/4)
                defender_soldiers_value = (results[defender]['soldiers'] * 1.75 + results[defender]['population'] * 0.0025) ** (3/4)
                defender_army_value = (defender_soldiers_value + defender_tanks_value) ** (3/4)

                attacker_tanks_value = (results[attacker]['tanks'] * 40 * results[f'{attacker}_tanks']) ** (3/4)
                attacker_soldiers_value = (results[attacker]['soldiers'] * 1.75) ** (3/4)
                attacker_army_value = (attacker_soldiers_value + attacker_tanks_value) ** (3/4)

                results[f'{attacker}_ground_win_rate'] = self.winrate_calc(attacker_army_value, defender_army_value)
                results[f'{attacker}_ground_it'] = results[f'{attacker}_ground_win_rate']**3
                results[f'{attacker}_ground_mod'] = results[f'{attacker}_ground_win_rate']**2 * (1 - results[f'{attacker}_ground_win_rate']) * 3
                results[f'{attacker}_ground_pyr'] = results[f'{attacker}_ground_win_rate'] * (1 - results[f'{attacker}_ground_win_rate'])**2 * 3
                results[f'{attacker}_ground_fail'] = (1 - results[f'{attacker}_ground_win_rate'])**3

                attacker_aircraft_value = (results[attacker]['aircraft'] * 3) ** (3/4)
                defender_aircraft_value = (results[defender]['aircraft'] * 3) ** (3/4)
                results[f'{attacker}_air_win_rate'] = self.winrate_calc(attacker_aircraft_value, defender_aircraft_value)
                results[f'{attacker}_air_it'] = results[f'{attacker}_air_win_rate']**3
                results[f'{attacker}_air_mod'] = results[f'{attacker}_air_win_rate']**2 * (1 - results[f'{attacker}_air_win_rate']) * 3
                results[f'{attacker}_air_pyr'] = results[f'{attacker}_air_win_rate'] * (1 - results[f'{attacker}_air_win_rate'])**2 * 3
                results[f'{attacker}_air_fail'] = (1 - results[f'{attacker}_air_win_rate'])**3

                attacker_ships_value = (results[attacker]['ships'] * 4) ** (3/4)
                defender_ships_value = (results[defender]['ships'] * 4) ** (3/4)
                results[f'{attacker}_naval_win_rate'] = self.winrate_calc(attacker_ships_value, defender_ships_value)
                results[f'{attacker}_naval_it'] = results[f'{attacker}_naval_win_rate']**3
                results[f'{attacker}_naval_mod'] = results[f'{attacker}_naval_win_rate']**2 * (1 - results[f'{attacker}_naval_win_rate']) * 3
                results[f'{attacker}_naval_pyr'] = results[f'{attacker}_naval_win_rate'] * (1 - results[f'{attacker}_naval_win_rate'])**2 * 3
                results[f'{attacker}_naval_fail'] = (1 - results[f'{attacker}_naval_win_rate'])**3
                
                attacker_casualties_soldiers_value = utils.weird_division((attacker_soldiers_value**(4/3) + defender_soldiers_value**(4/3)) , (attacker_soldiers_value + defender_soldiers_value)) * attacker_soldiers_value
                defender_casualties_soldiers_value = utils.weird_division((attacker_soldiers_value**(4/3) + defender_soldiers_value**(4/3)) , (attacker_soldiers_value + defender_soldiers_value)) * defender_soldiers_value
                attacker_casualties_tanks_value = utils.weird_division((attacker_tanks_value**(4/3) + defender_tanks_value**(4/3)) , (attacker_tanks_value + defender_tanks_value)) * attacker_tanks_value
                defender_casualties_tanks_value = utils.weird_division((attacker_tanks_value**(4/3) + defender_tanks_value**(4/3)) , (attacker_tanks_value + defender_tanks_value)) * defender_tanks_value
                attacker_casualties_aircraft_value = utils.weird_division((attacker_aircraft_value**(4/3) + defender_aircraft_value**(4/3)) , (attacker_aircraft_value + defender_aircraft_value)) * attacker_aircraft_value
                defender_casualties_aircraft_value = utils.weird_division((attacker_aircraft_value**(4/3) + defender_aircraft_value**(4/3)) , (attacker_aircraft_value + defender_aircraft_value)) * defender_aircraft_value
                attacker_casualties_ships_value = utils.weird_division((attacker_ships_value**(4/3) + defender_ships_value**(4/3)) , (attacker_ships_value + defender_ships_value)) * attacker_ships_value
                defender_casualties_ships_value = utils.weird_division((attacker_ships_value**(4/3) + defender_ships_value**(4/3)) , (attacker_ships_value + defender_ships_value)) * defender_ships_value

                if results['gc'] == results[attacker]:
                    results[f'{attacker}_ground_{defender}_avg_aircraft'] = avg_air = round(min(results[attacker]['tanks'] * 0.005 * results[f'{attacker}_ground_win_rate'] ** 3, results[defender]['aircraft']))
                    results[defender]['aircas'] = f"Def. Plane: {avg_air} ± {round(results[attacker]['tanks'] * 0.005 * (1 - results[f'{attacker}_ground_win_rate'] ** 3))}"
                else:
                    results[defender]['aircas'] = ""
                    results[f'{attacker}_ground_{defender}_avg_aircraft'] = 0
                
                for type, cas_rate in [("avg", 0.7), ("diff", 0.3)]:
                    # values should be multiplied by 0.7 again? no... https://politicsandwar.fandom.com/wiki/Ground_Battles?so=search -> make a function for the average tank/soldier value roll giving success
                    results[f'{attacker}_ground_{attacker}_{type}_soldiers'] = min(round(((defender_casualties_soldiers_value * 0.0084) + (defender_casualties_tanks_value * 0.0092)) * cas_rate * 3), results[attacker]['soldiers'])
                    results[f'{attacker}_ground_{attacker}_{type}_tanks'] = min(round((((defender_casualties_soldiers_value * 0.0004060606) + (defender_casualties_tanks_value * 0.00066666666)) * results[f'{attacker}_ground_win_rate'] + ((defender_soldiers_value * 0.00043225806) + (defender_tanks_value * 0.00070967741)) * (1 - results[f'{attacker}_ground_win_rate'])) * cas_rate * 3), results[attacker]['tanks'])
                    results[f'{attacker}_ground_{defender}_{type}_soldiers'] = min(round(((attacker_casualties_soldiers_value * 0.0084) + (attacker_casualties_tanks_value * 0.0092)) * cas_rate * 3), results[defender]['soldiers'])
                    results[f'{attacker}_ground_{defender}_{type}_tanks'] = min(round((((attacker_casualties_soldiers_value * 0.00043225806) + (attacker_casualties_tanks_value * 0.00070967741)) * results[f'{attacker}_ground_win_rate'] + ((attacker_soldiers_value * 0.0004060606) + (attacker_tanks_value * 0.00066666666)) * (1 - results[f'{attacker}_ground_win_rate'])) * cas_rate * 3), results[defender]['tanks'])

                results[f'{attacker}_airvair_{attacker}_avg'] = min(round(defender_casualties_aircraft_value * 0.7 * 0.01 * 3 * results[f'{attacker}_extra_cas']), results[attacker]['aircraft'])
                results[f'{attacker}_airvair_{attacker}_diff'] = min(round(defender_casualties_aircraft_value * 0.3 * 0.01 * 3 * results[f'{attacker}_extra_cas']), results[attacker]['aircraft'])
                results[f'{attacker}_airvother_{attacker}_avg'] = min(round(defender_casualties_aircraft_value * 0.7 * 0.015385 * 3 * results[f'{attacker}_extra_cas']), results[attacker]['aircraft'])
                results[f'{attacker}_airvother_{attacker}_diff'] = min(round(defender_casualties_aircraft_value * 0.3 * 0.015385 * 3 * results[f'{attacker}_extra_cas']), results[attacker]['aircraft'])

                results[f'{attacker}_airvair_{defender}_avg'] = min(round(attacker_casualties_aircraft_value * 0.7 * 0.018337 * 3), results[defender]['aircraft'])
                results[f'{attacker}_airvair_{defender}_diff'] = min(round(attacker_casualties_aircraft_value * 0.3 * 0.018337 * 3), results[defender]['aircraft'])
                results[f'{attacker}_airvother_{defender}_avg'] = min(round(attacker_casualties_aircraft_value * 0.7 * 0.009091 * 3), results[defender]['aircraft'])
                results[f'{attacker}_airvother_{defender}_diff'] = min(round(attacker_casualties_aircraft_value * 0.3 * 0.009091 * 3), results[defender]['aircraft'])

                results[f'{attacker}_naval_{defender}_avg'] = min(round(attacker_casualties_ships_value * 0.7 * 0.01375 * 3 * results[f'{attacker}_extra_cas']), results[defender]['aircraft'])
                results[f'{attacker}_naval_{defender}_diff'] = min(round(attacker_casualties_ships_value * 0.3 * 0.01375 * 3 * results[f'{attacker}_extra_cas']), results[defender]['aircraft'])
                results[f'{attacker}_naval_{attacker}_avg'] = min(round(defender_casualties_ships_value * 0.7 * 0.01375 * 3), results[attacker]['aircraft'])
                results[f'{attacker}_naval_{attacker}_diff'] = min(round(defender_casualties_ships_value * 0.3 * 0.01375 * 3), results[attacker]['aircraft'])

            def def_rss_consumption(winrate: Union[int, float]) -> float:
                rate = -0.4624 * winrate**2 + 1.06256 * winrate + 0.3999            
                if rate < 0.4:
                    rate = 0.4
                return rate
                ## See note

            results["nation1"]['city'] = sorted(results['nation1']['cities'], key=lambda k: k['infrastructure'], reverse=True)[0]
            results["nation2"]['city'] = sorted(results['nation2']['cities'], key=lambda k: k['infrastructure'], reverse=True)[0]

            for nation in ["nation1", "nation2"]:
                results[f'{nation}_policy_infra_dealt'] = 1
                results[f'{nation}_policy_loot_stolen'] = 1
                results[f'{nation}_policy_infra_lost'] = 1
                results[f'{nation}_policy_loot_lost'] = 1
                results[f'{nation}_policy_improvements_lost'] = 1
                results[f'{nation}_policy_loot_stolen'] = 1
                results[f'{nation}_policy_improvements_destroyed'] = 1
                results[f'{nation}_vds_mod'] = 1
                results[f'{nation}_irond_mod'] = 1
                results[f'{nation}_fallout_shelter_mod'] = 1
                results[f'{nation}_military_salvage_mod'] = 0
                results[f'{nation}_pirate_econ_loot'] = 1
                results[f'{nation}_advanced_pirate_econ_loot'] = 1

                if results[f'{nation}']['warpolicy'] == "Attrition":
                    results[f'{nation}_policy_infra_dealt'] = 1.1
                    results[f'{nation}_policy_loot_stolen'] = 0.8
                elif results[f'{nation}']['warpolicy'] == "Turtle":
                    results[f'{nation}_policy_infra_lost'] = 0.9
                    results[f'{nation}_policy_loot_lost'] = 1.2
                elif results[f'{nation}']['warpolicy'] == "Moneybags":
                    results[f'{nation}_policy_infra_lost'] = 1.05
                    results[f'{nation}_policy_loot_lost'] = 0.6
                elif results[f'{nation}']['warpolicy'] == "Pirate":
                    results[f'{nation}_policy_improvements_lost'] = 2.0
                    results[f'{nation}_policy_loot_stolen'] = 1.4
                elif results[f'{nation}']['warpolicy'] == "Tactician":
                    results[f'{nation}_policy_improvements_destroyed'] = 2.0
                elif results[f'{nation}']['warpolicy'] == "Guardian":
                    results[f'{nation}_policy_improvements_lost'] = 0.5
                    results[f'{nation}_policy_loot_lost'] = 1.2
                elif results[f'{nation}']['warpolicy'] == "Covert":
                    results[f'{nation}_policy_infra_lost'] = 1.05
                elif results[f'{nation}']['warpolicy'] == "Arcane":
                    results[f'{nation}_policy_infra_lost'] = 1.05
                if results[f'{nation}']['vds']:
                    results[f'{nation}_vds_mod'] = 0.75
                if results[f'{nation}']['irond']:
                    results[f'{nation}_irond_mod'] = 0.7
                if results[f'{nation}']['fallout_shelter']:
                    results[f'{nation}_fallout_shelter_mod'] = 0.9
                if results[f'{nation}']['military_salvage']:
                    results[f'{nation}_military_salvage_mod'] = 1
                if results[f'{nation}']['pirate_economy']:
                    results[f'{nation}_pirate_econ_loot'] = 1.05
                if results[f'{nation}']['advanced_pirate_economy']:
                    results[f'{nation}_advanced_pirate_econ_loot'] = 1.05
            
            def airstrike_casualties(winrate: Union[int, float]) -> float:
                rate = -0.4624 * winrate**2 + 1.06256 * winrate + 0.3999            
                if rate < 0.4:
                    rate = 0.4
                return rate
            
            def salvage(winrate, resources) -> int:
                return resources * (results[f'{attacker}_military_salvage_mod'] * (winrate ** 3) * 0.05)

            for attacker, defender in [("nation1", "nation2"), ("nation2", "nation1")]:
                results[f'{attacker}_ground_{defender}_lost_infra_avg'] = max(min(((results[attacker]['soldiers'] - results[defender]['soldiers'] * 0.5) * 0.000606061 + (results[attacker]['tanks'] - (results[defender]['tanks'] * 0.5)) * 0.01) * 0.95 * results[f'{attacker}_ground_win_rate'], results[defender]['city']['infrastructure'] * 0.2 + 25), 0) * results[f'{attacker}_war_infra_mod'] * results[f'{attacker}_policy_infra_dealt'] * results[f'{defender}_policy_infra_lost']
                results[f'{attacker}_ground_{defender}_lost_infra_diff'] = results[f'{attacker}_ground_{defender}_lost_infra_avg'] / 0.95 * 0.15
                results[f'{attacker}_ground_loot_avg'] = (results[attacker]['soldiers'] * 1.1 + results[attacker]['tanks'] * 25.15) * (results[f'{attacker}_ground_win_rate'] ** 3) * 3 * 0.95 * results[f'{attacker}_war_loot_mod'] * results[f'{attacker}_policy_loot_stolen'] * results[f'{defender}_policy_loot_lost'] * results[f'{attacker}_pirate_econ_loot'] * results[f'{attacker}_advanced_pirate_econ_loot']
                results[f'{attacker}_ground_loot_diff'] = results[f'{attacker}_ground_loot_avg'] / 0.95 * 0.1

                results[f'{attacker}_air_{defender}_lost_infra_avg'] = max(min((results[attacker]['aircraft'] - results[defender]['aircraft'] * 0.5) * 0.35353535 * 0.95 * results[f'{attacker}_air_win_rate'], results[defender]['city']['infrastructure'] * 0.5 + 100), 0) * results[f'{attacker}_war_infra_mod'] * results[f'{attacker}_policy_infra_dealt'] * results[f'{defender}_policy_infra_lost']
                results[f'{attacker}_air_{defender}_lost_infra_diff'] = results[f'{attacker}_air_{defender}_lost_infra_avg'] / 0.95 * 0.15
                results[f'{attacker}_air_{defender}_soldiers_destroyed_avg'] = round(max(min(results[defender]['soldiers'], results[defender]['soldiers'] * 0.75 + 1000, (results[attacker]['aircraft'] - results[defender]['aircraft'] * 0.5) * 35 * 0.95), 0)) * airstrike_casualties(results[f'{attacker}_air_win_rate'])
                results[f'{attacker}_air_{defender}_soldiers_destroyed_diff'] = results[f'{attacker}_air_{defender}_soldiers_destroyed_avg'] / 0.95 * 0.1
                results[f'{attacker}_air_{defender}_tanks_destroyed_avg'] = round(max(min(results[defender]['tanks'], results[defender]['tanks'] * 0.75 + 10, (results[attacker]['aircraft'] - results[defender]['aircraft'] * 0.5) * 1.25 * 0.95), 0)) * airstrike_casualties(results[f'{attacker}_air_win_rate'])
                results[f'{attacker}_air_{defender}_tanks_destroyed_diff'] = results[f'{attacker}_air_{defender}_tanks_destroyed_avg'] / 0.95 * 0.1
                results[f'{attacker}_air_{defender}_ships_destroyed_avg'] = round(max(min(results[defender]['ships'], results[defender]['ships'] * 0.75 + 4, (results[attacker]['aircraft'] - results[defender]['aircraft'] * 0.5) * 0.0285 * 0.95), 0)) * airstrike_casualties(results[f'{attacker}_air_win_rate'])
                results[f'{attacker}_air_{defender}_ships_destroyed_diff'] = results[f'{attacker}_air_{defender}_ships_destroyed_avg'] / 0.95 * 0.1

                results[f'{attacker}_naval_{defender}_lost_infra_avg'] = max(min((results[attacker]['ships'] - results[attacker]['ships'] * 0.5) * 2.625 * 0.95 * results[f'{attacker}_naval_win_rate'], results[defender]['city']['infrastructure'] * 0.5 + 25), 0) * results[f'{attacker}_war_infra_mod'] * results[f'{attacker}_policy_infra_dealt'] * results[f'{defender}_policy_infra_lost']
                results[f'{attacker}_naval_{defender}_lost_infra_diff'] = results[f'{attacker}_naval_{defender}_lost_infra_avg'] / 0.95 * 0.15

                results[f'{attacker}_nuke_{defender}_lost_infra_avg'] = max(min((1700 + max(2000, results[defender]['city']['infrastructure'] * 100 / results[defender]['city']['land'] * 13.5)) / 2, results[defender]['city']['infrastructure'] * 0.8 + 150), 0) * results[f'{attacker}_war_infra_mod'] * results[f'{attacker}_policy_infra_dealt'] * results[f'{defender}_policy_infra_lost'] * results[f'{defender}_fallout_shelter_mod']
                results[f'{attacker}_missile_{defender}_lost_infra_avg'] = max(min((300 + max(350, results[defender]['city']['infrastructure'] * 100 / results[defender]['city']['land'] * 3)) / 2, results[defender]['city']['infrastructure'] * 0.3 + 100), 0) * results[f'{attacker}_war_infra_mod'] * results[f'{attacker}_policy_infra_dealt'] * results[f'{defender}_policy_infra_lost']
                
                for infra in [
                        f"{attacker}_ground_{defender}_lost_infra",
                        f"{attacker}_air_{defender}_lost_infra",
                        f"{attacker}_naval_{defender}_lost_infra",
                        f"{attacker}_nuke_{defender}_lost_infra",
                        f"{attacker}_missile_{defender}_lost_infra",
                    ]:
                    if "missile" in infra:
                        modifier = results[f'{defender}_irond_mod']
                    elif "nuke" in infra:
                        modifier = results[f'{defender}_vds_mod']
                    else:
                        modifier = 1
                    results[f'{infra}_avg_value'] = utils.infra_cost(results[defender]['city']['infrastructure'] - results[f'{infra}_avg'], results[defender]['city']['infrastructure']) * modifier
                
                for attack in ['airvair', 'airvsoldiers', 'airvtanks', 'airvships']:
                    results[f"{attacker}_{attack}_{defender}_lost_infra_avg_value"] = results[f"{attacker}_air_{defender}_lost_infra_avg_value"] * 1/3
                results[f"{attacker}_airvinfra_{defender}_lost_infra_avg_value"] = results[f"{attacker}_air_{defender}_lost_infra_avg_value"]


                results[f'{attacker}_ground_{attacker}_mun'] = results[attacker]['soldiers'] * 0.0002 + results[attacker]['tanks'] * 0.01
                results[f'{attacker}_ground_{attacker}_gas'] = results[attacker]['tanks'] * 0.01
                results[f'{attacker}_ground_{attacker}_alum'] = 0 #-salvage(results[f'{attacker}_ground_win_rate'], results[f'{attacker}_ground_{defender}_alum']) 
                results[f'{attacker}_ground_{attacker}_steel'] = results[f'{attacker}_ground_{attacker}_avg_tanks'] * 0.5 - salvage(results[f'{attacker}_ground_win_rate'], results[f'{attacker}_ground_{attacker}_avg_tanks'] * 0.5) - salvage(results[f'{attacker}_ground_win_rate'], results[f'{attacker}_ground_{defender}_avg_tanks'] * 0.5)
                results[f'{attacker}_ground_{attacker}_money'] = -results[f'{attacker}_ground_loot_avg'] + results[f'{attacker}_ground_{attacker}_avg_tanks'] * 50 + results[f'{attacker}_ground_{attacker}_avg_soldiers'] * 5
                results[f'{attacker}_ground_{attacker}_total'] = results[f'{attacker}_ground_{attacker}_alum'] * 2971 + results[f'{attacker}_ground_{attacker}_steel'] * 3990 + results[f'{attacker}_ground_{attacker}_gas'] * 3340 + results[f'{attacker}_ground_{attacker}_mun'] * 1960 + results[f'{attacker}_ground_{attacker}_money'] 

                base_mun = (results[defender]['soldiers'] * 0.0002 + results[defender]['population'] / 2000000 + results[defender]['tanks'] * 0.01) * def_rss_consumption(results[f'{attacker}_ground_win_rate'])
                results[f'{attacker}_ground_{defender}_mun'] = (base_mun * (1 - results[f'{attacker}_ground_fail']) + min(base_mun, results[f'{attacker}_ground_{attacker}_mun']) * results[f'{attacker}_ground_fail'])
                base_gas = results[defender]['tanks'] * 0.01 * def_rss_consumption(results[f'{attacker}_ground_win_rate'])
                results[f'{attacker}_ground_{defender}_gas'] = (base_gas * (1 - results[f'{attacker}_ground_fail']) + min(base_gas, results[f'{attacker}_ground_{attacker}_gas']) * results[f'{attacker}_ground_fail'])
                results[f'{attacker}_ground_{defender}_alum'] = results[f'{attacker}_ground_{defender}_avg_aircraft'] * 5
                results[f'{attacker}_ground_{defender}_steel'] = results[f'{attacker}_ground_{defender}_avg_tanks'] * 0.5
                results[f'{attacker}_ground_{defender}_money'] = results[f'{attacker}_ground_loot_avg'] + results[f'{attacker}_ground_{defender}_avg_aircraft'] * 4000 + results[f'{attacker}_ground_{defender}_avg_tanks'] * 50 + results[f'{attacker}_ground_{defender}_avg_soldiers'] * 5 + results[f'{attacker}_ground_{defender}_lost_infra_avg_value']
                results[f'{attacker}_ground_{defender}_total'] = results[f'{attacker}_ground_{defender}_alum'] * 2971 + results[f'{attacker}_ground_{defender}_steel'] * 3990 + results[f'{attacker}_ground_{defender}_gas'] * 3340 + results[f'{attacker}_ground_{defender}_mun'] * 1960 + results[f'{attacker}_ground_{defender}_money'] 
                results[f'{attacker}_ground_net'] = results[f'{attacker}_ground_{defender}_total'] - results[f'{attacker}_ground_{attacker}_total']
                

                for attack in ['air', 'airvair', 'airvinfra', 'airvsoldiers', 'airvtanks', 'airvships']:
                    results[f'{attacker}_{attack}_{attacker}_gas'] = results[f'{attacker}_{attack}_{attacker}_mun'] = results[attacker]['aircraft'] / 4
                    base_gas = results[defender]['aircraft'] / 4 * def_rss_consumption(results[f'{attacker}_air_win_rate'])
                    results[f'{attacker}_{attack}_{defender}_gas'] = results[f'{attacker}_{attack}_{defender}_mun'] = (base_gas * (1 - results[f'{attacker}_air_fail']) + min(base_gas, results[f'{attacker}_air_{attacker}_gas']) * results[f'{attacker}_air_fail'])

                results[f'{attacker}_airvair_{attacker}_alum'] = results[f'{attacker}_airvair_{attacker}_avg'] * 5 - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvair_{attacker}_avg'] * 5) - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvair_{defender}_avg'] * 5)
                results[f'{attacker}_airvair_{attacker}_steel'] = 0
                results[f'{attacker}_airvair_{attacker}_money'] = results[f'{attacker}_airvair_{attacker}_avg'] * 4000
                results[f'{attacker}_airvair_{attacker}_total'] = results[f'{attacker}_airvair_{attacker}_alum'] * 2971 + results[f'{attacker}_airvair_{attacker}_steel'] * 3990 + results[f'{attacker}_air_{attacker}_gas'] * 3340 + results[f'{attacker}_air_{attacker}_mun'] * 1960 + results[f'{attacker}_airvair_{attacker}_money'] 
               
                results[f'{attacker}_airvair_{defender}_alum'] = results[f'{attacker}_airvair_{defender}_avg'] * 5
                results[f'{attacker}_airvair_{defender}_steel'] = 0
                results[f'{attacker}_airvair_{defender}_money'] = results[f'{attacker}_airvair_{defender}_avg'] * 4000 + results[f'{attacker}_air_{defender}_lost_infra_avg_value'] * 1/3
                results[f'{attacker}_airvair_{defender}_total'] = results[f'{attacker}_airvair_{defender}_alum'] * 2971 + results[f'{attacker}_airvair_{defender}_steel'] * 3990 + results[f'{attacker}_air_{defender}_gas'] * 3340 + results[f'{attacker}_air_{defender}_mun'] * 1960 + results[f'{attacker}_airvair_{defender}_money'] 
                results[f'{attacker}_airvair_net'] = results[f'{attacker}_airvair_{defender}_total'] - results[f'{attacker}_airvair_{attacker}_total']


                results[f'{attacker}_airvinfra_{attacker}_alum'] = results[f'{attacker}_airvother_{attacker}_avg'] * 5 - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvother_{attacker}_avg'] * 5) - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvother_{defender}_avg'] * 5)
                results[f'{attacker}_airvinfra_{attacker}_steel'] = 0
                results[f'{attacker}_airvinfra_{attacker}_money'] = results[f'{attacker}_airvother_{attacker}_avg'] * 4000
                results[f'{attacker}_airvinfra_{attacker}_total'] = results[f'{attacker}_airvinfra_{attacker}_alum'] * 2971 + results[f'{attacker}_airvinfra_{attacker}_steel'] * 3990 + results[f'{attacker}_air_{attacker}_gas'] * 3340 + results[f'{attacker}_air_{attacker}_mun'] * 1960 + results[f'{attacker}_airvinfra_{attacker}_money'] 

                results[f'{attacker}_airvinfra_{defender}_alum'] = results[f'{attacker}_airvother_{defender}_avg'] * 5
                results[f'{attacker}_airvinfra_{defender}_steel'] = 0
                results[f'{attacker}_airvinfra_{defender}_money'] = results[f'{attacker}_airvother_{defender}_avg'] * 4000 + results[f'{attacker}_air_{defender}_lost_infra_avg_value']
                results[f'{attacker}_airvinfra_{defender}_total'] = results[f'{attacker}_airvinfra_{defender}_alum'] * 2971 + results[f'{attacker}_airvinfra_{defender}_steel'] * 3990 + results[f'{attacker}_air_{defender}_gas'] * 3340 + results[f'{attacker}_air_{defender}_mun'] * 1960 + results[f'{attacker}_airvinfra_{defender}_money'] 
                results[f'{attacker}_airvinfra_net'] = results[f'{attacker}_airvinfra_{defender}_total'] - results[f'{attacker}_airvinfra_{attacker}_total']


                results[f'{attacker}_airvsoldiers_{attacker}_alum'] = results[f'{attacker}_airvother_{attacker}_avg'] * 5 - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvother_{attacker}_avg'] * 5) - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvother_{defender}_avg'] * 5)
                results[f'{attacker}_airvsoldiers_{attacker}_steel'] = 0
                results[f'{attacker}_airvsoldiers_{attacker}_money'] = results[f'{attacker}_airvother_{attacker}_avg'] * 4000
                results[f'{attacker}_airvsoldiers_{attacker}_total'] = results[f'{attacker}_airvsoldiers_{attacker}_alum'] * 2971 + results[f'{attacker}_airvsoldiers_{attacker}_steel'] * 3990 + results[f'{attacker}_air_{attacker}_gas'] * 3340 + results[f'{attacker}_air_{attacker}_mun'] * 1960 + results[f'{attacker}_airvsoldiers_{attacker}_money'] 
                
                results[f'{attacker}_airvsoldiers_{defender}_alum'] = results[f'{attacker}_airvother_{defender}_avg'] * 5
                results[f'{attacker}_airvsoldiers_{defender}_steel'] = 0
                results[f'{attacker}_airvsoldiers_{defender}_money'] = results[f'{attacker}_airvother_{defender}_avg'] * 4000 + results[f'{attacker}_air_{defender}_lost_infra_avg_value'] * 1/3 + results[f'{attacker}_air_{defender}_soldiers_destroyed_avg'] * 5
                results[f'{attacker}_airvsoldiers_{defender}_total'] = results[f'{attacker}_airvsoldiers_{defender}_alum'] * 2971 + results[f'{attacker}_airvsoldiers_{defender}_steel'] * 3990 + results[f'{attacker}_air_{defender}_gas'] * 3340 + results[f'{attacker}_air_{defender}_mun'] * 1960 + results[f'{attacker}_airvsoldiers_{defender}_money'] 
                results[f'{attacker}_airvsoldiers_net'] = results[f'{attacker}_airvair_{defender}_total'] - results[f'{attacker}_airvsoldiers_{attacker}_total']
                

                results[f'{attacker}_airvtanks_{attacker}_alum'] = results[f'{attacker}_airvother_{attacker}_avg'] * 5 - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvother_{attacker}_avg'] * 5) - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvother_{defender}_avg'] * 5)
                results[f'{attacker}_airvtanks_{attacker}_steel'] = 0
                results[f'{attacker}_airvtanks_{attacker}_money'] = results[f'{attacker}_airvother_{attacker}_avg'] * 4000
                results[f'{attacker}_airvtanks_{attacker}_total'] = results[f'{attacker}_airvtanks_{attacker}_alum'] * 2971 + results[f'{attacker}_airvtanks_{attacker}_steel'] * 3990 + results[f'{attacker}_air_{attacker}_gas'] * 3340 + results[f'{attacker}_air_{attacker}_mun'] * 1960 + results[f'{attacker}_airvtanks_{attacker}_money'] 

                results[f'{attacker}_airvtanks_{defender}_alum'] = results[f'{attacker}_airvother_{defender}_avg'] * 5
                results[f'{attacker}_airvtanks_{defender}_steel'] = results[f'{attacker}_air_{defender}_tanks_destroyed_avg'] * 0.5
                results[f'{attacker}_airvtanks_{defender}_money'] = results[f'{attacker}_airvother_{defender}_avg'] * 4000 + results[f'{attacker}_air_{defender}_lost_infra_avg_value'] * 1/3 + results[f'{attacker}_air_{defender}_tanks_destroyed_avg'] * 60
                results[f'{attacker}_airvtanks_{defender}_total'] = results[f'{attacker}_airvtanks_{defender}_alum'] * 2971 + results[f'{attacker}_airvtanks_{defender}_steel'] * 3990 + results[f'{attacker}_air_{defender}_gas'] * 3340 + results[f'{attacker}_air_{defender}_mun'] * 1960 + results[f'{attacker}_airvtanks_{defender}_money'] 
                results[f'{attacker}_airvtanks_net'] = results[f'{attacker}_airvtanks_{defender}_total'] - results[f'{attacker}_airvtanks_{attacker}_total']


                results[f'{attacker}_airvships_{attacker}_alum'] = results[f'{attacker}_airvother_{attacker}_avg'] * 5 - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvother_{attacker}_avg'] * 5) - salvage(results[f'{attacker}_air_win_rate'], results[f'{attacker}_airvother_{defender}_avg'] * 5)
                results[f'{attacker}_airvships_{attacker}_steel'] = 0
                results[f'{attacker}_airvships_{attacker}_money'] = results[f'{attacker}_airvother_{attacker}_avg'] * 4000
                results[f'{attacker}_airvships_{attacker}_total'] = results[f'{attacker}_airvships_{attacker}_alum'] * 2971 + results[f'{attacker}_airvships_{attacker}_steel'] * 3990 + results[f'{attacker}_air_{attacker}_gas'] * 3340 + results[f'{attacker}_air_{attacker}_mun'] * 1960 + results[f'{attacker}_airvships_{attacker}_money'] 
                
                results[f'{attacker}_airvships_{defender}_alum'] = results[f'{attacker}_airvother_{defender}_avg'] * 5
                results[f'{attacker}_airvships_{defender}_steel'] = results[f'{attacker}_air_{defender}_ships_destroyed_avg'] * 30
                results[f'{attacker}_airvships_{defender}_money'] = results[f'{attacker}_airvother_{defender}_avg'] * 4000 + results[f'{attacker}_air_{defender}_lost_infra_avg_value'] * 1/3 + results[f'{attacker}_air_{defender}_ships_destroyed_avg'] * 50000
                results[f'{attacker}_airvships_{defender}_total'] = results[f'{attacker}_airvships_{defender}_alum'] * 2971 + results[f'{attacker}_airvships_{defender}_steel'] * 3990 + results[f'{attacker}_air_{defender}_gas'] * 3340 + results[f'{attacker}_air_{defender}_mun'] * 1960 + results[f'{attacker}_airvships_{defender}_money'] 
                results[f'{attacker}_airvships_net'] = results[f'{attacker}_airvships_{defender}_total'] - results[f'{attacker}_airvships_{attacker}_total']


                results[f'{attacker}_naval_{attacker}_mun'] = results[attacker]['ships'] * 2.5
                results[f'{attacker}_naval_{attacker}_gas'] = results[attacker]['ships'] * 1.5
                results[f'{attacker}_naval_{attacker}_alum'] = 0
                results[f'{attacker}_naval_{attacker}_steel'] = results[f'{attacker}_naval_{attacker}_avg'] * 30 + salvage(results[f'{attacker}_naval_win_rate'], results[f'{attacker}_naval_{attacker}_avg'] * 30) + salvage(results[f'{attacker}_naval_win_rate'], results[f'{attacker}_naval_{defender}_avg'] * 30)
                results[f'{attacker}_naval_{attacker}_money'] = results[f'{attacker}_naval_{attacker}_avg'] * 50000
                results[f'{attacker}_naval_{attacker}_total'] = results[f'{attacker}_naval_{attacker}_alum'] * 2971 + results[f'{attacker}_naval_{attacker}_steel'] * 3990 + results[f'{attacker}_naval_{attacker}_gas'] * 3340 + results[f'{attacker}_naval_{attacker}_mun'] * 1960 + results[f'{attacker}_naval_{attacker}_money'] 
            
                base_mun = results[defender]['ships'] * 2.5 * def_rss_consumption(results[f'{attacker}_naval_win_rate'])
                results[f'{attacker}_naval_{defender}_mun'] = results[f'{attacker}_naval_{defender}_mun'] = (base_mun * (1 - results[f'{attacker}_naval_fail']) + min(base_gas, results[f'{attacker}_naval_{attacker}_mun']) * results[f'{attacker}_naval_fail'])
                base_gas = results[defender]['ships'] * 1.5 * def_rss_consumption(results[f'{attacker}_naval_win_rate'])
                results[f'{attacker}_naval_{defender}_gas'] = results[f'{attacker}_naval_{defender}_gas'] = (base_gas * (1 - results[f'{attacker}_naval_fail']) + min(base_gas, results[f'{attacker}_naval_{attacker}_gas']) * results[f'{attacker}_naval_fail'])
                results[f'{attacker}_naval_{defender}_alum'] = 0
                results[f'{attacker}_naval_{defender}_steel'] = results[f'{attacker}_naval_{defender}_avg'] * 30
                results[f'{attacker}_naval_{defender}_money'] = results[f'{attacker}_naval_{defender}_lost_infra_avg_value'] + results[f'{attacker}_naval_{defender}_avg'] * 50000
                results[f'{attacker}_naval_{defender}_total'] = results[f'{attacker}_naval_{defender}_alum'] * 2971 + results[f'{attacker}_naval_{defender}_steel'] * 3990 + results[f'{attacker}_naval_{defender}_gas'] * 3340 + results[f'{attacker}_naval_{defender}_mun'] * 1960 + results[f'{attacker}_naval_{defender}_money'] 
                results[f'{attacker}_naval_net'] = results[f'{attacker}_naval_{defender}_total'] - results[f'{attacker}_naval_{attacker}_total']


                results[f'{attacker}_nuke_{attacker}_alum'] = 750
                results[f'{attacker}_nuke_{attacker}_steel'] = 0
                results[f'{attacker}_nuke_{attacker}_gas'] = 500
                results[f'{attacker}_nuke_{attacker}_mun'] = 0
                results[f'{attacker}_nuke_{attacker}_money'] = 1750000
                results[f'{attacker}_nuke_{attacker}_total'] = results[f'{attacker}_nuke_{attacker}_alum'] * 2971 + results[f'{attacker}_nuke_{attacker}_steel'] * 3990 + results[f'{attacker}_nuke_{attacker}_gas'] * 3340 + results[f'{attacker}_nuke_{attacker}_mun'] * 1960 + results[f'{attacker}_nuke_{attacker}_money'] + 250 * 3039 #price of uranium
                
                results[f'{attacker}_nuke_{defender}_alum'] = 0
                results[f'{attacker}_nuke_{defender}_steel'] = 0
                results[f'{attacker}_nuke_{defender}_gas'] = 0
                results[f'{attacker}_nuke_{defender}_mun'] = 0
                results[f'{attacker}_nuke_{defender}_money'] = results[f'{attacker}_nuke_{defender}_lost_infra_avg_value']
                results[f'{attacker}_nuke_{defender}_total'] = results[f'{attacker}_nuke_{defender}_alum'] * 2971 + results[f'{attacker}_nuke_{defender}_steel'] * 3990 + results[f'{attacker}_nuke_{defender}_gas'] * 3340 + results[f'{attacker}_nuke_{defender}_mun'] * 1960 + results[f'{attacker}_nuke_{defender}_money'] 
                results[f'{attacker}_nuke_net'] = results[f'{attacker}_nuke_{defender}_total'] - results[f'{attacker}_nuke_{attacker}_total']


                results[f'{attacker}_missile_{attacker}_alum'] = 100
                results[f'{attacker}_missile_{attacker}_steel'] = 0
                results[f'{attacker}_missile_{attacker}_gas'] = 75
                results[f'{attacker}_missile_{attacker}_mun'] = 75
                results[f'{attacker}_missile_{attacker}_money'] = 150000
                results[f'{attacker}_missile_{attacker}_total'] = results[f'{attacker}_missile_{attacker}_alum'] * 2971 + results[f'{attacker}_missile_{attacker}_steel'] * 3990 + results[f'{attacker}_missile_{attacker}_gas'] * 3340 + results[f'{attacker}_missile_{attacker}_mun'] * 1960 + results[f'{attacker}_missile_{attacker}_money']

                results[f'{attacker}_missile_{defender}_alum'] = 0
                results[f'{attacker}_missile_{defender}_steel'] = 0
                results[f'{attacker}_missile_{defender}_gas'] = 0
                results[f'{attacker}_missile_{defender}_mun'] = 0
                results[f'{attacker}_missile_{defender}_money'] = results[f'{attacker}_missile_{defender}_lost_infra_avg_value']
                results[f'{attacker}_missile_{defender}_total'] = results[f'{attacker}_missile_{defender}_alum'] * 2971 + results[f'{attacker}_missile_{defender}_steel'] * 3990 + results[f'{attacker}_missile_{defender}_gas'] * 3340 + results[f'{attacker}_missile_{defender}_mun'] * 1960 + results[f'{attacker}_missile_{defender}_money'] 
                results[f'{attacker}_missile_net'] = results[f'{attacker}_missile_{defender}_total'] - results[f'{attacker}_missile_{attacker}_total']
                
            return results