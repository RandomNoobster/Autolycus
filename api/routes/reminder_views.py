"""
JSON views of reminder delivery state, shared by the reminders and push routes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping, Optional

from flask import current_app

from core.config import AUTOLYCUS_DISCORD_INVITE_URL
from database import reminders as reminder_db
from infra.webpush import get_push_sender
from logic import reminders as reminder_rules


def iso(value: Any) -> Optional[str]:
    """ISO 8601 UTC string for a stored datetime."""
    return reminder_rules.ensure_utc(value).isoformat() if isinstance(value, datetime) else None


def dm_view(profile: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    dm = (profile or {}).get('dm_delivery') or {}
    return {
        'state': dm.get('state') or reminder_rules.DM_STATE_UNKNOWN,
        'code': dm.get('code'),
        'reason': dm.get('reason'),
        'lastAttemptAt': iso(dm.get('last_attempt_at')),
        'lastSuccessAt': iso(dm.get('last_success_at')),
        'lastFailureAt': iso(dm.get('last_failure_at')),
        'confirmedAt': iso(dm.get('confirmed_at')),
    }


def test_dm_view(doc: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    if not doc:
        return None
    return {
        'id': str(doc.get('_id')),
        'state': doc.get('state'),
        'code': doc.get('code'),
        'reason': doc.get('reason'),
        'requestedAt': iso(doc.get('requested_at')),
        'sentAt': iso(doc.get('sent_at')),
        'confirmedAt': iso(doc.get('confirmed_at')),
    }


def problem_view(problem: Mapping[str, Any]) -> dict[str, Any]:
    return {
        'kind': problem.get('kind'),
        'nationId': str(problem.get('nation_id') or ''),
        'nationName': problem.get('nation_name'),
        'offsetMinutes': problem.get('offset_min'),
        'dueAt': iso(problem.get('due_at')),
        'code': problem.get('code'),
        'reminderRemoved': bool(problem.get('reminder_removed')),
        'at': iso(problem.get('at')),
    }


def device_view(doc: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    if not doc:
        return None
    return {
        'id': str(doc.get('_id')),
        'label': doc.get('label') or 'Browser',
        'createdAt': iso(doc.get('created_at')),
        'lastSeenAt': iso(doc.get('last_seen_at')),
        'lastSuccessAt': iso(doc.get('last_success_at')),
        'lastFailureAt': iso(doc.get('last_failure_at')),
    }


def delivery_view(mongo_db: Any, user_id: int, profile: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """Everything the website shows about how reminders reach a user."""
    push_configured = get_push_sender() is not None
    device_count = reminder_db.count_push_subscriptions_sync(mongo_db, user_id)
    channels = reminder_rules.ChannelSettings.from_doc((profile or {}).get('reminder_channels'))
    dm = dm_view(profile)
    problems = ((profile or {}).get('reminder_problems') or [])[: reminder_rules.MAX_RECENT_PROBLEMS]
    return {
        'channels': {'discordDm': channels.discord_dm, 'webPush': channels.web_push},
        'dm': dm,
        'latestTestDm': test_dm_view(reminder_db.latest_test_dm_sync(mongo_db, user_id)),
        'push': {'configured': push_configured, 'deviceCount': device_count},
        'recentProblems': [problem_view(p) for p in problems if isinstance(p, Mapping)],
        'supportInviteUrl': current_app.config.get('AUTOLYCUS_DISCORD_INVITE_URL') or AUTOLYCUS_DISCORD_INVITE_URL,
        'needsAttention': reminder_rules.needs_attention(
            channels,
            dm['state'],
            push_device_count=device_count,
            push_configured=push_configured,
        ),
    }


def upcoming_by_nation(jobs: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Optional[str]]]:
    """Exit time and next reminder time per watched nation."""
    exits: dict[str, datetime] = {}
    next_due: dict[str, datetime] = {}
    for job in jobs:
        status = job.get('status')
        if status == reminder_rules.JOB_CANCELLED or not isinstance(job.get('exit_at'), datetime):
            continue
        nation_id = str(job.get('nation_id'))
        exit_at = reminder_rules.ensure_utc(job['exit_at'])
        if nation_id not in exits or exit_at > exits[nation_id]:
            exits[nation_id] = exit_at
        if status in reminder_rules.JOB_ACTIVE_STATUSES and isinstance(job.get('due_at'), datetime):
            due_at = reminder_rules.ensure_utc(job['due_at'])
            if nation_id not in next_due or due_at < next_due[nation_id]:
                next_due[nation_id] = due_at
    return {
        nation_id: {
            'exitAt': iso(exits.get(nation_id)),
            'nextReminderAt': iso(next_due.get(nation_id)),
        }
        for nation_id in set(exits) | set(next_due)
    }
