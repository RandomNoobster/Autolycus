from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import discord

from bot.discord_utils.interaction_framework import encode_custom_id
from bot.discord_utils.modals import SimpleModal
from database import interaction_sessions
from database import reminders as reminder_db
from database.mongo import get_db
from services import reminders as reminder_service

logger = logging.getLogger(__name__)

# Discord UI components only. No business logic here.

# A prompt's answer is picked up by the slash command, which then edits its own
# reply. That interaction token stops working after 15 minutes, so prompts close
# before it does.
PROMPT_TTL_SECONDS = 14 * 60
# Tabs and pagers are edited through each click's own interaction and can stay
# usable for longer.
PAGER_TTL_SECONDS = interaction_sessions.DEFAULT_TTL_SECONDS
# Handlers wake the waiting command directly; this re-read only covers a missed wake.
_POLL_FALLBACK_SECONDS = 1.0

_RAIDS_PAGER_CACHE: dict[str, dict[str, Any]] = {}
_RAIDS_PAGER_CACHE_MAX = 64

# Commands waiting on a prompt, woken when a click completes its session.
_session_events: dict[str, asyncio.Event] = {}


def _prune_raids_pager_cache(now: float) -> None:
    for session_id in [sid for sid, entry in _RAIDS_PAGER_CACHE.items() if entry["expires_at"] <= now]:
        _RAIDS_PAGER_CACHE.pop(session_id, None)
    while len(_RAIDS_PAGER_CACHE) > _RAIDS_PAGER_CACHE_MAX:
        _RAIDS_PAGER_CACHE.pop(next(iter(_RAIDS_PAGER_CACHE)))


def _set_raids_pager_cache(
    session_id: str,
    *,
    embeds: list[dict[str, Any]],
    target_ids: list[str],
    beige_turns: list[int],
    ttl_seconds: float = PAGER_TTL_SECONDS,
) -> None:
    now = time.monotonic()
    _RAIDS_PAGER_CACHE[session_id] = {
        "embeds": embeds,
        "target_ids": target_ids,
        "beige_turns": beige_turns,
        "expires_at": now + ttl_seconds,
    }
    _prune_raids_pager_cache(now)


def _get_raids_pager_cache(session_id: str) -> dict[str, Any]:
    _prune_raids_pager_cache(time.monotonic())
    return _RAIDS_PAGER_CACHE.get(session_id) or {}


def _session_changed(session_id: str) -> None:
    event = _session_events.get(session_id)
    if event is not None:
        event.set()


async def _respond_ephemeral(interaction: discord.Interaction, content: str) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=True)
        else:
            await interaction.response.send_message(content, ephemeral=True)
    except discord.HTTPException:
        logger.debug("Could not send ephemeral reply", exc_info=True)


async def _edit_message(interaction: discord.Interaction, **kwargs: Any) -> None:
    if interaction.response.is_done():
        await interaction.edit_original_response(**kwargs)
    else:
        await interaction.response.edit_message(**kwargs)


class _RoutedView(discord.ui.View):
    """A view whose buttons InteractionRegistry routes by custom ID.

    Stopped as soon as it is built: py-cord keeps every unfinished view it sends,
    and these never need its callbacks, so each prompt, tab and page would otherwise
    stay in memory for the life of the process.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.stop()


class PersistentYesNoView(_RoutedView):
    """Generalized persisted yes/no interaction view."""

    def __init__(self, session_id: str, *, positive: str = "Yes", negative: str = "No"):
        super().__init__()
        self.session_id = session_id
        self.add_item(
            discord.ui.Button(
                label=positive,
                style=discord.ButtonStyle.green,
                custom_id=encode_custom_id("yesno", session_id, "yes"),
            )
        )
        self.add_item(
            discord.ui.Button(
                label=negative,
                style=discord.ButtonStyle.red,
                custom_id=encode_custom_id("yesno", session_id, "no"),
            )
        )


def _disabled_yesno_view(session_id: str, positive: str, negative: str) -> discord.ui.View:
    view = PersistentYesNoView(session_id, positive=positive, negative=negative)
    for child in view.children:
        child.disabled = True
    return view


async def create_persistent_yesno_prompt(
    *,
    command: str,
    ctx: discord.ApplicationContext,
    positive: str = "Yes",
    negative: str = "No",
    disable_on_submit: bool = True,
    ttl_seconds: int = PROMPT_TTL_SECONDS,
) -> tuple[PersistentYesNoView, str]:
    session = await interaction_sessions.create_session(
        command=command,
        handler_key="yesno",
        user_id=ctx.author.id,
        guild_id=ctx.guild.id if ctx.guild else None,
        channel_id=ctx.channel_id,
        message_id=0,
        state={
            "result": None,
            "positive": positive,
            "negative": negative,
            "disable_on_submit": bool(disable_on_submit),
        },
        ttl_seconds=ttl_seconds,
        flow_type="confirm",
    )
    return PersistentYesNoView(session["session_id"], positive=positive, negative=negative), session["session_id"]


class PersistentChoiceView(_RoutedView):
    """Generalized persisted multi-button choice view.

    A choice with a ``modal`` spec opens a text modal before it counts as chosen.
    """

    def __init__(self, session_id: str, choices: list[dict]):
        super().__init__()
        self.session_id = session_id
        for choice in choices:
            style_value = int(choice.get("style", int(discord.ButtonStyle.primary)))
            handler_key = "choice_modal" if choice.get("modal") else "choice"
            self.add_item(
                discord.ui.Button(
                    label=str(choice["label"]),
                    style=discord.ButtonStyle(style_value),
                    custom_id=encode_custom_id(handler_key, session_id, str(choice["action"])),
                )
            )


def _disabled_choice_view(session_id: str, choices: list[dict]) -> discord.ui.View:
    view = PersistentChoiceView(session_id, choices)
    for child in view.children:
        child.disabled = True
    return view


async def create_persistent_choice_prompt(
    *,
    command: str,
    ctx: discord.ApplicationContext,
    choices: list[tuple[str, str, discord.ButtonStyle]],
    disable_on_submit: bool = True,
    ttl_seconds: int = PROMPT_TTL_SECONDS,
    modals: Optional[dict[str, dict[str, str]]] = None,
) -> tuple[PersistentChoiceView, str]:
    """A button prompt; ``modals`` maps an action to ``{title, label, placeholder}``.

    The text typed into a choice's modal is returned by
    :func:`wait_for_persistent_choice` with the action.
    """
    modals = modals or {}
    stored_choices = []
    for action, label, style in choices:
        choice: dict[str, Any] = {"action": action, "label": label, "style": int(style)}
        if action in modals:
            choice["modal"] = dict(modals[action])
        stored_choices.append(choice)
    session = await interaction_sessions.create_session(
        command=command,
        handler_key="choice",
        user_id=ctx.author.id,
        guild_id=ctx.guild.id if ctx.guild else None,
        channel_id=ctx.channel_id,
        message_id=0,
        state={
            "result": None,
            "choices": stored_choices,
            "disable_on_submit": bool(disable_on_submit),
        },
        ttl_seconds=ttl_seconds,
        flow_type="wizard",
    )
    return PersistentChoiceView(session["session_id"], stored_choices), session["session_id"]


class PersistentTabsView(_RoutedView):
    """Persisted tab-switching view for pre-rendered embeds."""

    def __init__(
        self,
        session_id: str,
        tabs: list[dict[str, Any]],
        active_index: int,
        link_label: Optional[str] = None,
        link_url: Optional[str] = None,
    ):
        super().__init__()
        self.session_id = session_id
        for idx, tab in enumerate(tabs):
            self.add_item(
                discord.ui.Button(
                    label=str(tab["label"]),
                    style=discord.ButtonStyle.primary,
                    custom_id=encode_custom_id("tabs", session_id, f"t{idx}"),
                    disabled=idx == active_index,
                )
            )
        if link_label and link_url:
            self.add_item(
                discord.ui.Button(
                    label=link_label,
                    style=discord.ButtonStyle.link,
                    url=link_url,
                )
            )


async def create_persistent_tabs_prompt(
    *,
    command: str,
    ctx: discord.ApplicationContext,
    tabs: list[tuple[str, discord.Embed]],
    initial_index: int = 0,
    ttl_seconds: int = PAGER_TTL_SECONDS,
    link_label: Optional[str] = None,
    link_url: Optional[str] = None,
) -> tuple[PersistentTabsView, str, discord.Embed]:
    stored_tabs = [{"label": label, "embed": embed.to_dict()} for label, embed in tabs]
    safe_index = min(max(initial_index, 0), max(0, len(stored_tabs) - 1))
    session = await interaction_sessions.create_session(
        command=command,
        handler_key="tabs",
        user_id=ctx.author.id,
        guild_id=ctx.guild.id if ctx.guild else None,
        channel_id=ctx.channel_id,
        message_id=0,
        state={
            "tabs": stored_tabs,
            "active_index": safe_index,
            "link_label": link_label,
            "link_url": link_url,
        },
        ttl_seconds=ttl_seconds,
        flow_type="pagination",
    )
    active_embed = discord.Embed.from_dict(stored_tabs[safe_index]["embed"])
    return (
        PersistentTabsView(
            session["session_id"],
            stored_tabs,
            safe_index,
            link_label=link_label,
            link_url=link_url,
        ),
        session["session_id"],
        active_embed,
    )


class PersistentRaidsPagerView(_RoutedView):
    def __init__(self, session_id: str, beige_enabled: bool):
        super().__init__()
        for label, action in (("<<", "first"), ("<", "prev"), (">", "next"), (">>", "last")):
            self.add_item(
                discord.ui.Button(
                    label=label,
                    style=discord.ButtonStyle.primary,
                    custom_id=encode_custom_id("raids_pager", session_id, action),
                )
            )
        self.add_item(
            discord.ui.Button(
                label="Beige reminder",
                style=discord.ButtonStyle.primary,
                custom_id=encode_custom_id("raids_pager", session_id, "beige"),
                disabled=not beige_enabled,
            )
        )


async def create_persistent_raids_pager_prompt(
    *,
    ctx: discord.ApplicationContext,
    embeds: list[discord.Embed],
    target_ids: list[str],
    beige_turns: list[int],
    ttl_seconds: int = PAGER_TTL_SECONDS,
) -> tuple[PersistentRaidsPagerView, str, discord.Embed]:
    embed_dicts = [embed.to_dict() for embed in embeds]
    session = await interaction_sessions.create_session(
        command="raids",
        handler_key="raids_pager",
        user_id=ctx.author.id,
        guild_id=ctx.guild.id if ctx.guild else None,
        channel_id=ctx.channel_id,
        message_id=0,
        state={
            "index": 0,
            "count": len(embed_dicts),
        },
        ttl_seconds=ttl_seconds,
        flow_type="pagination",
    )
    _set_raids_pager_cache(
        session["session_id"],
        embeds=embed_dicts,
        target_ids=[str(x) for x in target_ids],
        beige_turns=[int(x) for x in beige_turns],
        ttl_seconds=ttl_seconds,
    )
    first_embed = discord.Embed.from_dict(embed_dicts[0])
    return (
        PersistentRaidsPagerView(
            session["session_id"],
            beige_enabled=bool(beige_turns and beige_turns[0] > 0),
        ),
        session["session_id"],
        first_embed,
    )


async def _wait_for_completed_session(session_id: str, timeout_seconds: float) -> Optional[dict]:
    """The session once a click completes it; None when it closes, expires or times out."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    event = _session_events.setdefault(session_id, asyncio.Event())
    try:
        while True:
            # Cleared before the read, so a click landing after it still wakes the wait.
            event.clear()
            session = await interaction_sessions.get_session(session_id)
            if not session:
                return None
            status = session.get("status")
            if status == "completed":
                return session
            if status in interaction_sessions.TERMINAL_STATUSES:
                return None
            remaining = deadline - loop.time()
            if interaction_sessions.is_expired(session) or remaining <= 0:
                # Later clicks then say the prompt expired instead of doing nothing.
                await interaction_sessions.mark_terminal(session_id, "expired")
                return None
            try:
                await asyncio.wait_for(event.wait(), timeout=min(_POLL_FALLBACK_SECONDS, remaining))
            except asyncio.TimeoutError:
                pass
    finally:
        _session_events.pop(session_id, None)


async def wait_for_persistent_yesno_result(
    session_id: str,
    timeout_seconds: float = PROMPT_TTL_SECONDS,
) -> Optional[bool]:
    """The yes/no answer, or None when the prompt closed without one."""
    session = await _wait_for_completed_session(session_id, timeout_seconds)
    result = ((session or {}).get("state") or {}).get("result")
    return result if isinstance(result, bool) else None


async def wait_for_persistent_choice(
    session_id: str,
    timeout_seconds: float = PROMPT_TTL_SECONDS,
) -> Optional[tuple[str, dict[str, Any]]]:
    """The chosen action and the prompt state (``text`` holds a modal's input)."""
    session = await _wait_for_completed_session(session_id, timeout_seconds)
    state = dict((session or {}).get("state") or {})
    result = state.get("result")
    if isinstance(result, str) and result:
        return result, state
    return None


async def wait_for_persistent_choice_result(
    session_id: str,
    timeout_seconds: float = PROMPT_TTL_SECONDS,
) -> Optional[str]:
    answer = await wait_for_persistent_choice(session_id, timeout_seconds)
    return answer[0] if answer else None


async def _complete_prompt(
    interaction: discord.Interaction,
    session: dict,
    new_state: dict[str, Any],
    disabled_view: Optional[discord.ui.View],
) -> None:
    if disabled_view is not None:
        # Before completing: the waiting command edits in its next step as soon as
        # the session completes, and this edit must not land on top of it.
        try:
            await _edit_message(interaction, view=disabled_view)
        except discord.HTTPException:
            logger.debug("Could not disable prompt buttons", exc_info=True)
    changed = await interaction_sessions.try_transition(
        session_id=session["session_id"],
        expected_version=int(session.get("version", 0)),
        new_state=new_state,
        new_status="completed",
    )
    if not changed:
        await _respond_ephemeral(interaction, "This interaction was already handled.")
        return
    _session_changed(session["session_id"])


async def _yesno_interaction_handler(
    interaction: discord.Interaction,
    session: dict,
    action_id: str,
) -> None:
    state = dict(session.get("state") or {})
    result = {"yes": True, "no": False}.get(action_id)
    if result is None:
        await _respond_ephemeral(interaction, "Unknown action.")
        return
    disabled_view = None
    if bool(state.get("disable_on_submit", True)):
        disabled_view = _disabled_yesno_view(
            session["session_id"],
            positive=str(state.get("positive", "Yes")),
            negative=str(state.get("negative", "No")),
        )
    await _complete_prompt(interaction, session, {**state, "result": result}, disabled_view)


async def _choice_interaction_handler(
    interaction: discord.Interaction,
    session: dict,
    action_id: str,
) -> None:
    state = dict(session.get("state") or {})
    choices = list(state.get("choices") or [])
    if action_id not in {str(choice.get("action")) for choice in choices}:
        await _respond_ephemeral(interaction, "Unknown action.")
        return
    disabled_view = None
    if bool(state.get("disable_on_submit", True)):
        disabled_view = _disabled_choice_view(session["session_id"], choices)
    await _complete_prompt(interaction, session, {**state, "result": action_id}, disabled_view)


async def _choice_modal_interaction_handler(
    interaction: discord.Interaction,
    session: dict,
    action_id: str,
) -> None:
    """A choice that first asks for text (registered without the automatic defer).

    A modal can only be the first response to the click, so it is opened here
    rather than by the waiting command.
    """
    state = dict(session.get("state") or {})
    spec = next(
        (
            choice.get("modal")
            for choice in state.get("choices") or []
            if str(choice.get("action")) == action_id and choice.get("modal")
        ),
        None,
    )
    if not spec:
        await _respond_ephemeral(interaction, "Unknown action.")
        return
    modal = SimpleModal(
        title=str(spec.get("title") or "Autolycus")[:45],
        label=str(spec.get("label") or "Value")[:45],
        placeholder=str(spec.get("placeholder") or "")[:100],
    )
    await interaction.response.send_modal(modal)
    await modal.wait()
    if not modal.submitted:
        return
    changed = await interaction_sessions.try_transition(
        session_id=session["session_id"],
        expected_version=int(session.get("version", 0)),
        new_state={**state, "result": action_id, "text": modal.text},
        new_status="completed",
    )
    if changed:
        _session_changed(session["session_id"])


async def _tabs_interaction_handler(
    interaction: discord.Interaction,
    session: dict,
    action_id: str,
) -> None:
    try:
        next_index = int(action_id[1:]) if action_id.startswith("t") else -1
    except ValueError:
        next_index = -1
    state = dict(session.get("state") or {})
    tabs = list(state.get("tabs") or [])
    if not 0 <= next_index < len(tabs):
        await _respond_ephemeral(interaction, "Invalid tab.")
        return

    changed = await interaction_sessions.try_transition(
        session_id=session["session_id"],
        expected_version=int(session.get("version", 0)),
        new_state={**state, "active_index": next_index},
        new_status="active",
    )
    if not changed:
        await _respond_ephemeral(interaction, "This interaction was updated elsewhere. Try again.")
        return

    embed = discord.Embed.from_dict(tabs[next_index]["embed"])
    view = PersistentTabsView(
        session["session_id"],
        tabs,
        next_index,
        link_label=state.get("link_label"),
        link_url=state.get("link_url"),
    )
    await _edit_message(interaction, embed=embed, view=view)


async def _raids_pager_interaction_handler(
    interaction: discord.Interaction,
    session: dict,
    action_id: str,
) -> None:
    state = dict(session.get("state") or {})
    payload = _get_raids_pager_cache(session["session_id"])
    embeds = list(payload.get("embeds") or [])
    target_ids = [str(x) for x in (payload.get("target_ids") or [])]
    beige_turns = [int(x) for x in (payload.get("beige_turns") or [])]
    if not embeds or len(embeds) != len(target_ids):
        # The pages are kept in memory only, so a restart loses them.
        await _respond_ephemeral(interaction, "This raid pager is no longer available. Please rerun `/raids`.")
        return

    index = min(max(int(state.get("index", 0)), 0), len(embeds) - 1)
    max_idx = len(embeds) - 1
    if action_id == "first":
        index = 0
    elif action_id == "prev":
        index = max_idx if index <= 0 else index - 1
    elif action_id == "next":
        index = 0 if index >= max_idx else index + 1
    elif action_id == "last":
        index = max_idx
    elif action_id != "beige":
        await _respond_ephemeral(interaction, "Unknown pager action.")
        return

    cur_target = target_ids[index]
    cur_beige = beige_turns[index] if index < len(beige_turns) else 0
    ephemeral_text: Optional[str] = None
    if action_id == "beige":
        if cur_beige <= 0:
            ephemeral_text = "They are not in beige!"
        else:
            result = await reminder_service.add_reminder(get_db(), interaction.user.id, cur_target)
            if not result.added:
                ephemeral_text = "You already have a beige reminder for this nation!"
            else:
                ephemeral_text = f"A beige reminder for <https://politicsandwar.com/nation/id={cur_target}> was added!"
                if result.test_dm is not None:
                    ephemeral_text += (
                        " I'm sending you a test DM. Press **Got it** in it so we know reminders reach you."
                    )

    # The button is offered for beige targets the user doesn't watch yet.
    beige_enabled = False
    if cur_beige > 0:
        profile = await reminder_db.get_profile(get_db(), interaction.user.id)
        beige_enabled = cur_target not in reminder_db.watched_nation_ids(profile)

    changed = await interaction_sessions.try_transition(
        session_id=session["session_id"],
        expected_version=int(session.get("version", 0)),
        new_state={**state, "index": index},
        new_status="active",
    )
    if not changed:
        await _respond_ephemeral(interaction, "This pager changed elsewhere. Try again.")
        return

    embed = discord.Embed.from_dict(embeds[index])
    view = PersistentRaidsPagerView(session["session_id"], beige_enabled=beige_enabled)
    await _edit_message(interaction, embed=embed, view=view)
    if ephemeral_text:
        await _respond_ephemeral(interaction, ephemeral_text)


def register_interaction_handlers(registry) -> None:
    registry.register("yesno", _yesno_interaction_handler)
    registry.register("choice", _choice_interaction_handler)
    registry.register("choice_modal", _choice_modal_interaction_handler, auto_defer=False)
    registry.register("tabs", _tabs_interaction_handler)
    registry.register("raids_pager", _raids_pager_interaction_handler)


class Switch(discord.ui.View):
    """In-memory pager over pre-rendered embeds (for results, not prompts)."""

    def __init__(self, ctx, max_page: int, embeds: list, timeout: int = 600, author_check: bool = True, cur_page: int = 0):
        # On timeout the buttons are disabled through the command's own token, which
        # only works for 15 minutes.
        super().__init__(timeout=min(timeout, PROMPT_TTL_SECONDS))
        self.ctx = ctx
        self.author_check = author_check
        self.cur_page = cur_page
        self.max_page = max_page - 1
        self.embeds = embeds

    @discord.ui.button(label="<<", style=discord.ButtonStyle.primary)
    async def far_left_callback(self, _button: discord.Button, interaction: discord.Interaction) -> None:
        self.cur_page = 0
        await interaction.response.edit_message(embed=self.embeds[0])

    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
    async def left_callback(self, _button: discord.Button, interaction: discord.Interaction) -> None:
        if self.cur_page == 0:
            self.cur_page = self.max_page
        else:
            self.cur_page -= 1
        await interaction.response.edit_message(embed=self.embeds[self.cur_page])

    @discord.ui.button(label=">", style=discord.ButtonStyle.primary)
    async def right_callback(self, _button: discord.Button, interaction: discord.Interaction) -> None:
        if self.cur_page == self.max_page:
            self.cur_page = 0
        else:
            self.cur_page += 1
        await interaction.response.edit_message(embed=self.embeds[self.cur_page])

    @discord.ui.button(label=">>", style=discord.ButtonStyle.primary)
    async def far_right_callback(self, _button: discord.Button, interaction: discord.Interaction) -> None:
        self.cur_page = self.max_page
        await interaction.response.edit_message(embed=self.embeds[self.max_page])

    async def interaction_check(self, interaction) -> bool:
        if interaction.user != self.ctx.author and self.author_check:
            await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        # Keep the results on screen; only the paging stops.
        for child in self.children:
            child.disabled = True
        try:
            await self.ctx.edit(view=self)
        except discord.HTTPException:
            logger.debug("Could not disable pager buttons after timeout", exc_info=True)
