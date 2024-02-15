from __future__ import annotations

import src.utils as utils
import src.types as types

class BattleCalc:
    async def __init__(self, attacker: types.Nation, defender: types.Nation) -> None:
        self.attacker = attacker
        self.defender = defender

        self.war = None
        for war in await attacker.get_wars(types.WarAttackerFilter.ALL, types.WarActiveFilter.ACTIVE):
            if war.defender == defender:
                self.war = war
                break

        self.attacker_using_munitions = True
        self.defender_using_munitions = True

        self.attacker_air_superiority = self.war.air_superiority == self.attacker.id if self.war else False
        self.defender_air_superiority = self.war.air_superiority == self.defender.id if self.war else False

        self.attacker_fortified = self.war.att_fortify if self.war else False
        self.defender_fortified = self.war.def_fortify if self.war else False

        self.attacker_air_value = self.attacker.aircraft * \
            types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).army_value
        self.defender_air_value = self.defender.aircraft * \
            types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).army_value

        self.attacker_naval_value = self.attacker.ships * \
            types.MilitaryUnit(types.MilitaryUnitEnum.SHIP).army_value
        self.defender_naval_value = self.defender.ships * \
            types.MilitaryUnit(types.MilitaryUnitEnum.SHIP).army_value

        self.attacker_casualties_aircraft_value = utils.weird_division((self.attacker_air_value + self.defender_air_value), (
            self.attacker_air_value ** (3/4) + self.defender_air_value ** (3/4))) * self.attacker_air_value ** (3/4)
        self.defender_casualties_aircraft_value = utils.weird_division((self.attacker_air_value + self.defender_air_value), (
            self.attacker_air_value ** (3/4) + self.defender_air_value ** (3/4))) * self.defender_air_value ** (3/4)

        self.attacker_casualties_ships_value = utils.weird_division((self.attacker_naval_value + self.defender_naval_value), (
            self.attacker_naval_value ** (3/4) + self.defender_naval_value ** (3/4))) * self.attacker_naval_value ** (3/4)
        self.defender_casualties_ships_value = utils.weird_division((self.attacker_naval_value + self.defender_naval_value), (
            self.attacker_naval_value ** (3/4) + self.defender_naval_value ** (3/4))) * self.defender_naval_value ** (3/4)

    @property
    def attacker_ground_army_value(self) -> float:
        return utils.get_army_value(soldiers=self.attacker.soldiers, tanks=self.attacker.tanks, using_munitions=self.attacker_using_munitions, air_superiority=self.attacker_air_superiority)

    @property
    def attacker_soldiers_value(self) -> float:
        return utils.get_army_value(soldiers=self.attacker.soldiers, using_munitions=self.attacker_using_munitions)

    @property
    def attacker_tanks_value(self) -> float:
        return utils.get_army_value(tanks=self.attacker.tanks, air_superiority=self.attacker_air_superiority)

    @property
    def defender_ground_army_value(self) -> float:
        return utils.get_army_value(soldiers=self.defender.soldiers, resisting_population=utils.resisting_population(self.defender.population), tanks=self.defender.tanks, using_munitions=self.defender_using_munitions, air_superiority=self.defender_air_superiority)

    @property
    def defender_soldiers_value(self) -> float:
        return utils.get_army_value(soldiers=self.defender.soldiers, using_munitions=self.defender_using_munitions)

    @property
    def defender_tanks_value(self) -> float:
        return utils.get_army_value(tanks=self.defender.tanks, air_superiority=self.defender_air_superiority)

    @property
    def defender_population_value(self) -> float:
        return utils.get_army_value(resisting_population=utils.resisting_population(self.defender.population), using_munitions=self.defender_using_munitions)

    @property
    def ground_winrate(self) -> float:
        """
        Calculates the ground winrate of the attacker.
        """
        return utils.universal_winrate(self.attacker_ground_army_value, self.defender_ground_army_value)

    @property
    def air_winrate(self) -> float:
        """
        Calculates the air winrate of the attacker.
        """
        return utils.universal_winrate(self.attacker.aircraft, self.defender.aircraft)

    @property
    def naval_winrate(self) -> float:
        """
        Calculates the naval winrate of the attacker.
        """
        return utils.universal_winrate(self.attacker.ships, self.defender.ships)

    @property
    def total_winrate(self) -> float:
        """
        Calculates the total winrate of the attacker. Average of ground, air and naval winrates.
        """
        return (self.ground_winrate() + self.air_winrate() + self.naval_winrate()) / 3

    def attack_result_type_odds(self, attack_type: types.AttackType, result_type: types.AttackSuccess) -> float:
        """
        Calculates the odds of a specific attack result.
        """
        if attack_type == types.AttackType.GROUND:
            winrate_func = self.ground_winrate
        elif attack_type in [types.AttackType.AIRVAIR, types.AttackType.AIRVINFRA, types.AttackType.AIRVMONEY, types.AttackType.AIRVSHIPS, types.AttackType.AIRVSOLDIERS, types.AttackType.AIRVTANKS]:
            winrate_func = self.air_winrate
        elif attack_type == types.AttackType.NAVAL:
            winrate_func = self.naval_winrate
        else:
            raise Exception("Invalid attack type.")

        if result_type == types.AttackSuccess.IMMENSE_TRIUMPH:
            return winrate_func ** 3
        elif result_type == types.AttackSuccess.MODERATE_SUCCESS:
            return (winrate_func ** 2) * (1 - winrate_func)
        elif result_type == types.AttackSuccess.PYRRHIC_VICTORY:
            return winrate_func * ((1 - winrate_func) ** 2)
        elif result_type == types.AttackSuccess.UTTER_FAILURE:
            return (1 - winrate_func) ** 3

    def attack_result_all_types_odds(self, attack_type: types.AttackType) -> dict[types.AttackSuccess, float]:
        """
        Calculates the odds of all attack results.
        """
        return {
            result_type: self.attack_result_type_odds(attack_type, result_type)
            for result_type in types.AttackSuccess
        }

    @property
    def attacker_casualties_soldiers_value(self):
        return utils.casualties_calculation_army_value(self.attacker_soldiers_value, self.defender_soldiers_value, types.AttackerEnum.ATTACKER)

    @property
    def attacker_casualties_tanks_value(self):
        return utils.casualties_calculation_army_value(self.attacker_tanks_value, self.defender_tanks_value, types.AttackerEnum.ATTACKER)

    @property
    def defender_casualties_soldiers_value(self):
        return utils.casualties_calculation_army_value(self.defender_soldiers_value, self.attacker_soldiers_value, types.AttackerEnum.DEFENDER)

    @property
    def defender_casualties_tanks_value(self):
        return utils.casualties_calculation_army_value(self.defender_tanks_value, self.attacker_tanks_value, types.AttackerEnum.DEFENDER)

    # TODO how does population come into play?
    # defender_casualties_population_value = (self.defender.population / 400) ** (3/4)

    def __stat_type_to_normal_casualties_modifier(self, stat_type: types.StatsEnum) -> float:
        """
        Converts a stat type to a normal casualties modifier. Average is 0.7 and difference is 0.3.
        """
        if stat_type == types.StatsEnum.AVERAGE:
            return 0.7
        elif stat_type == types.StatsEnum.DIFFERENCE:
            return 0.3
        else:
            raise ValueError("Invalid stat type")

    # Casualties

    def ground_attack_attacker_soldiers_casualties(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of soldiers the attacker will lose in a ground attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(
            stat_type)
        return utils.ground_attack_attacker_soldiers_casualties(self.defender_casualties_soldiers_value, self.defender_casualties_tanks_value, self.attacker.soldiers, self.defender_fortified, random_modifier)

    def ground_attack_attacker_tanks_casualties(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of tanks the attacker will lose in a ground attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(
            stat_type)
        return utils.ground_attack_attacker_tanks_casualties(self.defender_casualties_soldiers_value, self.defender_casualties_tanks_value, self.attacker.tanks, self.ground_winrate, self.defender_fortified, random_modifier)

    def ground_attack_defender_soldiers_casualties(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of soldiers the defender will lose in a ground attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(
            stat_type)
        return utils.ground_attack_defender_soldiers_casualties(self.attacker_casualties_soldiers_value, self.attacker_casualties_tanks_value, self.defender.soldiers, random_modifier)

    def ground_attack_defender_tanks_casualties(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of tanks the defender will lose in a ground attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(
            stat_type)
        return utils.ground_attack_defender_tanks_casualties(self.attacker_casualties_soldiers_value, self.attacker_casualties_tanks_value, self.defender.tanks, self.ground_winrate, random_modifier)

    def ground_attack_defender_aircraft_casualties(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of aircraft the defender will lose in a ground attack.
        """
        # TODO what are the casualty ratios?
        return utils.ground_attack_defender_aircraft_casualties(self.attacker.tanks, self.defender.aircraft, self.ground_winrate)

    def air_v_air_attacker_aircraft_casualties(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of aircraft the attacker will lose in an air v air attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(
            stat_type)
        return utils.air_v_air_attacker_aircraft_casualties(self.defender_casualties_aircraft_value, random_modifier, self.defender_fortified)

    def air_v_air_defender_aircraft_casualties(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of aircraft the defender will lose in an air v air attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(
            stat_type)
        return utils.air_v_air_defender_aircraft_casualties(self.attacker_casualties_aircraft_value, random_modifier)

    def air_v_other_attacker_aircraft_casualties(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of aircraft the attacker will lose in an air v other attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(
            stat_type)
        return utils.air_v_other_attacker_aircraft_casualties(self.defender_casualties_aircraft_value, random_modifier, self.defender_fortified)

    air_v_soldiers_attacker_aircraft_casualties = \
        air_v_tanks_attacker_aircraft_casualties = \
        air_v_infra_attacker_aircraft_casualties = \
        air_v_money_attacker_aircraft_casualties = \
        air_v_ships_attacker_aircraft_casualties = \
        air_v_other_attacker_aircraft_casualties

    def air_v_other_defender_aircraft_casualties(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of aircraft the defender will lose in an air v other attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(
            stat_type)
        return utils.air_v_other_defender_aircraft_casualties(self.attacker_casualties_aircraft_value, random_modifier)

    air_v_soldiers_defender_aircraft_casualties = \
        air_v_tanks_defender_aircraft_casualties = \
        air_v_infra_defender_aircraft_casualties = \
        air_v_money_defender_aircraft_casualties = \
        air_v_ships_defender_aircraft_casualties = \
        air_v_other_defender_aircraft_casualties

    def __stat_type_to_airstrike_casualties_modifier(self, stat_type: types.StatsEnum) -> float:
        if stat_type == types.StatsEnum.AVERAGE:
            return 0.95
        elif stat_type == types.StatsEnum.DIFFERENCE:
            return 0.1
        else:
            raise ValueError("Invalid stat type")

    def air_v_money_defender_money_destroyed(self) -> float:
        # TODO
        return 0

    def air_v_ships_defender_ships_casualties(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of ships the defender will lose in an air v ships attack.
        """
        # TODO is it correct to use the random_modifier here?
        random_modifier = self.__stat_type_to_airstrike_casualties_modifier(
            stat_type)
        return utils.air_v_ships_defender_ships_casualties(self.defender.ships, self.attacker.aircraft, self.defender.aircraft, random_modifier, self.air_winrate)

    def air_v_soldiers_defender_soldiers_casualties(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of soldiers the defender will lose in an air v soldiers attack.
        """
        # TODO is it correct to use the random_modifier here?
        random_modifier = self.__stat_type_to_airstrike_casualties_modifier(
            stat_type)
        return utils.air_v_soldiers_defender_soldiers_casualties(self.defender.soldiers, self.attacker.aircraft, self.defender.aircraft, random_modifier, self.air_winrate)

    def air_v_tanks_defender_tanks_casualties(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of tanks the defender will lose in an air v tanks attack.
        """
        # TODO is it correct to use the random_modifier here?
        random_modifier = self.__stat_type_to_airstrike_casualties_modifier(
            stat_type)
        return utils.air_v_tanks_defender_tanks_casualties(self.defender.tanks, self.attacker.aircraft, self.defender.aircraft, random_modifier, self.air_winrate)

    def naval_attack_attacker_ships_casualties(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of ships the attacker will lose in a naval attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(
            stat_type)
        return utils.naval_attack_attacker_ships_casualties(self.defender_casualties_ships_value, self.defender_fortified, random_modifier)

    def naval_attack_defender_ships_casualties(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of ships the defender will lose in a naval attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(
            stat_type)
        return utils.naval_attack_defender_ships_casualties(self.attacker_casualties_ships_value, random_modifier)

    def ground_attack_loot(self, stat_type: types.StatsEnum, attacker: types.AttackerEnum) -> float:
        """
        Calculates the amount of loot the attacker will get in a ground attack.
        """
        random_modifier = self.__stat_type_to_normal_casualties_modifier(
            stat_type)
        return utils.ground_attack_loot(self.attacker_soldiers_value, self.attacker_tanks_value, self.ground_winrate, self.attacker._war_policy_details, self.defender._war_policy_details, attacker, random_modifier, self.war._war_type_details if self.war else types.WarTypeDetails(types.WarTypeEnum.ORDINARY), self.attacker._pirate_economy, self.attacker._advanced_pirate_economy)

    # Infrastructure destroyed

    async def ground_attack_infrastructure_destroyed(self, stat_type: types.StatsEnum, attacker: types.AttackerEnum) -> float:
        random_modifier = self.__stat_type_to_airstrike_casualties_modifier(
            stat_type)
        return utils.ground_attack_infrastructure_destroyed(self.attacker_soldiers_value, self.attacker_tanks_value, self.defender_soldiers_value, self.defender_tanks_value, self.ground_winrate, (await self.defender.highest_infra_city).infrastructure, self.attacker._war_policy_details, self.defender._war_policy_details, types.AttackerEnum.ATTACKER, random_modifier, self.war._war_type_details if self.war else types.WarTypeDetails(types.WarTypeEnum.ORDINARY))

    async def air_v_infra_infrastructure_destroyed(self, stat_type: types.StatsEnum, attacker: types.AttackerEnum) -> float:
        random_modifier = self.__stat_type_to_airstrike_casualties_modifier(
            stat_type)
        return utils.air_v_infra_infrastructure_destroyed(self.attacker.aircraft, self.defender.aircraft, (await self.defender.highest_infra_city).infrastructure, random_modifier, self.air_winrate, attacker, self.attacker._war_policy_details, self.defender._war_policy_details, self.war._war_type_details if self.war else types.WarTypeDetails(types.WarTypeEnum.ORDINARY))

    async def air_v_other_infrastructure_destroyed(self, stat_type: types.StatsEnum, attacker: types.AttackerEnum) -> float:
        random_modifier = self.__stat_type_to_airstrike_casualties_modifier(
            stat_type)
        return utils.air_v_other_infrastructure_destroyed(self.attacker.aircraft, self.defender.aircraft, (await self.defender.highest_infra_city).infrastructure, random_modifier, self.air_winrate, attacker, self.attacker._war_policy_details, self.defender._war_policy_details, self.war._war_type_details if self.war else types.WarTypeDetails(types.WarTypeEnum.ORDINARY))

    air_v_soldiers_infrastructure_destroyed = \
        air_v_tanks_infrastructure_destroyed = \
        air_v_money_infrastructure_destroyed = \
        air_v_ships_infrastructure_destroyed = \
        air_v_air_infrastructure_destroyed = \
        air_v_other_infrastructure_destroyed

    async def naval_attack_infrastructure_destroyed(self, stat_type: types.StatsEnum, attacker: types.AttackerEnum) -> float:
        random_modifier = self.__stat_type_to_airstrike_casualties_modifier(
            stat_type)
        return utils.naval_attack_infrastructure_destroyed(self.attacker.ships, self.defender.ships, (await self.defender.highest_infra_city).infrastructure, random_modifier, self.naval_winrate, attacker, self.attacker._war_policy_details, self.defender._war_policy_details, self.war._war_type_details if self.war else types.WarTypeDetails(types.WarTypeEnum.ORDINARY))

    async def missile_strike_infrastructure_destroyed(self, stat_type: types.StatsEnum, attacker: types.AttackerEnum) -> float:
        city = await self.defender.highest_infra_city
        return utils.missile_strike_infrastructure_destroyed(stat_type, city.infrastructure, city.land, self.war._war_type_details if self.war else types.WarTypeDetails(types.WarTypeEnum.ORDINARY), attacker)

    async def nuclear_attack_infrastructure_destroyed(self, stat_type: types.StatsEnum, attacker: types.AttackerEnum) -> float:
        city = await self.defender.highest_infra_city
        return utils.nuclear_attack_infrastructure_destroyed(stat_type, city.infrastructure, city.land, self.war._war_type_details if self.war else types.WarTypeDetails(types.WarTypeEnum.ORDINARY), attacker)

    # Value of infrastructure destroyed

    async def ground_attack_infrastructure_destroyed_value(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the value of infrastructure destroyed in a ground attack.
        """
        return await utils.infrastructure_destroyed_value(await self.ground_attack_infrastructure_destroyed(stat_type), self.defender)

    async def air_v_infra_infrastructure_destroyed_value(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the value of infrastructure destroyed in an air v infra attack.
        """
        return await utils.infrastructure_destroyed_value(await self.air_v_infra_infrastructure_destroyed(stat_type), self.defender)

    async def air_v_other_infrastructure_destroyed_value(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the value of infrastructure destroyed in an air v other (than infra) attack.
        """
        return await utils.infrastructure_destroyed_value(await self.air_v_other_infrastructure_destroyed(stat_type), self.defender)

    air_v_soldiers_infrastructure_destroyed_value = \
        air_v_tanks_infrastructure_destroyed_value = \
        air_v_money_infrastructure_destroyed_value = \
        air_v_ships_infrastructure_destroyed_value = \
        air_v_air_infrastructure_destroyed_value = \
        air_v_other_infrastructure_destroyed_value

    async def naval_attack_infrastructure_destroyed_value(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the value of infrastructure destroyed in a naval attack.
        """
        return await utils.infrastructure_destroyed_value(await self.naval_attack_infrastructure_destroyed(stat_type), self.defender)

    async def missile_strike_infrastructure_destroyed_value(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the value of infrastructure destroyed in a missile strike.
        """
        return await utils.infrastructure_destroyed_value(await self.missile_strike_infrastructure_destroyed(stat_type), self.defender)

    async def nuclear_attack_infrastructure_destroyed_value(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the value of infrastructure destroyed in a nuclear attack.
        """
        return await utils.infrastructure_destroyed_value(await self.nuclear_attack_infrastructure_destroyed(stat_type), self.defender)

    # Ground attack resource consumption

    def ground_attack_defender_aluminum_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of aluminum used by the defender in a ground attack.
        """
        return self.ground_attack_defender_aircraft_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).aluminum_cost

    def ground_attack_attacker_aluminum_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of aluminum used by the attacker in a ground attack.
        """
        # TODO is aluminum from enemy planes recovered?
        return 0

    def ground_attack_attacker_aluminum_recovered(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of aluminum recovered by the attacker in a ground attack.
        """
        return utils.utils.recovered_by_military_salvage(self.ground_attack_attacker_aluminum_used(stat_type), self.ground_attack_defender_aluminum_used(stat_type), self.ground_winrate)

    def ground_attack_defender_gasoline_used(self) -> float:
        """
        Calculates the amount of gasoline used by the defender in a ground attack.
        """
        return self.defender.tanks * types.MilitaryUnit(types.MilitaryUnitEnum.TANK).gasoline_used * utils.utils.scale_with_winrate(self.ground_winrate)

    def ground_attack_attacker_gasoline_used(self) -> float:
        """
        Calculates the amount of gasoline used by the attacker in a ground attack.
        """
        return self.attacker.tanks * types.MilitaryUnit(types.MilitaryUnitEnum.TANK).gasoline_used

    def ground_attack_defender_munitions_used(self) -> float:
        """
        Calculates the amount of munitions used by the defender in a ground attack.
        """
        return ((self.defender.soldiers + self.defender.population) * types.MilitaryUnit(types.MilitaryUnitEnum.SOLDIER).munitions_used * utils.utils.scale_with_winrate(self.ground_winrate) * int(self.defender_using_munitions)
                + self.defender.tanks * types.MilitaryUnit(types.MilitaryUnitEnum.TANK).munitions_used * utils.utils.scale_with_winrate(self.ground_winrate))

    def ground_attack_attacker_munitions_used(self) -> float:
        """
        Calculates the amount of munitions used by the attacker in a ground attack.
        """
        return (self.attacker.soldiers * types.MilitaryUnit(types.MilitaryUnitEnum.SOLDIER).munitions_used * int(self.attacker_using_munitions)
                + self.attacker.tanks * types.MilitaryUnit(types.MilitaryUnitEnum.TANK).munitions_used)

    def ground_attack_defender_steel_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of steel used by the defender in a ground attack.
        """
        return self.ground_attack_defender_tanks_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.TANK).steel_cost

    def ground_attack_attacker_steel_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of steel used by the attacker in a ground attack.
        """
        return self.ground_attack_attacker_tanks_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.TANK).steel_cost

    def ground_attack_attacker_steel_recovered(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of steel recovered by the attacker in a ground attack.
        """
        return utils.recovered_by_military_salvage(self.ground_attack_attacker_steel_used(stat_type), self.ground_attack_defender_steel_used(stat_type), self.ground_winrate)

    def ground_attack_defender_money_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of money used by the defender in a ground attack.
        """
        return (self.defender.soldiers * types.MilitaryUnit(types.MilitaryUnitEnum.SOLDIER).money_cost
                + self.defender.tanks *
                types.MilitaryUnit(types.MilitaryUnitEnum.TANK).money_cost
                + self.ground_attack_infrastructure_destroyed_value(stat_type)
                + self.ground_attack_loot(stat_type))

    def ground_attack_attacker_money_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of money used by the attacker in a ground attack.
        """
        return (self.attacker.soldiers * types.MilitaryUnit(types.MilitaryUnitEnum.SOLDIER).money_cost
                + self.attacker.tanks *
                types.MilitaryUnit(types.MilitaryUnitEnum.TANK).money_cost
                - self.ground_attack_loot(stat_type))

    # Air attack resource consumption

    def air_v_air_defender_aluminum_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of aluminum used by the defender in an air v air attack.
        """
        return self.air_v_air_defender_aircraft_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).aluminum_cost

    def air_v_air_attacker_aluminum_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of aluminum used by the attacker in an air v air attack.
        """
        return self.air_v_air_attacker_aircraft_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).aluminum_cost

    def air_v_air_attacker_aluminum_recovered(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of aluminum recovered by the attacker in an air v air attack.
        """
        return utils.recovered_by_military_salvage(self.air_v_air_attacker_aluminum_used(stat_type), self.air_v_air_defender_aluminum_used(stat_type), self.air_winrate)

    def air_v_all_defender_gasoline_used(self) -> float:
        """
        Calculates the amount of gasoline used by the defender in an air v air attack.
        """
        return self.defender.aircraft * types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).gasoline_used * utils.scale_with_winrate(self.air_winrate)

    air_v_soldiers_defender_gasoline_used = \
        air_v_tanks_defender_gasoline_used = \
        air_v_infra_defender_gasoline_used = \
        air_v_money_defender_gasoline_used = \
        air_v_ships_defender_gasoline_used = \
        air_v_air_defender_gasoline_used = \
        air_v_other_defender_gasoline_used = \
        air_v_all_defender_gasoline_used

    def air_v_all_attacker_gasoline_used(self) -> float:
        """
        Calculates the amount of gasoline used by the attacker in an air v air attack.
        """
        return self.attacker.aircraft * types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).gasoline_used

    air_v_soldiers_attacker_gasoline_used = \
        air_v_tanks_attacker_gasoline_used = \
        air_v_infra_attacker_gasoline_used = \
        air_v_money_attacker_gasoline_used = \
        air_v_ships_attacker_gasoline_used = \
        air_v_air_attacker_gasoline_used = \
        air_v_other_attacker_gasoline_used = \
        air_v_all_attacker_gasoline_used

    def air_v_all_defender_munitions_used(self) -> float:
        """
        Calculates the amount of munitions used by the defender in an air v air attack.
        """
        return self.defender.aircraft * types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).munitions_used * utils.scale_with_winrate(self.air_winrate)

    air_v_soldiers_defender_munitions_used = \
        air_v_tanks_defender_munitions_used = \
        air_v_infra_defender_munitions_used = \
        air_v_money_defender_munitions_used = \
        air_v_ships_defender_munitions_used = \
        air_v_air_defender_munitions_used = \
        air_v_other_defender_munitions_used = \
        air_v_all_defender_munitions_used

    def air_v_all_attacker_munitions_used(self) -> float:
        """
        Calculates the amount of munitions used by the attacker in an air v air attack.
        """
        return self.attacker.aircraft * types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).munitions_used

    air_v_soldiers_attacker_munitions_used = \
        air_v_tanks_attacker_munitions_used = \
        air_v_infra_attacker_munitions_used = \
        air_v_money_attacker_munitions_used = \
        air_v_ships_attacker_munitions_used = \
        air_v_air_attacker_munitions_used = \
        air_v_other_attacker_munitions_used = \
        air_v_all_attacker_munitions_used

    def air_v_air_defender_money_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of money used by the defender in an air v air attack.
        """
        return (self.air_v_air_defender_aircraft_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).money_cost
                + self.air_v_air_infrastructure_destroyed_value(stat_type))

    def air_v_air_attacker_money_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of money used by the attacker in an air v air attack.
        """
        return self.air_v_air_attacker_aircraft_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).money_cost

    def air_v_other_attacker_money_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of money used by the attacker in an air v other attack.
        """
        return self.air_v_other_attacker_aircraft_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).money_cost

    air_v_soldiers_attacker_money_used = \
        air_v_tanks_attacker_money_used = \
        air_v_infra_attacker_money_used = \
        air_v_ships_attacker_money_used = \
        air_v_money_attacker_money_used = \
        air_v_other_attacker_money_used

    def air_v_soldiers_defender_money_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of money used by the defender in an air v soldiers attack.
        """
        return (self.air_v_soldiers_defender_soldiers_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.SOLDIER).money_cost
                + self.air_v_soldiers_infrastructure_destroyed_value(stat_type)
                + self.air_v_soldiers_defender_aircraft_casualties * types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).money_cost)

    def air_v_tanks_defender_money_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of money used by the defender in an air v tanks attack.
        """
        return (self.air_v_tanks_defender_tanks_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.TANK).money_cost
                + self.air_v_tanks_infrastructure_destroyed_value(stat_type)
                + self.air_v_tanks_defender_aircraft_casualties * types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).money_cost)

    def air_v_infra_defender_money_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of money used by the defender in an air v infra attack.
        """
        return (self.air_v_infra_infrastructure_destroyed_value(stat_type)
                + self.air_v_infra_defender_aircraft_casualties * types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).money_cost)

    def air_v_ships_defender_money_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of money used by the defender in an air v ships attack.
        """
        return (self.air_v_ships_defender_ships_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.SHIP).money_cost
                + self.air_v_ships_infrastructure_destroyed_value(stat_type)
                + self.air_v_ships_defender_aircraft_casualties * types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).money_cost)

    def air_v_money_defender_money_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of money used by the defender in an air v money attack.
        """
        return (self.air_v_money_defender_money_destroyed(stat_type)
                + self.air_v_money_infrastructure_destroyed_value(stat_type)
                + self.air_v_money_defender_aircraft_casualties * types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).money_cost)

    def air_v_other_defender_aluminum_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of aluminum used by the defender in an air v other attack.
        """
        return self.air_v_other_defender_aircraft_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).aluminum_cost

    air_v_soldiers_defender_aluminum_used = \
        air_v_tanks_defender_aluminum_used = \
        air_v_infra_defender_aluminum_used = \
        air_v_money_defender_aluminum_used = \
        air_v_ships_defender_aluminum_used = \
        air_v_other_defender_aluminum_used

    def air_v_other_attacker_aluminum_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of aluminum used by the attacker in an air v other attack.
        """
        return self.air_v_other_attacker_aircraft_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.AIRCRAFT).aluminum_cost

    def air_v_other_attacker_aluminum_recovered(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of aluminum recovered by the attacker in an air v other attack.
        """
        return utils.recovered_by_military_salvage(self.air_v_other_attacker_aluminum_used(stat_type), self.air_v_other_defender_aluminum_used(stat_type), self.air_winrate)

    def air_v_tanks_defender_steel_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of steel used by the defender in an air v tanks attack.
        """
        return self.air_v_tanks_defender_tanks_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.TANK).steel_cost

    def air_v_tanks_attacker_steel_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of steel used by the attacker in an air v tanks attack.
        """
        return 0

    def air_v_tanks_attacker_steel_recovered(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of steel recovered by the attacker in an air v tanks attack.
        """
        return utils.recovered_by_military_salvage(self.air_v_tanks_attacker_steel_used(stat_type), self.air_v_tanks_defender_steel_used(stat_type), self.air_winrate)

    def air_v_ships_defender_steel_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of steel used by the defender in an air v ships attack.
        """
        return self.air_v_ships_defender_ships_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.SHIP).steel_cost

    def air_v_ships_attacker_steel_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of steel used by the attacker in an air v ships attack.
        """
        return 0

    def air_v_ships_attacker_steel_recovered(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of steel recovered by the attacker in an air v ships attack.
        """
        return utils.recovered_by_military_salvage(self.air_v_ships_attacker_steel_used(stat_type), self.air_v_ships_defender_steel_used(stat_type), self.air_winrate)

    # Naval attack resource consumption

    def naval_attack_defender_steel_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of steel used by the defender in a naval attack.
        """
        return self.naval_attack_defender_ships_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.SHIP).steel_cost

    def naval_attack_attacker_steel_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of steel used by the attacker in a naval attack.
        """
        return self.naval_attack_attacker_ships_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.SHIP).steel_cost

    def naval_attack_attacker_steel_recovered(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of steel recovered by the attacker in a naval attack.
        """
        return utils.recovered_by_military_salvage(self.naval_attack_attacker_steel_used(stat_type), self.naval_attack_defender_steel_used(stat_type), self.naval_winrate)

    def naval_attack_attacker_net_steel_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net amount of steel used by the attacker in a naval attack.
        """
        return self.naval_attack_attacker_steel_used(stat_type) - self.naval_attack_attacker_steel_recovered(stat_type)

    def naval_attack_defender_gasoline_used(self) -> float:
        """
        Calculates the amount of gasoline used by the defender in a naval attack.
        """
        return self.defender.ships * types.MilitaryUnit(types.MilitaryUnitEnum.SHIP).gasoline_used * utils.scale_with_winrate(self.naval_winrate)

    def naval_attack_attacker_gasoline_used(self) -> float:
        """
        Calculates the amount of gasoline used by the attacker in a naval attack.
        """
        return self.attacker.ships * types.MilitaryUnit(types.MilitaryUnitEnum.SHIP).gasoline_used

    def naval_attack_defender_munitions_used(self) -> float:
        """
        Calculates the amount of munitions used by the defender in a naval attack.
        """
        return self.defender.ships * types.MilitaryUnit(types.MilitaryUnitEnum.SHIP).munitions_used * utils.scale_with_winrate(self.naval_winrate)

    def naval_attack_attacker_munitions_used(self) -> float:
        """
        Calculates the amount of munitions used by the attacker in a naval attack.
        """
        return self.attacker.ships * types.MilitaryUnit(types.MilitaryUnitEnum.SHIP).munitions_used

    def naval_attack_defender_money_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of money used by the defender in a naval attack.
        """
        return (self.naval_attack_defender_ships_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.SHIP).money_cost
                + self.naval_attack_infrastructure_destroyed_value(stat_type))

    def naval_attack_attacker_money_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of money used by the attacker in a naval attack.
        """
        return self.naval_attack_attacker_ships_casualties(stat_type) * types.MilitaryUnit(types.MilitaryUnitEnum.SHIP).money_cost

    # Missile strike resource consumption

    def missile_strike_attacker_aluminum_used(self) -> float:
        """
        Calculates the amount of aluminum used in a missile strike.
        """
        return types.MilitaryUnit(types.MilitaryUnitEnum.MISSILE).aluminum_cost

    def missile_strike_attacker_gasoline_used(self) -> float:
        """
        Calculates the amount of gasoline used in a missile strike.
        """
        return types.MilitaryUnit(types.MilitaryUnitEnum.MISSILE).gasoline_used

    def missile_strike_attacker_munitions_used(self) -> float:
        """
        Calculates the amount of munitions used in a missile strike.
        """
        return types.MilitaryUnit(types.MilitaryUnitEnum.MISSILE).munitions_used

    def missile_strike_attacker_steel_used(self) -> float:
        """
        Calculates the amount of steel used in a missile strike.
        """
        return types.MilitaryUnit(types.MilitaryUnitEnum.MISSILE).steel_cost

    def missile_strike_attacker_money_used(self) -> float:
        """
        Calculates the amount of money used in a missile strike.
        """
        return types.MilitaryUnit(types.MilitaryUnitEnum.MISSILE).money_cost

    def missile_strike_defender_money_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of money used in a missile strike.
        """
        return self.missile_strike_infrastructure_destroyed_value(stat_type)

    # Nuclear attack resource consumption

    def nuclear_attack_attacker_aluminum_used(self) -> float:
        """
        Calculates the amount of aluminum used in a nuclear attack.
        """
        return types.MilitaryUnit(types.MilitaryUnitEnum.NUKE).aluminum_cost

    def nuclear_attack_attacker_gasoline_used(self) -> float:
        """
        Calculates the amount of gasoline used in a nuclear attack.
        """
        return types.MilitaryUnit(types.MilitaryUnitEnum.NUKE).gasoline_used

    def nuclear_attack_attacker_munitions_used(self) -> float:
        """
        Calculates the amount of munitions used in a nuclear attack.
        """
        return types.MilitaryUnit(types.MilitaryUnitEnum.NUKE).munitions_used

    def nuclear_attack_attacker_steel_used(self) -> float:
        """
        Calculates the amount of steel used in a nuclear attack.
        """
        return types.MilitaryUnit(types.MilitaryUnitEnum.NUKE).steel_cost

    def nuclear_attack_attacker_money_used(self) -> float:
        """
        Calculates the amount of money used in a nuclear attack.
        """
        return types.MilitaryUnit(types.MilitaryUnitEnum.NUKE).money_cost

    def nuclear_attack_attacker_uranium_used(self) -> float:
        """
        Calculates the amount of uranium used in a nuclear attack.
        """
        return types.MilitaryUnit(types.MilitaryUnitEnum.NUKE).uranium_cost

    def nuclear_attack_defender_money_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the amount of money used in a nuclear attack.
        """
        return self.nuclear_attack_infrastructure_destroyed_value(stat_type)

    # Ground attack net cost

    def ground_attack_attacker_net_aluminum_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net amount of aluminum used by the attacker in a ground attack.
        """
        return self.ground_attack_attacker_aluminum_used(stat_type) - self.ground_attack_attacker_aluminum_recovered(stat_type)

    def ground_attack_attacker_net_steel_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net amount of steel used by the attacker in a ground attack.
        """
        return self.ground_attack_attacker_steel_used(stat_type) - self.ground_attack_attacker_steel_recovered(stat_type)

    async def ground_attack_attacker_net_cost(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net cost of a ground attack.
        """
        prices = await utils.get_prices()
        return (self.ground_attack_attacker_gasoline_used() * prices.gasoline
                + self.ground_attack_attacker_munitions_used() * prices.munitions
                + self.ground_attack_attacker_net_steel_used(stat_type) * prices.steel
                + self.ground_attack_attacker_net_aluminum_used(stat_type) * prices.aluminum
                + self.ground_attack_attacker_money_used(stat_type))

    async def ground_attack_defender_net_cost(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net cost of a ground attack.
        """
        prices = await utils.get_prices()
        return (self.ground_attack_defender_gasoline_used() * prices.gasoline
                + self.ground_attack_defender_munitions_used() * prices.munitions
                + self.ground_attack_defender_steel_used(stat_type) * prices.steel
                + self.ground_attack_defender_aluminum_used(stat_type) * prices.aluminum
                + self.ground_attack_defender_money_used(stat_type))

    # Air attack net cost

    def air_v_air_attacker_net_aluminum_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net amount of aluminum used by the attacker in an air v air attack.
        """
        return self.air_v_air_attacker_aluminum_used(stat_type) - self.air_v_air_attacker_aluminum_recovered(stat_type)

    async def air_v_air_attacker_net_cost(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net cost of an air v air attack.
        """
        prices = await utils.get_prices()
        return (self.air_v_air_attacker_gasoline_used() * prices.gasoline
                + self.air_v_air_attacker_munitions_used() * prices.munitions
                + self.air_v_air_attacker_net_aluminum_used(stat_type) * prices.aluminum
                + self.air_v_air_attacker_money_used(stat_type))

    async def air_v_air_defender_net_cost(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net cost of an air v air attack.
        """
        prices = await utils.get_prices()
        return (self.air_v_air_defender_gasoline_used() * prices.gasoline
                + self.air_v_air_defender_munitions_used() * prices.munitions
                + self.air_v_air_defender_aluminum_used(stat_type) * prices.aluminum
                + self.air_v_air_defender_money_used(stat_type))

    def air_v_other_attacker_net_aluminum_used(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net amount of aluminum used by the attacker in an air v other attack.
        """
        return self.air_v_other_attacker_aluminum_used(stat_type) - self.air_v_other_attacker_aluminum_recovered(stat_type)

    air_v_soldiers_attacker_net_aluminum_used = \
        air_v_tanks_attacker_net_aluminum_used = \
        air_v_infra_attacker_net_aluminum_used = \
        air_v_money_attacker_net_aluminum_used = \
        air_v_ships_attacker_net_aluminum_used = \
        air_v_other_attacker_net_aluminum_used

    async def air_v_other_attacker_net_cost(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net cost of an air v (other than air) attack.
        """
        prices = await utils.get_prices()
        return (self.air_v_other_attacker_gasoline_used() * prices.gasoline
                + self.air_v_other_attacker_munitions_used() * prices.munitions
                + self.air_v_other_attacker_net_aluminum_used(stat_type) * prices.aluminum
                + self.air_v_other_attacker_money_used(stat_type))

    air_v_soldiers_attacker_net_cost = \
        air_v_tanks_attacker_net_cost = \
        air_v_infra_attacker_net_cost = \
        air_v_money_attacker_net_cost = \
        air_v_ships_attacker_net_cost = \
        air_v_other_attacker_net_cost

    async def air_v_soldiers_defender_net_cost(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net cost of an air v soldiers attack.
        """
        prices = await utils.get_prices()
        return (self.air_v_soldiers_defender_gasoline_used() * prices.gasoline
                + self.air_v_soldiers_defender_munitions_used() * prices.munitions
                + self.air_v_soldiers_defender_aluminum_used * prices.aluminum
                + self.air_v_soldiers_defender_money_used(stat_type))

    async def air_v_tanks_defender_net_cost(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net cost of an air v tanks attack.
        """
        prices = await utils.get_prices()
        return (self.air_v_tanks_defender_gasoline_used() * prices.gasoline
                + self.air_v_tanks_defender_munitions_used() * prices.munitions
                + self.air_v_tanks_defender_aluminum_used * prices.aluminum
                + self.air_v_tanks_defender_steel_used(stat_type) * prices.steel
                + self.air_v_tanks_defender_money_used(stat_type))

    async def air_v_infra_defender_net_cost(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net cost of an air v infra attack.
        """
        prices = await utils.get_prices()
        return (self.air_v_infra_defender_gasoline_used() * prices.gasoline
                + self.air_v_infra_defender_munitions_used() * prices.munitions
                + self.air_v_infra_defender_aluminum_used * prices.aluminum
                + self.air_v_infra_defender_money_used(stat_type))

    async def air_v_ships_defender_net_cost(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net cost of an air v ships attack.
        """
        prices = await utils.get_prices()
        return (self.air_v_ships_defender_gasoline_used() * prices.gasoline
                + self.air_v_ships_defender_munitions_used() * prices.munitions
                + self.air_v_ships_defender_aluminum_used * prices.aluminum
                + self.air_v_ships_defender_steel_used(stat_type) * prices.steel
                + self.air_v_ships_defender_money_used(stat_type))

    async def air_v_money_defender_net_cost(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net cost of an air v money attack.
        """
        prices = await utils.get_prices()
        return (self.air_v_money_defender_gasoline_used() * prices.gasoline
                + self.air_v_money_defender_munitions_used() * prices.munitions
                + self.air_v_money_defender_aluminum_used * prices.aluminum
                + self.air_v_money_defender_money_used(stat_type))

    # Naval attack net cost

    async def naval_attack_attacker_net_cost(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net cost of a naval attack.
        """
        prices = await utils.get_prices()
        return (self.naval_attack_attacker_gasoline_used() * prices.gasoline
                + self.naval_attack_attacker_munitions_used() * prices.munitions
                + self.naval_attack_attacker_net_steel_used(stat_type) * prices.steel
                + self.naval_attack_attacker_money_used(stat_type))

    async def naval_attack_defender_net_cost(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net cost of a naval attack.
        """
        prices = await utils.get_prices()
        return (self.naval_attack_defender_gasoline_used() * prices.gasoline
                + self.naval_attack_defender_munitions_used() * prices.munitions
                + self.naval_attack_defender_steel_used(stat_type) * prices.steel
                + self.naval_attack_defender_money_used(stat_type))

    # Missile strike net cost

    async def missile_strike_attacker_net_cost(self) -> float:
        """
        Calculates the net cost of a missile strike.
        """
        prices = await utils.get_prices()
        return (self.missile_strike_attacker_gasoline_used() * prices.gasoline
                + self.missile_strike_attacker_munitions_used() * prices.munitions
                + self.missile_strike_attacker_steel_used() * prices.steel
                + self.missile_strike_attacker_aluminum_used() * prices.aluminum
                + self.missile_strike_attacker_money_used())

    def missile_strike_defender_net_cost(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net cost of a missile strike.
        """
        return self.missile_strike_defender_money_used(stat_type)

    # Nuclear attack net cost

    async def nuclear_attack_attacker_net_cost(self) -> float:
        """
        Calculates the net cost of a nuclear attack.
        """
        prices = await utils.get_prices()
        return (self.nuclear_attack_attacker_gasoline_used() * prices.gasoline
                + self.nuclear_attack_attacker_munitions_used() * prices.munitions
                + self.nuclear_attack_attacker_steel_used() * prices.steel
                + self.nuclear_attack_attacker_aluminum_used() * prices.aluminum
                + self.nuclear_attack_attacker_money_used()
                + self.nuclear_attack_attacker_uranium_used() * prices.uranium)

    def nuclear_attack_defender_net_cost(self, stat_type: types.StatsEnum) -> float:
        """
        Calculates the net cost of a nuclear attack.
        """
        return self.nuclear_attack_defender_money_used(stat_type)
    