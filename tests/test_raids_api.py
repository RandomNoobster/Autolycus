"""API tests for the raid target list, live score and alliance search (temporary SQLite)."""

import contextlib
import os
import sqlite3
import sys

import pytest
from flask import Flask, request
from pymongo.errors import ServerSelectionTimeoutError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import api.request_utils as request_utils
import api.routes.raids as raids_routes
from database.sqlite_cache import ensure_table_and_columns, upsert


@pytest.fixture
def db_paths(tmp_path, monkeypatch):
    nations = tmp_path / "nations.db"
    alliances = tmp_path / "alliances.db"
    monkeypatch.setattr(raids_routes, "get_nations_db_path", lambda: nations)
    monkeypatch.setattr(raids_routes, "get_alliances_db_path", lambda: alliances)
    monkeypatch.setattr(raids_routes, "optional_session_profile", lambda: None)
    return nations, alliances


@pytest.fixture
def client(db_paths):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="test-secret")
    app.register_blueprint(raids_routes.raids_bp)
    with app.test_client() as test_client:
        yield test_client


def _store(path, table, rows):
    with contextlib.closing(sqlite3.connect(path)) as conn:
        for row in rows:
            ensure_table_and_columns(conn, table, row)
            upsert(conn, table, row)


def _nation(nid, **fields):
    row = {
        "id": nid,
        "nation_name": f"Nation {nid}",
        "leader_name": "Leader",
        "alliance_id": 0,
        "alliance_position": "NOALLIANCE",
        "score": 1000.0,
        "color": "red",
        "vacation_mode_turns": 0,
        "soldiers": 1000,
        "tanks": 10,
        "aircraft": 5,
        "ships": 1,
        "population": 100000,
    }
    row.update(fields)
    return row


def test_rows_with_null_unit_counts_do_not_fail_the_list(client, db_paths):
    nations, _ = db_paths
    _store(nations, "nations", [_nation(1), {"id": 2, "score": 900.0, "vacation_mode_turns": 0}])

    response = client.get("/api/raids/?attackerNationId=1")

    assert response.status_code == 200
    by_id = {t["id"]: t for t in response.get_json()["targets"]}
    assert set(by_id) == {1, 2}
    assert by_id[2]["groundWin"] > 0


def test_taxable_needs_a_member_on_the_alliance_color(client, db_paths):
    nations, alliances = db_paths
    _store(alliances, "alliances", [
        {"id": 7, "name": "Seven", "color": "red"},
        {"id": 8, "name": "Grays", "color": "gray"},
    ])
    _store(nations, "nations", [
        _nation(1, alliance_id=7, alliance_position="MEMBER"),
        _nation(2, alliance_id=7, alliance_position="APPLICANT"),
        _nation(3, alliance_id=7, alliance_position="MEMBER", color="blue"),
        _nation(4, alliance_id=8, alliance_position="MEMBER", color="gray"),
    ])

    targets = {t["id"]: t for t in client.get("/api/raids/").get_json()["targets"]}

    assert targets[1]["taxable"] is True
    assert targets[2]["taxable"] is False  # applicants are not in a tax bracket
    assert targets[3]["taxable"] is False
    assert targets[4]["taxable"] is False  # gray nations are never taxed


def test_alliance_missing_from_alliances_db_uses_the_nations_own_alliance(client, db_paths):
    nations, _ = db_paths
    _store(nations, "nations", [
        _nation(1, alliance_id=9, alliance_position="MEMBER",
                alliance={"id": "9", "name": "New Alliance", "color": "red"}),
    ])

    [target] = client.get("/api/raids/").get_json()["targets"]
    assert target["allianceName"] == "New Alliance"
    assert target["taxable"] is True


def test_watch_list_is_normalized_and_tolerates_null(client, db_paths, monkeypatch):
    nations, _ = db_paths
    _store(nations, "nations", [_nation(1), _nation(123)])
    monkeypatch.setattr(raids_routes, "optional_session_profile",
                        lambda: {"id": "1", "beige_alerts": ["0123", "123", "junk"]})

    payload = client.get("/api/raids/").get_json()
    assert payload["beigeAlerts"] == ["123"]
    assert payload["discordLinked"] is True
    assert {t["id"]: t["hasReminderActive"] for t in payload["targets"]} == {1: False, 123: True}

    monkeypatch.setattr(raids_routes, "optional_session_profile",
                        lambda: {"id": True, "beige_alerts": None})
    payload = client.get("/api/raids/").get_json()
    assert payload["beigeAlerts"] == []
    assert payload["discordLinked"] is False


def test_profile_read_failure_means_no_profile():
    class DownCollection:
        def find_one(self, *args, **kwargs):
            raise ServerSelectionTimeoutError("no servers")

    app = Flask(__name__)
    with app.test_request_context("/"):
        request.session_user_id = 7
        original = request_utils.get_sync_db
        request_utils.get_sync_db = lambda: {"global_users": DownCollection()}
        try:
            assert request_utils.optional_session_profile() is None
        finally:
            request_utils.get_sync_db = original


def test_empty_cache_lists_no_targets(client):
    response = client.get("/api/raids/")
    assert response.status_code == 200
    assert response.get_json()["targets"] == []


def test_live_score_rejects_ids_the_game_cannot_have(client, monkeypatch):
    def no_api(*args, **kwargs):
        raise AssertionError("no upstream call for an impossible id")

    monkeypatch.setattr(raids_routes.api_client, "call", no_api)
    response = client.get("/api/raids/nation/9223372036854775808/live")
    assert response.status_code == 404
    assert response.get_json()["code"] == "NATION_NOT_FOUND"


@pytest.mark.parametrize(("limit", "expected"), [("abc", 10), ("-1", 1), ("0", 1), ("500", 50)])
def test_alliance_search_limit_is_clamped(client, db_paths, limit, expected):
    _, alliances = db_paths
    _store(alliances, "alliances", [
        {"id": i, "name": f"Alliance {i:03d}", "acronym": "A"} for i in range(1, 80)
    ])
    response = client.get(f"/api/raids/alliances/search?q=alliance&limit={limit}")
    assert response.status_code == 200
    assert len(response.get_json()) == expected
