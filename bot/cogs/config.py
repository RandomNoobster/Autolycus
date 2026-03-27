"""Configuration cog for Autolycus Discord bot."""

import logging
import os
from typing import Optional

import discord
from discord.commands import Option, SlashCommandGroup
from discord.ext import commands

from database import mongo as db_mongo
from bot.discord_utils import views
from logic import common

logger = logging.getLogger(__name__)


class Config(commands.Cog):
    """Handles guild and user configuration for the Autolycus bot."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the Config cog.
        
        Args:
            bot: The Discord bot instance.
        """
        self.bot = bot

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
            logger.error(e, exc_info=True)
            raise
    
    
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
            logger.error(e, exc_info=True)
            raise
        
    @config_group.command(
        name="reminders",
        description="Customize when you receive beige exit reminder DMs",
    )
    @commands.has_permissions(manage_guild=True)
    async def config_beige_reminders(
        self,
        ctx: discord.ApplicationContext,
    ) -> None:
        """Configure beige exit reminders for the user.
        
        Allows users to set up multiple reminders before their nations exit
        beige mode. Uses an interactive modal/button interface.
        
        Args:
            ctx: The Discord application context.
            
        Raises:
            Exception: Re-raised after logging for error tracking.
        """
        try:
            await ctx.defer()
            db = db_mongo.get_db()
            user = await db.global_users.find_one({"user": ctx.user.id})
            
            if not user:
                verify_cmd = ctx.bot.get_application_command("verify")
                await ctx.edit(
                    f"I could not find you in my database! Please use {verify_cmd.mention} first."
                )
                return
            
            # Initialize config fields if they don't exist
            user.setdefault("beige_alerts", [])
            user.setdefault("beige_alerts_config", [])

            while True:
                # Check if user already has reminders configured
                if user["beige_alerts_config"]:
                    reminders_text = common.comma_and_list(
                        [f"{minutes} minutes" for minutes in user["beige_alerts_config"]]
                    )
                    description = (
                        f"Your current configuration is to recieve reminders {reminders_text} "
                        "before a nation exits beige. Do you want to keep this configuration "
                        "(and have the option to add more reminders) or do you want to discard it?"
                    )
                    embed = discord.Embed(
                        title="Configuration of beige reminders",
                        description=description,
                        color=common.EMBED_COLOR,
                    )
                    view = views.YesOrNoView(
                        ctx, positive="Keep", negative="Discard"
                    )
                    await ctx.edit(embed=embed, view=view)
                    timed_out = await view.wait()
                    
                    if timed_out:
                        return
                    
                    if not view.result:
                        user["beige_alerts_config"] = []

                # Prompt for adding more reminders
                if user["beige_alerts_config"]:
                    reminders_text = common.comma_and_list(
                        [f"{minutes} minutes" for minutes in user["beige_alerts_config"]]
                    )
                    description = (
                        f"Your current configuration is to recieve reminders {reminders_text} "
                        "before a nation exits beige. Do you want to get another reminder at some other time?"
                    )
                else:
                    description = (
                        "You currently have no reminders configured. Do you want to add a reminder "
                        "for when a nation exits beige?"
                    )

                embed = discord.Embed(
                    title="Configuration of beige reminders",
                    description=description,
                    color=common.EMBED_COLOR,
                )
                modal = views.SimpleModal(
                    title="Configuration of beige reminders",
                    label="Minutes before exiting beige",
                    placeholder="Enter an integer, e.g. 5",
                )
                view = views.YesOrNoView(
                    ctx,
                    positive="Add more",
                    negative="Finish configuration",
                    positive_style=discord.ButtonStyle.blurple,
                    negative_style=discord.ButtonStyle.blurple,
                )

                async def primary_callback(interaction: discord.Interaction) -> None:
                    """Handle modal submission."""
                    view.result = True
                    await interaction.response.send_modal(modal)
                    view.stop()

                view.children[0].callback = primary_callback
                await ctx.edit(embed=embed, view=view)
                timed_out = await view.wait()
                
                if timed_out:
                    return

                if not view.result:
                    # User chose to finish configuration
                    if user["beige_alerts_config"]:
                        reminders_text = common.comma_and_list(
                            [f"{minutes} minutes" for minutes in user["beige_alerts_config"]]
                        )
                        description = f"You will be reminded {reminders_text} before a nation exits beige."
                    else:
                        description = (
                            "You finished the configuration without adding any reminders. "
                            "The system default of 15 minutes will be used."
                        )
                    
                    embed = discord.Embed(
                        title="Configuration of beige reminders",
                        description=description,
                        color=common.EMBED_COLOR,
                    )
                    view.disable_all_items()
                    await ctx.edit(embed=embed, view=view)
                    break

                # Wait for modal submission
                submitted = await modal.wait()
                if not submitted:
                    return

                reminder_str = modal.text
                if reminder_str.isdigit():
                    reminder = int(reminder_str)
                    if reminder not in user["beige_alerts_config"]:
                        user["beige_alerts_config"].append(reminder)
                        user["beige_alerts_config"].sort()
                    
                    await db.global_users.find_one_and_update(
                        {"user": ctx.user.id},
                        {"$set": {"beige_alerts_config": user["beige_alerts_config"]}},
                        upsert=True,
                    )
                else:
                    await ctx.edit(
                        content="The input must be a positive integer!", embed=None, view=None
                    )
                    return

        except Exception as e:
            logger.error(e, exc_info=True)
            raise

def setup(bot: commands.Bot) -> None:
    """Load the Config cog into the bot.
    
    Args:
        bot: The Discord bot instance.
    """
    bot.add_cog(Config(bot))