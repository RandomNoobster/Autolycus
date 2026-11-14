from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from logic.common import _war_field, compute_beige_loot, parse_war_date


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
        if last_active_dt.tzinfo is None:
            # P&W times without an offset are UTC (subscription rows store them as
            # offset-less ISO strings).
            last_active_dt = last_active_dt.replace(tzinfo=timezone.utc)

        if now is None:
            now = datetime.now(timezone.utc)
        # A clock a few seconds behind P&W's must not show -1 days.
        return max(0, (now - last_active_dt).days)
    except (ValueError, TypeError):
        return 0


def stored_time_since_war(value: Any) -> int | str:
    """The scanner's time_since_war column as the API returns it: days or "14+".

    The column's type comes from the first row ever stored, so days may read back
    as text ("3"); missing means no war in the last 14 days.
    """
    if value is None:
        return "14+"
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return value


def war_turns_left(war: dict[str, Any]) -> float:
    """Turns left in a war (deprecated or current field name); 0 when unknown."""
    raw = _war_field(war, "turnsleft", "turns_left")
    try:
        return float(raw) if raw is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def derive_def_slots_and_time_since_war(nation: dict[str, Any], now_utc: datetime) -> Tuple[int, int | str]:
    """Compute active defensive slots and recency of most recent war."""
    wars = [war for war in (nation.get("wars") or []) if isinstance(war, dict)]
    def_slots = 0
    time_since_war: int | str = "14+"
    if not wars:
        return def_slots, time_since_war

    nation_id_str = str(nation.get("id"))
    for war in wars:
        def_id = _war_field(war, "defid", "def_id")
        if war_turns_left(war) > 0 and str(def_id) == nation_id_str:
            def_slots += 1

    try:
        war_dt = max(parse_war_date(w.get("date")) for w in wars)
        if war_dt.year > 1970:
            days = max(0, (now_utc - war_dt).days)
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
