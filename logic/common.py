from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

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


def comma_and_list(listy: list[str]) -> str:
    if not listy:
        return ""
    if len(listy) == 1:
        return listy[0]
    return ", ".join(listy[:-1]) + " and " + listy[-1]


def get_datetime_of_turns(turns: int) -> datetime:
    # Timezone-aware: callers use .timestamp(), which reads naive datetimes as local time.
    now = datetime.now(timezone.utc)
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


# Rows written by the old pnwkit-based subscription path may hold AttackType ordinals
# (VICTORY=14). HTTP GraphQL nation scans return enum *names*.
_ATTACK_TYPE_BY_ORDINAL: dict[int, str] = {
    0: 'AIRVINFRA',
    1: 'AIRVSOLDIERS',
    2: 'AIRVTANKS',
    3: 'AIRVMONEY',
    4: 'AIRVSHIPS',
    5: 'AIRVAIR',
    6: 'GROUND',
    7: 'MISSILE',
    8: 'MISSILEFAIL',
    9: 'NUKE',
    10: 'NUKEFAIL',
    11: 'NAVAL',
    12: 'FORTIFY',
    13: 'PEACE',
    14: 'VICTORY',
    15: 'ALLIANCELOOT',
}


def normalize_attack_type(value: Any) -> str:
    """Normalize attack type to an uppercase enum name.

    Nation scans use raw HTTP GraphQL (string names like ``VICTORY``).
    Rows stored by the old pnwkit-based subscription path may hold ordinals (``14``).
    """
    if value is None or isinstance(value, bool):
        return ''
    if isinstance(value, (int, float)) and float(value).is_integer():
        return _ATTACK_TYPE_BY_ORDINAL.get(int(value), str(int(value)))
    text = str(value).strip()
    if not text:
        return ''
    if text.isdigit():
        return _ATTACK_TYPE_BY_ORDINAL.get(int(text), text)
    if '.' in text:
        text = text.split('.')[-1]
    return text.upper()


def _looted_field_name(resource: str) -> str:
    return 'money_looted' if resource == 'money' else f'{resource}_looted'


def attack_has_nonzero_structured_loot(attack: dict[str, Any]) -> bool:
    """True when any structured loot amount is present and non-zero."""
    for resource in BEIGE_LOOT_RESOURCES:
        raw = attack.get(_looted_field_name(resource))
        if raw is None:
            continue
        try:
            if float(raw) != 0.0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def structured_beige_loot_value(attack: dict[str, Any], prices: dict[str, float]) -> Optional[float]:
    """Market value of victory loot from GraphQL ``*_looted`` fields.

    ``loot_info`` is deprecated on the Politics & War API ("No longer in use").
    Victory / beige loot is exposed as ``money_looted`` plus ``{resource}_looted``.
    Returns *None* when no numeric ``*_looted`` amounts are present (keys may
    still exist as JSON ``null`` from GraphQL / pnwkit defaults).
    """
    total = 0.0
    found_amount = False
    for resource in BEIGE_LOOT_RESOURCES:
        raw = attack.get(_looted_field_name(resource))
        if raw is None:
            continue
        try:
            amount = float(raw)
        except (TypeError, ValueError):
            continue
        found_amount = True
        total += amount * _price_for(prices, resource)
    return total if found_amount else None


def _attack_beige_loot_market_value(
    attack: dict[str, Any],
    prices: dict[str, float],
) -> Optional[float]:
    """Resolve beige loot market value for one attack.

    Prefers structured ``*_looted`` fields when they carry a positive total;
    otherwise falls back to legacy ``loot_info`` text. Null/zero structured
    payloads must not mask a usable ``loot_info`` string (that previously
    forced ``nation_loot_value`` to 0 on the raids page).
    """
    structured = structured_beige_loot_value(attack, prices)
    if structured is not None and structured > 0:
        return structured

    text = attack.get('loot_info')
    if not text or "won the war and looted" not in str(text):
        # Genuine structured zero-loot victory (no loot_info fallback).
        if structured is not None:
            return structured
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

    attack_type = normalize_attack_type(attack.get('type'))
    if attack_type == 'ALLIANCELOOT':
        return False  # alliance bank loot, not nation beige loot
    if attack_type == 'VICTORY':
        return True

    # Legacy cached rows: only loot_info text identified beige loot.
    text = attack.get('loot_info')
    if text and "won the war and looted" in str(text):
        return True

    # Structured loot amounts without a usable type (partial cache / enum loss).
    if attack_type in ('', 'NONE') and attack_has_nonzero_structured_loot(attack):
        return True
    return False


# Share of the full loot each war type grants, by the side that takes it
# (PWPedia War-Types): a defender winning an attrition war takes 50%, not 25%.
_WAR_TYPE_LOOT_SHARE: dict[str, dict[str, float]] = {
    'attacker': {'RAID': 1.0, 'ORDINARY': 0.5, 'ATTRITION': 0.25},
    'defender': {'RAID': 1.0, 'ORDINARY': 0.5, 'ATTRITION': 0.5},
}


def _undo_loot_multipliers(loot_value: float, war: dict[str, Any], looter: str) -> float:
    """Reverse the looter's war policy, Advanced Pirate Economy and war-type share.

    *looter* is the war side that took the loot (``'attacker'`` or ``'defender'``),
    so the result is what a raider declaring a raid war without loot bonuses gets.
    """
    looter_info = war.get(looter) or {}
    policy = _normalize_war_policy(
        looter_info.get('war_policy') or looter_info.get('warpolicy')
    )
    if policy == "ATTRITION":
        loot_value = loot_value / 0.8
    elif policy == "PIRATE":
        loot_value = loot_value / 1.4
    # Advanced Pirate Economy adds 10% to victory loot; Pirate Economy only boosts
    # ground-attack loot, so it is not undone here (.ctx/projects_canon.md).
    if looter_info.get('advanced_pirate_economy'):
        loot_value = loot_value / 1.1

    war_type = normalize_war_type(war.get('war_type'))
    return loot_value / _WAR_TYPE_LOOT_SHARE[looter].get(war_type, 1.0)


_WAR_TYPE_BY_ORDINAL: dict[int, str] = {
    0: 'ORDINARY',
    1: 'ATTRITION',
    2: 'RAID',
}

# pnwkit WarPolicy ordinals (ATTRITION starts at 1), found in rows it stored.
_WAR_POLICY_BY_ORDINAL: dict[int, str] = {
    1: 'ATTRITION',
    2: 'TURTLE',
    3: 'BLITZKRIEG',
    4: 'FORTRESS',
    5: 'MONEYBAGS',
    6: 'PIRATE',
    7: 'TACTICIAN',
    8: 'GUARDIAN',
    9: 'COVERT',
    10: 'ARCANE',
}


def normalize_war_type(value: Any) -> str:
    """War type as an uppercase enum name (``RAID``), accepting ordinals and ``WarType.X``."""
    if value is None or isinstance(value, bool):
        return ''
    if isinstance(value, (int, float)) and float(value).is_integer():
        return _WAR_TYPE_BY_ORDINAL.get(int(value), str(int(value)))
    text = str(value).strip()
    if not text:
        return ''
    if text.isdigit():
        return _WAR_TYPE_BY_ORDINAL.get(int(text), text)
    if '.' in text:
        text = text.split('.')[-1]
    return text.upper()


def _normalize_war_policy(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ''
    if isinstance(value, (int, float)) and float(value).is_integer():
        return _WAR_POLICY_BY_ORDINAL.get(int(value), str(int(value)))
    text = str(value).strip()
    if not text:
        return ''
    if text.isdigit():
        return _WAR_POLICY_BY_ORDINAL.get(int(text), text)
    if '.' in text:
        text = text.split('.')[-1]
    return text.upper()


def _war_field(war: dict[str, Any], *keys: str) -> Any:
    """First non-null value among *keys* (deprecated and current GraphQL names)."""
    for key in keys:
        value = war.get(key)
        if value is not None:
            return value
    return None


def _nation_side(war: dict[str, Any], nation_id: str) -> Optional[str]:
    """``'defender'`` or ``'attacker'``: the side of *war* the nation fought on."""
    def_id = _war_field(war, 'defid', 'def_id')
    att_id = _war_field(war, 'attid', 'att_id')
    if def_id is not None and str(def_id) == nation_id:
        return 'defender'
    if att_id is not None and str(att_id) == nation_id:
        return 'attacker'
    if def_id is not None and att_id is None:
        # Nation.wars lists only the nation's own wars, and rows scanned before
        # ``attid`` was queried lack it: a war it did not defend, it declared.
        return 'attacker'
    return None


def _lost_war_loot(
    war: dict[str, Any],
    nation_id: str,
    prices: dict[str, float],
    side: str,
) -> tuple[bool, Optional[float]]:
    """``(lost, normalized_loot)`` for one finished war the nation fought on *side*.

    ``lost`` is True when the nation was beaten: a beige-loot attack against it,
    or the opponent recorded as the war's winner. The loot comes from the latest
    such attack, a genuine $0 included; when no attack carries loot data it is
    the money the winning side looted (``att_money_looted`` for a war the nation
    defended, ``def_money_looted`` for one it declared; bulk scans often omit
    nested attacks). It is None when the war has no loot data at all.
    """
    winner = str(_war_field(war, 'winner', 'winner_id') or '')
    if winner == nation_id:
        return False, None  # it won this war; any loot in it was its own

    looter = 'attacker' if side == 'defender' else 'defender'
    lost = False
    for attack in reversed(war.get('attacks') or []):  # latest attack first
        if not _is_beige_loot_attack(attack, nation_id):
            continue
        if side == 'attacker' and not attack.get('victor'):
            # Without a victor this could be the nation's own win, and raiders
            # usually win the wars they declare: only count a proven defeat.
            continue
        lost = True
        loot_value = _attack_beige_loot_market_value(attack, prices)
        if loot_value is not None:
            return True, _undo_loot_multipliers(max(float(loot_value), 0.0), war, looter)

    if winner not in ('', '0'):
        lost = True
    if not lost:
        return False, None

    raw_money = war.get('att_money_looted' if looter == 'attacker' else 'def_money_looted')
    try:
        money_loot = float(raw_money) if raw_money is not None else None
    except (TypeError, ValueError):
        money_loot = None
    if money_loot is None:
        return True, None
    return True, _undo_loot_multipliers(max(money_loot, 0.0), war, looter)


def compute_beige_loot(
    nation: dict[str, Any],
    prices: Optional[dict[str, float]],
) -> Optional[int]:
    """Estimate what a raider can expect to loot when this nation is next beiged.

    Uses only the nation's most recent lost war (ranked by end date), whether it
    defended that war or declared it and was beaten back, including a genuine $0
    result; older defeats never stand in for it. The loot is normalized to a
    baseline raider: the winner's war policy, Advanced Pirate Economy and its
    war-type share are undone, giving the value for a raid war declared by an
    attacker without loot bonuses. The nation's own war policy (Moneybags,
    Turtle, Guardian) is kept, since it also applies to the next raid.

    Prefers GraphQL structured ``money_looted`` / ``*_looted`` fields because
    ``loot_info`` is deprecated and commonly empty. Falls back to parsing
    legacy ``loot_info`` strings when structured fields are absent.

    Args:
        nation: Nation dict (must include ``id`` and ``wars`` fields).
        prices: Current market prices keyed by resource name.  When *None*
            the computation is skipped.

    Returns:
        Estimated loot value in dollars, or *None* when it cannot be computed
        (no prices, no lost war, or that war has no loot data).
    """
    if not prices:
        return None

    wars = nation.get('wars') or []
    nation_id = str(nation.get('id', ''))
    if not nation_id or not wars:
        return None

    latest_date: Optional[datetime] = None
    latest_loot: Optional[float] = None

    for war in wars:
        try:
            turns_left = war.get('turnsleft', war.get('turns_left', 1))
            try:
                turns_left_val = float(turns_left)
            except (TypeError, ValueError):
                turns_left_val = 1
            if turns_left_val > 0:
                continue  # still active

            side = _nation_side(war, nation_id)
            if side is None:
                continue

            lost, loot = _lost_war_loot(war, nation_id, prices, side)
            if not lost:
                continue

            # Rank by when the war ended (the defeat that set current holdings), not when
            # it was declared: overlapping wars can end in either order.
            war_dt = parse_war_date(war.get('end_date') or war.get('date'))
            if latest_date is None or war_dt > latest_date:
                latest_date = war_dt
                latest_loot = loot
        except Exception:
            continue

    if latest_loot is None:
        return None
    return int(round(latest_loot))


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