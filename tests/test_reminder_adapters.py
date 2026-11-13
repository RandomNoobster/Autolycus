"""Tests for the reminder adapters: P&W status, rendering, web push, storage and bot wiring."""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.reminders import notices, render, runtime, status
from database import reminders as reminder_db
from infra import webpush
from logic import reminders as rules

UTC = timezone.utc


def at(hour, minute=0):
    return datetime(2026, 9, 14, hour, minute, tzinfo=UTC)


# --- Status fetcher ---------------------------------------------------------


def _fetch_with(monkeypatch, response):
    async def fake_call(query, api_key):
        return response

    monkeypatch.setattr(status.api_client, "call", fake_call)
    return asyncio.run(status.PnwStatusFetcher("key").fetch(["100", "200"]))


def test_status_rows_are_read(monkeypatch):
    rows = [{"id": "100", "beige_turns": 3, "vacation_mode_turns": None}]
    assert _fetch_with(monkeypatch, {"data": {"nations": {"data": rows}}}) == {"100": (3, 0)}


@pytest.mark.parametrize(
    "response",
    [
        {"data": None, "errors": [{"message": "boom"}]},
        {"data": {"nations": None}, "errors": [{"message": "boom"}]},
        {"data": {"nations": {"data": []}}, "errors": [{"message": "partial"}]},
        {"data": {}},
        None,
    ],
)
def test_bad_status_responses_raise_instead_of_reporting_nations_missing(monkeypatch, response):
    # Missing nations get their reminders removed, so an error must not look like "none".
    with pytest.raises(status.StatusFetchError):
        _fetch_with(monkeypatch, response)


# --- Rendering --------------------------------------------------------------


def test_economy_lines_use_the_values_stored_for_the_raids_page():
    text = render.economy_lines({"nation_loot_value": 0, "monetary_net_num": 1234567.4})
    assert "Previous beige loot: **$0**" in text
    assert "Net income: **$1,234,567**" in text
    assert render.economy_lines({}).count("Unknown") == 3


def test_reminder_sent_after_its_due_time_says_it_is_late(monkeypatch):
    monkeypatch.setattr(render, "get_nation_by_id", lambda path, nation_id: {"nation": None, "last_fetched": None})
    monkeypatch.setattr(render, "get_nations_db_path", lambda: "unused")
    job = {"nation_id": "100", "kind": rules.JOB_KIND_LEAD, "offset_min": 60, "exit_at": at(14), "due_at": at(13)}

    on_time = asyncio.run(render.ReminderRenderer().render(job, None, at(13)))
    late = asyncio.run(render.ReminderRenderer().render(job, None, at(13, 50)))

    assert on_time.push_payload["notification"]["title"].endswith("in 1 hour")
    assert late.push_payload["notification"]["title"].endswith("in 10 minutes")
    assert "Late reminder" in late.embed["description"]
    assert "Late reminder" not in on_time.embed["description"]


# --- Web push ---------------------------------------------------------------


@pytest.mark.parametrize("subject", ["https://example.com/", "https://example.com/contact", "mailto:me@example"])
def test_vapid_subject_rejected_by_py_vapid_fails_at_startup(subject):
    private_key, _ = webpush.generate_vapid_keys()
    with pytest.raises(Exception):
        webpush.WebPushSender(private_key, subject)


def test_valid_vapid_subject_is_accepted():
    private_key, public_key = webpush.generate_vapid_keys()
    assert webpush.WebPushSender(private_key, "mailto:ops@example.com").public_key == public_key


@pytest.mark.parametrize(
    "exc, outcome",
    [
        (webpush.WebPushException("missing keys"), webpush.PushOutcome.GONE),
        (ValueError("not a point"), webpush.PushOutcome.GONE),
        (UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad"), webpush.PushOutcome.FAILED),
        (webpush.VapidException("bad sub"), webpush.PushOutcome.FAILED),
        (TypeError("bug"), webpush.PushOutcome.FAILED),
        (KeyError("bug"), webpush.PushOutcome.FAILED),
    ],
)
def test_only_subscription_errors_delete_the_device(exc, outcome):
    assert webpush._exception_result(exc).outcome is outcome


# --- Storage ----------------------------------------------------------------


class RecordingCollection:
    def __init__(self):
        self.updates = []

    def update_one(self, query, update, upsert=False):
        self.updates.append((query, update))


def test_test_dm_keeps_a_known_good_dm_state():
    users = RecordingCollection()
    reminder_db.mark_dm_pending_sync({reminder_db.USERS: users}, 7, at(12))
    state_update = next(q for q, u in users.updates if "dm_delivery.state" in u["$set"])
    assert state_update["dm_delivery.state"] == {"$nin": [rules.DM_STATE_OK, rules.DM_STATE_CONFIRMED]}


def test_revived_job_drops_what_its_cancelled_run_left_behind():
    job = rules.PlannedJob("7:100:1:15", 7, "100", rules.JOB_KIND_LEAD, 15, at(14), at(13, 45))
    update = reminder_db._revive_update(job, at(13))
    assert update["$set"]["status"] == rules.JOB_PENDING and "created_at" not in update["$set"]
    assert {"finished_at", "expire_at", "claim_id"} <= set(update["$unset"])

    skipped = rules.PlannedJob(job.job_id, 7, "100", rules.JOB_KIND_LEAD, 15, at(14), at(13, 45),
                               status=rules.JOB_SKIPPED, reason="added_after_due")
    assert "expire_at" in reminder_db._revive_update(skipped, at(13))["$set"]


# --- Bot wiring -------------------------------------------------------------


class FakeBot:
    async def wait_until_ready(self):
        return None


def test_failed_crash_report_does_not_stop_reminder_delivery(monkeypatch):
    runs = []

    class Scheduler:
        async def run(self):
            runs.append(1)
            if len(runs) == 1:
                raise RuntimeError("mongo not ready")

    async def no_pending():
        return None

    async def broken_report(self, name, exc):
        raise OSError("discord unreachable")

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(runtime.notices, "load_pending", no_pending)
    monkeypatch.setattr(runtime, "build_scheduler", lambda bot, reporter=None: (Scheduler(), None))
    monkeypatch.setattr(runtime._Reporter, "on_crash", broken_report)
    monkeypatch.setattr(runtime.asyncio, "sleep", no_sleep)

    asyncio.run(runtime.run_reminders(FakeBot()))
    assert len(runs) == 2


def test_delivery_notice_is_kept_when_it_cannot_be_shown(monkeypatch):
    restored = []

    async def take(db, user_id):
        return {"dm_delivery": {"reason": "dms_closed"}}

    async def restore(db, user_id):
        restored.append(user_id)

    class Followup:
        async def send(self, **kwargs):
            raise RuntimeError("interaction expired")

    class Ctx:
        author = type("Author", (), {"id": 42})()
        followup = Followup()

    monkeypatch.setattr(notices, "get_db", lambda: None)
    monkeypatch.setattr(notices.reminder_db, "take_dm_notice", take)
    monkeypatch.setattr(notices.reminder_db, "restore_dm_notice", restore)
    notices.mark_pending(42)

    asyncio.run(notices.maybe_notify(Ctx()))
    assert restored == [42] and 42 in notices._pending
    notices._pending.discard(42)
