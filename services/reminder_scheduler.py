"""On-time delivery of beige reminders.

The scheduler keeps ``reminder_jobs`` in line with each watched nation's exit time and
sends due jobs by Discord DM and browser push. Storage, the Politics & War status
source, message rendering and the delivery channels are injected, so the scheduling
rules can be tested with fakes and no Discord or Mongo connection.

Loops:
    status    Every ~100 s: batched turn counts for every watched nation, then planning.
    changes   Every ~5 s: picks up watch-list and timing edits from the website and bot.
    dispatch  Sleeps until the next wave; big waves start early so the last DM still
              lands on time.
    test DMs  Every ~2 s: sends queued test DMs.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Iterable, Mapping, Optional, Protocol, Sequence

from database import reminders as reminder_db
from infra.webpush import PushOutcome, PushResult
from logic import reminders as rules

logger = logging.getLogger(__name__)

Outcome = rules.DeliveryOutcome
_EARLY_EXIT_PUSH_TTL = timedelta(minutes=15)


# --- Collaborators ----------------------------------------------------------


class Clock(Protocol):
    """Time source; tests substitute a virtual clock."""

    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    """Real time."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(max(0.0, seconds))


class StatusFetcher(Protocol):
    """Reads beige and vacation-mode turns from Politics & War."""

    async def fetch(self, nation_ids: Sequence[str]) -> dict[str, tuple[int, int]]:
        """Return ``{nation_id: (beige_turns, vacation_mode_turns)}``; unknown nations are omitted."""
        ...


@dataclass(frozen=True)
class DmSendResult:
    """Outcome of one Discord DM attempt.

    Attributes:
        outcome: What happened.
        code: Discord JSON error code, when Discord returned one.
        reason: Likely cause of a refusal.
        status: HTTP status, when there was a response.
        channel_id: DM channel used or created, so it can be stored.
        message_id: ID of the delivered message.
    """

    outcome: rules.DeliveryOutcome
    code: Optional[int] = None
    reason: Optional[rules.DmFailureReason] = None
    status: Optional[int] = None
    channel_id: Optional[int] = None
    message_id: Optional[int] = None


class DiscordDelivery(Protocol):
    """Sends DMs through the bot."""

    async def ensure_dm_channel(self, user_id: int) -> DmSendResult: ...

    async def send_reminder(
        self,
        user_id: int,
        channel_id: Optional[int],
        embeds: Sequence[Mapping[str, Any]],
        nonce: str,
    ) -> DmSendResult: ...

    async def send_test_dm(self, user_id: int, channel_id: Optional[int], test_id: str) -> DmSendResult: ...


class PushDelivery(Protocol):
    """Sends one browser push message."""

    async def send(
        self,
        subscription: Mapping[str, Any],
        payload: Mapping[str, Any],
        *,
        ttl: int,
        topic: Optional[str],
    ) -> PushResult: ...


@dataclass(frozen=True)
class RenderedReminder:
    """A reminder ready to send on every channel."""

    embed: dict[str, Any]
    push_payload: dict[str, Any]
    nation_name: Optional[str] = None


class ReminderRenderer(Protocol):
    """Builds reminder messages; implementations cache per nation and exit."""

    async def render(
        self,
        job: Mapping[str, Any],
        status: Optional[rules.NationStatus],
        now: datetime,
    ) -> RenderedReminder: ...


class ReminderStore(Protocol):
    """Persistence used by the scheduler (see :class:`MongoReminderStore`)."""

    async def ensure_indexes(self) -> None: ...
    async def load_watching_users(self) -> list[dict[str, Any]]: ...
    async def load_users_changed_since(self, since: datetime) -> list[dict[str, Any]]: ...
    async def load_profiles(self, user_ids: Iterable[int]) -> dict[int, dict[str, Any]]: ...
    async def load_jobs_for_users(self, user_ids: Iterable[int], *, exits_after: datetime) -> list[rules.JobSnapshot]: ...
    async def insert_jobs(self, jobs: Sequence[rules.PlannedJob], now: datetime) -> int: ...
    async def cancel_jobs(self, cancels: Sequence[tuple[str, str]], now: datetime) -> int: ...
    async def remove_subscription(self, user_id: int, nation_id: str, now: datetime) -> None: ...
    async def add_problem(self, user_id: int, problem: Mapping[str, Any]) -> None: ...
    async def pending_jobs_due_by(self, until: datetime) -> list[dict[str, Any]]: ...
    async def next_pending_due_at(self) -> Optional[datetime]: ...
    async def claim_jobs(self, job_ids: Sequence[str], claim_id: str, now: datetime) -> list[dict[str, Any]]: ...
    async def finish_jobs(self, claim_id: str, updates: Sequence[tuple[str, Mapping[str, Any]]], now: datetime) -> None: ...
    async def release_jobs(self, job_ids: Sequence[str], claim_id: str, now: datetime, *, retry_at: Optional[datetime]) -> None: ...
    async def recover_stale_claims(self, older_than: datetime, now: datetime) -> int: ...
    async def set_dm_channel_id(self, user_id: int, channel_id: Optional[int]) -> None: ...
    async def record_dm_success(self, user_id: int, now: datetime) -> None: ...
    async def record_dm_failure(self, user_id: int, now: datetime, *, code: Optional[int], reason: Optional[str], notify: bool) -> None: ...
    async def clear_dm_pending(self, user_id: int) -> None: ...
    async def push_subscriptions_by_user(self, user_ids: Iterable[int]) -> dict[int, list[dict[str, Any]]]: ...
    async def record_push_results(self, *, delivered: Iterable[str], failed: Iterable[str], gone: Iterable[str], now: datetime) -> None: ...
    async def turn_off_push_channel_if_no_devices(self, user_id: int) -> None: ...
    async def claim_next_test_dm(self, now: datetime) -> Optional[dict[str, Any]]: ...
    async def finish_test_dm(self, test_id: str, *, state: str, now: datetime, code: Optional[int] = None, reason: Optional[str] = None, message_id: Optional[int] = None) -> None: ...
    async def recover_stale_test_dms(self, older_than: datetime) -> int: ...


# --- Configuration and bookkeeping -------------------------------------------


@dataclass(frozen=True)
class SchedulerConfig:
    """Tuning knobs; defaults suit a single bot process."""

    status_poll_seconds: float = 100.0
    changes_poll_seconds: float = 5.0
    test_dm_poll_seconds: float = 2.0
    dm_rate_per_second: float = 25.0
    dm_concurrency: int = 10
    push_concurrency: int = 20
    idle_sleep_seconds: float = 5.0
    prepare_ahead_seconds: float = 90.0
    burst_lead_cap_seconds: float = 30.0
    retry_delay_seconds: float = 20.0
    max_attempts: int = 3
    stale_claim_seconds: float = 300.0
    status_fetch_timeout_seconds: float = 90.0
    presend_fetch_timeout_seconds: float = 8.0
    missing_nation_threshold: int = 3
    job_history: timedelta = timedelta(days=1)
    # The changes loop re-reads this far back: writers stamp edits before committing
    # them, so a later commit can carry an earlier stamp than one already seen.
    changes_overlap_seconds: float = 30.0
    # Consecutive failures of a loop before it is reported to the debug channel.
    loop_failure_report_threshold: int = 3


class RatePacer:
    """Spaces Discord requests into fixed slots so bursts never exceed the rate."""

    def __init__(self, rate_per_second: float, clock: Clock) -> None:
        self._interval = 1.0 / max(rate_per_second, 0.1)
        self._clock = clock
        self._next_slot = 0.0
        self._slow_until = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        """Wait for the next free slot."""
        async with self._lock:
            now = self._clock.monotonic()
            interval = self._interval * (2 if now < self._slow_until else 1)
            slot = max(now, self._next_slot)
            self._next_slot = slot + interval
        if slot > now:
            await self._clock.sleep(slot - now)

    def slow_down(self, seconds: float = 60.0) -> None:
        """Halve the rate for a while after Discord rate-limits us."""
        self._slow_until = self._clock.monotonic() + seconds


@dataclass
class _PushTally:
    delivered: int = 0
    retry: int = 0
    gone: int = 0
    failed: int = 0

    def report(self) -> dict[str, int]:
        return {"delivered": self.delivered, "retry": self.retry, "gone": self.gone, "failed": self.failed}


@dataclass
class _UserOutcome:
    updates: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    retries: list[str] = field(default_factory=list)
    sent: int = 0
    failed: int = 0
    lateness_ms: list[int] = field(default_factory=list)
    dm_delivered: int = 0
    dm_refused: int = 0
    dm_errors: int = 0
    push_delivered: int = 0
    push_failed: int = 0
    push_removed: int = 0


@dataclass
class WaveSummary:
    """What happened to one group of reminders due in the same second."""

    due_at: datetime
    claimed: int = 0
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    retried: int = 0
    lateness_ms: list[int] = field(default_factory=list)
    dm_delivered: int = 0
    dm_refused: int = 0
    dm_errors: int = 0
    push_delivered: int = 0
    push_failed: int = 0
    push_removed: int = 0

    def add(self, outcome: _UserOutcome) -> None:
        self.sent += outcome.sent
        self.failed += outcome.failed
        self.lateness_ms.extend(outcome.lateness_ms)
        self.dm_delivered += outcome.dm_delivered
        self.dm_refused += outcome.dm_refused
        self.dm_errors += outcome.dm_errors
        self.push_delivered += outcome.push_delivered
        self.push_failed += outcome.push_failed
        self.push_removed += outcome.push_removed

    def percentile(self, fraction: float) -> Optional[int]:
        """Lateness percentile in milliseconds (negative means early)."""
        if not self.lateness_ms:
            return None
        ordered = sorted(self.lateness_ms)
        index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
        return ordered[index]

    def log_line(self) -> str:
        return (
            f"event=reminder_wave due={self.due_at.isoformat()} claimed={self.claimed} "
            f"sent={self.sent} skipped={self.skipped} failed={self.failed} retried={self.retried} "
            f"p50_ms={self.percentile(0.5)} p95_ms={self.percentile(0.95)} "
            f"max_ms={max(self.lateness_ms) if self.lateness_ms else None} "
            f"dm_ok={self.dm_delivered} dm_refused={self.dm_refused} dm_errors={self.dm_errors} "
            f"push_ok={self.push_delivered} push_failed={self.push_failed} push_removed={self.push_removed}"
        )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _ms(delta: timedelta) -> int:
    return int(delta.total_seconds() * 1000)


def _reason_value(result: DmSendResult) -> str:
    return (result.reason or rules.DmFailureReason.OTHER).value


def _group_waves(docs: Sequence[Mapping[str, Any]]) -> list[tuple[datetime, list[Mapping[str, Any]]]]:
    waves: dict[int, list[Mapping[str, Any]]] = {}
    for doc in docs:
        waves.setdefault(rules.to_epoch(doc["due_at"]), []).append(doc)
    return [
        (datetime.fromtimestamp(epoch, tz=timezone.utc), wave)
        for epoch, wave in sorted(waves.items())
    ]


# --- Scheduler ----------------------------------------------------------------


class ReminderScheduler:
    """Plans and delivers beige reminders on time."""

    def __init__(
        self,
        *,
        store: ReminderStore,
        fetcher: StatusFetcher,
        discord: DiscordDelivery,
        renderer: ReminderRenderer,
        push: Optional[PushDelivery] = None,
        clock: Optional[Clock] = None,
        config: Optional[SchedulerConfig] = None,
        on_wave: Optional[Callable[[WaveSummary], Awaitable[None]]] = None,
        on_crash: Optional[Callable[[str, BaseException], Awaitable[None]]] = None,
        on_notice: Optional[Callable[[int], None]] = None,
    ) -> None:
        self.store = store
        self.fetcher = fetcher
        self.discord = discord
        self.renderer = renderer
        self.push = push
        self.clock = clock or SystemClock()
        self.config = config or SchedulerConfig()
        self._on_wave = on_wave
        self._on_crash = on_crash
        self._on_notice = on_notice
        self._tracked: dict[str, rules.TrackedNation] = {}
        self._misses: dict[str, int] = {}
        self._prepared: set[str] = set()
        self._changes_since: Optional[datetime] = None
        self._changes_seen: dict[int, datetime] = {}
        self._loop_failures: dict[str, int] = {}
        self._wake = asyncio.Event()
        self._planning_lock = asyncio.Lock()
        self._dm_slots = asyncio.Semaphore(self.config.dm_concurrency)
        self._push_slots = asyncio.Semaphore(self.config.push_concurrency)
        self._pacer = RatePacer(self.config.dm_rate_per_second, self.clock)

    # -- lifecycle --

    def wake(self) -> None:
        """Ask the dispatcher to look for due jobs now."""
        self._wake.set()

    def tracked_status(self, nation_id: str) -> Optional[rules.TrackedNation]:
        """Latest reading and exit estimate for a nation, if it is being watched."""
        return self._tracked.get(nation_id)

    async def run(self) -> None:
        """Run every loop until cancelled, restarting any loop that crashes."""
        await self.store.ensure_indexes()
        now = self.clock.now()
        # A new process owns nothing yet, so anything left "sending" was interrupted.
        recovered = await self.store.recover_stale_claims(now, now)
        await self.store.recover_stale_test_dms(now)
        if recovered:
            logger.warning("Requeued %s reminder jobs interrupted by a restart", recovered)
        self._changes_since = now
        await asyncio.gather(
            self._supervise("status", self._status_loop),
            self._supervise("changes", self._changes_loop),
            self._supervise("dispatch", self._dispatch_loop),
            self._supervise("test_dms", self._test_dm_loop),
        )

    async def _supervise(self, name: str, loop: Callable[[], Awaitable[None]]) -> None:
        backoff = 1.0
        while True:
            try:
                await loop()
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - a crashed loop must restart
                logger.exception("Reminder %s loop crashed; restarting in %.0fs", name, backoff)
                await self._report_crash(name, exc)
                await self.clock.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    async def _report_crash(self, name: str, exc: BaseException) -> None:
        if self._on_crash is None:
            return
        try:
            await self._on_crash(name, exc)
        except Exception:  # noqa: BLE001
            logger.exception("Reporting the reminder %s failure failed", name)

    async def _loop_failed(self, name: str, exc: BaseException) -> None:
        """Log a failed loop pass; a loop that keeps failing is reported like a crash."""
        logger.exception("Reminder %s pass failed", name, exc_info=exc)
        count = self._loop_failures.get(name, 0) + 1
        self._loop_failures[name] = count
        if count >= self.config.loop_failure_report_threshold:
            await self._report_crash(name, exc)

    def _loop_ok(self, name: str) -> None:
        self._loop_failures.pop(name, None)

    async def _status_loop(self) -> None:
        while True:
            started = self.clock.monotonic()
            try:
                await self.refresh_all()
                self._loop_ok("status")
            except Exception as exc:  # noqa: BLE001
                await self._loop_failed("status", exc)
            elapsed = self.clock.monotonic() - started
            await self.clock.sleep(max(1.0, self.config.status_poll_seconds - elapsed))

    async def _changes_loop(self) -> None:
        while True:
            await self.clock.sleep(self.config.changes_poll_seconds)
            try:
                await self.refresh_changed()
                self._loop_ok("changes")
            except Exception as exc:  # noqa: BLE001
                await self._loop_failed("changes", exc)

    async def _dispatch_loop(self) -> None:
        last_recovery = self.clock.monotonic()
        while True:
            self._wake.clear()
            try:
                delay = await self.dispatch_due()
                self._loop_ok("dispatch")
            except Exception as exc:  # noqa: BLE001
                await self._loop_failed("dispatch", exc)
                delay = self.config.idle_sleep_seconds
            if self.clock.monotonic() - last_recovery >= self.config.stale_claim_seconds:
                last_recovery = self.clock.monotonic()
                now = self.clock.now()
                older_than = now - timedelta(seconds=self.config.stale_claim_seconds)
                try:
                    await self.store.recover_stale_claims(older_than, now)
                    await self.store.recover_stale_test_dms(older_than)
                except Exception:  # noqa: BLE001
                    logger.exception("Recovering stale reminder claims failed")
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=max(0.05, delay))
            except asyncio.TimeoutError:
                pass

    async def _test_dm_loop(self) -> None:
        while True:
            try:
                await self.process_test_dms()
                self._loop_ok("test_dms")
            except Exception as exc:  # noqa: BLE001
                await self._loop_failed("test_dms", exc)
            await self.clock.sleep(self.config.test_dm_poll_seconds)

    # -- planning --

    async def refresh_all(self) -> None:
        """Read turn counts for every watched nation and bring all jobs up to date."""
        users = await self.store.load_watching_users()
        subs = [sub for user in users for sub in reminder_db.subscriptions_for(user)]
        nation_ids = sorted({sub.nation_id for sub in subs})
        if nation_ids:
            statuses = await asyncio.wait_for(
                self.fetcher.fetch(nation_ids), self.config.status_fetch_timeout_seconds
            )
            self._record_statuses(nation_ids, statuses, self.clock.now())
        planned = await self._plan({sub.user_id for sub in subs}, self.clock.now())
        watched = set(nation_ids) | {sub.nation_id for sub in planned}
        for nation_id in [n for n in self._tracked if n not in watched]:
            self._tracked.pop(nation_id, None)
            self._misses.pop(nation_id, None)

    async def refresh_changed(self) -> int:
        """Plan for users who changed their watch list or timings since the last check.

        Returns:
            How many changed profiles were processed.
        """
        since = self._changes_since or self.clock.now()
        overlap = timedelta(seconds=self.config.changes_overlap_seconds)
        users = await self.store.load_users_changed_since(since - overlap)
        changed: dict[int, tuple[datetime, dict[str, Any]]] = {}
        for user in users:
            user_id = _int_or_none(user.get("user"))
            stamp = user.get("beige_alerts_updated_at")
            if user_id is None or not isinstance(stamp, datetime):
                continue
            stamp = rules.ensure_utc(stamp)
            self._changes_since = max(self._changes_since or stamp, stamp)
            if self._changes_seen.get(user_id) != stamp:  # Not planned in an overlapping pass yet.
                changed[user_id] = (stamp, user)
        horizon = (self._changes_since or since) - overlap
        self._changes_seen = {uid: stamp for uid, stamp in self._changes_seen.items() if stamp > horizon}
        if not changed:
            return 0

        subs = [sub for _, user in changed.values() for sub in reminder_db.subscriptions_for(user)]
        unknown = sorted({sub.nation_id for sub in subs if sub.nation_id not in self._tracked})
        if unknown:
            statuses = await asyncio.wait_for(
                self.fetcher.fetch(unknown), self.config.status_fetch_timeout_seconds
            )
            self._record_statuses(unknown, statuses, self.clock.now())
        await self._plan(set(changed), self.clock.now())
        # Only now: a failed pass is retried while the edit is inside the overlap.
        for user_id, (stamp, _) in changed.items():
            self._changes_seen[user_id] = stamp
        return len(changed)

    def _record_statuses(
        self,
        requested: Sequence[str],
        statuses: Mapping[str, tuple[int, int]],
        observed_at: datetime,
    ) -> None:
        for nation_id in requested:
            turns = statuses.get(nation_id)
            if turns is None:
                self._misses[nation_id] = self._misses.get(nation_id, 0) + 1
                continue
            self._misses.pop(nation_id, None)
            status = rules.NationStatus(nation_id, int(turns[0]), int(turns[1]), observed_at)
            estimate = rules.estimate_exit(status, self._tracked.get(nation_id))
            self._tracked[nation_id] = rules.TrackedNation(status, estimate)

    async def _plan(self, user_ids: Iterable[int], now: datetime) -> list[rules.Subscription]:
        """Bring the given users' jobs in line with their current subscriptions.

        Profiles are read inside the planning lock, next to the jobs, so a plan never
        works from a watch list or timings older than another plan's.

        Returns:
            The subscriptions that were planned.
        """
        ids = set(user_ids)
        if not ids:
            return []
        async with self._planning_lock:
            profiles = await self.store.load_profiles(ids)
            subs = [sub for profile in profiles.values() for sub in reminder_db.subscriptions_for(profile)]
            jobs = await self.store.load_jobs_for_users(ids, exits_after=now - self.config.job_history)
            watched = {(sub.user_id, sub.nation_id) for sub in subs}
            by_pair: dict[tuple[int, str], list[rules.JobSnapshot]] = {}
            for job in jobs:
                by_pair.setdefault((job.user_id, job.nation_id), []).append(job)

            creates: list[rules.PlannedJob] = []
            cancels: list[tuple[str, str]] = [
                (job.job_id, "unsubscribed")
                for job in jobs
                if job.status == rules.JOB_PENDING and (job.user_id, job.nation_id) not in watched
            ]
            removals: list[tuple[rules.Subscription, Optional[str]]] = []
            for sub in subs:
                if self._misses.get(sub.nation_id, 0) >= self.config.missing_nation_threshold:
                    removals.append((sub, rules.PROBLEM_NATION_MISSING))
                    continue
                tracked = self._tracked.get(sub.nation_id)
                if tracked is None:
                    continue
                plan = rules.plan_subscription(
                    sub, tracked.estimate, by_pair.get((sub.user_id, sub.nation_id), []), now
                )
                creates.extend(plan.create)
                cancels.extend(plan.cancel)
                if plan.remove_subscription:
                    removals.append((sub, plan.problem))

            if cancels:
                await self.store.cancel_jobs(cancels, now)
            if creates and await self.store.insert_jobs(creates, now):
                self.wake()
            for sub, problem in removals:
                await self.store.remove_subscription(sub.user_id, sub.nation_id, now)
                if problem is not None:
                    await self.store.add_problem(
                        sub.user_id,
                        reminder_db.problem_doc(problem, sub.nation_id, now=now, reminder_removed=True),
                    )
            for sub, problem in removals:
                if problem == rules.PROBLEM_NATION_MISSING:
                    self._misses.pop(sub.nation_id, None)
            return subs

    # -- dispatch --

    async def dispatch_due(self) -> float:
        """Send every wave whose start time has come.

        Returns:
            Seconds until the dispatcher should look again.
        """
        cfg = self.config
        now = self.clock.now()
        lookahead = timedelta(seconds=max(cfg.prepare_ahead_seconds, cfg.burst_lead_cap_seconds))
        docs = await self.store.pending_jobs_due_by(now + lookahead)
        if not docs:
            next_due = await self.store.next_pending_due_at()
            if next_due is None:
                return cfg.idle_sleep_seconds
            return _clamp((next_due - lookahead - now).total_seconds(), 0.05, cfg.idle_sleep_seconds)

        waves = []
        for due_at, wave in _group_waves(docs):
            lead = rules.burst_lead_seconds(
                len(wave), cfg.dm_rate_per_second, cap_seconds=cfg.burst_lead_cap_seconds
            )
            waves.append((due_at - timedelta(seconds=lead), due_at, wave))

        # Every wave whose start has come goes out together, so after downtime only the
        # latest missed timing per nation is sent; upcoming ones are prepared afterwards.
        now = self.clock.now()
        started = [(due_at, wave) for start_at, due_at, wave in waves if start_at <= now]
        if started:
            await self._send_wave(min(due_at for due_at, _ in started), [doc for _, wave in started for doc in wave])
            return 0.05

        await self._prepare([doc for doc in docs if str(doc["_id"]) not in self._prepared])
        now = self.clock.now()
        next_start = min((start_at - now).total_seconds() for start_at, _, _ in waves)
        return _clamp(next_start, 0.05, cfg.idle_sleep_seconds)

    async def _prepare(self, docs: Sequence[Mapping[str, Any]]) -> None:
        """Open DM channels and render messages shortly before jobs are due."""
        if not docs:
            return
        profiles = await self.store.load_profiles({int(doc["user_id"]) for doc in docs})
        missing = [
            user_id
            for user_id, profile in profiles.items()
            if rules.ChannelSettings.from_doc(profile.get("reminder_channels")).discord_dm
            and not profile.get("dm_channel_id")
        ]

        async def open_channel(user_id: int) -> None:
            async with self._dm_slots:
                await self._pacer.wait()
                result = await self.discord.ensure_dm_channel(user_id)
            if result.channel_id is not None:
                await self.store.set_dm_channel_id(user_id, result.channel_id)

        now = self.clock.now()
        outcomes = await asyncio.gather(
            *(open_channel(user_id) for user_id in missing),
            *(self.renderer.render(doc, self._status_for(str(doc["nation_id"])), now) for doc in docs),
            return_exceptions=True,
        )
        for outcome in outcomes:
            if isinstance(outcome, Exception):
                # Channels are opened and messages rendered again at send time.
                logger.warning("Preparing reminders failed: %r", outcome)
        self._prepared.update(str(doc["_id"]) for doc in docs)

    def _status_for(self, nation_id: str) -> Optional[rules.NationStatus]:
        tracked = self._tracked.get(nation_id)
        return tracked.status if tracked else None

    async def _refresh_stale_statuses(self, nation_ids: Iterable[str]) -> None:
        """Re-read nations whose last reading is too old to trust right before sending."""
        now = self.clock.now()
        max_age = timedelta(seconds=2 * self.config.status_poll_seconds)
        stale = sorted(
            nation_id
            for nation_id in set(nation_ids)
            if (tracked := self._tracked.get(nation_id)) is None
            or now - tracked.status.observed_at > max_age
        )
        if not stale:
            return
        try:
            statuses = await asyncio.wait_for(
                self.fetcher.fetch(stale), self.config.presend_fetch_timeout_seconds
            )
        except Exception as exc:  # noqa: BLE001 - send on the planned schedule anyway
            logger.warning("Pre-send status check failed for %s nations: %s", len(stale), exc)
            return
        self._record_statuses(stale, statuses, self.clock.now())

    def _presend_verdict(
        self, job: rules.JobSnapshot, profile: Optional[Mapping[str, Any]]
    ) -> Optional[dict[str, Any]]:
        """None when the job should be sent, otherwise the final job update."""
        if profile is None or job.nation_id not in reminder_db.watched_nation_ids(profile):
            return {"status": rules.JOB_CANCELLED, "reason": "unsubscribed"}
        if job.kind != rules.JOB_KIND_LEAD:
            return None
        tracked = self._tracked.get(job.nation_id)
        if tracked is None or not tracked.estimate.definitive:
            return None
        if tracked.estimate.exit_at is None:
            # Skipped rather than cancelled so planning still sees the expected exit
            # and sends the early-exit notice.
            return {"status": rules.JOB_SKIPPED, "reason": "exited_early"}
        if rules.ensure_utc(tracked.estimate.exit_at) != job.exit_at:
            return {"status": rules.JOB_CANCELLED, "reason": "exit_changed"}
        return None

    async def _send_wave(self, due_at: datetime, wave: Sequence[Mapping[str, Any]]) -> WaveSummary:
        cfg = self.config
        summary = WaveSummary(due_at=due_at)
        claim_id = uuid.uuid4().hex
        claimed = await self.store.claim_jobs([str(doc["_id"]) for doc in wave], claim_id, self.clock.now())
        summary.claimed = len(claimed)
        if not claimed:
            return summary
        docs = {str(doc["_id"]): doc for doc in claimed}
        for job_id in docs:
            self._prepared.discard(job_id)

        now = self.clock.now()
        send, skip = rules.select_sendable([reminder_db.snapshot_from_doc(doc) for doc in claimed], now)
        updates: list[tuple[str, dict[str, Any]]] = [
            (job.job_id, {"status": rules.JOB_SKIPPED, "reason": reason}) for job, reason in skip
        ]
        summary.skipped += len(skip)

        profiles = await self.store.load_profiles({job.user_id for job in send})
        await self._refresh_stale_statuses({job.nation_id for job in send})
        deliverable: list[rules.JobSnapshot] = []
        replan: set[int] = set()
        for job in send:
            verdict = self._presend_verdict(job, profiles.get(job.user_id))
            if verdict is None:
                deliverable.append(job)
                continue
            updates.append((job.job_id, verdict))
            summary.skipped += 1
            if verdict["reason"] in ("exited_early", "exit_changed"):
                replan.add(job.user_id)

        retries: list[str] = []
        if deliverable:
            rendered: dict[str, RenderedReminder] = {}
            results = await asyncio.gather(
                *(self.renderer.render(docs[job.job_id], self._status_for(job.nation_id), now) for job in deliverable),
                return_exceptions=True,
            )
            for job, result in zip(deliverable, results):
                if isinstance(result, BaseException):
                    if not isinstance(result, Exception):
                        raise result
                    logger.error("Rendering reminder %s failed", job.job_id, exc_info=result)
                    retries.append(job.job_id)
                else:
                    rendered[job.job_id] = result
            by_user: dict[int, list[rules.JobSnapshot]] = {}
            for job in deliverable:
                if job.job_id in rendered:
                    by_user.setdefault(job.user_id, []).append(job)

            push_users = [
                user_id
                for user_id in by_user
                if rules.ChannelSettings.from_doc(profiles[user_id].get("reminder_channels")).web_push
            ]
            subscriptions = (
                await self.store.push_subscriptions_by_user(push_users)
                if push_users and self.push is not None
                else {}
            )
            outcomes = await asyncio.gather(
                *(
                    self._deliver_safely(
                        user_id, jobs, profiles[user_id], rendered, subscriptions.get(user_id, []), docs
                    )
                    for user_id, jobs in by_user.items()
                )
            )
            for outcome in outcomes:
                updates.extend(outcome.updates)
                retries.extend(outcome.retries)
                summary.add(outcome)

        # Retries after unexpected errors get the same attempt limit as delivery retries,
        # so a job that keeps failing (an early-exit notice never becomes too late) ends.
        exhausted = {job_id for job_id in retries if int(docs[job_id].get("attempts") or 1) >= cfg.max_attempts}
        if exhausted:
            updates.extend((job_id, {"status": rules.JOB_FAILED, "reason": "not_delivered"}) for job_id in exhausted)
            summary.failed += len(exhausted)
            retries = [job_id for job_id in retries if job_id not in exhausted]

        finished_at = self.clock.now()
        await self.store.finish_jobs(claim_id, updates, finished_at)
        if retries:
            await self.store.release_jobs(
                retries,
                claim_id,
                finished_at,
                retry_at=finished_at + timedelta(seconds=cfg.retry_delay_seconds),
            )
            summary.retried += len(retries)
        if replan:
            await self._plan(replan, self.clock.now())
        await self._report_wave(summary)
        return summary

    async def _report_wave(self, summary: WaveSummary) -> None:
        logger.info(summary.log_line())
        if self._on_wave is not None:
            try:
                await self._on_wave(summary)
            except Exception:  # noqa: BLE001
                logger.exception("Reporting a reminder wave failed")

    async def _deliver_safely(
        self,
        user_id: int,
        jobs: Sequence[rules.JobSnapshot],
        profile: Mapping[str, Any],
        rendered: Mapping[str, RenderedReminder],
        subscriptions: Sequence[Mapping[str, Any]],
        docs: Mapping[str, Mapping[str, Any]],
    ) -> _UserOutcome:
        try:
            return await self._deliver_to_user(user_id, jobs, profile, rendered, subscriptions, docs)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - one user's failure must not stall the wave
            logger.exception("Delivering reminders to user %s failed unexpectedly", user_id)
            outcome = _UserOutcome()
            outcome.retries.extend(job.job_id for job in jobs)
            return outcome

    async def _deliver_to_user(
        self,
        user_id: int,
        jobs: Sequence[rules.JobSnapshot],
        profile: Mapping[str, Any],
        rendered: Mapping[str, RenderedReminder],
        subscriptions: Sequence[Mapping[str, Any]],
        docs: Mapping[str, Mapping[str, Any]],
    ) -> _UserOutcome:
        out = _UserOutcome()
        channels = rules.ChannelSettings.from_doc(profile.get("reminder_channels"))
        ordered = sorted(jobs, key=lambda job: (job.due_at, job.nation_id))
        # Without a push sender in this process a push-only user would get nothing, so
        # Discord stands in rather than the reminder being dropped.
        use_dm = channels.discord_dm or (channels.web_push and self.push is None)
        use_push = channels.web_push and self.push is not None and bool(subscriptions)

        async def no_results() -> dict[str, Any]:
            return {}

        # The channels are independent, so pushes don't wait behind the Discord queue.
        dm_results, push_results = await asyncio.gather(
            self._send_dms(user_id, profile, ordered, rendered) if use_dm else no_results(),
            self._send_pushes(user_id, ordered, rendered, subscriptions, out) if use_push else no_results(),
        )

        now = self.clock.now()
        dm_outcomes = list(dm_results.values())
        # Messages have gone out, so bookkeeping failures below must not trigger a resend.
        if any(result.outcome is Outcome.DELIVERED for result in dm_outcomes):
            await self._bookkeep("recording a delivered DM", self.store.record_dm_success(user_id, now))
        refusal = next((r for r in dm_outcomes if r.outcome is Outcome.REFUSED), None)
        if refusal is not None:
            await self._bookkeep(
                "recording a refused DM",
                self.store.record_dm_failure(
                    user_id, now, code=refusal.code, reason=_reason_value(refusal), notify=True
                ),
            )
            if self._on_notice is not None:
                self._on_notice(user_id)

        for job in ordered:
            dm = dm_results.get(job.job_id)
            push = push_results.get(job.job_id)
            dm_ok = dm is not None and dm.outcome is Outcome.DELIVERED
            push_ok = push is not None and push.delivered > 0
            report = {
                "discord_dm": None if dm is None else {"outcome": dm.outcome.value, "code": dm.code},
                "web_push": None if push is None else push.report(),
            }
            if dm is not None:
                if dm_ok:
                    out.dm_delivered += 1
                elif dm.outcome is Outcome.REFUSED:
                    out.dm_refused += 1
                else:
                    out.dm_errors += 1

            if dm_ok or push_ok:
                lateness = _ms(now - job.due_at)
                out.sent += 1
                out.lateness_ms.append(lateness)
                out.updates.append(
                    (job.job_id, {"status": rules.JOB_SENT, "sent_at": now, "lateness_ms": lateness, "channels": report})
                )
                if dm is not None and dm.outcome is Outcome.REFUSED:
                    await self._add_problem(user_id, job, rendered, rules.PROBLEM_DM_REFUSED, dm.code, False, now)
                elif push is not None and not push_ok and dm_ok:
                    await self._add_problem(user_id, job, rendered, rules.PROBLEM_PUSH_FAILED, None, False, now)
                if job.kind == rules.JOB_KIND_EARLY_EXIT:
                    await self._bookkeep(
                        "ending a reminder", self.store.remove_subscription(user_id, job.nation_id, now)
                    )
                continue

            retryable = (
                (dm is not None and dm.outcome in (Outcome.RETRY, Outcome.CHANNEL_GONE))
                or (push is not None and push.retry > 0)
                # The last push device just expired, which switches the user to Discord
                # DMs; the retry goes out that way.
                or (dm is None and push is not None and push.gone > 0)
            )
            attempts = int(docs[job.job_id].get("attempts") or 1)
            enough_time = job.kind == rules.JOB_KIND_EARLY_EXIT or (
                job.exit_at - now > rules.MIN_USEFUL_LEAD + timedelta(seconds=self.config.retry_delay_seconds)
            )
            if retryable and attempts < self.config.max_attempts and enough_time:
                out.retries.append(job.job_id)
                continue

            # Nothing reached the user. A refusal or a missing channel is a settings
            # problem, so the reminder is removed and the user is told why.
            settings_problem = (dm is None or dm.outcome is Outcome.REFUSED) and not retryable
            remove = settings_problem or job.kind == rules.JOB_KIND_EARLY_EXIT
            out.failed += 1
            out.updates.append((job.job_id, {"status": rules.JOB_FAILED, "reason": "not_delivered", "channels": report}))
            if remove:
                await self._bookkeep(
                    "removing an undeliverable reminder", self.store.remove_subscription(user_id, job.nation_id, now)
                )
            await self._add_problem(
                user_id, job, rendered, rules.PROBLEM_NOT_DELIVERED, dm.code if dm else None, remove, now
            )
        return out

    async def _bookkeep(self, what: str, operation: Awaitable[Any]) -> None:
        """Run a status write that follows a delivery; a failure is logged, not retried."""
        try:
            await operation
        except Exception:  # noqa: BLE001
            logger.exception("Reminder bookkeeping failed while %s", what)

    async def _add_problem(
        self,
        user_id: int,
        job: rules.JobSnapshot,
        rendered: Mapping[str, RenderedReminder],
        kind: str,
        code: Optional[int],
        removed: bool,
        now: datetime,
    ) -> None:
        message = rendered.get(job.job_id)
        await self._bookkeep(
            "recording a reminder problem",
            self.store.add_problem(
                user_id,
                reminder_db.problem_doc(
                    kind,
                    job.nation_id,
                    now=now,
                    reminder_removed=removed,
                    nation_name=message.nation_name if message else None,
                    offset_min=job.offset_min,
                    due_at=job.due_at,
                    code=code,
                ),
            ),
        )

    async def _send_dms(
        self,
        user_id: int,
        profile: Mapping[str, Any],
        jobs: Sequence[rules.JobSnapshot],
        rendered: Mapping[str, RenderedReminder],
    ) -> dict[str, DmSendResult]:
        results: dict[str, DmSendResult] = {}
        channel_id = _int_or_none(profile.get("dm_channel_id"))
        refusal: Optional[DmSendResult] = None
        # Discord caps a message at 10 embeds and 6000 characters across them.
        messages = rules.pack_by_size(
            list(jobs),
            [rules.embed_text_length(rendered[job.job_id].embed) for job in jobs],
            max_count=rules.MAX_EMBEDS_PER_MESSAGE,
            max_size=rules.MAX_EMBED_CHARS_PER_MESSAGE,
        )
        for chunk in messages:
            embeds = [rendered[job.job_id].embed for job in chunk]
            nonce = rules.message_nonce(job.job_id for job in chunk)
            async with self._dm_slots:
                await self._pacer.wait()
                result = await self.discord.send_reminder(user_id, channel_id, embeds, nonce)
            if result.status == 429:
                self._pacer.slow_down()
            if result.channel_id is not None and result.channel_id != channel_id:
                channel_id = result.channel_id
                await self._bookkeep("storing a DM channel", self.store.set_dm_channel_id(user_id, channel_id))
            for job in chunk:
                results[job.job_id] = result
            if result.outcome is Outcome.REFUSED:
                refusal = result
                break
        if refusal is not None:
            # Further DMs would be refused too; don't spend requests on them.
            for job in jobs:
                results.setdefault(job.job_id, refusal)
        return results

    async def _send_pushes(
        self,
        user_id: int,
        jobs: Sequence[rules.JobSnapshot],
        rendered: Mapping[str, RenderedReminder],
        subscriptions: Sequence[Mapping[str, Any]],
        out: _UserOutcome,
    ) -> dict[str, _PushTally]:
        assert self.push is not None
        now = self.clock.now()

        async def send_one(job: rules.JobSnapshot, subscription: Mapping[str, Any]) -> tuple[str, str, PushResult]:
            exit_for_ttl = job.exit_at if job.kind == rules.JOB_KIND_LEAD else now + _EARLY_EXIT_PUSH_TTL
            async with self._push_slots:
                try:
                    result = await self.push.send(
                        subscription,
                        rendered[job.job_id].push_payload,
                        ttl=rules.push_ttl_seconds(exit_for_ttl, now),
                        topic=rules.push_topic(job.nation_id),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Push to a device of user %s raised: %s", user_id, exc)
                    result = PushResult(PushOutcome.RETRY, None, type(exc).__name__)
            return job.job_id, str(subscription.get("_id")), result

        results = await asyncio.gather(*(send_one(job, sub) for job in jobs for sub in subscriptions))
        tallies = {job.job_id: _PushTally() for job in jobs}
        delivered: set[str] = set()
        failed: set[str] = set()
        gone: set[str] = set()
        for job_id, device_id, result in results:
            tally = tallies[job_id]
            if result.outcome is PushOutcome.DELIVERED:
                tally.delivered += 1
                delivered.add(device_id)
                out.push_delivered += 1
            elif result.outcome is PushOutcome.GONE:
                tally.gone += 1
                gone.add(device_id)
            elif result.outcome is PushOutcome.RETRY:
                tally.retry += 1
                failed.add(device_id)
                out.push_failed += 1
            else:
                tally.failed += 1
                failed.add(device_id)
                out.push_failed += 1
                logger.warning("Push service rejected a reminder for user %s (HTTP %s)", user_id, result.status)
        out.push_removed += len(gone)
        await self._bookkeep(
            "recording push results",
            self.store.record_push_results(
                delivered=delivered - gone, failed=failed - gone - delivered, gone=gone, now=self.clock.now()
            ),
        )
        if gone:
            await self._bookkeep(
                "updating push settings", self.store.turn_off_push_channel_if_no_devices(user_id)
            )
        return tallies

    # -- test DMs --

    async def process_test_dms(self) -> int:
        """Send every queued test DM.

        Returns:
            How many test DMs were processed.
        """
        processed = 0
        while True:
            doc = await self.store.claim_next_test_dm(self.clock.now())
            if doc is None:
                return processed
            processed += 1
            try:
                await self._send_test_dm(doc)
            except Exception:  # noqa: BLE001 - a claimed test DM must not stay "sending"
                logger.exception("Processing test DM %s failed", doc.get("_id"))
                await self._bookkeep(
                    "closing a failed test DM",
                    self.store.finish_test_dm(
                        str(doc["_id"]),
                        state=rules.TEST_DM_FAILED,
                        now=self.clock.now(),
                        reason=rules.DmFailureReason.OTHER.value,
                    ),
                )
                await self._bookkeep("clearing a pending DM check", self.store.clear_dm_pending(int(doc["user_id"])))

    async def _send_test_dm(self, doc: Mapping[str, Any]) -> None:
        user_id = int(doc["user_id"])
        test_id = str(doc["_id"])
        profile = (await self.store.load_profiles([user_id])).get(user_id) or {}
        channel_id = _int_or_none(profile.get("dm_channel_id"))
        try:
            async with self._dm_slots:
                await self._pacer.wait()
                result = await self.discord.send_test_dm(user_id, channel_id, test_id)
        except Exception:  # noqa: BLE001
            logger.exception("Sending test DM %s failed unexpectedly", test_id)
            result = DmSendResult(Outcome.RETRY)
        if result.status == 429:
            self._pacer.slow_down()
        now = self.clock.now()
        if result.channel_id is not None and result.channel_id != channel_id:
            await self.store.set_dm_channel_id(user_id, result.channel_id)
        if result.outcome is Outcome.DELIVERED:
            await self.store.finish_test_dm(test_id, state=rules.TEST_DM_SENT, now=now, message_id=result.message_id)
            await self.store.record_dm_success(user_id, now)
        elif result.outcome is Outcome.REFUSED:
            reason = _reason_value(result)
            await self.store.finish_test_dm(
                test_id, state=rules.TEST_DM_FAILED, now=now, code=result.code, reason=reason
            )
            # People who asked from Discord hear about it on their next command;
            # the website shows the result straight away.
            notify = doc.get("source") == rules.TEST_DM_SOURCE_BOT
            await self.store.record_dm_failure(user_id, now, code=result.code, reason=reason, notify=notify)
            if notify and self._on_notice is not None:
                self._on_notice(user_id)
        else:
            await self.store.finish_test_dm(
                test_id,
                state=rules.TEST_DM_FAILED,
                now=now,
                code=result.code,
                reason=rules.DmFailureReason.OTHER.value,
            )
            await self.store.clear_dm_pending(user_id)


class MongoReminderStore:
    """:class:`ReminderStore` backed by the bot's Motor database."""

    def __init__(self, db: Any) -> None:
        self.db = db

    async def ensure_indexes(self) -> None:
        await reminder_db.ensure_indexes(self.db)

    async def load_watching_users(self) -> list[dict[str, Any]]:
        return await reminder_db.load_watching_users(self.db)

    async def load_users_changed_since(self, since: datetime) -> list[dict[str, Any]]:
        return await reminder_db.load_users_changed_since(self.db, since)

    async def load_profiles(self, user_ids: Iterable[int]) -> dict[int, dict[str, Any]]:
        return await reminder_db.load_profiles(self.db, user_ids)

    async def load_jobs_for_users(
        self, user_ids: Iterable[int], *, exits_after: datetime
    ) -> list[rules.JobSnapshot]:
        return await reminder_db.load_jobs_for_users(self.db, user_ids, exits_after=exits_after)

    async def insert_jobs(self, jobs: Sequence[rules.PlannedJob], now: datetime) -> int:
        return await reminder_db.insert_jobs(self.db, jobs, now)

    async def cancel_jobs(self, cancels: Sequence[tuple[str, str]], now: datetime) -> int:
        return await reminder_db.cancel_jobs(self.db, cancels, now)

    async def remove_subscription(self, user_id: int, nation_id: str, now: datetime) -> None:
        await reminder_db.remove_alert(self.db, user_id, nation_id, now)
        await reminder_db.cancel_pending_jobs_for(self.db, user_id, nation_id, "reminder_removed", now)

    async def add_problem(self, user_id: int, problem: Mapping[str, Any]) -> None:
        await reminder_db.add_problem(self.db, user_id, problem)

    async def pending_jobs_due_by(self, until: datetime) -> list[dict[str, Any]]:
        return await reminder_db.pending_jobs_due_by(self.db, until)

    async def next_pending_due_at(self) -> Optional[datetime]:
        return await reminder_db.next_pending_due_at(self.db)

    async def claim_jobs(self, job_ids: Sequence[str], claim_id: str, now: datetime) -> list[dict[str, Any]]:
        return await reminder_db.claim_jobs(self.db, job_ids, claim_id, now)

    async def finish_jobs(
        self, claim_id: str, updates: Sequence[tuple[str, Mapping[str, Any]]], now: datetime
    ) -> None:
        await reminder_db.finish_jobs(self.db, claim_id, updates, now)

    async def release_jobs(
        self, job_ids: Sequence[str], claim_id: str, now: datetime, *, retry_at: Optional[datetime]
    ) -> None:
        await reminder_db.release_jobs(self.db, job_ids, claim_id, now, retry_at=retry_at)

    async def recover_stale_claims(self, older_than: datetime, now: datetime) -> int:
        return await reminder_db.recover_stale_claims(self.db, older_than, now)

    async def set_dm_channel_id(self, user_id: int, channel_id: Optional[int]) -> None:
        await reminder_db.set_dm_channel_id(self.db, user_id, channel_id)

    async def record_dm_success(self, user_id: int, now: datetime) -> None:
        await reminder_db.record_dm_success(self.db, user_id, now)

    async def record_dm_failure(
        self, user_id: int, now: datetime, *, code: Optional[int], reason: Optional[str], notify: bool
    ) -> None:
        await reminder_db.record_dm_failure(self.db, user_id, now, code=code, reason=reason, notify=notify)

    async def clear_dm_pending(self, user_id: int) -> None:
        await reminder_db.clear_dm_pending(self.db, user_id)

    async def push_subscriptions_by_user(self, user_ids: Iterable[int]) -> dict[int, list[dict[str, Any]]]:
        return await reminder_db.push_subscriptions_by_user(self.db, user_ids)

    async def record_push_results(
        self, *, delivered: Iterable[str], failed: Iterable[str], gone: Iterable[str], now: datetime
    ) -> None:
        await reminder_db.record_push_results(self.db, delivered=delivered, failed=failed, gone=gone, now=now)

    async def turn_off_push_channel_if_no_devices(self, user_id: int) -> None:
        await reminder_db.turn_off_push_channel_if_no_devices(self.db, user_id)

    async def claim_next_test_dm(self, now: datetime) -> Optional[dict[str, Any]]:
        return await reminder_db.claim_next_test_dm(self.db, now)

    async def finish_test_dm(
        self,
        test_id: str,
        *,
        state: str,
        now: datetime,
        code: Optional[int] = None,
        reason: Optional[str] = None,
        message_id: Optional[int] = None,
    ) -> None:
        await reminder_db.finish_test_dm(
            self.db, test_id, state=state, now=now, code=code, reason=reason, message_id=message_id
        )

    async def recover_stale_test_dms(self, older_than: datetime) -> int:
        return await reminder_db.recover_stale_test_dms(self.db, older_than)
