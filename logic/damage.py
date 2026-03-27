from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from . import queries
from logic import economy as economy_logic
from logic.common import weird_division
from logic.merge_utils import get_query
from logic.military import calculate_win_chance_raw

logger = logging.getLogger(__name__)

GraphQLCaller = Callable[[str], Awaitable[dict[str, Any]]]


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
            f"{get_query(queries.BATTLE_CALC)}"
            "}}"
        )
        response = await call_pnw(query)
        nation_list = response.get("data", {}).get("nations", {}).get("data", [])
        nation_list = sorted(nation_list, key=lambda item: int(item["id"]))
        for nation in nation_list:
            nid = nation["id"]
            if nid == nation1_id:
                results["nation1"] = nation
            if nid == nation2_id:
                results["nation2"] = nation

    if "nation1" not in results or "nation2" not in results:
        raise ValueError("Could not retrieve both nations for damage calculation")

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

    if war["war_type"] == "RAID":
        results[f"{defender}_war_infra_mod"] = 0.25
        results[f"{attacker}_war_infra_mod"] = 0.5
        results[f"{defender}_war_loot_mod"] = 1
        results[f"{attacker}_war_loot_mod"] = 1
    elif war["war_type"] == "ORDINARY":
        results[f"{defender}_war_infra_mod"] = 0.5
        results[f"{attacker}_war_infra_mod"] = 0.5
        results[f"{defender}_war_loot_mod"] = 0.5
        results[f"{attacker}_war_loot_mod"] = 0.5
    elif war["war_type"] == "ATTRITION":
        results[f"{defender}_war_infra_mod"] = 1
        results[f"{attacker}_war_infra_mod"] = 1
        results[f"{defender}_war_loot_mod"] = 0.25
        results[f"{attacker}_war_loot_mod"] = 0.5


def _calculate_win_rates(results: Dict[str, Any], attacker: str, defender: str) -> None:
    defender_tanks_value = (results[defender]["tanks"] * 40 * results[f"{defender}_tanks"]) ** (3 / 4)
    defender_soldiers_value = (
        results[defender]["soldiers"] * results.get(f"{defender}_soldier_munition_mod", 1.75)
        + results[defender]["population"] * 0.0025
    ) ** (3 / 4)
    defender_army_value = (defender_soldiers_value + defender_tanks_value) ** (3 / 4)

    attacker_tanks_value = (results[attacker]["tanks"] * 40 * results[f"{attacker}_tanks"]) ** (3 / 4)
    attacker_soldiers_value = (
        results[attacker]["soldiers"] * results.get(f"{attacker}_soldier_munition_mod", 1.75)
    ) ** (3 / 4)
    attacker_army_value = (attacker_soldiers_value + attacker_tanks_value) ** (3 / 4)

    results[f"{attacker}_ground_win_rate"] = calculate_win_chance_raw(attacker_army_value, defender_army_value)

    attacker_aircraft_value = (results[attacker]["aircraft"] * 3) ** (3 / 4)
    defender_aircraft_value = (results[defender]["aircraft"] * 3) ** (3 / 4)
    results[f"{attacker}_air_win_rate"] = calculate_win_chance_raw(attacker_aircraft_value, defender_aircraft_value)

    attacker_ships_value = (results[attacker]["ships"] * 4) ** (3 / 4)
    defender_ships_value = (results[defender]["ships"] * 4) ** (3 / 4)
    results[f"{attacker}_naval_win_rate"] = calculate_win_chance_raw(attacker_ships_value, defender_ships_value)

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

    for label, modifier in [("avg", 0.7), ("diff", 0.3)]:
        results[f"{attacker}_ground_{attacker}_{label}_soldiers"] = min(
            round(((defender_casualties_soldiers * 0.0084) + (defender_casualties_tanks * 0.0092)) * modifier * 3),
            results[attacker]["soldiers"],
        )
        results[f"{attacker}_ground_{attacker}_{label}_tanks"] = min(
            round(
                (
                    ((defender_casualties_soldiers * 0.0004060606) + (defender_casualties_tanks * 0.00066666666))
                    * results[f"{attacker}_ground_win_rate"]
                    + ((defender_soldiers_value * 0.00043225806) + (defender_tanks_value * 0.00070967741))
                    * (1 - results[f"{attacker}_ground_win_rate"])
                )
                * modifier
                * 3
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
                    + ((attacker_soldiers_value * 0.0004060606) + (attacker_tanks_value * 0.00066666666))
                    * (1 - results[f"{attacker}_ground_win_rate"])
                )
                * modifier
                * 3
            ),
            results[defender]["tanks"],
        )

    results[f"{attacker}_airvair_{attacker}_avg"] = min(
        round(defender_casualties_aircraft * 0.7 * 0.01 * 3 * results[f"{attacker}_extra_cas"]),
        results[attacker]["aircraft"],
    )
    results[f"{attacker}_airvair_{attacker}_diff"] = min(
        round(defender_casualties_aircraft * 0.3 * 0.01 * 3 * results[f"{attacker}_extra_cas"]),
        results[attacker]["aircraft"],
    )
    results[f"{attacker}_airvother_{attacker}_avg"] = min(
        round(defender_casualties_aircraft * 0.7 * 0.015385 * 3 * results[f"{attacker}_extra_cas"]),
        results[attacker]["aircraft"],
    )
    results[f"{attacker}_airvother_{attacker}_diff"] = min(
        round(defender_casualties_aircraft * 0.3 * 0.015385 * 3 * results[f"{attacker}_extra_cas"]),
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
        round(attacker_casualties_ships * 0.7 * 0.009625 * 3 * results[f"{attacker}_extra_cas"]),
        results[defender]["ships"],
    )
    results[f"{attacker}_navalvinfra_{defender}_diff"] = min(
        round(attacker_casualties_ships * 0.3 * 0.009625 * 3 * results[f"{attacker}_extra_cas"]),
        results[defender]["ships"],
    )
    results[f"{attacker}_navalvinfra_{attacker}_avg"] = min(
        round(defender_casualties_ships * 0.7 * 0.009625 * 3),
        results[attacker]["ships"],
    )
    results[f"{attacker}_navalvinfra_{attacker}_diff"] = min(
        round(defender_casualties_ships * 0.3 * 0.009625 * 3),
        results[attacker]["ships"],
    )

    results[f"{attacker}_navalvships_{defender}_avg"] = min(
        round(attacker_casualties_ships * 0.7 * 0.017875 * 3 * results[f"{attacker}_extra_cas"]),
        results[defender]["ships"],
    )
    results[f"{attacker}_navalvships_{defender}_diff"] = min(
        round(attacker_casualties_ships * 0.3 * 0.017875 * 3 * results[f"{attacker}_extra_cas"]),
        results[defender]["ships"],
    )
    results[f"{attacker}_navalvships_{attacker}_avg"] = min(
        round(defender_casualties_ships * 0.7 * 0.017875 * 3),
        results[attacker]["ships"],
    )
    results[f"{attacker}_navalvships_{attacker}_diff"] = min(
        round(defender_casualties_ships * 0.3 * 0.017875 * 3),
        results[attacker]["ships"],
    )

    results[f"{attacker}_naval_{defender}_avg"] = results[f"{attacker}_navalvinfra_{defender}_avg"]
    results[f"{attacker}_naval_{defender}_diff"] = results[f"{attacker}_navalvinfra_{defender}_diff"]
    results[f"{attacker}_naval_{attacker}_avg"] = results[f"{attacker}_navalvinfra_{attacker}_avg"]
    results[f"{attacker}_naval_{attacker}_diff"] = results[f"{attacker}_navalvinfra_{attacker}_diff"]


def _apply_policy_modifiers(results: Dict[str, Any], nation_key: str) -> None:
    results[f"{nation_key}_policy_infra_dealt"] = 1
    results[f"{nation_key}_policy_loot_stolen"] = 1
    results[f"{nation_key}_policy_infra_lost"] = 1
    results[f"{nation_key}_policy_loot_lost"] = 1
    results[f"{nation_key}_policy_improvements_lost"] = 1
    results[f"{nation_key}_policy_improvements_destroyed"] = 1
    results[f"{nation_key}_vds_mod"] = 1
    results[f"{nation_key}_irond_mod"] = 1
    results[f"{nation_key}_fallout_shelter_mod"] = 1
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
        results[f"{nation_key}_policy_improvements_lost"] = 2.0
        results[f"{nation_key}_policy_loot_stolen"] = 1.4
    elif policy == "Tactician":
        results[f"{nation_key}_policy_improvements_destroyed"] = 2.0
    elif policy == "Guardian":
        results[f"{nation_key}_policy_improvements_lost"] = 0.5
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
    if results[nation_key].get("military_salvage"):
        results[f"{nation_key}_military_salvage_mod"] = 1
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


def _calculate_damage_numbers(results: Dict[str, Any], attacker: str, defender: str) -> None:
    def_rss = _defender_consumption(results[f"{attacker}_ground_win_rate"])

    # Infra loss calculations
    results[f"{attacker}_ground_{defender}_lost_infra_avg"] = max(
        min(
            (results[attacker]["soldiers"] - results[defender]["soldiers"] * 0.5) * 0.000606061
            + (results[attacker]["tanks"] - (results[defender]["tanks"] * 0.5)) * 0.01,
            results[defender]["city"]["infrastructure"] * 0.2 + 25,
        )
        * 0.95
        * results[f"{attacker}_ground_win_rate"],
        0,
    ) * results[f"{attacker}_war_infra_mod"] * results[f"{attacker}_policy_infra_dealt"] * results[f"{defender}_policy_infra_lost"]

    results[f"{attacker}_ground_{defender}_lost_infra_diff"] = (
        results[f"{attacker}_ground_{defender}_lost_infra_avg"] / 0.95 * 0.10
    )

    results[f"{attacker}_ground_loot_avg"] = (
        (results[attacker]["soldiers"] * 1.1 + results[attacker]["tanks"] * 25.15)
        * results[f"{attacker}_ground_win_rate"]
        * 3
        * 0.95
        * results[f"{attacker}_war_loot_mod"]
        * results[f"{attacker}_policy_loot_stolen"]
        * results[f"{defender}_policy_loot_lost"]
        * results.get(f"{attacker}_pirate_econ_loot", 1)
        * results[f"{attacker}_advanced_pirate_econ_loot"]
    )

    results[f"{attacker}_ground_loot_diff"] = (
        results[f"{attacker}_ground_loot_avg"] / 0.95 * 0.15
    )

    results[f"{attacker}_air_{defender}_lost_infra_avg"] = max(
        min(
            (results[attacker]["aircraft"] - results[defender]["aircraft"] * 0.5) * 0.35353535,
            results[defender]["city"]["infrastructure"] * 0.5 + 100,
        )
        * 0.95
        * results[f"{attacker}_air_win_rate"],
        0,
    ) * results[f"{attacker}_war_infra_mod"] * results[f"{attacker}_policy_infra_dealt"] * results[f"{defender}_policy_infra_lost"]

    results[f"{attacker}_air_{defender}_lost_infra_diff"] = (
        results[f"{attacker}_air_{defender}_lost_infra_avg"] / 0.95 * 0.10
    )

    results[f"{attacker}_air_{defender}_soldiers_destroyed_avg"] = round(
        max(
            min(
                results[defender]["soldiers"],
                results[defender]["soldiers"] * 0.75 + 1000,
                (results[attacker]["aircraft"] - results[defender]["aircraft"] * 0.5) * 35 * 0.95,
            ),
            0,
        )
    ) * _defender_consumption(results[f"{attacker}_air_win_rate"])

    results[f"{attacker}_air_{defender}_soldiers_destroyed_diff"] = (
        results[f"{attacker}_air_{defender}_soldiers_destroyed_avg"] / 0.95 * 0.1
    )

    results[f"{attacker}_air_{defender}_tanks_destroyed_avg"] = round(
        max(
            min(
                results[defender]["tanks"],
                results[defender]["tanks"] * 0.75 + 10,
                (results[attacker]["aircraft"] - results[defender]["aircraft"] * 0.5) * 1.25 * 0.95,
            ),
            0,
        )
    ) * _defender_consumption(results[f"{attacker}_air_win_rate"])

    results[f"{attacker}_air_{defender}_tanks_destroyed_diff"] = (
        results[f"{attacker}_air_{defender}_tanks_destroyed_avg"] / 0.95 * 0.1
    )

    results[f"{attacker}_air_{defender}_ships_destroyed_avg"] = round(
        max(
            min(
                results[defender]["ships"],
                results[defender]["ships"] * 0.75 + 4,
                (results[attacker]["aircraft"] - results[defender]["aircraft"] * 0.5) * 0.0285 * 0.95,
            ),
            0,
        )
    ) * _defender_consumption(results[f"{attacker}_air_win_rate"])

    results[f"{attacker}_air_{defender}_ships_destroyed_diff"] = (
        results[f"{attacker}_air_{defender}_ships_destroyed_avg"] / 0.95 * 0.1
    )

    results[f"{attacker}_navalvinfra_{defender}_lost_infra_avg"] = max(
        min(
            (results[attacker]["ships"] - results[attacker]["ships"] * 0.5) * 2.625,
            results[defender]["city"]["infrastructure"] * 0.5 + 25,
        )
        * 0.95
        * results[f"{attacker}_naval_win_rate"],
        0,
    ) * results[f"{attacker}_war_infra_mod"] * results[f"{attacker}_policy_infra_dealt"] * results[f"{defender}_policy_infra_lost"]

    results[f"{attacker}_navalvinfra_{defender}_lost_infra_diff"] = (
        results[f"{attacker}_navalvinfra_{defender}_lost_infra_avg"] / 0.95 * 0.10
    )

    results[f"{attacker}_navalvships_{defender}_lost_infra_avg"] = max(
        min(
            (results[attacker]["ships"] - results[attacker]["ships"] * 0.5) * 1.8375,
            results[defender]["city"]["infrastructure"] * 0.5 + 25,
        )
        * 0.95
        * results[f"{attacker}_naval_win_rate"],
        0,
    ) * results[f"{attacker}_war_infra_mod"] * results[f"{attacker}_policy_infra_dealt"] * results[f"{defender}_policy_infra_lost"]

    results[f"{attacker}_navalvships_{defender}_lost_infra_diff"] = (
        results[f"{attacker}_navalvships_{defender}_lost_infra_avg"] / 0.95 * 0.10
    )

    results[f"{attacker}_naval_{defender}_lost_infra_avg"] = results[f"{attacker}_navalvinfra_{defender}_lost_infra_avg"]
    results[f"{attacker}_naval_{defender}_lost_infra_diff"] = results[f"{attacker}_navalvinfra_{defender}_lost_infra_diff"]

    results[f"{attacker}_nuke_{defender}_lost_infra_avg"] = max(
        min(
            (1700 + max(2000, results[defender]["city"]["infrastructure"] * 100 / results[defender]["city"]["land"] * 13.5)) / 2,
            results[defender]["city"]["infrastructure"] * 0.8 + 150,
        ),
        0,
    ) * results[f"{attacker}_war_infra_mod"] * results[f"{attacker}_policy_infra_dealt"] * results[f"{defender}_policy_infra_lost"] * results[f"{defender}_fallout_shelter_mod"]

    results[f"{attacker}_missile_{defender}_lost_infra_avg"] = max(
        min(
            (300 + max(350, results[defender]["city"]["infrastructure"] * 100 / results[defender]["city"]["land"] * 3)) / 2,
            results[defender]["city"]["infrastructure"] * 0.3 + 100,
        ),
        0,
    ) * results[f"{attacker}_war_infra_mod"] * results[f"{attacker}_policy_infra_dealt"] * results[f"{defender}_policy_infra_lost"]

    for key in [
        f"{attacker}_ground_{defender}_lost_infra",
        f"{attacker}_air_{defender}_lost_infra",
        f"{attacker}_naval_{defender}_lost_infra",
        f"{attacker}_navalvinfra_{defender}_lost_infra",
        f"{attacker}_navalvships_{defender}_lost_infra",
        f"{attacker}_nuke_{defender}_lost_infra",
        f"{attacker}_missile_{defender}_lost_infra",
    ]:
        if "missile" in key:
            mod = results[f"{defender}_irond_mod"]
        elif "nuke" in key:
            mod = results[f"{defender}_vds_mod"]
        else:
            mod = 1
        results[f"{key}_avg_value"] = economy_logic.infra_cost(
            results[defender]["city"]["infrastructure"] - results[f"{key}_avg"],
            results[defender]["city"]["infrastructure"],
        ) * mod

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
        results[attacker]["soldiers"] * 0.0002 * attacker_munition_factor
        + results[attacker]["tanks"] * 0.01
    )
    results[f"{attacker}_ground_{attacker}_gas"] = results[attacker]["tanks"] * 0.01
    results[f"{attacker}_ground_{attacker}_alum"] = 0
    results[f"{attacker}_ground_{attacker}_steel"] = (
        results[f"{attacker}_ground_{attacker}_avg_tanks"] * 0.5
        - _salvage(results, attacker, results[f"{attacker}_ground_win_rate"], results[f"{attacker}_ground_{attacker}_avg_tanks"] * 0.5)
        - _salvage(results, attacker, results[f"{attacker}_ground_win_rate"], results[f"{attacker}_ground_{defender}_avg_tanks"] * 0.5)
    )
    results[f"{attacker}_ground_{attacker}_money"] = (
        -results[f"{attacker}_ground_loot_avg"]
        + results[f"{attacker}_ground_{attacker}_avg_tanks"] * 60
        + results[f"{attacker}_ground_{attacker}_avg_soldiers"] * 5
    )
    results[f"{attacker}_ground_{attacker}_total"] = (
        results[f"{attacker}_ground_{attacker}_alum"] * 2971
        + results[f"{attacker}_ground_{attacker}_steel"] * 3990
        + results[f"{attacker}_ground_{attacker}_gas"] * 3340
        + results[f"{attacker}_ground_{attacker}_mun"] * 1960
        + results[f"{attacker}_ground_{attacker}_money"]
    )

    base_mun = (
        results[defender]["soldiers"] * 0.0002 * defender_munition_factor
        + results[defender]["population"] / 2_000_000
        + results[defender]["tanks"] * 0.01
    ) * def_rss
    results[f"{attacker}_ground_{defender}_mun"] = (
        base_mun * (1 - results[f"{attacker}_ground_fail"])
        + min(base_mun, results[f"{attacker}_ground_{attacker}_mun"]) * results[f"{attacker}_ground_fail"]
    )
    base_gas = results[defender]["tanks"] * 0.01 * def_rss
    results[f"{attacker}_ground_{defender}_gas"] = (
        base_gas * (1 - results[f"{attacker}_ground_fail"])
        + min(base_gas, results[f"{attacker}_ground_{attacker}_gas"]) * results[f"{attacker}_ground_fail"]
    )
    results[f"{attacker}_ground_{defender}_alum"] = results[f"{attacker}_ground_{defender}_avg_aircraft"] * 10
    results[f"{attacker}_ground_{defender}_steel"] = results[f"{attacker}_ground_{defender}_avg_tanks"] * 0.5
    results[f"{attacker}_ground_{defender}_money"] = (
        results[f"{attacker}_ground_loot_avg"]
        + results[f"{attacker}_ground_{defender}_avg_aircraft"] * 4000
        + results[f"{attacker}_ground_{defender}_avg_tanks"] * 60
        + results[f"{attacker}_ground_{defender}_avg_soldiers"] * 5
        + results[f"{attacker}_ground_{defender}_lost_infra_avg_value"]
    )
    results[f"{attacker}_ground_{defender}_total"] = (
        results[f"{attacker}_ground_{defender}_alum"] * 2971
        + results[f"{attacker}_ground_{defender}_steel"] * 3990
        + results[f"{attacker}_ground_{defender}_gas"] * 3340
        + results[f"{attacker}_ground_{defender}_mun"] * 1960
        + results[f"{attacker}_ground_{defender}_money"]
    )
    results[f"{attacker}_ground_net"] = (
        results[f"{attacker}_ground_{defender}_total"] - results[f"{attacker}_ground_{attacker}_total"]
    )

    for attack in ["air", "airvair", "airvinfra", "airvsoldiers", "airvtanks", "airvships"]:
        results[f"{attacker}_{attack}_{attacker}_gas"] = (
            results[f"{attacker}_{attack}_{attacker}_mun"]
        ) = results[attacker]["aircraft"] / 4
        base_gas = results[defender]["aircraft"] / 4 * _defender_consumption(results[f"{attacker}_air_win_rate"])
        results[f"{attacker}_{attack}_{defender}_gas"] = results[f"{attacker}_{attack}_{defender}_mun"] = (
            base_gas * (1 - results[f"{attacker}_air_fail"])
            + min(base_gas, results[f"{attacker}_air_{attacker}_gas"]) * results[f"{attacker}_air_fail"]
        )

    results[f"{attacker}_airvair_{attacker}_alum"] = (
        results[f"{attacker}_airvair_{attacker}_avg"] * 10
        - _salvage(results, attacker, results[f"{attacker}_air_win_rate"], results[f"{attacker}_airvair_{attacker}_avg"] * 10)
        - _salvage(results, attacker, results[f"{attacker}_air_win_rate"], results[f"{attacker}_airvair_{defender}_avg"] * 10)
    )
    results[f"{attacker}_airvair_{attacker}_steel"] = 0
    results[f"{attacker}_airvair_{attacker}_money"] = results[f"{attacker}_airvair_{attacker}_avg"] * 4000
    results[f"{attacker}_airvair_{attacker}_total"] = (
        results[f"{attacker}_airvair_{attacker}_alum"] * 2971
        + results[f"{attacker}_airvair_{attacker}_steel"] * 3990
        + results[f"{attacker}_air_{attacker}_gas"] * 3340
        + results[f"{attacker}_air_{attacker}_mun"] * 1960
        + results[f"{attacker}_airvair_{attacker}_money"]
    )

    results[f"{attacker}_airvair_{defender}_alum"] = results[f"{attacker}_airvair_{defender}_avg"] * 10
    results[f"{attacker}_airvair_{defender}_steel"] = 0
    results[f"{attacker}_airvair_{defender}_money"] = (
        results[f"{attacker}_airvair_{defender}_avg"] * 4000
        + results[f"{attacker}_air_{defender}_lost_infra_avg_value"] * 1 / 3
    )
    results[f"{attacker}_airvair_{defender}_total"] = (
        results[f"{attacker}_airvair_{defender}_alum"] * 2971
        + results[f"{attacker}_airvair_{defender}_steel"] * 3990
        + results[f"{attacker}_air_{defender}_gas"] * 3340
        + results[f"{attacker}_air_{defender}_mun"] * 1960
        + results[f"{attacker}_airvair_{defender}_money"]
    )
    results[f"{attacker}_airvair_net"] = (
        results[f"{attacker}_airvair_{defender}_total"] - results[f"{attacker}_airvair_{attacker}_total"]
    )

    results[f"{attacker}_airvinfra_{attacker}_alum"] = (
        results[f"{attacker}_airvother_{attacker}_avg"] * 10
        - _salvage(results, attacker, results[f"{attacker}_air_win_rate"], results[f"{attacker}_airvother_{attacker}_avg"] * 10)
        - _salvage(results, attacker, results[f"{attacker}_air_win_rate"], results[f"{attacker}_airvother_{defender}_avg"] * 10)
    )
    results[f"{attacker}_airvinfra_{attacker}_steel"] = 0
    results[f"{attacker}_airvinfra_{attacker}_money"] = results[f"{attacker}_airvother_{attacker}_avg"] * 4000
    results[f"{attacker}_airvinfra_{attacker}_total"] = (
        results[f"{attacker}_airvinfra_{attacker}_alum"] * 2971
        + results[f"{attacker}_airvinfra_{attacker}_steel"] * 3990
        + results[f"{attacker}_air_{attacker}_gas"] * 3340
        + results[f"{attacker}_air_{attacker}_mun"] * 1960
        + results[f"{attacker}_airvinfra_{attacker}_money"]
    )

    results[f"{attacker}_airvinfra_{defender}_alum"] = results[f"{attacker}_airvother_{defender}_avg"] * 10
    results[f"{attacker}_airvinfra_{defender}_steel"] = 0
    results[f"{attacker}_airvinfra_{defender}_money"] = (
        results[f"{attacker}_airvother_{defender}_avg"] * 4000
        + results[f"{attacker}_air_{defender}_lost_infra_avg_value"]
    )
    results[f"{attacker}_airvinfra_{defender}_total"] = (
        results[f"{attacker}_airvinfra_{defender}_alum"] * 2971
        + results[f"{attacker}_airvinfra_{defender}_steel"] * 3990
        + results[f"{attacker}_air_{defender}_gas"] * 3340
        + results[f"{attacker}_air_{defender}_mun"] * 1960
        + results[f"{attacker}_airvinfra_{defender}_money"]
    )
    results[f"{attacker}_airvinfra_net"] = (
        results[f"{attacker}_airvinfra_{defender}_total"] - results[f"{attacker}_airvinfra_{attacker}_total"]
    )

    for suffix, destroy_key, extra_money in [
        ("airvsoldiers", "soldiers_destroyed", lambda res: res * 5),
        ("airvtanks", "tanks_destroyed", lambda res: res * 60),
        ("airvships", "ships_destroyed", lambda res: res * 50000),
    ]:
        results[f"{attacker}_{suffix}_{attacker}_alum"] = (
            results[f"{attacker}_airvother_{attacker}_avg"] * 10
            - _salvage(results, attacker, results[f"{attacker}_air_win_rate"], results[f"{attacker}_airvother_{attacker}_avg"] * 10)
            - _salvage(results, attacker, results[f"{attacker}_air_win_rate"], results[f"{attacker}_airvother_{defender}_avg"] * 10)
        )
        results[f"{attacker}_{suffix}_{attacker}_steel"] = 0
        results[f"{attacker}_{suffix}_{attacker}_money"] = results[f"{attacker}_airvother_{attacker}_avg"] * 4000
        results[f"{attacker}_{suffix}_{attacker}_total"] = (
            results[f"{attacker}_{suffix}_{attacker}_alum"] * 2971
            + results[f"{attacker}_{suffix}_{attacker}_steel"] * 3990
            + results[f"{attacker}_air_{attacker}_gas"] * 3340
            + results[f"{attacker}_air_{attacker}_mun"] * 1960
            + results[f"{attacker}_{suffix}_{attacker}_money"]
        )

        results[f"{attacker}_{suffix}_{defender}_alum"] = results[f"{attacker}_airvother_{defender}_avg"] * 10
        results[f"{attacker}_{suffix}_{defender}_steel"] = (
            0 if suffix != "airvtanks" else results[f"{attacker}_air_{defender}_tanks_destroyed_avg"] * 0.5
        )
        destroyed_avg = results[f"{attacker}_air_{defender}_{destroy_key}_avg"]
        results[f"{attacker}_{suffix}_{defender}_money"] = (
            results[f"{attacker}_airvother_{defender}_avg"] * 4000
            + results[f"{attacker}_air_{defender}_lost_infra_avg_value"] * 1 / 3
            + extra_money(destroyed_avg)
        )
        results[f"{attacker}_{suffix}_{defender}_total"] = (
            results[f"{attacker}_{suffix}_{defender}_alum"] * 2971
            + results[f"{attacker}_{suffix}_{defender}_steel"] * 3990
            + results[f"{attacker}_air_{defender}_gas"] * 3340
            + results[f"{attacker}_air_{defender}_mun"] * 1960
            + results[f"{attacker}_{suffix}_{defender}_money"]
        )
        results[f"{attacker}_{suffix}_net"] = (
            results[f"{attacker}_{suffix}_{defender}_total"] - results[f"{attacker}_{suffix}_{attacker}_total"]
        )

    for tactic in ["naval", "navalvinfra", "navalvships"]:
        results[f"{attacker}_{tactic}_{attacker}_mun"] = results[attacker]["ships"] * 1.75
        results[f"{attacker}_{tactic}_{attacker}_gas"] = results[attacker]["ships"] * 1.0
        results[f"{attacker}_{tactic}_{attacker}_alum"] = 0
        results[f"{attacker}_{tactic}_{attacker}_steel"] = (
            results[f"{attacker}_{tactic}_{attacker}_avg"] * 30
            + _salvage(results, attacker, results[f"{attacker}_naval_win_rate"], results[f"{attacker}_{tactic}_{attacker}_avg"] * 30)
            + _salvage(results, attacker, results[f"{attacker}_naval_win_rate"], results[f"{attacker}_{tactic}_{defender}_avg"] * 30)
        )
        results[f"{attacker}_{tactic}_{attacker}_money"] = results[f"{attacker}_{tactic}_{attacker}_avg"] * 50000
        results[f"{attacker}_{tactic}_{attacker}_total"] = (
            results[f"{attacker}_{tactic}_{attacker}_alum"] * 2971
            + results[f"{attacker}_{tactic}_{attacker}_steel"] * 3990
            + results[f"{attacker}_{tactic}_{attacker}_gas"] * 3340
            + results[f"{attacker}_{tactic}_{attacker}_mun"] * 1960
            + results[f"{attacker}_{tactic}_{attacker}_money"]
        )

        base_mun = results[defender]["ships"] * 1.75 * _defender_consumption(results[f"{attacker}_naval_win_rate"])
        results[f"{attacker}_{tactic}_{defender}_mun"] = (
            base_mun * (1 - results[f"{attacker}_naval_fail"])
            + min(base_mun, results[f"{attacker}_{tactic}_{attacker}_mun"]) * results[f"{attacker}_naval_fail"]
        )
        base_gas = results[defender]["ships"] * 1.0 * _defender_consumption(results[f"{attacker}_naval_win_rate"])
        results[f"{attacker}_{tactic}_{defender}_gas"] = (
            base_gas * (1 - results[f"{attacker}_naval_fail"])
            + min(base_gas, results[f"{attacker}_{tactic}_{attacker}_gas"]) * results[f"{attacker}_naval_fail"]
        )
        results[f"{attacker}_{tactic}_{defender}_alum"] = 0
        results[f"{attacker}_{tactic}_{defender}_steel"] = results[f"{attacker}_{tactic}_{defender}_avg"] * 30
        results[f"{attacker}_{tactic}_{defender}_money"] = (
            results.get(f"{attacker}_{tactic}_{defender}_lost_infra_avg_value", 0)
            + results[f"{attacker}_{tactic}_{defender}_avg"] * 50000
        )
        results[f"{attacker}_{tactic}_{defender}_total"] = (
            results[f"{attacker}_{tactic}_{defender}_alum"] * 2971
            + results[f"{attacker}_{tactic}_{defender}_steel"] * 3990
            + results[f"{attacker}_{tactic}_{defender}_gas"] * 3340
            + results[f"{attacker}_{tactic}_{defender}_mun"] * 1960
            + results[f"{attacker}_{tactic}_{defender}_money"]
        )
        results[f"{attacker}_{tactic}_net"] = (
            results[f"{attacker}_{tactic}_{defender}_total"] - results[f"{attacker}_{tactic}_{attacker}_total"]
        )

    results[f"{attacker}_naval_{attacker}_mun"] = results[f"{attacker}_navalvinfra_{attacker}_mun"]
    results[f"{attacker}_naval_{attacker}_gas"] = results[f"{attacker}_navalvinfra_{attacker}_gas"]
    results[f"{attacker}_naval_{attacker}_alum"] = results[f"{attacker}_navalvinfra_{attacker}_alum"]
    results[f"{attacker}_naval_{attacker}_steel"] = results[f"{attacker}_navalvinfra_{attacker}_steel"]
    results[f"{attacker}_naval_{attacker}_money"] = results[f"{attacker}_navalvinfra_{attacker}_money"]
    results[f"{attacker}_naval_{attacker}_total"] = results[f"{attacker}_navalvinfra_{attacker}_total"]
    results[f"{attacker}_naval_{defender}_mun"] = results[f"{attacker}_navalvinfra_{defender}_mun"]
    results[f"{attacker}_naval_{defender}_gas"] = results[f"{attacker}_navalvinfra_{defender}_gas"]
    results[f"{attacker}_naval_{defender}_alum"] = results[f"{attacker}_navalvinfra_{defender}_alum"]
    results[f"{attacker}_naval_{defender}_steel"] = results[f"{attacker}_navalvinfra_{defender}_steel"]
    results[f"{attacker}_naval_{defender}_money"] = results[f"{attacker}_navalvinfra_{defender}_money"]
    results[f"{attacker}_naval_{defender}_total"] = results[f"{attacker}_navalvinfra_{defender}_total"]
    results[f"{attacker}_naval_net"] = results[f"{attacker}_navalvinfra_net"]

    results[f"{attacker}_nuke_{attacker}_alum"] = 1000
    results[f"{attacker}_nuke_{attacker}_steel"] = 0
    results[f"{attacker}_nuke_{attacker}_gas"] = 500
    results[f"{attacker}_nuke_{attacker}_mun"] = 0
    results[f"{attacker}_nuke_{attacker}_money"] = 1_750_000
    results[f"{attacker}_nuke_{attacker}_total"] = (
        results[f"{attacker}_nuke_{attacker}_alum"] * 2971
        + results[f"{attacker}_nuke_{attacker}_steel"] * 3990
        + results[f"{attacker}_nuke_{attacker}_gas"] * 3340
        + results[f"{attacker}_nuke_{attacker}_mun"] * 1960
        + results[f"{attacker}_nuke_{attacker}_money"]
        + 500 * 3039
    )

    results[f"{attacker}_nuke_{defender}_alum"] = 0
    results[f"{attacker}_nuke_{defender}_steel"] = 0
    results[f"{attacker}_nuke_{defender}_gas"] = 0
    results[f"{attacker}_nuke_{defender}_mun"] = 0
    results[f"{attacker}_nuke_{defender}_money"] = results[f"{attacker}_nuke_{defender}_lost_infra_avg_value"]
    results[f"{attacker}_nuke_{defender}_total"] = results[f"{attacker}_nuke_{defender}_money"]
    results[f"{attacker}_nuke_net"] = (
        results[f"{attacker}_nuke_{defender}_total"] - results[f"{attacker}_nuke_{attacker}_total"]
    )

    results[f"{attacker}_missile_{attacker}_alum"] = 150
    results[f"{attacker}_missile_{attacker}_steel"] = 0
    results[f"{attacker}_missile_{attacker}_gas"] = 100
    results[f"{attacker}_missile_{attacker}_mun"] = 100
    results[f"{attacker}_missile_{attacker}_money"] = 150_000
    results[f"{attacker}_missile_{attacker}_total"] = (
        results[f"{attacker}_missile_{attacker}_alum"] * 2971
        + results[f"{attacker}_missile_{attacker}_steel"] * 3990
        + results[f"{attacker}_missile_{attacker}_gas"] * 3340
        + results[f"{attacker}_missile_{attacker}_mun"] * 1960
        + results[f"{attacker}_missile_{attacker}_money"]
    )

    results[f"{attacker}_missile_{defender}_alum"] = 0
    results[f"{attacker}_missile_{defender}_steel"] = 0
    results[f"{attacker}_missile_{defender}_gas"] = 0
    results[f"{attacker}_missile_{defender}_mun"] = 0
    results[f"{attacker}_missile_{defender}_money"] = results[f"{attacker}_missile_{defender}_lost_infra_avg_value"]
    results[f"{attacker}_missile_{defender}_total"] = results[f"{attacker}_missile_{defender}_money"]
    results[f"{attacker}_missile_net"] = (
        results[f"{attacker}_missile_{defender}_total"] - results[f"{attacker}_missile_{attacker}_total"]
    )
