"""Pure rules for beige and vacation-mode reminders.

Shared by the API, the bot and the reminder scheduler. Nothing here does I/O:
turn maths, reminder planning decisions, validation, job identity, delivery-error
classification and small formatting helpers only.

Game timing, per PWPedia ("Terminology-Glossary", "Basics-of-War-Strategy"): a turn
lasts 2 hours and turns change on even UTC hours; day change at 00:00 UTC acts as
a turn change. ``beige_turns`` and ``vacation_mode_turns`` count the turns left, so
a nation with N turns leaves protection at the N-th turn change from now.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Iterable, Mapping, Optional, Sequence
from urllib.parse import urlparse

TURN_SECONDS = 2 * 60 * 60
TURN = timedelta(seconds=TURN_SECONDS)
# Right after a turn change the API can still report the previous turn's counts
# while the game processes the update; day change takes longer.
PROVISIONAL_WINDOW = timedelta(minutes=10)
DAY_CHANGE_PROVISIONAL_WINDOW = timedelta(minutes=15)

DEFAULT_REMINDER_OFFSETS: tuple[int, ...] = (15,)
MAX_REMINDER_OFFSETS = 10
MAX_REMINDER_OFFSET_MINUTES = 7 * 24 * 60

# A reminder that would land this close to (or after) the exit isn't worth sending late.
MIN_USEFUL_LEAD = timedelta(seconds=30)
# Jobs planned up to this long after their due time still count as on time.
PLANNING_GRACE = timedelta(seconds=5)

MAX_EMBEDS_PER_MESSAGE = 10
DISCORD_NONCE_MAX_LENGTH = 25
MAX_RECENT_PROBLEMS = 10
MAX_PUSH_DEVICES_PER_USER = 10

JOB_KIND_LEAD = "lead"
JOB_KIND_EARLY_EXIT = "early_exit"

JOB_PENDING = "pending"
JOB_SENDING = "sending"
JOB_SENT = "sent"
JOB_FAILED = "failed"
JOB_CANCELLED = "cancelled"
JOB_SKIPPED = "skipped"
JOB_ACTIVE_STATUSES: tuple[str, ...] = (JOB_PENDING, JOB_SENDING)
JOB_FINAL_STATUSES: tuple[str, ...] = (JOB_SENT, JOB_FAILED, JOB_CANCELLED, JOB_SKIPPED)

PROBLEM_NOT_DELIVERED = "not_delivered"
PROBLEM_DM_REFUSED = "dm_refused"
PROBLEM_PUSH_FAILED = "push_failed"
PROBLEM_NOT_PROTECTED = "not_protected"
PROBLEM_NATION_MISSING = "nation_missing"

DM_STATE_UNKNOWN = "unknown"
DM_STATE_PENDING = "pending"
DM_STATE_OK = "ok"
DM_STATE_CONFIRMED = "confirmed"
DM_STATE_FAILED = "failed"

TEST_DM_QUEUED = "queued"
TEST_DM_SENDING = "sending"
TEST_DM_SENT = "sent"
TEST_DM_FAILED = "failed"
TEST_DM_CONFIRMED = "confirmed"
TEST_DM_ACTIVE_STATES: tuple[str, ...] = (TEST_DM_QUEUED, TEST_DM_SENDING)

CHANNEL_REQUIRED = "CHANNEL_REQUIRED"
NO_PUSH_DEVICES = "NO_PUSH_DEVICES"
PUSH_NOT_CONFIGURED = "PUSH_NOT_CONFIGURED"


# --- Time -------------------------------------------------------------------


def utcnow() -> datetime:
    """Return the current time as an aware UTC datetime."""
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    """Return ``value`` as an aware UTC datetime.

    pymongo returns naive datetimes that are already UTC, so naive values are
    tagged as UTC rather than converted from local time.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_epoch(value: datetime) -> int:
    """Return whole seconds since the Unix epoch."""
    return int(ensure_utc(value).timestamp())


def turn_start(moment: datetime) -> datetime:
    """Return the start of the game turn containing ``moment`` (an even UTC hour)."""
    epoch = to_epoch(moment)
    return datetime.fromtimestamp(epoch - epoch % TURN_SECONDS, tz=timezone.utc)


def in_provisional_window(observed_at: datetime) -> bool:
    """Return True when a reading may predate the game processing the last turn change."""
    start = turn_start(observed_at)
    window = DAY_CHANGE_PROVISIONAL_WINDOW if start.hour == 0 else PROVISIONAL_WINDOW
    return ensure_utc(observed_at) - start < window


# --- Exit estimates ---------------------------------------------------------


@dataclass(frozen=True)
class NationStatus:
    """One reading of a nation's remaining protection turns."""

    nation_id: str
    beige_turns: int
    vm_turns: int
    observed_at: datetime

    @property
    def turns(self) -> int:
        """Turns until both beige and vacation mode have ended."""
        return max(self.beige_turns, self.vm_turns, 0)


@dataclass(frozen=True)
class ExitEstimate:
    """When a nation leaves protection, as far as the latest reading tells.

    Attributes:
        exit_at: Turn change at which protection ends, or None when the nation is
            not protected.
        definitive: False while the reading may not reflect the latest turn change;
            callers shouldn't change plans based on a non-definitive estimate.
    """

    exit_at: Optional[datetime]
    definitive: bool


@dataclass(frozen=True)
class TrackedNation:
    """A reading together with the estimate derived from it."""

    status: NationStatus
    estimate: ExitEstimate


def naive_exit_at(status: NationStatus) -> Optional[datetime]:
    """Exit time assuming the reading already reflects the current turn."""
    if status.turns <= 0:
        return None
    return turn_start(status.observed_at) + TURN * status.turns


def estimate_exit(current: NationStatus, previous: Optional[TrackedNation] = None) -> ExitEstimate:
    """Estimate when a nation leaves beige or vacation mode.

    Uses ``max(beige_turns, vacation_mode_turns)``: the nation stays protected until
    both have ended. If beige outlasts vacation mode, later readings reschedule it.

    Readings taken shortly after a turn change are compared with the previous
    reading, so a count the game hasn't decremented yet can't push the exit two
    hours late.

    Args:
        current: The newest reading.
        previous: The previous reading for the same nation and its estimate.

    Returns:
        The exit estimate for ``current``.
    """
    naive = naive_exit_at(current)
    if not in_provisional_window(current.observed_at):
        return ExitEstimate(naive, True)
    if previous is None or not previous.estimate.definitive:
        return ExitEstimate(naive, False)

    changed_at = turn_start(current.observed_at)
    turns = current.turns
    prev_turns = previous.status.turns

    if ensure_utc(previous.status.observed_at) < changed_at:
        if turns > 0 and turns == prev_turns:
            # Still the pre-change count, so the earlier reading's exit stands.
            return ExitEstimate(previous.estimate.exit_at, True)
        if turns == prev_turns - 1:
            return ExitEstimate(naive, True)
        return ExitEstimate(naive, False)

    # The previous reading came from this same window.
    if turns == prev_turns:
        return previous.estimate
    previous_was_stale = (
        prev_turns > 0
        and previous.estimate.exit_at is not None
        and ensure_utc(previous.estimate.exit_at) == changed_at + TURN * (prev_turns - 1)
    )
    if previous_was_stale and turns == prev_turns - 1:
        return ExitEstimate(naive, True)
    return ExitEstimate(naive, False)


# --- Planning ---------------------------------------------------------------


@dataclass(frozen=True)
class Subscription:
    """A user watching one nation.

    Attributes:
        user_id: Discord user ID.
        nation_id: Watched nation ID.
        offsets: Minutes before the exit to remind, largest first.
        added_at: When the nation was added; None for reminders created before
            scheduled delivery existed.
        offsets_changed_at: When the user last changed their timings, if known.
    """

    user_id: int
    nation_id: str
    offsets: tuple[int, ...]
    added_at: Optional[datetime] = None
    offsets_changed_at: Optional[datetime] = None


@dataclass(frozen=True)
class JobSnapshot:
    """The parts of a stored reminder job the planner and dispatcher reason about."""

    job_id: str
    user_id: int
    nation_id: str
    kind: str
    offset_min: Optional[int]
    exit_at: datetime
    due_at: datetime
    status: str


@dataclass(frozen=True)
class PlannedJob:
    """A reminder job the planner wants stored."""

    job_id: str
    user_id: int
    nation_id: str
    kind: str
    offset_min: Optional[int]
    exit_at: datetime
    due_at: datetime
    status: str = JOB_PENDING
    late: bool = False
    reason: Optional[str] = None


@dataclass
class SubscriptionPlan:
    """Changes needed to bring stored jobs in line with the latest estimate."""

    create: list[PlannedJob] = field(default_factory=list)
    cancel: list[tuple[str, str]] = field(default_factory=list)
    remove_subscription: bool = False
    problem: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not (self.create or self.cancel or self.remove_subscription)


def lead_job_id(user_id: int, nation_id: str, exit_at: datetime, offset_min: int) -> str:
    """Stable ID for the reminder ``offset_min`` minutes before ``exit_at``."""
    return f"{int(user_id)}:{nation_id}:{to_epoch(exit_at)}:{int(offset_min)}"


def early_exit_job_id(user_id: int, nation_id: str, expected_exit_at: datetime) -> str:
    """Stable ID for the "left early" notice replacing reminders for ``expected_exit_at``."""
    return f"{int(user_id)}:{nation_id}:{to_epoch(expected_exit_at)}:early"


def plan_subscription(
    sub: Subscription,
    estimate: ExitEstimate,
    jobs: Sequence[JobSnapshot],
    now: datetime,
) -> SubscriptionPlan:
    """Decide which jobs to create or cancel for one subscription.

    Args:
        sub: The subscription being planned.
        estimate: Latest exit estimate for the watched nation.
        jobs: Every stored job for this user and nation.
        now: Current time.

    Returns:
        The changes to apply. Empty when nothing changes or the estimate isn't
        definitive yet.
    """
    plan = SubscriptionPlan()
    if not estimate.definitive:
        return plan
    now = ensure_utc(now)
    pending_leads = [j for j in jobs if j.kind == JOB_KIND_LEAD and j.status == JOB_PENDING]

    if estimate.exit_at is None:
        return _plan_unprotected(sub, jobs, pending_leads, now)

    exit_at = ensure_utc(estimate.exit_at)
    if exit_at <= now:
        # The exit turn change has passed but the reading still carries it; wait for
        # a reading that shows the nation unprotected.
        return plan

    offsets = sorted(set(sub.offsets), reverse=True)
    for job in jobs:
        if job.kind == JOB_KIND_EARLY_EXIT and job.status == JOB_PENDING:
            plan.cancel.append((job.job_id, "protected_again"))
    for job in pending_leads:
        if ensure_utc(job.exit_at) != exit_at:
            plan.cancel.append((job.job_id, "exit_changed"))
        elif job.offset_min not in offsets:
            plan.cancel.append((job.job_id, "timing_removed"))

    existing_ids = {j.job_id for j in jobs}
    late_job: Optional[PlannedJob] = None
    for offset in offsets:
        job_id = lead_job_id(sub.user_id, sub.nation_id, exit_at, offset)
        if job_id in existing_ids:
            continue
        due_at = exit_at - timedelta(minutes=offset)
        if due_at >= now - PLANNING_GRACE:
            plan.create.append(
                PlannedJob(job_id, sub.user_id, sub.nation_id, JOB_KIND_LEAD, offset, exit_at, due_at)
            )
            continue
        # Past due. Only the latest missed timing of a reminder that already existed
        # at its due time is worth sending late; everything else is recorded as skipped.
        if _watched_before(sub, due_at) and exit_at - now > MIN_USEFUL_LEAD:
            if late_job is not None:
                plan.create.append(_as_skipped(late_job, "superseded"))
            late_job = PlannedJob(
                job_id, sub.user_id, sub.nation_id, JOB_KIND_LEAD, offset, exit_at, due_at, late=True
            )
        else:
            plan.create.append(
                PlannedJob(
                    job_id, sub.user_id, sub.nation_id, JOB_KIND_LEAD, offset, exit_at, due_at,
                    status=JOB_SKIPPED, reason="added_after_due",
                )
            )
    if late_job is not None:
        plan.create.append(late_job)
    return plan


def _watched_before(sub: Subscription, due_at: datetime) -> bool:
    if sub.added_at is None or ensure_utc(sub.added_at) > due_at:
        return False
    return sub.offsets_changed_at is None or ensure_utc(sub.offsets_changed_at) <= due_at


def _as_skipped(job: PlannedJob, reason: str) -> PlannedJob:
    return PlannedJob(
        job.job_id, job.user_id, job.nation_id, job.kind, job.offset_min, job.exit_at, job.due_at,
        status=JOB_SKIPPED, reason=reason,
    )


def _plan_unprotected(
    sub: Subscription,
    jobs: Sequence[JobSnapshot],
    pending_leads: Sequence[JobSnapshot],
    now: datetime,
) -> SubscriptionPlan:
    plan = SubscriptionPlan()
    expected_exits = [
        ensure_utc(j.exit_at) for j in jobs if j.kind == JOB_KIND_LEAD and j.status != JOB_CANCELLED
    ]
    latest_expected = max(expected_exits, default=None)
    early_jobs = [j for j in jobs if j.kind == JOB_KIND_EARLY_EXIT]

    if latest_expected is not None and latest_expected > turn_start(now):
        # Protection ended before the turn change we planned for.
        for job in pending_leads:
            plan.cancel.append((job.job_id, "exited_early"))
        early_id = early_exit_job_id(sub.user_id, sub.nation_id, latest_expected)
        if not any(j.job_id == early_id for j in early_jobs):
            plan.create.append(
                PlannedJob(
                    early_id, sub.user_id, sub.nation_id, JOB_KIND_EARLY_EXIT, None,
                    latest_expected, now,
                )
            )
        # The dispatcher removes the reminder once the notice has gone out.
        return plan

    for job in pending_leads:
        plan.cancel.append((job.job_id, "exited"))
    if any(j.status in JOB_ACTIVE_STATUSES for j in early_jobs):
        return plan
    plan.remove_subscription = True
    if latest_expected is None and not early_jobs:
        plan.problem = PROBLEM_NOT_PROTECTED
    return plan


def select_sendable(
    jobs: Sequence[JobSnapshot],
    now: datetime,
) -> tuple[list[JobSnapshot], list[tuple[JobSnapshot, str]]]:
    """Choose which due jobs to send.

    A user gets at most one message per watched nation per wave: an early-exit
    notice wins over timed reminders, and after downtime only the most recent
    missed timing is sent.

    Args:
        jobs: Jobs due in this wave.
        now: Current time.

    Returns:
        ``(send, skip)`` where ``skip`` pairs each dropped job with a reason.
    """
    now = ensure_utc(now)
    send: list[JobSnapshot] = []
    skip: list[tuple[JobSnapshot, str]] = []
    groups: dict[tuple[int, str], list[JobSnapshot]] = {}
    for job in jobs:
        groups.setdefault((job.user_id, job.nation_id), []).append(job)

    for group in groups.values():
        early = [j for j in group if j.kind == JOB_KIND_EARLY_EXIT]
        leads = [j for j in group if j.kind == JOB_KIND_LEAD]
        if early:
            send.append(early[0])
            skip.extend((j, "superseded") for j in early[1:])
            skip.extend((j, "exited_early") for j in leads)
            continue
        useful: list[JobSnapshot] = []
        for job in leads:
            if ensure_utc(job.exit_at) - now <= MIN_USEFUL_LEAD:
                skip.append((job, "too_late"))
            else:
                useful.append(job)
        if useful:
            useful.sort(key=lambda j: ensure_utc(j.due_at))
            send.append(useful[-1])
            skip.extend((j, "superseded") for j in useful[:-1])
    return send, skip


def burst_lead_seconds(
    count: int,
    rate_per_second: float,
    *,
    margin_seconds: float = 0.5,
    cap_seconds: float = 30.0,
) -> float:
    """How early to start a wave of ``count`` DMs so the last one lands on time."""
    if count <= 0 or rate_per_second <= 0:
        return 0.0
    return min(cap_seconds, count / rate_per_second + margin_seconds)


def message_nonce(job_ids: Iterable[str]) -> str:
    """Discord message nonce for a set of jobs; resending the same set is deduplicated."""
    digest = hashlib.sha256("|".join(sorted(job_ids)).encode("utf-8")).hexdigest()
    return digest[:DISCORD_NONCE_MAX_LENGTH]


def chunked(items: Sequence[Any], size: int) -> list[list[Any]]:
    """Split ``items`` into lists of at most ``size`` elements."""
    return [list(items[i:i + size]) for i in range(0, len(items), size)]


# --- Validation -------------------------------------------------------------


def normalize_nation_id(value: Any) -> Optional[str]:
    """Return a canonical numeric nation ID string, or None when invalid."""
    if isinstance(value, bool):
        return None
    text = str(value if value is not None else "").strip()
    if not text.isdigit():
        return None
    number = int(text)
    return str(number) if number > 0 else None


def sanitize_offsets(raw: Any) -> Optional[list[int]]:
    """Validate reminder timings.

    Args:
        raw: Candidate list of minutes before the exit.

    Returns:
        Unique minutes sorted largest first, or None when ``raw`` isn't a list of
        1-10 whole numbers between 1 and 10 080.
    """
    if not isinstance(raw, (list, tuple)):
        return None
    if not 1 <= len(raw) <= MAX_REMINDER_OFFSETS:
        return None
    out: set[int] = set()
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        if not 1 <= value <= MAX_REMINDER_OFFSET_MINUTES:
            return None
        out.add(value)
    return sorted(out, reverse=True)


def effective_offsets(raw: Any) -> list[int]:
    """Stored timings, falling back to the default when missing or invalid."""
    return sanitize_offsets(raw) or list(DEFAULT_REMINDER_OFFSETS)


def parse_offset_minutes(text: str) -> Optional[int]:
    """Parse one timing typed by a user; None unless it's 1-10 080 whole minutes."""
    cleaned = str(text or "").strip()
    if not cleaned.isdigit():
        return None
    value = int(cleaned)
    if not 1 <= value <= MAX_REMINDER_OFFSET_MINUTES:
        return None
    return value


def describe_offset(minutes: int) -> str:
    """Human-readable duration, e.g. ``90`` -> ``"1 hour 30 minutes"``."""
    days, rest = divmod(max(0, int(minutes)), 24 * 60)
    hours, mins = divmod(rest, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if mins or not parts:
        parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
    return " ".join(parts)


# --- Delivery channels ------------------------------------------------------


@dataclass(frozen=True)
class ChannelSettings:
    """Which delivery channels a user has switched on."""

    discord_dm: bool = True
    web_push: bool = False

    @classmethod
    def from_doc(cls, raw: Any) -> "ChannelSettings":
        """Read stored settings; a user is never left with every channel off."""
        if not isinstance(raw, Mapping):
            return cls()
        dm = raw.get("discord_dm")
        settings = cls(discord_dm=True if dm is None else bool(dm), web_push=bool(raw.get("web_push")))
        if not settings.discord_dm and not settings.web_push:
            return cls()
        return settings

    def to_doc(self) -> dict[str, bool]:
        return {"discord_dm": self.discord_dm, "web_push": self.web_push}


def validate_channel_settings(
    discord_dm: bool,
    web_push: bool,
    *,
    push_device_count: int,
    push_configured: bool,
) -> Optional[str]:
    """Return an error code when the requested channel settings aren't allowed."""
    if not discord_dm and not web_push:
        return CHANNEL_REQUIRED
    if web_push and not push_configured:
        return PUSH_NOT_CONFIGURED
    if web_push and push_device_count <= 0:
        return NO_PUSH_DEVICES
    return None


def needs_attention(
    channels: ChannelSettings,
    dm_state: str,
    *,
    push_device_count: int,
    push_configured: bool,
) -> bool:
    """True when a channel the user switched on can't deliver."""
    dm_broken = channels.discord_dm and dm_state == DM_STATE_FAILED
    push_broken = channels.web_push and (push_device_count <= 0 or not push_configured)
    return dm_broken or push_broken


class DmFailureReason(str, Enum):
    """Why Discord refused a DM, as far as its error code tells."""

    NO_MUTUAL_SERVER = "no_mutual_server"
    DMS_CLOSED = "dms_closed"
    UNKNOWN_USER = "unknown_user"
    OTHER = "other"


class DeliveryOutcome(str, Enum):
    """What to do after a Discord send attempt."""

    DELIVERED = "delivered"
    REFUSED = "refused"
    RETRY = "retry"
    CHANNEL_GONE = "channel_gone"
    FAILED = "failed"


# Discord JSON error codes: https://docs.discord.com/developers/topics/opcodes-and-status-codes
_REFUSED_CODES: dict[int, DmFailureReason] = {
    50007: DmFailureReason.DMS_CLOSED,  # Cannot send messages to this user
    50278: DmFailureReason.NO_MUTUAL_SERVER,  # No mutual guilds
    10013: DmFailureReason.UNKNOWN_USER,
    50033: DmFailureReason.UNKNOWN_USER,  # Invalid recipient
}
_RETRY_CODES = frozenset({
    40003,  # Opening direct messages too fast
    40004,  # Send messages has been temporarily disabled
    130000,  # API resource overloaded
})
_UNKNOWN_CHANNEL_CODE = 10003


def classify_discord_error(
    status: Optional[int],
    code: Optional[int],
) -> tuple[DeliveryOutcome, Optional[DmFailureReason]]:
    """Classify a failed Discord request.

    Args:
        status: HTTP status, or None for network errors and timeouts.
        code: Discord JSON error code (0 when the body had none).

    Returns:
        The outcome and, for refusals, the most likely reason.
    """
    if code in _REFUSED_CODES:
        return DeliveryOutcome.REFUSED, _REFUSED_CODES[int(code)]
    if code in _RETRY_CODES:
        return DeliveryOutcome.RETRY, None
    if code == _UNKNOWN_CHANNEL_CODE or (status == 404 and not code):
        return DeliveryOutcome.CHANNEL_GONE, None
    if status is None or status == 429 or status >= 500:
        return DeliveryOutcome.RETRY, None
    if status == 403:
        # A 403 without a Discord error code comes from Cloudflare, not the user's settings.
        if not code:
            return DeliveryOutcome.RETRY, None
        return DeliveryOutcome.REFUSED, DmFailureReason.OTHER
    return DeliveryOutcome.FAILED, None


def failure_reason_for_code(code: Optional[int]) -> Optional[str]:
    """Reason string stored alongside a DM failure code."""
    if code is None:
        return None
    reason = _REFUSED_CODES.get(int(code))
    return (reason or DmFailureReason.OTHER).value


# --- Browser push -----------------------------------------------------------

_PUSH_HOSTS = frozenset({
    "fcm.googleapis.com",
    "android.googleapis.com",
    "updates.push.services.mozilla.com",
    "web.push.apple.com",
})
_PUSH_HOST_SUFFIXES = (
    ".push.services.mozilla.com",
    ".notify.windows.com",
    ".push.apple.com",
)
MAX_PUSH_ENDPOINT_LENGTH = 2048


def is_allowed_push_endpoint(endpoint: Any) -> bool:
    """Only accept HTTPS endpoints on the browser vendors' push services.

    The bot POSTs to stored endpoints, so anything else would let a user point it at
    arbitrary URLs.
    """
    if not isinstance(endpoint, str) or not endpoint or len(endpoint) > MAX_PUSH_ENDPOINT_LENGTH:
        return False
    try:
        parsed = urlparse(endpoint)
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme != "https" or parsed.username or parsed.password or port not in (None, 443):
        return False
    host = (parsed.hostname or "").lower()
    return host in _PUSH_HOSTS or host.endswith(_PUSH_HOST_SUFFIXES)


def b64url_decode(value: str) -> bytes:
    """Decode unpadded base64url."""
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def valid_push_keys(p256dh: Any, auth: Any) -> bool:
    """Check the subscription keys: a P-256 public point and a 16-byte auth secret."""
    if not isinstance(p256dh, str) or not isinstance(auth, str):
        return False
    if len(p256dh) > 200 or len(auth) > 100:
        return False
    try:
        point = b64url_decode(p256dh)
        secret = b64url_decode(auth)
    except (binascii.Error, ValueError):
        return False
    return len(point) == 65 and point[0] == 4 and len(secret) == 16


def push_device_id(endpoint: str) -> str:
    """Stable, non-secret identifier for a push subscription endpoint."""
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:32]


def push_ttl_seconds(exit_at: Optional[datetime], now: datetime, *, minimum: int = 60) -> int:
    """How long a push service may hold a notification before dropping it.

    Expires shortly after the exit so an undelivered reminder never shows up after
    the target has left protection.
    """
    if exit_at is None:
        return minimum
    remaining = int((ensure_utc(exit_at) - ensure_utc(now)).total_seconds()) + 60
    return max(minimum, remaining)


def push_topic(nation_id: str) -> str:
    """Topic header so a newer notice about a nation replaces an undelivered older one."""
    return f"beige-{nation_id}"[:32]
