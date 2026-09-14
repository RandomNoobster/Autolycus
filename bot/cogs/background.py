"""Starts beige reminder delivery when the bot loads.

Scheduling lives in ``services/reminder_scheduler.py``; ``bot/reminders/runtime.py``
connects it to Discord, Politics & War, MongoDB and browser push.
"""
import asyncio
import logging

from discord.ext import commands

from bot.reminders.runtime import run_reminders

logger = logging.getLogger(__name__)


def _log_task_end(task: "asyncio.Task[None]") -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Reminder delivery stopped unexpectedly", exc_info=exc)


class ReminderDelivery(commands.Cog):
    """Owns the background reminder task (started once per process)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        if getattr(bot, "reminder_task", None) is None:
            task = bot.loop.create_task(run_reminders(bot))
            task.add_done_callback(_log_task_end)
            bot.reminder_task = task


def setup(bot: commands.Bot) -> None:
    """Load the reminder delivery cog."""
    bot.add_cog(ReminderDelivery(bot))
