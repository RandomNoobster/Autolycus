from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from . import queries
from infra.cache import cache_historical_prices
from logic.merge_utils import get_query
from logic.revenue import (calculate_nation_modifiers, pre_revenue_calc,
                           revenue_calc, revenue_calc_sync)
from database import sqlite_cache as db_utils

logger = logging.getLogger(__name__)

BuildDict = Dict[str, Any]
GraphQLCaller = Callable[[str], Awaitable[dict[str, Any]]]


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
        for project_key in [
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
        ]:
            nation[project_key] = project_key in selected
    if dom_policy is not None:
        nation["dompolicy"] = dom_policy


def _max_units_from_city(city: BuildDict, population: float) -> Dict[str, int]:
    return {
        "soldiers": max(0, math.floor(min(3000 * city.get("barracks", 0), population / 6.67))),
        "tanks": max(0, math.floor(min(250 * city.get("factory", 0), population / 66.67))),
        "aircraft": max(0, math.floor(min(15 * city.get("airforcebase", 0), population / 1000))),
        "ships": max(0, math.floor(min(5 * city.get("drydock", 0), population / 10000))),
    }


def _unit_upkeep_for_max(
    max_units: Dict[str, int],
    *,
    at_war: bool,
    mil_cost_mod: float,
) -> tuple[float, float, Dict[str, float], Dict[str, float]]:
    rates = {
        "soldiers": 1.88 if at_war else 1.25,
        "tanks": 75 if at_war else 50,
        "aircraft": 1000 if at_war else 750,
        "ships": 5000 if at_war else 3300,
    }
    food_rates = {"soldiers": (1 / (500 if at_war else 750)), "tanks": 0, "aircraft": 0, "ships": 0}
    breakdown = {}
    food_breakdown = {}
    total = 0.0
    food = 0.0
    for unit, count in max_units.items():
        upkeep = count * rates[unit] * mil_cost_mod
        breakdown[unit] = upkeep
        total += upkeep
        unit_food = count * food_rates.get(unit, 0)
        food_breakdown[unit] = unit_food
        food += unit_food
    return total, food, breakdown, food_breakdown


def _freeze_value(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple((k, _freeze_value(v)) for k, v in sorted(value.items()))
    if isinstance(value, list):
        return tuple(_freeze_value(v) for v in value)
    return value


def _score_build_cities_sync(
    *,
    base_nation: dict[str, Any],
    to_scan: list[BuildDict],
    radiation: dict[str, float],
    treasures: list[dict[str, Any]],
    prices: dict[str, float],
    colors: dict[str, float],
    seasonal_mod: dict[str, float],
    selected_upkeep_mode: str,
    mil_cost_mod: float,
    include_military_upkeep: bool,
    disable_population_income: bool,
) -> list[BuildDict]:
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
        )

        population = revenue.get("population", 0)
        max_units = _max_units_from_city(city, population)
        peace_total, peace_food, peace_breakdown, peace_food_breakdown = _unit_upkeep_for_max(
            max_units,
            at_war=False,
            mil_cost_mod=mil_cost_mod,
        )
        war_total, war_food, war_breakdown, war_food_breakdown = _unit_upkeep_for_max(
            max_units,
            at_war=True,
            mil_cost_mod=mil_cost_mod,
        )

        resolved_mode = selected_upkeep_mode
        active_total, active_food, active_breakdown, active_food_breakdown = (
            (war_total, war_food, war_breakdown, war_food_breakdown)
            if resolved_mode == "war"
            else (peace_total, peace_food, peace_breakdown, peace_food_breakdown)
        )

        revenue["unit_upkeep"] = {
            "included": include_military_upkeep,
            "selectedMode": selected_upkeep_mode,
            "mode": resolved_mode,
            "total": round(active_total),
            "food": round(active_food, 4),
            "breakdown": {k: round(v) for k, v in active_breakdown.items()},
            "breakdownFood": {k: round(v, 4) for k, v in active_food_breakdown.items()},
            "counts": max_units,
            "modes": {
                "peace": {
                    "total": round(peace_total),
                    "food": round(peace_food, 4),
                    "breakdown": {k: round(v) for k, v in peace_breakdown.items()},
                    "breakdownFood": {k: round(v, 4) for k, v in peace_food_breakdown.items()},
                },
                "war": {
                    "total": round(war_total),
                    "food": round(war_food, 4),
                    "breakdown": {k: round(v) for k, v in war_breakdown.items()},
                    "breakdownFood": {k: round(v, 4) for k, v in war_food_breakdown.items()},
                },
            },
        }
        if include_military_upkeep:
            revenue["net income"] = revenue.get("net income", 0) - active_total
            revenue["net_cash_num"] = revenue.get("net_cash_num", 0) - active_total
            revenue["net income real"] = revenue.get("net income real", revenue.get("net income", 0)) - active_total
            revenue["net_cash_num_real"] = revenue.get("net_cash_num_real", revenue.get("net_cash_num", 0)) - active_total
        cities.append(revenue)

    return cities


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

# Backwards-compatible alias (historical name incorrectly implied "restricted").
_CONTINENT_RESTRICTIONS = _CONTINENT_AVAILABLE

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
    """Parse military requirement string into numeric tuple (barracks/factory/hangar/drydock)."""
    if mmr.lower() == "any":
        return (0, 0, 0, 0)

    parts = [part.strip() for part in mmr.split("/")]
    if len(parts) != 4:
        raise ValueError(f"Invalid MMR format: {mmr}")
    try:
        values = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise ValueError(f"Invalid MMR format: {mmr}") from exc
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
        "ironw": False,
        "bauxitew": False,
        "armss": False,
        "egr": False,
        "massirr": False,
        "itc": False,
        "telecom_satellite": False,
        "recycling_initiative": False,
        "green_tech": False,
        "clinical_research_center": False,
        "specialized_police_training": False,
        "uap": False,
        "fallout_shelter": False,
        "government_support_agency": False,
        "bureau_of_domestic_affairs": False,
    }


def generate_build_template(build: BuildDict) -> str:
    """Generate JSON template for the P&W city bulk import."""
    return (
        "{\n"
        f"    \"infra_needed\": {build['infrastructure']},\n"
        f"    \"imp_total\": {math.floor(float(build['infrastructure'])/50)},\n"
        f"    \"imp_coalpower\": {build['coalpower']},\n"
        f"    \"imp_oilpower\": {build['oilpower']},\n"
        f"    \"imp_windpower\": {build['windpower']},\n"
        f"    \"imp_nuclearpower\": {build['nuclearpower']},\n"
        f"    \"imp_coalmine\": {build['coalmine']},\n"
        f"    \"imp_oilwell\": {build['oilwell']},\n"
        f"    \"imp_uramine\": {build['uramine']},\n"
        f"    \"imp_leadmine\": {build['leadmine']},\n"
        f"    \"imp_ironmine\": {build['ironmine']},\n"
        f"    \"imp_bauxitemine\": {build['bauxitemine']},\n"
        f"    \"imp_farm\": {build['farm']},\n"
        f"    \"imp_gasrefinery\": {build['gasrefinery']},\n"
        f"    \"imp_aluminumrefinery\": {build['aluminumrefinery']},\n"
        f"    \"imp_steelmill\": {build['steelmill']},\n"
        f"    \"imp_munitionsfactory\": {build['munitionsfactory']},\n"
        f"    \"imp_policestation\": {build['policestation']},\n"
        f"    \"imp_hospital\": {build['hospital']},\n"
        f"    \"imp_recyclingcenter\": {build['recyclingcenter']},\n"
        f"    \"imp_subway\": {build['subway']},\n"
        f"    \"imp_supermarket\": {build['supermarket']},\n"
        f"    \"imp_bank\": {build['bank']},\n"
        f"    \"imp_mall\": {build['mall']},\n"
        f"    \"imp_stadium\": {build['stadium']},\n"
        f"    \"imp_barracks\": {build['barracks']},\n"
        f"    \"imp_factory\": {build['factory']},\n"
        f"    \"imp_hangars\": {build['airforcebase']},\n"
        f"    \"imp_drydock\": {build['drydock']}\n"
        "}"
    )


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
    except Exception:
        logger.exception("Failed to fetch historical prices")
        return None

    price_data = result.get("data", {}).get("tradeprices", {}).get("data", [])
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
    status_target: Optional[Any] = None,
) -> dict[str, Any]:
    """Calculate optimal city builds using shared game logic."""

    if nation is None and nation_id is not None:
        query = "{" f"nations(first:1 id:{nation_id})" "{data" f"{get_query(queries.REVENUE)}" "}}"  # noqa: E501
        response = await call_pnw(query)
        nation_list = response.get("data", {}).get("nations", {}).get("data", [])
        if not nation_list:
            raise ValueError(f"Nation {nation_id} not found in API")
        nation = nation_list[0]
        nation_id = str(nation.get("id"))
    elif nation is not None:
        nation_id = str(nation.get("id")) if nation.get("id") is not None else nation_id
    else:
        # Manual configuration: no real nation — use a neutral baseline.
        if infra is None or land is None:
            raise ValueError("infra and land are required when nation_id is not provided")
        continent_code_for_manual = normalize_continent_code(continent_override or "na") or "na"
        nation = _neutral_manual_nation(continent_code_for_manual)
        nation_id = "0"

    if nation is None:
        raise ValueError("Nation data unavailable after fetch")

    if infra is None:
        total_infra = sum(city.get("infrastructure", 0) for city in nation.get("cities", []))
        infra = round(total_infra / max(nation.get("num_cities", 1), 1) / 50) * 50

    # P&W city improvement capacity is based on completed 50-infra chunks.
    # Normalize user-provided infra to the largest valid chunk the city can actually support.
    if infra % 50 != 0:
        normalized_infra = (infra // 50) * 50
        if normalized_infra <= 0:
            raise ValueError("Infrastructure must be at least 50")
        logger.info(
            "Normalizing non-multiple infrastructure from %s to %s for build lookup",
            infra,
            normalized_infra,
        )
        infra = normalized_infra

    if land is None:
        total_land = sum(city.get("land", 0) for city in nation.get("cities", []))
        land = round(total_land / max(nation.get("num_cities", 1), 1))

    try:
        mmr_values = parse_mmr(mmr)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

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
        raise ValueError(
            "military_upkeep_mode must be one of: peace, war"
        )

    db_path = db_utils.get_builds_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Builds database not found at {db_path}")

    caps = {
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
        raise ValueError(f"No builds found for infrastructure {infra} with the given criteria")

    nation_age = nation.get("date", "")
    if "T" in nation_age:
        nation_age = nation_age[: nation_age.index("T")]

    to_scan = []
    for row in rows:
        city = dict(row)
        city["powered"] = "am powered"
        city["land"] = land
        city["date"] = nation_age
        to_scan.append(city)

    _, colors, prices, treasures, radiation, seasonal_mod = await pre_revenue_calc(
        status_target,
        query_for_nation=False,
        parsed_nation=nation,
        call_func=call_pnw,
        get_query_func=get_query,
        queries_module=queries,
    )

    live_prices = dict(prices)
    averaged_prices = await _fetch_historical_prices(call_pnw)
    if averaged_prices:
        # If historical data is empty/zeroed out, fall back to live so UI never shows all zeros.
        non_money = [v for k, v in averaged_prices.items() if k != "money"]
        if not non_money or all(v == 0 for v in non_money):
            averaged_prices = dict(live_prices)

    if not use_live_prices:
        if averaged_prices:
            for resource, value in averaged_prices.items():
                prices[resource] = value

    modifiers = calculate_nation_modifiers(nation)
    mil_cost_mod = float(modifiers.get("mil_cost", 1))
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
        selected_upkeep_mode=selected_upkeep_mode,
        mil_cost_mod=mil_cost_mod,
        include_military_upkeep=include_military_upkeep,
        disable_population_income=disable_population_income,
    )

    if not cities:
        raise ValueError("No builds matched your criteria")

    improvement_fields = db_utils.IMPROVEMENT_FIELDS
    unique_keys = set()
    unique_builds: List[BuildDict] = []
    for city in cities:
        key = tuple(city.get(field, 0) for field in improvement_fields)
        if key not in unique_keys:
            unique_keys.add(key)
            unique_builds.append(city)

    unique_builds.sort(key=lambda build: build.get("net income", 0), reverse=True)

    builds: Dict[str, BuildDict] = {}
    top_builds: List[BuildDict] = []
    for resource in available_resources:
        sorted_builds = sorted(unique_builds, key=lambda build: build.get(resource, 0), reverse=True)
        if not sorted_builds:
            continue
        best_value = sorted_builds[0].get(resource, 0)
        best_builds = [b for b in sorted_builds if b.get(resource, 0) == best_value]
        top_builds.extend(best_builds[:20])
        winner = sorted(best_builds, key=lambda build: build.get("net income", 0), reverse=True)[0]
        winner["template"] = generate_build_template(winner)
        builds[resource] = winner

    # Deduplicate top builds while preserving dict structure
    seen = set()
    top_unique_builds: List[BuildDict] = []
    for build in top_builds:
        frozen = _freeze_value(build)
        if frozen not in seen:
            seen.add(frozen)
            top_unique_builds.append(build)

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
        "topUniqueBuilds": top_unique_builds,
        "prices": {
            "mode": "live" if use_live_prices else "average",
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
