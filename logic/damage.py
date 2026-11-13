from __future__ import annotations

import copy
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from . import queries
from logic import economy as economy_logic
from logic.common import normalize_war_type, weird_division
from logic.merge_utils import get_query
from logic.military import calculate_win_chance_raw, unit_buy_costs

logger = logging.getLogger(__name__)

GraphQLCaller = Callable[[str], Awaitable[dict[str, Any]]]


class NationsNotFoundError(ValueError):
    """One or both nations of a damage calculation do not exist."""


# Share of the potential infra damage and loot each side of a war gets, as
# (declarer, defender), by war type (PWPedia Raid-War / Ordinary-War / Attrition-War).
_WAR_TYPE_MODS: Dict[str, Dict[str, tuple[float, float]]] = {
    "RAID": {"infra": (0.25, 0.5), "loot": (1.0, 1.0)},
    "ORDINARY": {"infra": (0.5, 0.5), "loot": (0.5, 0.5)},
    "ATTRITION": {"infra": (1.0, 1.0), "loot": (0.25, 0.5)},
}

# Market prices used to value resources in the damage totals.
_PRICES = {"aluminum": 2971, "steel": 3990, "gasoline": 3340, "munitions": 1960, "uranium": 3039}
_TOTAL_RESOURCES = (("alum", "aluminum"), ("steel", "steel"), ("gas", "gasoline"), ("mun", "munitions"), ("uranium", "uranium"))


def _cost_total(results: Dict[str, Any], prefix: str, *, gas_mun_prefix: Optional[str] = None) -> float:
    """Money plus the market value of the resources recorded under ``{prefix}_*``.

    Air attacks record gasoline and munitions once under ``gas_mun_prefix``.
    """
    total = results[f"{prefix}_money"]
    for key, resource in _TOTAL_RESOURCES:
        source = gas_mun_prefix if gas_mun_prefix and key in ("gas", "mun") else prefix
        total += results.get(f"{source}_{key}", 0) * _PRICES[resource]
    return total


async def calculate_damage(
    *,
    call_pnw: GraphQLCaller,
    nation1_id: Optional[str] = None,
    nation2_id: Optional[str] = None,
    nation1: Optional[dict[str, Any]] = None,
    nation2: Optional[dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Calculate war damage outcomes between two nations.

    Per PWPedia "War-Mechanics" article; this centralizes all combat math so
    API and Discord layers only orchestrate data retrieval and presentation.

    Args:
        call_pnw: Coroutine factory to execute Politics & War GraphQL queries.
        nation1_id: Optional ID for the first nation if not pre-fetched.
        nation2_id: Optional ID for the second nation if not pre-fetched.
        nation1: Optional nation payload matching BATTLE_CALC shape.
        nation2: Optional nation payload matching BATTLE_CALC shape.

    Returns:
        Dictionary containing populated damage calculator values.

    Raises:
        ValueError: If required identifiers are missing or inputs conflict.
    """

    if nation1 and nation1_id:
        raise ValueError("Provide either nation1 or nation1_id, not both")
    if nation2 and nation2_id:
        raise ValueError("Provide either nation2 or nation2_id, not both")
    if not nation1 and not nation1_id:
        raise ValueError("nation1 or nation1_id is required")
    if not nation2 and not nation2_id:
        raise ValueError("nation2 or nation2_id is required")

    results: Dict[str, Any] = {}

    if nation1:
        results["nation1"] = nation1
        nation1_id = str(nation1["id"])
    if nation2:
        results["nation2"] = nation2
        nation2_id = str(nation2["id"])

    ids_to_fetch: list[str] = []
    if nation1_id and "nation1" not in results:
        ids_to_fetch.append(str(nation1_id))
    if nation2_id and "nation2" not in results:
        ids_to_fetch.append(str(nation2_id))

    if ids_to_fetch:
        query = (
            "{"
            f"nations(id:[{','.join(sorted(set(ids_to_fetch)))}])"
            "{data"
            f"{get_query(queries.DAMAGE_CALC)}"
            "}}"
        )
        response = await call_pnw(query)
        nation_list = ((response.get("data") or {}).get("nations") or {}).get("data") or []
        for nation in nation_list:
            nid = str(nation["id"])
            # Fill only the slots that were fetched; a caller-supplied nation stays.
            if nid == nation1_id and "nation1" not in results:
                results["nation1"] = nation
            if nid == nation2_id and "nation2" not in results:
                results["nation2"] = nation

    if "nation1" not in results or "nation2" not in results:
        raise NationsNotFoundError("Could not retrieve both nations for damage calculation")
    if results["nation1"] is results["nation2"]:
        # A nation against itself: each side gets its own dict to annotate.
        results["nation2"] = copy.deepcopy(results["nation1"])

    results.setdefault("nation1_append", "")
    results.setdefault("nation2_append", "")
    results["nation1_tanks"] = results["nation2_tanks"] = 1
    results["nation1_extra_cas"] = results["nation2_extra_cas"] = 1
    results["gc"] = None
    results["nation1_war_infra_mod"] = results["nation2_war_infra_mod"] = 0.5
    results["nation1_war_loot_mod"] = results["nation2_war_loot_mod"] = 0.5

    for nation_key in ("nation1", "nation2"):
        use_munitions = results[nation_key].get("soldiers_use_munitions", True)
        results[f"{nation_key}_soldiers_use_munitions"] = bool(use_munitions)
        results[f"{nation_key}_soldier_munition_mod"] = 1.75 if use_munitions else 1.0

    nation1_id = str(results["nation1"]["id"])
    nation2_id = str(results["nation2"]["id"])

    for war in results["nation1"].get("wars", []):
        if war["attid"] == nation2_id and war["turnsleft"] > 0 and war["defid"] == nation1_id:
            _apply_war_state(results, war, attacker="nation2", defender="nation1")
        elif war["defid"] == nation2_id and war["turnsleft"] > 0 and war["attid"] == nation1_id:
            _apply_war_state(results, war, attacker="nation1", defender="nation2")

    for attacker, defender in [("nation1", "nation2"), ("nation2", "nation1")]:
        _calculate_win_rates(results, attacker, defender)
        _calculate_casualties(results, attacker, defender)

    for attacker, defender in [("nation1", "nation2"), ("nation2", "nation1")]:
        _apply_policy_modifiers(results, attacker)

    results["nation1"]["city"] = _highest_infra_city(results["nation1"].get("cities", []))
    results["nation2"]["city"] = _highest_infra_city(results["nation2"].get("cities", []))

    for attacker, defender in [("nation1", "nation2"), ("nation2", "nation1")]:
        _calculate_damage_numbers(results, attacker, defender)

    return results


def _apply_war_state(results: Dict[str, Any], war: Dict[str, Any], *, attacker: str, defender: str) -> None:
    att_id = results[attacker]["id"]
    def_id = results[defender]["id"]

    if war["groundcontrol"] == att_id:
        results["gc"] = results[attacker]
        results[f"{attacker}_append"] += "<:small_gc:924988666613489685>"
    elif war["groundcontrol"] == def_id:
        results["gc"] = results[defender]
        results[f"{defender}_append"] += "<:small_gc:924988666613489685>"

    if war["airsuperiority"] == att_id:
        results[f"{defender}_tanks"] = 0.5
        results[f"{attacker}_append"] += "<:small_air:924988666810601552>"
    elif war["airsuperiority"] == def_id:
        results[f"{attacker}_tanks"] = 0.5
        results[f"{defender}_append"] += "<:small_air:924988666810601552>"

    if war["navalblockade"] == att_id:
        results[f"{defender}_append"] += "<:small_blockade:924988666814808114>"
    elif war["navalblockade"] == def_id:
        results[f"{attacker}_append"] += "<:small_blockade:924988666814808114>"

    if war["att_fortify"]:
        results[f"{attacker}_append"] += "<:fortified:925465012955385918>"
        results[f"{defender}_extra_cas"] = 1.25
    if war["def_fortify"]:
        results[f"{defender}_append"] += "<:fortified:925465012955385918>"
        results[f"{attacker}_extra_cas"] = 1.25

    if war["attpeace"]:
        results[f"{attacker}_append"] += "<:peace:926855240655990836>"
    elif war["defpeace"]:
        results[f"{defender}_append"] += "<:peace:926855240655990836>"

    # `attacker` declared the war; the mods scale what each side deals and loots.
    mods = _WAR_TYPE_MODS.get(normalize_war_type(war.get("war_type")))
    if mods:
        results[f"{attacker}_war_infra_mod"], results[f"{defender}_war_infra_mod"] = mods["infra"]
        results[f"{attacker}_war_loot_mod"], results[f"{defender}_war_loot_mod"] = mods["loot"]


def _calculate_win_rates(results: Dict[str, Any], attacker: str, defender: str) -> None:
    # Each roll draws 40-100% of the raw army value (PWPedia Ground Battles,
    # Airstrike, Naval Battles); the same values the raids page uses.
    defender_army_value = (
        results[defender]["soldiers"] * results.get(f"{defender}_soldier_munition_mod", 1.75)
        + results[defender]["population"] * 0.0025
        + results[defender]["tanks"] * 40 * results[f"{defender}_tanks"]
    )
    attacker_army_value = (
        results[attacker]["soldiers"] * results.get(f"{attacker}_soldier_munition_mod", 1.75)
        + results[attacker]["tanks"] * 40 * results[f"{attacker}_tanks"]
    )
    results[f"{attacker}_ground_win_rate"] = calculate_win_chance_raw(attacker_army_value, defender_army_value)
    results[f"{attacker}_air_win_rate"] = calculate_win_chance_raw(
        results[attacker]["aircraft"] * 3, results[defender]["aircraft"] * 3
    )
    results[f"{attacker}_naval_win_rate"] = calculate_win_chance_raw(
        results[attacker]["ships"] * 4, results[defender]["ships"] * 4
    )

    for prefix, winrate in [
        ("ground", results[f"{attacker}_ground_win_rate"]),
        ("air", results[f"{attacker}_air_win_rate"]),
        ("naval", results[f"{attacker}_naval_win_rate"]),
    ]:
        results[f"{attacker}_{prefix}_it"] = winrate ** 3
        results[f"{attacker}_{prefix}_mod"] = winrate ** 2 * (1 - winrate) * 3
        results[f"{attacker}_{prefix}_pyr"] = winrate * (1 - winrate) ** 2 * 3
        results[f"{attacker}_{prefix}_fail"] = (1 - winrate) ** 3


def _calculate_casualties(results: Dict[str, Any], attacker: str, defender: str) -> None:
    attacker_soldiers_value = (
        results[attacker]["soldiers"] * results.get(f"{attacker}_soldier_munition_mod", 1.75)
    ) ** (3 / 4)
    defender_soldiers_value = (
        results[defender]["soldiers"] * results.get(f"{defender}_soldier_munition_mod", 1.75)
        + results[defender]["population"] * 0.0025
    ) ** (3 / 4)
    attacker_tanks_value = (results[attacker]["tanks"] * 40 * results[f"{attacker}_tanks"]) ** (3 / 4)
    defender_tanks_value = (results[defender]["tanks"] * 40 * results[f"{defender}_tanks"]) ** (3 / 4)
    attacker_aircraft_value = (results[attacker]["aircraft"] * 3) ** (3 / 4)
    defender_aircraft_value = (results[defender]["aircraft"] * 3) ** (3 / 4)
    attacker_ships_value = (results[attacker]["ships"] * 4) ** (3 / 4)
    defender_ships_value = (results[defender]["ships"] * 4) ** (3 / 4)

    attacker_casualties_soldiers = weird_division(
        attacker_soldiers_value ** (4 / 3) + defender_soldiers_value ** (4 / 3),
        attacker_soldiers_value + defender_soldiers_value,
    ) * attacker_soldiers_value
    defender_casualties_soldiers = weird_division(
        attacker_soldiers_value ** (4 / 3) + defender_soldiers_value ** (4 / 3),
        attacker_soldiers_value + defender_soldiers_value,
    ) * defender_soldiers_value

    attacker_casualties_tanks = weird_division(
        attacker_tanks_value ** (4 / 3) + defender_tanks_value ** (4 / 3),
        attacker_tanks_value + defender_tanks_value,
    ) * attacker_tanks_value
    defender_casualties_tanks = weird_division(
        attacker_tanks_value ** (4 / 3) + defender_tanks_value ** (4 / 3),
        attacker_tanks_value + defender_tanks_value,
    ) * defender_tanks_value

    attacker_casualties_aircraft = weird_division(
        attacker_aircraft_value ** (4 / 3) + defender_aircraft_value ** (4 / 3),
        attacker_aircraft_value + defender_aircraft_value,
    ) * attacker_aircraft_value
    defender_casualties_aircraft = weird_division(
        attacker_aircraft_value ** (4 / 3) + defender_aircraft_value ** (4 / 3),
        attacker_aircraft_value + defender_aircraft_value,
    ) * defender_aircraft_value

    attacker_casualties_ships = weird_division(
        attacker_ships_value ** (4 / 3) + defender_ships_value ** (4 / 3),
        attacker_ships_value + defender_ships_value,
    ) * attacker_ships_value
    defender_casualties_ships = weird_division(
        attacker_ships_value ** (4 / 3) + defender_ships_value ** (4 / 3),
        attacker_ships_value + defender_ships_value,
    ) * defender_ships_value

    if results.get("gc") == results[attacker]:
        avg_air = round(min(results[attacker]["tanks"] * 0.005 * results[f"{attacker}_ground_win_rate"] ** 3, results[defender]["aircraft"]))
        results[f"{attacker}_ground_{defender}_avg_aircraft"] = avg_air
        results[defender]["aircas"] = f"Def. Plane: {avg_air} ± {round(results[attacker]['tanks'] * 0.005 * (1 - results[f'{attacker}_ground_win_rate'] ** 3))}"
    else:
        results[defender]["aircas"] = ""
        results[f"{attacker}_ground_{defender}_avg_aircraft"] = 0

    # A fortified defender makes the attacker suffer 25% more casualties (PWPedia Fortify).
    extra_cas = results[f"{attacker}_extra_cas"]
    for label, modifier in [("avg", 0.7), ("diff", 0.3)]:
        results[f"{attacker}_ground_{attacker}_{label}_soldiers"] = min(
            round(((defender_casualties_soldiers * 0.0084) + (defender_casualties_tanks * 0.0092)) * modifier * 3 * extra_cas),
            results[attacker]["soldiers"],
        )
        # Both roll outcomes use the defending rolls; only the coefficients differ.
        results[f"{attacker}_ground_{attacker}_{label}_tanks"] = min(
            round(
                (
                    ((defender_casualties_soldiers * 0.0004060606) + (defender_casualties_tanks * 0.00066666666))
                    * results[f"{attacker}_ground_win_rate"]
                    + ((defender_casualties_soldiers * 0.00043225806) + (defender_casualties_tanks * 0.00070967741))
                    * (1 - results[f"{attacker}_ground_win_rate"])
                )
                * modifier
                * 3
                * extra_cas
            ),
            results[attacker]["tanks"],
        )
        results[f"{attacker}_ground_{defender}_{label}_soldiers"] = min(
            round(((attacker_casualties_soldiers * 0.0084) + (attacker_casualties_tanks * 0.0092)) * modifier * 3),
            results[defender]["soldiers"],
        )
        results[f"{attacker}_ground_{defender}_{label}_tanks"] = min(
            round(
                (
                    ((attacker_casualties_soldiers * 0.00043225806) + (attacker_casualties_tanks * 0.00070967741))
                    * results[f"{attacker}_ground_win_rate"]
                    + ((attacker_casualties_soldiers * 0.0004060606) + (attacker_casualties_tanks * 0.00066666666))
                    * (1 - results[f"{attacker}_ground_win_rate"])
                )
                * modifier
                * 3
            ),
            results[defender]["tanks"],
        )

    results[f"{attacker}_airvair_{attacker}_avg"] = min(
        round(defender_casualties_aircraft * 0.7 * 0.01 * 3 * extra_cas),
        results[attacker]["aircraft"],
    )
    results[f"{attacker}_airvair_{attacker}_diff"] = min(
        round(defender_casualties_aircraft * 0.3 * 0.01 * 3 * extra_cas),
        results[attacker]["aircraft"],
    )
    results[f"{attacker}_airvother_{attacker}_avg"] = min(
        round(defender_casualties_aircraft * 0.7 * 0.015385 * 3 * extra_cas),
        results[attacker]["aircraft"],
    )
    results[f"{attacker}_airvother_{attacker}_diff"] = min(
        round(defender_casualties_aircraft * 0.3 * 0.015385 * 3 * extra_cas),
        results[attacker]["aircraft"],
    )

    results[f"{attacker}_airvair_{defender}_avg"] = min(
        round(attacker_casualties_aircraft * 0.7 * 0.018337 * 3),
        results[defender]["aircraft"],
    )
    results[f"{attacker}_airvair_{defender}_diff"] = min(
        round(attacker_casualties_aircraft * 0.3 * 0.018337 * 3),
        results[defender]["aircraft"],
    )
    results[f"{attacker}_airvother_{defender}_avg"] = min(
        round(attacker_casualties_aircraft * 0.7 * 0.009091 * 3),
        results[defender]["aircraft"],
    )
    results[f"{attacker}_airvother_{defender}_diff"] = min(
        round(attacker_casualties_aircraft * 0.3 * 0.009091 * 3),
        results[defender]["aircraft"],
    )

    results[f"{attacker}_navalvinfra_{defender}_avg"] = min(
        round(attacker_casualties_ships * 0.7 * 0.009625 * 3),
        results[defender]["ships"],
    )
    results[f"{attacker}_navalvinfra_{defender}_diff"] = min(
        round(attacker_casualties_ships * 0.3 * 0.009625 * 3),
        results[defender]["ships"],
    )
    results[f"{attacker}_navalvinfra_{attacker}_avg"] = min(
        round(defender_casualties_ships * 0.7 * 0.009625 * 3 * extra_cas),
        results[attacker]["ships"],
    )
    results[f"{attacker}_navalvinfra_{attacker}_diff"] = min(
        round(defender_casualties_ships * 0.3 * 0.009625 * 3 * extra_cas),
        results[attacker]["ships"],
    )

    results[f"{attacker}_navalvships_{defender}_avg"] = min(
        round(attacker_casualties_ships * 0.7 * 0.017875 * 3),
        results[defender]["ships"],
    )
    results[f"{attacker}_navalvships_{defender}_diff"] = min(
        round(attacker_casualties_ships * 0.3 * 0.017875 * 3),
        results[defender]["ships"],
    )
    results[f"{attacker}_navalvships_{attacker}_avg"] = min(
        round(defender_casualties_ships * 0.7 * 0.017875 * 3 * extra_cas),
        results[attacker]["ships"],
    )
    results[f"{attacker}_navalvships_{attacker}_diff"] = min(
        round(defender_casualties_ships * 0.3 * 0.017875 * 3 * extra_cas),
        results[attacker]["ships"],
    )


def _apply_policy_modifiers(results: Dict[str, Any], nation_key: str) -> None:
    results[f"{nation_key}_policy_infra_dealt"] = 1
    results[f"{nation_key}_policy_loot_stolen"] = 1
    results[f"{nation_key}_policy_infra_lost"] = 1
    results[f"{nation_key}_policy_loot_lost"] = 1
    results[f"{nation_key}_vds_mod"] = 1
    results[f"{nation_key}_irond_mod"] = 1
    results[f"{nation_key}_fallout_shelter_mod"] = 1
    results[f"{nation_key}_guiding_satellite_mod"] = 1
    results[f"{nation_key}_military_salvage_mod"] = 0
    results[f"{nation_key}_pirate_econ_loot"] = 1
    results[f"{nation_key}_advanced_pirate_econ_loot"] = 1

    policy = results[nation_key].get("warpolicy")
    if policy == "Attrition":
        results[f"{nation_key}_policy_infra_dealt"] = 1.1
        results[f"{nation_key}_policy_loot_stolen"] = 0.8
    elif policy == "Turtle":
        results[f"{nation_key}_policy_infra_lost"] = 0.9
        results[f"{nation_key}_policy_loot_lost"] = 1.2
    elif policy == "Moneybags":
        results[f"{nation_key}_policy_infra_lost"] = 1.05
        results[f"{nation_key}_policy_loot_lost"] = 0.6
    elif policy == "Pirate":
        results[f"{nation_key}_policy_loot_stolen"] = 1.4
    elif policy == "Guardian":
        results[f"{nation_key}_policy_loot_lost"] = 1.2
    elif policy == "Covert":
        results[f"{nation_key}_policy_infra_lost"] = 1.05
    elif policy == "Arcane":
        results[f"{nation_key}_policy_infra_lost"] = 1.05

    if results[nation_key].get("vds"):
        results[f"{nation_key}_vds_mod"] = 0.75
    if results[nation_key].get("irond"):
        results[f"{nation_key}_irond_mod"] = 0.7
    if results[nation_key].get("fallout_shelter"):
        results[f"{nation_key}_fallout_shelter_mod"] = 0.9
    if results[nation_key].get("guiding_satellite"):
        results[f"{nation_key}_guiding_satellite_mod"] = 1.2
    if results[nation_key].get("military_salvage"):
        results[f"{nation_key}_military_salvage_mod"] = 1
    # Pirate Economy and Advanced Pirate Economy each add 5% ground-attack loot
    # (.ctx/projects_canon.md); APE's extra 10% applies to victory loot only.
    if results[nation_key].get("pirate_economy"):
        results[f"{nation_key}_pirate_econ_loot"] = 1.05
    if results[nation_key].get("advanced_pirate_economy"):
        results[f"{nation_key}_advanced_pirate_econ_loot"] = 1.05


def _highest_infra_city(cities: list[dict[str, Any]]) -> dict[str, Any]:
    if not cities:
        return {"infrastructure": 0, "land": 0}
    return sorted(cities, key=lambda city: city.get("infrastructure", 0), reverse=True)[0]


def _defender_consumption(winrate: float) -> float:
    try:
        p_fail = (1 - winrate) ** 3
        p_pyrr = 3 * winrate * (1 - winrate) ** 2
        p_mod = 3 * winrate ** 2 * (1 - winrate)
        p_imm = winrate ** 3
        return (p_fail * 0.40) + (p_pyrr * 0.75) + (p_mod * 0.95) + (p_imm * 1.00)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to compute defender consumption factor")
        return 0.4


def _salvage(results: Dict[str, Any], attacker: str, winrate: float, resources: float) -> float:
    return resources * (results.get(f"{attacker}_military_salvage_mod", 0) * (winrate ** 3) * 0.05)


def _battle_infra(
    results: Dict[str, Any], attacker: str, defender: str, *, raw: float, cap: float, win_rate: float
) -> float:
    """Expected infra one battle destroys, after war-type and war-policy modifiers.

    PWPedia: ``MAX(MIN(raw * RAND(0.85, 1.05) * VictoryType / 3, cap), 0)``; the
    random factor averages 0.95 and VictoryType / 3 averages the per-roll win rate.
    """
    return (
        max(min(raw * 0.95 * win_rate, cap), 0)
        * results[f"{attacker}_war_infra_mod"]
        * results[f"{attacker}_policy_infra_dealt"]
        * results[f"{defender}_policy_infra_lost"]
    )


def _calculate_damage_numbers(results: Dict[str, Any], attacker: str, defender: str) -> None:
    att = results[attacker]
    dfn = results[defender]
    # Lost units are valued at their owner's buy cost after Efficiency research.
    att_cost = unit_buy_costs(att)
    dfn_cost = unit_buy_costs(dfn)
    city_infra = dfn["city"]["infrastructure"]
    city_land = dfn["city"]["land"]
    ground_win_rate = results[f"{attacker}_ground_win_rate"]
    air_win_rate = results[f"{attacker}_air_win_rate"]
    naval_win_rate = results[f"{attacker}_naval_win_rate"]
    def_rss = _defender_consumption(ground_win_rate)

    # Infra loss calculations
    results[f"{attacker}_ground_{defender}_lost_infra_avg"] = _battle_infra(
        results, attacker, defender,
        raw=(att["soldiers"] - dfn["soldiers"] * 0.5) * 0.000606061 + (att["tanks"] - dfn["tanks"] * 0.5) * 0.01,
        cap=city_infra * 0.2 + 25,
        win_rate=ground_win_rate,
    )

    results[f"{attacker}_ground_loot_avg"] = (
        (att["soldiers"] * 1.1 + att["tanks"] * 25.15)
        * ground_win_rate
        * 3
        * 0.95
        * results[f"{attacker}_war_loot_mod"]
        * results[f"{attacker}_policy_loot_stolen"]
        * results[f"{defender}_policy_loot_lost"]
        * results[f"{attacker}_pirate_econ_loot"]
        * results[f"{attacker}_advanced_pirate_econ_loot"]
    )

    results[f"{attacker}_air_{defender}_lost_infra_avg"] = _battle_infra(
        results, attacker, defender,
        raw=(att["aircraft"] - dfn["aircraft"] * 0.5) * 0.35353535,
        cap=city_infra * 0.5 + 100,
        win_rate=air_win_rate,
    )

    air_strength = att["aircraft"] - dfn["aircraft"] * 0.5
    for unit, cap_bonus, per_plane in (("soldiers", 1000, 35), ("tanks", 10, 1.25), ("ships", 4, 0.0285)):
        results[f"{attacker}_air_{defender}_{unit}_destroyed_avg"] = round(
            max(min(dfn[unit], dfn[unit] * 0.75 + cap_bonus, air_strength * per_plane * 0.95), 0)
        ) * _defender_consumption(air_win_rate)

    # PWPedia Naval Battles: attacking ships minus half the defending ships.
    naval_strength = att["ships"] - dfn["ships"] * 0.5
    for tactic, per_ship in (("navalvinfra", 2.625), ("navalvships", 1.8375)):
        results[f"{attacker}_{tactic}_{defender}_lost_infra_avg"] = _battle_infra(
            results, attacker, defender,
            raw=naval_strength * per_ship,
            cap=city_infra * 0.5 + 25,
            win_rate=naval_win_rate,
        )

    results[f"{attacker}_nuke_{defender}_lost_infra_avg"] = max(
        min(
            (1700 + max(2000, city_infra * 100 / city_land * 13.5)) / 2,
            city_infra * 0.8 + 150,
        ),
        0,
    ) * results[f"{attacker}_war_infra_mod"] * results[f"{attacker}_policy_infra_dealt"] * results[f"{defender}_policy_infra_lost"] * results[f"{defender}_fallout_shelter_mod"] * results[f"{attacker}_guiding_satellite_mod"]

    results[f"{attacker}_missile_{defender}_lost_infra_avg"] = max(
        min(
            (300 + max(350, city_infra * 100 / city_land * 3)) / 2,
            city_infra * 0.3 + 100,
        ),
        0,
    ) * results[f"{attacker}_war_infra_mod"] * results[f"{attacker}_policy_infra_dealt"] * results[f"{defender}_policy_infra_lost"] * results[f"{attacker}_guiding_satellite_mod"]

    for attack in ("ground", "air", "navalvinfra", "navalvships", "nuke", "missile"):
        key = f"{attacker}_{attack}_{defender}_lost_infra"
        if attack == "missile":
            mod = results[f"{defender}_irond_mod"]
        elif attack == "nuke":
            mod = results[f"{defender}_vds_mod"]
        else:
            mod = 1
        results[f"{key}_avg_value"] = economy_logic.infra_rebuild_cost(city_infra, results[f"{key}_avg"]) * mod

    for attack in ["airvair", "airvsoldiers", "airvtanks", "airvships"]:
        results[f"{attacker}_{attack}_{defender}_lost_infra_avg_value"] = (
            results[f"{attacker}_air_{defender}_lost_infra_avg_value"] * 1 / 3
        )
    results[f"{attacker}_airvinfra_{defender}_lost_infra_avg_value"] = (
        results[f"{attacker}_air_{defender}_lost_infra_avg_value"]
    )

    # Ground resource consumption
    attacker_munition_factor = 1 if results.get(f"{attacker}_soldiers_use_munitions", True) else 0
    defender_munition_factor = 1 if results.get(f"{defender}_soldiers_use_munitions", True) else 0

    results[f"{attacker}_ground_{attacker}_mun"] = (
        att["soldiers"] * 0.0002 * attacker_munition_factor + att["tanks"] * 0.01
    )
    results[f"{attacker}_ground_{attacker}_gas"] = att["tanks"] * 0.01
    results[f"{attacker}_ground_{attacker}_alum"] = 0
    results[f"{attacker}_ground_{attacker}_steel"] = (
        results[f"{attacker}_ground_{attacker}_avg_tanks"] * att_cost["tanks"]["steel"]
        - _salvage(results, attacker, ground_win_rate, results[f"{attacker}_ground_{attacker}_avg_tanks"] * att_cost["tanks"]["steel"])
        - _salvage(results, attacker, ground_win_rate, results[f"{attacker}_ground_{defender}_avg_tanks"] * dfn_cost["tanks"]["steel"])
    )
    results[f"{attacker}_ground_{attacker}_money"] = (
        -results[f"{attacker}_ground_loot_avg"]
        + results[f"{attacker}_ground_{attacker}_avg_tanks"] * att_cost["tanks"]["money"]
        + results[f"{attacker}_ground_{attacker}_avg_soldiers"] * att_cost["soldiers"]["money"]
    )
    results[f"{attacker}_ground_{attacker}_total"] = _cost_total(results, f"{attacker}_ground_{attacker}")

    base_mun = (
        dfn["soldiers"] * 0.0002 * defender_munition_factor
        + dfn["population"] / 2_000_000
        + dfn["tanks"] * 0.01
    ) * def_rss
    results[f"{attacker}_ground_{defender}_mun"] = (
        base_mun * (1 - results[f"{attacker}_ground_fail"])
        + min(base_mun, results[f"{attacker}_ground_{attacker}_mun"]) * results[f"{attacker}_ground_fail"]
    )
    base_gas = dfn["tanks"] * 0.01 * def_rss
    results[f"{attacker}_ground_{defender}_gas"] = (
        base_gas * (1 - results[f"{attacker}_ground_fail"])
        + min(base_gas, results[f"{attacker}_ground_{attacker}_gas"]) * results[f"{attacker}_ground_fail"]
    )
    results[f"{attacker}_ground_{defender}_alum"] = results[f"{attacker}_ground_{defender}_avg_aircraft"] * dfn_cost["aircraft"]["aluminum"]
    results[f"{attacker}_ground_{defender}_steel"] = results[f"{attacker}_ground_{defender}_avg_tanks"] * dfn_cost["tanks"]["steel"]
    results[f"{attacker}_ground_{defender}_money"] = (
        results[f"{attacker}_ground_loot_avg"]
        + results[f"{attacker}_ground_{defender}_avg_aircraft"] * dfn_cost["aircraft"]["money"]
        + results[f"{attacker}_ground_{defender}_avg_tanks"] * dfn_cost["tanks"]["money"]
        + results[f"{attacker}_ground_{defender}_avg_soldiers"] * dfn_cost["soldiers"]["money"]
        + results[f"{attacker}_ground_{defender}_lost_infra_avg_value"]
    )
    results[f"{attacker}_ground_{defender}_total"] = _cost_total(results, f"{attacker}_ground_{defender}")
    results[f"{attacker}_ground_net"] = (
        results[f"{attacker}_ground_{defender}_total"] - results[f"{attacker}_ground_{attacker}_total"]
    )

    for attack in ["air", "airvair", "airvinfra", "airvsoldiers", "airvtanks", "airvships"]:
        results[f"{attacker}_{attack}_{attacker}_gas"] = (
            results[f"{attacker}_{attack}_{attacker}_mun"]
        ) = att["aircraft"] / 4
        base_gas = dfn["aircraft"] / 4 * _defender_consumption(air_win_rate)
        results[f"{attacker}_{attack}_{defender}_gas"] = results[f"{attacker}_{attack}_{defender}_mun"] = (
            base_gas * (1 - results[f"{attacker}_air_fail"])
            + min(base_gas, results[f"{attacker}_air_{attacker}_gas"]) * results[f"{attacker}_air_fail"]
        )

    # Air vs air uses the dogfight casualty rates; every other air target the "airvother" ones.
    for attack, casualties in [
        ("airvair", "airvair"),
        ("airvinfra", "airvother"),
        ("airvsoldiers", "airvother"),
        ("airvtanks", "airvother"),
        ("airvships", "airvother"),
    ]:
        results[f"{attacker}_{attack}_{attacker}_alum"] = (
            results[f"{attacker}_{casualties}_{attacker}_avg"] * att_cost["aircraft"]["aluminum"]
            - _salvage(results, attacker, air_win_rate, results[f"{attacker}_{casualties}_{attacker}_avg"] * att_cost["aircraft"]["aluminum"])
            - _salvage(results, attacker, air_win_rate, results[f"{attacker}_{casualties}_{defender}_avg"] * dfn_cost["aircraft"]["aluminum"])
        )
        results[f"{attacker}_{attack}_{attacker}_steel"] = 0
        results[f"{attacker}_{attack}_{attacker}_money"] = results[f"{attacker}_{casualties}_{attacker}_avg"] * att_cost["aircraft"]["money"]
        results[f"{attacker}_{attack}_{attacker}_total"] = _cost_total(results, f"{attacker}_{attack}_{attacker}")

    results[f"{attacker}_airvair_{defender}_alum"] = results[f"{attacker}_airvair_{defender}_avg"] * dfn_cost["aircraft"]["aluminum"]
    results[f"{attacker}_airvair_{defender}_steel"] = 0
    results[f"{attacker}_airvair_{defender}_money"] = (
        results[f"{attacker}_airvair_{defender}_avg"] * dfn_cost["aircraft"]["money"]
        + results[f"{attacker}_air_{defender}_lost_infra_avg_value"] * 1 / 3
    )

    results[f"{attacker}_airvinfra_{defender}_alum"] = results[f"{attacker}_airvother_{defender}_avg"] * dfn_cost["aircraft"]["aluminum"]
    results[f"{attacker}_airvinfra_{defender}_steel"] = 0
    results[f"{attacker}_airvinfra_{defender}_money"] = (
        results[f"{attacker}_airvother_{defender}_avg"] * dfn_cost["aircraft"]["money"]
        + results[f"{attacker}_air_{defender}_lost_infra_avg_value"]
    )

    for suffix, destroy_key, unit_price in [
        ("airvsoldiers", "soldiers_destroyed", dfn_cost["soldiers"]["money"]),
        ("airvtanks", "tanks_destroyed", dfn_cost["tanks"]["money"]),
        ("airvships", "ships_destroyed", dfn_cost["ships"]["money"]),
    ]:
        results[f"{attacker}_{suffix}_{defender}_alum"] = results[f"{attacker}_airvother_{defender}_avg"] * dfn_cost["aircraft"]["aluminum"]
        results[f"{attacker}_{suffix}_{defender}_steel"] = (
            0 if suffix != "airvtanks" else results[f"{attacker}_air_{defender}_tanks_destroyed_avg"] * dfn_cost["tanks"]["steel"]
        )
        results[f"{attacker}_{suffix}_{defender}_money"] = (
            results[f"{attacker}_airvother_{defender}_avg"] * dfn_cost["aircraft"]["money"]
            + results[f"{attacker}_air_{defender}_lost_infra_avg_value"] * 1 / 3
            + results[f"{attacker}_air_{defender}_{destroy_key}_avg"] * unit_price
        )

    for attack in ["airvair", "airvinfra", "airvsoldiers", "airvtanks", "airvships"]:
        results[f"{attacker}_{attack}_{defender}_total"] = _cost_total(results, f"{attacker}_{attack}_{defender}")
        results[f"{attacker}_{attack}_net"] = (
            results[f"{attacker}_{attack}_{defender}_total"] - results[f"{attacker}_{attack}_{attacker}_total"]
        )

    for tactic in ["navalvinfra", "navalvships"]:
        results[f"{attacker}_{tactic}_{attacker}_mun"] = att["ships"] * 1.75
        results[f"{attacker}_{tactic}_{attacker}_gas"] = att["ships"] * 1.0
        results[f"{attacker}_{tactic}_{attacker}_alum"] = 0
        results[f"{attacker}_{tactic}_{attacker}_steel"] = (
            results[f"{attacker}_{tactic}_{attacker}_avg"] * att_cost["ships"]["steel"]
            - _salvage(results, attacker, naval_win_rate, results[f"{attacker}_{tactic}_{attacker}_avg"] * att_cost["ships"]["steel"])
            - _salvage(results, attacker, naval_win_rate, results[f"{attacker}_{tactic}_{defender}_avg"] * dfn_cost["ships"]["steel"])
        )
        results[f"{attacker}_{tactic}_{attacker}_money"] = results[f"{attacker}_{tactic}_{attacker}_avg"] * att_cost["ships"]["money"]
        results[f"{attacker}_{tactic}_{attacker}_total"] = _cost_total(results, f"{attacker}_{tactic}_{attacker}")

        base_mun = dfn["ships"] * 1.75 * _defender_consumption(naval_win_rate)
        results[f"{attacker}_{tactic}_{defender}_mun"] = (
            base_mun * (1 - results[f"{attacker}_naval_fail"])
            + min(base_mun, results[f"{attacker}_{tactic}_{attacker}_mun"]) * results[f"{attacker}_naval_fail"]
        )
        base_gas = dfn["ships"] * 1.0 * _defender_consumption(naval_win_rate)
        results[f"{attacker}_{tactic}_{defender}_gas"] = (
            base_gas * (1 - results[f"{attacker}_naval_fail"])
            + min(base_gas, results[f"{attacker}_{tactic}_{attacker}_gas"]) * results[f"{attacker}_naval_fail"]
        )
        results[f"{attacker}_{tactic}_{defender}_alum"] = 0
        results[f"{attacker}_{tactic}_{defender}_steel"] = results[f"{attacker}_{tactic}_{defender}_avg"] * dfn_cost["ships"]["steel"]
        results[f"{attacker}_{tactic}_{defender}_money"] = (
            results[f"{attacker}_{tactic}_{defender}_lost_infra_avg_value"]
            + results[f"{attacker}_{tactic}_{defender}_avg"] * dfn_cost["ships"]["money"]
        )
        results[f"{attacker}_{tactic}_{defender}_total"] = _cost_total(results, f"{attacker}_{tactic}_{defender}")
        results[f"{attacker}_{tactic}_net"] = (
            results[f"{attacker}_{tactic}_{defender}_total"] - results[f"{attacker}_{tactic}_{attacker}_total"]
        )

    # Launch costs per PWPedia july-2025-update.
    for attack, launch in (
        ("nuke", {"alum": 1000, "gas": 500, "uranium": 500, "money": 1_750_000}),
        ("missile", {"alum": 150, "gas": 100, "mun": 100, "money": 150_000}),
    ):
        for key in ("alum", "steel", "gas", "mun", "uranium"):
            results[f"{attacker}_{attack}_{attacker}_{key}"] = launch.get(key, 0)
            results[f"{attacker}_{attack}_{defender}_{key}"] = 0
        results[f"{attacker}_{attack}_{attacker}_money"] = launch["money"]
        results[f"{attacker}_{attack}_{attacker}_total"] = _cost_total(results, f"{attacker}_{attack}_{attacker}")
        results[f"{attacker}_{attack}_{defender}_money"] = results[f"{attacker}_{attack}_{defender}_lost_infra_avg_value"]
        results[f"{attacker}_{attack}_{defender}_total"] = results[f"{attacker}_{attack}_{defender}_money"]
        results[f"{attacker}_{attack}_net"] = (
            results[f"{attacker}_{attack}_{defender}_total"] - results[f"{attacker}_{attack}_{attacker}_total"]
        )
