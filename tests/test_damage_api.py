"""API tests for custom input validation on POST /api/damage/calculate.

Runs the real damage math on a bare Flask app; only the Politics & War API call is faked.
"""
import json
import logging
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import api.routes.damage as damage_routes

IDS = {"nation1Id": 1, "nation2Id": 2}


def _nation(nation_id):
    return {
        "id": str(nation_id),
        "nation_name": f"Nation {nation_id}",
        "population": 2_000_000,
        "warpolicy": "Attrition",
        "flag": "",
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


@pytest.fixture
def pnw_calls(monkeypatch):
    calls = []

    async def fake_call_pnw(query, **kwargs):
        calls.append(query)
        return {"data": {"nations": {"data": [_nation(1), _nation(2)]}}}

    monkeypatch.setattr(damage_routes, "_call_pnw", fake_call_pnw)
    return calls


@pytest.fixture
def client(pnw_calls):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(damage_routes.damage_bp)
    with app.test_client() as test_client:
        yield test_client


def _post(client, body):
    # json.dumps writes NaN/Infinity tokens, which Flask's JSON parser accepts.
    return client.post("/api/damage/calculate", data=json.dumps(body), content_type="application/json")


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"nation1": "soldiers"}, "nation1"),
        ({"nation2": [1]}, "nation2"),
        ({"nation1": 5}, "nation1"),
        ({"war": [1]}, "war"),
        ({"war": "RAID"}, "war"),
        ({"nation1": {"soldiers": "abc"}}, "nation1.soldiers"),
        ({"nation1": {"tanks": ""}}, "nation1.tanks"),
        ({"nation2": {"ships": [1]}}, "nation2.ships"),
        ({"nation1": {"aircraft": 10**12}}, "nation1.aircraft"),
        ({"nation1": {"soldiers": float("inf")}}, "nation1.soldiers"),
        ({"nation2": {"nukes": float("nan")}}, "nation2.nukes"),
        ({"nation1": {"cityInfrastructure": "lots", "cityLand": 2000}}, "nation1.cityInfrastructure"),
        ({"nation1": {"cityInfrastructure": -1, "cityLand": 2000}}, "nation1.cityInfrastructure"),
        ({"nation1": {"cityInfrastructure": 1e12, "cityLand": 2000}}, "nation1.cityInfrastructure"),
        ({"nation2": {"cityInfrastructure": float("nan"), "cityLand": 2000}}, "nation2.cityInfrastructure"),
        ({"nation2": {"cityLand": {}}}, "nation2.cityLand"),
        ({"nation1": {"cityLand": 0}}, "nation1.cityLand"),
        ({"nation1": {"cityInfrastructure": 2000}}, "nation1.cityLand"),
    ],
    ids=[
        "nation-string", "nation-list", "nation-number", "war-list", "war-string",
        "unit-non-numeric", "unit-empty-string", "unit-list", "unit-too-large",
        "unit-infinity", "unit-nan", "infra-non-numeric", "infra-negative",
        "infra-too-large", "infra-nan", "land-object", "land-zero", "land-missing",
    ],
)
def test_malformed_override_returns_400(client, pnw_calls, caplog, overrides, field):
    with caplog.at_level(logging.ERROR):
        response = _post(client, {**IDS, **overrides})

    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["field"] == field
    assert body["message"].startswith(field + " ")
    assert pnw_calls == [], "bad input should be rejected before calling the PnW API"
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR], caplog.text


def test_infinite_nation_id_is_treated_as_missing(client, pnw_calls):
    response = _post(client, {"nation1Id": float("inf"), "nation2Id": 2})

    assert response.status_code == 400
    assert response.get_json()["code"] == "MISSING_NATIONS"
    assert pnw_calls == []


@pytest.mark.parametrize("overrides", [{}, {"nation1": None, "nation2": None, "war": None}])
def test_missing_or_null_overrides_use_live_nations(client, overrides):
    response = _post(client, {**IDS, **overrides})

    assert response.status_code == 200
    nation1 = response.get_json()["inputs"]["nation1"]
    assert nation1["soldiers"] == 150_000
    assert nation1["cityInfrastructure"] == 2000.0


def test_valid_overrides_are_applied(client):
    response = _post(client, {
        **IDS,
        "nation1": {
            "soldiers": 100_000,
            "tanks": "5000",
            "aircraft": 1200.7,
            "ships": None,
            "warpolicy": "Turtle",
            "vds": True,
            "cityInfrastructure": 1800,
            "cityLand": "2000.5",
        },
        "nation2": {"ships": -5, "falloutShelter": True, "cityLand": 1500},
        "war": {"warType": "RAID", "nation1Fortified": True},
    })

    assert response.status_code == 200
    inputs = response.get_json()["inputs"]
    nation1, nation2 = inputs["nation1"], inputs["nation2"]
    assert nation1["soldiers"] == 100_000
    assert nation1["tanks"] == 5000
    assert nation1["aircraft"] == 1200
    assert nation1["ships"] == 200  # null leaves the live value
    assert nation1["warpolicy"] == "Turtle"
    assert nation1["vds"] is True
    assert (nation1["cityInfrastructure"], nation1["cityLand"]) == (1800.0, 2000.5)
    assert nation2["ships"] == 0  # negative counts clamp to 0
    assert nation2["falloutShelter"] is True
    assert (nation2["cityInfrastructure"], nation2["cityLand"]) == (0.0, 1500.0)
    assert inputs["war"]["warType"] == "RAID"
    assert inputs["war"]["nation1Fortified"] is True


def test_same_nation_keeps_each_sides_overrides(client):
    response = _post(client, {
        "nation1Id": 1,
        "nation2Id": 1,
        "nation1": {"aircraft": 3000},
        "nation2": {"aircraft": 500},
    })

    assert response.status_code == 200
    inputs = response.get_json()["inputs"]
    assert inputs["nation1"]["aircraft"] == 3000
    assert inputs["nation2"]["aircraft"] == 500


def test_custom_city_keeps_the_real_city_count(client, monkeypatch):
    async def three_cities(query, **kwargs):
        nation = _nation(1)
        nation["cities"] = [{"infrastructure": 2000.0, "land": 2500.0}] * 3
        return {"data": {"nations": {"data": [nation, _nation(2)]}}}

    monkeypatch.setattr(damage_routes, "_call_pnw", three_cities)
    response = _post(client, {**IDS, "nation1": {"cityInfrastructure": 1500, "cityLand": 2000}})

    assert response.status_code == 200
    assert response.get_json()["nations"]["nation1"]["numCities"] == 3


def test_get_unknown_nation_returns_404(client, monkeypatch, caplog):
    async def only_nation1(query, **kwargs):
        return {"data": {"nations": {"data": [_nation(1)]}}}

    monkeypatch.setattr(damage_routes, "_call_pnw", only_nation1)
    with caplog.at_level(logging.ERROR):
        response = client.get("/api/damage/?nation1=1&nation2=999999")

    assert response.status_code == 404
    assert response.get_json()["code"] == "NATION_NOT_FOUND"
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR], caplog.text


def _stats(body, scenario, side, attack_type, table="perAttack"):
    rows = body["scenarios"][scenario][side]["stats"][table]
    return next(row for row in rows if row["attackType"] == attack_type)


def test_defender_stats_describe_the_same_battle(client):
    body = _post(client, IDS).get_json()

    attacker_nuke = _stats(body, "nation1Attacks", "attacker", "nuke")
    defender_nuke = _stats(body, "nation1Attacks", "defender", "nuke")
    # The attacker pays the launch; the defender spends nothing on a nuke it receives.
    assert attacker_nuke["uraniumConsumed"] == 500
    assert attacker_nuke["gasConsumed"] == 500
    assert defender_nuke["uraniumConsumed"] == 0
    assert defender_nuke["gasConsumed"] == 0
    assert defender_nuke["damageReceived"] == attacker_nuke["damageDealt"]


def test_nuke_resistance_uses_the_defenders_vital_defense_system(client):
    plain = _post(client, IDS).get_json()
    attacker_vds = _post(client, {**IDS, "nation1": {"vds": True}}).get_json()
    defender_vds = _post(client, {**IDS, "nation2": {"vds": True}}).get_json()

    def per_resistance_cost(body):
        return _stats(body, "nation1Attacks", "attacker", "nuke", "perResistance")["moneyUsed"]

    # 1.75M launch money over 25 resistance, or 18.75 when 25% of nukes are shot down.
    assert per_resistance_cost(plain) == round(1_750_000 / 25)
    assert per_resistance_cost(attacker_vds) == per_resistance_cost(plain)
    assert per_resistance_cost(defender_vds) == round(1_750_000 / 18.75)


def test_battle_resistance_weights_each_victory_tier():
    results = {
        "nation1_ground_it": 0.5, "nation1_ground_mod": 0.25, "nation1_ground_pyr": 0.25,
        "nation1_air_it": 0.0, "nation1_air_mod": 1.0, "nation1_air_pyr": 0.0,
        "nation2_irond_mod": 0.7,
    }

    assert damage_routes._calculate_resistance(results, "nation1", "nation2", "ground") == pytest.approx(5 + 1.75 + 1)
    assert damage_routes._calculate_resistance(results, "nation1", "nation2", "airvinfra") == pytest.approx(9)
    assert damage_routes._calculate_resistance(results, "nation1", "nation2", "missile") == pytest.approx(18 * 0.7)


@pytest.mark.parametrize("limit,expected", [("-1", 1), ("0", 1), ("500", 50)])
def test_search_limit_is_clamped(monkeypatch, tmp_path, limit, expected):
    db_path = tmp_path / "nations.db"
    db_path.write_bytes(b"")
    rows = [{"id": i, "nation_name": f"Alpha {i}", "leader_name": "Leader"} for i in range(1, 80)]
    monkeypatch.setattr(damage_routes, "get_nations_db_path", lambda: db_path)
    monkeypatch.setattr(damage_routes, "get_nation_search_rows", lambda path: rows)
    app = Flask(__name__)
    app.register_blueprint(damage_routes.damage_bp)

    response = app.test_client().get(f"/api/damage/nations/search?q=alpha&limit={limit}")

    assert response.status_code == 200
    assert len(response.get_json()) == expected


def test_search_rejects_a_non_numeric_limit(client):
    response = client.get("/api/damage/nations/search?q=alpha&limit=abc")

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_PARAMETER"


def test_search_reuses_rows_until_the_database_changes(monkeypatch, tmp_path):
    db_path = tmp_path / "nations.db"
    db_path.write_bytes(b"one")
    loads = []

    def rows(path):
        loads.append(path)
        return [{"id": 7, "nation_name": f"Alpha {len(loads)}", "leader_name": "Leader"}]

    monkeypatch.setattr(damage_routes, "get_nations_db_path", lambda: db_path)
    monkeypatch.setattr(damage_routes, "get_nation_search_rows", rows)
    app = Flask(__name__)
    app.register_blueprint(damage_routes.damage_bp)
    client = app.test_client()

    assert client.get("/api/damage/nations/search?q=alpha").get_json()[0]["nationName"] == "Alpha 1"
    assert client.get("/api/damage/nations/search?q=alp").get_json()[0]["nationName"] == "Alpha 1"
    assert len(loads) == 1

    db_path.write_bytes(b"changed")  # the scanner rewrote nations.db
    assert client.get("/api/damage/nations/search?q=alpha").get_json()[0]["nationName"] == "Alpha 2"


def test_linked_war_preset_reads_the_snake_case_war_fields():
    war = {
        "id": "5", "war_type": "raid", "turns_left": 10, "att_id": "1", "def_id": "2",
        "ground_control": "2", "air_superiority": None, "naval_blockade": "0",
        "att_peace": False, "def_peace": True, "att_fortify": False, "def_fortify": True,
        "att_resistance": 80, "def_resistance": 40, "att_points": 9, "def_points": 4,
        "attacker": {"id": "1", "nation_name": "One"},
        "defender": {"id": "2", "nation_name": "Two", "flag": "f.png", "alliance": {"name": "Allies"}},
    }

    item = damage_routes._build_linked_war_preset_item(war, 1)

    assert (item["opponent_id"], item["opponent_name"], item["opponent_alliance_name"]) == (2, "Two", "Allies")
    assert (item["linked_stance"], item["your_maps"], item["enemy_resistance"]) == ("offensive", 9, 40)
    assert item["war"] == {
        "attackerId": 1, "defenderId": 2, "warType": "RAID",
        "groundControlId": 2, "airSuperiorityId": None, "navalBlockadeId": None,
        "nation1Fortified": False, "nation2Fortified": True,
        "attackerPeace": False, "defenderPeace": True,
    }


def test_finished_linked_war_is_skipped():
    war = {"att_id": "1", "def_id": "2", "turns_left": 0}

    assert damage_routes._build_linked_war_preset_item(war, 1) is None
