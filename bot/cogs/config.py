"""Configuration cog for Autolycus Discord bot."""

import logging

import discord
from discord.commands import Option, SlashCommandGroup
from discord.ext import commands

from database import mongo as db_mongo
from bot.discord_utils import errors as err_util
from bot.discord_utils import views
from logic import common
from database import reminders as reminder_db
from logic import reminders as reminder_rules

logger = logging.getLogger(__name__)

# Discord's limit for a message's content.
_MAX_MESSAGE_CHARS = 2000


class Config(commands.Cog):
    """Handles guild and user configuration for the Autolycus bot."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the Config cog.

        Args:
            bot: The Discord bot instance.
        """
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
            title="Configuration failed",
            message="I couldn't update or read that setting. Please try again.",
        )

    async def _set_alliance_list(
        self,
        ctx: discord.ApplicationContext,
        *,
        field: str,
        alliance_ids: str,
        label: str,
    ) -> None:
        """Store a guild's alliance id list; empty input clears it."""
        id_list: list[str] = []
        id_str = "None"
        if alliance_ids.strip():
            id_list, id_str = common.str_to_id_list(alliance_ids)
            if not id_list:
                # Names instead of ids would otherwise wipe the stored list.
                await ctx.respond(
                    "I couldn't find any alliance ids in that. Use the numeric ids "
                    "(from the alliance's page link), separated by commas. "
                    f"The {label} list was not changed.",
                    ephemeral=True,
                )
                return
        await db_mongo.get_db().guild_configs.find_one_and_update(
            {"guild_id": ctx.guild.id},
            {"$set": {field: id_list}},
            upsert=True,
        )
        await ctx.respond(f"{label} set to `{id_str}`")

    config_group = SlashCommandGroup("config", "Server and personal configuration settings")

    @config_group.command(
        name="dnr",
        description="Set the Do Not Raid alliance list for this server",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def config_dnr(
        self,
        ctx: discord.ApplicationContext,
        alliance_ids: Option(str, "The alliance id(s) to include in the DNR list. Leave empty to clear it.") = "",
    ) -> None:
        """Set the Do Not Raid (DNR) alliance list for this server.

        Args:
            ctx: The Discord application context.
            alliance_ids: Comma-separated alliance IDs for the DNR list.
        """
        try:
            await self._set_alliance_list(
                ctx, field="dnr_alliance_ids", alliance_ids=alliance_ids, label="DNR"
            )
        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="config dnr")
            return

    @config_group.command(
        name="targets",
        description="Set the alliances /nuketargets looks for targets in",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def config_targets(
        self,
        ctx: discord.ApplicationContext,
        alliance_ids: Option(str, "The enemy alliance id(s) to target. Leave empty to target all alliances.") = "",
    ) -> None:
        """Set the alliances /nuketargets searches (``targets_alliance_ids``)."""
        try:
            await self._set_alliance_list(
                ctx, field="targets_alliance_ids", alliance_ids=alliance_ids, label="Target alliances"
            )
        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="config targets")
            return

    @config_group.command(
        name="view_current_settings",
        description="View this server's current Autolycus configuration",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def config_view_current_settings(
        self,
        ctx: discord.ApplicationContext,
    ) -> None:
        """Display the current configuration settings for this server.

        Args:
            ctx: The Discord application context.
        """
        try:
            await ctx.defer(ephemeral=True)
            db = db_mongo.get_db()
            server = await db.guild_configs.find_one({"guild_id": ctx.guild.id})

            if not server:
                await ctx.edit(content="No configurable commands have been configured in this server!")
            else:
                content = "The configuration for this guild is as follows:\n\n```\n"
                for key, value in server.items():
                    if key == "_id":
                        continue
                    content += f"{key}: {value}\n"
                closing = "```"
                if len(content) + len(closing) > _MAX_MESSAGE_CHARS:
                    content = content[: _MAX_MESSAGE_CHARS - len(closing) - 2] + "…\n"
                await ctx.edit(content=content + closing)
        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="config view_current_settings")
            return

    @config_group.command(
        name="reminders",
        description="Customize when you receive beige exit reminders",
    )
    async def config_beige_reminders(
        self,
        ctx: discord.ApplicationContext,
    ) -> None:
        """Configure how long before an exit beige reminders arrive.

        A personal setting, so it works in any server and in DMs. Uses the same
        limits as the website: 1-10 times, each from 1 minute to 7 days.

        Args:
            ctx: The Discord application context.
        """
        try:
            await ctx.defer()
            db = db_mongo.get_db()
            profile = await reminder_db.get_profile(db, ctx.user.id) or {}
            stored = profile.get("beige_alerts_config")
            # The timings the scheduler actually uses (it keeps the valid entries of
            # an older list); nothing stored means the default applies.
            offsets = reminder_rules.effective_offsets(stored) if stored else []

            def describe(minutes: list[int]) -> str:
                return common.comma_and_list(
                    [reminder_rules.describe_offset(m) for m in sorted(minutes, reverse=True)]
                )

            if offsets:
                embed = discord.Embed(
                    title="Configuration of beige reminders",
                    description=(
                        f"You currently get reminders {describe(offsets)} before a nation exits beige. "
                        "Do you want to keep these times (and have the option to add more) or start over?"
                    ),
                    color=common.EMBED_COLOR,
                )
                view, session_id = await views.create_persistent_yesno_prompt(
                    command="config_reminders",
                    ctx=ctx,
                    positive="Keep",
                    negative="Start over",
                    disable_on_submit=False,
                )
                await ctx.edit(embed=embed, view=view)
                result = await views.wait_for_persistent_yesno_result(session_id)
                if result is None:
                    return
                if not result:
                    offsets = []

            while True:
                if offsets:
                    description = (
                        f"You'll get reminders {describe(offsets)} before a nation exits beige. "
                        "Do you want another reminder at some other time?"
                    )
                else:
                    description = (
                        "You have no reminder times configured. Add one, or finish to use "
                        "the default of 15 minutes."
                    )
                embed = discord.Embed(
                    title="Configuration of beige reminders",
                    description=description,
                    color=common.EMBED_COLOR,
                )
                choices = [("finish", "Finish configuration", discord.ButtonStyle.blurple)]
                if len(offsets) < reminder_rules.MAX_REMINDER_OFFSETS:
                    choices.insert(0, ("add", "Add more", discord.ButtonStyle.blurple))
                view, session_id = await views.create_persistent_choice_prompt(
                    command="config_reminders",
                    ctx=ctx,
                    choices=choices,
                    disable_on_submit=False,
                    # The button opens the modal itself: a modal must be the first
                    # response to the click.
                    modals={
                        "add": {
                            "title": "Configuration of beige reminders",
                            "label": "Minutes before exiting beige",
                            "placeholder": "A whole number from 1 to 10080, e.g. 15",
                        }
                    },
                )
                await ctx.edit(embed=embed, view=view)
                answer = await views.wait_for_persistent_choice(session_id)
                if answer is None:
                    return
                result, state = answer

                if result == "finish":
                    final = offsets or list(reminder_rules.DEFAULT_REMINDER_OFFSETS)
                    await reminder_db.set_offsets(
                        db, ctx.user.id, sorted(final, reverse=True), reminder_rules.utcnow()
                    )
                    embed = discord.Embed(
                        title="Configuration of beige reminders",
                        description=f"You'll be reminded {describe(final)} before a nation exits beige.",
                        color=common.EMBED_COLOR,
                    )
                    await ctx.edit(embed=embed, view=None)
                    break

                minutes = reminder_rules.parse_offset_minutes(str(state.get("text") or ""))
                if minutes is None:
                    await ctx.edit(
                        content="Enter a whole number of minutes from 1 to 10080 (7 days).",
                        embed=None,
                        view=None,
                    )
                    return
                if minutes not in offsets:
                    offsets.append(minutes)
                await reminder_db.set_offsets(
                    db, ctx.user.id, sorted(offsets, reverse=True), reminder_rules.utcnow()
                )

        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="config reminders")
            return

def setup(bot: commands.Bot) -> None:
    """Load the Config cog into the bot.

    Args:
        bot: The Discord bot instance.
    """
    bot.add_cog(Config(bot))
