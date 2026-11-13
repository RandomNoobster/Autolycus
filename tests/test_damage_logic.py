"""Tests for the war damage model in logic/damage.py."""
import asyncio
import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from logic import damage
from logic.military import calculate_win_chance_raw


def _nation(nation_id, **overrides):
    nation = {
        "id": str(nation_id),
        "nation_name": f"Nation {nation_id}",
        "population": 2_000_000,
        "warpolicy": "Fortress",  # no infra or loot modifiers
        "soldiers": 150_000,
        "tanks": 12_000,
        "aircraft": 1_500,
        "ships": 200,
        "advanced_pirate_economy": False,
        "pirate_economy": False,
        "irond": False,
        "vds": False,
        "fallout_shelter": False,
        "guiding_satellite": False,
        "military_salvage": False,
        "cities": [{"infrastructure": 2000.0, "land": 2500.0}],
        "wars": [],
    }
    nation.update(overrides)
    return nation


def _war(war_type="ORDINARY", **overrides):
    """An active war nation 1 declared on nation 2."""
    war = {
        "attid": "1",
        "defid": "2",
        "turnsleft": 5,
        "war_type": war_type,
        "groundcontrol": None,
        "airsuperiority": None,
        "navalblockade": None,
        "att_fortify": False,
        "def_fortify": False,
        "attpeace": False,
        "defpeace": False,
    }
    war.update(overrides)
    return war


async def _no_fetch(_query):
    raise AssertionError("both nations were supplied")


def _calc(nation1, nation2):
    return asyncio.run(
        damage.calculate_damage(call_pnw=_no_fetch, nation1=copy.deepcopy(nation1), nation2=copy.deepcopy(nation2))
    )


@pytest.mark.parametrize("war_type", ["RAID", "raid"])
def test_raid_declarer_deals_a_quarter_and_defender_half(war_type):
    results = _calc(_nation(1, wars=[_war(war_type)]), _nation(2))

    assert results["nation1_war_infra_mod"] == 0.25
    assert results["nation2_war_infra_mod"] == 0.5
    assert results["nation1_war_loot_mod"] == results["nation2_war_loot_mod"] == 1.0


def test_attrition_declarer_loots_a_quarter_and_defender_half():
    results = _calc(_nation(1, wars=[_war("ATTRITION")]), _nation(2))

    assert results["nation1_war_infra_mod"] == results["nation2_war_infra_mod"] == 1.0
    assert results["nation1_war_loot_mod"] == 0.25
    assert results["nation2_war_loot_mod"] == 0.5


def test_war_type_follows_the_declarer_when_nation2_declared():
    war = _war("RAID", attid="2", defid="1")
    results = _calc(_nation(1, wars=[war]), _nation(2))

    assert results["nation2_war_infra_mod"] == 0.25
    assert results["nation1_war_infra_mod"] == 0.5


def test_win_rates_use_raw_army_values():
    results = _calc(_nation(1), _nation(2, aircraft=1_000, ships=0))

    assert results["nation1_air_win_rate"] == pytest.approx(calculate_win_chance_raw(1500 * 3, 1000 * 3))
    assert results["nation1_naval_win_rate"] == 1.0
    assert results["nation2_naval_win_rate"] == 0.0


def test_naval_infra_damage_accounts_for_the_defending_fleet():
    outgunned = _calc(_nation(1, ships=50), _nation(2, ships=100))
    unopposed = _calc(_nation(1, ships=50), _nation(2, ships=0))

    # 50 - 100 * 0.5 = 0 effective ships.
    assert outgunned["nation1_navalvinfra_nation2_lost_infra_avg"] == 0
    assert unopposed["nation1_navalvinfra_nation2_lost_infra_avg"] > 0


def test_infra_cap_is_not_scaled_by_win_rate():
    # 2000 vs 0 aircraft: raw 707 * 0.95 is past the 1000-infra city's cap of 600.
    results = _calc(
        _nation(1, aircraft=2_000),
        _nation(2, aircraft=0, cities=[{"infrastructure": 1000.0, "land": 2000.0}]),
    )

    assert results["nation1_air_win_rate"] == 1.0
    # Cap 600, times the default ordinary-war infra share of 0.5.
    assert results["nation1_air_nation2_lost_infra_avg"] == pytest.approx(300)


def test_fortified_defender_raises_the_attackers_casualties():
    plain = _calc(_nation(1, wars=[_war()]), _nation(2))
    fortified = _calc(_nation(1, wars=[_war(def_fortify=True)]), _nation(2))

    for key in (
        "nation1_ground_nation1_avg_soldiers",
        "nation1_ground_nation1_avg_tanks",
        "nation1_navalvinfra_nation1_avg",
        "nation1_navalvships_nation1_avg",
        "nation1_airvair_nation1_avg",
    ):
        assert fortified[key] > plain[key], key
    # The fortified defender's own losses don't change.
    for key in ("nation1_navalvinfra_nation2_avg", "nation1_ground_nation2_avg_soldiers"):
        assert fortified[key] == plain[key], key


def test_lost_units_are_valued_at_the_owners_researched_cost():
    efficient = {"military_research": {"ground_cost": 10, "air_cost": 10, "naval_cost": 10}}
    base = _calc(_nation(1), _nation(2))
    cheap_defender = _calc(_nation(1), _nation(2, **efficient))

    # The defender's research lowers the value of what it loses...
    soldiers = base["nation1_ground_nation2_avg_soldiers"]
    tanks = base["nation1_ground_nation2_avg_tanks"]
    aircraft = base["nation1_ground_nation2_avg_aircraft"]
    assert base["nation1_ground_nation2_money"] - cheap_defender["nation1_ground_nation2_money"] == pytest.approx(
        soldiers * 1 + tanks * 10 + aircraft * 500
    )
    assert cheap_defender["nation1_navalvships_nation2_steel"] == pytest.approx(
        base["nation1_navalvships_nation2_avg"] * 25
    )
    # ...and leaves the attacker's own losses alone.
    for key in ("nation1_ground_nation1_money", "nation1_airvair_nation1_money", "nation1_navalvships_nation1_steel"):
        assert cheap_defender[key] == pytest.approx(base[key]), key


def test_military_salvage_lowers_naval_steel_cost():
    without = _calc(_nation(1), _nation(2, ships=150))
    with_salvage = _calc(_nation(1, military_salvage=True), _nation(2, ships=150))

    assert with_salvage["nation1_navalvinfra_nation1_steel"] < without["nation1_navalvinfra_nation1_steel"]


@pytest.mark.parametrize(
    "projects,bonus",
    [({"pirate_economy": True}, 1.05), ({"pirate_economy": True, "advanced_pirate_economy": True}, 1.05 * 1.05)],
)
def test_pirate_economy_projects_add_ground_loot(projects, bonus):
    base = _calc(_nation(1), _nation(2))
    pirate = _calc(_nation(1, **projects), _nation(2))

    assert pirate["nation1_ground_loot_avg"] == pytest.approx(base["nation1_ground_loot_avg"] * bonus)


def test_nuke_launch_cost_includes_uranium():
    results = _calc(_nation(1), _nation(2))

    assert results["nation1_nuke_nation1_uranium"] == 500
    assert results["nation1_nuke_nation1_total"] == pytest.approx(1000 * 2971 + 500 * 3340 + 500 * 3039 + 1_750_000)


def test_tank_losses_on_lost_rolls_use_the_roll_values():
    # Nation1 is outmatched on the ground, so most rolls are lost.
    results = _calc(_nation(1, soldiers=50_000, tanks=2_000), _nation(2, soldiers=200_000, tanks=15_000))

    assert results["nation1_ground_win_rate"] < 0.1
    # The lost-roll formula gives hundreds of tanks; the old ^3/4 values gave a handful.
    assert results["nation1_ground_nation1_avg_tanks"] > 500


def test_a_nation_against_itself_gets_two_separate_dicts():
    async def fetch_one(_query):
        return {"data": {"nations": {"data": [_nation(1)]}}}

    results = asyncio.run(damage.calculate_damage(call_pnw=fetch_one, nation1_id="1", nation2_id="1"))

    assert results["nation1"] is not results["nation2"]
    assert results["nation1"]["id"] == results["nation2"]["id"] == "1"


def test_missing_nation_raises_not_found():
    async def fetch_one(_query):
        return {"data": {"nations": {"data": [_nation(1)]}}}

    with pytest.raises(damage.NationsNotFoundError):
        asyncio.run(damage.calculate_damage(call_pnw=fetch_one, nation1_id="1", nation2_id="2"))


def test_null_data_counts_as_not_found():
    async def fetch_null(_query):
        return {"data": None, "errors": [{"message": "boom"}]}

    with pytest.raises(damage.NationsNotFoundError):
        asyncio.run(damage.calculate_damage(call_pnw=fetch_null, nation1_id="1", nation2_id="2"))
