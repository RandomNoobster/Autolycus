from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

RSS = ['aluminum', 'bauxite', 'coal', 'food', 'gasoline', 'iron', 'lead', 'money', 'munitions', 'oil', 'steel', 'uranium', 'credits']
EMBED_COLOR = 0xff5100  # Orange color used throughout Autolycus embeds


def cut_string(string: str, length: int = 2000) -> str:
    if len(string) > length:
        return string[:length-6] + "...```"
    else:
        return string


def comma_and_list(listy: list[str]) -> str:
    if not listy:
        return ""
    if len(listy) == 1:
        return listy[0]
    return ", ".join(listy[:-1]) + " and " + listy[-1]


def get_datetime_of_turns(turns: int) -> datetime:
    now = datetime.utcnow()
    if turns == 0:
        return now
    if turns < 0:
        return (now + timedelta(hours=turns * 2 + 1 * (not bool(now.hour % 2)) + 1)).replace(minute=0, second=0, microsecond=0)
    return (now + timedelta(hours=turns * 2 - 1 * bool(now.hour % 2))).replace(minute=0, second=0, microsecond=0)


def beige_loot_value(loot_string: str, prices: dict[str, float]) -> int:
    loot_string = loot_string[loot_string.index('$'):loot_string.index('Food.')]
    loot_string = re.sub(r"[^0-9-]+", "", loot_string.replace(", ", "-"))
    rss = ['money', 'coal', 'oil', 'uranium', 'iron', 'bauxite', 'lead', 'gasoline', 'munitions', 'steel', 'aluminum', 'food']
    n = 0
    loot: dict[str, int] = {}
    for sub in loot_string.split("-"):
        loot[rss[n]] = int(sub)
        n += 1
    nation_loot = 0
    for rs in rss:
        amount = loot[rs]
        price = int(prices[rs])
        nation_loot += amount * price
    return nation_loot


logger = logging.getLogger(__name__)


def parse_war_date(date_str: Optional[str]) -> datetime:
    """Best-effort parser for war dates to enable ordering.

    Handles both ISO-8601 and ``YYYY-MM-DD HH:MM:SS`` formats that appear in
    the cached nation data.  Returns the epoch when the date cannot be parsed.

    Args:
        date_str: Raw date string from the war record.

    Returns:
        Timezone-aware datetime (UTC).
    """
    if not date_str:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        if "T" in date_str:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def compute_beige_loot(
    nation: dict[str, Any],
    prices: Optional[dict[str, float]],
) -> Optional[int]:
    """Compute estimated beige loot value from a nation's finished wars.

    Scans cached war logs for the most recent war where the nation was the
    defender and lost, then reverse-engineers the *base* loot value by
    undoing attacker policy / war-type multipliers.  This gives a rough
    estimate of how much loot the nation is holding.

    The function performs a single linear pass (no sorting) over the wars
    list to find the most recent qualifying war.

    Args:
        nation: Nation dict (must include ``id`` and ``wars`` fields).
        prices: Current market prices keyed by resource name.  When *None*
            the computation is skipped.

    Returns:
        Estimated loot value in dollars, or *None* when computation cannot
        be performed (no prices, no wars, no qualifying loot records).
    """
    if not prices:
        return None

    wars = nation.get('wars') or []
    nation_id = str(nation.get('id', ''))
    if not nation_id or not wars:
        return None

    best_loot: Optional[int] = None
    best_date: Optional[datetime] = None

    for war in wars:
        try:
            turns_left = war.get('turnsleft', 1)
            try:
                turns_left_val = float(turns_left)
            except (TypeError, ValueError):
                turns_left_val = 1
            if turns_left_val > 0:
                continue  # still active

            if str(war.get('defid')) != nation_id:
                continue  # only care about wars where this nation was defender

            war_dt = parse_war_date(war.get('date'))
            attacks = war.get('attacks') or []

            for attack in reversed(attacks):  # reverse to favour latest attack
                text = attack.get('loot_info')
                if not text or "won the war and looted" not in text:
                    continue
                victor = str(attack.get('victor', ''))
                if victor == nation_id:
                    continue  # they won, so no beige loot

                try:
                    loot_value = float(beige_loot_value(text, prices))
                except Exception:
                    continue

                # Undo attacker policy multipliers to estimate base loot
                attacker_info = war.get('attacker') or {}
                policy = (attacker_info.get('war_policy') or '').upper()
                if policy == "ATTRITION":
                    loot_value = loot_value / 0.8
                elif policy == "PIRATE":
                    loot_value = loot_value / 1.4
                if attacker_info.get('advanced_pirate_economy'):
                    loot_value = loot_value / 1.1

                # Undo war-type multipliers
                war_type = (war.get('war_type') or '').upper()
                if war_type == "ATTRITION":
                    loot_value *= 4
                elif war_type == "ORDINARY":
                    loot_value *= 2

                if best_date is None or war_dt > best_date:
                    best_date = war_dt
                    best_loot = int(round(loot_value))
                    break  # latest attack in this war found; move to next war
        except Exception:
            continue

    return best_loot


def weird_division(a: float, b: float) -> float:
    return a / b if b else 0


def str_to_int(string: str) -> int:
    string = str(string).replace(",", "")
    amount: Any = string
    try:
        if "." in str(amount):
            number = re.sub("[A-z]", "", str(amount))
            amount = int(number.replace(".", "")) / 10**(len(number) - number.rfind(".") - 1)
    except (ValueError, AttributeError):
        pass
    if "k" in string.lower():
        amount = int(float(re.sub("[A-z]", "", str(amount))) * 1000)
    elif "m" in string.lower():
        amount = int(float(re.sub("[A-z]", "", str(amount))) * 1000000)
    elif "b" in string.lower():
        amount = int(float(re.sub("[A-z]", "", str(amount))) * 1000000000)
    else:
        try:
            amount = int(amount)
        except (ValueError, TypeError):
            pass
    if not isinstance(amount, int):
        raise ValueError("The provided value is not a valid amount.")
    return amount

def str_to_id_list(value: str) -> tuple[list[str], str]:
    """Convert mixed string input into list of numeric substrings and CSV."""
    value = re.sub("[^0-9]", " ", value)
    value = value.strip().replace(" ", ",")
    index = 0
    while True:
        try:
            if value[index] == value[index + 1] and not value[index].isdigit():
                value = value[:index] + value[index + 1:]
                index -= 1
            index += 1
        except Exception:
            break
    parts = [segment for segment in value.split(",") if segment]
    return parts, value


def str_to_api_key_list(value: str) -> list[str]:
    """Parse API keys from mixed strings, preserving legacy behaviour."""
    value = re.sub("[^0-9a-zA-Z]", " ", value)
    value = value.strip().replace(" ", ",")
    index = 0
    while True:
        try:
            if value[index] == value[index + 1] and not value[index].isdigit():
                value = value[:index] + value[index + 1:]
                index -= 1
            index += 1
        except Exception:
            break
    return [segment for segment in value.split(",") if segment]


# Order matches Politics & War GraphQL ``AlliancePositionEnum`` (``.ctx/pnwSchema.graphql``).
ALLIANCE_POSITION_ENUM_ORDER: tuple[str, ...] = (
    "NOALLIANCE",
    "APPLICANT",
    "MEMBER",
    "OFFICER",
    "HEIR",
    "LEADER",
)
_ALLIANCE_POSITION_ENUM_SET = frozenset(ALLIANCE_POSITION_ENUM_ORDER)


def normalize_alliance_position(value: Any) -> Any:
    """Coerce ``alliance_position`` to enum name strings.

    Full nation scans return uppercase enum strings; websocket subscription
    payloads may send the same field as a small integer (enum ordinal). SQLite
    can surface either shape depending on how the row was last updated.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value

    idx: int | None = None
    if isinstance(value, int):
        idx = value
    elif isinstance(value, float) and value.is_integer():
        idx = int(value)
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        upper = s.upper()
        if upper in _ALLIANCE_POSITION_ENUM_SET:
            return upper
        if s.isdigit():
            idx = int(s)
        else:
            return value
    else:
        return value

    if idx is not None and 0 <= idx < len(ALLIANCE_POSITION_ENUM_ORDER):
        return ALLIANCE_POSITION_ENUM_ORDER[idx]
    return value