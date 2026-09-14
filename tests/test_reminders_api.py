"""API tests for reminder and browser push routes (bare Flask app, database calls patched)."""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import api.routes.push as push_routes
import api.routes.raids as raids_routes
import api.routes.reminder_views as reminder_views
from database import reminders as reminder_db
from services import reminders as reminder_service

UTC = timezone.utc
USER_ID = 7
SAME_ORIGIN = {"Sec-Fetch-Site": "same-origin"}


class FakeSender:
    public_key = "BPUBLICKEY"
    key_id = "abcdef0123456789"


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        CORS_ORIGINS=["http://localhost:5173"],
        AUTOLYCUS_WEB_BASE_URL="https://autolycus.example",
    )
    app.register_blueprint(raids_routes.raids_bp)
    app.register_blueprint(push_routes.push_bp)

    fake_db = object()
    monkeypatch.setattr(raids_routes, "get_sync_db", lambda: fake_db)
    monkeypatch.setattr(push_routes, "get_sync_db", lambda: fake_db)
    for module in (raids_routes, reminder_views, push_routes):
        monkeypatch.setattr(module, "get_push_sender", lambda: None)
    monkeypatch.setattr(reminder_db, "count_push_subscriptions_sync", lambda db, uid: 0)
    monkeypatch.setattr(reminder_db, "latest_test_dm_sync", lambda db, uid: None)
    monkeypatch.setattr(
        reminder_db,
        "get_profile_sync",
        lambda db, uid: {"user": uid, "beige_alerts": ["100"], "beige_alerts_config": [60, 15]},
    )

    with app.test_client() as test_client:
        with test_client.session_transaction() as session:
            session["discord_user_id"] = USER_ID
        yield test_client


def test_cross_site_writes_are_rejected(client):
    response = client.post(
        "/api/raids/reminders", json={"nationId": 100}, headers={"Sec-Fetch-Site": "cross-site"}
    )
    assert response.status_code == 403
    assert response.get_json()["code"] == "CROSS_SITE_REQUEST"


def test_untrusted_origin_is_rejected_without_fetch_metadata(client):
    response = client.put(
        "/api/raids/reminders/channels",
        json={"discordDm": True, "webPush": False},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_add_reminder_validates_nation_id(client):
    response = client.post("/api/raids/reminders", json={"nationId": "abc"}, headers=SAME_ORIGIN)
    assert response.status_code == 400
    assert response.get_json()["code"] == "VALIDATION_ERROR"


def test_add_reminder_returns_delivery_and_test_dm(client, monkeypatch):
    requested = datetime(2026, 9, 14, 12, tzinfo=UTC)
    calls = []

    def fake_add(db, uid, nation_id, **kwargs):
        calls.append((uid, nation_id))
        return reminder_service.AddReminderResult(
            True, {"_id": "t1", "state": "queued", "requested_at": requested}
        )

    monkeypatch.setattr(reminder_service, "add_reminder_sync", fake_add)
    response = client.post("/api/raids/reminders", json={"nationId": 100}, headers=SAME_ORIGIN)

    assert response.status_code == 200
    body = response.get_json()
    assert calls == [(USER_ID, "100")]
    assert body["beigeAlerts"] == ["100"]
    assert body["beigeAlertConfig"] == [60, 15]
    assert body["testDm"] == {
        "id": "t1",
        "state": "queued",
        "code": None,
        "reason": None,
        "requestedAt": "2026-09-14T12:00:00+00:00",
        "sentAt": None,
        "confirmedAt": None,
    }
    delivery = body["delivery"]
    assert delivery["channels"] == {"discordDm": True, "webPush": False}
    assert delivery["dm"]["state"] == "unknown"
    assert delivery["push"] == {"configured": False, "deviceCount": 0}
    assert delivery["needsAttention"] is False
    assert delivery["supportInviteUrl"].startswith("https://")


def test_get_reminders_includes_schedule(client, monkeypatch):
    exit_at = datetime(2026, 9, 14, 18, tzinfo=UTC)
    jobs = [
        {"nation_id": "100", "kind": "lead", "exit_at": exit_at, "due_at": exit_at - timedelta(minutes=15), "status": "pending"},
        {"nation_id": "100", "kind": "lead", "exit_at": exit_at, "due_at": exit_at - timedelta(minutes=60), "status": "sent"},
    ]
    monkeypatch.setattr(reminder_db, "upcoming_jobs_for_user_sync", lambda db, uid, now: jobs)
    monkeypatch.setattr(
        raids_routes,
        "get_nation_by_id",
        lambda path, nation_id: {"nation": {"nation_name": "Foo", "leader_name": "Bar", "beige_turns": 2}},
    )

    response = client.get("/api/raids/reminders")
    assert response.status_code == 200
    [item] = response.get_json()["reminders"]
    assert item["nationName"] == "Foo"
    assert item["exitAt"] == "2026-09-14T18:00:00+00:00"
    assert item["nextReminderAt"] == "2026-09-14T17:45:00+00:00"


def test_dm_failure_needs_attention(client, monkeypatch):
    monkeypatch.setattr(
        reminder_db,
        "get_profile_sync",
        lambda db, uid: {
            "user": uid,
            "beige_alerts": [],
            "dm_delivery": {"state": "failed", "code": 50278, "reason": "no_mutual_server"},
            "reminder_problems": [{"kind": "not_delivered", "nation_id": "100", "reminder_removed": True}],
        },
    )
    delivery = client.get("/api/raids/reminders/delivery").get_json()["delivery"]
    assert delivery["needsAttention"] is True
    assert delivery["dm"]["reason"] == "no_mutual_server"
    assert delivery["recentProblems"][0]["reminderRemoved"] is True


def test_channels_require_at_least_one(client):
    response = client.put(
        "/api/raids/reminders/channels", json={"discordDm": False, "webPush": False}, headers=SAME_ORIGIN
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "CHANNEL_REQUIRED"


def test_channels_reject_non_boolean_values(client):
    response = client.put(
        "/api/raids/reminders/channels", json={"discordDm": "yes", "webPush": False}, headers=SAME_ORIGIN
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "VALIDATION_ERROR"


def test_push_channel_needs_server_keys(client):
    response = client.put(
        "/api/raids/reminders/channels", json={"discordDm": True, "webPush": True}, headers=SAME_ORIGIN
    )
    assert response.status_code == 503
    assert response.get_json()["code"] == "PUSH_NOT_CONFIGURED"


def test_test_dm_is_rate_limited(client, monkeypatch):
    now = datetime.now(UTC)
    monkeypatch.setattr(
        reminder_db,
        "latest_test_dm_sync",
        lambda db, uid: {"_id": "t0", "state": "sent", "requested_at": now - timedelta(seconds=10)},
    )
    monkeypatch.setattr(reminder_db, "count_test_dms_since_sync", lambda db, uid, since: 1)
    response = client.post("/api/raids/reminders/test-dm", json={}, headers=SAME_ORIGIN)
    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 60


def test_test_dm_returns_the_one_already_on_its_way(client, monkeypatch):
    requested = datetime(2026, 9, 14, 12, tzinfo=UTC)
    monkeypatch.setattr(
        reminder_db, "latest_test_dm_sync", lambda db, uid: {"_id": "t9", "state": "queued", "requested_at": requested}
    )

    def fail(*args, **kwargs):
        raise AssertionError("a second test DM must not be created")

    monkeypatch.setattr(reminder_db, "create_test_dm_sync", fail)
    response = client.post("/api/raids/reminders/test-dm", json={}, headers=SAME_ORIGIN)
    assert response.status_code == 202
    assert response.get_json()["testDm"]["id"] == "t9"


def test_test_dm_is_queued(client, monkeypatch):
    created = []

    def fake_create(db, uid, source, now):
        created.append((uid, source))
        return {"_id": "t2", "state": "queued", "requested_at": now}, True

    monkeypatch.setattr(reminder_db, "count_test_dms_since_sync", lambda db, uid, since: 0)
    monkeypatch.setattr(reminder_db, "ensure_profile_sync", lambda db, uid: None)
    monkeypatch.setattr(reminder_db, "create_test_dm_sync", fake_create)
    response = client.post("/api/raids/reminders/test-dm", json={}, headers=SAME_ORIGIN)
    assert response.status_code == 202
    assert created == [(USER_ID, "website")]


def test_vapid_key_unavailable_when_push_is_off(client):
    response = client.get("/api/push/vapid-public-key")
    assert response.status_code == 503
    assert response.get_json()["code"] == "PUSH_NOT_CONFIGURED"


def test_vapid_key_is_served_when_configured(client, monkeypatch):
    monkeypatch.setattr(push_routes, "get_push_sender", lambda: FakeSender())
    assert client.get("/api/push/vapid-public-key").get_json() == {
        "publicKey": "BPUBLICKEY",
        "keyId": "abcdef0123456789",
    }


def test_register_device_rejects_unknown_push_hosts(client, monkeypatch):
    monkeypatch.setattr(push_routes, "get_push_sender", lambda: FakeSender())
    response = client.post(
        "/api/push/subscriptions",
        json={"endpoint": "https://evil.example/push", "keys": {"p256dh": "x", "auth": "y"}},
        headers=SAME_ORIGIN,
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_SUBSCRIPTION"


def test_remove_device_validates_id(client):
    response = client.delete("/api/push/subscriptions/not-a-device", headers=SAME_ORIGIN)
    assert response.status_code == 400
