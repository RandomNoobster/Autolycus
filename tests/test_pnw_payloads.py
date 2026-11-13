"""Tests for coercing subscription payloads the way pnwkit-py 2.6.26 did."""

import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from infra.pnw_payloads import PayloadTypeError, coerce_payload, model_typename


def test_nation_fields_are_coerced_like_pnwkit():
    row = coerce_payload(
        "nation",
        {
            "id": "42",
            "alliance_id": "0",
            "alliance_position": "MEMBER",
            "war_policy": 6,  # ordinals were never valid enum names: pnwkit stored None
            "government_type": "not-a-government",
            "last_active": "2026-11-12 10:20:30",
            "date": "2026-11-12T10:20:30.000000Z",
            "alliance_join_date": None,
            "global": 1,
            "score": "1.5",  # no converter: left as sent
        },
    )
    assert row == {
        "id": 42,
        "alliance_id": 0,
        "alliance_position": "MEMBER",
        "war_policy": None,
        "government_type": None,
        "last_active": "2026-11-12T10:20:30",
        "date": "2026-11-12T10:20:30+00:00",
        "alliance_join_date": None,
        "global_": 1,
        "score": "1.5",
    }


def test_nested_objects_convert_only_with_typename():
    row = coerce_payload(
        "nation",
        {
            "wars": [
                {
                    "__typename": "War",
                    "id": "9",
                    "war_type": "RAID",
                    "attacks": [{"__typename": "WarAttack", "id": "5", "type": "VICTORY"}],
                }
            ],
            "cities": [{"__typename": "City", "id": "1", "nuke_date": "0000-00-00"}],
            "military_research": {"ground_cost": "1"},  # no __typename: untouched
            "treasures": [{"nation_id": "3"}],  # first item has no __typename: untouched
            "bounties": {
                "__typename": "BountyPaginator",
                "data": [{"__typename": "Bounty", "id": "2"}],
            },
        },
    )
    assert row["wars"] == [
        {
            "__typename": "War",
            "id": 9,
            "war_type": "RAID",
            "attacks": [{"__typename": "WarAttack", "id": 5, "type": "VICTORY"}],
        }
    ]
    assert row["cities"] == [{"__typename": "City", "id": 1, "nuke_date": None}]
    assert row["military_research"] == {"ground_cost": "1"}
    assert row["treasures"] == [{"nation_id": "3"}]
    assert row["bounties"] == [{"__typename": "Bounty", "id": 2}]


def test_enum_names_newer_than_pnwkit_are_kept():
    # pnwkit 2.6.26 predates these and stored None; full scans store the names.
    row = coerce_payload(
        "nation",
        {
            "government_type": "MINDHIVE",
            "wars": [
                {
                    "__typename": "War",
                    "attacks": [{"__typename": "WarAttack", "type": "NAVALVAIR"}],
                }
            ],
        },
    )
    assert row["government_type"] == "MINDHIVE"
    assert row["wars"][0]["attacks"][0]["type"] == "NAVALVAIR"


@pytest.mark.parametrize(
    ("item", "error"),
    [
        ({"id": None}, TypeError),
        ({"last_active": "yesterday"}, ValueError),
        ({"alliance": {"__typename": "NoSuchType"}}, PayloadTypeError),
        ({"cities": [{"__typename": "City", "nuke_date": None}]}, AttributeError),
    ],
)
def test_uncoercible_items_raise_like_pnwkit(item, error):
    # pnwkit dropped these items; the scanner logs them as invalid and skips them.
    with pytest.raises(error):
        coerce_payload("nation", item)


def test_non_object_items_raise():
    with pytest.raises(TypeError):
        coerce_payload("nation", ["not", "a", "nation"])


def test_model_typename():
    assert model_typename("nation") == "Nation"
    assert model_typename("war_attack") == "WarAttack"
    assert model_typename("bbteam") == "Bbteam"
