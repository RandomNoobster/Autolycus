"""Loading text and a random GIF on a command's reply while it works.

The GIFs are served by the website (frontend/public/loading/) and shown as an
embed image. Discord fetches and caches them itself, so a command no longer
uploads a file of several megabytes before it starts working.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Optional
from urllib.parse import urlparse

import discord

from bot.discord_utils.embeds import EMBED_COLOR
from core.config import AUTOLYCUS_WEB_BASE_URL

logger = logging.getLogger(__name__)

# Files in frontend/public/loading/.
LOADING_GIFS = (
    "bob-dylan.gif",
    "cat-sitting.gif",
    "travolta.gif",
    "waiting.gif",
    "waiting2.gif",
    "waiting3.gif",
)
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def loading_gif_urls(base_url: str = AUTOLYCUS_WEB_BASE_URL) -> list[str]:
    """Public URLs of the loading GIFs; none when Discord can't reach the site (local dev)."""
    host = (urlparse(base_url).hostname or "").lower()
    if not host or host in _LOCAL_HOSTS or host.endswith(".localhost"):
        return []
    return [f"{base_url.rstrip('/')}/loading/{name}" for name in LOADING_GIFS]


class LoadingDisplay:
    """Manage loading text + random GIF on a single interaction response message.

    Final edits that only set ``content`` must pass ``embed=None`` (or call
    :meth:`clear` first), or the loading GIF stays under the result.
    """

    def __init__(
        self,
        target: discord.ApplicationContext | discord.Interaction,
        *,
        show_after: float = 0.0,
        gif_urls: Optional[list[str]] = None,
    ) -> None:
        self._target = target
        self._show_after = max(0.0, float(show_after))
        self._gif_urls = loading_gif_urls() if gif_urls is None else list(gif_urls)
        self._embed: Optional[discord.Embed] = None
        self._delay_task: asyncio.Task[None] | None = None
        self._visible = False
        self._closed = False
        self._pending_message = "Working on it..."

    async def __aenter__(self) -> "LoadingDisplay":
        await self.start(self._pending_message)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.clear()

    async def start(self, message: str) -> None:
        self._pending_message = message
        if self._show_after > 0:
            self._delay_task = asyncio.create_task(self._delayed_show())
            return
        await self._show_now(message, new_gif=True)

    async def update(self, message: str, *, new_gif: bool = False, force_show: bool = False) -> None:
        self._pending_message = message
        if self._closed:
            return

        if not self._visible:
            # Still waiting for show_after; keep the freshest message.
            if force_show:
                await self._show_now(message, new_gif=True)
            return
        await self._show_now(message, new_gif=new_gif)

    async def clear(self) -> None:
        """Take the loading GIF off the message (the text is left for the caller)."""
        if self._closed:
            return
        self._closed = True
        await self._cancel_delay_task()
        if not self._visible:
            return
        try:
            # attachments=[] also strips GIFs older bot versions uploaded.
            await self._edit_response(embed=None, attachments=[])
        except Exception:
            logger.debug("Failed to clear loading display", exc_info=True)
        finally:
            self._embed = None

    async def _delayed_show(self) -> None:
        try:
            await asyncio.sleep(self._show_after)
            if self._closed:
                return
            await self._show_now(self._pending_message, new_gif=True)
        except asyncio.CancelledError:
            return

    async def _cancel_delay_task(self) -> None:
        if self._delay_task is None:
            return
        self._delay_task.cancel()
        try:
            await self._delay_task
        except asyncio.CancelledError:
            pass
        self._delay_task = None

    def _gif_embed(self) -> Optional[discord.Embed]:
        if not self._gif_urls:
            return None
        return discord.Embed(color=EMBED_COLOR).set_image(url=random.choice(self._gif_urls))

    async def _show_now(self, message: str, *, new_gif: bool) -> None:
        if asyncio.current_task() is not self._delay_task:
            await self._cancel_delay_task()
        if new_gif or self._embed is None:
            self._embed = self._gif_embed()
        try:
            await self._edit_response(content=message, embed=self._embed, view=None, attachments=[])
            self._visible = True
        except Exception:
            logger.debug("Failed to update loading display message", exc_info=True)

    async def _edit_response(self, **kwargs: Any) -> None:
        if isinstance(self._target, discord.ApplicationContext):
            await self._target.edit(**kwargs)
            return

        if self._target.response.is_done():
            await self._target.edit_original_response(**kwargs)
        else:
            # A first response has nothing to strip yet; send_message takes no attachments.
            first = {k: kwargs[k] for k in ("content", "embed") if kwargs.get(k) is not None}
            await self._target.response.send_message(**first)
