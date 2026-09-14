"""Handles the "Got it" button on test DMs, including after bot restarts."""
from __future__ import annotations

import logging

import discord

from bot.reminders.discord_delivery import DM_TEST_ACK_HANDLER, TestDmView
from database import reminders as reminder_db
from database.mongo import get_db
from logic import reminders as rules

logger = logging.getLogger(__name__)

__all__ = ["DM_TEST_ACK_HANDLER", "handle_test_dm_ack"]


async def _ephemeral(interaction: discord.Interaction, content: str) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=True)
        else:
            await interaction.response.send_message(content, ephemeral=True)
    except discord.HTTPException:
        logger.debug("Could not answer a test DM button click", exc_info=True)


async def handle_test_dm_ack(interaction: discord.Interaction, parts: list[str]) -> None:
    """Record that the user saw their test DM.

    Args:
        interaction: The button click.
        parts: ``[user_id, test_id]`` from the button's custom ID.
    """
    if len(parts) != 2 or not parts[0].isdigit():
        await _ephemeral(interaction, "This button is no longer valid.")
        return
    user_id = int(parts[0])
    test_id = parts[1]
    if interaction.user is None or interaction.user.id != user_id:
        await _ephemeral(interaction, "This button belongs to someone else.")
        return
    try:
        await interaction.response.edit_message(view=TestDmView(user_id, test_id, confirmed=True))
    except discord.HTTPException:
        logger.debug("Could not update the test DM after a click", exc_info=True)
    await reminder_db.confirm_test_dm(get_db(), test_id, user_id, rules.utcnow())
