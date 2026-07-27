"""API tests for nuke targets route (minimal Flask app)."""

import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.routes.nuke_targets import nuke_targets_bp


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
