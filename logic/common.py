from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

RSS = ['aluminum', 'bauxite', 'coal', 'food', 'gasoline', 'iron', 'lead', 'money', 'munitions', 'oil', 'steel', 'uranium', 'credits']
EMBED_COLOR = 0xff5100  # Orange color used throughout Autolycus embeds

# Resource order matches legacy loot_info strings and GraphQL ``*_looted`` fields.
BEIGE_LOOT_RESOURCES: tuple[str, ...] = (
    'money',
    'coal',
    'oil',
    'uranium',
    'iron',
    'bauxite',
    'lead',
    'gasoline',
    'munitions',
    'steel',
    'aluminum',
    'food',
)


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
    n = 0
    loot: dict[str, int] = {}
    for sub in loot_string.split("-"):
        loot[BEIGE_LOOT_RESOURCES[n]] = int(sub)
        n += 1
    nation_loot = 0.0
    for rs in BEIGE_LOOT_RESOURCES:
        amount = loot[rs]
        price = float(prices[rs])
        nation_loot += amount * price
    return int(round(nation_loot))


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


def _price_for(prices: dict[str, float], resource: str) -> float:
    if resource == 'money':
        return 1.0
    raw = prices.get(resource)
    if raw is None:
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _looted_field_name(resource: str) -> str:
    return 'money_looted' if resource == 'money' else f'{resource}_looted'


def attack_has_structured_loot(attack: dict[str, Any]) -> bool:
    """True when the attack payload includes GraphQL ``*_looted`` fields."""
    return any(_looted_field_name(rs) in attack for rs in BEIGE_LOOT_RESOURCES)


def structured_beige_loot_value(attack: dict[str, Any], prices: dict[str, float]) -> Optional[float]:
    """Market value of victory loot from GraphQL ``*_looted`` fields.

    ``loot_info`` is deprecated on the Politics & War API ("No longer in use").
    Victory / beige loot is exposed as ``money_looted`` plus ``{resource}_looted``.
    Returns *None* when the attack has no structured loot payload at all.
    """
    if not attack_has_structured_loot(attack):
        return None
    total = 0.0
    for resource in BEIGE_LOOT_RESOURCES:
        raw = attack.get(_looted_field_name(resource))
        if raw is None:
            continue
        try:
            amount = float(raw)
        except (TypeError, ValueError):
            continue
        total += amount * _price_for(prices, resource)
    return total


def _attack_beige_loot_market_value(
    attack: dict[str, Any],
    prices: dict[str, float],
) -> Optional[float]:
    """Resolve beige loot market value for one attack.

    Prefers structured ``*_looted`` fields; falls back to legacy ``loot_info``
    text parsing for older cached war rows.
    """
    structured = structured_beige_loot_value(attack, prices)
    if structured is not None:
        return structured

    text = attack.get('loot_info')
    if not text or "won the war and looted" not in str(text):
        return None
    try:
        return float(beige_loot_value(str(text), prices))
    except Exception:
        return None


def _is_beige_loot_attack(attack: dict[str, Any], nation_id: str) -> bool:
    """True when *attack* is a victory loot event against *nation_id*."""
    victor = str(attack.get('victor', '') or '')
    if victor and victor == nation_id:
        return False  # they won, so this is not their beige loot

    attack_type = str(attack.get('type') or '').upper()
    if attack_type == 'ALLIANCELOOT':
        return False  # alliance bank loot, not nation beige loot
    if attack_type == 'VICTORY':
        return True

    # Legacy cached rows: only loot_info text identified beige loot.
    text = attack.get('loot_info')
    return bool(text and "won the war and looted" in str(text))


def _undo_loot_multipliers(loot_value: float, war: dict[str, Any]) -> float:
    """Reverse attacker policy / war-type multipliers to estimate base loot."""
    attacker_info = war.get('attacker') or {}
    policy = (attacker_info.get('war_policy') or '').upper()
    if policy == "ATTRITION":
        loot_value = loot_value / 0.8
    elif policy == "PIRATE":
        loot_value = loot_value / 1.4
    if attacker_info.get('advanced_pirate_economy'):
        loot_value = loot_value / 1.1

    war_type = (war.get('war_type') or '').upper()
    if war_type == "ATTRITION":
        loot_value *= 4
    elif war_type == "ORDINARY":
        loot_value *= 2
    return loot_value


def compute_beige_loot(
    nation: dict[str, Any],
    prices: Optional[dict[str, float]],
) -> Optional[int]:
    """Compute estimated beige loot value from a nation's finished wars.

    Scans cached war logs for the most recent war where the nation was the
    defender and lost, then reverse-engineers the *base* loot value by
    undoing attacker policy / war-type multipliers.  This gives a rough
    estimate of how much loot the nation is holding.

    Prefers GraphQL structured ``money_looted`` / ``*_looted`` fields because
    ``loot_info`` is deprecated and commonly empty. Falls back to parsing
    legacy ``loot_info`` strings when structured fields are absent.

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
            turns_left = war.get('turnsleft', war.get('turns_left', 1))
            try:
                turns_left_val = float(turns_left)
            except (TypeError, ValueError):
                turns_left_val = 1
            if turns_left_val > 0:
                continue  # still active

            def_id = war.get('defid', war.get('def_id'))
            if str(def_id) != nation_id:
                continue  # only care about wars where this nation was defender

            war_dt = parse_war_date(war.get('date'))
            attacks = war.get('attacks') or []

            for attack in reversed(attacks):  # reverse to favour latest attack
                if not _is_beige_loot_attack(attack, nation_id):
                    continue

                loot_value = _attack_beige_loot_market_value(attack, prices)
                if loot_value is None:
                    continue

                loot_value = _undo_loot_multipliers(float(loot_value), war)

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