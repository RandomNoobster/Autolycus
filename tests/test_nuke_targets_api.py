"""API tests for nuke targets route (minimal Flask app)."""

import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.routes.nuke_targets import apply_attacker_damage_overrides, nuke_targets_bp


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(nuke_targets_bp)
    with app.test_client() as client:
        yield client


def test_nuke_targets_route_returns_json(client):
    response = client.get("/api/nuke-targets/?minScore=15&maxScore=50000")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload is not None
    assert "targets" in payload
    assert "assumptions" in payload
    assert payload["assumptions"]["warType"] == "ATTRITION"
    assert isinstance(payload["targets"], list)


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
