"""Coerce raw Politics & War subscription payloads the way pnwkit-py did.

The scanner used to receive subscription events through pnwkit-py 2.6.26, which turned
each raw JSON item into typed objects (``Nation.from_data``) before the scanner flattened
them back into the dict it stores. That round trip changed values: ID-like fields became
ints, dates were re-serialised by ``datetime.fromisoformat(...).isoformat()``, unknown
enum names became ``None``, nested objects carrying ``__typename`` were converted the same
way, and ``global`` was renamed to ``global_``. :func:`coerce_payload` repeats those rules
on plain dicts so the rows written to ``nations.db`` stay the same without pnwkit.

Deliberate differences from pnwkit:

* No ``"__dict__"`` keys. pnwkit's ``Data.to_dict()`` spread ``__slots__ = ("__dict__",)``
  and so duplicated every converted object under a ``"__dict__"`` key (and therefore into a
  ``nations.__dict__`` column). Nothing reads it.
* Enum names come from the current GraphQL schema (``.ctx/pnwSchema.graphql``), which adds
  ``MINDHIVE`` and the four ``NAVALV*`` attack types that pnwkit 2.6.26 predates and stored
  as ``None``. Full HTTP scans already store these names.
* ``BBTeam.date`` is parsed like every other date; pnwkit's converter raised on any value.

As in pnwkit, a value that cannot be coerced (for example ``int(None)`` or an unknown
``__typename``) raises, so the caller can skip that item, as pnwkit did.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

Converter = Callable[[Any], Any]


def _iso(value: str) -> str:
    return datetime.fromisoformat(value).isoformat()


def _iso_or_none(value: str | None) -> str | None:
    return None if value is None else _iso(value)


def _int_or_none(value: Any) -> int | None:
    return None if value is None else int(value)


def _nuke_date(value: str) -> str | None:
    return None if value.startswith("-") or "0000-00-00" in value else _iso(value)


def _enum(names: str) -> Converter:
    """Keep a value only if it is one of the enum's member names, like ``Enum.__members__.get``."""
    allowed = frozenset(names.split())

    def convert(value: Any) -> Any:
        return value if value in allowed else None

    return convert


_ALLIANCE_POSITION = _enum("NOALLIANCE APPLICANT MEMBER OFFICER HEIR LEADER")
_WAR_POLICY = _enum(
    "ATTRITION TURTLE BLITZKRIEG FORTRESS MONEYBAGS PIRATE TACTICIAN GUARDIAN COVERT ARCANE"
)
_DOMESTIC_POLICY = _enum(
    "MANIFEST_DESTINY OPEN_MARKETS TECHNOLOGICAL_ADVANCEMENT IMPERIALISM URBANIZATION"
    " RAPID_EXPANSION"
)
_ECONOMIC_POLICY = _enum("EXTREME_LEFT FAR_LEFT LEFT MODERATE RIGHT FAR_RIGHT EXTREME_RIGHT")
_SOCIAL_POLICY = _enum(
    "ANARCHIST LIBERTARIAN LIBERAL MODERATE CONSERVATIVE AUTHORITARIAN FASCIST"
)
_GOVERNMENT_TYPE = _enum(
    "ABSOLUTE_MONARCHY ANARCHY ARISTOCRACY BANANA_REPUBLIC COMMUNIST_DEMOCRACY"
    " COMMUNIST_DICTATORSHIP COMMUNIST_MONARCHY COMMUNIST_REPUBLIC COMMUNIST_THEOCRACY"
    " CONSTITUTIONAL_MONARCHY CONSTITUTIONAL_REPUBLIC DEMARCHY DEMOCRACY DEMOCRATIC_REPUBLIC"
    " DICTATORSHIP FEDERAL_REPUBLIC MONARCHY NOOCRACY OLIGARCHY PARLIAMENTARY_DEMOCRACY"
    " PARLIAMENTARY_REPUBLIC PEOPLES_REPUBLIC REPUBLIC SOCIAL_DEMOCRACY SOCIALIST_DICTATORSHIP"
    " SOCIALIST_REPUBLIC SOCIALIST_THEOCRACY STRATOCRACY TECHNOCRACY THEOCRACY"
    " THEOCRATIC_DEMOCRACY THEOCRATIC_DICTATORSHIP THEOCRATIC_REPUBLIC MINDHIVE"
)
_WAR_TYPE = _enum("ORDINARY ATTRITION RAID")
_ATTACK_TYPE = _enum(
    "AIRVINFRA AIRVSOLDIERS AIRVTANKS AIRVMONEY AIRVSHIPS AIRVAIR GROUND MISSILE MISSILEFAIL"
    " NUKE NUKEFAIL NAVAL NAVALVSHIPS NAVALVINFRA NAVALVGROUND NAVALVAIR FORTIFY PEACE VICTORY"
    " ALLIANCELOOT"
)
_BOUNTY_TYPE = _enum("ORDINARY ATTRITION RAID NUCLEAR")
_TRADE_TYPE = _enum("GLOBAL PERSONAL ALLIANCE")


def _ints(*fields: str) -> dict[str, Converter]:
    return {field: int for field in fields}


def _dates(*fields: str) -> dict[str, Converter]:
    return {field: _iso for field in fields}


# Per-``__typename`` field converters, copied from pnwkit-py 2.6.26 ``pnwkit/data.py``.
# Types listed with no converters still take part in nested conversion.
_CONVERTERS: dict[str, dict[str, Converter]] = {
    "Data": {},
    "ApiKeyPermissions": {},
    "ApiKeyDetails": {},
    "Color": {},
    "Radiation": {},
    "PaginatorInfo": {},
    "Account": {"last_active": _iso, "discord_id": _int_or_none},
    "Nation": {
        **_ints("id", "alliance_id", "alliance_position_id", "tax_id"),
        **_dates("last_active", "date"),
        "alliance_position": _ALLIANCE_POSITION,
        "war_policy": _WAR_POLICY,
        "domestic_policy": _DOMESTIC_POLICY,
        "economic_policy": _ECONOMIC_POLICY,
        "social_policy": _SOCIAL_POLICY,
        "government_type": _GOVERNMENT_TYPE,
        "moon_landing_date": _iso_or_none,
        "mars_landing_date": _iso_or_none,
        "alliance_join_date": _iso_or_none,
    },
    "AlliancePosition": {
        **_ints("id", "alliance_id", "creator_id", "last_editor_id"),
        **_dates("date", "date_modified"),
    },
    "Alliance": {"id": int, "date": _iso},
    "Treaty": {**_ints("id", "alliance1_id", "alliance2_id"), "date": _iso},
    "Bankrec": {
        **_ints(
            "id", "sid", "sender_id", "rid", "recipient_id", "receiver_id", "pid",
            "banker_id", "tax_id",
        ),
        "date": _iso,
    },
    "TaxBracket": {
        **_ints("id", "alliance_id", "last_modifier_id"),
        **_dates("date", "date_modified"),
    },
    "City": {
        **_ints("id", "nation_id"),
        "date": _iso,
        "nukedate": _nuke_date,
        "nuke_date": _nuke_date,
    },
    "Treasure": {"nation_id": int, **_dates("spawndate", "spawn_date")},
    "War": {
        **_ints(
            "id", "groundcontrol", "ground_control", "airsuperiority", "air_superiority",
            "navalblockade", "naval_blockade", "winner", "winner_id", "attid", "att_id",
            "att_alliance_id", "defid", "def_id", "def_alliance_id",
        ),
        "date": _iso,
        "war_type": _WAR_TYPE,
        "att_alliance_position": _ALLIANCE_POSITION,
        "def_alliance_position": _ALLIANCE_POSITION,
    },
    "WarAttack": {
        **_ints(
            "id", "attid", "att_id", "defid", "def_id", "warid", "war_id", "cityid", "city_id"
        ),
        "date": _iso,
        "type": _ATTACK_TYPE,
    },
    "Bounty": {**_ints("id", "nation_id"), "date": _iso, "type": _BOUNTY_TYPE},
    "BBTeam": {**_ints("id", "nation_id"), "date": _iso},
    "BBGame": {
        **_ints("id", "home_id", "away_id", "home_nation_id", "away_nation_id"),
        "date": _iso,
    },
    "BBPlayer": {**_ints("id", "nation_id", "team_id"), "date": _iso},
    "GameInfo": {"game_date": _iso},
    "Tradeprice": {"id": int, "date": _iso},
    "Trade": {
        **_ints("id", "sid", "sender_id", "rid", "recipient_id", "receiver_id"),
        "type": _TRADE_TYPE,
        "date": _iso,
        "date_accepted": _iso_or_none,
        "original_trade_id": _int_or_none,
    },
    "TreasureTrade": {
        **_ints("id", "sender_id", "receiver_id"),
        **_dates("offer_date", "accept_date"),
    },
    "Embargo": {**_ints("id", "sender_id", "receiver_id"), "date": _iso},
}


class PayloadTypeError(ValueError):
    """A payload names a ``__typename`` that pnwkit had no data class for."""


def _converters_for(typename: Any) -> dict[str, Converter]:
    try:
        return _CONVERTERS[typename]
    except (KeyError, TypeError):
        raise PayloadTypeError(f"unknown __typename {typename!r}") from None


def _coerce_object(typename: str, data: dict[str, Any]) -> dict[str, Any]:
    converters = _converters_for(typename)
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key == "global":
            key = "global_"
        if isinstance(value, dict):
            value = _coerce_dict(value)
        elif isinstance(value, list):
            value = _coerce_list(value)
        converter = converters.get(key)
        if converter is not None:
            value = converter(value)
        out[key] = value
    return out


def _coerce_dict(data: dict[str, Any]) -> Any:
    typename = data.get("__typename")
    if typename is None:
        return data
    if isinstance(typename, str) and typename.endswith("Paginator"):
        return _coerce_list(data["data"])
    return _coerce_object(typename, data)


def _coerce_list(items: list[Any]) -> list[Any]:
    # Like pnwkit, the first element decides whether (and as what) the whole list converts.
    if not items:
        return []
    first = items[0]
    if not isinstance(first, dict) or first.get("__typename") is None:
        return items
    typename = first["__typename"]
    return [_coerce_object(typename, item) for item in items]


def model_typename(model: str) -> str:
    """Return the ``__typename`` pnwkit used for a subscription model, e.g. ``"Nation"``."""
    name = "".join(part.capitalize() for part in model.split("_"))
    return "WarAttack" if name.lower() == "warattack" else name


def coerce_payload(model: str, item: dict[str, Any]) -> dict[str, Any]:
    """Coerce one subscription item for ``model`` exactly as pnwkit-py would have.

    Args:
        model: Subscription model name, e.g. ``"nation"``.
        item: One decoded item from a subscription event.

    Returns:
        A new dict whose values are JSON-safe and match what the scanner stored when
        events came through pnwkit-py.

    Raises:
        PayloadTypeError: If the model or a nested ``__typename`` is unknown.
        TypeError, ValueError, AttributeError: If a field cannot be coerced (pnwkit dropped
            such items).
    """
    if not isinstance(item, dict):
        raise TypeError(f"subscription item must be an object, got {type(item).__name__}")
    return _coerce_object(model_typename(model), item)
