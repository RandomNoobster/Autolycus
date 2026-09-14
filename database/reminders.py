"""Mongo data access for beige reminders.

Covers watch lists and delivery settings on ``global_users`` plus the
``reminder_jobs``, ``dm_tests`` and ``push_subscriptions`` collections.

Async functions take the Motor database (bot); ``*_sync`` functions take a pymongo
database (API). No Discord imports.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, Optional, Sequence

from pymongo import ASCENDING, DESCENDING, ReturnDocument, UpdateOne
from pymongo.errors import PyMongoError

from logic import reminders as rules

logger = logging.getLogger(__name__)

USERS = "global_users"
JOBS = "reminder_jobs"
TEST_DMS = "dm_tests"
PUSH_SUBSCRIPTIONS = "push_subscriptions"

JOB_RETENTION = timedelta(days=14)
TEST_DM_RETENTION = timedelta(days=7)

PROFILE_PROJECTION: dict[str, int] = {
    "_id": 0,
    "user": 1,
    "id": 1,
    "beige_alerts": 1,
    "beige_alerts_config": 1,
    "beige_alert_added_at": 1,
    "beige_alerts_updated_at": 1,
    "beige_alerts_config_updated_at": 1,
    "reminder_channels": 1,
    "dm_channel_id": 1,
    "dm_delivery": 1,
    "reminder_problems": 1,
    "dm_notice_pending": 1,
}

_INDEXES: dict[str, list[tuple[list[tuple[str, int]], dict[str, Any]]]] = {
    USERS: [
        ([("user", ASCENDING)], {"name": "user_1"}),
        (
            [("beige_alerts_updated_at", ASCENDING)],
            {"name": "beige_alerts_updated_at_1", "sparse": True},
        ),
    ],
    JOBS: [
        ([("status", ASCENDING), ("due_at", ASCENDING)], {"name": "status_due"}),
        ([("user_id", ASCENDING), ("nation_id", ASCENDING)], {"name": "user_nation"}),
        ([("expire_at", ASCENDING)], {"name": "expire_at_ttl", "expireAfterSeconds": 0}),
    ],
    TEST_DMS: [
        ([("state", ASCENDING), ("requested_at", ASCENDING)], {"name": "state_requested"}),
        ([("user_id", ASCENDING), ("requested_at", DESCENDING)], {"name": "user_requested"}),
        ([("expire_at", ASCENDING)], {"name": "expire_at_ttl", "expireAfterSeconds": 0}),
    ],
    PUSH_SUBSCRIPTIONS: [
        ([("user_id", ASCENDING)], {"name": "user_id_1"}),
    ],
}


# --- Helpers ----------------------------------------------------------------


def _as_utc(value: Any) -> Optional[datetime]:
    return rules.ensure_utc(value) if isinstance(value, datetime) else None


def _nation_id_variants(nation_id: str) -> list[Any]:
    """Watch lists may hold nation IDs as strings or (legacy) integers."""
    variants: list[Any] = [nation_id]
    if nation_id.isdigit():
        variants.append(int(nation_id))
    return variants


def _profile_seed() -> dict[str, Any]:
    return {
        "beige_alerts": [],
        "beige_alerts_config": list(rules.DEFAULT_REMINDER_OFFSETS),
    }


async def ensure_indexes(db: Any) -> None:
    """Create reminder indexes (idempotent); failures are logged, not raised."""
    for collection, specs in _INDEXES.items():
        for keys, options in specs:
            try:
                await db[collection].create_index(keys, **options)
            except PyMongoError as exc:
                logger.warning("Could not create index %s on %s: %s", options.get("name"), collection, exc)


def ensure_indexes_sync(db: Any) -> None:
    """Synchronous variant of :func:`ensure_indexes` for the API process."""
    for collection, specs in _INDEXES.items():
        for keys, options in specs:
            try:
                db[collection].create_index(keys, **options)
            except PyMongoError as exc:
                logger.warning("Could not create index %s on %s: %s", options.get("name"), collection, exc)


# --- Profiles and watch lists ----------------------------------------------


def get_profile_sync(db: Any, user_id: int) -> Optional[dict[str, Any]]:
    """Read a user's reminder fields without creating anything."""
    return db[USERS].find_one({"user": user_id}, PROFILE_PROJECTION)


def ensure_profile_sync(db: Any, user_id: int) -> None:
    """Create an empty reminder profile if the user has none."""
    db[USERS].update_one({"user": user_id}, {"$setOnInsert": _profile_seed()}, upsert=True)


async def get_profile(db: Any, user_id: int) -> Optional[dict[str, Any]]:
    """Async variant of :func:`get_profile_sync`."""
    return await db[USERS].find_one({"user": user_id}, PROFILE_PROJECTION)


def watched_nation_ids(profile: Optional[Mapping[str, Any]]) -> list[str]:
    """Normalized, de-duplicated watch list in stored order."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in (profile or {}).get("beige_alerts") or []:
        nation_id = rules.normalize_nation_id(raw)
        if nation_id is not None and nation_id not in seen:
            seen.add(nation_id)
            out.append(nation_id)
    return out


def subscriptions_for(profile: Mapping[str, Any]) -> list[rules.Subscription]:
    """Build scheduler subscriptions from a ``global_users`` document."""
    try:
        user_id = int(profile.get("user"))
    except (TypeError, ValueError):
        return []
    offsets = tuple(rules.effective_offsets(profile.get("beige_alerts_config")))
    added = profile.get("beige_alert_added_at")
    added_map = added if isinstance(added, Mapping) else {}
    changed_at = _as_utc(profile.get("beige_alerts_config_updated_at"))
    return [
        rules.Subscription(
            user_id=user_id,
            nation_id=nation_id,
            offsets=offsets,
            added_at=_as_utc(added_map.get(nation_id)),
            offsets_changed_at=changed_at,
        )
        for nation_id in watched_nation_ids(profile)
    ]


def _add_alert_update(nation_id: str, now: datetime) -> dict[str, Any]:
    return {
        "$push": {"beige_alerts": nation_id},
        "$set": {f"beige_alert_added_at.{nation_id}": now, "beige_alerts_updated_at": now},
    }


def _remove_alert_update(nation_id: str, now: datetime) -> dict[str, Any]:
    return {
        "$pull": {"beige_alerts": {"$in": _nation_id_variants(nation_id)}},
        "$unset": {f"beige_alert_added_at.{nation_id}": ""},
        "$set": {"beige_alerts_updated_at": now},
    }


def add_alert_sync(db: Any, user_id: int, nation_id: str, now: datetime) -> bool:
    """Add a nation to a user's watch list, creating the profile if needed.

    Returns:
        True when the nation was newly added.
    """
    users = db[USERS]
    users.update_one({"user": user_id}, {"$setOnInsert": _profile_seed()}, upsert=True)
    result = users.update_one(
        {"user": user_id, "beige_alerts": {"$nin": _nation_id_variants(nation_id)}},
        _add_alert_update(nation_id, now),
    )
    return result.modified_count > 0


async def add_alert(db: Any, user_id: int, nation_id: str, now: datetime) -> bool:
    """Async variant of :func:`add_alert_sync`."""
    users = db[USERS]
    await users.update_one({"user": user_id}, {"$setOnInsert": _profile_seed()}, upsert=True)
    result = await users.update_one(
        {"user": user_id, "beige_alerts": {"$nin": _nation_id_variants(nation_id)}},
        _add_alert_update(nation_id, now),
    )
    return result.modified_count > 0


def remove_alert_sync(db: Any, user_id: int, nation_id: str, now: datetime) -> bool:
    """Remove a nation from a user's watch list; True when it was there."""
    result = db[USERS].update_one(
        {"user": user_id, "beige_alerts": {"$in": _nation_id_variants(nation_id)}},
        _remove_alert_update(nation_id, now),
    )
    return result.modified_count > 0


async def remove_alert(db: Any, user_id: int, nation_id: str, now: datetime) -> bool:
    """Async variant of :func:`remove_alert_sync`."""
    result = await db[USERS].update_one(
        {"user": user_id, "beige_alerts": {"$in": _nation_id_variants(nation_id)}},
        _remove_alert_update(nation_id, now),
    )
    return result.modified_count > 0


def _set_offsets_update(offsets: Sequence[int], now: datetime) -> dict[str, Any]:
    return {
        "$set": {
            "beige_alerts_config": list(offsets),
            "beige_alerts_config_updated_at": now,
            "beige_alerts_updated_at": now,
        },
        "$setOnInsert": {"beige_alerts": []},
    }


def set_offsets_sync(db: Any, user_id: int, offsets: Sequence[int], now: datetime) -> None:
    """Replace a user's reminder timings (already validated)."""
    db[USERS].update_one({"user": user_id}, _set_offsets_update(offsets, now), upsert=True)


async def set_offsets(db: Any, user_id: int, offsets: Sequence[int], now: datetime) -> None:
    """Async variant of :func:`set_offsets_sync`."""
    await db[USERS].update_one({"user": user_id}, _set_offsets_update(offsets, now), upsert=True)


def set_channels_sync(db: Any, user_id: int, channels: rules.ChannelSettings) -> None:
    """Store which delivery channels a user has switched on."""
    db[USERS].update_one(
        {"user": user_id},
        {"$set": {"reminder_channels": channels.to_doc()}, "$setOnInsert": _profile_seed()},
        upsert=True,
    )


# --- Discord DM delivery status --------------------------------------------


def mark_dm_pending_sync(db: Any, user_id: int, now: datetime) -> None:
    """A test DM is on its way."""
    db[USERS].update_one(
        {"user": user_id},
        {"$set": {"dm_delivery.state": rules.DM_STATE_PENDING, "dm_delivery.last_attempt_at": now}},
    )


async def mark_dm_pending(db: Any, user_id: int, now: datetime) -> None:
    """Async variant of :func:`mark_dm_pending_sync`."""
    await db[USERS].update_one(
        {"user": user_id},
        {"$set": {"dm_delivery.state": rules.DM_STATE_PENDING, "dm_delivery.last_attempt_at": now}},
    )


async def record_dm_success(db: Any, user_id: int, now: datetime) -> None:
    """A DM was delivered; a previous "Got it" confirmation is kept."""
    users = db[USERS]
    await users.update_one(
        {"user": user_id},
        {
            "$set": {
                "dm_delivery.code": None,
                "dm_delivery.reason": None,
                "dm_delivery.last_attempt_at": now,
                "dm_delivery.last_success_at": now,
                "dm_notice_pending": False,
            }
        },
    )
    await users.update_one(
        {"user": user_id, "dm_delivery.state": {"$ne": rules.DM_STATE_CONFIRMED}},
        {"$set": {"dm_delivery.state": rules.DM_STATE_OK}},
    )


async def record_dm_failure(
    db: Any,
    user_id: int,
    now: datetime,
    *,
    code: Optional[int],
    reason: Optional[str],
    notify: bool = True,
) -> None:
    """Discord refused a DM; the user is told on the website and their next command."""
    fields: dict[str, Any] = {
        "dm_delivery.state": rules.DM_STATE_FAILED,
        "dm_delivery.code": code,
        "dm_delivery.reason": reason,
        "dm_delivery.last_attempt_at": now,
        "dm_delivery.last_failure_at": now,
    }
    if notify:
        fields["dm_notice_pending"] = True
    await db[USERS].update_one({"user": user_id}, {"$set": fields})


async def mark_dm_confirmed(db: Any, user_id: int, now: datetime) -> None:
    """The user clicked "Got it" in a DM, so DMs reach them and they see them."""
    await db[USERS].update_one(
        {"user": user_id},
        {
            "$set": {
                "dm_delivery.state": rules.DM_STATE_CONFIRMED,
                "dm_delivery.confirmed_at": now,
                "dm_delivery.code": None,
                "dm_delivery.reason": None,
                "dm_notice_pending": False,
            }
        },
    )


async def set_dm_channel_id(db: Any, user_id: int, channel_id: Optional[int]) -> None:
    """Remember (or forget) the user's DM channel so sends take one request."""
    if channel_id is None:
        await db[USERS].update_one({"user": user_id}, {"$unset": {"dm_channel_id": ""}})
    else:
        await db[USERS].update_one({"user": user_id}, {"$set": {"dm_channel_id": int(channel_id)}})


async def take_dm_notice(db: Any, user_id: int) -> Optional[dict[str, Any]]:
    """Atomically claim the pending "we couldn't DM you" notice, if any."""
    return await db[USERS].find_one_and_update(
        {"user": user_id, "dm_notice_pending": True},
        {"$set": {"dm_notice_pending": False}},
        projection={"_id": 0, "dm_delivery": 1, "reminder_problems": {"$slice": 1}},
    )


async def users_with_pending_notice(db: Any) -> set[int]:
    """Discord IDs that have a delivery notice waiting."""
    cursor = db[USERS].find({"dm_notice_pending": True}, {"_id": 0, "user": 1})
    docs = await cursor.to_list(length=None)
    out: set[int] = set()
    for doc in docs:
        try:
            out.add(int(doc.get("user")))
        except (TypeError, ValueError):
            continue
    return out


# --- Problems shown on the website -----------------------------------------


def problem_doc(
    kind: str,
    nation_id: str,
    *,
    now: datetime,
    reminder_removed: bool,
    nation_name: Optional[str] = None,
    offset_min: Optional[int] = None,
    due_at: Optional[datetime] = None,
    code: Optional[int] = None,
) -> dict[str, Any]:
    """Build one entry for a user's recent reminder problems."""
    return {
        "kind": kind,
        "nation_id": str(nation_id),
        "nation_name": nation_name,
        "offset_min": offset_min,
        "due_at": due_at,
        "code": code,
        "reminder_removed": bool(reminder_removed),
        "at": now,
    }


async def add_problem(db: Any, user_id: int, problem: Mapping[str, Any]) -> None:
    """Prepend a problem, keeping the most recent ones."""
    await db[USERS].update_one(
        {"user": user_id},
        {
            "$push": {
                "reminder_problems": {
                    "$each": [dict(problem)],
                    "$position": 0,
                    "$slice": rules.MAX_RECENT_PROBLEMS,
                }
            }
        },
    )


# --- Scheduler inputs -------------------------------------------------------

SUBSCRIPTION_PROJECTION: dict[str, int] = {
    "_id": 0,
    "user": 1,
    "beige_alerts": 1,
    "beige_alerts_config": 1,
    "beige_alert_added_at": 1,
    "beige_alerts_config_updated_at": 1,
    "beige_alerts_updated_at": 1,
}


async def load_watching_users(db: Any) -> list[dict[str, Any]]:
    """Every profile that watches at least one nation."""
    cursor = db[USERS].find({"beige_alerts.0": {"$exists": True}}, SUBSCRIPTION_PROJECTION)
    return await cursor.to_list(length=None)


async def load_users_changed_since(db: Any, since: datetime) -> list[dict[str, Any]]:
    """Profiles whose watch list or timings changed after ``since``."""
    cursor = db[USERS].find({"beige_alerts_updated_at": {"$gt": since}}, SUBSCRIPTION_PROJECTION)
    return await cursor.to_list(length=None)


async def load_profiles(db: Any, user_ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    """Reminder profiles keyed by Discord ID."""
    ids = sorted({int(uid) for uid in user_ids})
    if not ids:
        return {}
    cursor = db[USERS].find({"user": {"$in": ids}}, PROFILE_PROJECTION)
    out: dict[int, dict[str, Any]] = {}
    for doc in await cursor.to_list(length=None):
        try:
            out.setdefault(int(doc.get("user")), doc)
        except (TypeError, ValueError):
            continue
    return out


# --- Jobs -------------------------------------------------------------------


def snapshot_from_doc(doc: Mapping[str, Any]) -> rules.JobSnapshot:
    """Convert a stored job into the shape the planning rules use."""
    return rules.JobSnapshot(
        job_id=str(doc["_id"]),
        user_id=int(doc["user_id"]),
        nation_id=str(doc["nation_id"]),
        kind=str(doc.get("kind") or rules.JOB_KIND_LEAD),
        offset_min=doc.get("offset_min"),
        exit_at=rules.ensure_utc(doc["exit_at"]),
        due_at=rules.ensure_utc(doc["due_at"]),
        status=str(doc.get("status") or rules.JOB_PENDING),
    )


def _job_insert_doc(job: rules.PlannedJob, now: datetime) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "user_id": job.user_id,
        "nation_id": job.nation_id,
        "kind": job.kind,
        "offset_min": job.offset_min,
        "exit_at": job.exit_at,
        "due_at": job.due_at,
        "status": job.status,
        "late": job.late,
        "reason": job.reason,
        "attempts": 0,
        "created_at": now,
        "updated_at": now,
    }
    if job.status in rules.JOB_FINAL_STATUSES:
        doc["finished_at"] = now
        doc["expire_at"] = now + JOB_RETENTION
    return doc


async def insert_jobs(db: Any, jobs: Sequence[rules.PlannedJob], now: datetime) -> int:
    """Store planned jobs; jobs that already exist are left untouched.

    Returns:
        How many jobs were newly created.
    """
    if not jobs:
        return 0
    ops = [
        UpdateOne({"_id": job.job_id}, {"$setOnInsert": _job_insert_doc(job, now)}, upsert=True)
        for job in jobs
    ]
    result = await db[JOBS].bulk_write(ops, ordered=False)
    return int(result.upserted_count)


async def cancel_jobs(db: Any, cancels: Sequence[tuple[str, str]], now: datetime) -> int:
    """Cancel pending jobs; jobs already being sent are not touched."""
    if not cancels:
        return 0
    ops = [
        UpdateOne(
            {"_id": job_id, "status": rules.JOB_PENDING},
            {
                "$set": {
                    "status": rules.JOB_CANCELLED,
                    "reason": reason,
                    "finished_at": now,
                    "updated_at": now,
                    "expire_at": now + JOB_RETENTION,
                }
            },
        )
        for job_id, reason in cancels
    ]
    result = await db[JOBS].bulk_write(ops, ordered=False)
    return int(result.modified_count)


def _cancel_pending_for_update(reason: str, now: datetime) -> dict[str, Any]:
    return {
        "$set": {
            "status": rules.JOB_CANCELLED,
            "reason": reason,
            "finished_at": now,
            "updated_at": now,
            "expire_at": now + JOB_RETENTION,
        }
    }


async def cancel_pending_jobs_for(
    db: Any, user_id: int, nation_id: Optional[str], reason: str, now: datetime
) -> int:
    """Cancel a user's pending jobs, for one nation or all of them."""
    query: dict[str, Any] = {"user_id": user_id, "status": rules.JOB_PENDING}
    if nation_id is not None:
        query["nation_id"] = nation_id
    result = await db[JOBS].update_many(query, _cancel_pending_for_update(reason, now))
    return int(result.modified_count)


def cancel_pending_jobs_for_sync(
    db: Any, user_id: int, nation_id: Optional[str], reason: str, now: datetime
) -> int:
    """Synchronous variant of :func:`cancel_pending_jobs_for`."""
    query: dict[str, Any] = {"user_id": user_id, "status": rules.JOB_PENDING}
    if nation_id is not None:
        query["nation_id"] = nation_id
    result = db[JOBS].update_many(query, _cancel_pending_for_update(reason, now))
    return int(result.modified_count)


async def load_jobs_for_users(
    db: Any, user_ids: Iterable[int], *, exits_after: datetime
) -> list[rules.JobSnapshot]:
    """Jobs for the given users whose exit is after ``exits_after``."""
    ids = sorted({int(uid) for uid in user_ids})
    if not ids:
        return []
    cursor = db[JOBS].find(
        {"user_id": {"$in": ids}, "exit_at": {"$gte": exits_after}},
        {"user_id": 1, "nation_id": 1, "kind": 1, "offset_min": 1, "exit_at": 1, "due_at": 1, "status": 1},
    )
    return [snapshot_from_doc(doc) for doc in await cursor.to_list(length=None)]


def upcoming_jobs_for_user_sync(db: Any, user_id: int, now: datetime) -> list[dict[str, Any]]:
    """Jobs for exits that haven't happened yet (for showing the schedule)."""
    cursor = db[JOBS].find(
        {"user_id": user_id, "exit_at": {"$gte": now}},
        {"nation_id": 1, "kind": 1, "offset_min": 1, "exit_at": 1, "due_at": 1, "status": 1},
    )
    return list(cursor)


def active_jobs_for_user_sync(db: Any, user_id: int) -> list[dict[str, Any]]:
    """Pending or in-flight jobs for a user, earliest first (for display)."""
    cursor = db[JOBS].find(
        {"user_id": user_id, "status": {"$in": list(rules.JOB_ACTIVE_STATUSES)}},
        {"nation_id": 1, "kind": 1, "offset_min": 1, "exit_at": 1, "due_at": 1, "status": 1},
    ).sort("due_at", ASCENDING)
    return list(cursor)


async def active_jobs_for_user(db: Any, user_id: int) -> list[dict[str, Any]]:
    """Async variant of :func:`active_jobs_for_user_sync`."""
    cursor = db[JOBS].find(
        {"user_id": user_id, "status": {"$in": list(rules.JOB_ACTIVE_STATUSES)}},
        {"nation_id": 1, "kind": 1, "offset_min": 1, "exit_at": 1, "due_at": 1, "status": 1},
    ).sort("due_at", ASCENDING)
    return await cursor.to_list(length=None)


async def next_pending_due_at(db: Any) -> Optional[datetime]:
    """Due time of the earliest pending job."""
    doc = await db[JOBS].find_one(
        {"status": rules.JOB_PENDING}, {"due_at": 1}, sort=[("due_at", ASCENDING)]
    )
    return _as_utc(doc.get("due_at")) if doc else None


async def pending_jobs_due_by(db: Any, until: datetime, *, limit: int = 1000) -> list[dict[str, Any]]:
    """Pending jobs due at or before ``until``, earliest first."""
    cursor = (
        db[JOBS]
        .find({"status": rules.JOB_PENDING, "due_at": {"$lte": until}})
        .sort("due_at", ASCENDING)
        .limit(limit)
    )
    return await cursor.to_list(length=None)


async def claim_jobs(
    db: Any, job_ids: Sequence[str], claim_id: str, now: datetime
) -> list[dict[str, Any]]:
    """Atomically move pending jobs to ``sending`` and return the ones this call won."""
    if not job_ids:
        return []
    await db[JOBS].update_many(
        {"_id": {"$in": list(job_ids)}, "status": rules.JOB_PENDING},
        {
            "$set": {
                "status": rules.JOB_SENDING,
                "claim_id": claim_id,
                "claimed_at": now,
                "updated_at": now,
            },
            "$inc": {"attempts": 1},
        },
    )
    cursor = db[JOBS].find({"_id": {"$in": list(job_ids)}, "claim_id": claim_id, "status": rules.JOB_SENDING})
    return await cursor.to_list(length=None)


async def finish_jobs(
    db: Any, claim_id: str, updates: Sequence[tuple[str, Mapping[str, Any]]], now: datetime
) -> None:
    """Record final results for claimed jobs.

    Args:
        db: Motor database.
        claim_id: The claim the jobs were taken under.
        updates: ``(job_id, fields)`` pairs; fields must include ``status``.
        now: Current time.
    """
    if not updates:
        return
    ops = []
    for job_id, fields in updates:
        values = dict(fields)
        values.update({"finished_at": now, "updated_at": now, "expire_at": now + JOB_RETENTION})
        ops.append(UpdateOne({"_id": job_id, "claim_id": claim_id}, {"$set": values}))
    await db[JOBS].bulk_write(ops, ordered=False)


async def release_jobs(
    db: Any,
    job_ids: Sequence[str],
    claim_id: str,
    now: datetime,
    *,
    retry_at: Optional[datetime] = None,
) -> None:
    """Put claimed jobs back to ``pending`` (optionally with a later due time) for a retry."""
    if not job_ids:
        return
    fields: dict[str, Any] = {"status": rules.JOB_PENDING, "claim_id": None, "updated_at": now}
    if retry_at is not None:
        fields["due_at"] = retry_at
    await db[JOBS].update_many({"_id": {"$in": list(job_ids)}, "claim_id": claim_id}, {"$set": fields})


async def recover_stale_claims(db: Any, older_than: datetime, now: datetime) -> int:
    """Return jobs stuck in ``sending`` (e.g. after a crash) to ``pending``."""
    result = await db[JOBS].update_many(
        {"status": rules.JOB_SENDING, "claimed_at": {"$lt": older_than}},
        {"$set": {"status": rules.JOB_PENDING, "claim_id": None, "updated_at": now}},
    )
    return int(result.modified_count)


# --- Test DMs ---------------------------------------------------------------


def _new_test_dm(user_id: int, source: str, now: datetime) -> dict[str, Any]:
    return {
        "_id": uuid.uuid4().hex,
        "user_id": user_id,
        "source": source,
        "state": rules.TEST_DM_QUEUED,
        "code": None,
        "reason": None,
        "requested_at": now,
        "sent_at": None,
        "confirmed_at": None,
        "message_id": None,
        "expire_at": now + TEST_DM_RETENTION,
    }


def create_test_dm_sync(
    db: Any, user_id: int, source: str, now: datetime
) -> tuple[dict[str, Any], bool]:
    """Queue a test DM unless one is already on its way.

    Returns:
        ``(test_dm, created)``.
    """
    existing = db[TEST_DMS].find_one(
        {"user_id": user_id, "state": {"$in": list(rules.TEST_DM_ACTIVE_STATES)}},
        sort=[("requested_at", DESCENDING)],
    )
    if existing:
        return existing, False
    doc = _new_test_dm(user_id, source, now)
    db[TEST_DMS].insert_one(doc)
    mark_dm_pending_sync(db, user_id, now)
    return doc, True


async def create_test_dm(
    db: Any, user_id: int, source: str, now: datetime
) -> tuple[dict[str, Any], bool]:
    """Async variant of :func:`create_test_dm_sync`."""
    existing = await db[TEST_DMS].find_one(
        {"user_id": user_id, "state": {"$in": list(rules.TEST_DM_ACTIVE_STATES)}},
        sort=[("requested_at", DESCENDING)],
    )
    if existing:
        return existing, False
    doc = _new_test_dm(user_id, source, now)
    await db[TEST_DMS].insert_one(doc)
    await mark_dm_pending(db, user_id, now)
    return doc, True


def latest_test_dm_sync(db: Any, user_id: int) -> Optional[dict[str, Any]]:
    """Most recent test DM for a user."""
    return db[TEST_DMS].find_one({"user_id": user_id}, sort=[("requested_at", DESCENDING)])


def count_test_dms_since_sync(db: Any, user_id: int, since: datetime) -> int:
    """How many test DMs a user requested after ``since``."""
    return int(db[TEST_DMS].count_documents({"user_id": user_id, "requested_at": {"$gte": since}}))


async def latest_test_dm(db: Any, user_id: int) -> Optional[dict[str, Any]]:
    """Async variant of :func:`latest_test_dm_sync`."""
    return await db[TEST_DMS].find_one({"user_id": user_id}, sort=[("requested_at", DESCENDING)])


async def count_test_dms_since(db: Any, user_id: int, since: datetime) -> int:
    """Async variant of :func:`count_test_dms_since_sync`."""
    return int(await db[TEST_DMS].count_documents({"user_id": user_id, "requested_at": {"$gte": since}}))


async def clear_dm_pending(db: Any, user_id: int) -> None:
    """A test DM hit a temporary error; don't leave the status stuck on "checking"."""
    await db[USERS].update_one(
        {"user": user_id, "dm_delivery.state": rules.DM_STATE_PENDING},
        {"$set": {"dm_delivery.state": rules.DM_STATE_UNKNOWN}},
    )


async def claim_next_test_dm(db: Any, now: datetime) -> Optional[dict[str, Any]]:
    """Take the oldest queued test DM."""
    return await db[TEST_DMS].find_one_and_update(
        {"state": rules.TEST_DM_QUEUED},
        {"$set": {"state": rules.TEST_DM_SENDING, "claimed_at": now}},
        sort=[("requested_at", ASCENDING)],
        return_document=ReturnDocument.AFTER,
    )


async def finish_test_dm(
    db: Any,
    test_id: str,
    *,
    state: str,
    now: datetime,
    code: Optional[int] = None,
    reason: Optional[str] = None,
    message_id: Optional[int] = None,
) -> None:
    """Record the result of sending a test DM."""
    fields: dict[str, Any] = {"state": state, "code": code, "reason": reason}
    if state == rules.TEST_DM_SENT:
        fields["sent_at"] = now
        fields["message_id"] = message_id
    await db[TEST_DMS].update_one({"_id": test_id}, {"$set": fields})


async def confirm_test_dm(db: Any, test_id: str, user_id: int, now: datetime) -> None:
    """Mark a test DM as seen by its recipient."""
    await db[TEST_DMS].update_one(
        {"_id": test_id, "user_id": user_id},
        {"$set": {"state": rules.TEST_DM_CONFIRMED, "confirmed_at": now}},
    )
    await mark_dm_confirmed(db, user_id, now)


async def recover_stale_test_dms(db: Any, older_than: datetime) -> int:
    """Requeue test DMs stuck in ``sending``."""
    result = await db[TEST_DMS].update_many(
        {"state": rules.TEST_DM_SENDING, "claimed_at": {"$lt": older_than}},
        {"$set": {"state": rules.TEST_DM_QUEUED}},
    )
    return int(result.modified_count)


# --- Push subscriptions -----------------------------------------------------


def get_push_subscription_sync(db: Any, device_id: str) -> Optional[dict[str, Any]]:
    """One push device by ID."""
    return db[PUSH_SUBSCRIPTIONS].find_one({"_id": device_id})


def upsert_push_subscription_sync(
    db: Any,
    *,
    user_id: int,
    endpoint: str,
    p256dh: str,
    auth: str,
    key_id: Optional[str],
    label: str,
    now: datetime,
) -> dict[str, Any]:
    """Register (or refresh) this browser's push subscription for a user."""
    device_id = rules.push_device_id(endpoint)
    return db[PUSH_SUBSCRIPTIONS].find_one_and_update(
        {"_id": device_id},
        {
            "$set": {
                "user_id": user_id,
                "endpoint": endpoint,
                "keys": {"p256dh": p256dh, "auth": auth},
                "key_id": key_id,
                "label": label,
                "last_seen_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )


def list_push_subscriptions_sync(db: Any, user_id: int) -> list[dict[str, Any]]:
    """A user's push devices, newest first."""
    return list(db[PUSH_SUBSCRIPTIONS].find({"user_id": user_id}).sort("created_at", DESCENDING))


def count_push_subscriptions_sync(db: Any, user_id: int) -> int:
    """How many push devices a user has."""
    return int(db[PUSH_SUBSCRIPTIONS].count_documents({"user_id": user_id}))


def delete_push_subscription_sync(db: Any, user_id: int, device_id: str) -> bool:
    """Remove one of a user's push devices; True when something was deleted."""
    result = db[PUSH_SUBSCRIPTIONS].delete_one({"_id": device_id, "user_id": user_id})
    return result.deleted_count > 0


def _push_result_ops(
    delivered: Iterable[str], failed: Iterable[str], now: datetime
) -> list[UpdateOne]:
    ops = [UpdateOne({"_id": d}, {"$set": {"last_success_at": now}}) for d in delivered]
    ops += [UpdateOne({"_id": d}, {"$set": {"last_failure_at": now}}) for d in failed]
    return ops


def record_push_results_sync(
    db: Any,
    *,
    delivered: Iterable[str] = (),
    failed: Iterable[str] = (),
    gone: Iterable[str] = (),
    now: datetime,
) -> None:
    """Update device timestamps and delete devices the push service no longer knows."""
    ops = _push_result_ops(delivered, failed, now)
    if ops:
        db[PUSH_SUBSCRIPTIONS].bulk_write(ops, ordered=False)
    gone_ids = list(gone)
    if gone_ids:
        db[PUSH_SUBSCRIPTIONS].delete_many({"_id": {"$in": gone_ids}})


async def record_push_results(
    db: Any,
    *,
    delivered: Iterable[str] = (),
    failed: Iterable[str] = (),
    gone: Iterable[str] = (),
    now: datetime,
) -> None:
    """Async variant of :func:`record_push_results_sync`."""
    ops = _push_result_ops(delivered, failed, now)
    if ops:
        await db[PUSH_SUBSCRIPTIONS].bulk_write(ops, ordered=False)
    gone_ids = list(gone)
    if gone_ids:
        await db[PUSH_SUBSCRIPTIONS].delete_many({"_id": {"$in": gone_ids}})


async def push_subscriptions_by_user(
    db: Any, user_ids: Iterable[int]
) -> dict[int, list[dict[str, Any]]]:
    """Push devices for several users."""
    ids = sorted({int(uid) for uid in user_ids})
    if not ids:
        return {}
    cursor = db[PUSH_SUBSCRIPTIONS].find({"user_id": {"$in": ids}})
    out: dict[int, list[dict[str, Any]]] = {}
    for doc in await cursor.to_list(length=None):
        out.setdefault(int(doc["user_id"]), []).append(doc)
    return out


async def count_push_subscriptions(db: Any, user_id: int) -> int:
    """Async variant of :func:`count_push_subscriptions_sync`."""
    return int(await db[PUSH_SUBSCRIPTIONS].count_documents({"user_id": user_id}))


_PUSH_OFF_DM_ON = {"reminder_channels": {"discord_dm": True, "web_push": False}}


async def turn_off_push_channel_if_no_devices(db: Any, user_id: int) -> None:
    """Keep channel settings consistent after a user's last push device goes away.

    Push is switched off; Discord DMs are switched on so a channel always remains.
    """
    if await count_push_subscriptions(db, user_id) > 0:
        return
    profile = await db[USERS].find_one({"user": user_id}, {"_id": 0, "reminder_channels": 1})
    channels = rules.ChannelSettings.from_doc((profile or {}).get("reminder_channels"))
    if channels.web_push:
        await db[USERS].update_one({"user": user_id}, {"$set": _PUSH_OFF_DM_ON})


def turn_off_push_channel_if_no_devices_sync(db: Any, user_id: int) -> None:
    """Synchronous variant of :func:`turn_off_push_channel_if_no_devices`."""
    if count_push_subscriptions_sync(db, user_id) > 0:
        return
    profile = db[USERS].find_one({"user": user_id}, {"_id": 0, "reminder_channels": 1})
    channels = rules.ChannelSettings.from_doc((profile or {}).get("reminder_channels"))
    if channels.web_push:
        db[USERS].update_one({"user": user_id}, {"$set": _PUSH_OFF_DM_ON})


# --- Account removal --------------------------------------------------------


async def delete_user_reminder_data(db: Any, user_id: int) -> None:
    """Delete jobs, test DMs and push devices belonging to a user."""
    await db[JOBS].delete_many({"user_id": user_id})
    await db[TEST_DMS].delete_many({"user_id": user_id})
    await db[PUSH_SUBSCRIPTIONS].delete_many({"user_id": user_id})
