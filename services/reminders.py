"""Reminder flows shared by the API (sync) and the bot (async).

Validation lives in ``logic.reminders`` and storage in ``database.reminders``. This
module decides what happens when someone adds or removes a reminder, changes
delivery channels, registers a push device or asks for a test DM.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional

from database import reminders as reminder_db
from logic import reminders as rules

TEST_DM_MIN_INTERVAL = timedelta(minutes=1)
TEST_DM_DAILY_LIMIT = 10

INVALID_SUBSCRIPTION = "INVALID_SUBSCRIPTION"
DEVICE_LIMIT = "DEVICE_LIMIT"

TEST_DM_SOURCE_WEBSITE = "website"
TEST_DM_SOURCE_BOT = "bot"
TEST_DM_SOURCE_AUTOMATIC = "automatic"


@dataclass(frozen=True)
class AddReminderResult:
    """Outcome of adding a nation to a watch list."""

    added: bool
    test_dm: Optional[dict[str, Any]] = None


def _should_auto_test(profile: Optional[Mapping[str, Any]]) -> bool:
    """A user's first reminder checks DM delivery unless DMs are already known to work."""
    if reminder_db.watched_nation_ids(profile):
        return False
    channels = rules.ChannelSettings.from_doc((profile or {}).get("reminder_channels"))
    state = ((profile or {}).get("dm_delivery") or {}).get("state") or rules.DM_STATE_UNKNOWN
    return channels.discord_dm and state in (rules.DM_STATE_UNKNOWN, rules.DM_STATE_FAILED)


def _retry_after(
    latest: Optional[Mapping[str, Any]], recent_count: int, now: datetime
) -> Optional[int]:
    requested_at = (latest or {}).get("requested_at")
    if isinstance(requested_at, datetime):
        elapsed = now - rules.ensure_utc(requested_at)
        if elapsed < TEST_DM_MIN_INTERVAL:
            return max(1, math.ceil((TEST_DM_MIN_INTERVAL - elapsed).total_seconds()))
    if recent_count >= TEST_DM_DAILY_LIMIT:
        return 60 * 60
    return None


def test_dm_retry_after_sync(db: Any, user_id: int, now: datetime) -> Optional[int]:
    """Seconds until another test DM is allowed, or None when one can be sent now."""
    latest = reminder_db.latest_test_dm_sync(db, user_id)
    recent = reminder_db.count_test_dms_since_sync(db, user_id, now - timedelta(days=1))
    return _retry_after(latest, recent, now)


async def test_dm_retry_after(db: Any, user_id: int, now: datetime) -> Optional[int]:
    """Async variant of :func:`test_dm_retry_after_sync`."""
    latest = await reminder_db.latest_test_dm(db, user_id)
    recent = await reminder_db.count_test_dms_since(db, user_id, now - timedelta(days=1))
    return _retry_after(latest, recent, now)


def add_reminder_sync(
    db: Any, user_id: int, nation_id: str, *, now: Optional[datetime] = None
) -> AddReminderResult:
    """Watch a nation; a first reminder also queues a test DM when useful."""
    now = now or rules.utcnow()
    auto_test = _should_auto_test(reminder_db.get_profile_sync(db, user_id))
    added = reminder_db.add_alert_sync(db, user_id, nation_id, now)
    test_dm = None
    if added and auto_test and test_dm_retry_after_sync(db, user_id, now) is None:
        test_dm, _ = reminder_db.create_test_dm_sync(db, user_id, TEST_DM_SOURCE_AUTOMATIC, now)
    return AddReminderResult(added, test_dm)


async def add_reminder(
    db: Any,
    user_id: int,
    nation_id: str,
    *,
    now: Optional[datetime] = None,
    source: str = TEST_DM_SOURCE_BOT,
) -> AddReminderResult:
    """Async variant of :func:`add_reminder_sync` for bot commands and buttons."""
    now = now or rules.utcnow()
    auto_test = _should_auto_test(await reminder_db.get_profile(db, user_id))
    added = await reminder_db.add_alert(db, user_id, nation_id, now)
    test_dm = None
    if added and auto_test and await test_dm_retry_after(db, user_id, now) is None:
        test_dm, _ = await reminder_db.create_test_dm(db, user_id, source, now)
    return AddReminderResult(added, test_dm)


def remove_reminder_sync(
    db: Any, user_id: int, nation_id: str, *, now: Optional[datetime] = None
) -> bool:
    """Stop watching a nation and cancel its scheduled reminders right away."""
    now = now or rules.utcnow()
    removed = reminder_db.remove_alert_sync(db, user_id, nation_id, now)
    reminder_db.cancel_pending_jobs_for_sync(db, user_id, nation_id, "unsubscribed", now)
    return removed


async def remove_reminder(
    db: Any, user_id: int, nation_id: str, *, now: Optional[datetime] = None
) -> bool:
    """Async variant of :func:`remove_reminder_sync`."""
    now = now or rules.utcnow()
    removed = await reminder_db.remove_alert(db, user_id, nation_id, now)
    await reminder_db.cancel_pending_jobs_for(db, user_id, nation_id, "unsubscribed", now)
    return removed


def update_channels_sync(
    db: Any,
    user_id: int,
    *,
    discord_dm: bool,
    web_push: bool,
    push_configured: bool,
) -> Optional[str]:
    """Switch delivery channels; returns an error code when the change isn't allowed."""
    device_count = reminder_db.count_push_subscriptions_sync(db, user_id) if web_push else 0
    error = rules.validate_channel_settings(
        bool(discord_dm),
        bool(web_push),
        push_device_count=device_count,
        push_configured=push_configured,
    )
    if error is None:
        reminder_db.set_channels_sync(db, user_id, rules.ChannelSettings(bool(discord_dm), bool(web_push)))
    return error


def _clean_label(label: Any) -> str:
    text = " ".join(str(label or "").split())[:60]
    return text or "Browser"


def register_push_device_sync(
    db: Any,
    user_id: int,
    *,
    endpoint: Any,
    p256dh: Any,
    auth: Any,
    key_id: Optional[str],
    label: Any,
    enable_channel: bool,
    now: Optional[datetime] = None,
) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """Store this browser's push subscription.

    Returns:
        ``(error_code, device)``; ``device`` is None when ``error_code`` is set.
    """
    now = now or rules.utcnow()
    if not rules.is_allowed_push_endpoint(endpoint) or not rules.valid_push_keys(p256dh, auth):
        return INVALID_SUBSCRIPTION, None
    device_id = rules.push_device_id(endpoint)
    existing = reminder_db.get_push_subscription_sync(db, device_id)
    previous_owner = int(existing["user_id"]) if existing and existing.get("user_id") is not None else None
    if previous_owner != user_id and (
        reminder_db.count_push_subscriptions_sync(db, user_id) >= rules.MAX_PUSH_DEVICES_PER_USER
    ):
        return DEVICE_LIMIT, None
    device = reminder_db.upsert_push_subscription_sync(
        db,
        user_id=user_id,
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth,
        key_id=key_id,
        label=_clean_label(label),
        now=now,
    )
    if previous_owner is not None and previous_owner != user_id:
        # The browser now belongs to a different Discord account.
        reminder_db.turn_off_push_channel_if_no_devices_sync(db, previous_owner)
    if enable_channel:
        profile = reminder_db.get_profile_sync(db, user_id)
        channels = rules.ChannelSettings.from_doc((profile or {}).get("reminder_channels"))
        if not channels.web_push:
            reminder_db.set_channels_sync(db, user_id, rules.ChannelSettings(channels.discord_dm, True))
    return None, device


def remove_push_device_sync(db: Any, user_id: int, device_id: str) -> bool:
    """Remove a push device; channels stay consistent when it was the last one."""
    removed = reminder_db.delete_push_subscription_sync(db, user_id, device_id)
    if removed:
        reminder_db.turn_off_push_channel_if_no_devices_sync(db, user_id)
    return removed
