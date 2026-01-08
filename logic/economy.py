from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any, Optional

from .common import weird_division


def infra_cost(starting_infra: int, ending_infra: int, nation: Optional[dict[str, Any]] = None) -> float:
    def unit_cost(amount: int):
        return ((abs(amount - 10) ** 2.2) / 710) + 300
    difference = ending_infra - starting_infra
    cost = 0
    if difference < 0:
        return 150 * difference
    if difference > 100 and difference % 100 != 0:
        delta = difference % 100
        cost += (round(unit_cost(starting_infra), 2) * delta)
        starting_infra += delta
        difference -= delta
    for _ in range(math.floor(difference // 100)):
        cost += round(unit_cost(starting_infra), 2) * 100
        starting_infra += 100
        difference -= 100
    if difference:
        cost += (round(unit_cost(starting_infra), 2) * difference)
    multiplier = 1
    if nation:
        if nation['center_for_civil_engineering']:
            multiplier -= 0.05
        if nation['advanced_engineering_corps']:
            multiplier -= 0.05
        if nation['domestic_policy'] == "URBANIZATION":
            if nation['government_support_agency']:
                multiplier -= 0.075
            else:
                multiplier -= 0.05
    return cost * multiplier


def land_cost(starting_land: int, ending_land: int, nation: Optional[dict[str, Any]] = None) -> float:
    def unit_cost(amount: int):
        return (.002*(amount-20)*(amount-20))+50
    difference = ending_land - starting_land
    cost = 0
    if difference < 0:
        return 50 * difference
    if difference > 500 and difference % 500 != 0:
        delta = difference % 500
        cost += round(unit_cost(starting_land), 2) * delta
        starting_land += delta
        difference -= delta
    for _ in range(math.floor(difference // 500)):
        cost += round(unit_cost(starting_land), 2) * 500
        starting_land += 500
        difference -= 500
    if difference:
        cost += (round(unit_cost(starting_land), 2) * difference)
    multiplier = 1
    if nation:
        if nation['arable_land_agency']:
            multiplier -= 0.05
        if nation['advanced_engineering_corps']:
            multiplier -= 0.05
        if nation['domestic_policy'] == "RAPID_EXPANSION":
            if nation['government_support_agency']:
                multiplier -= 0.075
            else:
                multiplier -= 0.05
    return cost * multiplier


def city_cost(city: int, nation: Optional[dict[str, Any]] = None) -> float:
    if city <= 1:
        raise ValueError("The provided value cannot be less than or equal to 1.")
    city -= 1
    modifier = 0
    multiplier = 1
    if nation:
        if nation['urban_planning']:
            modifier -= 50000000
        if nation['advanced_urban_planning']:
            modifier -= 100000000
        if nation['metropolitan_planning']:
            modifier -= 100000000
        if nation['domestic_policy'] == "MANIFEST_DESTINY":
            if nation['government_support_agency']:
                multiplier -= 0.075
            else:
                multiplier -= 0.05        
    return (50000 * math.pow((city - 1), 3) + 150000 * city + 75000 + modifier) * multiplier


def expansion_cost(current: int, end: int, infra: int, land: int, nation: Optional[dict[str, Any]] = None) -> float:
    diff = end - current
    if diff < 1:
        raise ValueError("Invalid start and end input.")
    cost = 0
    while current < end:
        current += 1
        cost += city_cost(current, nation)
        cost += infra_cost(10, infra, nation)
        cost += land_cost(250, land, nation)
    return cost
