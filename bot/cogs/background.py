"""Background tasks for monitoring nation alerts and status updates.

This module manages the Discord bot's background scanning for nation beige alerts
and vacation mode transitions. It uses websocket subscriptions for real-time updates
and polls the Politics & War API periodically.
"""

import asyncio
import logging
import os
import traceback
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv

from bot.discord_utils import errors as err_util
from database import mongo as db_mongo
from database.sqlite_cache import get_nation_by_id, get_nations_db_path
from bot.discord_utils.embeds import EMBED_COLOR
from logic import api_client, common

load_dotenv()

logger = logging.getLogger(__name__)

# Configuration
API_KEY = os.getenv("API_KEY")
DEBUG_CHANNEL_ID = int(os.getenv("DEBUG_CHANNEL"))
SCAN_INTERVAL = 100  # seconds
REMINDER_THRESHOLD = 50  # seconds
ENABLE_PNW_WS = os.getenv("ENABLE_PNW_WS", "false").lower() in (
    "1",
    "true",
    "yes",
    "on",
)


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

        # Keep websocket optional. Some pnwkit/runtime combinations emit malformed
        # websocket payloads and spam logs; polling remains reliable.
        if ENABLE_PNW_WS:
            try:
                nation_updates = await self.bot.pnw_kit.subscribe("nation", "update")
                asyncio.ensure_future(
                    self._handle_subscriptions(nation_updates, unique_ids, alerts)
                )
                logger.info("PNW websocket subscription enabled for nation updates")
            except Exception as e:
                logger.warning(
                    "Failed to start PNW websocket subscription; using polling only: %s",
                    e,
                )
        else:
            logger.info("PNW websocket subscription disabled; using polling only")

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
                    embed = err_util.error_embed(
                        "Background scanner failure",
                        "An exception occurred while scanning beige alerts.",
                        reference=None,
                        color=err_util.ERROR_EMBED_COLOR,
                        contact_footer=None,
                    )
                    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
                    await err_util.send_embed_with_trace_thread(
                        debug_channel,
                        embed=embed,
                        traceback_text=traceback.format_exc(),
                        log=logger,
                        thread_name=f"trace-scanning-beige-alerts-{timestamp}",
                    )

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
        nation_ids: list[str] = []
        for user in alerts:
            nation_ids.extend([str(nid) for nid in user.get("beige_alerts", [])])
        return sorted(list(set(nation_ids)))

    async def _fetch_nation_data(self, nation_ids: list[str]) -> list[dict]:
        """Fetch current nation data from Politics & War API.

        Args:
            nation_ids: List of nation IDs to fetch.

        Returns:
            List of nation data dictionaries.
        """
        api_key = os.getenv("API_KEY")
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
                nation_id_str = str(nation_id)
                nation = next(
                    (n for n in nations_data if str(n.get("id")) == nation_id_str),
                    None,
                )
                if not nation:
                    continue

                beige_turns = int(nation.get("beige_turns", 0))
                vm_turns = int(nation.get("vacation_mode_turns", 0))

                await self._process_nation_alert(
                    user,
                    nation_id_str,
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
            nation_payload = await asyncio.to_thread(
                get_nation_by_id, get_nations_db_path(), nation_id
            )
            nation = nation_payload.get("nation")
            data_timestamp = self._extract_data_timestamp(
                nation,
                nation_payload.get("last_fetched"),
            )
            embed = self._build_reminder_embed(
                nation=nation,
                nation_id=nation_id,
                beige_turns=beige_turns,
                vm_turns=vm_turns,
                data_timestamp=data_timestamp,
                preemptive=False,
            )
            await disc_user.send(embed=embed)
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
            logger.error(f"Error sending reminder: {e}", exc_info=True)
            debug_channel = self.bot.get_channel(DEBUG_CHANNEL_ID)
            if debug_channel:
                embed = err_util.error_embed(
                    "Failed to send reminder",
                    (
                        f"Could not DM user `{user['user']}` "
                        f"for nation `{nation_id}`."
                    ),
                    reference=None,
                    color=err_util.ERROR_EMBED_COLOR,
                    contact_footer=None,
                )
                timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
                await err_util.send_embed_with_trace_thread(
                    debug_channel,
                    embed=embed,
                    traceback_text=traceback.format_exc(),
                    log=logger,
                    thread_name=f"trace-reminder-send-{timestamp}",
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

    @staticmethod
    def _extract_data_timestamp(
        nation: Optional[dict],
        last_fetched: Optional[int | float],
    ) -> Optional[int]:
        """Extract a Unix timestamp for when the cached data was updated.

        Args:
            nation: Cached nation data, if available.
            last_fetched: Global cache timestamp from metadata.

        Returns:
            Unix timestamp in seconds, or None if unavailable.
        """
        if nation:
            raw = nation.get("_created_at")
            try:
                if raw is not None:
                    return int(raw)
            except (TypeError, ValueError):
                pass
        try:
            if last_fetched is not None:
                return int(last_fetched)
        except (TypeError, ValueError):
            pass
        return None

    def _build_reminder_embed(
        self,
        nation: Optional[dict],
        nation_id: str,
        beige_turns: int,
        vm_turns: int,
        data_timestamp: Optional[int],
        preemptive: bool,
    ) -> discord.Embed:
        """Build a rich embed for beige/vacation reminders.

        Args:
            nation: Cached nation data if available.
            nation_id: The nation ID.
            beige_turns: Remaining beige turns.
            vm_turns: Remaining vacation mode turns.
            data_timestamp: Unix timestamp of cached data update.
            preemptive: True if the nation exited early.

        Returns:
            Discord embed for the reminder.
        """
        nation_url = f"https://politicsandwar.com/nation/id={nation_id}"
        nation_name = nation.get("nation_name") if nation else f"Nation {nation_id}"
        leader_name = nation.get("leader_name") if nation else "Unknown"
        alliance_name = "None"
        if nation and isinstance(nation.get("alliance"), dict):
            alliance_name = nation.get("alliance", {}).get("name") or "None"

        embed = discord.Embed(
            title=nation_name,
            url=nation_url,
            color=EMBED_COLOR,
        )
        embed.description = (
            f"Leader: **{leader_name}**\n"
            f"Alliance: **{alliance_name}**\n"
            f"[Open nation profile]({nation_url})"
        )

        flag_url = nation.get("flag") if nation else None
        if flag_url:
            embed.set_thumbnail(url=str(flag_url))

        status_lines: list[str] = []
        if preemptive:
            status_lines.append("Exited beige/vacation early")
        if beige_turns > 0:
            exit_time = common.get_datetime_of_turns(beige_turns)
            timestamp = round(exit_time.timestamp())
            status_lines.append(
                f"Beige turns: **{beige_turns}**"
            )
            status_lines.append(
                f"Exits beige: <t:{timestamp}:f> (<t:{timestamp}:R>)"
            )
        elif vm_turns > 0:
            exit_time = common.get_datetime_of_turns(vm_turns)
            timestamp = round(exit_time.timestamp())
            status_lines.append(
                f"VM turns: **{vm_turns}**"
            )
            status_lines.append(
                f"Exits VM: <t:{timestamp}:f> (<t:{timestamp}:R>)"
            )
        else:
            status_lines.append("No active beige/VM turns")

        embed.add_field(name="Status", value="\n".join(status_lines), inline=False)

        if nation:
            soldiers = nation.get("soldiers", 0)
            tanks = nation.get("tanks", 0)
            aircraft = nation.get("aircraft", 0)
            ships = nation.get("ships", 0)
            missiles = nation.get("missiles", 0)
            nukes = nation.get("nukes", 0)
            military = (
                f"Soldiers: **{soldiers:,}**\n"
                f"Tanks: **{tanks:,}**\n"
                f"Aircraft: **{aircraft:,}**\n"
                f"Ships: **{ships:,}**\n"
                f"Missiles: **{missiles}**\n"
                f"Nukes: **{nukes}**"
            )
            embed.add_field(name="Military", value=military, inline=True)

            score = nation.get("score")
            cities = nation.get("num_cities")
            color = nation.get("color")
            info_parts = []
            if score is not None:
                info_parts.append(f"Score: **{score}**")
            if cities is not None:
                info_parts.append(f"Cities: **{cities}**")
            if color:
                info_parts.append(f"Color: **{str(color).capitalize()}**")
            if info_parts:
                embed.add_field(name="Nation Info", value="\n".join(info_parts), inline=True)

        if data_timestamp:
            embed.add_field(
                name="Data Updated",
                value=f"<t:{data_timestamp}:R> (<t:{data_timestamp}:f>)",
                inline=False,
            )

        embed.set_footer(text="Autolycus beige reminder")
        return embed

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
                nation_payload = await asyncio.to_thread(
                    get_nation_by_id, get_nations_db_path(), nation_id
                )
                nation = nation_payload.get("nation")
                data_timestamp = self._extract_data_timestamp(
                    nation,
                    nation_payload.get("last_fetched"),
                )
                embed = self._build_reminder_embed(
                    nation=nation,
                    nation_id=nation_id,
                    beige_turns=0,
                    vm_turns=0,
                    data_timestamp=data_timestamp,
                    preemptive=True,
                )
                await disc_user.send(embed=embed)
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
                logger.error(f"Error sending preemptive reminder: {e}", exc_info=True)
                debug_channel = self.bot.get_channel(DEBUG_CHANNEL_ID)
                if debug_channel:
                    embed = err_util.error_embed(
                        "Failed to send preemptive reminder",
                        (
                            f"Could not DM user `{user['user']}` "
                            f"for nation `{nation_id}`."
                        ),
                        reference=None,
                        color=err_util.ERROR_EMBED_COLOR,
                        contact_footer=None,
                    )
                    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
                    await err_util.send_embed_with_trace_thread(
                        debug_channel,
                        embed=embed,
                        traceback_text=traceback.format_exc(),
                        log=logger,
                        thread_name=f"trace-preemptive-reminder-{timestamp}",
                    )
                break



def setup(bot: commands.Bot) -> None:
    """Load the background tasks cog.

    Args:
        bot: The Discord bot instance.
    """
    bot.add_cog(General(bot))