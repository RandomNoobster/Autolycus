"""Wires the reminder scheduler into the running bot."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Mapping, Optional

import aiohttp
import discord

from bot.discord_utils import errors as err_util
from bot.reminders import notices
from bot.reminders.discord_delivery import DiscordDmDelivery
from bot.reminders.render import ReminderRenderer
from bot.reminders.status import PnwStatusFetcher
from core.config import REMINDER_DM_RATE_PER_SECOND, REMINDER_STATUS_POLL_SECONDS
from database.mongo import get_db
from infra.webpush import PushResult, WebPushSender, get_push_sender
from services.reminder_scheduler import (
    MongoReminderStore,
    ReminderScheduler,
    SchedulerConfig,
    WaveSummary,
)

logger = logging.getLogger(__name__)

LATE_WAVE_P95_MS = 10_000
_CRASH_REPORT_INTERVAL_SECONDS = 10 * 60


class BrowserPushDelivery:
    """Scheduler push channel backed by one shared aiohttp session."""

    def __init__(self, sender: WebPushSender) -> None:
        self._sender = sender
        self._session: Optional[aiohttp.ClientSession] = None

    async def send(
        self,
        subscription: Mapping[str, Any],
        payload: Mapping[str, Any],
        *,
        ttl: int,
        topic: Optional[str],
    ) -> PushResult:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit_per_host=50))
        return await self._sender.send(self._session, subscription, payload, ttl=ttl, topic=topic)

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()


class _Reporter:
    """Posts crashes and delivery anomalies to the admin debug channel."""

    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot
        self._last_crash_report: dict[str, float] = {}

    def _debug_channel(self) -> Optional[Any]:
        raw = os.getenv("DEBUG_CHANNEL")
        try:
            return self.bot.get_channel(int(raw)) if raw else None
        except (TypeError, ValueError):
            return None

    async def on_wave(self, summary: WaveSummary) -> None:
        p95 = summary.percentile(0.95)
        late = p95 is not None and p95 > LATE_WAVE_P95_MS
        failing = summary.failed >= 5 and summary.failed * 2 >= max(1, summary.claimed)
        if not (late or failing):
            return
        channel = self._debug_channel()
        if channel is None:
            return
        problem = "late" if late else "failing"
        embed = err_util.error_embed(
            f"Reminder wave {problem}",
            f"```{summary.log_line()[:3900]}```",
            reference=None,
            color=err_util.ERROR_EMBED_COLOR,
            contact_footer=None,
        )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            logger.warning("Could not post a reminder anomaly to the debug channel")

    async def on_crash(self, loop_name: str, exc: BaseException) -> None:
        now = asyncio.get_running_loop().time()
        if now - self._last_crash_report.get(loop_name, -1e9) < _CRASH_REPORT_INTERVAL_SECONDS:
            return
        self._last_crash_report[loop_name] = now
        await err_util.report_bot_exception(
            self.bot, exc, logger, title=f"Reminder {loop_name} loop crashed"
        )


def build_scheduler(bot: discord.Client) -> tuple[ReminderScheduler, Optional[BrowserPushDelivery]]:
    """Create the scheduler with Discord, Politics & War, Mongo and push adapters."""
    api_key = os.getenv("API_KEY") or ""
    sender = get_push_sender()
    push = BrowserPushDelivery(sender) if sender is not None else None
    reporter = _Reporter(bot)
    scheduler = ReminderScheduler(
        store=MongoReminderStore(get_db()),
        fetcher=PnwStatusFetcher(api_key),
        discord=DiscordDmDelivery(bot),
        renderer=ReminderRenderer(api_key),
        push=push,
        config=SchedulerConfig(
            status_poll_seconds=float(REMINDER_STATUS_POLL_SECONDS),
            dm_rate_per_second=float(REMINDER_DM_RATE_PER_SECOND),
        ),
        on_wave=reporter.on_wave,
        on_crash=reporter.on_crash,
        on_notice=notices.mark_pending,
    )
    return scheduler, push


async def run_reminders(bot: discord.Client) -> None:
    """Start reminder delivery once the bot is ready; restarts after startup failures."""
    await bot.wait_until_ready()
    await notices.load_pending()
    backoff = 5.0
    while True:
        scheduler, push = build_scheduler(bot)
        bot.reminder_scheduler = scheduler  # type: ignore[attr-defined]
        logger.info(
            "Reminder scheduler starting (browser push %s)", "enabled" if push is not None else "disabled"
        )
        try:
            await scheduler.run()
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Reminder scheduler stopped; restarting in %.0fs", backoff)
            await _Reporter(bot).on_crash("scheduler", exc)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300.0)
        finally:
            if push is not None:
                await push.close()
