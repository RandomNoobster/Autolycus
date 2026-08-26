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
    """pnwkit serializes AttackType.VICTORY as integer 14 in subscription payloads."""
    nation = {
        "id": "55556",
        "wars": [
            {
                "date": "2026-08-17T19:43:00+00:00",
                "defid": "55556",
                "turnsleft": 0,
                "war_type": 2,  # RAID
                "attacker": {"war_policy": "FORTRESS"},
                "attacks": [
                    _victory_attack(type=14, money_looted=2_000_000, coal_looted=0, food_looted=0),
                ],
            }
        ],
    }
    assert compute_beige_loot(nation, SAMPLE_PRICES) == 2_000_000


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
        "type",
        "loot_info",
        "victor",
    ):
        assert field in q
