from __future__ import annotations

import math
from typing import Any


# --- Military research -------------------------------------------------------
# Effects per level, from the in-game Military Research page (2026-11-13; see
# .ctx/military_research_canon.md). The page shows only the step from level 0
# to 1; every level up to 20 is assumed to
# add the same step. Capacity research raises unit caps and cuts upkeep;
# Efficiency ("cost") research cuts buy costs and raises daily recruitment.
RESEARCH_MAX_LEVEL = 20
RESEARCH_FIELDS = ("ground_capacity", "ground_cost", "air_capacity", "air_cost", "naval_capacity", "naval_cost")
UNIT_BRANCH = {'soldiers': 'ground', 'tanks': 'ground', 'aircraft': 'air', 'ships': 'naval'}

CAPACITY_PER_LEVEL = {'soldiers': 3000, 'tanks': 250, 'aircraft': 15, 'ships': 5}
REBUY_PER_LEVEL = {'soldiers': 2000, 'tanks': 100, 'aircraft': 6, 'ships': 2}

# Buy cost per unit at level 0, and the cut per Efficiency level.
BASE_UNIT_COST = {
    'soldiers': {'money': 5.0},
    'tanks': {'money': 60.0, 'steel': 0.5},
    'aircraft': {'money': 4000.0, 'aluminum': 10.0},
    'ships': {'money': 50000.0, 'steel': 30.0},
}
UNIT_COST_CUT_PER_LEVEL = {
    'soldiers': {'money': 0.1},
    'tanks': {'money': 1.0, 'steel': 0.01},
    'aircraft': {'money': 50.0, 'aluminum': 0.2},
    'ships': {'money': 500.0, 'steel': 0.5},
}

# Money upkeep per unit at level 0 as (peace, war), and the cut per Capacity level.
BASE_UPKEEP = {'soldiers': (1.25, 1.88), 'tanks': (50.0, 75.0), 'aircraft': (750.0, 1000.0), 'ships': (3300.0, 5000.0)}
UPKEEP_CUT_PER_LEVEL = {'soldiers': (0.04, 0.06), 'tanks': (2.0, 3.0), 'aircraft': (30.0, 20.0), 'ships': (60.0, 100.0)}
# Soldiers eat 1 food per this many soldiers as (peace, war); Ground Capacity adds to it.
SOLDIERS_PER_FOOD = (750, 500)
SOLDIERS_PER_FOOD_PER_LEVEL = (20, 30)


def research_levels(nation: dict[str, Any]) -> dict[str, int]:
    """The nation's six research levels, clamped to 0..20 (missing or hidden = 0)."""
    research = nation.get('military_research') or {}
    levels = {}
    for field in RESEARCH_FIELDS:
        try:
            level = int(research.get(field) or 0)
        except (TypeError, ValueError):
            level = 0
        levels[field] = min(max(level, 0), RESEARCH_MAX_LEVEL)
    return levels


def unit_buy_costs(nation: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Per-unit buy cost after Efficiency research: ``{unit: {resource: amount}}``."""
    levels = research_levels(nation)
    return {
        unit: {
            resource: amount - UNIT_COST_CUT_PER_LEVEL[unit][resource] * levels[f"{UNIT_BRANCH[unit]}_cost"]
            for resource, amount in costs.items()
        }
        for unit, costs in BASE_UNIT_COST.items()
    }


def max_units(
    barracks: int, factories: int, hangars: int, drydocks: int, population: float,
    levels: dict[str, int] | None = None,
) -> dict[str, int]:
    """Unit caps from military improvements plus Capacity research, each also limited by population.

    ``levels`` comes from research_levels(); without it no research is counted.
    """
    levels = levels or {}
    improvement_caps = {
        'soldiers': (3000 * barracks, population / 6.67),
        'tanks': (250 * factories, population / 66.67),
        'aircraft': (15 * hangars, population / 1000),
        'ships': (5 * drydocks, population / 10000),
    }
    caps = {}
    for unit, (from_improvements, from_population) in improvement_caps.items():
        bonus = CAPACITY_PER_LEVEL[unit] * levels.get(f"{UNIT_BRANCH[unit]}_capacity", 0)
        caps[unit] = max(0, math.floor(min(from_improvements + bonus, from_population)))
    return caps


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
    levels = research_levels(nation)
    caps = max_units(barracks, factories, hangars, drydocks, nation['population'], levels)
    for unit, cap in caps.items():
        milt[f'max_{unit}'] = cap
    # Daily recruitment comes from the improvements (a third of the soldier cap,
    # a fifth of the others) plus Efficiency research; Capacity research does
    # not raise it. Propaganda Bureau recruits 10% more (.ctx/projects_canon.md).
    pg_mod = int(bool(nation.get("propaganda_bureau"))) * 0.1 + 1
    base_caps = max_units(barracks, factories, hangars, drydocks, nation['population'])
    for unit, share in (('soldiers', 3), ('tanks', 5), ('aircraft', 5), ('ships', 5)):
        rebuy = REBUY_PER_LEVEL[unit] * levels[f"{UNIT_BRANCH[unit]}_cost"]
        milt[f'{unit}_daily'] = (round(base_caps[unit] / share) + rebuy) * pg_mod
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