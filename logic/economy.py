from __future__ import annotations

import math
from typing import Any, Optional


def infra_rebuild_cost(
    current_infra: float,
    infra_lost: float,
    nation: Optional[dict[str, Any]] = None,
) -> float:
    """Cost for a nation to buy back destroyed infrastructure (not sell proceeds)."""
    if infra_lost <= 0:
        return 0.0
    current = float(current_infra)
    # Both ends stay fractional: rounding only one of them could make a small
    # loss look like a sale (a negative cost).
    return infra_cost(max(0.0, current - float(infra_lost)), current, nation)


def _domestic_policy(nation: dict[str, Any]) -> str:
    """Domestic policy as an enum-style name: 'Urbanization' and 'URBANIZATION' both match."""
    raw = nation.get('domestic_policy') or nation.get('dompolicy') or ''
    return str(raw).strip().upper().replace(' ', '_')


def infra_cost(starting_infra: float, ending_infra: float, nation: Optional[dict[str, Any]] = None) -> float:
    def unit_cost(amount: float):
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
        if nation.get('center_for_civil_engineering'):
            multiplier -= 0.05
        if nation.get('advanced_engineering_corps'):
            multiplier -= 0.05
        if _domestic_policy(nation) == "URBANIZATION":
            # 5%, raised 50% by Government Support Agency and a further 25% by
            # Bureau of Domestic Affairs (.ctx/projects_canon.md).
            scale = 1.0
            if nation.get('government_support_agency'):
                scale += 0.5
            if nation.get('bureau_of_domestic_affairs'):
                scale += 0.25
            multiplier -= 0.05 * scale
    return cost * multiplier
