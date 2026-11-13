"""API tests for non-object JSON body handling on auth and damage routes (bare Flask app, no database)."""
import logging
import os
import sqlite3
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import api.routes.auth as auth_routes
import api.routes.damage as damage_routes
from api.security import generate_token

AUTH_TOKEN_API_KEY = "test-auth-key"
DISCORD_BOT_API_KEY = "test-bot-key"

# Bodies sent with Content-Type: application/json that are not a JSON object:
# undecodable ones make get_json() raise, decodable non-objects have no .get().
BAD_BODIES = [
    pytest.param(b"", id="empty-body"),
    pytest.param(b"{not valid json", id="invalid-json"),
    pytest.param(b"[1, 2]", id="json-array"),
    pytest.param(b'"token"', id="json-string"),
    pytest.param(b"5", id="json-number"),
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
def test_non_object_json_body_returns_400(client, caplog, path, headers, expected_code, body):
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


@pytest.mark.parametrize("token", [5, True, 1.5, {"a": 1}, ["x"]])
def test_token_verify_rejects_non_string_token_without_500(client, caplog, token):
    with caplog.at_level(logging.ERROR):
        response = client.post("/api/auth/token/verify", json={"token": token})

    assert response.status_code == 401
    assert response.get_json()["code"] == "TOKEN_INVALID"
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR], caplog.text


def test_token_verify_enforces_the_lifetime_the_token_was_issued_with(app, client, monkeypatch):
    import api.security as security

    with app.app_context():
        token = generate_token(user_id=7, timestamp=1, data_type="raids", expires_in=60)

    real_time = security.time.time
    monkeypatch.setattr(security.time, "time", lambda: real_time() + 120)
    response = client.post("/api/auth/token/verify", json={"token": token})

    assert response.status_code == 401
    assert response.get_json()["code"] == "TOKEN_EXPIRED"


@pytest.mark.parametrize("code", [{"$ne": None}, {"$regex": "^a"}, ["x"], 5])
def test_token_exchange_rejects_non_string_code_before_querying(client, code):
    # The client fixture fails the test if the route touches the database.
    response = client.post("/api/auth/token/exchange", json={"code": code})

    assert response.status_code == 400
    assert response.get_json()["code"] == "VALIDATION_ERROR"


@pytest.fixture
def oauth_app(app):
    app.config.update(
        DISCORD_CLIENT_ID="client-id",
        DISCORD_CLIENT_SECRET="client-secret",
        DISCORD_REDIRECT_URI="https://autolycus.example/api/auth/discord/callback",
    )
    return app


@pytest.mark.parametrize(
    "target",
    ["//evil.example/login", "/\\evil.example", "https://evil.example", "evil.example", "/\t/evil.example"],
)
def test_oauth_start_keeps_redirects_on_site(oauth_app, target):
    with oauth_app.test_client() as test_client:
        response = test_client.get("/api/auth/discord/start", query_string={"redirect": target})
        assert response.status_code == 302
        with test_client.session_transaction() as session:
            assert session["oauth_redirect"] == "/raids"


def test_oauth_start_keeps_internal_redirect(oauth_app):
    with oauth_app.test_client() as test_client:
        test_client.get("/api/auth/discord/start", query_string={"redirect": "/damage?x=1"})
        with test_client.session_transaction() as session:
            assert session["oauth_redirect"] == "/damage?x=1"


def test_oauth_cancel_returns_user_to_the_app(oauth_app):
    with oauth_app.test_client() as test_client:
        with test_client.session_transaction() as session:
            session["oauth_state"] = "state-1"
            session["oauth_redirect"] = "/damage"

        response = test_client.get(
            "/api/auth/discord/callback",
            query_string={"error": "access_denied", "state": "state-1"},
        )

        assert response.status_code == 302
        assert response.headers["Location"] == "/damage"
        with test_client.session_transaction() as session:
            assert "oauth_state" not in session


def test_oauth_callback_never_redirects_off_site_from_a_stored_target(oauth_app, monkeypatch):
    monkeypatch.setattr(auth_routes, "_oauth_exchange_code_for_token", lambda code: {"access_token": "t"})
    monkeypatch.setattr(auth_routes, "_oauth_fetch_user", lambda token: {"id": "42", "username": "tester"})
    with oauth_app.test_client() as test_client:
        with test_client.session_transaction() as session:
            session["oauth_state"] = "state-1"
            session["oauth_redirect"] = "//evil.example/x"

        response = test_client.get(
            "/api/auth/discord/callback",
            query_string={"code": "c", "state": "state-1"},
        )

        assert response.status_code == 302
        assert response.headers["Location"] == "/raids"


class _FakeUsers:
    def __init__(self, profile):
        self.profile = profile

    def find_one(self, query):
        return self.profile


class _FakeDb:
    def __init__(self, profile):
        self.global_users = _FakeUsers(profile)


def _linked_nation_client(app, tmp_path, monkeypatch, profile):
    from database import sqlite_cache

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    conn = sqlite3.connect(str(data_dir / "nations.db"))
    row = {"id": 300, "nation_name": "Athens", "flag": "https://flags.example/athens.png"}
    sqlite_cache.ensure_table_and_columns(conn, "nations", row)
    sqlite_cache.upsert(conn, "nations", row)
    conn.close()

    app.root_path = str(tmp_path / "api")
    app.config["API_KEY"] = "server-key"
    monkeypatch.setattr(auth_routes, "get_sync_db", lambda: _FakeDb(profile))
    client = app.test_client()
    with client.session_transaction() as session:
        session["discord_user_id"] = 7
    return client


def test_linked_nation_reads_name_and_flag_from_the_scanner_cache(app, tmp_path, monkeypatch):
    def no_api_call(*args, **kwargs):
        raise AssertionError("cached nations must not spend the server API key")

    monkeypatch.setattr(auth_routes, "query_sync", no_api_call)
    client = _linked_nation_client(app, tmp_path, monkeypatch, {"user": 7, "id": "300"})

    body = client.get("/api/auth/linked-nation").get_json()

    assert body == {
        "authenticated": True,
        "linked": True,
        "nation_id": "300",
        "nation_name": "Athens",
        "flag_url": "https://flags.example/athens.png",
    }


@pytest.mark.parametrize("stored_id", [True, "", "abc", None])
def test_linked_nation_treats_malformed_ids_as_unlinked(app, tmp_path, monkeypatch, stored_id):
    monkeypatch.setattr(auth_routes, "query_sync", lambda *a, **k: pytest.fail("no lookup"))
    client = _linked_nation_client(app, tmp_path, monkeypatch, {"user": 7, "id": stored_id})

    body = client.get("/api/auth/linked-nation").get_json()

    assert body["linked"] is False
    assert body["nation_id"] is None


_VERIFY_OK = {"ok": True, "code": "SUCCESS", "nation_id": "300", "message": "ok", "relinked": False}
_MONTH = 30 * 24 * 3600


def _verify_client(app, monkeypatch, session_values, discord_user=None, discord_error=None):
    app.config["API_KEY"] = "server-key"
    monkeypatch.setattr(auth_routes, "get_sync_db", lambda: object())
    calls = []

    def fake_verify(**kwargs):
        calls.append(kwargs)
        return dict(_VERIFY_OK)

    def fake_fetch_user(token):
        if discord_error is not None:
            raise discord_error
        return discord_user

    monkeypatch.setattr(auth_routes, "verify_discord_nation_link_sync", fake_verify)
    monkeypatch.setattr(auth_routes, "_oauth_fetch_user", fake_fetch_user)
    client = app.test_client()
    with client.session_transaction() as session:
        session.update({"discord_user_id": 7, "discord_username": "oldname", **session_values})
    return client, calls


def test_verify_checks_the_current_discord_username(app, monkeypatch):
    import time

    client, calls = _verify_client(
        app,
        monkeypatch,
        {
            "discord_authenticated_at": int(time.time()) - _MONTH,
            "discord_access_token": "token",
            "discord_access_token_expires_at": int(time.time()) + 3600,
        },
        discord_user={"id": "7", "username": "newname"},
    )

    response = client.post("/api/auth/verify", json={"nationId": "300"})

    assert response.status_code == 200
    assert calls[0]["discord_username"] == "newname"
    with client.session_transaction() as session:
        assert session["discord_username"] == "newname"


def test_verify_asks_for_a_new_login_when_the_saved_username_is_too_old(app, monkeypatch):
    import time

    client, calls = _verify_client(
        app, monkeypatch, {"discord_authenticated_at": int(time.time()) - _MONTH}
    )

    response = client.post("/api/auth/verify", json={"nationId": "300"})

    assert response.status_code == 401
    assert response.get_json()["code"] == "REAUTH_REQUIRED"
    assert calls == []


def test_verify_trusts_a_recent_login_without_a_token(app, monkeypatch):
    import time

    client, calls = _verify_client(
        app, monkeypatch, {"discord_authenticated_at": int(time.time()) - 60}
    )

    response = client.post("/api/auth/verify", json={"nationId": "300"})

    assert response.status_code == 200
    assert calls[0]["discord_username"] == "oldname"


def test_verify_with_a_revoked_token_and_old_login_asks_for_a_new_login(app, monkeypatch):
    import time
    import urllib.error

    client, calls = _verify_client(
        app,
        monkeypatch,
        {
            "discord_authenticated_at": int(time.time()) - _MONTH,
            "discord_access_token": "token",
            "discord_access_token_expires_at": int(time.time()) + 3600,
        },
        discord_error=urllib.error.HTTPError("https://discord.com", 401, "Unauthorized", {}, None),
    )

    response = client.post("/api/auth/verify", json={"nationId": "300"})

    assert response.get_json()["code"] == "REAUTH_REQUIRED"
    assert calls == []


def test_verify_reports_discord_outage_instead_of_using_a_stale_name(app, monkeypatch):
    import time
    import urllib.error

    client, calls = _verify_client(
        app,
        monkeypatch,
        {
            "discord_authenticated_at": int(time.time()) - _MONTH,
            "discord_access_token": "token",
            "discord_access_token_expires_at": int(time.time()) + 3600,
        },
        discord_error=urllib.error.URLError("unreachable"),
    )

    response = client.post("/api/auth/verify", json={"nationId": "300"})

    assert response.status_code == 503
    assert response.get_json()["code"] == "DISCORD_UNAVAILABLE"
    assert calls == []


def test_oauth_callback_keeps_the_access_token_for_verification(oauth_app, monkeypatch):
    monkeypatch.setattr(
        auth_routes, "_oauth_exchange_code_for_token", lambda code: {"access_token": "t", "expires_in": 600}
    )
    monkeypatch.setattr(auth_routes, "_oauth_fetch_user", lambda token: {"id": "42", "username": "tester"})
    with oauth_app.test_client() as test_client:
        with test_client.session_transaction() as session:
            session["oauth_state"] = "state-1"

        test_client.get("/api/auth/discord/callback", query_string={"code": "c", "state": "state-1"})

        with test_client.session_transaction() as session:
            assert session["discord_access_token"] == "t"
            assert session["discord_access_token_expires_at"] - session["discord_authenticated_at"] == 600

        test_client.post("/api/auth/logout")
        with test_client.session_transaction() as session:
            assert "discord_access_token" not in session
            assert "discord_user_id" not in session


@pytest.mark.parametrize("path", ["/api/auth/verify", "/api/auth/unlink-nation", "/api/auth/logout"])
def test_cookie_authenticated_auth_writes_reject_cross_site_requests(client, path):
    response = client.post(path, json={}, headers={"Sec-Fetch-Site": "cross-site"})

    assert response.status_code == 403
    assert response.get_json()["code"] == "CROSS_SITE_REQUEST"
