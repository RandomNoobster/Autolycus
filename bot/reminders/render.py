"""Discord embeds and browser push payloads for beige reminders."""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional

import discord

from bot.discord_utils.embeds import EMBED_COLOR, with_support_footer
from database.sqlite_cache import get_nation_by_id, get_nations_db_path
from infra.webpush import notification_payload
from logic import reminders as rules
from services.reminder_scheduler import RenderedReminder

logger = logging.getLogger(__name__)

_CONTEXT_TTL_SECONDS = 10 * 60
# Longer than the scheduler prepares ahead (90 s), so a failed lookup isn't retried
# while the wave is being sent.
_FAILED_CONTEXT_TTL_SECONDS = 2 * 60
_CONTEXT_TIMEOUT_SECONDS = 5.0
# A reminder sent this long after its due time says it is late and shows the time left.
_LATE_AFTER = timedelta(minutes=2)


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


def _money(nation: Optional[Mapping[str, Any]], key: str) -> str:
    raw = (nation or {}).get(key)
    if raw is None:
        return "Unknown"
    try:
        return f"${int(round(float(raw))):,}"
    except (TypeError, ValueError):
        return "Unknown"


def economy_lines(nation: Optional[Mapping[str, Any]]) -> str:
    """Previous beige loot, net income and alliance tax.

    Loot and income are the values the scanner stores on the nation row for the raids
    page, so the DM matches it (including a genuine $0 loot) without recomputing.
    """
    loot_text = _money(nation, "nation_loot_value")
    net_text = _money(nation, "monetary_net_num")

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
    """Builds reminder messages from the scanner's nation cache."""

    def __init__(self) -> None:
        self._contexts: dict[str, tuple[float, float, dict[str, Any]]] = {}

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
            due_at = job.get("due_at")
            overdue = isinstance(due_at, datetime) and rules.ensure_utc(now) - rules.ensure_utc(due_at) > _LATE_AFTER
            late = bool(job.get("late")) or overdue
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
            context = {"nation": None, "data_timestamp": None}
            ttl = _FAILED_CONTEXT_TTL_SECONDS
        self._contexts[nation_id] = (now, ttl, context)
        for key in [k for k, (created, keep, _) in self._contexts.items() if now - created >= keep]:
            self._contexts.pop(key, None)
        return context

    async def _load_context(self, nation_id: str) -> dict[str, Any]:
        payload = await asyncio.to_thread(get_nation_by_id, get_nations_db_path(), nation_id)
        nation = payload.get("nation")
        return {"nation": nation, "data_timestamp": _data_timestamp(nation, payload.get("last_fetched"))}

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
            value=economy_lines(nation),
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
            lines.append("**Late reminder:** Autolycus couldn't send this on time.")
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
