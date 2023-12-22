from __future__ import annotations
from typing import Tuple
import math

from ...types import DomesticPolicyEnum

__all__ = ("score_range", "infra_cost", "land_cost", "city_cost", "expansion_cost")


def score_range(score: float) -> Tuple[float, float]:
    """
    Determines the offensive score range for a given score.
    :param score: Score to determine offensive war ranges for.
    :return: Minimum attacking range and maximum attacking range, in that order.
    """
    min_score = score * 0.75
    max_score = score * 1.75
    return min_score, max_score


def infra_cost(starting_infra: int, ending_infra: int, nation: dict = None) -> float:
    """
    Calculate the cost to purchase or sell infrastructure.
    :param starting_infra: A starting infrastructure amount.
    :param ending_infra: The desired infrastructure amount.
    :param multiplier: A multiplier to adjust the ending result by.
    :param nation: Must include `center_for_civil_engineering`, `advanced_engineering_corps`, `government_support_agency` and `domestic_policy`.
    :return: The cost to purchase or sell infrastructure.
    """
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


def land_cost(starting_land: int, ending_land: int, nation: dict = None) -> float:
    """
    Calculate the cost to purchase or sell land.
    :param starting_land: A starting land amount.
    :param ending_land: The desired land amount.
    :param multiplier: A multiplier to adjust the ending result by.
    :param nation: Must include `arable_land_agency`, `advanced_engineering_corps`, `government_support_agency` and `domestic_policy`.
    :return: The cost to purchase or sell land.
    """
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


def city_cost(city: int, nation: dict = None) -> float:
    """
    Calculate the cost to purchase a specified city.
    :param city: The city to be purchased.
    :param nation: Must include `urban_planning`, `advanced_urban_planning`, `government_support_agency` and `domestic_policy`.
    :return: The cost to purchase the specified city.
    """
    if city <= 1:
        raise ValueError(
            "The provided value cannot be less than or equal to 1.")
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


def expansion_cost(current: int, end: int, infra: int, land: int, nation: dict = None) -> float:
    """
    Calculate the cost to purchase a specified city.
    :param current: The current city
    :param end: The final city to be purchased.
    :param infra: The amount of infra in city to be purchased.
    :param land: The amount of land in city to be purchased.
    :return: The cost to purchase the specified city.
    """
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

