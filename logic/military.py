from __future__ import annotations

import math
from typing import Any


def max_units(barracks: int, factories: int, hangars: int, drydocks: int, population: float) -> dict[str, int]:
    """Unit caps from military improvements, each also limited by population."""
    return {
        'soldiers': max(0, math.floor(min(3000 * barracks, population / 6.67))),
        'tanks': max(0, math.floor(min(250 * factories, population / 66.67))),
        'aircraft': max(0, math.floor(min(15 * hangars, population / 1000))),
        'ships': max(0, math.floor(min(5 * drydocks, population / 10000))),
    }


def militarization_checker(nation: dict[str, Any]) -> dict[str, float]:
    """Average military improvements per city, unit caps and daily recruitment."""
    milt: dict[str, float] = {}
    cities = len(nation['cities'])
    barracks = sum(city['barracks'] for city in nation['cities'])
    factories = sum(city['factory'] for city in nation['cities'])
    hangars = sum(city['airforcebase'] for city in nation['cities'])
    drydocks = sum(city['drydock'] for city in nation['cities'])
    milt['barracks_mmr'] = round(barracks / cities, 1)
    milt['factory_mmr'] = round(factories / cities, 1)
    milt['hangar_mmr'] = round(hangars / cities, 1)
    milt['drydock_mmr'] = round(drydocks / cities, 1)
    caps = max_units(barracks, factories, hangars, drydocks, nation['population'])
    for unit, cap in caps.items():
        milt[f'max_{unit}'] = cap
    # Propaganda Bureau recruits 10% more per day (.ctx/projects_canon.md).
    pg_mod = int(bool(nation.get("propaganda_bureau"))) * 0.1 + 1
    milt['soldiers_daily'] = round(milt['max_soldiers']/3) * pg_mod
    milt['tanks_daily'] = round(milt['max_tanks']/5) * pg_mod
    milt['aircraft_daily'] = round(milt['max_aircraft']/5) * pg_mod
    milt['ships_daily'] = round(milt['max_ships']/5) * pg_mod
    return milt


def max_offensive_wars(nation: dict[str, Any]) -> int:
    """Offensive war slots: 5, plus one each for Pirate Economy and Advanced Pirate Economy."""
    return 5 + int(bool(nation.get("pirate_economy"))) + int(bool(nation.get("advanced_pirate_economy")))


def score_range(score: float) -> tuple[float, float]:
    """Exact PnW offensive war range (display / docs)."""
    min_score = score * 0.75
    max_score = score * 2.5
    return min_score, max_score


def war_range_query_bounds(score: float) -> tuple[int, int]:
    """
    Conservative score bounds for raid/nuke target queries.

    Prefer hiding a barely-in-range nation over showing one that fails declare.
    Pair with inclusive filters (score >= min AND score <= max).
    """
    lo = max(15, math.ceil(score * 0.75))
    hi = math.floor(score * 2.5)
    return lo, hi

def calculate_win_chance_raw(attacker_value: float, defender_value: float) -> float:
    """
    Calculate the exact win probability based on the Uniform Distribution model.
    
    Game Logic (Per PWPedia):
        Both sides roll a random value between 40% and 100% of their score.
        Win Rate = Probability(Attacker_Roll > Defender_Roll).
        
    Args:
        attacker_value: The military score/strength of the attacker.
        defender_value: The military score/strength of the defender.
        
    Returns:
        float: Probability of winning (0.0 to 1.0).
        
    Raises:
        ValueError: If values are negative.
    """
    # Game mechanics constants (per PWPedia)
    MIN_EFFICIENCY = 0.4  # Both sides roll between 40% and 100% of their score
    MAX_EFFICIENCY = 1.0
    
    # Handle edge cases. An attacker with nothing to attack with cannot win, even
    # against an empty defender (the game does not allow the attack at all).
    if attacker_value <= 0:
        return 0.0
    if defender_value <= 0:
        return 1.0

    # Define the ranges for both sides (40% to 100% efficiency)
    min_a = MIN_EFFICIENCY * attacker_value
    max_a = MAX_EFFICIENCY * attacker_value
    min_d = MIN_EFFICIENCY * defender_value
    max_d = MAX_EFFICIENCY * defender_value

    # Case 1: Guaranteed Win
    # Even if Attacker rolls worst (40%) and Defender rolls best (100%), Attacker wins.
    # Occurs when attacker_value > 2.5 * defender_value
    if min_a >= max_d:
        return 1.0

    # Case 2: Guaranteed Loss
    # Even if Attacker rolls best (100%) and Defender rolls worst (40%), Attacker loses.
    # Occurs when attacker_value < 0.4 * defender_value
    if max_a <= min_d:
        return 0.0

    # Case 3: Overlap (Calculate Geometric Probability)
    # We calculate the area of the rectangle defined by the two ranges
    # and find the proportion of that area where a > d.
    
    width_a = max_a - min_a
    width_d = max_d - min_d
    total_area = width_a * width_d
    
    # Intersection logic:
    # We integrate the area where x > y inside the rectangle [min_a, max_a] x [min_d, max_d]
    
    # Determine the effective range of overlap on the x-axis (Attacker's side)
    overlap_area = 0.0
    
    # Segment where x <= max_d (Triangle/Trapezoid part)
    low_bound = max(min_a, min_d)
    high_bound = min(max_a, max_d)
    
    if high_bound > low_bound:
        # Integral of (x - min_d) dx = [0.5*x^2 - min_d*x]
        val_high = 0.5 * high_bound**2 - min_d * high_bound
        val_low = 0.5 * low_bound**2 - min_d * low_bound
        overlap_area += (val_high - val_low)
    
    # Segment where x > max_d (Attacker rolls higher than Defender's max possible)
    # In this range, Attacker wins 100% of the specific sub-cases
    low_bound_win = max(min_a, max_d)
    high_bound_win = max_a
    
    if high_bound_win > low_bound_win:
        # Integral of (width_d) dx
        overlap_area += width_d * (high_bound_win - low_bound_win)
        
    return overlap_area / total_area