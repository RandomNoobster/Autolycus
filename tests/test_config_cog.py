"""Tests for the ``/config view_current_settings`` slash command callback.

``ApplicationContext.edit`` forwards to ``Interaction.edit_original_response``, whose
parameters are all keyword-only, so a positional ``ctx.edit("...")`` raises ``TypeError``
and the user sees the generic error embed instead of the intended reply.
"""

import asyncio
import inspect
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.cogs import config as config_cog

GUILD_ID = 1234


def _run_view_current_settings(monkeypatch: pytest.MonkeyPatch, stored_config):
    find_one = AsyncMock(return_value=stored_config)
    fake_db = SimpleNamespace(guild_configs=SimpleNamespace(find_one=find_one))
    monkeypatch.setattr(config_cog.db_mongo, "get_db", lambda: fake_db)

    cog = config_cog.Config(bot=MagicMock())
    handle_exception = AsyncMock()
    monkeypatch.setattr(cog, "_handle_command_exception", handle_exception)

    ctx = MagicMock()
    ctx.guild.id = GUILD_ID
    ctx.defer = AsyncMock()
    ctx.edit = AsyncMock()

    callback = config_cog.Config.config_view_current_settings.callback
    asyncio.run(callback(cog, ctx))

    find_one.assert_awaited_once_with({"guild_id": GUILD_ID})
    handle_exception.assert_not_awaited()
    ctx.edit.assert_awaited_once()
    call = ctx.edit.await_args
    # Must be callable against py-cord's real (keyword-only) signature.
    inspect.signature(discord.Interaction.edit_original_response).bind(
        None, *call.args, **call.kwargs
    )
    assert call.args == ()
    return call.kwargs["content"]


def test_view_current_settings_without_config_replies_with_message(monkeypatch):
    content = _run_view_current_settings(monkeypatch, stored_config=None)

    assert content == "No configurable commands have been configured in this server!"


def test_view_current_settings_lists_stored_config(monkeypatch):
    content = _run_view_current_settings(
        monkeypatch, stored_config={"guild_id": GUILD_ID, "dnr": "1,2"}
    )

    assert content.startswith("The configuration for this guild is as follows:")
    assert f"guild_id: {GUILD_ID}\n" in content
    assert "dnr: 1,2\n" in content
