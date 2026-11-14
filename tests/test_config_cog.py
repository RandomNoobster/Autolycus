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


def _run_dnr(monkeypatch, alliance_ids):
    update = AsyncMock()
    fake_db = SimpleNamespace(guild_configs=SimpleNamespace(find_one_and_update=update))
    monkeypatch.setattr(config_cog.db_mongo, "get_db", lambda: fake_db)
    cog = config_cog.Config(bot=MagicMock())
    monkeypatch.setattr(cog, "_handle_command_exception", AsyncMock())
    ctx = MagicMock()
    ctx.guild.id = GUILD_ID
    ctx.respond = AsyncMock()
    asyncio.run(config_cog.Config.config_dnr.callback(cog, ctx, alliance_ids))
    return update, ctx.respond.await_args


def test_dnr_with_names_instead_of_ids_keeps_the_list(monkeypatch):
    update, reply = _run_dnr(monkeypatch, "Rose, TKR")
    update.assert_not_awaited()
    assert "not changed" in reply.args[0]


def test_dnr_ids_and_clearing(monkeypatch):
    update, reply = _run_dnr(monkeypatch, "770, 1234")
    assert update.await_args.args[1] == {"$set": {"dnr_alliance_ids": ["770", "1234"]}}
    update, reply = _run_dnr(monkeypatch, "")
    assert update.await_args.args[1] == {"$set": {"dnr_alliance_ids": []}}
    assert reply.args[0] == "DNR set to `None`"


def test_config_has_a_targets_command_for_nuketargets():
    names = {cmd.name for cmd in config_cog.Config.config_group.subcommands}
    assert {"dnr", "targets", "reminders", "view_current_settings"} <= names
