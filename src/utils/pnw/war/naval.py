from __future__ import annotations

from . import defender_fortified_modifier, infrastructure_destroyed_modifier
from ....types import WarTypeEnum, WarTypeDetails, MilitaryUnitEnum, MilitaryUnit, WarPolicyDetails, AttackerEnum


def naval_attack_attacker_ships_casualties(defender_casualties_ships_value: int, defender_fortified: bool = False, random_factor: float = 1.0) -> float:
    """
    Calculates the amount of ships the attacker will lose in a naval attack.
    """
    return (defender_casualties_ships_value * 0.01375) * random_factor * defender_fortified_modifier(defender_fortified)    


def naval_attack_defender_ships_casualties(attacker_casualties_ships_value: int, random_factor: float = 1.0) -> float:
    """
    Calculates the amount of ships the defender will lose in a naval attack.
    """
    return (attacker_casualties_ships_value * 0.01375) * random_factor


async def naval_attack_infrastructure_destroyed(attacker_ships: int, defender_ships: int, city_infrastructure: int, naval_winrate: float, attacker: AttackerEnum, attacker_war_policy_details: WarPolicyDetails, defender_war_policy_details: WarPolicyDetails, random_factor: float = 1.0, war_type_details: WarTypeDetails = WarTypeDetails(WarTypeEnum.ORDINARY)) -> float:
    return (
        max(
            min((attacker_ships - defender_ships * 0.5) * 2.625
                * random_factor
                * naval_winrate ** 3
                , city_infrastructure * 0.5 + 25)
            , 0)) * infrastructure_destroyed_modifier(war_type_details, attacker, attacker_war_policy_details, defender_war_policy_details)