from __future__ import annotations
from . import defender_fortified_modifier, scale_with_winrate, infrastructure_destroyed_modifier
import src.types as types


def air_v_air_attacker_aircraft_casualties(defender_casualties_aircraft_value: float, attacker_aircraft: float, random_factor: float, defender_fortified: bool) -> float:
    """
    Calculates the amount of aircraft the attacker will lose in an air v air attack.
    """
    return min((defender_casualties_aircraft_value * 0.01) * random_factor * defender_fortified_modifier(defender_fortified)
               , attacker_aircraft)


def air_v_air_defender_aircraft_casualties(attacker_casualties_aircraft_value: float, defender_aircraft: float, random_factor: float) -> float:
    """
    Calculates the amount of aircraft the defender will lose in an air v air attack.
    """
    return min((attacker_casualties_aircraft_value * 0.018337) * random_factor
               , defender_aircraft)


def air_v_other_attacker_aircraft_casualties(defender_casualties_aircraft_value: float, attacker_aircraft: float, random_factor: float, defender_fortified: bool) -> float:
    """
    Calculates the amount of aircraft the attacker will lose in an air v (other than air) attacks.
    """
    return min((defender_casualties_aircraft_value * 0.015385) * random_factor * defender_fortified_modifier(defender_fortified)
               , attacker_aircraft)


def air_v_other_defender_aircraft_casualties(attacker_casualties_aircraft_value: float, defender_aircraft: float, random_factor: float) -> float:
    """
    Calculates the amount of aircraft the defender will lose in an air v (other than air) attack.
    """
    return min((attacker_casualties_aircraft_value * 0.009091) * random_factor
               , defender_aircraft)


def air_v_ships_defender_ships_casualties(defender_ships: int, attacker_aircraft: int, defender_aircraft: int, random_factor: float, air_winrate: float) -> float:
    """
    Calculates the amount of ships the defender will lose in an air v ships attack.
    """
    # TODO is it correct to use the random_modifier here?
    return max(min(defender_ships, defender_ships * 0.75 + 4, (attacker_aircraft - defender_aircraft * 0.5) * 0.0285 * random_factor), 0) * scale_with_winrate(air_winrate)


def air_v_soldiers_defender_soldiers_casualties(defender_soldiers: int, attacker_aircraft: int, defender_aircraft: int, random_factor: float, air_winrate: float) -> float:
    """
    Calculates the amount of soldiers the defender will lose in an air v soldiers attack.
    """
    # TODO is it correct to use the random_modifier here?
    return max(min(defender_soldiers, defender_soldiers * 0.75 + 1000, (attacker_aircraft - defender_aircraft * 0.5) * 35 * random_factor), 0) * scale_with_winrate(air_winrate)


def air_v_tanks_defender_tanks_casualties(defender_tanks: int, attacker_aircraft: int, defender_aircraft: int, random_factor: float, air_winrate: float) -> float:
    """
    Calculates the amount of tanks the defender will lose in an air v tanks attack.
    """
    # TODO is it correct to use the random_modifier here?
    return max(min(defender_tanks, defender_tanks * 0.75 + 10, (attacker_aircraft - defender_aircraft * 0.5) * 1.25 * random_factor), 0) * scale_with_winrate(air_winrate)


async def air_v_infra_infrastructure_destroyed(attacker_aircraft: int, defender_aircraft: int, city_infrastructure: int, random_factor: float, air_winrate: float, attacker: types.AttackerEnum, attacker_war_policy_details: types.WarPolicyDetails, defender_war_policy_details: types.WarPolicyDetails, war_type_details: types.WarTypeDetails) -> float:
    """
    Calculates the amount of infrastructure the defender will lose in an air v infrastructure attack.
    """
    return (
        max(
            min((attacker_aircraft - defender_aircraft * 0.5) * 0.35353535
                * random_factor
                * air_winrate ** 3
                , city_infrastructure * 0.5 + 100)
            , 0)) * infrastructure_destroyed_modifier(war_type_details, attacker, attacker_war_policy_details, defender_war_policy_details)


async def air_v_other_infrastructure_destroyed(attacker_aircraft: int, defender_aircraft: int, city_infrastructure: int, random_factor: float, air_winrate: float, attacker: types.AttackerEnum, attacker_war_policy_details: types.WarPolicyDetails, defender_war_policy_details: types.WarPolicyDetails, war_type_details: types.WarTypeDetails) -> float:
    """
    Calculates the amount of infrastructure the defender will lose in an air v (other than infra) attack.
    """
    return air_v_infra_infrastructure_destroyed(attacker_aircraft, defender_aircraft, city_infrastructure, random_factor, air_winrate, attacker, attacker_war_policy_details, defender_war_policy_details, war_type_details) / 3