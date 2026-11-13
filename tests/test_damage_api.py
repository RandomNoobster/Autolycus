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
