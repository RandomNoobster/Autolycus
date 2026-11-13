"""Tests for database.sqlite_cache readers (scratch SQLite files, no real data)."""
import json
import sqlite3

import pytest

from database import sqlite_cache


def _make_nations_db(path, rows):
    conn = sqlite3.connect(str(path))
    try:
        sqlite_cache.ensure_table_and_columns(conn, "nations", rows[0])
        for row in rows:
            sqlite_cache.upsert(conn, "nations", row)
    finally:
        conn.close()


def _nation(nation_id, **fields):
    row = {
        "id": nation_id,
        "nation_name": f"Nation {nation_id}",
        "leader_name": f"Leader {nation_id}",
        "discord": "",
        "alliance_id": "0",
        "cities": [{"infrastructure": 100.0}],
    }
    row.update(fields)
    return row


@pytest.fixture
def nations_db(tmp_path, monkeypatch):
    path = tmp_path / "nations.db"
    _make_nations_db(
        path,
        [
            _nation(300, nation_name="Athens"),
            _nation(999, nation_name="Sparta300", alliance_id="4729"),
            _nation(1984, nation_name="1984", leader_name="NaN"),
            _nation(500, nation_name="Mallory", discord="123456789012345678"),
            _nation(600, nation_name="Null Land", leader_name="null", discord="tester"),
        ],
    )
    monkeypatch.setattr(sqlite_cache, "get_nations_db_path", lambda: path)
    return path


def test_decode_row_keeps_scalar_text_as_text(nations_db):
    nation = sqlite_cache.get_nation_by_id(nations_db, 999)["nation"]
    assert nation["alliance_id"] == "4729"
    assert nation["cities"] == [{"infrastructure": 100.0}]

    odd = sqlite_cache.get_nation_by_id(nations_db, 1984)["nation"]
    assert odd["nation_name"] == "1984"
    assert odd["leader_name"] == "NaN"
    # Valid JSON for the API: no bare NaN/Infinity from player-chosen names.
    json.dumps(odd, allow_nan=False)


def test_all_readers_agree_on_column_types(nations_db):
    from_all = {n["id"]: n for n in sqlite_cache.get_all_nations(nations_db)["nations"]}
    from_filtered = {
        n["id"]: n for n in sqlite_cache.get_all_nations_filtered(nations_db)["nations"]
    }
    for nation_id, nation in from_all.items():
        assert nation == from_filtered[nation_id]


def test_find_nation_does_not_pull_ids_out_of_names(nations_db):
    assert sqlite_cache.find_nation("Sparta300")["id"] == 999


def test_find_nation_accepts_ids_and_links(nations_db):
    assert sqlite_cache.find_nation("300")["id"] == 300
    assert sqlite_cache.find_nation(300)["id"] == 300
    assert sqlite_cache.find_nation("https://politicsandwar.com/nation/id=300")["id"] == 300


def test_find_nation_handles_numbers_too_large_for_sqlite(nations_db):
    assert sqlite_cache.find_nation("9" * 25) is None


def test_find_nation_never_matches_a_discord_user_id_against_the_free_text_field(nations_db):
    # Nation 500's player typed someone else's Discord id into the Discord field.
    assert sqlite_cache.find_nation(123456789012345678) is None
    assert sqlite_cache.find_nation("123456789012345678") is None


def test_find_nation_still_matches_names_and_discord_usernames(nations_db):
    assert sqlite_cache.find_nation("athens")["id"] == 300
    assert sqlite_cache.find_nation("1984")["id"] == 1984
    assert sqlite_cache.find_nation("Tester")["id"] == 600


def test_get_nation_search_rows_reads_only_search_columns(nations_db):
    rows = sqlite_cache.get_nation_search_rows(nations_db)
    assert {row["id"] for row in rows} == {300, 999, 1984, 500, 600}
    assert all(set(row) == {"id", "nation_name", "leader_name"} for row in rows)


def test_get_nation_search_rows_without_table(tmp_path):
    assert sqlite_cache.get_nation_search_rows(tmp_path / "empty.db") == []
