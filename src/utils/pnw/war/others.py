from __future__ import annotations

from . import infrastructure_destroyed_modifier
from ....types import StatsEnum, WarTypeEnum, WarTypeDetails, AttackerEnum


def missile_strike_infrastructure_destroyed(stat_type: StatsEnum, city_infrastructure: int, city_land: int, war_type_details: WarTypeDetails = WarTypeDetails(WarTypeEnum.ORDINARY), attacker: AttackerEnum = AttackerEnum.ATTACKER) -> float:

    avg = (300 + max(350, city_infrastructure * 100 / city_land * 3)) / 2
    diff = max(350, city_infrastructure * 100 / city_land * 3) - avg

    if stat_type == StatsEnum.AVERAGE:
        x = avg
    elif stat_type == StatsEnum.DIFFERENCE:
        x = diff
    else:
        raise ValueError("Invalid stat type")
    
    return (max(min(x, city_infrastructure * 0.8 + 150), 0)) * infrastructure_destroyed_modifier(war_type_details, attacker, None, None)


async def nuclear_attack_infrastructure_destroyed(stat_type: StatsEnum, city_infrastructure: int, city_land: int, war_type_details: WarTypeDetails = WarTypeDetails(WarTypeEnum.ORDINARY), attacker: AttackerEnum = AttackerEnum.ATTACKER) -> float:

    avg = (1700 + max(2000, city_infrastructure * 100 / city_land * 13.5)) / 2
    diff = max(2000, city_infrastructure * 100 / city_land * 13.5) - avg

    if stat_type == StatsEnum.AVERAGE:
        x = avg
    elif stat_type == StatsEnum.DIFFERENCE:
        x = diff
    else:
        raise ValueError("Invalid stat type")
    
    return (max(min(x, city_infrastructure * 0.8 + 150), 0)) * infrastructure_destroyed_modifier(war_type_details, attacker, None, None)