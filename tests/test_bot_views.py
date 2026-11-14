"""Bot interaction plumbing: routing, prompts, modals, pagers and error text."""

import asyncio
import os
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.discord_utils import errors, interaction_framework, views
from bot.discord_utils.interaction_framework import InteractionRegistry, encode_custom_id
from database import interaction_sessions


def _ctx(user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(author=SimpleNamespace(id=user_id), guild=None, channel_id=5)


def _component(custom_id: str, user_id: int = 1) -> MagicMock:
    interaction = MagicMock()
    interaction.type = discord.InteractionType.component
    interaction.data = {"custom_id": custom_id}
    interaction.user = SimpleNamespace(id=user_id)
    done = {"value": False}

    async def defer(*args, **kwargs):
        done["value"] = True

    async def send_modal(modal):
        done["value"] = True

    interaction.response.is_done = lambda: done["value"]
    interaction.response.defer = AsyncMock(side_effect=defer)
    interaction.response.send_modal = AsyncMock(side_effect=send_modal)
    interaction.response.send_message = AsyncMock()
    interaction.edit_original_response = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _registry() -> InteractionRegistry:
    registry = InteractionRegistry()
    views.register_interaction_handlers(registry)
    return registry


def test_autocomplete_and_slash_commands_reach_pycord():
    processed = []

    async def process(interaction):
        processed.append(interaction.type)

    bot = SimpleNamespace(interaction_registry=InteractionRegistry(), process_application_commands=process)
    for kind in (discord.InteractionType.auto_complete, discord.InteractionType.application_command):
        interaction = SimpleNamespace(type=kind, data={"name": "help"})
        asyncio.run(interaction_framework.route_interaction(bot, interaction))
    assert processed == [discord.InteractionType.auto_complete, discord.InteractionType.application_command]


def test_routed_views_are_not_kept_by_pycord():
    async def build():
        return views.PersistentChoiceView("sid", [{"action": "a", "label": "A", "style": 1}])

    view = asyncio.run(build())
    # py-cord only stores unfinished views when a message is sent or edited.
    assert view.is_finished()
    assert view.children[0].custom_id == encode_custom_id("choice", "sid", "a")


def test_a_click_wakes_the_waiting_prompt_without_polling():
    async def scenario():
        _view, session_id = await views.create_persistent_choice_prompt(
            command="t", ctx=_ctx(), choices=[("go", "Go", discord.ButtonStyle.primary)]
        )
        waiter = asyncio.create_task(views.wait_for_persistent_choice_result(session_id))
        await asyncio.sleep(0)
        clicked_at = time.monotonic()
        await _registry().dispatch(_component(encode_custom_id("choice", session_id, "go")))
        result = await waiter
        return result, time.monotonic() - clicked_at

    result, waited = asyncio.run(scenario())
    assert result == "go"
    assert waited < 0.5  # woken by the click, not the 1 s fallback re-read


def test_prompts_close_before_the_commands_token_expires():
    assert views.PROMPT_TTL_SECONDS < 15 * 60

    async def scenario():
        _view, session_id = await views.create_persistent_yesno_prompt(command="t", ctx=_ctx())
        result = await views.wait_for_persistent_yesno_result(session_id, timeout_seconds=0.05)
        return result, await interaction_sessions.get_session(session_id)

    result, session = asyncio.run(scenario())
    assert result is None
    assert session["status"] == "expired"  # later clicks say so instead of doing nothing


def test_add_more_opens_its_modal_from_the_click():
    """The modal is the click's first response; the registry must not defer it."""

    async def scenario():
        _view, session_id = await views.create_persistent_choice_prompt(
            command="config_reminders",
            ctx=_ctx(),
            choices=[("add", "Add more", discord.ButtonStyle.blurple)],
            modals={"add": {"title": "Reminders", "label": "Minutes", "placeholder": "15"}},
        )
        waiter = asyncio.create_task(views.wait_for_persistent_choice(session_id))
        interaction = _component(encode_custom_id("choice_modal", session_id, "add"))
        dispatch = asyncio.create_task(_registry().dispatch(interaction))
        for _ in range(50):
            await asyncio.sleep(0.01)
            if interaction.response.send_modal.await_count:
                break
        interaction.response.defer.assert_not_awaited()
        modal = interaction.response.send_modal.await_args.args[0]
        modal.children[0].value = "45"
        submit = _component("modal")
        await modal.callback(submit)
        await dispatch
        return await waiter

    action, state = asyncio.run(scenario())
    assert action == "add"
    assert state["text"] == "45"


def test_a_dismissed_modal_does_not_count_as_submitted():
    async def scenario():
        modal = views.SimpleModal(title="T", label="L", placeholder="P", timeout=0.01)
        modal._start_listening_from_store(MagicMock())
        await modal.wait()
        return modal.submitted

    assert asyncio.run(scenario()) is False


def test_raids_pager_pages_expire_with_their_session(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(views.time, "monotonic", lambda: clock["now"])
    views._set_raids_pager_cache("old", embeds=[{}], target_ids=["1"], beige_turns=[0], ttl_seconds=60)
    assert views._get_raids_pager_cache("old")
    clock["now"] += 61
    assert views._get_raids_pager_cache("old") == {}


def test_switch_timeout_keeps_the_results_on_screen():
    async def scenario():
        ctx = SimpleNamespace(author=SimpleNamespace(id=1), edit=AsyncMock())
        switch = views.Switch(ctx=ctx, embeds=[discord.Embed(title="a"), discord.Embed(title="b")], max_page=2, timeout=3600)
        await switch.on_timeout()
        return switch, ctx.edit.await_args

    switch, call = asyncio.run(scenario())
    assert switch.timeout <= views.PROMPT_TTL_SECONDS
    assert set(call.kwargs) == {"view"}  # no "Timed out" embed over the results
    assert all(child.disabled for child in switch.children)


def test_long_traceback_lines_are_split_for_discord():
    chunks = errors.chunk_text_for_discord("short\n" + "x" * 5000 + "\nend", max_len=1700)
    assert all(len(chunk) <= 1700 for chunk in chunks)
    assert "".join(chunks).replace("\n", "") == "short" + "x" * 5000 + "end"


def test_discord_errors_raised_in_commands_are_not_shown_as_pnw_outages():
    response = SimpleNamespace(status=500, reason="Internal Server Error")
    wrapped = discord.ApplicationCommandInvokeError(discord.HTTPException(response, "boom"))
    root = errors.unwrap_command_error(wrapped)
    assert isinstance(root, discord.HTTPException)


@pytest.mark.parametrize("handler", ["yesno", "choice", "tabs", "raids_pager"])
def test_session_handlers_are_deferred_and_modal_choices_are_not(handler):
    registry = _registry()
    assert handler in registry._handlers and handler not in registry._no_auto_defer
    assert "choice_modal" in registry._no_auto_defer


def test_discord_500s_are_not_pnw_outages():
    response = SimpleNamespace(status=500, reason="Internal Server Error")
    assert not errors.is_pnw_server_error(discord.HTTPException(response, "boom"))
    assert errors.is_pnw_server_error(Exception("PnW server error: 502"))


def test_command_errors_reply_before_posting_the_trace(monkeypatch):
    order = []

    async def reply(ctx, embed, **kwargs):
        order.append(("reply", kwargs["reference"]))

    async def report(bot, ctx, error, log, *, reference=None, command_name=None):
        order.append(("report", reference))
        return reference

    monkeypatch.setattr(errors, "safe_reply_error", reply)
    monkeypatch.setattr(errors, "report_handled_exception", report)
    asyncio.run(errors.handle_command_exception(None, None, ValueError("x"), MagicMock(), command_name="t"))
    assert [step for step, _ in order] == ["reply", "report"]
    assert order[0][1] == order[1][1]


def test_loading_gifs_are_linked_from_the_website_not_uploaded():
    from bot.discord_utils.loading_display import LoadingDisplay, loading_gif_urls

    urls = loading_gif_urls("https://autolycus.example/")
    assert urls and all(url.startswith("https://autolycus.example/loading/") for url in urls)
    # Discord can't fetch from a developer's machine.
    assert loading_gif_urls("http://localhost:5173") == []

    async def scenario():
        ctx = MagicMock(spec=discord.ApplicationContext)
        ctx.edit = AsyncMock()
        loading = LoadingDisplay(ctx, gif_urls=urls)
        await loading.start("Working...")
        shown = ctx.edit.await_args.kwargs
        await loading.update("Still working...")
        updated = ctx.edit.await_args.kwargs
        await loading.clear()
        return shown, updated, ctx.edit.await_args.kwargs

    shown, updated, cleared = asyncio.run(scenario())
    assert "files" not in shown
    assert shown["embed"].image.url in urls
    assert updated["embed"] is shown["embed"]  # text updates keep the same GIF
    assert cleared["embed"] is None


def test_frontend_serves_every_loading_gif():
    from bot.discord_utils.loading_display import LOADING_GIFS

    root = os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "loading")
    assert sorted(os.listdir(root)) == sorted(LOADING_GIFS)
