"""Discord embeds and browser push payloads for beige reminders."""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime
from typing import Any, Mapping, Optional

import discord

from bot.discord_utils.embeds import EMBED_COLOR, with_support_footer
from database.sqlite_cache import get_nation_by_id, get_nations_db_path
from infra.webpush import notification_payload
from logic import api_client, queries
from logic import reminders as rules
from logic.common import compute_beige_loot
from logic.merge_utils import get_query
from logic.revenue import pre_revenue_calc, revenue_calc_sync
from services.reminder_scheduler import RenderedReminder

logger = logging.getLogger(__name__)

_CONTEXT_TTL_SECONDS = 10 * 60
_FAILED_CONTEXT_TTL_SECONDS = 60
_CONTEXT_TIMEOUT_SECONDS = 20.0


def nation_url(nation_id: str) -> str:
    return f"https://politicsandwar.com/nation/id={nation_id}"


def declare_war_url(nation_id: str) -> str:
    return f"https://politicsandwar.com/nation/war/declare/id={nation_id}"


def protection_label(beige_turns: int, vm_turns: int) -> str:
    """What the nation is leaving, in words."""
    if beige_turns > 0 and vm_turns > 0:
        return "beige and vacation mode"
    if vm_turns > 0:
        return "vacation mode"
    return "beige"


def economy_lines(
    nation: Optional[Mapping[str, Any]],
    prices: Optional[Mapping[str, float]],
    revenue: Optional[Mapping[str, Any]],
) -> str:
    """Previous beige loot, net income and alliance tax (matches the raids page)."""
    loot = 0
    if nation:
        try:
            loot = int(nation.get("nation_loot_value") or 0)
        except (TypeError, ValueError):
            loot = 0
    if loot <= 0 and nation and prices:
        computed = compute_beige_loot(dict(nation), dict(prices))
        if computed is not None:
            loot = computed
    loot_text = f"${loot:,}" if loot > 0 else "Unknown"

    net_text = "Unknown"
    if revenue and revenue.get("monetary_net_num") is not None:
        try:
            net_text = f"${int(round(float(revenue['monetary_net_num']))):,}"
        except (TypeError, ValueError):
            net_text = "Unknown"

    tax_text = "Unknown"
    if nation:
        alliance = nation.get("alliance") if isinstance(nation.get("alliance"), dict) else {}
        alliance_color = alliance.get("color") if alliance else None
        nation_color = nation.get("color") or ""
        if nation_color and alliance_color:
            tax_text = "Yes" if str(nation_color).lower() == str(alliance_color).lower() else "No"

    return (
        f"Previous beige loot: **{loot_text}**\n"
        f"Net income: **{net_text}**\n"
        f"Paying alliance tax: **{tax_text}**"
    )


def _data_timestamp(nation: Optional[Mapping[str, Any]], last_fetched: Any) -> Optional[int]:
    for raw in ((nation or {}).get("_created_at"), last_fetched):
        try:
            if raw is not None:
                return int(raw)
        except (TypeError, ValueError):
            continue
    return None


class ReminderRenderer:
    """Builds reminder messages from the scanner's nation cache plus revenue maths."""

    def __init__(self, api_key: Optional[str]) -> None:
        self._api_key = api_key
        self._contexts: dict[str, tuple[float, float, dict[str, Any]]] = {}

    async def _call(self, query: str) -> dict[str, Any]:
        return await api_client.call(query, self._api_key)

    async def render(
        self,
        job: Mapping[str, Any],
        status: Optional[rules.NationStatus],
        now: datetime,
    ) -> RenderedReminder:
        """Render one job for Discord and browser push."""
        nation_id = str(job["nation_id"])
        context = await self._context(nation_id)
        nation = context.get("nation")
        name = str((nation or {}).get("nation_name") or f"Nation {nation_id}")
        exit_at = rules.ensure_utc(job["exit_at"])
        beige_turns, vm_turns = self._turns(status, nation)

        if job.get("kind") == rules.JOB_KIND_EARLY_EXIT:
            embed = self._early_exit_embed(nation_id, name, context, exit_at)
            payload = notification_payload(
                title=f"{name} left beige early",
                body="They can be attacked now. Tap to open their nation.",
                navigate=nation_url(nation_id),
                tag=rules.push_topic(nation_id),
                kind="early_exit",
                timestamp=now,
                nation_id=nation_id,
            )
        else:
            label = protection_label(beige_turns, vm_turns)
            late = bool(job.get("late"))
            embed = self._lead_embed(nation_id, name, context, exit_at, beige_turns, vm_turns, label, late)
            offset = job.get("offset_min")
            remaining = max(1, math.ceil((exit_at - rules.ensure_utc(now)).total_seconds() / 60))
            minutes = remaining if late or not offset else int(offset)
            payload = notification_payload(
                title=f"{name} leaves {label} in {rules.describe_offset(minutes)}",
                body=f"Exits at {exit_at:%H:%M} UTC. Tap to open their nation.",
                navigate=nation_url(nation_id),
                tag=rules.push_topic(nation_id),
                kind="beige_reminder",
                timestamp=now,
                nation_id=nation_id,
            )
        return RenderedReminder(embed=embed.to_dict(), push_payload=payload, nation_name=name)

    @staticmethod
    def _turns(
        status: Optional[rules.NationStatus], nation: Optional[Mapping[str, Any]]
    ) -> tuple[int, int]:
        if status is not None:
            return status.beige_turns, status.vm_turns
        if nation:
            try:
                return int(nation.get("beige_turns") or 0), int(nation.get("vacation_mode_turns") or 0)
            except (TypeError, ValueError):
                pass
        return 1, 0

    async def _context(self, nation_id: str) -> dict[str, Any]:
        now = time.monotonic()
        cached = self._contexts.get(nation_id)
        if cached is not None and now - cached[0] < cached[1]:
            return cached[2]
        try:
            context = await asyncio.wait_for(self._load_context(nation_id), _CONTEXT_TIMEOUT_SECONDS)
            ttl = _CONTEXT_TTL_SECONDS
        except Exception as exc:  # noqa: BLE001 - a plain reminder beats no reminder
            logger.warning("Reminder details unavailable for nation %s: %s", nation_id, exc)
            context = {"nation": None, "data_timestamp": None, "prices": None, "revenue": None}
            ttl = _FAILED_CONTEXT_TTL_SECONDS
        self._contexts[nation_id] = (now, ttl, context)
        for key in [k for k, (created, keep, _) in self._contexts.items() if now - created >= keep]:
            self._contexts.pop(key, None)
        return context

    async def _load_context(self, nation_id: str) -> dict[str, Any]:
        payload = await asyncio.to_thread(get_nation_by_id, get_nations_db_path(), nation_id)
        nation = payload.get("nation")
        context: dict[str, Any] = {
            "nation": nation,
            "data_timestamp": _data_timestamp(nation, payload.get("last_fetched")),
            "prices": None,
            "revenue": None,
        }
        if not nation or not self._api_key:
            return context
        try:
            _, colors, prices, treasures, radiation, seasonal_mod = await pre_revenue_calc(
                message=None,
                query_for_nation=False,
                parsed_nation=nation,
                call_func=self._call,
                get_query_func=get_query,
                queries_module=queries,
            )
            context["prices"] = prices
            context["revenue"] = await asyncio.to_thread(
                revenue_calc_sync,
                nation,
                radiation,
                treasures,
                prices,
                colors,
                seasonal_mod,
                include_spies=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Revenue for reminder nation %s unavailable: %s", nation_id, exc)
        return context

    @staticmethod
    def _identity_lines(nation_id: str, nation: Optional[Mapping[str, Any]]) -> list[str]:
        leader = (nation or {}).get("leader_name") or "Unknown"
        alliance = "None"
        if nation and isinstance(nation.get("alliance"), dict):
            alliance = nation["alliance"].get("name") or "None"
        return [
            f"Leader: **{leader}**",
            f"Alliance: **{alliance}**",
            f"[Open nation profile]({nation_url(nation_id)}) · [Declare war]({declare_war_url(nation_id)})",
        ]

    @staticmethod
    def _detail_fields(embed: discord.Embed, context: Mapping[str, Any]) -> None:
        nation = context.get("nation")
        embed.add_field(
            name="Economy",
            value=economy_lines(nation, context.get("prices"), context.get("revenue")),
            inline=False,
        )
        if nation:
            embed.add_field(
                name="Military",
                value=(
                    f"Soldiers: **{int(nation.get('soldiers') or 0):,}**\n"
                    f"Tanks: **{int(nation.get('tanks') or 0):,}**\n"
                    f"Aircraft: **{int(nation.get('aircraft') or 0):,}**\n"
                    f"Ships: **{int(nation.get('ships') or 0):,}**\n"
                    f"Missiles: **{nation.get('missiles') or 0}**\n"
                    f"Nukes: **{nation.get('nukes') or 0}**"
                ),
                inline=True,
            )
            info = []
            if nation.get("score") is not None:
                info.append(f"Score: **{nation.get('score')}**")
            if nation.get("num_cities") is not None:
                info.append(f"Cities: **{nation.get('num_cities')}**")
            if nation.get("color"):
                info.append(f"Color: **{str(nation.get('color')).capitalize()}**")
            if info:
                embed.add_field(name="Nation Info", value="\n".join(info), inline=True)
            flag = nation.get("flag")
            if flag:
                embed.set_thumbnail(url=str(flag))
        stamp = context.get("data_timestamp")
        if stamp:
            embed.add_field(name="Data Updated", value=f"<t:{stamp}:R> (<t:{stamp}:f>)", inline=False)
        embed.set_footer(text=with_support_footer("Autolycus beige reminder"))

    def _lead_embed(
        self,
        nation_id: str,
        name: str,
        context: Mapping[str, Any],
        exit_at: datetime,
        beige_turns: int,
        vm_turns: int,
        label: str,
        late: bool,
    ) -> discord.Embed:
        stamp = rules.to_epoch(exit_at)
        lines: list[str] = []
        if late:
            lines.append("**Late reminder:** Autolycus was offline when this was due.")
        lines.append(f"Leaves {label} <t:{stamp}:R> (<t:{stamp}:t>)")
        lines.extend(self._identity_lines(nation_id, context.get("nation")))
        embed = discord.Embed(title=name, url=nation_url(nation_id), description="\n".join(lines), color=EMBED_COLOR)
        status = []
        if beige_turns > 0:
            status.append(f"Beige turns: **{beige_turns}**")
        if vm_turns > 0:
            status.append(f"VM turns: **{vm_turns}**")
        status.append(f"Exits: <t:{stamp}:f>")
        embed.add_field(name="Status", value="\n".join(status), inline=False)
        self._detail_fields(embed, context)
        return embed

    def _early_exit_embed(
        self,
        nation_id: str,
        name: str,
        context: Mapping[str, Any],
        expected_exit_at: datetime,
    ) -> discord.Embed:
        stamp = rules.to_epoch(expected_exit_at)
        lines = [
            f"Left protection before its expected exit at <t:{stamp}:t>. They can be attacked now.",
            *self._identity_lines(nation_id, context.get("nation")),
        ]
        embed = discord.Embed(
            title=f"{name} left beige early",
            url=nation_url(nation_id),
            description="\n".join(lines),
            color=EMBED_COLOR,
        )
        self._detail_fields(embed, context)
        return embed
