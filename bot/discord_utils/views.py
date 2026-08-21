from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import discord

logger = logging.getLogger(__name__)

from bot.discord_utils import errors as err_util
from bot.discord_utils.interaction_framework import encode_custom_id
from bot.discord_utils.modals import SimpleModal
from database import interaction_sessions
from database.mongo import get_db

# Discord UI components only. No business logic here.
_RAIDS_PAGER_CACHE: dict[str, dict[str, Any]] = {}
_RAIDS_PAGER_CACHE_ORDER: list[str] = []
_RAIDS_PAGER_CACHE_MAX = 256


def _set_raids_pager_cache(
    session_id: str,
    *,
    embeds: list[dict[str, Any]],
    target_ids: list[str],
    beige_turns: list[int],
) -> None:
    _RAIDS_PAGER_CACHE[session_id] = {
        "embeds": embeds,
        "target_ids": target_ids,
        "beige_turns": beige_turns,
    }
    _RAIDS_PAGER_CACHE_ORDER.append(session_id)
    while len(_RAIDS_PAGER_CACHE_ORDER) > _RAIDS_PAGER_CACHE_MAX:
        old_session_id = _RAIDS_PAGER_CACHE_ORDER.pop(0)
        _RAIDS_PAGER_CACHE.pop(old_session_id, None)


async def run_timeout(ctx, view: Optional[discord.ui.View]) -> None:
    try:
        ref = err_util.new_error_reference()
        embed = err_util.error_embed(
            "Timed out",
            f"<@{ctx.author.id}> You didn't respond in time, so this command closed.",
            reference=ref,
        )
        if view:
            for x in view.children:
                x.disabled = True
            await ctx.edit(content="", embed=embed, view=view)
        else:
            await ctx.edit(content="", embed=embed)
    except Exception:
        # Swallow timeout errors silently; logging handled by caller
        pass

class YesOrNoView(discord.ui.View):
    def __init__(self, ctx, positive: str = "Yes", negative: str = "No", positive_style: discord.ButtonStyle = discord.ButtonStyle.green, negative_style: discord.ButtonStyle = discord.ButtonStyle.red, timeout: int = 600, author_check: bool = True):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.author_check = author_check
        self.result: Optional[bool] = None
        positive_button = discord.ui.Button(label=positive, style=positive_style)
        positive_button.callback = self.primary_callback
        self.add_item(positive_button)
        negative_button = discord.ui.Button(label=negative, style=negative_style)
        negative_button.callback = self.secondary_callback
        self.add_item(negative_button)

    async def primary_callback(self, i: discord.Interaction):
        self.result = True
        await i.response.edit_message()
        self.stop()
    
    async def secondary_callback(self, i: discord.Interaction):
        self.result = False
        await i.response.edit_message()
        self.stop()

    async def interaction_check(self, interaction) -> bool:
        if interaction.user != self.ctx.author and self.author_check:
            await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
            return False
        return True
    
    async def on_timeout(self):
        await run_timeout(self.ctx, self)


class PersistentYesNoView(discord.ui.View):
    """Generalized persisted yes/no interaction view."""

    def __init__(self, session_id: str, *, positive: str = "Yes", negative: str = "No"):
        super().__init__(timeout=None)
        self.session_id = session_id
        positive_button = discord.ui.Button(
            label=positive,
            style=discord.ButtonStyle.green,
            custom_id=encode_custom_id("yesno", session_id, "yes"),
        )
        negative_button = discord.ui.Button(
            label=negative,
            style=discord.ButtonStyle.red,
            custom_id=encode_custom_id("yesno", session_id, "no"),
        )
        self.add_item(positive_button)
        self.add_item(negative_button)


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
    ttl_seconds: int = interaction_sessions.DEFAULT_TTL_SECONDS,
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


class PersistentChoiceView(discord.ui.View):
    """Generalized persisted multi-button choice view."""

    def __init__(self, session_id: str, choices: list[dict]):
        super().__init__(timeout=None)
        self.session_id = session_id
        for choice in choices:
            style_value = int(choice.get("style", int(discord.ButtonStyle.primary)))
            style = discord.ButtonStyle(style_value)
            action = str(choice["action"])
            button = discord.ui.Button(
                label=str(choice["label"]),
                style=style,
                custom_id=encode_custom_id("choice", session_id, action),
            )
            self.add_item(button)


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
    ttl_seconds: int = interaction_sessions.DEFAULT_TTL_SECONDS,
) -> tuple[PersistentChoiceView, str]:
    stored_choices = [
        {"action": action, "label": label, "style": int(style)}
        for action, label, style in choices
    ]
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


class PersistentTabsView(discord.ui.View):
    """Persisted tab-switching view for pre-rendered embeds."""

    def __init__(
        self,
        session_id: str,
        tabs: list[dict[str, Any]],
        active_index: int,
        link_label: Optional[str] = None,
        link_url: Optional[str] = None,
    ):
        super().__init__(timeout=None)
        self.session_id = session_id
        for idx, tab in enumerate(tabs):
            btn = discord.ui.Button(
                label=str(tab["label"]),
                style=discord.ButtonStyle.primary,
                custom_id=encode_custom_id("tabs", session_id, f"t{idx}"),
                disabled=idx == active_index,
            )
            self.add_item(btn)
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
    ttl_seconds: int = interaction_sessions.DEFAULT_TTL_SECONDS,
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


class PersistentRaidsPagerView(discord.ui.View):
    def __init__(self, session_id: str, beige_enabled: bool):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="<<",
                style=discord.ButtonStyle.primary,
                custom_id=encode_custom_id("raids_pager", session_id, "first"),
            )
        )
        self.add_item(
            discord.ui.Button(
                label="<",
                style=discord.ButtonStyle.primary,
                custom_id=encode_custom_id("raids_pager", session_id, "prev"),
            )
        )
        self.add_item(
            discord.ui.Button(
                label=">",
                style=discord.ButtonStyle.primary,
                custom_id=encode_custom_id("raids_pager", session_id, "next"),
            )
        )
        self.add_item(
            discord.ui.Button(
                label=">>",
                style=discord.ButtonStyle.primary,
                custom_id=encode_custom_id("raids_pager", session_id, "last"),
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
    ttl_seconds: int = interaction_sessions.DEFAULT_TTL_SECONDS,
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


async def bind_persistent_prompt_message(session_id: str, message_id: int) -> None:
    await interaction_sessions.set_session_message(session_id, message_id)


async def wait_for_persistent_yesno_result(
    session_id: str,
    timeout_seconds: int = interaction_sessions.DEFAULT_TTL_SECONDS,
) -> Optional[bool]:
    """Poll session state for yes/no completion."""
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        session = await interaction_sessions.get_session(session_id)
        if not session:
            return None
        if interaction_sessions.is_expired(session):
            await interaction_sessions.mark_terminal(session_id, "expired")
            return None
        if session.get("status") == "completed":
            result = session.get("state", {}).get("result")
            if isinstance(result, bool):
                return result
            return None
        if session.get("status") in interaction_sessions.TERMINAL_STATUSES:
            return None
        await asyncio.sleep(0.05)
    return None


async def wait_for_persistent_choice_result(
    session_id: str,
    timeout_seconds: int = interaction_sessions.DEFAULT_TTL_SECONDS,
) -> Optional[str]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        session = await interaction_sessions.get_session(session_id)
        if not session:
            return None
        if interaction_sessions.is_expired(session):
            await interaction_sessions.mark_terminal(session_id, "expired")
            return None
        if session.get("status") == "completed":
            result = session.get("state", {}).get("result")
            if isinstance(result, str) and result:
                return result
            return None
        if session.get("status") in interaction_sessions.TERMINAL_STATUSES:
            return None
        await asyncio.sleep(0.05)
    return None


async def _yesno_interaction_handler(
    interaction: discord.Interaction,
    session: dict,
    action_id: str,
) -> None:
    state = dict(session.get("state") or {})
    positive = str(state.get("positive", "Yes"))
    negative = str(state.get("negative", "No"))
    result = True if action_id == "yes" else False if action_id == "no" else None
    if result is None:
        if interaction.response.is_done():
            await interaction.followup.send("Unknown action.", ephemeral=True)
        else:
            await interaction.response.send_message("Unknown action.", ephemeral=True)
        return

    new_state = dict(state)
    new_state["result"] = result
    disable_on_submit = bool(state.get("disable_on_submit", True))
    changed = await interaction_sessions.try_transition(
        session_id=session["session_id"],
        expected_version=int(session.get("version", 0)),
        new_state=new_state,
        new_status="completed",
    )
    if not changed:
        if interaction.response.is_done():
            await interaction.followup.send("This interaction was already handled.", ephemeral=True)
        else:
            await interaction.response.send_message("This interaction was already handled.", ephemeral=True)
        return

    if disable_on_submit:
        view = _disabled_yesno_view(session["session_id"], positive=positive, negative=negative)
        if interaction.response.is_done():
            await interaction.edit_original_response(view=view)
        else:
            await interaction.response.edit_message(view=view)
    elif interaction.response.is_done():
        # Keep the current wizard embed visible; the slash command will replace it
        # with the next step immediately after polling returns.
        return
    else:
        await interaction.response.defer()


async def _choice_interaction_handler(
    interaction: discord.Interaction,
    session: dict,
    action_id: str,
) -> None:
    state = dict(session.get("state") or {})
    choices = list(state.get("choices") or [])
    valid_actions = {str(choice.get("action")) for choice in choices}
    if action_id not in valid_actions:
        if interaction.response.is_done():
            await interaction.followup.send("Unknown action.", ephemeral=True)
        else:
            await interaction.response.send_message("Unknown action.", ephemeral=True)
        return

    new_state = dict(state)
    new_state["result"] = action_id
    disable_on_submit = bool(state.get("disable_on_submit", True))
    changed = await interaction_sessions.try_transition(
        session_id=session["session_id"],
        expected_version=int(session.get("version", 0)),
        new_state=new_state,
        new_status="completed",
    )
    if not changed:
        if interaction.response.is_done():
            await interaction.followup.send("This interaction was already handled.", ephemeral=True)
        else:
            await interaction.response.send_message("This interaction was already handled.", ephemeral=True)
        return

    if disable_on_submit:
        view = _disabled_choice_view(session["session_id"], choices)
        if interaction.response.is_done():
            await interaction.edit_original_response(view=view)
        else:
            await interaction.response.edit_message(view=view)
    elif interaction.response.is_done():
        # Keep the current wizard embed visible; the slash command will replace it
        # with the next step immediately after polling returns.
        return
    else:
        await interaction.response.defer()


async def _tabs_interaction_handler(
    interaction: discord.Interaction,
    session: dict,
    action_id: str,
) -> None:
    if not action_id.startswith("t"):
        if interaction.response.is_done():
            await interaction.followup.send("Unknown tab action.", ephemeral=True)
        else:
            await interaction.response.send_message("Unknown tab action.", ephemeral=True)
        return
    try:
        next_index = int(action_id[1:])
    except ValueError:
        if interaction.response.is_done():
            await interaction.followup.send("Invalid tab action.", ephemeral=True)
        else:
            await interaction.response.send_message("Invalid tab action.", ephemeral=True)
        return

    state = dict(session.get("state") or {})
    tabs = list(state.get("tabs") or [])
    if not tabs or next_index < 0 or next_index >= len(tabs):
        if interaction.response.is_done():
            await interaction.followup.send("Invalid tab target.", ephemeral=True)
        else:
            await interaction.response.send_message("Invalid tab target.", ephemeral=True)
        return

    new_state = dict(state)
    new_state["active_index"] = next_index
    changed = await interaction_sessions.try_transition(
        session_id=session["session_id"],
        expected_version=int(session.get("version", 0)),
        new_state=new_state,
        new_status="active",
    )
    if not changed:
        if interaction.response.is_done():
            await interaction.followup.send("This interaction was updated elsewhere. Try again.", ephemeral=True)
        else:
            await interaction.response.send_message("This interaction was updated elsewhere. Try again.", ephemeral=True)
        return

    embed = discord.Embed.from_dict(tabs[next_index]["embed"])
    view = PersistentTabsView(
        session["session_id"],
        tabs,
        next_index,
        link_label=state.get("link_label"),
        link_url=state.get("link_url"),
    )
    if interaction.response.is_done():
        await interaction.edit_original_response(embed=embed, view=view)
    else:
        await interaction.response.edit_message(embed=embed, view=view)


async def _raids_pager_interaction_handler(
    interaction: discord.Interaction,
    session: dict,
    action_id: str,
) -> None:
    # Ack immediately to avoid the 3-second interaction timeout while
    # we do DB/session work for pager updates.
    if not interaction.response.is_done():
        await interaction.response.defer()

    state = dict(session.get("state") or {})
    payload = _RAIDS_PAGER_CACHE.get(session["session_id"]) or {}
    embeds = list(payload.get("embeds") or [])
    target_ids = [str(x) for x in (payload.get("target_ids") or [])]
    beige_turns = [int(x) for x in (payload.get("beige_turns") or [])]
    # Backward compatibility for old sessions created before cache-only payload.
    if not embeds:
        embeds = list(state.get("embeds") or [])
    if not target_ids:
        target_ids = [str(x) for x in (state.get("target_ids") or [])]
    if not beige_turns:
        beige_turns = [int(x) for x in (state.get("beige_turns") or [])]
    if not embeds or len(embeds) != len(target_ids):
        await interaction.followup.send("This raid pager is invalid. Please rerun `/raids`.", ephemeral=True)
        return

    index = int(state.get("index", 0))
    max_idx = len(embeds) - 1
    if action_id == "first":
        index = 0
    elif action_id == "prev":
        index = max_idx if index <= 0 else index - 1
    elif action_id == "next":
        index = 0 if index >= max_idx else index + 1
    elif action_id == "last":
        index = max_idx
    elif action_id == "beige":
        pass
    else:
        await interaction.followup.send("Unknown pager action.", ephemeral=True)
        return

    ephemeral_text: Optional[str] = None
    if action_id == "beige":
        cur_target = target_ids[index]
        cur_beige = beige_turns[index] if index < len(beige_turns) else 0
        if cur_beige <= 0:
            ephemeral_text = "They are not in beige!"
        else:
            db = get_db()
            user = await db.global_users.find_one({"user": interaction.user.id})
            if user is None:
                ephemeral_text = "I didn't find you in the database! Make sure to `/verify`!"
            else:
                alerts = [str(x) for x in user.get("beige_alerts", [])]
                if cur_target in alerts:
                    ephemeral_text = "You already have a beige reminder for this nation!"
                else:
                    await db.global_users.find_one_and_update(
                        {"user": interaction.user.id},
                        {"$addToSet": {"beige_alerts": cur_target}},
                    )
                    ephemeral_text = f"A beige reminder for <https://politicsandwar.com/nation/id={cur_target}> was added!"

    # Re-check whether beige should be enabled for current index (state + user reminders)
    beige_enabled = False
    cur_beige = beige_turns[index] if index < len(beige_turns) else 0
    if cur_beige > 0:
        db = get_db()
        user = await db.global_users.find_one({"user": interaction.user.id})
        alerts = [str(x) for x in (user or {}).get("beige_alerts", [])]
        beige_enabled = target_ids[index] not in alerts

    new_state = dict(state)
    new_state["index"] = index
    changed = await interaction_sessions.try_transition(
        session_id=session["session_id"],
        expected_version=int(session.get("version", 0)),
        new_state=new_state,
        new_status="active",
    )
    if not changed:
        await interaction.followup.send("This pager changed elsewhere. Try again.", ephemeral=True)
        return

    embed = discord.Embed.from_dict(embeds[index])
    view = PersistentRaidsPagerView(session["session_id"], beige_enabled=beige_enabled)
    await interaction.edit_original_response(embed=embed, view=view)
    if ephemeral_text:
        await interaction.followup.send(ephemeral_text, ephemeral=True)


def register_interaction_handlers(registry) -> None:
    registry.register("yesno", _yesno_interaction_handler)
    registry.register("choice", _choice_interaction_handler)
    registry.register("tabs", _tabs_interaction_handler)
    registry.register("raids_pager", _raids_pager_interaction_handler)

class Dropdown(discord.ui.Select):
    def __init__(self, main_view, select_options: dict = {}):
        self.apples = main_view
        options = []
        n = 0
        for x in select_options.get('options', []):
            options.append(discord.SelectOption(label=x['label'], description=x['description'], emoji=x['emoji'], value=n, default=x.get('default', False)))
            n += 1
        self.selectable_options = options
        super().__init__(
            placeholder=select_options.get('placeholder', "Select an option from the dropdown"),
            min_values=select_options.get('min_values', 1),
            max_values=select_options.get('max_values', 1),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.apples.embeds = sorted(self.apples.embeds, key=self.selectable_options[int(interaction.data['values'][0])]['sort_by'], reverse=True)
        await interaction.response.edit_message(embed=self.apples.embeds[0])

class Switch(discord.ui.View):
    def __init__(self, ctx, max_page: int, embeds: list, timeout: int = 600, author_check: bool = True, cur_page: int = 0, select_options: dict = {}):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.author_check = author_check
        self.cur_page = cur_page
        self.max_page = max_page - 1
        self.embeds = embeds
        if select_options:
            self.add_item(Dropdown(self, select_options))

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
        await run_timeout(self.ctx, self)

async def reaction_checker(bot: discord.Bot, message: discord.Message, embeds: list[discord.Embed]) -> None:
    reactions = []
    for i in range(len(embeds)):
        reactions.append(asyncio.create_task(message.add_reaction(f"{i+1}\N{variation selector-16}\N{combining enclosing keycap}")))
    await asyncio.gather(*reactions)
    while True:
        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=600)
            if user.bot or reaction.message != message:
                continue
            elif "\N{variation selector-16}\N{combining enclosing keycap}" in str(reaction.emoji):
                await message.edit(embed=embeds[int(str(reaction.emoji)[0])-1])
                await message.remove_reaction(reaction, user)
        except asyncio.TimeoutError:
            ref = err_util.new_error_reference()
            to_embed = err_util.error_embed(
                "Timed out",
                "This command closed because nothing was selected in time.",
                reference=ref,
            )
            await message.edit(content=None, embed=to_embed)
            break
