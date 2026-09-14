"""Discord DM delivery for reminders and test DMs.

Sends go straight to a stored DM channel ID (one request per message); the channel
is created, or re-created once if Discord says it no longer exists, only when needed.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Mapping, Optional, Sequence

import aiohttp
import discord

from bot.discord_utils.embeds import EMBED_COLOR, with_support_footer
from bot.discord_utils.interaction_framework import encode_stateless_custom_id
from core.config import AUTOLYCUS_WEB_BASE_URL
from logic import reminders as rules
from services.reminder_scheduler import DmSendResult

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 20.0
DM_TEST_ACK_HANDLER = "dm_test_ack"


def test_dm_ack_custom_id(user_id: int, test_id: str) -> str:
    """Button ID that carries everything the handler needs, so it survives restarts."""
    return encode_stateless_custom_id(DM_TEST_ACK_HANDLER, str(user_id), test_id)


class TestDmView(discord.ui.View):
    """The "Got it" button on a test DM."""

    def __init__(self, user_id: int, test_id: str, *, confirmed: bool = False) -> None:
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="Thanks, reminders will reach you here" if confirmed else "Got it",
                style=discord.ButtonStyle.success,
                custom_id=test_dm_ack_custom_id(user_id, test_id),
                disabled=confirmed,
            )
        )


def test_dm_embed() -> discord.Embed:
    """The test DM a user gets when checking that reminders reach them."""
    embed = discord.Embed(
        title="Checking that reminders reach you",
        description=(
            "This is a test from Autolycus. Your beige reminders will arrive in this chat.\n\n"
            "Press **Got it** so we know you can see these messages."
        ),
        color=EMBED_COLOR,
    )
    embed.add_field(
        name="Manage reminders",
        value=f"[Open the Reminders page]({AUTOLYCUS_WEB_BASE_URL}/reminders)",
        inline=False,
    )
    embed.set_footer(text=with_support_footer())
    return embed


class DiscordDmDelivery:
    """Implements the scheduler's Discord delivery with py-cord."""

    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot

    async def ensure_dm_channel(self, user_id: int) -> DmSendResult:
        """Open (or look up) the DM channel with a user."""
        try:
            channel = await asyncio.wait_for(
                self.bot.create_dm(discord.Object(id=user_id)), _REQUEST_TIMEOUT_SECONDS
            )
        except discord.HTTPException as exc:
            outcome, reason = rules.classify_discord_error(exc.status, exc.code)
            return DmSendResult(outcome, code=exc.code or None, reason=reason, status=exc.status)
        except (asyncio.TimeoutError, aiohttp.ClientError, OSError):
            return DmSendResult(rules.DeliveryOutcome.RETRY)
        return DmSendResult(rules.DeliveryOutcome.DELIVERED, channel_id=channel.id)

    async def send_reminder(
        self,
        user_id: int,
        channel_id: Optional[int],
        embeds: Sequence[Mapping[str, Any]],
        nonce: str,
    ) -> DmSendResult:
        """Send up to 10 reminder embeds in one message; the nonce stops duplicates."""
        return await self._send(
            user_id,
            channel_id,
            embeds=[discord.Embed.from_dict(dict(embed)) for embed in embeds],
            nonce=nonce,
            enforce_nonce=True,
        )

    async def send_test_dm(self, user_id: int, channel_id: Optional[int], test_id: str) -> DmSendResult:
        """Send a test DM with a "Got it" button."""
        view = TestDmView(user_id, test_id)
        try:
            return await self._send(user_id, channel_id, embed=test_dm_embed(), view=view)
        finally:
            # Clicks go through the stateless interaction handler, not this view object.
            view.stop()

    async def _send(self, user_id: int, channel_id: Optional[int], **kwargs: Any) -> DmSendResult:
        recreated = False
        while True:
            if channel_id is None:
                opened = await self.ensure_dm_channel(user_id)
                if opened.channel_id is None:
                    return opened
                channel_id = opened.channel_id
            target = self.bot.get_partial_messageable(channel_id, type=discord.ChannelType.private)
            try:
                message = await asyncio.wait_for(target.send(**kwargs), _REQUEST_TIMEOUT_SECONDS)
            except discord.HTTPException as exc:
                outcome, reason = rules.classify_discord_error(exc.status, exc.code)
                if outcome is rules.DeliveryOutcome.CHANNEL_GONE and not recreated:
                    recreated = True
                    channel_id = None
                    continue
                return DmSendResult(
                    outcome, code=exc.code or None, reason=reason, status=exc.status, channel_id=channel_id
                )
            except (asyncio.TimeoutError, aiohttp.ClientError, OSError):
                return DmSendResult(rules.DeliveryOutcome.RETRY, channel_id=channel_id)
            return DmSendResult(
                rules.DeliveryOutcome.DELIVERED,
                channel_id=channel_id,
                message_id=getattr(message, "id", None),
            )
