from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from logic.common import compute_beige_loot, parse_war_date


def is_in_vacation_mode(nation: dict[str, Any]) -> bool:
    """Return True when Vacation Mode is active."""
    vmode = nation.get("vmode")
    if isinstance(vmode, bool):
        if vmode:
            return True
    elif isinstance(vmode, (int, float)):
        if vmode > 0:
            return True

    vmt = nation.get("vacation_mode_turns")
    try:
        vmt_val = int(vmt) if vmt is not None else 0
    except (TypeError, ValueError):
        vmt_val = 0
    return vmt_val > 0


def calculate_days_inactive(last_active: str, now: Optional[datetime] = None) -> int:
    """Calculate days since last activity from cached nation timestamp."""
    if not last_active or last_active == "-0001-11-30 00:00:00":
        return 0

    try:
        if "T" in last_active:
            last_active_dt = datetime.fromisoformat(last_active.replace("Z", "+00:00"))
        else:
            last_active_dt = datetime.strptime(last_active, "%Y-%m-%d %H:%M:%S")
            last_active_dt = last_active_dt.replace(tzinfo=timezone.utc)

        if now is None:
            now = datetime.now(timezone.utc)
        return (now - last_active_dt).days
    except (ValueError, TypeError):
        return 0


def derive_def_slots_and_time_since_war(nation: dict[str, Any], now_utc: datetime) -> Tuple[int, int | str]:
    """Compute active defensive slots and recency of most recent war."""
    wars = nation.get("wars") or []
    def_slots = 0
    time_since_war: int | str = "14+"
    if not wars:
        return def_slots, time_since_war

    nation_id_str = str(nation.get("id"))
    for war in wars:
        if war.get("turnsleft", 0) > 0 and str(war.get("defid")) == nation_id_str:
            def_slots += 1

    try:
        most_recent = max(wars, key=lambda w: parse_war_date(w.get("date")))
        war_dt = parse_war_date(most_recent.get("date"))
        if war_dt.year > 1970:
            days = (now_utc - war_dt).days
            time_since_war = 0 if def_slots > 0 else days
    except Exception:
        time_since_war = "14+"

    return def_slots, time_since_war


def compute_beige_loot_or_zero(
    nation: dict[str, Any],
    prices: Optional[dict[str, float]],
) -> tuple[int, str]:
    """Return standardized loot value/text for raids surfaces."""
    loot_value = compute_beige_loot(nation, prices)
    if loot_value is None or loot_value <= 0:
        return 0, "NaN"
    return int(loot_value), f"{int(round(loot_value)):,}"
