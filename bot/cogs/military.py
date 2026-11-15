import asyncio
import logging
import math
import os
import re
from datetime import datetime, timezone
from functools import partial
from typing import Any, Optional

import discord
from discord.commands import Option, SlashCommandGroup, slash_command
from discord.ext import commands

from logic import queries
from logic import common
from database import mongo as db_mongo
from bot.discord_utils import helpers, views
from bot.discord_utils import errors as err_util
from bot.discord_utils.embeds import with_support_footer
from bot.discord_utils.loading_display import LoadingDisplay
from logic import api_client
from logic import military as military_logic
from logic.common import _war_field, normalize_alliance_position, parse_war_date
from logic.damage import calculate_damage as calculate_damage_logic
from logic.merge_utils import get_query
from logic.nuke_targets import (
    NUKE_TARGET_COLUMNS,
    NUKE_TARGET_JSON_FIELDS,
    compute_nuke_missile_metrics,
)
from logic.raids import calculate_days_inactive, current_turn_counts, is_in_vacation_mode, war_turns_left
from database.sqlite_cache import (
    find_nation as sqlite_find_nation,
    get_alliances_by_ids,
    get_all_nations_filtered,
    get_nations_by_ids,
    get_nations_db_path,
)
from core.config import (
    AUTOLYCUS_WEB_BASE_URL as WEB_BASE_URL,
)
from database import reminders as reminder_db
from logic import reminders as reminder_rules
from services import reminders as reminder_service

logger = logging.getLogger(__name__)

api_key = os.getenv("API_KEY")
call_api = partial(api_client.call, api_key=api_key)

# Get database instance for queries
db = db_mongo.get_db()

# What /raids reads: the scanner precomputes income, loot, defensive slots and
# treasure counts per nation, as the website's raids page uses them.
_RAID_COLUMNS = [
    "id", "nation_name", "leader_name", "alliance_id", "alliance_position", "alliance",
    "score", "color", "beige_turns", "vacation_mode_turns", "vmode", "nation_loot_value",
    "last_active", "soldiers", "tanks", "aircraft", "ships", "missiles", "nukes",
    "population", "_created_at", "monetary_net_num", "net_cash_num", "def_slots",
    "treasure_count",
]
# Always left out of /raids.
_EXCLUDED_RAID_ALLIANCES = frozenset({"4729", "8819"})
# Saved /raids "who" filters (kept in this form in users' saved configs).
WHO_ALL = ""
WHO_APPLICANTS = " alliance_position:[0,1]"
WHO_NO_ALLIANCE = " alliance_id:0"
# The raids pager keeps its pages in memory, so it holds the best targets only.
MAX_RAID_PAGES = 100
MESSAGE_MODE_TARGETS = 20
NUKE_TARGETS_PER_PAGE = 8
# Under Discord's 6000-character limit per embed, leaving room for a closing note.
_EMBED_CHAR_BUDGET = 5700
_MAX_DESCRIPTION_CHARS = 4096
_RAIDS_NOT_VERIFIED_MESSAGE = 'I could not find your nation, make sure that you are verified by using `/verify`!'
# War threads are named "... (<nation id>)".
_THREAD_NATION_ID = re.compile(r"\((\d+)\)\s*$")


def _num(value: Any) -> float:
    """A stored count as a number; NULL or junk (a partial row) is 0."""
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _money(value: Any) -> str:
    return f"${round(_num(value)):,}"


def thread_nation_id(channel: Any) -> Optional[str]:
    """The nation id ending a war thread's name, e.g. "Raid on Rose (123456)"; else None."""
    if not isinstance(channel, discord.Thread):
        return None
    match = _THREAD_NATION_ID.search(channel.name or "")
    return match.group(1) if match else None


def select_raid_targets(
    nations: list[dict[str, Any]],
    *,
    who: str,
    max_wars: int,
    inactive_limit: int,
    include_beige: bool,
    minimum_loot: int,
    excluded_alliances: set[str],
    now: datetime,
    fallback_written_at: Any,
    attacker_id: Optional[str] = None,
    attacker_alliance_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Cached nations that pass the /raids filters, with normalized fields.

    The attacker and members of the attacker's alliance are left out. Beige and
    vacation-mode turns are counted down by the turns since each row was written,
    so a row cached before a turn change isn't shown a turn behind.
    """
    own_alliance = str(attacker_alliance_id or "0")
    targets: list[dict[str, Any]] = []
    for nation in nations:
        if attacker_id is not None and str(nation.get("id")) == str(attacker_id):
            continue
        alliance_id = str(nation.get("alliance_id") or "0")
        if own_alliance != "0" and alliance_id == own_alliance:
            continue
        position = normalize_alliance_position(nation.get("alliance_position"))
        if who == WHO_APPLICANTS and alliance_id != "0" and position not in ("NOALLIANCE", "APPLICANT"):
            continue
        if who == WHO_NO_ALLIANCE and alliance_id != "0":
            continue
        if alliance_id in excluded_alliances:
            continue

        beige_left, vm_turns = current_turn_counts(nation, now, fallback_written_at)
        # Nations in vacation mode can't be declared on.
        if is_in_vacation_mode({"vmode": nation.get("vmode"), "vacation_mode_turns": vm_turns}):
            continue
        if nation.get("beige_turns") is None:
            beige_turns = 0
            in_beige = nation.get("color") == "beige"
        else:
            beige_turns = beige_left
            in_beige = beige_turns > 0
        if in_beige and not include_beige:
            continue

        def_slots = _int(nation.get("def_slots"))
        if def_slots > max_wars:
            continue
        days_inactive = calculate_days_inactive(nation.get("last_active"), now)
        if days_inactive < inactive_limit:
            continue
        loot = _int(nation.get("nation_loot_value"))
        if loot < minimum_loot:
            continue

        targets.append({
            **nation,
            "alliance_id": alliance_id,
            "alliance_position": position,
            "beige_turns": beige_turns,
            "def_slots": def_slots,
            "days_inactive": days_inactive,
            "nation_loot_value": loot,
            "updated_at": _int(nation.get("_created_at") or fallback_written_at, 0) or None,
        })
    return targets


def raid_win_rates(attacker: dict[str, Any], target: dict[str, Any]) -> tuple[float, float, float]:
    """Per-roll ground, air and naval win chances of ``attacker`` against ``target``."""
    ground = military_logic.calculate_win_chance_raw(
        _num(attacker.get("soldiers")) * 1.75 + _num(attacker.get("tanks")) * 40,
        _num(target.get("soldiers")) * 1.75
        + _num(target.get("tanks")) * 40
        + _num(target.get("population")) * 0.0025,
    )
    air = military_logic.calculate_win_chance_raw(
        _num(attacker.get("aircraft")) * 3, _num(target.get("aircraft")) * 3
    )
    naval = military_logic.calculate_win_chance_raw(
        _num(attacker.get("ships")) * 4, _num(target.get("ships")) * 4
    )
    return ground, air, naval


def is_bad_raid_target(target: dict[str, Any]) -> bool:
    """The /raids performance filter: a stronger ground force, little income or no loot."""
    return (
        target["groundwin"] < 0.4
        or target["nation_loot_value"] <= 0
        or _num(target.get("net_cash_num")) < 10000
    )


def _infra_stats(cities: Any) -> Optional[tuple[float, float]]:
    values = [_num(city.get("infrastructure")) for city in cities or [] if isinstance(city, dict)]
    if not values:
        return None
    return max(values), sum(values) / len(values)


def _alliance_link(target: dict[str, Any], alliances_by_id: dict[str, dict[str, Any]]) -> Optional[str]:
    alliance_id = target["alliance_id"]
    if alliance_id == "0":
        return None
    own = target.get("alliance") if isinstance(target.get("alliance"), dict) else {}
    name = (alliances_by_id.get(alliance_id) or {}).get("name") or own.get("name") or f"Alliance {alliance_id}"
    return f"[{name}](https://politicsandwar.com/alliance/id={alliance_id})"


def _at_war_with(user_nation: dict[str, Any], nation_id: str) -> bool:
    """Whether the user is in, or recently ended, a war with ``nation_id``."""
    for war in user_nation.get("wars") or []:
        if not isinstance(war, dict):
            continue
        sides = {str(_war_field(war, "attid", "att_id")), str(_war_field(war, "defid", "def_id"))}
        if nation_id in sides and war_turns_left(war) > -12:
            return True
    return False


def rank_nuke_targets(
    user_nation: dict[str, Any],
    nations: list[dict[str, Any]],
    *,
    alliance_ids: set[str],
    include_beige: bool,
    include_slotted: bool,
    sort_key: str,
    now: datetime,
    fallback_written_at: Any,
) -> list[dict[str, Any]]:
    """/nuketargets rows with the website's per-launch damage (logic/nuke_targets.py).

    The user's own nation and alliance are left out.
    """
    user_id = str(user_nation.get("id"))
    own_alliance = str(
        user_nation.get("alliance_id") or (user_nation.get("alliance") or {}).get("id") or "0"
    )
    ranked: list[dict[str, Any]] = []
    for nation in nations:
        nation_id = str(nation.get("id"))
        if nation_id == user_id:
            continue
        nation_alliance = str(nation.get("alliance_id") or "0")
        if own_alliance != "0" and nation_alliance == own_alliance:
            continue
        if alliance_ids and nation_alliance not in alliance_ids:
            continue
        beige_turns, vm_turns = current_turn_counts(nation, now, fallback_written_at)
        if is_in_vacation_mode({"vmode": nation.get("vmode"), "vacation_mode_turns": vm_turns}):
            continue
        if not include_beige and (beige_turns > 0 or (nation.get("beige_turns") is None and nation.get("color") == "beige")):
            continue
        if not include_slotted and (_int(nation.get("def_slots")) >= 3 or _at_war_with(user_nation, nation_id)):
            continue
        metrics = compute_nuke_missile_metrics(user_nation, nation)
        if metrics is None:
            continue
        ranked.append({
            "id": nation_id,
            "nation_name": nation.get("nation_name") or f"Nation {nation_id}",
            "alliance_id": str(nation.get("alliance_id") or "0"),
            "alliance": nation.get("alliance") if isinstance(nation.get("alliance"), dict) else None,
            "alliance_position": normalize_alliance_position(nation.get("alliance_position")),
            "nuke_damage": metrics.nuke_damage,
            "missile_damage": metrics.missile_damage,
            "max_infra": metrics.max_infra,
            "avg_infra": metrics.avg_infra,
            "vds": metrics.vds,
            "iron_dome": metrics.iron_dome,
        })
    ranked.sort(key=lambda row: row[sort_key], reverse=True)
    return ranked


def add_fields_within_limit(embed: discord.Embed, fields: list[tuple[str, str, bool]], *, noun: str) -> None:
    """Add ``(name, value, inline)`` fields while the embed stays under Discord's size limit."""
    for index, (name, value, inline) in enumerate(fields):
        if len(embed) + len(name) + len(value) > _EMBED_CHAR_BUDGET:
            left = sum(1 for field_name, _, _ in fields[index:] if field_name != "​")
            if left:
                embed.add_field(
                    name=f"{left} more {noun} not shown",
                    value="Discord limits how much one message can hold.",
                    inline=False,
                )
            return
        embed.add_field(name=name, value=value, inline=inline)


class TargetFinding(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _handle_command_exception(
        self,
        ctx: discord.ApplicationContext,
        error: Exception,
        *,
        command_name: str,
    ) -> None:
        await err_util.handle_command_exception(
            self.bot,
            ctx,
            error,
            logger,
            command_name=command_name,
            message="I couldn't complete that military command. Please try again.",
        )

    async def _fetch_reminder_embed_nation(
        self, nation_id: int | str, *, minimal: bool = False
    ) -> Optional[dict]:
        if minimal:
            fields = "id nation_name leader_name flag alliance{name}"
        else:
            fields = (
                "id nation_name leader_name flag score num_cities color "
                "vacation_mode_turns beige_turns soldiers tanks aircraft ships missiles nukes "
                "alliance{name}"
            )
        query = f"{{nations(first:1 id:{nation_id}){{data{{{fields}}}}}}}"
        response = await api_client.call(query, api_key)
        nations = (((response or {}).get("data") or {}).get("nations") or {}).get("data") or []
        if not nations:
            return None
        return nations[0]

    def _build_beige_reminder_action_embed(self, nation: dict, *, action: str) -> discord.Embed:
        nation_id = nation.get("id", "unknown")
        nation_url = f"https://politicsandwar.com/nation/id={nation_id}"
        nation_name = nation.get("nation_name", f"Nation {nation_id}")
        leader_name = nation.get("leader_name", "Unknown")
        alliance = nation.get("alliance")
        if isinstance(alliance, dict):
            alliance_name = alliance.get("name") or "None"
        else:
            alliance_name = alliance or "None"

        if action == "deleted":
            embed = discord.Embed(
                title="Beige reminder removed",
                description=(
                    "That nation is no longer on your beige reminder list. "
                    "You won't get reminders when they leave beige or vacation mode.\n\n"
                    f"**Nation:** [{nation_name}]({nation_url}) (`{nation_id}`)\n"
                    f"**Leader:** {leader_name}\n"
                    f"**Alliance:** {alliance_name}\n\n"
                    f"[Open nation profile]({nation_url}) · "
                ),
                color=0xFF5100,
            )
            flag_url = nation.get("flag")
            if flag_url:
                embed.set_thumbnail(url=str(flag_url))
            embed.set_footer(text=with_support_footer())
            return embed

        embed = discord.Embed(
            title=nation_name,
            url=nation_url,
            description=(
                "Beige reminder **added**.\n"
                f"Leader: **{leader_name}**\n"
                f"Alliance: **{alliance_name}**\n"
                f"[Open nation profile]({nation_url})\n"
                f"[Declare war](https://politicsandwar.com/nation/war/declare/id={nation_id})"
            ),
            color=0xFF5100,
        )
        flag_url = nation.get("flag")
        if flag_url:
            embed.set_thumbnail(url=str(flag_url))

        beige_turns = int(nation.get("beige_turns") or 0)
        vm_turns = int(nation.get("vacation_mode_turns") or 0)
        turns = max(beige_turns, vm_turns)
        if turns > 0:
            exit_time = common.get_datetime_of_turns(turns)
            ts = round(exit_time.timestamp())
            lines: list[str] = []
            if beige_turns > 0:
                lines.append(f"Beige turns: **{beige_turns}**")
            if vm_turns > 0:
                lines.append(f"VM turns: **{vm_turns}**")
            if beige_turns > 0 and vm_turns > 0:
                lines.append(f"Exits beige/VM: <t:{ts}:f> (<t:{ts}:R>)")
            elif beige_turns > 0:
                lines.append(f"Exits beige: <t:{ts}:f> (<t:{ts}:R>)")
            else:
                lines.append(f"Exits VM: <t:{ts}:f> (<t:{ts}:R>)")
            status_value = "\n".join(lines)
        else:
            status_value = "No active beige/VM turns"
        embed.add_field(name="Status", value=status_value, inline=False)

        military = (
            f"Soldiers: **{int(nation.get('soldiers') or 0):,}**\n"
            f"Tanks: **{int(nation.get('tanks') or 0):,}**\n"
            f"Aircraft: **{int(nation.get('aircraft') or 0):,}**\n"
            f"Ships: **{int(nation.get('ships') or 0):,}**\n"
            f"Missiles: **{int(nation.get('missiles') or 0)}**\n"
            f"Nukes: **{int(nation.get('nukes') or 0)}**"
        )
        embed.add_field(name="Military", value=military, inline=True)

        nation_info = (
            f"Score: **{nation.get('score', 'Unknown')}**\n"
            f"Cities: **{nation.get('num_cities', 'Unknown')}**\n"
            f"Color: **{str(nation.get('color') or 'Unknown').capitalize()}**"
        )
        embed.add_field(name="Nation Info", value=nation_info, inline=True)
        embed.set_footer(text=with_support_footer())
        return embed

    def _raid_target_embed(
        self,
        target: dict[str, Any],
        *,
        description: str,
        alliances_by_id: dict[str, dict[str, Any]],
        cities: Any,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"{target.get('nation_name') or 'Nation ' + str(target['id'])}",
            url=f"https://politicsandwar.com/nation/id={target['id']}",
            description=description,
            color=0xff5100,
        )
        loot = target["nation_loot_value"]
        embed.add_field(name="Previous nation loot", value=f"${loot:,}" if loot > 0 else "None recorded")
        embed.add_field(name="Monetary Net Income", value=_money(target.get("monetary_net_num")))
        embed.add_field(name="Net Cash Income", value=_money(target.get("net_cash_num")))
        embed.add_field(name="Treasures", value=str(_int(target.get("treasure_count"))))
        embed.add_field(name="Slots", value=f"{target['def_slots']}/3 used slots")
        embed.add_field(name="Beige", value=f"{target['beige_turns']} turns")
        embed.add_field(name="Inactivity", value=f"{target['days_inactive']} days")
        alliance = _alliance_link(target, alliances_by_id)
        if alliance:
            position = target.get("alliance_position")
            if isinstance(position, str) and position:
                alliance += f"\n{position.capitalize()}"
            embed.add_field(name="Alliance", value=alliance)
        else:
            embed.add_field(name="Alliance", value="No alliance")
        infra = _infra_stats(cities)
        embed.add_field(
            name="Infra",
            value=f"Max: {infra[0]:,.0f}\nAvg: {infra[1]:,.0f}" if infra else "Unknown",
        )
        for label, key in (
            ("Soldiers", "soldiers"),
            ("Tanks", "tanks"),
            ("Aircraft", "aircraft"),
            ("Ships", "ships"),
            ("Nukes", "nukes"),
            ("Missiles", "missiles"),
        ):
            embed.add_field(name=label, value=f"{_int(target.get(key)):,} {key}")
        embed.add_field(name="Chance to get ground IT", value=f"{round(100 * target['groundwin'] ** 3)}%")
        embed.add_field(name="Chance to get air IT", value=f"{round(100 * target['airwin'] ** 3)}%")
        embed.add_field(name="Chance to get naval IT", value=f"{round(100 * target['navalwin'] ** 3)}%\n​")
        return embed

    @slash_command(
        name="raids",
        description="Find profitable raid targets in your war range",
    )
    async def raids(
        self,
        ctx: discord.ApplicationContext,
        score: Option(float, "Set a custom score range.") = None
        ):
        loading: LoadingDisplay | None = None
        try:
            try:
                await ctx.defer()
            except discord.NotFound:
                # Interaction already expired before we could acknowledge it.
                logger.warning("Skipping /raids: interaction expired before defer.")
                return

            use_same = False
            webpage = None
            discord_embed = None
            who = None
            max_wars = None
            inactive_limit = None
            beige = None
            minimum_beige_loot = 0
            performance_filter = None

            embed1 = discord.Embed(title=f"Configuration", description="Do you want to use the same configuration (presenatation & filters) that you used last time running this command?", color=0xff5100)
            embed2 = discord.Embed(title=f"Presentation", description="How do you want to get your targets?\n\nEmbed on discord returns a paginated embed with some information about each nation. Use this if you can't use the webpage for whatever reason.\n\nMessage on discord returns a small list of the nations with the highest recent beige loot. Use this if you are very lazy.\n\nAs a webpage returns a link to a webpage with a sortable table that has lots of important information about each nation. If used well, this gives you the best targets.", color=0xff5100)
            embed3 = discord.Embed(title=f"Filters (1/6)", description="What nations do you want to include?", color=0xff5100)
            embed4 = discord.Embed(title=f"Filters (2/6)", description="How many active defensive wars should they have?", color=0xff5100)
            embed5 = discord.Embed(title=f"Filters (3/6)", description="How inactive should they be?", color=0xff5100)
            embed6 = discord.Embed(title=f"Filters (4/6)", description="Do you want to include beige nations?", color=0xff5100)
            embed7 = discord.Embed(title=f"Filters (5/6)", description="Should there be a minimum previous beige loot?", color=0xff5100)
            embed8 = discord.Embed(title=f"Filters (6/6)", description='Do you want to improve performance by filtering out "bad" targets?\n\nMore specifically, this will omit nations with negative income, nations that have a stronger ground force than you, and nations with no recorded beige loot.', color=0xff5100)

            db = db_mongo.get_db()
            user = await db.global_users.find_one({"user": ctx.author.id})
            saved_raids_cfg = user.get("raids_config") if user else None

            async def _ask_choice(
                embed: discord.Embed,
                choices: list[tuple[str, str, discord.ButtonStyle]],
                *,
                disable_on_submit: bool = False,
            ) -> str | None:
                view, session_id = await views.create_persistent_choice_prompt(
                    command="raids",
                    ctx=ctx,
                    choices=choices,
                    disable_on_submit=disable_on_submit,
                )
                await ctx.edit(content="", embed=embed, view=view)
                return await views.wait_for_persistent_choice_result(session_id)

            if isinstance(saved_raids_cfg, dict) and "webpage" in saved_raids_cfg:
                same_result = await _ask_choice(
                    embed1,
                    [
                        ("yes", "Yes", discord.ButtonStyle.success),
                        ("no", "No", discord.ButtonStyle.danger),
                    ],
                    disable_on_submit=True,
                )
                if same_result is None:
                    return
                use_same = same_result == "yes"

            if use_same:
                cfg = saved_raids_cfg
                webpage = bool(cfg.get("webpage"))
                discord_embed = bool(cfg.get("discord_embed"))
                who = cfg.get("who") or WHO_ALL
                max_wars = _int(cfg.get("max_wars"), 3)
                inactive_limit = _int(cfg.get("inactive_limit"))
                beige = bool(cfg.get("beige", True))
                performance_filter = bool(cfg.get("performace_filter"))
                minimum_beige_loot = _int(cfg.get("minimum_beige_loot"))
            else:
                presentation = await _ask_choice(
                    embed2,
                    [
                        ("embed", "Embed on discord", discord.ButtonStyle.primary),
                        ("message", "Message on discord", discord.ButtonStyle.primary),
                        ("web", "As a webpage (recommended)", discord.ButtonStyle.primary),
                    ],
                )
                if presentation is None:
                    return
                webpage = presentation == "web"
                discord_embed = presentation == "embed"

                # The Discord modes need the user's nation: say so before the filters.
                if not webpage and not await helpers.find_nation_plus(self.bot, ctx.author.id, guild=ctx.guild):
                    await ctx.edit(content=_RAIDS_NOT_VERIFIED_MESSAGE, embed=None, view=None)
                    return

                if webpage:
                    # Webpage mode should return the link immediately without the filter wizard.
                    who = WHO_ALL
                    max_wars = 3
                    inactive_limit = 0
                    beige = True
                    minimum_beige_loot = 0
                    performance_filter = False
                else:
                    who_result = await _ask_choice(
                        embed3,
                        [
                            ("all", "All nations", discord.ButtonStyle.primary),
                            ("apps", "Applicants and nations not in alliances", discord.ButtonStyle.primary),
                            ("none", "Nations not affiliated with any alliance", discord.ButtonStyle.primary),
                        ],
                    )
                    if who_result is None:
                        return
                    who = {"all": WHO_ALL, "apps": WHO_APPLICANTS, "none": WHO_NO_ALLIANCE}[who_result]

                    wars_result = await _ask_choice(
                        embed4,
                        [
                            ("w0", "0", discord.ButtonStyle.primary),
                            ("w1", "1 or less", discord.ButtonStyle.primary),
                            ("w2", "2 or less", discord.ButtonStyle.primary),
                            ("w3", "3 or less", discord.ButtonStyle.primary),
                        ],
                    )
                    if wars_result is None:
                        return
                    max_wars = {"w0": 0, "w1": 1, "w2": 2, "w3": 3}[wars_result]

                    inactive_result = await _ask_choice(
                        embed5,
                        [
                            ("i0", "I don't care", discord.ButtonStyle.primary),
                            ("i7", "7+ days inactive", discord.ButtonStyle.primary),
                            ("i14", "14+ days inactive", discord.ButtonStyle.primary),
                            ("i30", "30+ days inactive", discord.ButtonStyle.primary),
                        ],
                    )
                    if inactive_result is None:
                        return
                    inactive_limit = {"i0": 0, "i7": 7, "i14": 14, "i30": 30}[inactive_result]

                    beige_result = await _ask_choice(
                        embed6,
                        [
                            ("yes", "Yes", discord.ButtonStyle.success),
                            ("no", "No", discord.ButtonStyle.danger),
                        ],
                    )
                    if beige_result is None:
                        return
                    beige = beige_result == "yes"

                    loot_result = await _ask_choice(
                        embed7,
                        [
                            ("l0", "No minimum", discord.ButtonStyle.primary),
                            ("l5", "$5 million", discord.ButtonStyle.primary),
                            ("l10", "$10 million", discord.ButtonStyle.primary),
                            ("l20", "$20 million", discord.ButtonStyle.primary),
                        ],
                    )
                    if loot_result is None:
                        return
                    minimum_beige_loot = {"l0": 0, "l5": 5000000, "l10": 10000000, "l20": 20000000}[loot_result]

                    perf_result = await _ask_choice(
                        embed8,
                        [
                            ("yes", "Yes", discord.ButtonStyle.success),
                            ("no", "No", discord.ButtonStyle.danger),
                        ],
                        disable_on_submit=True,
                    )
                    if perf_result is None:
                        return
                    performance_filter = perf_result == "yes"
                    # Give immediate feedback right after the final wizard click.
                    loading = LoadingDisplay(ctx, show_after=0)
                    await loading.start("Filters saved. Loading targets now... this can take a little while.")

            if not webpage and loading is None:
                loading = LoadingDisplay(ctx, show_after=0)
                await loading.start("Loading targets now... this can take a little while.")

            dnr_alliance_ids: list[str] = []
            if ctx.guild:
                guild_config = await db.guild_configs.find_one({"guild_id": ctx.guild.id}) or {}
                dnr_alliance_ids = [str(x) for x in guild_config.get("dnr_alliance_ids") or []]

            await db.global_users.find_one_and_update(
                {"user": ctx.author.id},
                {
                    "$set": {
                        "raids_config": {
                            "webpage": webpage,
                            "discord_embed": discord_embed,
                            "who": who,
                            "max_wars": max_wars,
                            "inactive_limit": inactive_limit,
                            "beige": beige,
                            "performace_filter": performance_filter,
                            "minimum_beige_loot": minimum_beige_loot,
                        }
                    }
                },
            )

            if webpage:
                raids_url = f"{WEB_BASE_URL}/raids"

                webpage_embed = discord.Embed(
                    title="Open Raid Targets",
                    description=(
                        "Open Raid Targets in your browser. "
                        "Use Login with Discord on the website to enable reminders."
                    ),
                    color=0xff5100,
                )
                view = discord.ui.View(
                    discord.ui.Button(
                        label="Open Raid Targets",
                        style=discord.ButtonStyle.link,
                        url=raids_url,
                    ),
                    timeout=None,
                )
                await ctx.edit(content="", attachments=[], embed=webpage_embed, view=view)
                return

            attacker = await helpers.find_nation_plus(self.bot, ctx.author.id, guild=ctx.guild)
            if not attacker:
                await loading.clear()
                await ctx.edit(content=_RAIDS_NOT_VERIFIED_MESSAGE, embed=None, attachments=[])
                return
            # Prefer cached nation data from SQLite to avoid extra P&W API latency.
            atck_ntn = attacker
            required_attacker_fields = ("id", "nation_name", "score", "population", "soldiers", "tanks", "aircraft", "ships")
            if any(atck_ntn.get(field) is None for field in required_attacker_fields):
                attacker_res = await api_client.call(
                    f"{{nations(first:1 id:{attacker['id']}){{data{{id nation_name score population soldiers tanks aircraft ships}}}}}}",
                    api_key,
                )
                attacker_data = (((attacker_res or {}).get("data") or {}).get("nations") or {}).get("data") or []
                atck_ntn = attacker_data[0] if attacker_data else None
                if atck_ntn is None:
                    await loading.clear()
                    await ctx.edit(content='I did not find that person!', embed=None, attachments=[])
                    return

            minscore, maxscore = military_logic.war_range_query_bounds(score if score else _num(atck_ntn.get("score")))

            file_content = None
            last_load_exception = None
            for i in range(3):
                try:
                    file_content = await asyncio.to_thread(
                        get_all_nations_filtered,
                        get_nations_db_path(),
                        min_score=minscore,
                        max_score=maxscore,
                        columns=_RAID_COLUMNS,
                        json_fields={"alliance"},
                    )
                    break
                except Exception as e:
                    logger.debug(f"Attempt {i + 1} to load nations failed: {e}")
                    last_load_exception = e
            last_fetched = (file_content or {}).get("last_fetched")

            if not last_fetched or file_content is None:
                ref = err_util.new_error_reference()
                logger.info(
                    "raids_nations_db_unready reference=%r user_id=%s",
                    ref,
                    ctx.author.id,
                    extra={"error_reference": ref},
                )
                if last_load_exception is not None:
                    await err_util.report_handled_exception(
                        self.bot,
                        ctx,
                        last_load_exception,
                        logger,
                        reference=ref,
                        command_name="raids",
                    )
                embed = err_util.error_embed(
                    "Nations data not ready",
                    "I couldn't load nations yet. The scanner may still be filling the database. "
                    "Please wait—this can take on the order of half an hour—then try again. "
                    "If this keeps happening for hours, contact randomnoobster with the reference below.",
                    reference=ref,
                )
                await loading.clear()
                await ctx.followup.send(embed=embed)
                return

            await loading.update("Getting targets...")
            now = datetime.now(timezone.utc)
            target_list = select_raid_targets(
                file_content["nations"],
                who=who,
                max_wars=max_wars,
                inactive_limit=inactive_limit,
                include_beige=beige,
                minimum_loot=minimum_beige_loot,
                excluded_alliances=set(_EXCLUDED_RAID_ALLIANCES) | set(dnr_alliance_ids),
                now=now,
                fallback_written_at=last_fetched,
                attacker_id=str(atck_ntn.get("id")),
                attacker_alliance_id=str(attacker.get("alliance_id") or "0"),
            )
            for target in target_list:
                target["groundwin"], target["airwin"], target["navalwin"] = raid_win_rates(atck_ntn, target)
            if performance_filter:
                target_list = [target for target in target_list if not is_bad_raid_target(target)]

            if len(target_list) == 0:
                await loading.clear()
                await ctx.edit(content="No targets matched your criteria!", embed=None, attachments=[])
                return

            filter_list = []
            if not beige:
                filter_list.append("hide beige nations")
            if who == WHO_APPLICANTS:
                filter_list.append("hide full alliance members")
            elif who == WHO_NO_ALLIANCE:
                filter_list.append("hide full alliance members and applicants")
            if max_wars != 3:
                filter_list.append("0 active wars" if max_wars == 0 else f"{max_wars} or less active wars")
            if performance_filter:
                filter_list.append('omit "bad" targets')
            if inactive_limit != 0:
                filter_list.append(f"hide nations that logged in within the last {inactive_limit} days")
            if minimum_beige_loot != 0:
                filter_list.append(f"hide nations with less than ${minimum_beige_loot:,} previous beige loot".replace(",000,000","m"))
            if dnr_alliance_ids:
                filter_list.append(f"hide {len(dnr_alliance_ids)} alliances marked as do not raid")
            filters = ("Active filters: " + ", ".join(filter_list)) if filter_list else "No active filters"

            await loading.update("Calculating best targets...")

            if discord_embed:
                best_targets = sorted(target_list, key=lambda k: _num(k.get("monetary_net_num")), reverse=True)
                shown = best_targets[:MAX_RAID_PAGES]
                shown_ids = [target["id"] for target in shown]
                cities_by_id = await asyncio.to_thread(
                    get_nations_by_ids, get_nations_db_path(), shown_ids, ["cities"], {"cities"}
                )
                alliance_rows = await asyncio.to_thread(
                    get_alliances_by_ids, [target["alliance_id"] for target in shown]
                )
                alliances_by_id = {str(row["id"]): row for row in alliance_rows}
                pages = len(shown)
                capped_note = (
                    f"  |  Best {pages} of {len(best_targets)} targets by income" if len(best_targets) > pages else ""
                )
                embeds = []
                for idx, target in enumerate(shown, start=1):
                    updated_at = target.get("updated_at") or _int(last_fetched, 0) or None
                    cache_line = (
                        f"Nation information fetched <t:{updated_at}:R>"
                        if updated_at
                        else "Nation information fetched (unknown)"
                    )
                    embed = self._raid_target_embed(
                        target,
                        description=f"{cache_line}\n{filters}\n​",
                        alliances_by_id=alliances_by_id,
                        cities=(cities_by_id.get(_int(target["id"])) or {}).get("cities"),
                    )
                    embed.set_footer(text=with_support_footer(f"Page {idx}/{pages}{capped_note}"))
                    embeds.append(embed)

                view, session_id, active_embed = await views.create_persistent_raids_pager_prompt(
                    ctx=ctx,
                    embeds=embeds,
                    target_ids=[str(target["id"]) for target in shown],
                    beige_turns=[target["beige_turns"] for target in shown],
                    ttl_seconds=3600,
                )
                await loading.clear()
                await ctx.edit(content="", embed=active_embed, attachments=[], view=view)

            else:
                targets = sorted(target_list, key=lambda k: k["nation_loot_value"], reverse=True)
                desc = filters
                for target in targets[:MESSAGE_MODE_TARGETS]:
                    loot = target["nation_loot_value"]
                    loot_text = f"${loot:,}" if loot > 0 else "none recorded"
                    updated_at = target.get("updated_at") or _int(last_fetched, 0) or None
                    cache_age = f"<t:{updated_at}:R>" if updated_at else "unknown"
                    active_at = parse_war_date(target.get("last_active"))
                    active = f"<t:{round(active_at.timestamp())}:R>" if active_at.year > 1970 else "unknown"
                    line = (
                        f"\n\n**Last beige: {loot_text}**\n"
                        f"[{target.get('nation_name')}](https://politicsandwar.com/nation/id={target['id']}) | "
                        f"Active: {active} | Updated: {cache_age} | Ground IT: {round(100 * target['groundwin'] ** 3)}%"
                    )
                    if len(desc) + len(line) > _MAX_DESCRIPTION_CHARS:
                        break
                    desc += line
                embed = discord.Embed(title="Top nations by beige loot", description=desc, color=0xff5100)
                embed.set_footer(text=with_support_footer())
                await loading.clear()
                await ctx.edit(content="", embed=embed, attachments=[], view=None)

        except Exception as e:
            if loading is not None:
                await loading.clear()
            await self._handle_command_exception(ctx, e, command_name="raids")
            return

    reminder_group = SlashCommandGroup("reminders", "Manage beige exit reminder notifications")

    @reminder_group.command(
        name="show",
        description="View all your active beige exit reminders",
    )
    async def reminders(self, ctx: discord.ApplicationContext):
        try:
            # Private, like the website: the list shows who the user plans to hit.
            await ctx.defer(ephemeral=True)
            profile = await reminder_db.get_profile(db, ctx.author.id) or {}
            nation_ids = reminder_db.watched_nation_ids(profile)
            reminders_url = f"{WEB_BASE_URL}/reminders"

            if not nation_ids:
                embed = discord.Embed(
                    title="No beige reminders",
                    description=(
                        "You do not have any beige exit reminders yet.\n\n"
                        f"Add some with **`/reminders add`** or on the "
                        f"[Reminders webpage]({reminders_url})."
                    ),
                    color=0xFF5100,
                )
                embed.set_footer(text=with_support_footer())
                await ctx.respond(embed=embed)
                return

            schedule: dict[str, tuple[datetime, datetime]] = {}
            for job in await reminder_db.active_jobs_for_user(db, ctx.author.id):
                job_nation = str(job.get("nation_id"))
                due_at = reminder_rules.ensure_utc(job["due_at"])
                if job_nation not in schedule or due_at < schedule[job_nation][0]:
                    schedule[job_nation] = (due_at, reminder_rules.ensure_utc(job["exit_at"]))

            names = await asyncio.to_thread(
                get_nations_by_ids, get_nations_db_path(), nation_ids, ["nation_name"]
            )
            scheduler = getattr(self.bot, "reminder_scheduler", None)
            far_future = datetime.max.replace(tzinfo=timezone.utc)
            rows: list[tuple[datetime, str]] = []
            for nation_id in nation_ids:
                name = (names.get(_int(nation_id)) or {}).get("nation_name") or f"Nation {nation_id}"
                link = f"[{name}](https://politicsandwar.com/nation/id={nation_id})"
                due_at, exit_at = schedule.get(nation_id, (None, None))
                if exit_at is None and scheduler is not None:
                    tracked = scheduler.tracked_status(nation_id)
                    if tracked is not None and tracked.estimate.exit_at is not None:
                        exit_at = tracked.estimate.exit_at
                if exit_at is None:
                    rows.append((far_future, f"\nScheduling... - {link}"))
                    continue
                stamp = reminder_rules.to_epoch(exit_at)
                line = f"\n<t:{stamp}:f> <t:{stamp}:R> - {link}"
                if due_at is not None:
                    line += f" · next reminder <t:{reminder_rules.to_epoch(due_at)}:R>"
                rows.append((exit_at, line))
            rows.sort(key=lambda row: row[0])
            lines = [line for _, line in rows]

            channels = reminder_rules.ChannelSettings.from_doc(profile.get("reminder_channels"))
            delivery = " and ".join(
                label
                for label, enabled in (
                    ("Discord DM", channels.discord_dm),
                    ("browser notifications", channels.web_push),
                )
                if enabled
            )
            dm_failing = (
                channels.discord_dm
                and (profile.get("dm_delivery") or {}).get("state") == reminder_rules.DM_STATE_FAILED
            )

            embeds = []
            for n in range(0, len(lines), 20):
                embed = discord.Embed(title="Beige reminders", description="".join(lines[n:n+20]), color=0xff5100)
                if dm_failing:
                    embed.add_field(
                        name="Reminder DMs aren't reaching you",
                        value=f"Open the [Reminders page]({reminders_url}) for the steps to fix it.",
                        inline=False,
                    )
                embed.set_footer(text=with_support_footer(f"Delivered by {delivery}"))
                embeds.append(embed)

            if len(embeds) > 1:
                view = views.Switch(ctx=ctx, embeds=embeds, max_page=len(embeds))
            else:
                view = None

            await ctx.respond(embed=embeds[0])
            if view is not None:
                await ctx.edit(view=view)

        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="reminders show")
            return

    @reminder_group.command(
        name="delete",
        description="Remove a beige reminder for a specific nation",
    )
    async def delreminder(
        self,
        ctx: discord.ApplicationContext,
        nation: Option(str, "Nation name, nation link, discord username etc of the nation whose beige reminder you want to remove")
    ):
        try:
            await ctx.defer(ephemeral=True)
            parsed_nation = await asyncio.to_thread(sqlite_find_nation, nation)
            if parsed_nation is None:
                await ctx.respond("I could not find that nation!")
                return
            nation_id = str(parsed_nation["id"])

            removed = await reminder_service.remove_reminder(db, ctx.author.id, nation_id)
            if not removed:
                await ctx.respond(content="I did not find a reminder for that nation!")
                return

            nation_for_embed = await self._fetch_reminder_embed_nation(nation_id, minimal=True)
            embed = self._build_beige_reminder_action_embed(
                nation_for_embed or parsed_nation,
                action="deleted",
            )
            await ctx.respond(embed=embed)

        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="reminders delete")
            return

    @reminder_group.command(
        name="add",
        description="Get notified when a nation exits beige or VM",
    )
    async def addreminder(
        self,
        ctx: discord.ApplicationContext,
        nation: Option(str, "Nation name, nation link, discord username etc of the nation you want to add a beige reminder for")
    ):
        try:
            await ctx.defer(ephemeral=True)
            nation = await asyncio.to_thread(sqlite_find_nation, nation)

            if nation is None:
                await ctx.respond(content='I could not find that nation!')
                return

            res = await self._fetch_reminder_embed_nation(nation["id"])
            if not res:
                await ctx.respond(content="I could not load that nation right now. Please try again.")
                return

            if res['beige_turns'] == 0 and res['vacation_mode_turns'] == 0:
                await ctx.respond(content="They are not in beige or vacation mode!")
                return

            result = await reminder_service.add_reminder(db, ctx.author.id, str(nation['id']))
            if not result.added:
                await ctx.respond(content="You already have a beige reminder for this nation!")
                return

            embed = self._build_beige_reminder_action_embed(res, action="added")
            if result.test_dm is not None:
                embed.add_field(
                    name="Checking that reminders reach you",
                    value="I'm sending you a test DM. Press **Got it** in it so we know you can see reminders.",
                    inline=False,
                )
            await ctx.respond(embed=embed)

        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="reminders add")
            return

    async def _resolve_nation_pair(
        self,
        ctx: discord.ApplicationContext,
        nation1: Optional[str],
        nation2: Optional[str],
    ) -> Optional[tuple[str, str]]:
        """Nation ids for a two-nation command, or None after telling the user.

        A missing nation defaults to the user's own, or, in a war thread, to the
        thread's nation.
        """
        if nation1 is None and nation2:
            nation1, nation2 = nation2, None

        nation1_nation = await helpers.find_nation_plus(
            self.bot, nation1 if nation1 is not None else ctx.author.id, guild=ctx.guild
        )
        if not nation1_nation:
            await ctx.respond(content='I could not find that nation!' if nation2 is None else 'I could not find nation 1!')
            return None
        nation1_id = str(nation1_nation['id'])

        if nation2 is None:
            thread_id = thread_nation_id(ctx.channel)
            if thread_id is not None:
                return nation1_id, thread_id
            own = await helpers.find_nation_plus(self.bot, ctx.author.id, guild=ctx.guild)
            if not own:
                await ctx.respond(content='I was able to find the nation you linked, but I could not find *your* nation!')
                return None
            return nation1_id, str(own['id'])

        nation2_nation = await helpers.find_nation_plus(self.bot, nation2, guild=ctx.guild)
        if not nation2_nation:
            await ctx.respond(content='I could not find nation 2!')
            return None
        return nation1_id, str(nation2_nation['id'])

    @slash_command(
        name="battlesimulation",
        description="Simulate ground, air, and naval battles between two nations",
    )
    async def battlesim(
        self,
        ctx: discord.ApplicationContext,
        nation1: Option(str, "Nation name, leader name, nation id, nation link or discord username. Defaults to your nation.") = None,
        nation2: Option(str, "Nation name, leader name, nation id, nation link or discord username. Defaults to your nation.") = None
    ):
        try:
            await ctx.defer()
            pair = await self._resolve_nation_pair(ctx, nation1, nation2)
            if pair is None:
                return
            nation1_id, nation2_id = pair

            results = await self.battle_calc(nation1_id, nation2_id)

            embed = discord.Embed(title="Battle Simulator", description=f"These are the results for when [{results['nation1']['nation_name']}](https://politicsandwar.com/nation/id={results['nation1']['id']}){results['nation1_append']} attacks [{results['nation2']['nation_name']}](https://politicsandwar.com/nation/id={results['nation2']['id']}){results['nation2_append']}\nIf you want to use custom troop counts, you can use the [in-game battle simulators](https://politicsandwar.com/tools/)", color=0xff5100)
            embed1 = discord.Embed(title="Battle Simulator", description=f"These are the results for when [{results['nation2']['nation_name']}](https://politicsandwar.com/nation/id={results['nation2']['id']}){results['nation2_append']} attacks [{results['nation1']['nation_name']}](https://politicsandwar.com/nation/id={results['nation1']['id']}){results['nation1_append']}\nIf you want to use custom troop counts, you can use the [in-game battle simulators](https://politicsandwar.com/tools/)", color=0xff5100)

            if results['nation2']['soldiers'] + results['nation2']['tanks'] + results['nation1']['soldiers'] + results['nation1']['tanks'] == 0:
                embed.add_field(name="Ground Attack", value="Nobody has any forces!")
                embed1.add_field(name="Ground Attack", value="Nobody has any forces!")
            else:
                embed.add_field(name="Ground Attack", value=f"Immense Triumph: {round(results['nation1_ground_it']*100)}%\nModerate Success: {round(results['nation1_ground_mod']*100)}%\nPyrrhic Victory: {round(results['nation1_ground_pyr']*100)}%\nUtter Failure: {round(results['nation1_ground_fail']*100)}%")
                embed1.add_field(name="Ground Attack", value=f"Immense Triumph: {round(results['nation2_ground_it']*100)}%\nModerate Success: {round(results['nation2_ground_mod']*100)}%\nPyrrhic Victory: {round(results['nation2_ground_pyr']*100)}%\nUtter Failure: {round(results['nation2_ground_fail']*100)}%")

            if results['nation2']['aircraft'] + results['nation1']['aircraft'] != 0:
                embed.add_field(name="Airstrike", value=f"Immense Triumph: {round(results['nation1_air_it']*100)}%\nModerate Success: {round(results['nation1_air_mod']*100)}%\nPyrrhic Victory: {round(results['nation1_air_pyr']*100)}%\nUtter Failure: {round(results['nation1_air_fail']*100)}%")
                embed1.add_field(name="Airstrike", value=f"Immense Triumph: {round(results['nation1_air_fail']*100)}%\nModerate Success: {round(results['nation1_air_pyr']*100)}%\nPyrrhic Victory: {round(results['nation1_air_mod']*100)}%\nUtter Failure: {round(results['nation1_air_it']*100)}%")
            else:
                embed.add_field(name="Airstrike", value="Nobody has any forces!")
                embed1.add_field(name="Airstrike", value="Nobody has any forces!")

            if results['nation2']['ships'] + results['nation1']['ships'] != 0:
                embed.add_field(name="Naval Battle", value=f"Immense Triumph: {round(results['nation1_naval_it']*100)}%\nModerate Success: {round(results['nation1_naval_mod']*100)}%\nPyrrhic Victory: {round(results['nation1_naval_pyr']*100)}%\nUtter Failure: {round(results['nation1_naval_fail']*100)}%")
                embed1.add_field(name="Naval Battle", value=f"Immense Triumph: {round(results['nation1_naval_fail']*100)}%\nModerate Success: {round(results['nation1_naval_pyr']*100)}%\nPyrrhic Victory: {round(results['nation1_naval_mod']*100)}%\nUtter Failure: {round(results['nation1_naval_it']*100)}%")

            else:
                embed.add_field(name="Naval Battle", value="Nobody has any forces!")
                embed1.add_field(name="Naval Battle", value="Nobody has any forces!")

            embed.add_field(name="Casualties", value=f"Att. Sol.: {results['nation1_ground_nation1_avg_soldiers']:,} ± {results['nation1_ground_nation1_diff_soldiers']:,}\nAtt. Tnk.: {results['nation1_ground_nation1_avg_tanks']:,} ± {results['nation1_ground_nation1_diff_tanks']:,}\n\nDef. Sol.: {results['nation1_ground_nation2_avg_soldiers']:,} ± {results['nation1_ground_nation2_diff_soldiers']:,}\nDef. Tnk.: {results['nation1_ground_nation2_avg_tanks']:,} ± {results['nation1_ground_nation2_diff_tanks']:,}\n\n{results['nation2']['aircas']}")
            embed1.add_field(name="Casualties", value=f"Att. Sol.: {results['nation2_ground_nation2_avg_soldiers']:,} ± {results['nation2_ground_nation2_diff_soldiers']:,}\nAtt. Tnk.: {results['nation2_ground_nation2_avg_tanks']:,} ± {results['nation2_ground_nation2_diff_tanks']:,}\n\nDef. Sol.: {results['nation2_ground_nation1_avg_soldiers']:,} ± {results['nation2_ground_nation1_diff_soldiers']:,}\nDef. Tnk.: {results['nation2_ground_nation1_avg_tanks']:,} ± {results['nation2_ground_nation1_diff_tanks']:,}\n\n{results['nation1']['aircas']}")

            embed.add_field(name="Casualties", value=f"*Targeting air:*\nAtt. Plane: {results['nation1_airvair_nation1_avg']:,} ± {results['nation1_airvair_nation1_diff']:,}\nDef. Plane: {results['nation1_airvair_nation2_avg']:,} ± {results['nation1_airvair_nation2_diff']:,}\n\n*Targeting other:*\nAtt. Plane: {results['nation1_airvother_nation1_avg']:,} ± {results['nation1_airvother_nation1_diff']:,}\nDef. Plane: {results['nation1_airvother_nation2_avg']:,} ± {results['nation1_airvother_nation2_diff']:,}\n​")
            embed1.add_field(name="Casualties", value=f"*Targeting air:*\nAtt. Plane: {results['nation2_airvair_nation2_avg']:,} ± {results['nation2_airvair_nation2_diff']:,}\nDef. Plane: {results['nation2_airvair_nation1_avg']:,} ± {results['nation2_airvair_nation1_diff']:,}\n\n*Targeting other:*\nAtt. Plane: {results['nation2_airvother_nation2_avg']:,} ± {results['nation2_airvother_nation2_diff']:,}\nDef. Plane: {results['nation2_airvother_nation1_avg']:,} ± {results['nation2_airvother_nation1_diff']:,}\n​")

            embed.add_field(name="Casualties", value=f"*Targeting other:*\nAtt. Ships: {results['nation1_navalvinfra_nation1_avg']:,} ± {results['nation1_navalvinfra_nation1_diff']:,}\nDef. Ships: {results['nation1_navalvinfra_nation2_avg']:,} ± {results['nation1_navalvinfra_nation2_diff']:,}\n\n*Targeting ships:*\nAtt. Ships: {results['nation1_navalvships_nation1_avg']:,} ± {results['nation1_navalvships_nation1_diff']:,}\nDef. Ships: {results['nation1_navalvships_nation2_avg']:,} ± {results['nation1_navalvships_nation2_diff']:,}")
            embed1.add_field(name="Casualties", value=f"*Targeting other:*\nAtt. Ships: {results['nation2_navalvinfra_nation2_avg']:,} ± {results['nation2_navalvinfra_nation2_diff']:,}\nDef. Ships: {results['nation2_navalvinfra_nation1_avg']:,} ± {results['nation2_navalvinfra_nation1_diff']:,}\n\n*Targeting ships:*\nAtt. Ships: {results['nation2_navalvships_nation2_avg']:,} ± {results['nation2_navalvships_nation2_diff']:,}\nDef. Ships: {results['nation2_navalvships_nation1_avg']:,} ± {results['nation2_navalvships_nation1_diff']:,}")

            # Build URL for the frontend damage page using live API
            nation1_id = results.get('nation1', {}).get('id', '')
            nation2_id = results.get('nation2', {}).get('id', '')
            url = f"{WEB_BASE_URL}/damage?nation1={nation1_id}&nation2={nation2_id}"
            view, _session_id, active_embed = await views.create_persistent_tabs_prompt(
                command="battlesimulation",
                ctx=ctx,
                tabs=[("Attacker", embed), ("Defender", embed1)],
                initial_index=0,
                ttl_seconds=3600,
                link_label="Damage sheet",
                link_url=url,
            )
            await ctx.respond(embed=active_embed, content="", view=view)
        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="battlesimulation")
            return


    @slash_command(
        name="war_status",
        description="Get a detailed overview of a nation's ongoing wars",
    )
    async def war_status(
        self,
        ctx: discord.ApplicationContext,
        nation: Option(str, "The person whose war status you'd like to see") = None
    ):
        try:
            await ctx.defer()
            if not nation:
                nation_id = thread_nation_id(ctx.channel)
                if nation_id is None:
                    person = await helpers.find_user(self.bot, ctx.author.id)
                    nation_id = helpers.linked_nation_id(person)
                    if nation_id is None:
                        await ctx.respond(helpers.NATION_NOT_LINKED_MESSAGE)
                        return
            else:
                person = await helpers.find_nation_plus(self.bot, nation, guild=ctx.guild)
                if not person:
                    await ctx.respond("I could not find that nation!")
                    return
                nation_id = str(person['id'])

            response = await api_client.call(f"{{nations(first:1 id:{nation_id}) {{data{get_query(queries.WAR_STATUS)}}}}}", api_key)
            found = (((response or {}).get("data") or {}).get("nations") or {}).get("data") or []
            if not found:
                await ctx.respond("I could not find that nation!")
                return
            nation = found[0]

            max_offense = military_logic.max_offensive_wars(nation)

            milt = military_logic.militarization_checker(nation)
            max_sol = milt['max_soldiers']
            max_tnk = milt['max_tanks']
            max_pln = milt['max_aircraft']
            max_shp = milt['max_ships']

            nation['offensive_wars'] = [y for y in nation['wars'] if y['turnsleft'] > 0 and y['attid'] == nation['id']]
            nation['defensive_wars'] = [y for y in nation['wars'] if y['turnsleft'] > 0 and y['defid'] == nation['id']]
            nation['wars'] = nation['offensive_wars'] + nation['defensive_wars']

            if nation['alliance']:
                alliance = f"[{nation['alliance']['name']}](https://politicsandwar.com/alliance/id={nation['alliance_id']})"
            else:
                alliance = "No alliance"

            desc = f"[{nation['nation_name']}](https://politicsandwar.com/nation/id={nation['id']}) | {alliance}\n\nLast login: <t:{round(parse_war_date(nation['last_active']).timestamp())}:R>\nOffensive wars: {len(nation['offensive_wars'])}/{max_offense}\nDefensive wars: {len(nation['defensive_wars'])}/3\nDefensive range: {round(nation['score'] / 2.5)} - {round(nation['score'] / 0.75)}\nCities: {nation['num_cities']}\nBeige (turns): {nation['beigeturns']}\n\nSoldiers: **{nation['soldiers']:,}** / {max_sol:,}\nTanks: **{nation['tanks']:,}** / {max_tnk:,}\nPlanes: **{nation['aircraft']:,}** / {max_pln:,}\nShips: **{nation['ships']:,}** / {max_shp:,}"
            embed = discord.Embed(title=f"{nation['nation_name']} ({nation['id']}) & their wars", description=desc, color=0xff5100)
            embed1 = discord.Embed(title=f"{nation['nation_name']} ({nation['id']}) & their wars", description=desc, color=0xff5100)
            embed2 = discord.Embed(title=f"{nation['nation_name']} ({nation['id']}) & their wars", description=desc, color=0xff5100)
            embed.set_footer(text=with_support_footer(f"The chance to get immense triumphs is if the nation attacks {nation['nation_name']}. On average, it's worth attacking if the % is above 13%. Use /battlesimulation for more detailed predictions."))
            embed1.set_footer(text=with_support_footer(f"The chance to get immense triumphs is if the nation attacks {nation['nation_name']}. On average, it's worth attacking if the % is above 13%. Use /battlesimulation for more detailed predictions."))
            embed2.set_footer(text=with_support_footer("These are the average net damage per MAP predictions for the nations in question. Negative numbers means the net damage would be negative (not good). Use /damage for more detailed predictions."))

            # One damage calculation per enemy, fetched together.
            enemies = [
                war['defender'] if war in nation['offensive_wars'] else war['attacker']
                for war in nation['wars']
            ]
            results = await asyncio.gather(
                *(self.battle_calc(nation1=nation, nation2_id=enemy['id']) for enemy in enemies)
            )

            general_fields: list[tuple[str, str, bool]] = []
            military_fields: list[tuple[str, str, bool]] = []
            damage_fields: list[tuple[str, str, bool]] = []
            for n, (war, x, result) in enumerate(zip(nation['wars'], enemies, results), start=2):
                spacer = ("​", "​", n % 2 != 0)
                general_fields.append(spacer)
                military_fields.append(spacer)
                damage_fields.append(spacer)

                if war in nation['offensive_wars']:
                    war_emoji_1 = "<:offensive_swords:1054714270547447828>"
                    war_emoji_2 = "<:defensive_shield:1054714196715110411>"
                    main_enemy_res = war['att_resistance']
                    main_enemy_points = war['attpoints']
                    their_enemy_points = war['defpoints']
                    their_enemy_res = war['def_resistance']
                else:
                    war_emoji_1 = "<:defensive_shield:1054714196715110411>"
                    war_emoji_2 = "<:offensive_swords:1054714270547447828>"
                    main_enemy_res = war['def_resistance']
                    main_enemy_points = war['defpoints']
                    their_enemy_points = war['attpoints']
                    their_enemy_res = war['att_resistance']

                main_enemy_bar = ""
                their_enemy_bar = ""
                for z in range(math.ceil(main_enemy_res / 10)):
                    if main_enemy_res > 66:
                        main_enemy_bar += "🟩"
                    elif main_enemy_res > 33:
                        main_enemy_bar += "🟨"
                    else:
                        main_enemy_bar += "🟥"
                while len(main_enemy_bar) < 10:
                    main_enemy_bar += "⬛"

                for z in range(math.ceil(their_enemy_res / 10)):
                    if their_enemy_res > 66:
                        their_enemy_bar += "🟩"
                    elif their_enemy_res > 33:
                        their_enemy_bar += "🟨"
                    else:
                        their_enemy_bar += "🟥"
                while len(their_enemy_bar) < 10:
                    their_enemy_bar += "⬛"

                x_max_offense = military_logic.max_offensive_wars(x)

                if x['beigeturns'] > 0:
                    beige = f"\nBeige (turns): {x['beigeturns']}"
                else:
                    beige = ""

                x_milt = military_logic.militarization_checker(x)
                x_max_sol = x_milt['max_soldiers']
                x_max_tnk = x_milt['max_tanks']
                x_max_pln = x_milt['max_aircraft']
                x_max_shp = x_milt['max_ships']

                if x['vmode'] > 0:
                    vmstart = "~~"
                    vmend = "~~"
                else:
                    vmstart = ""
                    vmend = ""

                x['offensive_wars'] = [y for y in x['wars'] if y['turnsleft'] > 0 and y['attid'] == x['id']]
                x['defensive_wars'] = [y for y in x['wars'] if y['turnsleft'] > 0 and y['defid'] == x['id']]

                if x['alliance']:
                    x_alliance = f"[{x['alliance']['name']}](https://politicsandwar.com/alliance/id={x['alliance_id']})"
                else:
                    x_alliance = "No alliance"

                name = f"{x['nation_name']} ({x['id']})"
                general_fields.append((name, f"{vmstart}[War timeline](https://politicsandwar.com/nation/war/timeline/war={war['id']}) | {x_alliance}\n\n{war_emoji_1} **[{nation['nation_name']}](https://politicsandwar.com/nation/id={nation['id']})**{result['nation1_append']}\n{main_enemy_bar}\n**{main_enemy_res}/100** | MAPs: **{main_enemy_points}/12**\n\n{war_emoji_2} **[{x['nation_name']}](https://politicsandwar.com/nation/id={x['id']})**{result['nation2_append']}\n{their_enemy_bar}\n**{their_enemy_res}/100** | MAPs: **{their_enemy_points}/12**\n\nExpiration (turns): {war['turnsleft']}\nLast login: <t:{round(parse_war_date(x['last_active']).timestamp())}:R>\nOngoing wars: {len(x['offensive_wars'] + x['defensive_wars'])}\n\nGround IT chance: **{round(100 * result['nation2_ground_win_rate']**3)}%**\nAir IT chance: **{round(100 * result['nation2_air_win_rate']**3)}%**\nNaval IT chance: **{round(100 * result['nation2_naval_win_rate']**3)}%**{vmend}", True))
                military_fields.append((name, f"{vmstart}[War timeline](https://politicsandwar.com/nation/war/timeline/war={war['id']}) | {x_alliance}\n\n{war_emoji_1} **[{nation['nation_name']}](https://politicsandwar.com/nation/id={nation['id']})**{result['nation1_append']}\n{war_emoji_2} **[{x['nation_name']}](https://politicsandwar.com/nation/id={x['id']})**{result['nation2_append']}\n\nOffensive wars: {len(x['offensive_wars'])}/{x_max_offense}\nDefensive wars: {len(x['defensive_wars'])}/3{beige}\n\n Soldiers: **{x['soldiers']:,}** / {x_max_sol:,}\nTanks: **{x['tanks']:,}** / {x_max_tnk:,}\nPlanes: **{x['aircraft']:,}** / {x_max_pln:,}\nShips: **{x['ships']:,}** / {x_max_shp:,}\nMissiles: {x['missiles']}\nNukes: {x['nukes']}\n\nGround IT chance: **{round(100 * result['nation2_ground_win_rate']**3)}%**\nAir IT chance: **{round(100 * result['nation2_air_win_rate']**3)}%**\nNaval IT chance: **{round(100 * result['nation2_naval_win_rate']**3)}%**{vmend}", True))
                damage_fields.append((name, f"{vmstart}[War timeline](https://politicsandwar.com/nation/war/timeline/war={war['id']}) | {x_alliance}\n\n{war_emoji_1} **[{nation['nation_name']}](https://politicsandwar.com/nation/id={nation['id']})**{result['nation1_append']}\nGround: **${result['nation1_ground_net']/3:,.0f}**\nAir vs Air: **${result['nation1_airvair_net']/4:,.0f}**\nNaval vs Other: **${result['nation1_navalvinfra_net']/4:,.0f}**\nNaval vs Naval: **${result['nation1_navalvships_net']/4:,.0f}**\nMissile: **${result['nation1_missile_net']/8:,.0f}**\nNuke: **${result['nation1_nuke_net']/12:,.0f}**\n\n{war_emoji_2} **[{x['nation_name']}](https://politicsandwar.com/nation/id={x['id']})**{result['nation2_append']}\nGround: **${result['nation2_ground_net']/3:,.0f}**\nAir vs Air: **${result['nation2_airvair_net']/4:,.0f}**\nNaval vs Other: **${result['nation2_navalvinfra_net']/4:,.0f}**\nNaval vs Naval: **${result['nation2_navalvships_net']/4:,.0f}**\nMissile: **${result['nation2_missile_net']/8:,.0f}**\nNuke: **${result['nation2_nuke_net']/12:,.0f}**{vmend}", True))

            # A nation can be in 10 wars; that many fields overflow Discord's limit.
            add_fields_within_limit(embed, general_fields, noun="wars")
            add_fields_within_limit(embed1, military_fields, noun="wars")
            add_fields_within_limit(embed2, damage_fields, noun="wars")

            view, _session_id, active_embed = await views.create_persistent_tabs_prompt(
                command="war_status",
                ctx=ctx,
                tabs=[("General", embed), ("Military", embed1), ("Damage", embed2)],
                initial_index=0,
                ttl_seconds=3600,
            )
            await ctx.respond(content="", embed=active_embed, view=view)
        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="war_status")
            return

    @slash_command(
        name="nuketargets",
        description="Find high-infra nations to nuke or missile in your range",
    )
    @commands.guild_only()
    async def nuketargets(
        self,
        ctx: discord.ApplicationContext,
        sort: Option(str, "The metric to sort the targets by", choices=["Nuke damage", "Missile damage"]) = "Nuke damage",
        include_beige: Option(bool, "Include beige nations", default=False) = False,
        include_slotted: Option(bool, "Include slotted nations", default=False) = False
    ):
        loading: LoadingDisplay | None = None
        try:
            await ctx.respond("Let me think for a second...")
            loading = LoadingDisplay(ctx, show_after=0)
            await loading.start("Let me think for a second...")

            user = await helpers.find_nation_plus(self.bot, ctx.author.id, guild=ctx.guild)
            if not user:
                await loading.clear()
                await ctx.edit(content="Make sure that you are verified with `/verify`!", embed=None, attachments=[])
                return

            config = await db.guild_configs.find_one({"guild_id": ctx.guild.id}) or {}
            alliance_ids = {str(x) for x in (config.get("targets_alliance_ids") or []) if str(x).strip()}
            if not alliance_ids:
                view, session_id = await views.create_persistent_yesno_prompt(
                    command="nuketargets",
                    ctx=ctx,
                    disable_on_submit=False,
                )
                embed = discord.Embed(title="Targets not configured", description="This command has not been configured for this server. To configure targeted alliances, someone with the `Manage Server` permission can use `/config targets`.\n\nDo you want to continue with all alliances being targeted?", color=0xff5100)
                await ctx.edit(content="", embed=embed, view=view, attachments=[])
                result = await views.wait_for_persistent_yesno_result(session_id)
                if result is None:
                    await loading.clear()
                    return
                if result is False:
                    await loading.clear()
                    await ctx.edit(
                        content="Parsing of command was cancelled <:kekw:984765354452602880>",
                        embed=None,
                        view=None,
                        attachments=[],
                    )
                    return
                await loading.update("Let me think for a second...", force_show=True)

            res = await api_client.call(f"{{nations(first:1 id:{user['id']}){{data{get_query(queries.NUKETARGETS)}}}}}", api_key)
            user_nations = (((res or {}).get("data") or {}).get("nations") or {}).get("data") or []
            if not user_nations:
                await loading.clear()
                await ctx.edit(content="I could not load your nation right now. Please try again.", embed=None, view=None, attachments=[])
                return
            user_nation = user_nations[0]
            minscore, maxscore = military_logic.war_range_query_bounds(_num(user_nation.get('score')))
            file_content = await asyncio.to_thread(
                get_all_nations_filtered,
                get_nations_db_path(),
                min_score=minscore,
                max_score=maxscore,
                columns=[*NUKE_TARGET_COLUMNS, "_created_at"],
                json_fields=set(NUKE_TARGET_JSON_FIELDS),
            )
            nation_list = await asyncio.to_thread(
                rank_nuke_targets,
                user_nation,
                file_content["nations"],
                alliance_ids=alliance_ids,
                include_beige=include_beige,
                include_slotted=include_slotted,
                sort_key="missile_damage" if sort == "Missile damage" else "nuke_damage",
                now=datetime.now(timezone.utc),
                fallback_written_at=file_content.get("last_fetched"),
            )

            if len(nation_list) == 0:
                await loading.clear()
                await ctx.edit(content="No eligible targets found!", embed=None, view=None, attachments=[])
                return

            page_count = math.ceil(len(nation_list) / NUKE_TARGETS_PER_PAGE)
            embeds = []
            for page, start in enumerate(range(0, len(nation_list), NUKE_TARGETS_PER_PAGE), start=1):
                embed = discord.Embed(
                    title="Nuke Targets",
                    description=(
                        "Expected rebuild cost of the infrastructure one nuke or missile destroys in "
                        "their best city, after Vital Defense System and Iron Dome intercepts. Assumes an "
                        "Attrition war (or the war you're already in with them); projects and rebuild "
                        f"discounts are included. The [nuke targets page]({WEB_BASE_URL}/nuke-targets) "
                        "has full-war estimates."
                    ),
                    color=0xff5100,
                )
                for i, target in enumerate(nation_list[start:start + NUKE_TARGETS_PER_PAGE]):
                    if i:
                        embed.add_field(name="​", value="​", inline=i % 2 != 0)
                    if target["alliance_id"] != "0":
                        alliance_name = (target["alliance"] or {}).get("name") or f"Alliance {target['alliance_id']}"
                        alliance = f"[{alliance_name}](https://politicsandwar.com/alliance/id={target['alliance_id']})"
                        if isinstance(target["alliance_position"], str):
                            alliance += f" ({target['alliance_position'].capitalize()})"
                    else:
                        alliance = "No alliance"
                    embed.add_field(name=f"{target['nation_name']}", value=f"[Nation](https://politicsandwar.com/nation/id={target['id']}) | {alliance}\nDamage/nuke: `${target['nuke_damage']:,.0f}`\nDamage/missile: `${target['missile_damage']:,.0f}`\nMax infra: `{target['max_infra']:.0f}`\nAvg. infra: `{target['avg_infra']:.0f}`\nVital Defense: {'✅' if target['vds'] else '<:redcross:862669500977905694>'}\nIron Dome: {'✅' if target['iron_dome'] else '<:redcross:862669500977905694>'}")
                embed.set_footer(text=with_support_footer(f"Page {page}/{page_count}"))
                embeds.append(embed)

            if len(embeds) > 1:
                view = views.Switch(ctx=ctx, embeds=embeds, max_page=len(embeds))
            else:
                view = None

            await loading.clear()
            await ctx.edit(embed=embeds[0], content="", view=view, attachments=[])

        except Exception as e:
            if loading is not None:
                await loading.clear()
            await self._handle_command_exception(ctx, e, command_name="nuketargets")
            return

    @slash_command(
        name="damage",
        description="View full damage calculations between two nations",
    )
    async def damage(
        self,
        ctx: discord.ApplicationContext,
        nation1: Option(str, "Nation name, leader name, nation id, nation link or discord username. Defaults to your nation.") = None,
        nation2: Option(str, "Nation name, leader name, nation id, nation link or discord username. Defaults to your nation.") = None
    ):
        try:
            await ctx.defer()
            pair = await self._resolve_nation_pair(ctx, nation1, nation2)
            if pair is None:
                return
            nation1_id, nation2_id = pair
            # The damage page fetches both nations and does the math itself.
            damage_url = f"{WEB_BASE_URL}/damage?nation1={nation1_id}&nation2={nation2_id}"
            await ctx.respond(content=f"Go to {damage_url}")
        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="damage")
            return


    async def battle_calc(
        self,
        nation1_id: Optional[str] = None,
        nation2_id: Optional[str] = None,
        nation1: Optional[dict[str, Any]] = None,
        nation2: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return await calculate_damage_logic(
            call_pnw=call_api,
            nation1_id=nation1_id,
            nation2_id=nation2_id,
            nation1=nation1,
            nation2=nation2,
        )

def setup(bot):
    bot.add_cog(TargetFinding(bot))
