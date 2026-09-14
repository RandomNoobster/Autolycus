"""Unit tests for logic.reminders (pure reminder rules)."""
import base64
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from logic import reminders as r

UTC = timezone.utc
LEAD = r.JOB_KIND_LEAD
EARLY = r.JOB_KIND_EARLY_EXIT


def at(hour, minute=0, second=0, day=14):
    return datetime(2026, 9, day, hour, minute, second, tzinfo=UTC)


def reading(turns, when, vm=0, nation_id="100"):
    return r.NationStatus(nation_id, turns, vm, when)


def tracked(status):
    return r.TrackedNation(status, r.estimate_exit(status))


def sub(offsets=(15,), added=None, changed=None):
    return r.Subscription(
        user_id=7, nation_id="100", offsets=tuple(offsets), added_at=added, offsets_changed_at=changed
    )


def job(kind, offset, exit_at, status=r.JOB_PENDING):
    if kind == LEAD:
        job_id = r.lead_job_id(7, "100", exit_at, offset)
        due = exit_at - timedelta(minutes=offset)
    else:
        job_id = r.early_exit_job_id(7, "100", exit_at)
        due = exit_at
    return r.JobSnapshot(job_id, 7, "100", kind, offset, exit_at, due, status)


def definitive(exit_at):
    return r.ExitEstimate(exit_at, True)


# --- Turn maths -------------------------------------------------------------


def test_turn_start_is_previous_even_hour():
    assert r.turn_start(at(13, 45)) == at(12)
    assert r.turn_start(at(14)) == at(14)
    assert r.turn_start(at(14) - timedelta(seconds=1)) == at(12)


def test_naive_datetimes_are_treated_as_utc():
    assert r.turn_start(datetime(2026, 9, 14, 15, 30)) == at(14)


def test_provisional_window_is_longer_at_day_change():
    assert r.in_provisional_window(at(14, 5))
    assert not r.in_provisional_window(at(14, 10))
    assert r.in_provisional_window(at(0, 14, day=15))
    assert not r.in_provisional_window(at(0, 15, day=15))


# --- Exit estimates ---------------------------------------------------------


def test_one_turn_left_exits_at_next_turn_change():
    assert r.estimate_exit(reading(1, at(13, 30))) == definitive(at(14))


def test_exit_uses_the_longer_of_beige_and_vacation_mode():
    estimate = r.estimate_exit(reading(2, at(13, 30), vm=5))
    assert estimate == definitive(at(12) + timedelta(hours=10))


def test_unprotected_nation_has_no_exit():
    assert r.estimate_exit(reading(0, at(13, 30))) == definitive(None)


def test_stale_count_after_turn_change_keeps_previous_exit():
    previous = tracked(reading(3, at(13, 58)))
    assert previous.estimate == definitive(at(18))
    assert r.estimate_exit(reading(3, at(14, 2)), previous) == definitive(at(18))
    assert r.estimate_exit(reading(2, at(14, 2)), previous) == definitive(at(18))


def test_reading_in_window_without_history_is_not_definitive():
    assert r.estimate_exit(reading(3, at(14, 2))) == r.ExitEstimate(at(20), False)


def test_exit_detected_when_decrement_arrives_later_in_window():
    before = tracked(reading(1, at(13, 59)))
    stale_status = reading(1, at(14, 1))
    stale = r.TrackedNation(stale_status, r.estimate_exit(stale_status, before))
    assert stale.estimate == definitive(at(14))
    assert r.estimate_exit(reading(0, at(14, 3)), stale) == definitive(None)


def test_unexpected_change_in_window_waits_for_definitive_reading():
    before = tracked(reading(1, at(13, 59)))
    assert r.estimate_exit(reading(25, at(14, 1)), before).definitive is False


# --- Planning ---------------------------------------------------------------


def test_plans_a_job_per_timing():
    plan = r.plan_subscription(sub((60, 15)), definitive(at(18)), [], at(13))
    assert [(j.offset_min, j.due_at, j.status) for j in plan.create] == [
        (60, at(17), r.JOB_PENDING),
        (15, at(17, 45), r.JOB_PENDING),
    ]


def test_existing_jobs_are_not_duplicated():
    existing = [job(LEAD, 15, at(18))]
    assert r.plan_subscription(sub(), definitive(at(18)), existing, at(13)).is_empty


def test_moved_exit_cancels_and_replans():
    existing = [job(LEAD, 15, at(18))]
    plan = r.plan_subscription(sub(), definitive(at(20)), existing, at(13))
    assert plan.cancel == [(existing[0].job_id, "exit_changed")]
    assert [j.exit_at for j in plan.create] == [at(20)]


def test_removed_timing_is_cancelled():
    existing = [job(LEAD, 60, at(18)), job(LEAD, 15, at(18))]
    plan = r.plan_subscription(sub((15,)), definitive(at(18)), existing, at(13))
    assert plan.cancel == [(existing[0].job_id, "timing_removed")]
    assert plan.create == []


def test_timings_already_past_when_added_are_skipped():
    plan = r.plan_subscription(sub((60, 15), added=at(17, 50)), definitive(at(18)), [], at(17, 50))
    assert [(j.offset_min, j.status) for j in plan.create] == [(60, r.JOB_SKIPPED), (15, r.JOB_SKIPPED)]


def test_only_latest_missed_timing_is_sent_after_downtime():
    plan = r.plan_subscription(sub((60, 15), added=at(10)), definitive(at(18)), [], at(17, 50))
    outcome = {j.offset_min: (j.status, j.late) for j in plan.create}
    assert outcome == {60: (r.JOB_SKIPPED, False), 15: (r.JOB_PENDING, True)}


def test_legacy_reminder_without_added_time_is_never_sent_late():
    plan = r.plan_subscription(sub((15,)), definitive(at(18)), [], at(17, 50))
    assert [j.status for j in plan.create] == [r.JOB_SKIPPED]


def test_timing_added_after_its_due_time_is_not_sent_late():
    plan = r.plan_subscription(
        sub((60,), added=at(10), changed=at(17, 30)), definitive(at(18)), [], at(17, 40)
    )
    assert [j.status for j in plan.create] == [r.JOB_SKIPPED]


def test_missed_timing_right_before_exit_is_not_sent():
    plan = r.plan_subscription(sub((15,), added=at(10)), definitive(at(18)), [], at(17, 59, 45))
    assert [j.status for j in plan.create] == [r.JOB_SKIPPED]


def test_non_definitive_estimate_changes_nothing():
    assert r.plan_subscription(sub(), r.ExitEstimate(at(18), False), [], at(13)).is_empty


def test_early_exit_sends_one_notice_and_cancels_pending_timings():
    existing = [job(LEAD, 60, at(18), status=r.JOB_SENT), job(LEAD, 15, at(18))]
    plan = r.plan_subscription(sub((60, 15)), definitive(None), existing, at(15, 10))
    assert plan.cancel == [(existing[1].job_id, "exited_early")]
    assert [(j.kind, j.due_at) for j in plan.create] == [(EARLY, at(15, 10))]
    assert not plan.remove_subscription

    after = existing[:1] + [
        job(LEAD, 15, at(18), status=r.JOB_CANCELLED),
        job(EARLY, None, at(18)),
    ]
    assert r.plan_subscription(sub((60, 15)), definitive(None), after, at(15, 12)).is_empty


def test_reminder_removed_once_early_notice_is_sent():
    existing = [job(LEAD, 15, at(18), status=r.JOB_CANCELLED), job(EARLY, None, at(18), status=r.JOB_SENT)]
    plan = r.plan_subscription(sub(), definitive(None), existing, at(15, 20))
    assert plan.remove_subscription and plan.problem is None


def test_normal_exit_removes_reminder_without_problem():
    existing = [job(LEAD, 15, at(14), status=r.JOB_SENT)]
    plan = r.plan_subscription(sub(), definitive(None), existing, at(14, 12))
    assert plan.remove_subscription and plan.problem is None


def test_nation_never_protected_is_reported():
    plan = r.plan_subscription(sub(), definitive(None), [], at(13))
    assert plan.remove_subscription and plan.problem == r.PROBLEM_NOT_PROTECTED


def test_pending_early_notice_cancelled_when_protected_again():
    existing = [job(EARLY, None, at(18))]
    plan = r.plan_subscription(sub(), definitive(at(20)), existing, at(15))
    assert (existing[0].job_id, "protected_again") in plan.cancel


# --- Sending decisions ------------------------------------------------------


def test_only_latest_due_timing_sent_per_nation():
    first, second = job(LEAD, 60, at(18)), job(LEAD, 15, at(18))
    send, skip = r.select_sendable([first, second], at(17, 50))
    assert send == [second]
    assert skip == [(first, "superseded")]


def test_jobs_too_close_to_exit_are_dropped():
    late = job(LEAD, 1, at(18))
    assert r.select_sendable([late], at(17, 59, 45)) == ([], [(late, "too_late")])


def test_early_exit_notice_wins_over_timings():
    early, lead = job(EARLY, None, at(18)), job(LEAD, 15, at(18))
    send, skip = r.select_sendable([lead, early], at(15))
    assert send == [early]
    assert skip == [(lead, "exited_early")]


def test_burst_lead_scales_with_wave_size_and_is_capped():
    assert r.burst_lead_seconds(0, 25) == 0
    assert r.burst_lead_seconds(50, 25) == pytest.approx(2.5)
    assert r.burst_lead_seconds(10_000, 25) == 30


def test_message_nonce_is_short_and_order_independent():
    nonce = r.message_nonce(["b", "a"])
    assert nonce == r.message_nonce(["a", "b"])
    assert len(nonce) == r.DISCORD_NONCE_MAX_LENGTH


# --- Validation -------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ([15, 60, 15], [60, 15]),
        ([10080], [10080]),
        ([], None),
        ([0], None),
        ([10081], None),
        ([True], None),
        (["15"], None),
        (list(range(1, 12)), None),
        (None, None),
    ],
)
def test_sanitize_offsets(raw, expected):
    assert r.sanitize_offsets(raw) == expected


def test_effective_offsets_fall_back_to_default():
    assert r.effective_offsets([0, 5]) == [15]


@pytest.mark.parametrize("text, expected", [("15", 15), (" 90 ", 90), ("0", None), ("abc", None), ("10081", None)])
def test_parse_offset_minutes(text, expected):
    assert r.parse_offset_minutes(text) == expected


@pytest.mark.parametrize(
    "minutes, text",
    [(1, "1 minute"), (15, "15 minutes"), (60, "1 hour"), (90, "1 hour 30 minutes"), (1440, "1 day"), (2880, "2 days")],
)
def test_describe_offset(minutes, text):
    assert r.describe_offset(minutes) == text


@pytest.mark.parametrize("raw, expected", [("123", "123"), (123, "123"), ("0123", "123"), ("0", None), ("x1", None), (True, None)])
def test_normalize_nation_id(raw, expected):
    assert r.normalize_nation_id(raw) == expected


# --- Channels and Discord errors --------------------------------------------


def test_channel_settings_never_leave_everything_off():
    assert r.ChannelSettings.from_doc({"discord_dm": False, "web_push": False}) == r.ChannelSettings()
    assert r.ChannelSettings.from_doc({"discord_dm": False, "web_push": True}) == r.ChannelSettings(False, True)
    assert r.ChannelSettings.from_doc(None) == r.ChannelSettings(True, False)


def test_validate_channel_settings():
    assert r.validate_channel_settings(False, False, push_device_count=1, push_configured=True) == r.CHANNEL_REQUIRED
    assert r.validate_channel_settings(True, True, push_device_count=0, push_configured=True) == r.NO_PUSH_DEVICES
    assert r.validate_channel_settings(True, True, push_device_count=1, push_configured=False) == r.PUSH_NOT_CONFIGURED
    assert r.validate_channel_settings(False, True, push_device_count=2, push_configured=True) is None


def test_needs_attention_when_enabled_channel_is_broken():
    dm_only = r.ChannelSettings(True, False)
    assert r.needs_attention(dm_only, r.DM_STATE_FAILED, push_device_count=0, push_configured=True)
    assert not r.needs_attention(dm_only, r.DM_STATE_OK, push_device_count=0, push_configured=True)
    push_only = r.ChannelSettings(False, True)
    assert r.needs_attention(push_only, r.DM_STATE_FAILED, push_device_count=0, push_configured=True) is True
    assert not r.needs_attention(push_only, r.DM_STATE_FAILED, push_device_count=1, push_configured=True)


@pytest.mark.parametrize(
    "status, code, outcome, reason",
    [
        (403, 50007, r.DeliveryOutcome.REFUSED, r.DmFailureReason.DMS_CLOSED),
        (403, 50278, r.DeliveryOutcome.REFUSED, r.DmFailureReason.NO_MUTUAL_SERVER),
        (404, 10013, r.DeliveryOutcome.REFUSED, r.DmFailureReason.UNKNOWN_USER),
        (404, 10003, r.DeliveryOutcome.CHANNEL_GONE, None),
        (400, 40003, r.DeliveryOutcome.RETRY, None),
        (429, 0, r.DeliveryOutcome.RETRY, None),
        (503, 0, r.DeliveryOutcome.RETRY, None),
        (None, None, r.DeliveryOutcome.RETRY, None),
        (403, 50001, r.DeliveryOutcome.REFUSED, r.DmFailureReason.OTHER),
        (403, 0, r.DeliveryOutcome.RETRY, None),
        (400, 50035, r.DeliveryOutcome.FAILED, None),
    ],
)
def test_classify_discord_error(status, code, outcome, reason):
    assert r.classify_discord_error(status, code) == (outcome, reason)


# --- Push -------------------------------------------------------------------


@pytest.mark.parametrize(
    "endpoint, allowed",
    [
        ("https://fcm.googleapis.com/fcm/send/abc", True),
        ("https://updates.push.services.mozilla.com/wpush/v2/abc", True),
        ("https://wns2-db5p.notify.windows.com/w/?token=abc", True),
        ("https://web.push.apple.com/abc", True),
        ("http://fcm.googleapis.com/fcm/send/abc", False),
        ("https://fcm.googleapis.com.evil.example/abc", False),
        ("https://user:pw@fcm.googleapis.com/abc", False),
        ("https://fcm.googleapis.com:8443/abc", False),
        ("https://169.254.169.254/latest", False),
        ("not a url", False),
        (None, False),
    ],
)
def test_push_endpoint_allowlist(endpoint, allowed):
    assert r.is_allowed_push_endpoint(endpoint) is allowed


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def test_push_key_validation():
    point = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    assert r.valid_push_keys(_b64url(point), _b64url(os.urandom(16)))
    assert not r.valid_push_keys(_b64url(point[:30]), _b64url(os.urandom(16)))
    assert not r.valid_push_keys(_b64url(point), _b64url(os.urandom(8)))
    assert not r.valid_push_keys("%%%", "%%%")


def test_push_ttl_expires_shortly_after_exit():
    assert r.push_ttl_seconds(at(18), at(17, 45)) == 15 * 60 + 60
    assert r.push_ttl_seconds(at(18), at(18, 30)) == 60
    assert r.push_ttl_seconds(None, at(18)) == 60


def test_push_topic_fits_header_limit():
    assert r.push_topic("123456789") == "beige-123456789"
    assert len(r.push_topic("9" * 40)) == 32
