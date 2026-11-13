"""Tests for beige loot valuation (structured GraphQL fields + legacy loot_info)."""

from __future__ import annotations

from logic.common import (
    beige_loot_value,
    compute_beige_loot,
    structured_beige_loot_value,
)
from logic import queries
from logic.merge_utils import get_query


SAMPLE_PRICES = {
    "money": 1,
    "coal": 10,
    "oil": 20,
    "uranium": 30,
    "iron": 40,
    "bauxite": 50,
    "lead": 60,
    "gasoline": 70,
    "munitions": 80,
    "steel": 90,
    "aluminum": 100,
    "food": 5,
}


def _victory_attack(**overrides):
    attack = {
        "type": "VICTORY",
        "victor": "999",
        "loot_info": None,
        "money_looted": 1_000_000,
        "coal_looted": 10,
        "oil_looted": 0,
        "uranium_looted": 0,
        "iron_looted": 0,
        "bauxite_looted": 0,
        "lead_looted": 0,
        "gasoline_looted": 0,
        "munitions_looted": 0,
        "steel_looted": 0,
        "aluminum_looted": 0,
        "food_looted": 100,
    }
    attack.update(overrides)
    return attack


def test_structured_beige_loot_value_sums_resources():
    attack = _victory_attack()
    # 1_000_000*1 + 10*10 + 100*5 = 1_000_000 + 100 + 500 = 1_000_600
    assert structured_beige_loot_value(attack, SAMPLE_PRICES) == 1_000_600.0


def test_structured_beige_loot_value_none_without_fields():
    assert structured_beige_loot_value({"type": "GROUND", "moneystolen": 500}, SAMPLE_PRICES) is None


def test_structured_beige_loot_value_none_when_all_null():
    """GraphQL/pnwkit often include *_looted keys as null — that is not a 0 total."""
    attack = {
        "type": "VICTORY",
        "money_looted": None,
        "coal_looted": None,
        "oil_looted": None,
        "uranium_looted": None,
        "iron_looted": None,
        "bauxite_looted": None,
        "lead_looted": None,
        "gasoline_looted": None,
        "munitions_looted": None,
        "steel_looted": None,
        "aluminum_looted": None,
        "food_looted": None,
    }
    assert structured_beige_loot_value(attack, SAMPLE_PRICES) is None


def test_compute_beige_loot_falls_back_when_structured_fields_are_null():
    """Null *_looted keys must not mask a usable loot_info string as $0."""
    loot_info = (
        "Sparkle won the war and looted $16,754, 77 Coal, 11 Oil, 19 Uranium, "
        "68 Iron, 5 Bauxite, 15 Lead, 52 Gasoline, 242 Munitions, 31 Steel, "
        "35 Aluminum, and 2,422 Food. Kingdom of Svearmark also lost 4% of the "
        "infrastructure in each of their cities."
    )
    nation = {
        "id": "55556",
        "wars": [
            {
                "date": "2026-08-17T19:43:00+00:00",
                "defid": "55556",
                "turnsleft": 0,
                "war_type": "RAID",
                "attacker": {"war_policy": "FORTRESS"},
                "attacks": [
                    {
                        "type": "VICTORY",
                        "victor": "999",
                        "loot_info": loot_info,
                        "money_looted": None,
                        "coal_looted": None,
                        "oil_looted": None,
                        "uranium_looted": None,
                        "iron_looted": None,
                        "bauxite_looted": None,
                        "lead_looted": None,
                        "gasoline_looted": None,
                        "munitions_looted": None,
                        "steel_looted": None,
                        "aluminum_looted": None,
                        "food_looted": None,
                    }
                ],
            }
        ],
    }
    expected = beige_loot_value(loot_info, SAMPLE_PRICES)
    assert compute_beige_loot(nation, SAMPLE_PRICES) == expected
    assert expected > 0


def test_compute_beige_loot_uses_structured_fields_when_loot_info_empty():
    """Reproduce production failure mode: loot_info deprecated/empty, *_looted present."""
    nation = {
        "id": "55556",
        "wars": [
            {
                "date": "2026-08-17T19:43:00+00:00",
                "defid": "55556",
                "turnsleft": 0,
                "war_type": "RAID",
                "attacker": {"war_policy": "PIRATE", "advanced_pirate_economy": False},
                "attacks": [
                    {"type": "GROUND", "victor": "999", "moneystolen": 123},
                    _victory_attack(),
                ],
            }
        ],
    }
    loot = compute_beige_loot(nation, SAMPLE_PRICES)
    # RAID has no war-type undo; PIRATE divides by 1.4
    assert loot == int(round(1_000_600 / 1.4))


def test_compute_beige_loot_returns_none_when_only_empty_loot_info():
    """Legacy path: empty loot_info and no structured fields → no value (shows as $0)."""
    nation = {
        "id": "55556",
        "wars": [
            {
                "date": "2026-08-17T19:43:00+00:00",
                "defid": "55556",
                "turnsleft": 0,
                "war_type": "RAID",
                "attacker": {"war_policy": "FORTRESS"},
                "attacks": [
                    {"loot_info": None, "victor": "999", "moneystolen": 0},
                ],
            }
        ],
    }
    assert compute_beige_loot(nation, SAMPLE_PRICES) is None


def test_compute_beige_loot_falls_back_to_loot_info_text():
    loot_info = (
        "Sparkle won the war and looted $16,754, 77 Coal, 11 Oil, 19 Uranium, "
        "68 Iron, 5 Bauxite, 15 Lead, 52 Gasoline, 242 Munitions, 31 Steel, "
        "35 Aluminum, and 2,422 Food. Kingdom of Svearmark also lost 4% of the "
        "infrastructure in each of their cities."
    )
    nation = {
        "id": "55556",
        "wars": [
            {
                "date": "2026-08-17T19:43:00+00:00",
                "defid": "55556",
                "turnsleft": 0,
                "war_type": "RAID",
                "attacker": {"war_policy": "FORTRESS"},
                "attacks": [
                    {"loot_info": loot_info, "victor": "999"},
                ],
            }
        ],
    }
    expected = beige_loot_value(loot_info, SAMPLE_PRICES)
    assert compute_beige_loot(nation, SAMPLE_PRICES) == expected
    assert expected > 0


def test_compute_beige_loot_skips_alliance_loot():
    nation = {
        "id": "55556",
        "wars": [
            {
                "date": "2026-08-17T19:43:00+00:00",
                "defid": "55556",
                "turnsleft": 0,
                "war_type": "RAID",
                "attacker": {"war_policy": "FORTRESS"},
                "attacks": [
                    _victory_attack(type="ALLIANCELOOT", money_looted=9_999_999),
                ],
            }
        ],
    }
    assert compute_beige_loot(nation, SAMPLE_PRICES) is None


def test_compute_beige_loot_prefers_most_recent_finished_defensive_war():
    nation = {
        "id": "55556",
        "wars": [
            {
                "date": "2026-07-01T00:00:00+00:00",
                "defid": "55556",
                "turnsleft": 0,
                "war_type": "RAID",
                "attacker": {"war_policy": "FORTRESS"},
                "attacks": [_victory_attack(money_looted=100)],
            },
            {
                "date": "2026-08-17T00:00:00+00:00",
                "defid": "55556",
                "turnsleft": 0,
                "war_type": "RAID",
                "attacker": {"war_policy": "FORTRESS"},
                "attacks": [_victory_attack(money_looted=5_000_000, coal_looted=0, food_looted=0)],
            },
        ],
    }
    assert compute_beige_loot(nation, SAMPLE_PRICES) == 5_000_000


def _lost_raid_war(date, end_date=None, **attack_overrides):
    war = {
        "date": date,
        "defid": "55556",
        "turnsleft": 0,
        "war_type": "RAID",
        "attacker": {"war_policy": "FORTRESS"},
        "attacks": [_victory_attack(**attack_overrides)],
    }
    if end_date:
        war["end_date"] = end_date
    return war


_NO_RESOURCES = {"coal_looted": 0, "food_looted": 0}


def test_compute_beige_loot_uses_a_zero_result_from_the_latest_war():
    """A $0 latest defeat means the raider can expect nothing; older loot is stale."""
    nation = {
        "id": "55556",
        "wars": [
            _lost_raid_war("2026-07-01T00:00:00+00:00", money_looted=5_000_000, **_NO_RESOURCES),
            _lost_raid_war("2026-08-17T00:00:00+00:00", money_looted=0, **_NO_RESOURCES),
        ],
    }
    assert compute_beige_loot(nation, SAMPLE_PRICES) == 0


def test_compute_beige_loot_does_not_fall_back_when_the_latest_war_has_no_loot_data():
    nation = {
        "id": "55556",
        "wars": [
            _lost_raid_war("2026-07-01T00:00:00+00:00", money_looted=5_000_000, **_NO_RESOURCES),
            {
                "date": "2026-08-17T00:00:00+00:00",
                "defid": "55556",
                "turnsleft": 0,
                "war_type": "RAID",
                "winner": "999",
                "attacker": {"war_policy": "FORTRESS"},
                "attacks": [],
            },
        ],
    }
    # The latest defeat is unknown, so the estimate is unknown (the scanner keeps
    # its stored value) rather than the older $5M.
    assert compute_beige_loot(nation, SAMPLE_PRICES) is None


def test_compute_beige_loot_ranks_wars_by_end_date():
    nation = {
        "id": "55556",
        "wars": [
            # Declared first but lost last: this defeat set the current holdings.
            _lost_raid_war(
                "2026-11-01T00:00:00+00:00",
                end_date="2026-11-05T00:00:00+00:00",
                money_looted=300_000,
                **_NO_RESOURCES,
            ),
            _lost_raid_war(
                "2026-11-02T00:00:00+00:00",
                end_date="2026-11-03T00:00:00+00:00",
                money_looted=2_000_000,
                **_NO_RESOURCES,
            ),
        ],
    }
    assert compute_beige_loot(nation, SAMPLE_PRICES) == 300_000


def test_compute_beige_loot_keeps_the_defenders_own_policy():
    """Moneybags still cuts the next raid's loot, so the estimate isn't scaled back up."""
    war = _lost_raid_war("2026-08-17T00:00:00+00:00", money_looted=600_000, **_NO_RESOURCES)
    war["defender"] = {"war_policy": "MONEYBAGS"}
    assert compute_beige_loot({"id": "55556", "wars": [war]}, SAMPLE_PRICES) == 600_000


def test_compute_beige_loot_ignores_wars_that_were_not_lost():
    expired = {
        "date": "2026-09-01T00:00:00+00:00",
        "defid": "55556",
        "turnsleft": 0,
        "war_type": "RAID",
        "winner": "0",
        "attacker": {"war_policy": "FORTRESS"},
        "attacks": [],
    }
    nation = {
        "id": "55556",
        "wars": [
            _lost_raid_war("2026-08-17T00:00:00+00:00", money_looted=1_000, **_NO_RESOURCES),
            expired,
        ],
    }
    assert compute_beige_loot(nation, SAMPLE_PRICES) == 1_000


def test_compute_beige_loot_ordinary_war_type_multiplier():
    nation = {
        "id": "1",
        "wars": [
            {
                "date": "2026-08-17T00:00:00+00:00",
                "defid": "1",
                "turnsleft": 0,
                "war_type": "ORDINARY",
                "attacker": {"war_policy": "FORTRESS"},
                "attacks": [_victory_attack(money_looted=1000, coal_looted=0, food_looted=0)],
            }
        ],
    }
    # Ordinary undoes by *2
    assert compute_beige_loot(nation, SAMPLE_PRICES) == 2000


def test_compute_beige_loot_accepts_numeric_victory_type():
    """Rows stored via the old pnwkit subscription path hold AttackType.VICTORY as 14."""
    nation = {
        "id": "55556",
        "wars": [
            {
                "date": "2026-08-17T19:43:00+00:00",
                "defid": "55556",
                "turnsleft": 0,
                "war_type": 2,  # RAID
                "attacker": {"war_policy": 6},  # PIRATE
                "attacks": [
                    _victory_attack(type=14, money_looted=2_000_000, coal_looted=0, food_looted=0),
                ],
            }
        ],
    }
    assert compute_beige_loot(nation, SAMPLE_PRICES) == int(round(2_000_000 / 1.4))


def test_compute_beige_loot_falls_back_to_war_att_money_looted():
    nation = {
        "id": "55556",
        "wars": [
            {
                "date": "2026-08-17T19:43:00+00:00",
                "defid": "55556",
                "turnsleft": 0,
                "war_type": "RAID",
                "winner": "999",
                "att_money_looted": 1_250_000,
                "attacker": {"war_policy": "FORTRESS"},
                "attacks": [],  # bulk scans often omit nested attacks
            }
        ],
    }
    assert compute_beige_loot(nation, SAMPLE_PRICES) == 1_250_000


def _lost_offensive_war(date, war_type="RAID", defender=None, **attack_overrides):
    """A war nation 55556 declared on 999 and lost (999 looted it)."""
    return {
        "date": date,
        "attid": "55556",
        "defid": "999",
        "turnsleft": 0,
        "war_type": war_type,
        "attacker": {"war_policy": "FORTRESS"},
        "defender": defender or {"war_policy": "FORTRESS"},
        "attacks": [_victory_attack(**attack_overrides)],
    }


def test_compute_beige_loot_counts_a_war_the_nation_declared_and_lost():
    war = _lost_offensive_war(
        "2026-08-17T00:00:00+00:00",
        defender={"war_policy": "PIRATE", "advanced_pirate_economy": True},
        money_looted=1_540_000,
        **_NO_RESOURCES,
    )
    # The defender looted it, so the defender's Pirate and APE bonuses are undone.
    assert compute_beige_loot({"id": "55556", "wars": [war]}, SAMPLE_PRICES) == 1_000_000


def test_compute_beige_loot_uses_the_defenders_share_of_an_attrition_war():
    war = _lost_offensive_war(
        "2026-08-17T00:00:00+00:00", war_type="ATTRITION", money_looted=500_000, **_NO_RESOURCES
    )
    # A defender takes 50% of the loot in an attrition war (an attacker takes 25%).
    assert compute_beige_loot({"id": "55556", "wars": [war]}, SAMPLE_PRICES) == 1_000_000


def test_compute_beige_loot_falls_back_to_def_money_looted_for_an_offensive_defeat():
    war = {
        "date": "2026-08-17T00:00:00+00:00",
        "attid": "55556",
        "defid": "999",
        "turnsleft": 0,
        "war_type": "ORDINARY",
        "winner": "999",
        "att_money_looted": 9_999_999,  # what the nation looted earlier, not its loss
        "def_money_looted": 400_000,
        "defender": {"war_policy": "FORTRESS"},
        "attacks": [],
    }
    assert compute_beige_loot({"id": "55556", "wars": [war]}, SAMPLE_PRICES) == 800_000


def test_compute_beige_loot_ignores_wars_the_nation_won():
    defensive_loss = _lost_raid_war("2026-08-01T00:00:00+00:00", money_looted=700_000, **_NO_RESOURCES)
    offensive_win = _lost_offensive_war(
        "2026-08-17T00:00:00+00:00", victor="55556", money_looted=3_000_000, **_NO_RESOURCES
    )
    nation = {"id": "55556", "wars": [defensive_loss, offensive_win]}
    assert compute_beige_loot(nation, SAMPLE_PRICES) == 700_000


def test_compute_beige_loot_ignores_attacks_in_a_war_recorded_as_won():
    war = _lost_raid_war("2026-08-17T00:00:00+00:00", money_looted=700_000, **_NO_RESOURCES)
    war["winner"] = "55556"
    assert compute_beige_loot({"id": "55556", "wars": [war]}, SAMPLE_PRICES) is None


def test_compute_beige_loot_needs_a_victor_to_count_an_offensive_defeat():
    war = _lost_offensive_war(
        "2026-08-17T00:00:00+00:00", victor=None, money_looted=3_000_000, **_NO_RESOURCES
    )
    assert compute_beige_loot({"id": "55556", "wars": [war]}, SAMPLE_PRICES) is None


def test_compute_beige_loot_treats_a_war_it_did_not_defend_as_declared():
    """Rows scanned before attid was queried only carry defid."""
    war = _lost_offensive_war("2026-08-17T00:00:00+00:00", money_looted=250_000, **_NO_RESOURCES)
    del war["attid"]
    assert compute_beige_loot({"id": "55556", "wars": [war]}, SAMPLE_PRICES) == 250_000


def test_compute_beige_loot_picks_the_latest_defeat_on_either_side():
    nation = {
        "id": "55556",
        "wars": [
            _lost_raid_war("2026-08-01T00:00:00+00:00", money_looted=700_000, **_NO_RESOURCES),
            _lost_offensive_war("2026-08-10T00:00:00+00:00", money_looted=90_000, **_NO_RESOURCES),
        ],
    }
    assert compute_beige_loot(nation, SAMPLE_PRICES) == 90_000


def test_normalize_attack_type_maps_ordinals():
    from logic.common import normalize_attack_type
    assert normalize_attack_type(14) == "VICTORY"
    assert normalize_attack_type("14") == "VICTORY"
    assert normalize_attack_type("VICTORY") == "VICTORY"
    assert normalize_attack_type("AttackType.VICTORY") == "VICTORY"


def test_background_scanner_query_requests_structured_loot_fields():
    q = get_query(queries.BACKGROUND_SCANNER)
    for field in (
        "money_looted",
        "coal_looted",
        "food_looted",
        "att_money_looted",
        "def_money_looted",
        "attid",
        "type",
        "loot_info",
        "victor",
    ):
        assert field in q
    # Nation.wars already returns finished wars by default; do not require active:false.
    assert "wars(active:false)" not in q
