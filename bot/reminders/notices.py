"""Tells users on their next slash command that a reminder DM didn't reach them."""
from __future__ import annotations

import logging
from typing import Any, Mapping

import discord

from bot.discord_utils.embeds import EMBED_COLOR, with_support_footer
from core.config import AUTOLYCUS_WEB_BASE_URL
from database import reminders as reminder_db
from database.mongo import get_db

logger = logging.getLogger(__name__)

# Users with a notice waiting; avoids a database read on every slash command.
_pending: set[int] = set()

_REASON_TEXT = {
    "no_mutual_server": "you don't share a server with Autolycus",
    "dms_closed": "your Discord privacy settings or a block stopped it",
    "unknown_user": "Discord couldn't find your account",
}


def mark_pending(user_id: int) -> None:
    """Remember that a user has a delivery notice waiting."""
    _pending.add(int(user_id))


async def load_pending() -> None:
    """Load users with waiting notices after a restart."""
    try:
        _pending.update(await reminder_db.users_with_pending_notice(get_db()))
    except Exception:  # noqa: BLE001
        logger.exception("Loading pending reminder notices failed")


def notice_embed(dm_delivery: Mapping[str, Any]) -> discord.Embed:
    """Explain why the reminder DM failed and where to fix it."""
    reason = _REASON_TEXT.get(str(dm_delivery.get("reason")), "Discord refused it")
    code = dm_delivery.get("code")
    code_text = f" (Discord error {code})" if code else ""
    embed = discord.Embed(
        title="A beige reminder couldn't reach you",
        description=(
            f"I tried to DM you a reminder, but {reason}{code_text}.\n\n"
            f"Open the [Reminders page]({AUTOLYCUS_WEB_BASE_URL}/reminders) for the steps to fix it "
            "and to send yourself a test DM."
        ),
        color=EMBED_COLOR,
    )
    embed.set_footer(text=with_support_footer())
    return embed


async def maybe_notify(ctx: discord.ApplicationContext) -> None:
    """Send the waiting notice, once, as an ephemeral follow-up to a finished command."""
    author = getattr(ctx, "author", None)
    if author is None or author.id not in _pending:
        return
    _pending.discard(author.id)
    try:
        doc = await reminder_db.take_dm_notice(get_db(), author.id)
        if not doc:
            return
        await ctx.followup.send(embed=notice_embed(doc.get("dm_delivery") or {}), ephemeral=True)
    except Exception:  # noqa: BLE001 - a notice must never break a command
        logger.debug("Could not send a reminder delivery notice to %s", author.id, exc_info=True)
