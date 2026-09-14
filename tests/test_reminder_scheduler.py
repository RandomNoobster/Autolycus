"""Scheduler tests with an in-memory store, a fake clock and fake delivery channels."""
import asyncio
import copy
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import reminders as reminder_db
from infra.webpush import PushOutcome, PushResult
from logic import reminders as rules
from services.reminder_scheduler import (
    DmSendResult,
    RatePacer,
    ReminderScheduler,
    RenderedReminder,
    SchedulerConfig,
    WaveSummary,
)

UTC = timezone.utc
Outcome = rules.DeliveryOutcome


def at(hour, minute=0, second=0, ms=0):
    return datetime(2026, 9, 14, hour, minute, second, ms * 1000, tzinfo=UTC)


class FakeClock:
    def __init__(self, start):
        self._now = start
        self._mono = 0.0

    def now(self):
        return self._now

    def monotonic(self):
        return self._mono

    async def sleep(self, seconds):
        if seconds > 0:
            self.advance(seconds)
        await asyncio.sleep(0)

    def advance(self, seconds):
        self._now += timedelta(seconds=seconds)
        self._mono += seconds

    def set(self, when):
        self.advance((when - self._now).total_seconds())


class FakeFetcher:
    def __init__(self, statuses):
        self.statuses = dict(statuses)
        self.calls = []

    async def fetch(self, nation_ids):
        self.calls.append(list(nation_ids))
        return {n: self.statuses[n] for n in nation_ids if n in self.statuses}


class FakeDiscord:
    def __init__(self, clock, outcomes=None, scripts=None):
        self.clock = clock
        self.outcomes = outcomes or {}
        self.scripts = {k: list(v) for k, v in (scripts or {}).items()}
        self.sent = []
        self.tests = []

    def _result(self, user_id, channel_id):
        script = self.scripts.get(user_id)
        if script:
            return script.pop(0)
        return self.outcomes.get(user_id) or DmSendResult(
            Outcome.DELIVERED, channel_id=channel_id or 900, message_id=1
        )

    async def ensure_dm_channel(self, user_id):
        return DmSendResult(Outcome.DELIVERED, channel_id=900 + user_id)

    async def send_reminder(self, user_id, channel_id, embeds, nonce):
        result = self._result(user_id, channel_id)
        self.sent.append({"user_id": user_id, "embeds": list(embeds), "nonce": nonce, "at": self.clock.now()})
        return result

    async def send_test_dm(self, user_id, channel_id, test_id):
        result = self._result(user_id, channel_id)
        self.tests.append((user_id, test_id))
        return result


class FakeRenderer:
    async def render(self, job, status, now):
        nation_id = str(job["nation_id"])
        return RenderedReminder(
            embed={"title": f"Nation {nation_id}", "kind": job.get("kind")},
            push_payload={"notification": {"title": nation_id}},
            nation_name=f"Nation {nation_id}",
        )


class FakePush:
    def __init__(self, default=PushResult(PushOutcome.DELIVERED, 201)):
        self.default = default
        self.sent = []

    async def send(self, subscription, payload, *, ttl, topic):
        self.sent.append((subscription["_id"], ttl, topic))
        return self.default


class FakeStore:
    def __init__(self):
        self.users = {}
        self.jobs = {}
        self.tests = {}
        self.push = {}

    async def ensure_indexes(self):
        return None

    async def load_watching_users(self):
        return [copy.deepcopy(u) for u in self.users.values() if u.get("beige_alerts")]

    async def load_users_changed_since(self, since):
        return [
            copy.deepcopy(u)
            for u in self.users.values()
            if u.get("beige_alerts_updated_at") and rules.ensure_utc(u["beige_alerts_updated_at"]) > since
        ]

    async def load_profiles(self, user_ids):
        return {uid: copy.deepcopy(self.users[uid]) for uid in set(user_ids) if uid in self.users}

    async def load_jobs_for_users(self, user_ids, *, exits_after):
        ids = set(user_ids)
        return [
            reminder_db.snapshot_from_doc(job)
            for job in self.jobs.values()
            if job["user_id"] in ids and job["exit_at"] >= exits_after
        ]

    async def insert_jobs(self, jobs, now):
        created = 0
        for job in jobs:
            if job.job_id not in self.jobs:
                self.jobs[job.job_id] = {"_id": job.job_id, **reminder_db._job_insert_doc(job, now)}
                created += 1
        return created

    async def cancel_jobs(self, cancels, now):
        count = 0
        for job_id, reason in cancels:
            job = self.jobs.get(job_id)
            if job and job["status"] == rules.JOB_PENDING:
                job.update(status=rules.JOB_CANCELLED, reason=reason)
                count += 1
        return count

    async def remove_subscription(self, user_id, nation_id, now):
        user = self.users.get(user_id)
        if user:
            user["beige_alerts"] = [n for n in user.get("beige_alerts", []) if str(n) != nation_id]
        for job in self.jobs.values():
            if job["user_id"] == user_id and job["nation_id"] == nation_id and job["status"] == rules.JOB_PENDING:
                job.update(status=rules.JOB_CANCELLED, reason="reminder_removed")

    async def add_problem(self, user_id, problem):
        self.users[user_id].setdefault("reminder_problems", []).insert(0, dict(problem))

    async def pending_jobs_due_by(self, until):
        due = [copy.deepcopy(j) for j in self.jobs.values() if j["status"] == rules.JOB_PENDING and j["due_at"] <= until]
        return sorted(due, key=lambda j: j["due_at"])

    async def next_pending_due_at(self):
        dues = [j["due_at"] for j in self.jobs.values() if j["status"] == rules.JOB_PENDING]
        return min(dues) if dues else None

    async def claim_jobs(self, job_ids, claim_id, now):
        claimed = []
        for job_id in job_ids:
            job = self.jobs.get(job_id)
            if job and job["status"] == rules.JOB_PENDING:
                job.update(status=rules.JOB_SENDING, claim_id=claim_id, attempts=job.get("attempts", 0) + 1)
                claimed.append(copy.deepcopy(job))
        return claimed

    async def finish_jobs(self, claim_id, updates, now):
        for job_id, fields in updates:
            job = self.jobs[job_id]
            if job.get("claim_id") == claim_id:
                job.update(fields)

    async def release_jobs(self, job_ids, claim_id, now, *, retry_at):
        for job_id in job_ids:
            job = self.jobs[job_id]
            if job.get("claim_id") == claim_id:
                job.update(status=rules.JOB_PENDING, claim_id=None)
                if retry_at is not None:
                    job["due_at"] = retry_at

    async def recover_stale_claims(self, older_than, now):
        return 0

    async def set_dm_channel_id(self, user_id, channel_id):
        self.users[user_id]["dm_channel_id"] = channel_id

    def _dm(self, user_id):
        return self.users[user_id].setdefault("dm_delivery", {})

    async def record_dm_success(self, user_id, now):
        dm = self._dm(user_id)
        dm.update(code=None, reason=None, last_success_at=now)
        if dm.get("state") != rules.DM_STATE_CONFIRMED:
            dm["state"] = rules.DM_STATE_OK

    async def record_dm_failure(self, user_id, now, *, code, reason, notify):
        self._dm(user_id).update(state=rules.DM_STATE_FAILED, code=code, reason=reason)
        if notify:
            self.users[user_id]["dm_notice_pending"] = True

    async def clear_dm_pending(self, user_id):
        dm = self._dm(user_id)
        if dm.get("state") == rules.DM_STATE_PENDING:
            dm["state"] = rules.DM_STATE_UNKNOWN

    async def push_subscriptions_by_user(self, user_ids):
        ids = set(user_ids)
        out = {}
        for sub in self.push.values():
            if sub["user_id"] in ids:
                out.setdefault(sub["user_id"], []).append(copy.deepcopy(sub))
        return out

    async def record_push_results(self, *, delivered, failed, gone, now):
        for device_id in gone:
            self.push.pop(device_id, None)

    async def turn_off_push_channel_if_no_devices(self, user_id):
        if any(s["user_id"] == user_id for s in self.push.values()):
            return
        if (self.users[user_id].get("reminder_channels") or {}).get("web_push"):
            self.users[user_id]["reminder_channels"] = {"discord_dm": True, "web_push": False}

    async def claim_next_test_dm(self, now):
        queued = sorted(
            (t for t in self.tests.values() if t["state"] == rules.TEST_DM_QUEUED),
            key=lambda t: t["requested_at"],
        )
        if not queued:
            return None
        queued[0]["state"] = rules.TEST_DM_SENDING
        return copy.deepcopy(queued[0])

    async def finish_test_dm(self, test_id, *, state, now, code=None, reason=None, message_id=None):
        self.tests[test_id].update(state=state, code=code, reason=reason, message_id=message_id)

    async def recover_stale_test_dms(self, older_than):
        return 0


def make_user(uid=7, nations=("100",), offsets=(15,), added=at(12), channels=None, dm_channel_id=555):
    doc = {
        "user": uid,
        "beige_alerts": list(nations),
        "beige_alerts_config": list(offsets),
        "dm_channel_id": dm_channel_id,
    }
    if added is not None:
        doc["beige_alert_added_at"] = {n: added for n in nations}
    if channels is not None:
        doc["reminder_channels"] = channels
    return doc


def build(store, clock, fetcher, discord, *, push=None, notices=None, **overrides):
    config = SchedulerConfig(**{"dm_rate_per_second": 1000.0, **overrides})
    return ReminderScheduler(
        store=store,
        fetcher=fetcher,
        discord=discord,
        renderer=FakeRenderer(),
        push=push,
        clock=clock,
        config=config,
        on_notice=(notices.append if notices is not None else None),
    )


def only_job(store):
    [job] = store.jobs.values()
    return job


def test_reminder_is_sent_at_its_due_time():
    async def scenario():
        clock = FakeClock(at(13, 30))
        store = FakeStore()
        store.users[7] = make_user()
        discord = FakeDiscord(clock)
        scheduler = build(store, clock, FakeFetcher({"100": (1, 0)}), discord)

        await scheduler.refresh_all()
        job = only_job(store)
        assert (job["exit_at"], job["due_at"], job["status"]) == (at(14), at(13, 45), rules.JOB_PENDING)

        clock.set(at(13, 44, 59))
        await scheduler.dispatch_due()
        assert discord.sent == []

        clock.set(at(13, 44, 59, ms=600))
        await scheduler.dispatch_due()
        assert len(discord.sent) == 1
        assert job["status"] == rules.JOB_SENT
        assert -1000 < job["lateness_ms"] <= 0
        assert store.users[7]["dm_delivery"]["state"] == rules.DM_STATE_OK

    asyncio.run(scenario())


def test_restart_does_not_resend_or_duplicate_jobs():
    async def scenario():
        clock = FakeClock(at(13, 30))
        store = FakeStore()
        store.users[7] = make_user()
        fetcher = FakeFetcher({"100": (1, 0)})
        discord = FakeDiscord(clock)
        first = build(store, clock, fetcher, discord)
        await first.refresh_all()
        clock.set(at(13, 45))
        await first.dispatch_due()
        assert len(discord.sent) == 1

        restarted = build(store, clock, fetcher, discord)
        await restarted.refresh_all()
        clock.advance(2)
        await restarted.dispatch_due()
        assert len(store.jobs) == 1
        assert len(discord.sent) == 1

    asyncio.run(scenario())


def test_refused_dm_removes_reminder_and_tells_the_user():
    async def scenario():
        clock = FakeClock(at(13, 30))
        store = FakeStore()
        store.users[7] = make_user()
        refused = DmSendResult(Outcome.REFUSED, code=50007, reason=rules.DmFailureReason.DMS_CLOSED, status=403, channel_id=555)
        notices = []
        scheduler = build(store, clock, FakeFetcher({"100": (1, 0)}), FakeDiscord(clock, outcomes={7: refused}), notices=notices)
        await scheduler.refresh_all()
        clock.set(at(13, 45))
        await scheduler.dispatch_due()

        job = only_job(store)
        user = store.users[7]
        assert job["status"] == rules.JOB_FAILED
        assert user["beige_alerts"] == []
        assert user["dm_delivery"]["state"] == rules.DM_STATE_FAILED
        assert user["dm_delivery"]["code"] == 50007
        problem = user["reminder_problems"][0]
        assert (problem["kind"], problem["reminder_removed"], problem["code"]) == (rules.PROBLEM_NOT_DELIVERED, True, 50007)
        assert notices == [7]

    asyncio.run(scenario())


def test_refused_dm_keeps_reminder_when_push_delivers():
    async def scenario():
        clock = FakeClock(at(13, 30))
        store = FakeStore()
        store.users[7] = make_user(channels={"discord_dm": True, "web_push": True})
        store.push["dev1"] = {"_id": "dev1", "user_id": 7, "endpoint": "https://fcm.googleapis.com/x", "keys": {}}
        refused = DmSendResult(Outcome.REFUSED, code=50278, reason=rules.DmFailureReason.NO_MUTUAL_SERVER, status=403)
        push = FakePush()
        scheduler = build(store, clock, FakeFetcher({"100": (1, 0)}), FakeDiscord(clock, outcomes={7: refused}), push=push)
        await scheduler.refresh_all()
        clock.set(at(13, 45))
        await scheduler.dispatch_due()

        job = only_job(store)
        assert job["status"] == rules.JOB_SENT
        assert store.users[7]["beige_alerts"] == ["100"]
        problem = store.users[7]["reminder_problems"][0]
        assert (problem["kind"], problem["reminder_removed"]) == (rules.PROBLEM_DM_REFUSED, False)
        assert push.sent == [("dev1", 15 * 60 + 60, "beige-100")]

    asyncio.run(scenario())


def test_temporary_error_is_retried():
    async def scenario():
        clock = FakeClock(at(13, 30))
        store = FakeStore()
        store.users[7] = make_user()
        discord = FakeDiscord(
            clock,
            scripts={7: [DmSendResult(Outcome.RETRY, status=503, channel_id=555), DmSendResult(Outcome.DELIVERED, channel_id=555, message_id=2)]},
        )
        scheduler = build(store, clock, FakeFetcher({"100": (1, 0)}), discord, retry_delay_seconds=20)
        await scheduler.refresh_all()
        clock.set(at(13, 45))
        await scheduler.dispatch_due()
        job = only_job(store)
        assert job["status"] == rules.JOB_PENDING
        assert job["due_at"] > at(13, 45, 19)

        clock.set(job["due_at"] + timedelta(seconds=1))
        await scheduler.dispatch_due()
        assert job["status"] == rules.JOB_SENT
        assert len(discord.sent) == 2

    asyncio.run(scenario())


def test_large_wave_starts_early_enough_to_finish_on_time():
    async def scenario():
        clock = FakeClock(at(13, 30))
        store = FakeStore()
        statuses = {}
        for i in range(50):
            nation = str(1000 + i)
            store.users[i + 1] = make_user(uid=i + 1, nations=(nation,))
            statuses[nation] = (1, 0)
        discord = FakeDiscord(clock)
        scheduler = build(store, clock, FakeFetcher(statuses), discord, dm_rate_per_second=25.0)
        await scheduler.refresh_all()

        clock.set(at(13, 44, 57))  # 50 DMs at 25/s need a 2.5 s head start
        await scheduler.dispatch_due()
        assert discord.sent == []

        clock.set(at(13, 44, 57, ms=600))
        await scheduler.dispatch_due()
        assert len(discord.sent) == 50

    asyncio.run(scenario())


def test_early_exit_sends_one_notice_and_ends_the_reminder():
    async def scenario():
        clock = FakeClock(at(13))
        store = FakeStore()
        store.users[7] = make_user()
        fetcher = FakeFetcher({"100": (3, 0)})
        discord = FakeDiscord(clock)
        scheduler = build(store, clock, fetcher, discord)
        await scheduler.refresh_all()
        lead = only_job(store)
        assert lead["exit_at"] == at(18)

        clock.set(at(15, 10))
        fetcher.statuses["100"] = (0, 0)
        await scheduler.refresh_all()
        assert lead["status"] == rules.JOB_CANCELLED
        early = next(j for j in store.jobs.values() if j["kind"] == rules.JOB_KIND_EARLY_EXIT)

        clock.advance(1)
        await scheduler.dispatch_due()
        assert early["status"] == rules.JOB_SENT
        assert [s["embeds"][0]["kind"] for s in discord.sent] == [rules.JOB_KIND_EARLY_EXIT]
        assert store.users[7]["beige_alerts"] == []

    asyncio.run(scenario())


def test_reminder_removed_before_due_is_not_sent():
    async def scenario():
        clock = FakeClock(at(13, 30))
        store = FakeStore()
        store.users[7] = make_user()
        discord = FakeDiscord(clock)
        scheduler = build(store, clock, FakeFetcher({"100": (1, 0)}), discord)
        await scheduler.refresh_all()
        store.users[7]["beige_alerts"] = []

        clock.set(at(13, 45))
        await scheduler.dispatch_due()
        assert discord.sent == []
        assert only_job(store)["status"] == rules.JOB_CANCELLED

    asyncio.run(scenario())


def test_push_only_user_without_devices_is_told_and_reminder_removed():
    async def scenario():
        clock = FakeClock(at(13, 30))
        store = FakeStore()
        store.users[7] = make_user(channels={"discord_dm": False, "web_push": True})
        discord = FakeDiscord(clock)
        scheduler = build(store, clock, FakeFetcher({"100": (1, 0)}), discord, push=FakePush())
        await scheduler.refresh_all()
        clock.set(at(13, 45))
        await scheduler.dispatch_due()

        assert discord.sent == []
        assert only_job(store)["status"] == rules.JOB_FAILED
        assert store.users[7]["beige_alerts"] == []
        assert store.users[7]["reminder_problems"][0]["kind"] == rules.PROBLEM_NOT_DELIVERED

    asyncio.run(scenario())


def test_new_reminder_from_website_is_planned_within_seconds():
    async def scenario():
        clock = FakeClock(at(13, 6))
        store = FakeStore()
        fetcher = FakeFetcher({"100": (1, 0)})
        scheduler = build(store, clock, fetcher, FakeDiscord(clock))
        scheduler._changes_since = at(13)

        store.users[7] = make_user(added=at(13, 5))
        store.users[7]["beige_alerts_updated_at"] = at(13, 5)
        assert await scheduler.refresh_changed() == 1
        assert fetcher.calls == [["100"]]
        assert only_job(store)["due_at"] == at(13, 45)
        assert await scheduler.refresh_changed() == 0

    asyncio.run(scenario())


def test_missing_nation_is_removed_after_repeated_misses():
    async def scenario():
        clock = FakeClock(at(13))
        store = FakeStore()
        store.users[7] = make_user()
        scheduler = build(store, clock, FakeFetcher({}), FakeDiscord(clock))
        for _ in range(3):
            await scheduler.refresh_all()
        assert store.users[7]["beige_alerts"] == []
        assert store.users[7]["reminder_problems"][0]["kind"] == rules.PROBLEM_NATION_MISSING

    asyncio.run(scenario())


def test_test_dms_record_delivery_and_refusals():
    async def scenario():
        clock = FakeClock(at(13))
        store = FakeStore()
        store.users[7] = make_user(nations=())
        refused = DmSendResult(Outcome.REFUSED, code=50278, reason=rules.DmFailureReason.NO_MUTUAL_SERVER, status=403)
        discord = FakeDiscord(clock, scripts={7: [DmSendResult(Outcome.DELIVERED, channel_id=555, message_id=9), refused]})
        notices = []
        scheduler = build(store, clock, FakeFetcher({}), discord, notices=notices)

        store.tests["t1"] = {"_id": "t1", "user_id": 7, "source": "website", "state": "queued", "requested_at": at(12)}
        assert await scheduler.process_test_dms() == 1
        assert store.tests["t1"]["state"] == rules.TEST_DM_SENT
        assert store.users[7]["dm_delivery"]["state"] == rules.DM_STATE_OK

        store.tests["t2"] = {"_id": "t2", "user_id": 7, "source": "bot", "state": "queued", "requested_at": at(12, 30)}
        await scheduler.process_test_dms()
        assert (store.tests["t2"]["state"], store.tests["t2"]["code"]) == (rules.TEST_DM_FAILED, 50278)
        assert store.users[7]["dm_delivery"]["reason"] == "no_mutual_server"
        assert notices == [7]

    asyncio.run(scenario())


def test_rate_pacer_spaces_requests():
    async def scenario():
        clock = FakeClock(at(12))
        pacer = RatePacer(10, clock)
        times = []
        for _ in range(4):
            await pacer.wait()
            times.append(round(clock.monotonic(), 3))
        assert times == [0.0, 0.1, 0.2, 0.3]

    asyncio.run(scenario())


def test_wave_summary_percentiles():
    summary = WaveSummary(due_at=at(12), lateness_ms=[400, 100, 300, 200])
    assert summary.percentile(0.5) == 200
    assert summary.percentile(0.95) == 400
    assert "event=reminder_wave" in summary.log_line()
