"""Tests for city build filtering and override helpers."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.sqlite_cache import fetch_build_rows, get_builds_db_path
from logic.builds import (
    _apply_overrides,
    get_continent_resources,
    get_restricted_mines,
    normalize_continent_code,
    parse_mmr,
)

ALL_MINES = ["coalmine", "oilwell", "uramine", "leadmine", "ironmine", "bauxitemine"]


def test_parse_mmr_slash_format_supports_multi_digit():
    assert parse_mmr("5/5/3/1") == (5, 5, 3, 1)
    assert parse_mmr("10/0/0/2") == (10, 0, 0, 2)
    assert parse_mmr("any") == (0, 0, 0, 0)


def test_parse_mmr_compact_four_digit():
    assert parse_mmr("1251") == (1, 2, 5, 1)
    assert parse_mmr("0250") == (0, 2, 5, 0)
    assert parse_mmr("0000") == (0, 0, 0, 0)


def test_parse_mmr_rejects_invalid():
    with pytest.raises(ValueError):
        parse_mmr("5/5/3")
    with pytest.raises(ValueError):
        parse_mmr("a/b/c/d")
    with pytest.raises(ValueError):
        parse_mmr("125")
    with pytest.raises(ValueError):
        parse_mmr("12510")


def test_normalize_continent_accepts_aliases():
    assert normalize_continent_code("North America") == "na"
    assert normalize_continent_code("north_america") == "na"
    assert normalize_continent_code("SA") == "sa"
    assert normalize_continent_code("not-a-place") is None


def test_restricted_mines_are_unavailable_not_available():
    na_available = set(get_continent_resources("na")["json_names"])
    na_restricted = set(get_restricted_mines("na"))
    assert na_available == {"coalmine", "ironmine", "uramine"}
    assert na_restricted == set(ALL_MINES) - na_available
    assert not na_available & na_restricted

    sa_restricted = set(get_restricted_mines("South America"))
    assert sa_restricted == {"coalmine", "ironmine", "uramine"}


def test_apply_overrides_clears_and_sets_policy_and_projects():
    nation = {
        "ironw": True,
        "massirr": True,
        "dompolicy": "Open Markets",
    }
    _apply_overrides(nation, ["massirr"], "")
    assert nation["ironw"] is False
    assert nation["massirr"] is True
    assert nation["dompolicy"] == ""

    _apply_overrides(nation, None, "Imperialism")
    assert nation["massirr"] is True  # projects unchanged when None
    assert nation["dompolicy"] == "Imperialism"


@pytest.mark.skipif(not get_builds_db_path().exists(), reason="city_builds.db not present")
def test_fetch_build_rows_uses_exact_mmr_and_restricted_mines():
    db_path: Path = get_builds_db_path()
    caps = {"hospital": 5, "recyclingcenter": 3, "bank": 5, "mall": 4}
    mmr = {"barracks": 5, "factory": 5, "airforcebase": 3, "drydock": 1}
    restricted = get_restricted_mines("na")

    rows = fetch_build_rows(db_path, 2000, mmr, caps, restricted)
    assert rows, "expected matching NA builds at 2000 infra"

    for row in rows:
        assert row["barracks"] == 5
        assert row["factory"] == 5
        assert row["airforcebase"] == 3
        assert row["drydock"] == 1
        for mine in restricted:
            assert row[mine] == 0

    # At least some rows should use an available NA mine (otherwise filter likely inverted).
    assert any(row["coalmine"] or row["ironmine"] or row["uramine"] for row in rows)
