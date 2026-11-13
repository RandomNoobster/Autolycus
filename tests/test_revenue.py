"""Tests for revenue calculation fixes in logic/revenue.py."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from logic.revenue import revenue_calc_sync

PRICES = {
    "coal": 100, "oil": 100, "uranium": 2000, "iron": 100, "bauxite": 100, "lead": 100,
    "gasoline": 3000, "munitions": 2000, "steel": 3500, "aluminum": 2500, "food": 150,
}
RADIATION = {"na": 0.0}
SEASONS = {"na": 1.0}
COLORS = {"beige": 0}


def _city(**overrides):
    city = {"infrastructure": 1000.0, "land": 1500.0, "date": "2020-01-01", "powered": True}
    city.update(overrides)
    return city


def _nation(cities, **overrides):
    nation = {
        "id": "1", "continent": "na", "num_cities": 10, "color": "beige", "dompolicy": "",
        "alliance_id": "0", "alliance": None, "wars": [], "cities": cities,
    }
    nation.update(overrides)
    return nation


def _single(city, **nation_overrides):
    return revenue_calc_sync(
        _nation([city], **nation_overrides), RADIATION, [], PRICES, COLORS, SEASONS, single_city=True
    )


def test_farms_pollute_two_each_and_green_tech_halves_it():
    plain = _single(_city(farm=10))
    green = _single(_city(farm=10), green_tech=True)
    none = _single(_city())

    assert plain["real_pollution"] - none["real_pollution"] == pytest.approx(20)
    assert green["real_pollution"] - none["real_pollution"] == pytest.approx(10)


def test_single_city_mode_charges_no_military_upkeep():
    """Builds adds unit upkeep itself, only when asked to."""
    civilian = _single(_city())
    military = _single(_city(barracks=5, factory=5, airforcebase=5, drydock=3))

    assert military["net_cash_num"] == civilian["net_cash_num"]


def test_iso_city_dates_are_accepted():
    date_only = _single(_city(date="2020-01-01"))
    iso = _single(_city(date="2020-01-01T00:00:00"))

    assert iso["population"] == pytest.approx(date_only["population"])


def test_hidden_spy_count_does_not_break_spy_upkeep():
    nation = _nation([_city()], spies=None)

    result = revenue_calc_sync(nation, RADIATION, [], PRICES, COLORS, SEASONS, include_spies=True)

    assert "net_cash_num" in result


def test_open_markets_bonus_is_shown_as_a_gain():
    nation = _nation([_city(farm=5)], dompolicy="Open Markets")

    result = revenue_calc_sync(nation, RADIATION, [], PRICES, COLORS, SEASONS)

    assert "Open Markets Bonus: $" in result["income_txt"]
    assert "Open Markets Bonus: $-" not in result["income_txt"]


def test_military_upkeep_uses_capacity_research():
    from logic.revenue import calculate_military_upkeep, unit_upkeep_rates

    nation = {
        "soldiers": 100_000, "tanks": 1_000, "aircraft": 100, "ships": 10, "missiles": 1, "nukes": 1,
        # Efficiency ("cost") research lowers buy costs, not upkeep.
        "military_research": {"ground_capacity": 2, "air_capacity": 1, "naval_capacity": 0,
                              "ground_cost": 20, "air_cost": 20, "naval_cost": 20},
        "wars": [],
    }
    upkeep, food = calculate_military_upkeep(nation, {})

    assert upkeep == pytest.approx(
        100_000 * (1.25 - 0.08) + 1_000 * (50 - 4) + 100 * (750 - 30) + 10 * 3300 + 21000 + 35000
    )
    assert food == pytest.approx(100_000 / (750 + 40))
    war_rates = unit_upkeep_rates({"military_research": None}, at_war=True)
    assert war_rates["soldiers"] == (1.88, 1 / 500) and war_rates["ships"][0] == 5000


def test_war_upkeep_matches_the_research_page_at_level_one():
    """Level 0 -> 1 values from the in-game Military Research page."""
    from logic.revenue import unit_upkeep_rates

    research = {"ground_capacity": 1, "air_capacity": 1, "naval_capacity": 1}
    peace = unit_upkeep_rates({"military_research": research}, at_war=False)
    war = unit_upkeep_rates({"military_research": research}, at_war=True)

    assert peace["soldiers"] == pytest.approx((1.21, 1 / 770))
    assert war["soldiers"] == pytest.approx((1.82, 1 / 530))
    assert (peace["tanks"][0], war["tanks"][0]) == (48, 72)
    assert (peace["aircraft"][0], war["aircraft"][0]) == (720, 980)
    assert (peace["ships"][0], war["ships"][0]) == (3240, 4900)
