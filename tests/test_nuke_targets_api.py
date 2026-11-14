"""API tests for nuke targets route (minimal Flask app, temporary SQLite caches)."""

import contextlib
import os
import sqlite3
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import api.routes.nuke_targets as nuke_routes
from api.routes.nuke_targets import apply_attacker_damage_overrides, nuke_targets_bp
from database.sqlite_cache import ensure_table_and_columns, upsert


@pytest.fixture
def db_paths(tmp_path, monkeypatch):
    nations = tmp_path / "nations.db"
    alliances = tmp_path / "alliances.db"
    monkeypatch.setattr(nuke_routes, "get_nations_db_path", lambda: nations)
    monkeypatch.setattr(nuke_routes, "get_alliances_db_path", lambda: alliances)
    return nations, alliances


@pytest.fixture
def client(db_paths):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(nuke_targets_bp)
    with app.test_client() as client:
        yield client


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
        "cities": [{"infrastructure": 2000, "land": 2000}],
        "wars": [],
        "def_slots": 0,
        "time_since_war": "14+",
    }
    row.update(fields)
    return row


def test_nuke_targets_route_returns_json(client):
    # Before the scanner has written anything there is no nations table: empty list.
    response = client.get("/api/nuke-targets/?minScore=15&maxScore=50000")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload is not None
    assert "targets" in payload
    assert "assumptions" in payload
    assert payload["assumptions"]["warType"] == "ATTRITION"
    assert payload["targets"] == []


def test_targets_get_metrics_against_the_requested_attacker(client, db_paths):
    nations, alliances = db_paths
    _store(alliances, "alliances", [{"id": 7, "name": "Seven", "color": "red"}])
    _store(nations, "nations", [
        _nation(1, warpolicy="Attrition"),
        # Alliance JSON missing (a live update cleared it): the name comes from alliances.db.
        _nation(2, alliance_id=7, alliance=None, def_slots=2, time_since_war=0),
        # A malformed wars blob must not fail the whole list.
        _nation(3, wars=[{"turnsleft": None}, "not a war"]),
        _nation(4, vacation_mode_turns=5),
    ])

    payload = client.get("/api/nuke-targets/?attackerNationId=1").get_json()

    by_id = {t["id"]: t for t in payload["targets"]}
    assert sorted(by_id) == [2, 3]  # attacker and the VM nation are left out
    assert payload["attacker"]["id"] == 1
    assert by_id[2]["allianceName"] == "Seven"
    assert by_id[2]["allianceId"] == "7"
    assert by_id[2]["defSlots"] == 2 and by_id[2]["timeSinceWar"] == 0
    assert by_id[3]["nukeDamage"] > 0
    assert by_id[3]["allianceId"] == "0" and by_id[3]["allianceName"] == "None"


def test_without_an_attacker_targets_show_infra_and_projects(client, db_paths):
    nations, _ = db_paths
    _store(nations, "nations", [
        _nation(5, vital_defense_system=True, war_policy="TURTLE",
                cities=[{"infrastructure": 1500.25, "land": 900}]),
    ])

    [target] = client.get("/api/nuke-targets/").get_json()["targets"]
    assert target["maxInfra"] == 1500.25
    assert target["vds"] is True
    assert target["defenderWarPolicy"] == "TURTLE"
    assert "nukeDamage" not in target


def test_apply_attacker_damage_overrides_attrition_and_satellite():
    attacker = {
        "id": 1,
        "warpolicy": "Turtle",
        "guiding_satellite": False,
    }
    forced = apply_attacker_damage_overrides(
        attacker, attrition=True, guiding_satellite=True
    )
    assert forced["warpolicy"] == "Attrition"
    assert forced["guiding_satellite"] is True
    assert attacker["warpolicy"] == "Turtle"
    assert attacker["guiding_satellite"] is False

    cleared = apply_attacker_damage_overrides(
        {"id": 2, "warpolicy": "Attrition", "guiding_satellite": True},
        attrition=False,
        guiding_satellite=False,
    )
    assert cleared["warpolicy"] == "None"
    assert cleared["guiding_satellite"] is False
