"""Configuration cog for Autolycus Discord bot."""

import logging
import os
from typing import Optional

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
        ref = await err_util.report_handled_exception(
            self.bot,
            ctx,
            error,
            logger,
            command_name=command_name,
        )
        embed = err_util.error_embed(
            "Configuration failed",
            (
                err_util.PNW_SERVER_USER_MESSAGE
                if err_util.is_pnw_server_error(error)
                else "I couldn't update or read that setting. Please try again."
            ),
            reference=ref,
        )
        await err_util.safe_reply_error(ctx, embed, ephemeral=True, reference=ref, log=logger)

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
        alliance_ids: Option(str, "The alliance id(s) to include in the DNR list") = "",
    ) -> None:
        """Set the Do Not Raid (DNR) alliance list for this server.
        
        Args:
            ctx: The Discord application context.
            alliance_ids: Comma-separated alliance IDs to add to the DNR list.
            
        Raises:
            Exception: Re-raised after logging for error tracking.
        """
        try:
            id_list: list[int] = []
            id_str: str = "None"
            
            if alliance_ids:
                id_list, id_str = common.str_to_id_list(alliance_ids)
            
            db = db_mongo.get_db()
            await db.guild_configs.find_one_and_update(
                {"guild_id": ctx.guild.id},
                {"$set": {"dnr_alliance_ids": id_list}},
                upsert=True,
            )
            await ctx.respond(f"DNR set to `{id_str}`")
        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="config dnr")
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
            
        Raises:
            Exception: Re-raised after logging for error tracking.
        """
        try:
            await ctx.defer(ephemeral=True)
            db = db_mongo.get_db()
            server = await db.guild_configs.find_one({"guild_id": ctx.guild.id})
            
            if not server:
                await ctx.edit("No configurable commands have been configured in this server!")
            else:
                content = "The configuration for this guild is as follows:\n\n```\n"
                for key, value in server.items():
                    content += f"{key}: {value}\n"
                await ctx.edit(content=content + "```")
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
            offsets = reminder_rules.sanitize_offsets(profile.get("beige_alerts_config")) or []

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
                msg = await ctx.edit(embed=embed, view=view)
                if msg and getattr(msg, "id", None):
                    await views.bind_persistent_prompt_message(session_id, msg.id)
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
                modal = views.SimpleModal(
                    title="Configuration of beige reminders",
                    label="Minutes before exiting beige",
                    placeholder="A whole number from 1 to 10080, e.g. 15",
                )
                choices = [("finish", "Finish configuration", discord.ButtonStyle.blurple)]
                if len(offsets) < reminder_rules.MAX_REMINDER_OFFSETS:
                    choices.insert(0, ("add", "Add more", discord.ButtonStyle.blurple))
                view, session_id = await views.create_persistent_choice_prompt(
                    command="config_reminders",
                    ctx=ctx,
                    choices=choices,
                    disable_on_submit=False,
                )
                msg = await ctx.edit(embed=embed, view=view)
                if msg and getattr(msg, "id", None):
                    await views.bind_persistent_prompt_message(session_id, msg.id)
                result = await views.wait_for_persistent_choice_result(session_id)

                if result is None:
                    return

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

                # Wait for modal submission
                await ctx.send_modal(modal)
                submitted = await modal.wait()
                if not submitted:
                    return

                minutes = reminder_rules.parse_offset_minutes(modal.text)
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
