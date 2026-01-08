"""Background tasks for monitoring nation alerts and status updates.

This module manages the Discord bot's background scanning for nation beige alerts
and vacation mode transitions. It uses websocket subscriptions for real-time updates
and polls the Politics & War API periodically.
"""

import asyncio
import os
import traceback
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv
from main import logger, kit

from logic import api_client, common
from database import mongo as db_mongo

load_dotenv()

# Configuration
API_KEY = os.getenv("api_key")
DEBUG_CHANNEL_ID = int(os.getenv("debug_channel"))
SCAN_INTERVAL = 100  # seconds
REMINDER_THRESHOLD = 50  # seconds


class General(commands.Cog):
    """Background task cog for managing alert subscriptions and notifications."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the background tasks cog.

        Args:
            bot: The Discord bot instance.
        """
        self.bot = bot
        self.bot.bg_task = self.bot.loop.create_task(self.alert_scanner())

    async def alert_scanner(self) -> None:
        """Main alert scanner task that monitors nation status changes.

        Continuously monitors tracked nations for beige and vacation mode transitions,
        sending Discord DM reminders at configured intervals.
        """
        await self.bot.wait_until_ready()
        unique_ids: list[str] = []
        alerts: list[dict] = []
        debug_channel = self.bot.get_channel(DEBUG_CHANNEL_ID)

        # Subscribe to nation updates for real-time notifications
        nation_updates = await kit.subscribe("nation", "update")
        asyncio.ensure_future(
            self._handle_subscriptions(nation_updates, unique_ids, alerts)
        )

        while True:
            try:
                logger.debug("Scanning beige alerts")
                alerts = await self._fetch_active_alerts()
                unique_ids = await self._extract_nation_ids(alerts)

                if not unique_ids:
                    await asyncio.sleep(SCAN_INTERVAL)
                    continue

                nations_data = await self._fetch_nation_data(unique_ids)
                await self._check_and_remind_alerts(alerts, nations_data)

            except Exception as e:
                logger.error(f"Exception in alert scanner: {e}", exc_info=True)
                if debug_channel:
                    error_msg = common.cut_string(
                        f"**Exception caught!**\n"
                        f"Where: Scanning beige alerts\n\n"
                        f"Error:```{traceback.format_exc()}```"
                    )
                    await debug_channel.send(error_msg)

            await asyncio.sleep(SCAN_INTERVAL)

    async def _handle_subscriptions(
        self,
        subscription,
        unique_ids: list[str],
        alerts: list[dict],
    ) -> None:
        """Handle incoming nation subscription updates.

        Args:
            subscription: The websocket subscription iterator.
            unique_ids: List of unique nation IDs being tracked.
            alerts: List of active alert configurations.
        """
        async for update in subscription:
            try:
                nation_id = str(update.id)
                beige_turns = int(update.beige_turns)
                vm_turns = int(update.vacation_mode_turns)

                if nation_id in unique_ids:
                    if beige_turns == 0 and vm_turns == 0:
                        logger.info(f"Nation {nation_id} left status early")
                        await self._send_preemptive_reminder(nation_id, alerts)

            except Exception as e:
                logger.error(
                    f"Error processing subscription update: {e}",
                    exc_info=True,
                )

    async def _fetch_active_alerts(self) -> list[dict]:
        """Fetch all users with active beige alerts from database.

        Returns:
            List of user documents containing beige alert configurations.
        """
        db = db_mongo.get_db()
        return await db_mongo.listify(
            db.global_users.find({
                "beige_alerts": {"$exists": True, "$not": {"$size": 0}}
            })
        )

    async def _extract_nation_ids(self, alerts: list[dict]) -> list[str]:
        """Extract and deduplicate nation IDs from alert configurations.

        Args:
            alerts: List of user alert configurations.

        Returns:
            Sorted list of unique nation IDs.
        """
        nation_ids = []
        for user in alerts:
            nation_ids.extend(user.get("beige_alerts", []))
        return sorted(list(set(nation_ids)))

    async def _fetch_nation_data(self, nation_ids: list[str]) -> list[dict]:
        """Fetch current nation data from Politics & War API.

        Args:
            nation_ids: List of nation IDs to fetch.

        Returns:
            List of nation data dictionaries.
        """
        api_key = os.getenv("api_key")
        query = (
            f"{{nations(page:page_number first:500 "
            f"id:[{','.join(nation_ids)}])"
            f"{{paginatorInfo{{hasMorePages}} "
            f"data{{id vacation_mode_turns beige_turns}}}}}}"
        )
        return await api_client.paginate_call(query, "nations", api_key)

    async def _check_and_remind_alerts(
        self,
        alerts: list[dict],
        nations_data: list[dict],
    ) -> None:
        """Check alert conditions and send reminders as needed.

        Args:
            alerts: List of user alert configurations.
            nations_data: Current nation data from the API.
        """
        for user in alerts:
            times_to_send = user.get("beige_alerts_config", [15])
            times_to_send = sorted(times_to_send, reverse=True)

            for nation_id in user.get("beige_alerts", []):
                nation = next(
                    (n for n in nations_data if n["id"] == nation_id),
                    None,
                )
                if not nation:
                    continue

                beige_turns = int(nation.get("beige_turns", 0))
                vm_turns = int(nation.get("vacation_mode_turns", 0))

                await self._process_nation_alert(
                    user,
                    nation_id,
                    beige_turns,
                    vm_turns,
                    times_to_send,
                )

    async def _process_nation_alert(
        self,
        user: dict,
        nation_id: str,
        beige_turns: int,
        vm_turns: int,
        times_to_send: list[int],
    ) -> None:
        """Process a single nation alert and send reminder if conditions met.

        Args:
            user: User configuration document.
            nation_id: The nation ID to check.
            beige_turns: Remaining beige turns.
            vm_turns: Remaining vacation mode turns.
            times_to_send: List of reminder times in minutes.
        """
        try:
            exit_time = self._calculate_exit_time(beige_turns, vm_turns)

            for reminder_minutes in times_to_send:
                reminder_time = exit_time - timedelta(minutes=reminder_minutes)

                if self._is_reminder_time(reminder_time):
                    pull_after = times_to_send.index(reminder_minutes) == (
                        len(times_to_send) - 1
                    )
                    await self._send_reminder(
                        user,
                        nation_id,
                        beige_turns,
                        vm_turns,
                        pull_after,
                    )
                    break

            # Send late reminder if both timers expired while we weren't watching
            if (
                beige_turns == 0
                and vm_turns == 0
                and exit_time == datetime.utcnow()
            ):
                logger.warning(
                    f"Late reminder for {user['user']} about {nation_id}"
                )
                await self._send_reminder(
                    user, nation_id, beige_turns, vm_turns, pull_after=True
                )

        except Exception as e:
            logger.error(f"Error processing alert for {nation_id}: {e}")

    @staticmethod
    def _calculate_exit_time(beige_turns: int, vm_turns: int) -> datetime:
        """Calculate when a nation will exit beige/vacation mode.

        Args:
            beige_turns: Remaining beige turns.
            vm_turns: Remaining vacation mode turns.

        Returns:
            Datetime when the nation exits status.
        """
        if beige_turns >= 1:
            return common.get_datetime_of_turns(beige_turns)
        elif vm_turns >= 1:
            return common.get_datetime_of_turns(vm_turns)
        else:
            return common.get_datetime_of_turns(0)

    @staticmethod
    def _is_reminder_time(reminder_time: datetime) -> bool:
        """Check if current time is within reminder threshold.

        Args:
            reminder_time: The target reminder time.

        Returns:
            True if within threshold window.
        """
        now = datetime.utcnow()
        time_delta = abs((reminder_time - now).total_seconds())
        return time_delta < REMINDER_THRESHOLD

    async def _send_reminder(
        self,
        user: dict,
        nation_id: str,
        beige_turns: int,
        vm_turns: int,
        pull_after: bool = False,
    ) -> None:
        """Send a reminder DM to a user about a nation status change.

        Args:
            user: User configuration document.
            nation_id: The nation ID being reminded about.
            beige_turns: Current remaining beige turns.
            vm_turns: Current remaining vacation mode turns.
            pull_after: Whether to remove this alert after sending.
        """
        try:
            disc_user = await self.bot.fetch_user(user["user"])
            content = self._build_reminder_message(
                nation_id, beige_turns, vm_turns
            )
            await disc_user.send(content)
            logger.info(f"Reminder sent to {user['user']} about {nation_id}")

            if pull_after:
                db = db_mongo.get_db()
                await db.global_users.find_one_and_update(
                    {"user": user["user"]},
                    {"$pull": {"beige_alerts": nation_id}},
                )

        except (discord.NotFound, discord.Forbidden):
            logger.warning(f"Discord did not find/allow me to message {user['user']}, removing alert")
            if pull_after:
                db = db_mongo.get_db()
                await db.global_users.find_one_and_update(
                    {"user": user["user"]},
                    {"$pull": {"beige_alerts": nation_id}},
                )
        except Exception as e:
            logger.error(f"Error sending reminder: {e}")
            debug_channel = self.bot.get_channel(DEBUG_CHANNEL_ID)
            if debug_channel:
                await debug_channel.send(
                    f"**Failed to send reminder**\n"
                    f"User: {user['user']}\n"
                    f"Nation: {nation_id}\n"
                    f"Error: {e}"
                )

    @staticmethod
    def _build_reminder_message(
        nation_id: str, beige_turns: int, vm_turns: int
    ) -> str:
        """Build a formatted reminder message about nation status.

        Args:
            nation_id: The nation ID.
            beige_turns: Remaining beige turns.
            vm_turns: Remaining vacation mode turns.

        Returns:
            Formatted Discord message string.
        """
        nation_url = f"https://politicsandwar.com/nation/id={nation_id}"

        if beige_turns > 0:
            exit_time = common.get_datetime_of_turns(beige_turns)
            timestamp = round(exit_time.timestamp())
            return (
                f"Hey, {nation_url} is scheduled to leave beige at "
                f"<t:{timestamp}:f> (<t:{timestamp}:R>)"
            )
        elif vm_turns > 0:
            exit_time = common.get_datetime_of_turns(vm_turns)
            timestamp = round(exit_time.timestamp())
            return (
                f"Hey, {nation_url} is scheduled to leave vacation mode at "
                f"<t:{timestamp}:f> (<t:{timestamp}:R>)"
            )
        else:
            return (
                f"Hey, {nation_url} left beige while I wasn't looking!"
            )

    async def _send_preemptive_reminder(
        self, nation_id: str, alerts: list[dict]
    ) -> None:
        """Send a preemptive reminder when a nation exits status early.

        Args:
            nation_id: The nation ID that exited early.
            alerts: List of active alert configurations.
        """
        for user in alerts:
            if nation_id not in user.get("beige_alerts", []):
                continue

            try:
                disc_user = await self.bot.fetch_user(user["user"])
                nation_url = (
                    f"https://politicsandwar.com/nation/id={nation_id}"
                )
                content = (
                    f"Hey, {nation_url} has left beige prematurely!"
                )
                await disc_user.send(content)
                logger.info(
                    f"Preemptive reminder sent to {user['user']} "
                    f"about {nation_id}"
                )

                # Remove alert after sending
                db = db_mongo.get_db()
                await db.global_users.find_one_and_update(
                    {"user": user["user"]},
                    {"$pull": {"beige_alerts": nation_id}},
                )

            except Exception as e:
                logger.error(f"Error sending preemptive reminder: {e}")
                break



def setup(bot: commands.Bot) -> None:
    """Load the background tasks cog.

    Args:
        bot: The Discord bot instance.
    """
    bot.add_cog(General(bot))