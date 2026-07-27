"""Tests for nuke/missile target metrics and war simulation."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from logic.economy import infra_cost, infra_rebuild_cost
from logic.nuke_targets import (
    DEFENDER_STARTING_RESISTANCE,
    IRON_DOME_INTERCEPT_CHANCE,
    MISSILE_RESISTANCE_ON_HIT,
    NUKE_LAUNCH_COST,
    NUKE_RESISTANCE_ON_HIT,
    VDS_INTERCEPT_CHANCE,
    InterceptStrikeEV,
    compute_nuke_missile_metrics,
    simulate_war_net_damage,
)


def _city(infra: float, land: float = 500.0) -> dict:
    return {"infrastructure": infra, "land": land}


def _nation(
    nid: int,
    *,
    cities: list[dict],
    vds: bool = False,
    irond: bool = False,
    fallout_shelter: bool = False,
    warpolicy: str = "None",
    score: float = 1000.0,
) -> dict:
    return {
        "id": nid,
        "nation_name": f"Nation {nid}",
        "score": score,
        "cities": cities,
        "vds": vds,
        "irond": irond,
        "fallout_shelter": fallout_shelter,
        "warpolicy": warpolicy,
        "wars": [],
    }


class TestInterceptStrikeEV:
    def test_vds_hit_probability(self):
        strike = InterceptStrikeEV("nuke", vds=True, iron_dome=False)
        assert strike.hit_probability == pytest.approx(1.0 - VDS_INTERCEPT_CHANCE)

    def test_iron_dome_hit_probability(self):
        strike = InterceptStrikeEV("missile", vds=False, iron_dome=True)
        assert strike.hit_probability == pytest.approx(1.0 - IRON_DOME_INTERCEPT_CHANCE)

    def test_resistance_uses_on_hit_times_hit_probability_only(self):
        nuke_vds = InterceptStrikeEV("nuke", vds=True, iron_dome=False)
        assert nuke_vds.expected_resistance_reduction == pytest.approx(
            NUKE_RESISTANCE_ON_HIT * (1.0 - VDS_INTERCEPT_CHANCE)
        )

        missile_dome = InterceptStrikeEV("missile", vds=False, iron_dome=True)
        assert missile_dome.expected_resistance_reduction == pytest.approx(
            MISSILE_RESISTANCE_ON_HIT * (1.0 - IRON_DOME_INTERCEPT_CHANCE)
        )


class TestInfraRebuildCost:
    def test_rebuild_exceeds_sell_proceeds_at_high_infra(self):
        current = 2500
        lost = 800
        rebuild = infra_rebuild_cost(current, lost)
        sell = abs(infra_cost(current, current - lost))
        assert rebuild > sell * 10

    def test_zero_lost_is_zero(self):
        assert infra_rebuild_cost(1000, 0) == 0


class TestNukeMissileMetrics:
    def test_attrition_attacker_policy_boosts_damage(self):
        attacker = _nation(1, cities=[_city(1000)], warpolicy="Attrition")
        defender = _nation(2, cities=[_city(2000, 600)])
        base_attacker = _nation(1, cities=[_city(1000)], warpolicy="None")

        with_attrition = compute_nuke_missile_metrics(attacker, defender)
        without_attrition = compute_nuke_missile_metrics(base_attacker, defender)

        assert with_attrition is not None
        assert without_attrition is not None
        assert with_attrition.nuke_damage > without_attrition.nuke_damage

    def test_vds_reduces_expected_nuke_damage(self):
        defender_vds = _nation(2, cities=[_city(2000, 600)], vds=True)
        defender_plain = _nation(3, cities=[_city(2000, 600)], vds=False)
        attacker = _nation(1, cities=[_city(1000)], warpolicy="Attrition")

        with_vds = compute_nuke_missile_metrics(attacker, defender_vds)
        without_vds = compute_nuke_missile_metrics(attacker, defender_plain)

        assert with_vds is not None and without_vds is not None
        assert with_vds.nuke_damage < without_vds.nuke_damage
        assert with_vds.nuke_damage_without_vds == pytest.approx(
            without_vds.nuke_damage_without_vds, rel=1e-6
        )

    def test_iron_dome_reduces_missile_damage(self):
        defender_dome = _nation(2, cities=[_city(1500, 500)], irond=True)
        defender_plain = _nation(3, cities=[_city(1500, 500)], irond=False)
        attacker = _nation(1, cities=[_city(1000)], warpolicy="Attrition")

        with_dome = compute_nuke_missile_metrics(attacker, defender_dome)
        without_dome = compute_nuke_missile_metrics(attacker, defender_plain)

        assert with_dome is not None and without_dome is not None
        assert with_dome.missile_damage < without_dome.missile_damage


class TestSimulatedWar:
    def test_nuke_war_breaks_resistance_without_vds_in_four_shots(self):
        attacker = _nation(1, cities=[_city(1000)], warpolicy="Attrition")
        defender = _nation(2, cities=[_city(2500, 600), _city(800, 400)])

        net, shots, total_damage, total_cost = simulate_war_net_damage(
            attacker, defender, "nuke"
        )

        assert shots == 4
        assert total_cost == pytest.approx(4 * NUKE_LAUNCH_COST)
        assert net == pytest.approx(total_damage - total_cost)

    def test_vds_requires_more_nuke_shots_via_intercept_ev(self):
        attacker = _nation(1, cities=[_city(1000)], warpolicy="Attrition")
        defender = _nation(2, cities=[_city(2500, 600)], vds=True)

        _, shots_vds, _, _ = simulate_war_net_damage(attacker, defender, "nuke")
        defender_plain = _nation(3, cities=[_city(2500, 600)], vds=False)
        _, shots_plain, _, _ = simulate_war_net_damage(attacker, defender_plain, "nuke")

        # 100 / (25 * 0.75) = 5.33 → 6 launches; plain stays at 4.
        assert shots_vds == 6
        assert shots_plain == 4
        assert shots_vds > shots_plain

    def test_sim_metrics_populated(self):
        attacker = _nation(1, cities=[_city(1000)], warpolicy="Attrition")
        defender = _nation(2, cities=[_city(2200, 550)])

        metrics = compute_nuke_missile_metrics(attacker, defender)
        assert metrics is not None
        assert metrics.sim_nuke_shots >= 4
        assert metrics.sim_missile_shots >= 6
        assert metrics.sim_nuke_net != metrics.nuke_net

    def test_starting_resistance_is_pwpedia_default(self):
        assert DEFENDER_STARTING_RESISTANCE == 100
