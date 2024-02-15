from __future__ import annotations
from . import defender_fortified_modifier, infrastructure_destroyed_modifier
import src.types as types


def ground_attack_attacker_soldiers_casualties(defender_casualties_soldiers_value: int, defender_casualties_tanks_value: int, attacker_soldiers: int, defender_fortified: bool = False, random_factor: float = 1.0) -> float:
    """
    Calculates the attacker's soldier casualties in a ground attack.
    :param random_factor: The random factor. During simulation this is a float between 0.4 and 1.
    """
    return min(
        (defender_casualties_soldiers_value * 0.0084 + defender_casualties_tanks_value * 0.0092) * random_factor * defender_fortified_modifier(defender_fortified)
        , attacker_soldiers)


def ground_attack_attacker_tanks_casualties(defender_casualties_soldiers_value: int, defender_casualties_tanks_value: int, attacker_tanks: int, ground_winrate: float, defender_fortified: bool = False, random_factor: float = 1.0) -> float:
    """
    Calculates the amount of tanks the attacker will lose in a ground attack.
    """
    return min((
        defender_casualties_soldiers_value * (0.0004060606 * ground_winrate + 0.00043225806 * (1 - ground_winrate))
            + defender_casualties_tanks_value * (0.00066666666 * ground_winrate + 0.00070967741 * (1 - ground_winrate))
            ) * random_factor * defender_fortified_modifier(defender_fortified)
        , attacker_tanks)


def ground_attack_defender_soldiers_casualties(attacker_casualties_soldiers_value: int, attacker_casualties_tanks_value: int, defending_soldiers: int, random_factor: float = 1.0) -> float:
    """
    Calculates the attacker's soldier casualties in a ground attack.
    :param random_factor: The random factor. During simulation this is a float between 0.4 and 1.
    """
    return min(
        (attacker_casualties_soldiers_value * 0.0084 + attacker_casualties_tanks_value * 0.0092) * random_factor
        , defending_soldiers)


def ground_attack_defender_tanks_casualties(attacker_casualties_soldiers_value: int, attacker_casualties_tanks_value: int, defender_tanks: int, ground_winrate: float, random_factor: float = 1.0) -> float:
    """
    Calculates the amount of tanks the defender will lose in a ground attack.
    """
    return min((
        attacker_casualties_soldiers_value * (0.0004060606 * (1 - ground_winrate) + 0.00043225806 * ground_winrate)
            + attacker_casualties_tanks_value * (0.00066666666 * (1 - ground_winrate) + 0.00070967741 * ground_winrate)
            ) * random_factor
        , defender_tanks)


def ground_attack_defender_aircraft_casualties(attacking_tanks: int, defending_aircraft: int, ground_winrate: float) -> float:
    """
    Calculates the amount of aircraft the defender will lose in a ground attack.
    """
    # TODO what are the casualty ratios?
    return min(attacking_tanks * 0.005 * ground_winrate ** 3, defending_aircraft)


def ground_attack_loot(attacker_soldiers: int, attacker_tanks: int, ground_winrate: float, attacker_war_policy_details: types.WarPolicyDetails, defender_war_policy_details: types.WarPolicyDetails, attacker: types.AttackerEnum, random_factor: float = 1.0, war_type_details: types.WarTypeDetails = types.WarTypeDetails(types.WarTypeEnum.ORDINARY), pirate_economy: bool = False, advanced_pirate_economy: bool = False) -> float:
    """
    Calculates the amount of loot the attacker will get in a ground attack.
    """
    if attacker == types.AttackerEnum.ATTACKER:
        war_modifier = war_type_details.attacker_loot
    elif attacker == types.AttackerEnum.DEFENDER:
        war_modifier = war_type_details.defender_loot
    else:
        raise ValueError("Invalid attacker")
    
    return (
        (attacker_soldiers * types.MilitaryUnit(types.MilitaryUnitEnum.SOLDIER).loot_stolen
            + attacker_tanks * types.MilitaryUnit(types.MilitaryUnitEnum.TANK).loot_stolen)
        * ((ground_winrate ** 3) * 3
            + (ground_winrate ** 2) * (1 - ground_winrate) * 2
            + ground_winrate * (1 - ground_winrate) ** 2)   
        * random_factor
        * war_modifier
        * attacker_war_policy_details.loot_stolen
        * defender_war_policy_details.loot_lost
        * 1.05 if advanced_pirate_economy else 1
        * 1.05 if pirate_economy else 1
        # TODO * blitzkrieg
    )

def ground_attack_infrastructure_destroyed(attacker_soldiers: int, attacker_tanks: int, defender_soldiers: int, defender_tanks: int, ground_winrate: float, city_infrastructure: int, attacker_war_policy_details: types.WarPolicyDetails, defender_war_policy_details: types.WarPolicyDetails, attacker: types.AttackerEnum, random_factor: float = 1.0, war_type_details: types.WarTypeDetails = types.WarTypeDetails(types.WarTypeEnum.ORDINARY)) -> float:
    """
    Calculates the amount of infrastructure the defender will lose in a ground attack.
    """
    return (
        max(
            min(((attacker_soldiers - defender_soldiers * 0.5) * 0.000606061
                    + (attacker_tanks - (defender_tanks * 0.5)) * 0.01)
                * random_factor
                * ground_winrate ** 3 
                , city_infrastructure * 0.2 + 25)
            , 0)) * infrastructure_destroyed_modifier(war_type_details, attacker, attacker_war_policy_details, defender_war_policy_details)