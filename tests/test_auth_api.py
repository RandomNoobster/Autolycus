"""API tests for JSON body handling on auth routes (bare Flask app, no database)."""
import logging
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import api.routes.auth as auth_routes
import api.routes.damage as damage_routes
from api.security import generate_token

AUTH_TOKEN_API_KEY = "test-auth-key"
DISCORD_BOT_API_KEY = "test-bot-key"

# Bodies sent with Content-Type: application/json that get_json() cannot decode.
BAD_BODIES = [
    pytest.param(b"", id="empty-body"),
    pytest.param(b"{not valid json", id="invalid-json"),
]

# (path, extra headers, expected error code once the body is treated as {}).
ROUTES = [
    pytest.param("/api/auth/token/verify", {}, "TOKEN_MISSING", id="token-verify"),
    pytest.param("/api/auth/token/exchange", {}, "VALIDATION_ERROR", id="token-exchange"),
    pytest.param(
        "/api/auth/token/generate",
        {"X-Auth-Token": AUTH_TOKEN_API_KEY},
        "INVALID_USER",
        id="token-generate",
    ),
    pytest.param(
        "/api/auth/token/issue",
        {"X-Bot-Token": DISCORD_BOT_API_KEY},
        "INVALID_USER",
        id="token-issue",
    ),
    pytest.param("/api/auth/verify", {}, "VALIDATION_ERROR", id="discord-verify"),
    pytest.param("/api/damage/calculate", {}, "MISSING_NATIONS", id="damage-calculate"),
]


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        AUTH_TOKEN_API_KEY=AUTH_TOKEN_API_KEY,
        DISCORD_BOT_API_KEY=DISCORD_BOT_API_KEY,
    )
    app.register_blueprint(auth_routes.auth_bp)
    app.register_blueprint(damage_routes.damage_bp)
    return app


@pytest.fixture
def client(app, monkeypatch):
    def no_db():
        raise AssertionError("route should reject the body before touching the database")

    monkeypatch.setattr(auth_routes, "get_sync_db", no_db)

    with app.test_client() as test_client:
        with test_client.session_transaction() as session:
            session["discord_user_id"] = 7
            session["discord_username"] = "tester"
        yield test_client


@pytest.mark.parametrize("body", BAD_BODIES)
@pytest.mark.parametrize("path,headers,expected_code", ROUTES)
def test_undecodable_json_body_returns_400(client, caplog, path, headers, expected_code, body):
    with caplog.at_level(logging.ERROR):
        response = client.post(
            path,
            data=body,
            headers={"Content-Type": "application/json", **headers},
        )

    assert response.status_code == 400
    assert response.is_json
    assert response.get_json()["code"] == expected_code
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR], caplog.text


def test_token_verify_still_accepts_valid_token(app, client):
    with app.app_context():
        token = generate_token(user_id=7, timestamp=1, data_type="raids")

    response = client.post("/api/auth/token/verify", json={"token": token})

    assert response.status_code == 200
    body = response.get_json()
    assert body["valid"] is True
    assert body["payload"]["user_id"] == 7
