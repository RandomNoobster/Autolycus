from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
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


_CENT = Decimal("0.01")


def _round2(value: float) -> float:
    """PHP's round($value, 2): halves go away from zero on the number as written,
    so 2.675 -> 2.68 where Python's round() gives 2.67."""
    return float(Decimal(repr(value)).quantize(_CENT, rounding=ROUND_HALF_UP))


def _infra_unit_price(amount: float) -> float:
    return _round2(abs(amount - 10) ** 2.2 / 710 + 300)


def infra_cost(starting_infra: float, ending_infra: float, nation: Optional[dict[str, Any]] = None) -> float:
    """Cost to go from ``starting_infra`` to ``ending_infra``; negative is the $150/point sale refund.

    Follows the game's calcInfraValue (PHP, on the Fandom "City Formulas" page).
    Both ends are rounded to 2 decimals. A buy is priced in chunks, each at the
    unit price where the chunk starts. While more than 100 is left, the next
    chunk is ``difference % 100``, or 100 when that is 0, and the rest is the
    last chunk. PHP's ``%`` truncates to whole numbers first, so for 150.5 the
    first chunk is 50 and the fraction ends up in the last chunk.
    """
    start = _round2(starting_infra)
    end = _round2(ending_infra)
    difference = end - start
    if difference < 0:
        return 150 * difference
    cost = 0.0
    while difference > 100:
        chunk = int(difference) % 100 or 100
        cost += _infra_unit_price(start) * chunk
        start = _round2(start + chunk)
        difference = end - start
    if difference > 0:
        cost += _infra_unit_price(start) * difference
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
