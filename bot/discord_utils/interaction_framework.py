from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

import discord

from bot.discord_utils import errors as err_util
from database import interaction_sessions

logger = logging.getLogger(__name__)

CUSTOM_ID_PREFIX = "ix"
DELIMITER = ":"


@dataclass
class ParsedCustomId:
    handler_key: str
    session_id: str
    action_id: str


def encode_custom_id(handler_key: str, session_id: str, action_id: str) -> str:
    return f"{CUSTOM_ID_PREFIX}{DELIMITER}{handler_key}{DELIMITER}{session_id}{DELIMITER}{action_id}"


def parse_custom_id(custom_id: str) -> Optional[ParsedCustomId]:
    if not custom_id:
        return None
    parts = custom_id.split(DELIMITER)
    if len(parts) != 4:
        return None
    if parts[0] != CUSTOM_ID_PREFIX:
        return None
    return ParsedCustomId(handler_key=parts[1], session_id=parts[2], action_id=parts[3])


SessionHandler = Callable[[discord.Interaction, dict, str], Awaitable[None]]


class InteractionRegistry:
    """Registry for generalized persisted interaction handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, SessionHandler] = {}

    def register(self, handler_key: str, handler: SessionHandler) -> None:
        self._handlers[handler_key] = handler

    def get(self, handler_key: str) -> Optional[SessionHandler]:
        return self._handlers.get(handler_key)

    async def dispatch(self, interaction: discord.Interaction) -> bool:
        data = getattr(interaction, "data", None)
        if not isinstance(data, dict):
            return False
        custom_id = data.get("custom_id")
        if not isinstance(custom_id, str):
            return False

        parsed = parse_custom_id(custom_id)
        if parsed is None:
            return False

        # Ack component interactions immediately to avoid Discord's 3s timeout
        # when session/db lookups are slow.
        if (
            interaction.type == discord.InteractionType.component
            and not interaction.response.is_done()
        ):
            try:
                await interaction.response.defer()
            except Exception:
                # If defer fails (expired/unknown interaction), stop here.
                return True

        session = await interaction_sessions.get_session(parsed.session_id)
        if session is None:
            await _safe_ephemeral(interaction, "This interaction session no longer exists. Please run the command again.")
            return True

        if interaction_sessions.is_expired(session):
            await interaction_sessions.mark_terminal(parsed.session_id, "expired")
            await _safe_ephemeral(interaction, "This interaction session expired. Please run the command again.")
            return True

        if int(session.get("user_id", 0)) != int(interaction.user.id):
            await _safe_ephemeral(interaction, "These buttons are reserved for someone else.")
            return True

        if session.get("status") not in interaction_sessions.ACTIVE_STATUSES:
            await _safe_ephemeral(interaction, "This interaction is already closed.")
            return True

        handler = self.get(parsed.handler_key)
        if handler is None:
            await _safe_ephemeral(interaction, "This interaction handler is unavailable. Please run the command again.")
            return True

        try:
            await handler(interaction, session, parsed.action_id)
        except Exception as exc:
            ref = await err_util.report_bot_exception(
                interaction.client,
                exc,
                logger,
                title="Interaction dispatch failed",
                details=(
                    f"handler=`{parsed.handler_key}` session=`{parsed.session_id}` "
                    f"action=`{parsed.action_id}` user=`{interaction.user.id}`"
                ),
            )
            await _safe_ephemeral(
                interaction,
                f"Something went wrong handling this interaction. Please try the command again. (Reference: {ref})",
            )
        return True


async def _safe_ephemeral(interaction: discord.Interaction, content: str) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content=content, ephemeral=True)
        else:
            await interaction.response.send_message(content=content, ephemeral=True)
    except Exception:
        logger.debug("Could not send ephemeral interaction framework response", exc_info=True)
