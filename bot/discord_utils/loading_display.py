from __future__ import annotations

import asyncio
import logging
import random
from pathlib import Path
from typing import Any

import discord

logger = logging.getLogger(__name__)

_UNSET = object()

# One scan per attachments directory per process (avoids synchronous glob on every command).
_gif_paths_cache: dict[str, list[Path]] = {}


def _scan_gif_paths(attachments_dir: Path) -> list[Path]:
    try:
        return [p for p in attachments_dir.glob("*.gif") if p.is_file()]
    except Exception:
        logger.debug("Failed scanning gifs in %s", attachments_dir, exc_info=True)
        return []


class LoadingDisplay:
    """Manage loading text + random GIF on a single interaction response message."""

    def __init__(
        self,
        target: discord.ApplicationContext | discord.Interaction,
        *,
        show_after: float = 0.0,
        attachments_dir: Path | None = None,
    ) -> None:
        self._target = target
        self._show_after = max(0.0, float(show_after))
        self._attachments_dir = attachments_dir or Path(__file__).resolve().parents[1] / "attachments"

        self._gif_paths: list[Path] = []
        self._delay_task: asyncio.Task[None] | None = None
        self._visible = False
        self._has_gif = False
        self._closed = False
        self._pending_message = "Working on it..."

    async def __aenter__(self) -> "LoadingDisplay":
        await self.start(self._pending_message)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.clear()

    async def start(self, message: str) -> None:
        self._pending_message = message
        self._ensure_gif_paths()
        if self._show_after > 0:
            self._delay_task = asyncio.create_task(self._delayed_show())
            return
        await self._show_now(message, include_gif=True)

    async def update(self, message: str, *, new_gif: bool = False, force_show: bool = False) -> None:
        self._pending_message = message
        if self._closed:
            return

        if not self._visible:
            # Still waiting for show_after; keep the freshest message.
            if force_show:
                await self._show_now(message, include_gif=True)
            return
        if new_gif:
            await self._show_now(message, include_gif=True)
        else:
            await self._edit_loading_text_only(message)

    async def clear(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._cancel_delay_task()

        # Strip GIF if we ever showed the message or attached a GIF (handles edge cases
        # where _visible desynced but an attachment remains).
        if not self._visible and not self._has_gif:
            return
        try:
            kwargs: dict[str, Any] = {"attachments": []}
            await self._edit_response(**kwargs)
        except Exception:
            logger.debug("Failed to clear loading display attachment", exc_info=True)
        finally:
            self._has_gif = False

    async def _delayed_show(self) -> None:
        try:
            await asyncio.sleep(self._show_after)
            if self._closed:
                return
            await self._show_now(self._pending_message, include_gif=True)
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

    def _ensure_gif_paths(self) -> None:
        if self._gif_paths:
            return
        key = str(self._attachments_dir.resolve())
        if key not in _gif_paths_cache:
            _gif_paths_cache[key] = _scan_gif_paths(self._attachments_dir)
        self._gif_paths = list(_gif_paths_cache[key])

    def _pick_gif(self) -> Path | None:
        if not self._gif_paths:
            return None
        return random.choice(self._gif_paths)

    async def _show_now(self, message: str, *, include_gif: bool) -> None:
        await self._cancel_delay_task()
        kwargs: dict[str, Any] = {"content": message, "embed": None, "view": None}

        gif_path = self._pick_gif() if include_gif else None
        if gif_path is not None:
            try:
                kwargs["files"] = [discord.File(str(gif_path), filename=gif_path.name)]
                kwargs["attachments"] = []
                self._has_gif = True
            except Exception:
                logger.debug("Failed preparing loading gif file %s", gif_path, exc_info=True)
        elif self._has_gif:
            kwargs["attachments"] = []
            self._has_gif = False

        try:
            await self._edit_response(**kwargs)
            self._visible = True
        except Exception:
            logger.debug("Failed to update loading display message", exc_info=True)

    async def _edit_loading_text_only(self, message: str) -> None:
        """Update status text without removing an existing GIF attachment."""
        kwargs: dict[str, Any] = {"content": message, "embed": None, "view": None}
        try:
            await self._edit_response(**kwargs)
            self._visible = True
        except Exception:
            logger.debug("Failed to update loading display text", exc_info=True)

    async def _edit_response(self, **kwargs: Any) -> None:
        cleaned = {k: v for k, v in kwargs.items() if v is not _UNSET}
        if isinstance(self._target, discord.ApplicationContext):
            await self._target.edit(**cleaned)
            return

        if self._target.response.is_done():
            await self._target.edit_original_response(**cleaned)
        else:
            await self._target.response.send_message(**cleaned)
