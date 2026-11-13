from __future__ import annotations

import asyncio
import json
import logging
import math
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from . import queries
from infra.cache import cache_historical_prices
from logic.merge_utils import get_query
from logic.military import max_units
from logic.revenue import (calculate_nation_modifiers, calculate_treasure_bonus,
                           pre_revenue_calc, revenue_calc_sync, unit_upkeep_rates)
from database import sqlite_cache as db_utils

logger = logging.getLogger(__name__)

BuildDict = Dict[str, Any]
GraphQLCaller = Callable[[str], Awaitable[dict[str, Any]]]


class BuildInputError(ValueError):
    """The requested build criteria can't be used; the message is shown to users."""


class NationNotFoundError(ValueError):
    """The nation to calculate builds for does not exist."""


# Project flags that change revenue or build caps; api/constants/projects.py
# describes the same keys for the builds form.
REVENUE_PROJECT_FIELDS = (
    "ironw",
    "bauxitew",
    "armss",
    "egr",
    "massirr",
    "itc",
    "telecom_satellite",
    "recycling_initiative",
    "green_tech",
    "clinical_research_center",
    "specialized_police_training",
    "uap",
    "fallout_shelter",
    "government_support_agency",
    "bureau_of_domestic_affairs",
)


def _apply_overrides(
    nation: dict[str, Any],
    projects: Optional[List[str]],
    dom_policy: Optional[str],
) -> None:
    """Apply form overrides onto a nation payload.

    ``projects``:
      - ``None`` keeps the nation's existing project flags
      - a list (including empty) replaces revenue-relevant project flags
    ``dom_policy``:
      - ``None`` keeps the nation's domestic policy
      - any string (including ``""``) replaces ``dompolicy``
    """
    if projects is not None:
        selected = set(projects)
        for project_key in REVENUE_PROJECT_FIELDS:
            nation[project_key] = project_key in selected
    if dom_policy is not None:
        nation["dompolicy"] = dom_policy


def _max_units_from_city(city: BuildDict, population: float) -> Dict[str, int]:
    return max_units(
        city.get("barracks", 0), city.get("factory", 0), city.get("airforcebase", 0), city.get("drydock", 0), population
    )


def _unit_upkeep(
    max_units: Dict[str, int],
    rates: Dict[str, tuple[float, float]],
    mil_cost_mod: float,
) -> tuple[float, float, Dict[str, float], Dict[str, float]]:
    """``(money, food, money_by_unit, food_by_unit)`` for a city's maximum units."""
    breakdown = {unit: count * rates[unit][0] * mil_cost_mod for unit, count in max_units.items()}
    food_breakdown = {unit: count * rates[unit][1] for unit, count in max_units.items()}
    return sum(breakdown.values()), sum(food_breakdown.values()), breakdown, food_breakdown


def _unit_upkeep_report(
    max_units: Dict[str, int],
    *,
    peace_rates: Dict[str, tuple[float, float]],
    war_rates: Dict[str, tuple[float, float]],
    selected_mode: str,
    mil_cost_mod: float,
    included: bool,
) -> Dict[str, Any]:
    """The ``unit_upkeep`` block the builds page shows for one build."""
    modes = {}
    for mode, rates in (("peace", peace_rates), ("war", war_rates)):
        total, food, breakdown, food_breakdown = _unit_upkeep(max_units, rates, mil_cost_mod)
        modes[mode] = {
            "total": round(total),
            "food": round(food, 4),
            "breakdown": {k: round(v) for k, v in breakdown.items()},
            "breakdownFood": {k: round(v, 4) for k, v in food_breakdown.items()},
        }
    return {
        "included": included,
        "selectedMode": selected_mode,
        "mode": selected_mode,
        **modes[selected_mode],
        "counts": max_units,
        "modes": modes,
    }


def _score_build_cities_sync(
    *,
    base_nation: dict[str, Any],
    to_scan: list[BuildDict],
    radiation: dict[str, float],
    treasures: list[dict[str, Any]],
    prices: dict[str, float],
    colors: dict[str, float],
    seasonal_mod: dict[str, float],
    modifiers: dict[str, float],
    treasure_bonus: float,
    upkeep_rates: Dict[str, tuple[float, float]],
    include_military_upkeep: bool,
    disable_population_income: bool,
) -> list[BuildDict]:
    mil_cost_mod = float(modifiers.get("mil_cost", 1))
    cities: list[BuildDict] = []
    for city in to_scan:
        nation_local = dict(base_nation)
        nation_local["cities"] = [city]

        revenue = revenue_calc_sync(
            nation_local,
            radiation,
            treasures,
            prices,
            colors,
            seasonal_mod,
            single_city=True,
            disable_population_income=disable_population_income,
            modifiers=modifiers,
            treasure_bonus=treasure_bonus,
        )

        # The per-unit breakdown is built later, only for the builds returned.
        max_units = _max_units_from_city(city, revenue.get("population", 0))
        revenue["_max_units"] = max_units
        if include_military_upkeep:
            active_total = sum(count * upkeep_rates[unit][0] for unit, count in max_units.items()) * mil_cost_mod
            # "money" ranks the money winner, so it carries the upkeep too.
            for key in ("net income", "net_cash_num", "net income real", "net_cash_num_real", "money", "money real"):
                revenue[key] = revenue.get(key, 0) - active_total
        cities.append(revenue)

    return cities


def _rank_builds_sync(
    cities: list[BuildDict], resources: list[str]
) -> tuple[list[BuildDict], Dict[str, BuildDict]]:
    """Order builds by net income and pick the best build for each resource.

    city_builds.db rows are unique per infrastructure level, so no dedupe is
    needed. Ties on a resource go to the build with the higher net income:
    ``max`` keeps the first of equal items and the list is in that order.
    """
    ranked = sorted(cities, key=lambda build: build.get("net income", 0), reverse=True)
    best = {resource: max(ranked, key=lambda build: build.get(resource, 0)) for resource in resources}
    return ranked, best


# Raw resource availability per continent.
# Source: fandom_data.jsonl - continent-specific articles (Africa, Asia, Australia, Antarctica, Europe, North America, South America)
# Each continent has exactly 3 raw resources available.
_CONTINENT_AVAILABLE: Dict[str, Dict[str, List[str]]] = {
    "af": {  # Africa: Oil, Bauxite, Uranium
        "api_names": ["oil_wells", "bauxite_mines", "uranium_mines"],
        "json_names": ["oilwell", "bauxitemine", "uramine"],
    },
    "as": {  # Asia: Oil, Iron, Uranium
        "api_names": ["oil_wells", "iron_mines", "uranium_mines"],
        "json_names": ["oilwell", "ironmine", "uramine"],
    },
    "au": {  # Australia: Coal, Bauxite, Lead
        "api_names": ["coal_mines", "bauxite_mines", "lead_mines"],
        "json_names": ["coalmine", "bauxitemine", "leadmine"],
    },
    "an": {  # Antarctica: Coal, Oil, Uranium
        "api_names": ["coal_mines", "oil_wells", "uranium_mines"],
        "json_names": ["coalmine", "oilwell", "uramine"],
    },
    "eu": {  # Europe: Coal, Iron, Lead
        "api_names": ["coal_mines", "iron_mines", "lead_mines"],
        "json_names": ["coalmine", "ironmine", "leadmine"],
    },
    "na": {  # North America: Coal, Iron, Uranium
        "api_names": ["coal_mines", "iron_mines", "uranium_mines"],
        "json_names": ["coalmine", "ironmine", "uramine"],
    },
    "sa": {  # South America: Oil, Bauxite, Lead
        "api_names": ["oil_wells", "bauxite_mines", "lead_mines"],
        "json_names": ["oilwell", "bauxitemine", "leadmine"],
    },
}

_ALL_RAW_MINE_JSON = [
    "coalmine",
    "oilwell",
    "uramine",
    "leadmine",
    "ironmine",
    "bauxitemine",
]


_CONTINENT_NORMALISATION = {
    "africa": "af",
    "af": "af",
    "asia": "as",
    "as": "as",
    "australia": "au",
    "au": "au",
    "antarctica": "an",
    "an": "an",
    "europe": "eu",
    "eu": "eu",
    "north america": "na",
    "north_america": "na",
    "na": "na",
    "south america": "sa",
    "south_america": "sa",
    "sa": "sa",
}


_RESOURCE_KEYS = [
    "net income",
    "aluminum",
    "bauxite",
    "coal",
    "food",
    "gasoline",
    "iron",
    "lead",
    "money",
    "munitions",
    "oil",
    "steel",
    "uranium",
]


def parse_mmr(mmr: str) -> Tuple[int, int, int, int]:
    """Parse military requirement string into numeric tuple (barracks/factory/hangar/drydock).

    Accepts slash-separated values (`5/5/3/1`, `10/0/0/2`), a compact 4-digit
    string (`1251` → `1/2/5/1`), or `any`.
    """
    raw = mmr.strip()
    if raw.lower() == "any":
        return (0, 0, 0, 0)

    if len(raw) == 4 and raw.isdigit():
        return tuple(int(digit) for digit in raw)  # type: ignore[return-value]

    parts = [part.strip() for part in raw.split("/")]
    if len(parts) != 4:
        raise BuildInputError(f"Invalid MMR format: {mmr}")
    try:
        values = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise BuildInputError(f"Invalid MMR format: {mmr}") from exc
    return values  # type: ignore[return-value]


def normalize_continent_code(continent: str) -> Optional[str]:
    """Normalize a continent label to a short code (na, sa, …), or None if unknown."""
    key = continent.strip().lower()
    return _CONTINENT_NORMALISATION.get(key)


def get_continent_resources(continent: str) -> Dict[str, List[str]]:
    """Return available raw-resource improvements for a continent."""
    code = normalize_continent_code(continent)
    if code is None:
        logger.debug("Unknown continent '%s'; no availability list applied", continent)
        return {"api_names": [], "json_names": []}
    return _CONTINENT_AVAILABLE.get(code, {"api_names": [], "json_names": []})


def get_restricted_mines(continent: str) -> List[str]:
    """Return mine fields that must be zero because they are unavailable on the continent."""
    code = normalize_continent_code(continent)
    if code is None:
        logger.debug("Unknown continent '%s'; no mine restrictions applied", continent)
        return []
    available = set(_CONTINENT_AVAILABLE.get(code, {}).get("json_names", []))
    return [mine for mine in _ALL_RAW_MINE_JSON if mine not in available]


def _neutral_manual_nation(continent_code: str) -> dict[str, Any]:
    """Baseline nation used when calculating builds without a real nation id."""
    return {
        "id": 0,
        "nation_name": "Manual Configuration",
        "leader_name": "",
        "continent": continent_code,
        "color": "beige",
        "num_cities": 30,
        "dompolicy": "",
        "alliance_id": 0,
        "alliance": None,
        "date": "2010-01-01T00:00:00.000000Z",
        "cities": [],
        **{project_key: False for project_key in REVENUE_PROJECT_FIELDS},
    }


# P&W city bulk-import keys, in the order the import form lists them.
_TEMPLATE_FIELDS = (
    ("imp_coalpower", "coalpower"),
    ("imp_oilpower", "oilpower"),
    ("imp_windpower", "windpower"),
    ("imp_nuclearpower", "nuclearpower"),
    ("imp_coalmine", "coalmine"),
    ("imp_oilwell", "oilwell"),
    ("imp_uramine", "uramine"),
    ("imp_leadmine", "leadmine"),
    ("imp_ironmine", "ironmine"),
    ("imp_bauxitemine", "bauxitemine"),
    ("imp_farm", "farm"),
    ("imp_gasrefinery", "gasrefinery"),
    ("imp_aluminumrefinery", "aluminumrefinery"),
    ("imp_steelmill", "steelmill"),
    ("imp_munitionsfactory", "munitionsfactory"),
    ("imp_policestation", "policestation"),
    ("imp_hospital", "hospital"),
    ("imp_recyclingcenter", "recyclingcenter"),
    ("imp_subway", "subway"),
    ("imp_supermarket", "supermarket"),
    ("imp_bank", "bank"),
    ("imp_mall", "mall"),
    ("imp_stadium", "stadium"),
    ("imp_barracks", "barracks"),
    ("imp_factory", "factory"),
    ("imp_hangars", "airforcebase"),
    ("imp_drydock", "drydock"),
)


def generate_build_template(build: BuildDict) -> str:
    """Generate the JSON template for the P&W city bulk import."""
    infra = build.get("infrastructure", 0)
    template = {"infra_needed": infra, "imp_total": math.floor(float(infra) / 50)}
    template.update({key: build.get(field, 0) for key, field in _TEMPLATE_FIELDS})
    return json.dumps(template, indent=4)


async def _fetch_historical_prices(call_pnw: GraphQLCaller) -> Optional[dict[str, float]]:  
    """Fetch 30-day average trade prices from the API.
    
    Note: The API tradeprices endpoint doesn't support date filtering.
    We fetch the most recent 30 records which should correspond to ~30 days.
    Per pnwSchema.graphql: tradeprices only accepts 'first' and 'page' parameters.
    
    Note: This function is cached via _fetch_historical_prices_cached for 30 minutes.
    """
    return await _fetch_historical_prices_cached(call_pnw)


@cache_historical_prices(ttl=1800)  # Cache for 30 minutes - historical prices change slowly
async def _fetch_historical_prices_cached(call_pnw: GraphQLCaller) -> Optional[dict[str, float]]:  
    """Cached implementation of historical price fetching."""
    logger.debug("Fetching fresh historical prices from P&W API (cache miss or expired)")
    prices_selection = get_query(queries.PRICES)
    price_query = "{" f'tradeprices(first:30){{data{prices_selection}}}' "}"
    try:
        result = await call_pnw(price_query)
        # A partial-error response can carry "data": null or "tradeprices": null.
        price_data = ((result.get("data") or {}).get("tradeprices") or {}).get("data") or []
    except Exception:
        logger.exception("Failed to fetch historical prices")
        return None

    if not price_data:
        return None

    averaged: dict[str, float] = {"money": 1.0}
    resources = [
        "coal",
        "oil",
        "uranium",
        "iron",
        "bauxite",
        "lead",
        "gasoline",
        "munitions",
        "steel",
        "aluminum",
        "food",
        "credits",
    ]
    for resource in resources:
        values = [float(day.get(resource, 0)) for day in price_data if resource in day and day.get(resource) is not None]
        if values:
            averaged[resource] = sum(values) / len(values)
        else:
            averaged[resource] = 0.0
    return averaged


def _project_cap(nation: dict[str, Any], key: str, base: int) -> int:
    return base + int(bool(nation.get(key)))


async def calculate_builds(
    *,
    call_pnw: GraphQLCaller,
    nation_id: Optional[str] = None,
    nation: Optional[dict[str, Any]] = None,
    infra: Optional[int] = None,
    land: Optional[int] = None,
    mmr: str = "0/0/0/0",
    continent_override: Optional[str] = None,
    use_live_prices: bool = True,
    include_military_upkeep: bool = False,
    projects_override: Optional[List[str]] = None,
    domestic_policy_override: Optional[str] = None,
    military_upkeep_mode: Optional[str] = None,
    disable_population_income: bool = False,
) -> dict[str, Any]:
    """Calculate optimal city builds using shared game logic."""

    if nation is None and nation_id is not None:
        query = "{" f"nations(first:1 id:{nation_id})" "{data" f"{get_query(queries.BUILDS_NATION)}" "}}"  # noqa: E501
        response = await call_pnw(query)
        nation_list = ((response.get("data") or {}).get("nations") or {}).get("data") or []
        if not nation_list:
            raise NationNotFoundError(f"Nation {nation_id} not found in API")
        nation = nation_list[0]
        nation_id = str(nation.get("id"))
    elif nation is not None:
        nation_id = str(nation.get("id")) if nation.get("id") is not None else nation_id
    else:
        # Manual configuration: no real nation — use a neutral baseline.
        if infra is None or land is None:
            raise BuildInputError("infra and land are required when nation_id is not provided")
        continent_code_for_manual = normalize_continent_code(continent_override or "na") or "na"
        nation = _neutral_manual_nation(continent_code_for_manual)
        nation_id = "0"

    if nation is None:
        raise ValueError("Nation data unavailable after fetch")

    if infra is None:
        # Floor to a completed 50-infra chunk: rounding up would return builds
        # that need more improvement slots than the cities have.
        total_infra = sum(city.get("infrastructure", 0) for city in nation.get("cities", []))
        infra = int(total_infra / max(nation.get("num_cities", 1), 1) // 50) * 50
        if infra <= 0:
            raise BuildInputError("Infrastructure must be at least 50")

    # P&W city improvement capacity is based on completed 50-infra chunks.
    # Normalize user-provided infra to the largest valid chunk the city can actually support.
    if infra % 50 != 0:
        normalized_infra = (infra // 50) * 50
        if normalized_infra <= 0:
            raise BuildInputError("Infrastructure must be at least 50")
        logger.info(
            "Normalizing non-multiple infrastructure from %s to %s for build lookup",
            infra,
            normalized_infra,
        )
        infra = normalized_infra

    if land is None:
        total_land = sum(city.get("land", 0) for city in nation.get("cities", []))
        land = round(total_land / max(nation.get("num_cities", 1), 1))

    mmr_values = parse_mmr(mmr)

    continent_key = (continent_override or str(nation.get("continent", ""))).strip()
    continent_code = normalize_continent_code(continent_key)
    if continent_code is None:
        logger.debug("Unknown continent '%s'; defaulting food/radiation scoring to na", continent_key)
        continent_code = "na"
    # Ensure food/radiation scoring uses the selected continent, not the fetched nation's.
    nation["continent"] = continent_code
    restricted_mines = get_restricted_mines(continent_code)
    available_resources = list(_RESOURCE_KEYS)

    _apply_overrides(nation, projects_override, domestic_policy_override)

    valid_upkeep_modes = {"peace", "war"}
    selected_upkeep_mode = (military_upkeep_mode or "peace").lower()
    if selected_upkeep_mode not in valid_upkeep_modes:
        raise BuildInputError(
            "military_upkeep_mode must be one of: peace, war"
        )

    db_path = db_utils.get_builds_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Builds database not found at {db_path}")

    # Hard / project-gated per-city improvement caps.
    # Live P&W city dumps (2026-07) show supermarket max is 4 (pwpedia still says 6).
    # Project-gated caps confirmed by live dumps: hospital 5→6, recycling 3→4,
    # bank 5→6 (ITC), mall 4→5 (Telecom). Stadium/subway/police hard maxes
    # are already respected by city_builds.db contents.
    caps = {
        "supermarket": 4,
        "hospital": _project_cap(nation, "clinical_research_center", 5),
        "recyclingcenter": _project_cap(nation, "recycling_initiative", 3),
        "bank": _project_cap(nation, "itc", 5),
        "mall": _project_cap(nation, "telecom_satellite", 4),
    }

    mmr_dict = {}
    if mmr.lower() != "any":
        mmr_dict = {
            "barracks": mmr_values[0],
            "factory": mmr_values[1],
            "airforcebase": mmr_values[2],
            "drydock": mmr_values[3],
        }

    rows = await asyncio.to_thread(
        db_utils.fetch_build_rows, db_path, infra, mmr_dict, caps, restricted_mines
    )
    if not rows:
        raise BuildInputError(f"No builds found for infrastructure {infra} with the given criteria")

    nation_age = nation.get("date", "")
    if "T" in nation_age:
        nation_age = nation_age[: nation_age.index("T")]

    # fetch_build_rows returns fresh dicts, so they are filled in place.
    to_scan = rows
    for city in to_scan:
        city["powered"] = "am powered"
        city["land"] = land
        city["date"] = nation_age

    # The game context and the 30-day prices don't depend on each other.
    (_, colors, prices, treasures, radiation, seasonal_mod), averaged_prices = await asyncio.gather(
        pre_revenue_calc(
            None,
            query_for_nation=False,
            parsed_nation=nation,
            call_func=call_pnw,
            get_query_func=get_query,
            queries_module=queries,
        ),
        _fetch_historical_prices(call_pnw),
    )

    live_prices = dict(prices)
    if averaged_prices:
        # If historical data is empty/zeroed out, fall back to live so UI never shows all zeros.
        non_money = [v for k, v in averaged_prices.items() if k != "money"]
        if not non_money or all(v == 0 for v in non_money):
            averaged_prices = dict(live_prices)

    # The 30-day average is used only when it was actually fetched; the response
    # reports the prices the builds were ranked with.
    price_mode = "average" if not use_live_prices and averaged_prices else "live"
    if price_mode == "average":
        for resource, value in averaged_prices.items():
            prices[resource] = value

    # Nation-wide values, computed once instead of once per candidate city.
    modifiers = calculate_nation_modifiers(nation)
    mil_cost_mod = float(modifiers.get("mil_cost", 1))
    peace_rates = unit_upkeep_rates(nation, at_war=False)
    war_rates = unit_upkeep_rates(nation, at_war=True)
    base_nation = dict(nation)

    cities: List[BuildDict] = await asyncio.to_thread(
        _score_build_cities_sync,
        base_nation=base_nation,
        to_scan=to_scan,
        radiation=radiation,
        treasures=treasures,
        prices=prices,
        colors=colors,
        seasonal_mod=seasonal_mod,
        modifiers=modifiers,
        treasure_bonus=calculate_treasure_bonus(nation, treasures),
        upkeep_rates=war_rates if selected_upkeep_mode == "war" else peace_rates,
        include_military_upkeep=include_military_upkeep,
        disable_population_income=disable_population_income,
    )

    if not cities:
        raise BuildInputError("No builds matched your criteria")

    # Ranking tens of thousands of builds is CPU work; keep it off the shared loop.
    unique_builds, builds = await asyncio.to_thread(_rank_builds_sync, cities, available_resources)
    for build in [*unique_builds[:100], *builds.values()]:
        if "unit_upkeep" not in build:
            build["unit_upkeep"] = _unit_upkeep_report(
                build["_max_units"],
                peace_rates=peace_rates,
                war_rates=war_rates,
                selected_mode=selected_upkeep_mode,
                mil_cost_mod=mil_cost_mod,
                included=include_military_upkeep,
            )

    food_rad_effect_mod = modifiers.get("food_rad_effect_mod", 1)
    radiation_value = radiation.get(continent_code, 0)
    seasonal_value = seasonal_mod.get(continent_code, 1)
    radiation_multiplier = 1 + radiation_value * food_rad_effect_mod
    food_multiplier = radiation_multiplier * seasonal_value

    total_unique_builds = len(unique_builds)
    displayed_unique_builds = min(total_unique_builds, 100)

    return {
        "builds": builds,
        "resources": available_resources,
        "land": land,
        "infrastructure": infra,
        "uniqueBuilds": unique_builds[:100],
        "totalUniqueBuilds": total_unique_builds,
        "displayedUniqueBuilds": displayed_unique_builds,
        "prices": {
            "mode": price_mode,
            "live": live_prices,
            "average30d": averaged_prices,
        },
        "nation": {
            "id": nation_id,
            "name": nation.get("nation_name"),
            "leader": nation.get("leader_name"),
        },
        "mmr": {
            "barracks": mmr_values[0],
            "factory": mmr_values[1],
            "airforcebase": mmr_values[2],
            "drydock": mmr_values[3],
        },
        "radiation": {
            "continent": continent_code,
            "raw": round(-1000 * radiation_value, 2),
            "value": radiation_value,
        },
        "foodModifiers": {
            "continent": continent_code,
            "seasonal": seasonal_value,
            "radiationMultiplier": radiation_multiplier,
            "combinedFoodMultiplier": food_multiplier,
        },
    }
