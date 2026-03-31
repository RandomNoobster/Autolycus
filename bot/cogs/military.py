import json
import logging
import math
import os
import pathlib
import random
import urllib.parse
from datetime import datetime, timedelta
from functools import partial
from typing import Any, Dict, List, Optional

import aiofiles
import aiohttp
import discord
from discord.commands import Option, SlashCommandGroup, slash_command
from discord.ext import commands

from logic import queries
from database import mongo as db_mongo
from database import users as db_users
from bot.discord_utils import helpers, views
from bot.discord_utils import errors as err_util
# Import from new architecture layers
from logic import api_client
from logic import military as military_logic
from logic.damage import calculate_damage as calculate_damage_logic
from logic.merge_utils import get_query
from logic.revenue import pre_revenue_calc, revenue_calc
from database.sqlite_cache import (
    find_nation as sqlite_find_nation,
    get_all_nations,
    get_alliances_by_ids,
    get_nations_db_path,
)
from logic.raids import compute_beige_loot_or_zero
from core.config import (
    AUTOLYCUS_API_BASE_URL as API_BASE_URL,
    AUTOLYCUS_WEB_BASE_URL as WEB_BASE_URL,
)

logger = logging.getLogger(__name__)

api_key = os.getenv("API_KEY")
call_api = partial(api_client.call, api_key=api_key)

DISCORD_BOT_API_KEY = os.getenv("DISCORD_BOT_API_KEY")

# Get database instance for queries
db = db_mongo.get_db()


class TargetFinding(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _handle_command_exception(
        self,
        ctx: discord.ApplicationContext,
        error: Exception,
        *,
        command_name: str,
        user_message: str = "I couldn't complete that military command. Please try again.",
    ) -> None:
        ref = await err_util.report_handled_exception(
            self.bot,
            ctx,
            error,
            logger,
            command_name=command_name,
        )
        embed = err_util.error_embed(
            "Command failed",
            user_message,
            reference=ref,
        )
        await err_util.safe_reply_error(ctx, embed, ephemeral=True, reference=ref, log=logger)

    def calculate_win_chance(self, attacker_value: float, defender_value: float) -> float:
        """
        Calculate the exact win probability based on the Uniform Distribution model.
        
        Delegates to logic.military.militarization_checker for the core calculation.
        
        Args:
            attacker_value: The military score/strength of the attacker.
            defender_value: The military score/strength of the defender.
            
        Returns:
            float: Probability of winning (0.0 to 1.0).
        """
        return military_logic.calculate_win_chance_raw(attacker_value, defender_value)
    
    # Legacy alias for backward compatibility
    def winrate_calc(self, attacker_value: float, defender_value: float) -> float:
        """Legacy alias for calculate_win_chance. Use calculate_win_chance for new code."""
        return self.calculate_win_chance(attacker_value, defender_value)


    @slash_command(
        name="raids",
        description="Find profitable raid targets in your war range",
    )
    async def raids(
        self, 
        ctx: discord.ApplicationContext,
        score: Option(float, "Set a custom score range.") = None
        ):
        try:
            try:
                await ctx.defer()
            except discord.NotFound:
                # Interaction already expired before we could acknowledge it.
                logger.warning("Skipping /raids: interaction expired before defer.")
                return
            
            when_to_timeout = datetime.utcnow() + timedelta(minutes=10)

            attacker = await helpers.find_nation_plus(self.bot, ctx.author.id)
            if not attacker:
                await ctx.edit(content='I could not find your nation, make sure that you are verified by using `/verify`!')
                return
            atck_ntn = (await api_client.call(f"{{nations(first:1 id:{attacker['id']}){{data{get_query(queries.WINRATE_CALC, {'nations': ['nation_name', 'score', 'id', 'population']})}}}}}", api_key))['data']['nations']['data'][0]
            if atck_ntn == None:
                await ctx.edit(content='I did not find that person!')
                return
            
            if score:
                minscore = round(score * 0.75)
                maxscore = round(score * 2.5)
            else:
                minscore = round(atck_ntn['score'] * 0.75)
                maxscore = round(atck_ntn['score'] * 2.5)
            
            use_same = None
            class stage_one(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal use_same
                    use_same = True
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal use_same
                    use_same = False
                    await i.response.edit_message()
                    self.stop()

                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await views.run_timeout(ctx, view)

            webpage = None
            discord_embed = None
            class stage_two(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                @discord.ui.button(label="Embed on discord", style=discord.ButtonStyle.primary)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal webpage, discord_embed
                    webpage = False
                    discord_embed = True
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="Message on discord", style=discord.ButtonStyle.primary)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal webpage, discord_embed
                    webpage = False
                    discord_embed = False
                    await i.response.edit_message()
                    self.stop()

                @discord.ui.button(label="As a webpage (recommended)", style=discord.ButtonStyle.primary)
                async def tertiary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal webpage, discord_embed
                    webpage = True
                    discord_embed = False
                    await i.response.edit_message()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await views.run_timeout(ctx, view)
            
            who = None
            class stage_three(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                @discord.ui.button(label="All nations", style=discord.ButtonStyle.primary)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal who
                    who = ""
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="Applicants and nations not in alliances", style=discord.ButtonStyle.primary)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal who
                    who = " alliance_position:[0,1]"
                    await i.response.edit_message()
                    self.stop()

                @discord.ui.button(label="Nations not affiliated with any alliance", style=discord.ButtonStyle.primary)
                async def tertiary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal who
                    who = " alliance_id:0"
                    await i.response.edit_message()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await views.run_timeout(ctx, view)               
                
            max_wars = None
            class stage_four(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                @discord.ui.button(label="0", style=discord.ButtonStyle.primary)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal max_wars
                    max_wars = 0
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="1 or less", style=discord.ButtonStyle.primary)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal max_wars
                    max_wars = 1
                    await i.response.edit_message()
                    self.stop()

                @discord.ui.button(label="2 or less", style=discord.ButtonStyle.primary)
                async def tertiary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal max_wars
                    max_wars = 2
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="3 or less", style=discord.ButtonStyle.primary)
                async def quadrary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal max_wars
                    max_wars = 3
                    await i.response.edit_message()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await views.run_timeout(ctx, view)
        
            inactive_limit = None
            class stage_five(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                @discord.ui.button(label="I don't care", style=discord.ButtonStyle.primary)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal inactive_limit
                    inactive_limit = 0
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="7+ days inactive", style=discord.ButtonStyle.primary)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal inactive_limit
                    inactive_limit = 7
                    await i.response.edit_message()
                    self.stop()

                @discord.ui.button(label="14+ days inactive", style=discord.ButtonStyle.primary)
                async def tertiary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal inactive_limit
                    inactive_limit = 14
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="30+ days inactive", style=discord.ButtonStyle.primary)
                async def quadrary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal inactive_limit
                    inactive_limit = 30
                    await i.response.edit_message()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await views.run_timeout(ctx, view)
            
            beige = None
            class stage_six(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal beige
                    beige = True
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal beige
                    beige = False
                    await i.response.edit_message()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await views.run_timeout(ctx, view)
                                
            minimum_beige_loot = None
            class stage_seven(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                @discord.ui.button(label="No minimum", style=discord.ButtonStyle.primary)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal minimum_beige_loot
                    minimum_beige_loot = 0
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="$5 million", style=discord.ButtonStyle.primary)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal minimum_beige_loot
                    minimum_beige_loot = 5000000
                    await i.response.edit_message()
                    self.stop()

                @discord.ui.button(label="$10 million", style=discord.ButtonStyle.primary)
                async def tertiary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal minimum_beige_loot
                    minimum_beige_loot = 10000000
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="$20 million", style=discord.ButtonStyle.primary)
                async def quadrary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal minimum_beige_loot
                    minimum_beige_loot = 20000000
                    await i.response.edit_message()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await views.run_timeout(ctx, view)
            
            performace_filter = None
            class stage_eight(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
                async def primary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal performace_filter
                    performace_filter = True
                    await i.response.edit_message()
                    self.stop()
                
                @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
                async def secondary_callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal performace_filter
                    performace_filter = False
                    await i.response.edit_message()
                    self.stop()
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    await views.run_timeout(ctx, view)

            target_list = []
            
            file_content = last_fetched = None
            last_load_exception = None
            for i in range(3):
                try:
                    file_content = get_all_nations(get_nations_db_path())
                    last_fetched = file_content['last_fetched']
                    break
                except Exception as e:
                    logger.debug(f"Attempt {i + 1} to load nations failed: {e}")
                    last_load_exception = e
            
            if not last_fetched or not file_content:
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
                    "If this keeps happening for hours, contact RandomNoobster#0093 with the reference below.",
                    reference=ref,
                )
                await ctx.followup.send(embed=embed)
                return
            new_turn: bool = datetime.fromtimestamp(last_fetched).hour % 2 != 0 and datetime.utcnow().hour % 2 == 0
                
            embed1 = discord.Embed(title=f"Configuration", description="Do you want to use the same configuration (presenatation & filters) that you used last time running this command?", color=0xff5100)
            embed2 = discord.Embed(title=f"Presentation", description="How do you want to get your targets?\n\nEmbed on discord returns a paginated embed with some information about each nation. Use this if you can't use the webpage for whatever reason.\n\nMessage on discord returns a small list of the nations with the highest recent beige loot. Use this if you are very lazy.\n\nAs a webpage returns a link to a webpage with a sortable table that has lots of important information about each nation. If used well, this gives you the best targets.", color=0xff5100)
            embed3 = discord.Embed(title=f"Filters (1/6)", description="What nations do you want to include?", color=0xff5100)
            embed4 = discord.Embed(title=f"Filters (2/6)", description="How many active defensive wars should they have?", color=0xff5100)
            embed5 = discord.Embed(title=f"Filters (3/6)", description="How inactive should they be?", color=0xff5100)
            embed6 = discord.Embed(title=f"Filters (4/6)", description="Do you want to include beige nations?", color=0xff5100)
            embed7 = discord.Embed(title=f"Filters (5/6)", description="Should there be a minimum previous beige loot?", color=0xff5100)
            embed8 = discord.Embed(title=f"Filters (6/6)", description='Do you want to improve performance by filtering out "bad" targets?\n\nMore specifically, this will omit nations with negative income, nations that have a stronger ground force than you, and nations that were previously beiged for $0.', color=0xff5100)

            option_list = [(embed1, stage_one()), (embed2, stage_two()), (embed3, stage_three()), (embed4, stage_four()), (embed5, stage_five()), (embed6, stage_six()), (embed7, stage_seven()), (embed8, stage_eight())]
            db = db_mongo.get_db()
            user = await db.global_users.find_one({"user": ctx.author.id})
            saved_raids_cfg = user.get("raids_config") if user else None
            if not isinstance(saved_raids_cfg, dict) or "webpage" not in saved_raids_cfg:
                option_list.pop(0)

            for embed, view in option_list:
                await ctx.edit(content="", embed=embed, view=view)
                timed_out = await view.wait()
                if timed_out:
                    return
                if use_same == True:
                    cfg = user["raids_config"]
                    webpage = cfg["webpage"]
                    discord_embed = cfg["discord_embed"]
                    who = cfg["who"]
                    max_wars = cfg["max_wars"]
                    inactive_limit = cfg["inactive_limit"]
                    beige = cfg["beige"]
                    performace_filter = cfg["performace_filter"]
                    # this was added later on when some people may not have it in their raid_config
                    # which makes this check necessary (null in DB must not become None here)
                    minimum_beige_loot = cfg.get("minimum_beige_loot")
                    if minimum_beige_loot is None:
                        minimum_beige_loot = 0
                    break

            if ctx.guild:
                if guild_config := await db.guild_configs.find_one({"guild_id": ctx.guild.id}):
                    if "dnr_alliance_ids" in guild_config:
                        dnr_alliance_ids = guild_config['dnr_alliance_ids']
                    else:
                        dnr_alliance_ids = []
                else:
                    dnr_alliance_ids = []
            else:
                dnr_alliance_ids = []

            if minimum_beige_loot is None:
                minimum_beige_loot = 0

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
                            "performace_filter": performace_filter,
                            "minimum_beige_loot": minimum_beige_loot,
                        }
                    }
                },
            )
            
            view = None

            if webpage:
                scope_param = None
                if who == " alliance_position:[0,1]":
                    scope_param = "apps_or_none"
                elif who == " alliance_id:0":
                    scope_param = "no_alliance"

                params = {
                    "attackerNationId": atck_ntn.get("id", ""),
                    "maxWars": max_wars if max_wars != 3 else None,
                    "inactiveMinDays": inactive_limit if inactive_limit else None,
                    "scope": scope_param,
                    "minBeigeLoot": minimum_beige_loot if minimum_beige_loot else None,
                    "performance": True if performace_filter else None,
                    "minScore": int(minscore) if minscore is not None else None,
                    "maxScore": int(maxscore) if maxscore is not None else None,
                }
                if beige is False:
                    params["beige"] = "false"

                clean_params = {k: v for k, v in params.items() if v is not None and v != ""}
                raids_query = urllib.parse.urlencode(clean_params)
                raids_redirect = f"/raids?{raids_query}"
                raids_url = f"{WEB_BASE_URL}{raids_redirect}"
                if not DISCORD_BOT_API_KEY:
                    ref = err_util.new_error_reference()
                    logger.error(
                        "raids_token_config_missing reference=%r",
                        ref,
                        extra={"error_reference": ref},
                    )
                    embed = err_util.error_embed(
                        "Configuration error",
                        "Secure token issuance is not configured. Please contact an admin.",
                        reference=ref,
                    )
                    await ctx.edit(content="", embed=embed, view=None)
                    return

                issue_url = f"{API_BASE_URL}/api/auth/token/issue"
                payload = {
                    "user_id": ctx.author.id,
                    "data_type": "raids",
                    "expires_in": 3600,
                }

                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            issue_url,
                            json=payload,
                            headers={"X-Bot-Token": DISCORD_BOT_API_KEY},
                            timeout=aiohttp.ClientTimeout(total=10),
                        ) as resp:
                            if resp.status != 200:
                                error_text = await resp.text()
                                ref = err_util.new_error_reference()
                                logger.error(
                                    "raids_token_issue_http reference=%r status=%s body=%s",
                                    ref,
                                    resp.status,
                                    error_text[:800],
                                    extra={"error_reference": ref},
                                )
                                embed = err_util.error_embed(
                                    "Web link unavailable",
                                    "I couldn't issue a secure web token. Please try again later.",
                                    reference=ref,
                                )
                                await ctx.edit(content="", embed=embed, view=None)
                                return
                            data = await resp.json()
                except Exception as e:
                    ref = err_util.new_error_reference()
                    logger.error(
                        "raids_token_issue_exception reference=%r issue_url=%s",
                        ref,
                        issue_url,
                        exc_info=True,
                        extra={"error_reference": ref},
                    )
                    await err_util.report_handled_exception(
                        self.bot,
                        ctx,
                        e,
                        logger,
                        reference=ref,
                        command_name="raids",
                    )
                    embed = err_util.error_embed(
                        "Web link unavailable",
                        "I couldn't reach the auth service. Please try again later.",
                        reference=ref,
                    )
                    await ctx.edit(content="", embed=embed, view=None)
                    return

                code = data.get("code")
                if not code:
                    ref = err_util.new_error_reference()
                    logger.error(
                        "raids_token_issue_empty_code reference=%r",
                        ref,
                        extra={"error_reference": ref},
                    )
                    embed = err_util.error_embed(
                        "Web link unavailable",
                        "I couldn't issue a secure web token. Please try again later.",
                        reference=ref,
                    )
                    await ctx.edit(content="", embed=embed, view=None)
                    return

                token_url = (
                    f"{WEB_BASE_URL}/token-request?type=raids"
                    f"&redirect={urllib.parse.quote(raids_redirect)}"
                    "&auto=true"
                    f"&code={urllib.parse.quote(code)}"
                )

                webpage_embed = discord.Embed(
                    title="Targets ready",
                    description=(
                        "Your configuration has been sent to the raids page. "
                        "Click the button below to get your personal link."
                    ),
                    color=0xff5100,
                )

                class webpage_view(discord.ui.View):
                    def __init__(self):
                        super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())
                        btn = discord.ui.Button(
                            label="Get your link",
                            style=discord.ButtonStyle.primary,
                        )
                        btn.callback = self.send_link
                        self.add_item(btn)

                    async def send_link(self, interaction: discord.Interaction):
                        if interaction.user != ctx.author:
                            await interaction.response.send_message(
                                "This button is reserved for the person who ran the command!",
                                ephemeral=True,
                            )
                            return
                        await interaction.response.send_message(
                            f"Here is your personal link (do not share it):\n{token_url}",
                            ephemeral=True,
                        )

                    async def on_timeout(self):
                        await views.run_timeout(ctx, view)

                view = webpage_view()
                await ctx.edit(content="", attachments=[], embed=webpage_embed, view=view)
                return

            await ctx.edit(content="Getting targets...", view=view, embed=None)
            done_jobs = [{"data": {"nations": {"data": file_content['nations']}}}]

            await ctx.edit(content="Caching targets...")
            temp, colors, prices, treasures, radiation, seasonal_mod = await pre_revenue_calc(
                ctx,
                query_for_nation=False,
                parsed_nation=atck_ntn,
                call_func=call_api,
                get_query_func=get_query,
                queries_module=queries,
            )
            for done_job in done_jobs:
                for x in done_job['data']['nations']['data']:
                    if who == " alliance_position:[0,1]":
                        if x['alliance_position'] not in ["NOALLIANCE", "APPLICANT"]:
                            continue
                    elif who == " alliance_id:0":
                        if x['alliance_id'] != "0":
                            continue
                    nation_score = x.get('score')
                    if nation_score is None:
                        continue
                    if not minscore < nation_score < maxscore:
                        continue
                    if beige:
                        pass
                    else:
                        if x['color'] == "beige":
                            continue
                        else: 
                            pass
                    used_slots = 0
                    for war in x['wars']:
                        tl = war.get('turnsleft') or 0
                        if tl > 0 and war['defid'] == x['id']:
                            used_slots += 1
                        for attack in war['attacks']:
                            if attack['loot_info']:
                                attack['loot_info'] = attack['loot_info'].replace("\r\n", "")
                    if x['alliance_id'] in ["4729", "8819"] + dnr_alliance_ids:
                        continue
                    if used_slots > max_wars:
                        continue
                    if (datetime.utcnow() - datetime.strptime(x['last_active'], "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=None)).days < inactive_limit:
                        continue

                    # minimum loot filter start
                    x['def_slots'] = 0
                    x['time_since_war'] = "14+"
                    
                    if x['wars'] != []:
                        for war in x['wars']:
                            if war['date'] == '-0001-11-30 00:00:00':
                                x['wars'].remove(war)
                            elif war['defid'] == x['id']:
                                if (war.get('turnsleft') or 0) > 0:
                                    x['def_slots'] += 1
                                
                        wars = sorted(x['wars'], key=lambda k: k['date'], reverse=True)
                        war = wars[0]
                        if x['def_slots'] == 0:
                            x['time_since_war'] = (datetime.utcnow() - datetime.strptime(war['date'], "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=None)).days
                        else:
                            x['time_since_war'] = "Ongoing"
                        for war in wars:
                            if (war.get('turnsleft') or 0) <= 0:
                                loot_value, loot_text = compute_beige_loot_or_zero(x, prices)
                                x['nation_loot_value'] = loot_value
                                x['nation_loot'] = loot_text
                                break

                    if "nation_loot_value" not in x:
                        x['nation_loot'] = "NaN"
                        x['nation_loot_value'] = 0
                    
                    nation_loot_value = x.get('nation_loot_value')
                    if nation_loot_value is None:
                        nation_loot_value = 0
                    x['nation_loot_value'] = nation_loot_value
                    if nation_loot_value < minimum_beige_loot:
                        continue
                    # minimum loot filter end

                    if new_turn:
                        x['beige_turns'] -= 1
                        x['vacation_mode_turns'] -= 1
                    target_list.append(x)

                    
            if len(target_list) == 0:
                await ctx.edit(content="No targets matched your criteria!", attachments=[])
                return

            filters = f"Nation information was fetched <t:{last_fetched}:R>\n"
            filter_list = []
            if not beige or who != "" or max_wars != 3 or performace_filter or inactive_limit != 0 or minimum_beige_loot != 0 or dnr_alliance_ids != []:
                filters += "Active filters: "
                if not beige:
                    filter_list.append("hide beige nations")
                if who != "":
                    if who == " alliance_position:[0,1]":
                        filter_list.append("hide full alliance members")
                    elif who == " alliance_id:0":
                        filter_list.append("hide full alliance members and applicants")
                if max_wars != 3:
                    if max_wars == 0:
                        filter_list.append("0 active wars")
                    else:
                        filter_list.append(f"{max_wars} or less active wars")
                if performace_filter:
                    filter_list.append('omit "bad" targets')
                if inactive_limit != 0:
                    filter_list.append(f"hide nations that logged in within the last {inactive_limit} days")
                if minimum_beige_loot != 0:
                    filter_list.append(f"hide nations with less than ${minimum_beige_loot:,} previous beige loot".replace(",000,000","m"))
                if dnr_alliance_ids:
                    filter_list.append(f"hide {len(dnr_alliance_ids)} alliances marked as do not raid")
                filters = filters + ", ".join(filter_list)
            else:
                filters += "No active filters"

            await ctx.edit(content='Calculating best targets...')

            alliances = {
                str(x['id']): x
                for x in get_alliances_by_ids([str(x['alliance_id']) for x in target_list])
            }

            for target in target_list:
                embed = discord.Embed(title=f"{target['nation_name']}", url=f"https://politicsandwar.com/nation/id={target['id']}", description=f"{filters}\n\u200b", color=0xff5100)
                target['infrastructure'] = 0
                target_loot = target.get("nation_loot")
                if not target_loot:
                    target_loot = "NaN"
                    target["nation_loot"] = target_loot
                
                embed.add_field(name="Previous nation loot", value=target_loot)

                if target['alliance_id'] != "0":
                    try:
                        target['taxable'] = (target['color'] == alliances[target['alliance_id']]['color'])
                    except KeyError:
                        # Here we are if the alliance is not in the cache
                        target['taxable'] = True
                else: 
                    target['taxable'] = False

                rev_obj = await revenue_calc(ctx, target, radiation, treasures, prices, colors, seasonal_mod)

                target['monetary_net_num'] = rev_obj['monetary_net_num']
                embed.add_field(name="Monetary Net Income", value=rev_obj['mon_net_txt'])
                
                target['net_cash_num'] = rev_obj['net_cash_num']
                target['money_txt'] = rev_obj['money_txt']
                embed.add_field(name="Net Cash Income", value=rev_obj['money_txt'])

                target['treasures'] = len(target['treasures'])
                embed.add_field(name="Treasures", value=target['treasures'])

                embed.add_field(name="Slots", value=f"{target['def_slots']}/3 used slots") 

                if target['last_active'] == '-0001-11-30 00:00:00':
                    days_inactive = 0
                else:
                    days_inactive = (datetime.utcnow() - datetime.strptime(target['last_active'], "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=None)).days

                for city in target['cities']:
                    target['infrastructure'] += city['infrastructure']

                embed.add_field(name="Beige", value=f"{target['beige_turns']} turns")

                embed.add_field(name="Inactivity", value=f"{days_inactive} days")

                if target['alliance']:
                    embed.add_field(name="Alliance", value=f"[{target['alliance']['name']}](https://politicsandwar.com/alliance/id={target['alliance_id']})\n{target['alliance_position'].lower().capitalize()}")
                else:
                    target['alliance'] = {"name": "None"}
                    embed.add_field(name="Alliance", value=f"No alliance")

                target['max_infra'] = rev_obj['max_infra']
                target['avg_infra'] = rev_obj['avg_infra']
                embed.add_field(name="Infra", value=f"Max: {rev_obj['max_infra']}\nAvg: {rev_obj['avg_infra']}")

                embed.add_field(name="Soldiers", value=f"{target['soldiers']:,} soldiers")

                embed.add_field(name="Tanks", value=f"{target['tanks']:,} tanks")

                embed.add_field(name="Aircraft", value=f"{target['aircraft']} aircraft")

                embed.add_field(name="Ships", value=f"{target['ships']:,} ships")

                embed.add_field(name="Nukes", value=f"{target['nukes']:,} nukes")

                embed.add_field(name="Missiles", value=f"{target['missiles']:,} missiles")
                
                # works perfectly fine, but the API is broken....
                # target['bounty_txt'] = "0"
                # bounty_info = {"ATTRITION": 0, "RAID": 0, "ORDINARY": 0, "NUCLEAR": 0}
                # for bounty in target['bounties']:
                #     if bounty['type'] == None:
                #         bounty['type'] = "NUCLEAR"
                #     bounty_info[bounty['type']] += bounty['amount']   
                # temp_list = []
                # for k, v in bounty_info.items():
                #     if v != 0:
                #         temp_list.append(f"{k.capitalize()}: ${v:,}")
                # target['bounty_txt'] = ", ".join(temp_list)

                ground_win_rate = self.winrate_calc((atck_ntn['soldiers'] * 1.75 + atck_ntn['tanks'] * 40), (target['soldiers'] * 1.75 + target['tanks'] * 40 + target['population'] * 0.0025))

                target['groundwin'] = ground_win_rate
                embed.add_field(name="Chance to get ground IT", value=str(round(100*ground_win_rate**3)) + "%")

                air_win_rate = self.winrate_calc((atck_ntn['aircraft'] * 3), (target['aircraft'] * 3))
                
                target['airwin'] = air_win_rate
                embed.add_field(name="Chance to get air IT", value=str(round(100*air_win_rate**3)) + "%")

                naval_win_rate = self.winrate_calc((atck_ntn['ships'] * 4), (target['ships'] * 4))
                
                target['navalwin'] = naval_win_rate
                embed.add_field(name="Chance to get naval IT", value=str(round(100*naval_win_rate**3)) + "%\n\u200b")

                target['winchance'] = round((ground_win_rate+air_win_rate+naval_win_rate)*100/3)

                if not webpage:
                    target['embed'] = embed

            if performace_filter:
                def determine(x):
                    if x['groundwin'] < .4 or x['nation_loot'] == "0" or x['net_cash_num'] < 10000:
                        return False
                    else:
                        return True
                target_list[:] = [target for target in target_list if determine(target)]
                if len(target_list) == 0:
                    await ctx.edit(content="No targets matched your criteria!", attachments=[])
                    no_timeout = True
                    return
                
            best_targets = sorted(target_list, key=lambda k: k['monetary_net_num'], reverse=True)

            if webpage:
                # Build URL for the frontend raids page using live API
                # The frontend will call the API with the user's token
                target_ids = [
                    int(target.get('id'))
                    for target in best_targets
                    if str(target.get('id', '')).isdigit()
                ]
                await db.global_users.find_one_and_update(
                    {"user": ctx.author.id},
                    {"$set": {
                        "raids_target_ids": target_ids,
                        "raids_target_generated": round(datetime.utcnow().timestamp()),
                    }},
                    upsert=True,
                )

                raids_query = f"attackerNationId={atck_ntn.get('id', '')}&useSavedTargets=true"
                raids_redirect = f"/raids?{raids_query}"
                raids_url = f"{WEB_BASE_URL}{raids_redirect}"
                if not DISCORD_BOT_API_KEY:
                    ref = err_util.new_error_reference()
                    logger.error(
                        "raids_token_config_missing reference=%r",
                        ref,
                        extra={"error_reference": ref},
                    )
                    embed = err_util.error_embed(
                        "Configuration error",
                        "Secure token issuance is not configured. Please contact an admin.",
                        reference=ref,
                    )
                    await ctx.edit(content="", embed=embed, view=None)
                    return

                issue_url = f"{API_BASE_URL}/api/auth/token/issue"
                payload = {
                    "user_id": ctx.author.id,
                    "data_type": "raids",
                    "expires_in": 3600,
                }

                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            issue_url,
                            json=payload,
                            headers={"X-Bot-Token": DISCORD_BOT_API_KEY},
                            timeout=aiohttp.ClientTimeout(total=10),
                        ) as resp:
                            if resp.status != 200:
                                error_text = await resp.text()
                                ref = err_util.new_error_reference()
                                logger.error(
                                    "raids_token_issue_http reference=%r status=%s body=%s",
                                    ref,
                                    resp.status,
                                    error_text[:800],
                                    extra={"error_reference": ref},
                                )
                                embed = err_util.error_embed(
                                    "Web link unavailable",
                                    "I couldn't issue a secure web token. Please try again later.",
                                    reference=ref,
                                )
                                await ctx.edit(content="", embed=embed, view=None)
                                return
                            data = await resp.json()
                except Exception as e:
                    ref = err_util.new_error_reference()
                    logger.error(
                        "raids_token_issue_exception reference=%r issue_url=%s",
                        ref,
                        issue_url,
                        exc_info=True,
                        extra={"error_reference": ref},
                    )
                    await err_util.report_handled_exception(
                        self.bot,
                        ctx,
                        e,
                        logger,
                        reference=ref,
                        command_name="raids",
                    )
                    embed = err_util.error_embed(
                        "Web link unavailable",
                        "I couldn't reach the auth service. Please try again later.",
                        reference=ref,
                    )
                    await ctx.edit(content="", embed=embed, view=None)
                    return

                code = data.get("code")
                if not code:
                    ref = err_util.new_error_reference()
                    logger.error(
                        "raids_token_issue_empty_code reference=%r",
                        ref,
                        extra={"error_reference": ref},
                    )
                    embed = err_util.error_embed(
                        "Web link unavailable",
                        "I couldn't issue a secure web token. Please try again later.",
                        reference=ref,
                    )
                    await ctx.edit(content="", embed=embed, view=None)
                    return

                token_url = (
                    f"{WEB_BASE_URL}/token-request?type=raids"
                    f"&redirect={urllib.parse.quote(raids_redirect)}"
                    "&auto=true"
                    f"&code={urllib.parse.quote(code)}"
                )
                
                webpage_embed = discord.Embed(title=f"Targets successfully gathered", description=f"{filters}\n\nYou can view your targets by pressing the button below.", color=0xff5100)
                class webpage_view(discord.ui.View):
                    def __init__(self):
                        super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())
                        self.add_item(
                            discord.ui.Button(
                                label="See your targets",
                                style=discord.ButtonStyle.link,
                                url=token_url,
                            )
                        )
                    
                    async def interaction_check(self, interaction) -> bool:
                        if interaction.user != ctx.author:
                            await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                            return False
                        else:
                            return True
                    
                    async def on_timeout(self):
                        await views.run_timeout(ctx, view)

                view = webpage_view()
                await ctx.edit(content="", attachments=[], embed=webpage_embed, view=view)
                return

            elif discord_embed:
                pages = len(target_list)
                cur_page = 1

                def get_embed(nation):
                    nonlocal pages, cur_page
                    embed = nation['embed']
                    if "*" in nation['money_txt']:
                        embed.set_footer(text=f"Page {cur_page}/{pages}  |  * the income if the nation is out of food.")
                    else:
                        embed.set_footer(text=f"Page {cur_page}/{pages}")
                    return embed

                msg_embd = get_embed(best_targets[0])
                timed_out = False

                class embed_paginator(discord.ui.View):
                    def __init__(self):
                            super().__init__(timeout=(when_to_timeout - datetime.utcnow()).total_seconds())

                    async def button_check(self, x):
                        beige_button = [x for x in self.children if x.custom_id == "beige"][0]
                        user = await db.global_users.find_one({"user": ctx.author.id})
                        for entry in user['beige_alerts']:
                            if x['id'] == entry:
                                beige_button.disabled = True
                                return
                        if x['beige_turns'] > 0:
                            beige_button.disabled = False
                        else:
                            beige_button.disabled = True
                    
                    @discord.ui.button(label="<<", style=discord.ButtonStyle.primary)
                    async def far_left_callback(self, b: discord.Button, i: discord.Interaction):
                        nonlocal cur_page
                        cur_page = 1
                        msg_embd = get_embed(best_targets[cur_page-1])
                        await self.button_check(best_targets[cur_page-1])
                        await i.response.edit_message(content="", embed=msg_embd, view=view)

                    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
                    async def left_callback(self, b: discord.Button, i: discord.Interaction):
                        nonlocal cur_page
                        if cur_page > 1:
                            cur_page -= 1
                            msg_embd = get_embed(best_targets[cur_page-1])
                            await self.button_check(best_targets[cur_page-1])
                            await i.response.edit_message(content="", embed=msg_embd, view=view)
                        else:
                            cur_page = pages
                            msg_embd = get_embed(best_targets[cur_page-1])
                            await self.button_check(best_targets[cur_page-1])
                            await i.response.edit_message(content="", embed=msg_embd, view=view)
                    
                    @discord.ui.button(label=">", style=discord.ButtonStyle.primary)
                    async def right_callback(self, b: discord.Button, i: discord.Interaction):
                        nonlocal cur_page
                        if cur_page != pages:
                            cur_page += 1
                            msg_embd = get_embed(best_targets[cur_page-1])
                            await self.button_check(best_targets[cur_page-1])
                            await i.response.edit_message(content="", embed=msg_embd, view=view)
                        else:
                            cur_page = 1
                            msg_embd = get_embed(best_targets[cur_page-1])
                            await self.button_check(best_targets[cur_page-1])
                            await i.response.edit_message(content="", embed=msg_embd, view=view)

                    @discord.ui.button(label=">>", style=discord.ButtonStyle.primary)
                    async def far_right_callback(self, b: discord.Button, i: discord.Interaction):
                        nonlocal cur_page
                        cur_page = pages
                        msg_embd = get_embed(best_targets[cur_page-1])
                        await self.button_check(best_targets[cur_page-1])
                        await i.response.edit_message(content="", embed=msg_embd, view=view)
                
                    if best_targets[0]['beige_turns'] > 0:
                        disabled = False
                    else:
                        disabled = True

                    @discord.ui.button(label="Beige reminder", style=discord.ButtonStyle.primary, disabled=disabled, custom_id="beige")
                    async def beige_callback(self, b: discord.Button, i: discord.Interaction):
                        nonlocal cur_page
                        beige_button = [x for x in self.children if x.custom_id == "beige"][0]
                        cur_embed = best_targets[cur_page-1]
                        turns = cur_embed['beige_turns']
                        if turns == 0:
                            beige_button.disabled = True
                            await ctx.edit(view=view)
                            await i.response.send_message(content=f"They are not in beige!", ephemeral=True)
                            return
                        reminder = cur_embed['id']
                        user = await db.global_users.find_one({"user": ctx.author.id})
                        if user == None:
                            await i.response.send_message(content=f"I didn't find you in the database! Make sure to `/verify`!", ephemeral=True)
                            return
                        for entry in user['beige_alerts']:
                            if reminder == entry:
                                beige_button.disabled = True
                                await ctx.edit(view=view)
                                await i.response.send_message(content=f"You already have a beige reminder for this nation!", ephemeral=True)
                                return
                        await db.global_users.find_one_and_update({"user": ctx.author.id}, {"$push": {"beige_alerts": reminder}})
                        beige_button.disabled = True
                        await ctx.edit(view=view)
                        await i.response.send_message(content=f"A beige reminder for <https://politicsandwar.com/nation/id={cur_embed['id']}> was added!", ephemeral=True)

                    async def interaction_check(self, interaction) -> bool:
                        if interaction.user != ctx.author:
                            await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                            return False
                        else:
                            return True
                    
                    async def on_timeout(self):
                        await views.run_timeout(ctx, view)
                    
                view = embed_paginator()
                await ctx.edit(content="", embed=msg_embd, attachments=[], view=view)

            else:
                targets = sorted(best_targets, key=lambda k: k['nation_loot_value'], reverse=True)
                desc = filters
                for n in range(min(20, len(targets))):
                    target = targets[n]
                    desc += f"\n\n**Last beige: ${target['nation_loot']}**\n[{target['nation_name']}](https://politicsandwar.com/nation/id={target['id']}) | Active: <t:{round(datetime.strptime(target['last_active'], '%Y-%m-%dT%H:%M:%S%z').timestamp())}:R> | Ground IT: {round(100*target['groundwin']**3)}%"
                embed = discord.Embed(title="Top nations by beige loot", description=desc, color=0xff5100)
                embed.set_footer(text="Contact RandomNoobster#0093 for help or bug reports")
                await ctx.edit(content="", embed=embed, attachments=[], view=None)

        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="raids")
            return
    
    reminder_group = SlashCommandGroup("reminders", "Manage beige exit reminder notifications")

    @reminder_group.command(
        name="show",
        description="View all your active beige exit reminders",
    )
    async def reminders(self, ctx: discord.ApplicationContext):
        try:
            await ctx.defer()
            person = await db.global_users.find_one({"user": ctx.author.id})

            if person == None:
                await ctx.respond(content=f"I didn't find you in the database! Make sure that you have verified your nation!")
                return

            if person['beige_alerts'] == []:
                insults = ['ha loser', 'what a nub', 'such a pleb', 'get gud', 'u suc lol', 'ur useless lmao']
                insult = random.choice(insults)
                await ctx.respond(content=f"You have no beige reminders!\n\n||{insult}||")
                return

            res = (await api_client.call(f"{{nations(id:[{','.join(person['beige_alerts'])}]){{data{get_query(queries.REMINDERS)}}}}}", api_key))['data']['nations']['data']

            reminders = []
            for alert in person['beige_alerts']:
                for nation in res:
                    if alert == nation['id']:
                        beige_turns = int(nation['beige_turns'])
                        vacation_mode_turns = int(nation['vacation_mode_turns'])
                        turns = sorted([beige_turns, vacation_mode_turns])[1]
                        time = datetime.utcnow()
                        if time.hour % 2 == 0:
                            time += timedelta(hours=turns*2)
                        else:
                            time += timedelta(hours=turns*2-1)
                        time = datetime(time.year, time.month, time.day, time.hour)
                        reminders.append(f"\n<t:{round(time.timestamp())}> <t:{round(time.timestamp())}:R> - [{nation['nation_name']}](https://politicsandwar.com/nation/id={alert})")

            reminders = sorted(reminders)
            embeds = []

            for n in range(0, len(reminders), 20):
                embed = discord.Embed(title="Beige reminders", description="".join(reminders[n:n+20]), color=0xff5100)
                embeds.append(embed)

            if len(embeds) > 1:
                cur_page = 0
                pages = len(embeds)
                class switch(discord.ui.View):
                    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
                    async def left_callback(self, b: discord.Button, i: discord.Interaction):
                        nonlocal cur_page
                        if cur_page == 0:
                            cur_page = pages - 1
                            await i.response.edit_message(embed=embeds[cur_page])
                        else:
                            cur_page -= 1
                            await i.response.edit_message(embed=embeds[cur_page])
                    
                    @discord.ui.button(label=">", style=discord.ButtonStyle.primary)
                    async def right_callback(self, b: discord.Button, i: discord.Interaction):
                        nonlocal cur_page
                        if cur_page == pages - 1:
                            cur_page = 0
                            await i.response.edit_message(embed=embeds[cur_page])
                        else:
                            cur_page += 1
                            await i.response.edit_message(embed=embeds[cur_page])
                    
                    async def interaction_check(self, interaction) -> bool:
                        if interaction.user != ctx.author:
                            await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                            return False
                        else:
                            return True
                    
                    async def on_timeout(self):
                        await views.run_timeout(ctx, view)
                
                view = switch()
            else:
                view = None

            await ctx.respond(embed=embeds[0])
            if view != None:
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
            await ctx.defer()
            person = await db.global_users.find_one({"user": ctx.author.id})
            if person == None:
                await ctx.respond(content=f"I didn't find you in the database! Make sure that you have verified your nation!")
                return
            parsed_nation = sqlite_find_nation(nation)
            if parsed_nation == None:
                await ctx.respond("I could not find that nation!")
                return
            else:
                id = str(parsed_nation['id'])

            found = False
            for alert in person['beige_alerts']:
                if alert == id:
                    person['beige_alerts'].remove(alert)
                    found = True
                    break

            if not found:
                await ctx.respond(content="I did not find a reminder for that nation!")
                return

            await db.global_users.find_one_and_update({"user": ctx.author.id}, {"$pull": {"beige_alerts": id}})
            await ctx.respond(content=f"Your beige reminder for https://politicsandwar.com/nation/id={id} was deleted.")

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
            await ctx.defer()
            nation = sqlite_find_nation(nation)

            if nation == None:
                await ctx.respond(content='I could not find that nation!')
                return

            res = (await api_client.call(f"{{nations(first:1 id:{nation['id']}){{data{get_query(queries.REMINDERS)}}}}}", api_key))['data']['nations']['data'][0]

            if res['beige_turns'] == 0 and res['vacation_mode_turns'] == 0:
                await ctx.respond(content="They are not in beige or vacation mode!")
                return

            reminder = str(nation['id'])
            user = await db.global_users.find_one({"user": ctx.author.id})

            if user == None:
                await ctx.respond(content=f"I didn't find you in the database! Make sure that you have verified your nation!")
                return

            for entry in user['beige_alerts']:
                if reminder == entry:
                    await ctx.respond(content=f"You already have a beige reminder for this nation!")
                    return

            await db.global_users.find_one_and_update({"user": ctx.author.id}, {"$push": {"beige_alerts": reminder}})
            await ctx.respond(content=f"A beige reminder for https://politicsandwar.com/nation/id={nation['id']} was added.")

        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="reminders add")
            return

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

            if nation1 == None and nation2:
                nation1 = nation2
                nation2 = None

            if nation1 == None:
                nation1 = ctx.author.id
            nation1_nation = await helpers.find_nation_plus(self.bot, nation1)
            if not nation1_nation:
                if nation2 == None:
                    await ctx.respond(content='I could not find that nation!')
                    return
                else:
                    await ctx.respond(content='I could not find nation 1!')
                    return 
            nation1_id = str(nation1_nation['id'])

            done = False
            if isinstance(ctx.channel, discord.Thread) and nation2 == None:
                try:
                    chan = ctx.channel.name
                    nation2_id = str(chan[chan.index("(")+1:-1])
                    done = True
                except (ValueError, IndexError):
                    pass

            if not done:
                if nation2 == None:
                    nation2 = ctx.author.id
                nation2_nation = await helpers.find_nation_plus(self.bot, nation2)
                if not nation2_nation:
                    if nation2 == None:
                        await ctx.respond(content='I was able to find the nation you linked, but I could not find *your* nation!')
                        return
                    else:
                        await ctx.respond(content='I could not find nation 2!')
                        return 
                nation2_id = str(nation2_nation['id'])

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
            
            embed.add_field(name="Casualties", value=f"*Targeting air:*\nAtt. Plane: {results['nation1_airvair_nation1_avg']:,} ± {results['nation1_airvair_nation1_diff']:,}\nDef. Plane: {results['nation1_airvair_nation2_avg']:,} ± {results['nation1_airvair_nation2_diff']:,}\n\n*Targeting other:*\nAtt. Plane: {results['nation1_airvother_nation1_avg']:,} ± {results['nation1_airvother_nation1_diff']:,}\nDef. Plane: {results['nation1_airvother_nation2_avg']:,} ± {results['nation1_airvother_nation2_diff']:,}\n\u200b")        
            embed1.add_field(name="Casualties", value=f"*Targeting air:*\nAtt. Plane: {results['nation2_airvair_nation2_avg']:,} ± {results['nation2_airvair_nation2_diff']:,}\nDef. Plane: {results['nation2_airvair_nation1_avg']:,} ± {results['nation2_airvair_nation1_diff']:,}\n\n*Targeting other:*\nAtt. Plane: {results['nation2_airvother_nation2_avg']:,} ± {results['nation2_airvother_nation2_diff']:,}\nDef. Plane: {results['nation2_airvother_nation1_avg']:,} ± {results['nation2_airvother_nation1_diff']:,}\n\u200b")        

            embed.add_field(name="Casualties", value=f"*Targeting other:*\nAtt. Ships: {results['nation1_navalvinfra_nation1_avg']:,} ± {results['nation1_navalvinfra_nation1_diff']:,}\nDef. Ships: {results['nation1_navalvinfra_nation2_avg']:,} ± {results['nation1_navalvinfra_nation2_diff']:,}\n\n*Targeting ships:*\nAtt. Ships: {results['nation1_navalvships_nation1_avg']:,} ± {results['nation1_navalvships_nation1_diff']:,}\nDef. Ships: {results['nation1_navalvships_nation2_avg']:,} ± {results['nation1_navalvships_nation2_diff']:,}")        
            embed1.add_field(name="Casualties", value=f"*Targeting other:*\nAtt. Ships: {results['nation2_navalvinfra_nation2_avg']:,} ± {results['nation2_navalvinfra_nation2_diff']:,}\nDef. Ships: {results['nation2_navalvinfra_nation1_avg']:,} ± {results['nation2_navalvinfra_nation1_diff']:,}\n\n*Targeting ships:*\nAtt. Ships: {results['nation2_navalvships_nation2_avg']:,} ± {results['nation2_navalvships_nation2_diff']:,}\nDef. Ships: {results['nation2_navalvships_nation1_avg']:,} ± {results['nation2_navalvships_nation1_diff']:,}")        

            cur_page = 1

            # Build URL for the frontend damage page using live API
            nation1_id = results.get('nation1', {}).get('id', '')
            nation2_id = results.get('nation2', {}).get('id', '')
            url = f"{WEB_BASE_URL}/damage?nation1={nation1_id}&nation2={nation2_id}"

            class switch(discord.ui.View):
                def __init__(self):
                    super().__init__(discord.ui.Button(label="Damage sheet", url=url))

                @discord.ui.button(label="Switch attacker/defender", style=discord.ButtonStyle.primary)
                async def callback(self, b: discord.Button, i: discord.Interaction):
                    nonlocal cur_page
                    if cur_page == 1:
                        cur_page = 2
                        await i.response.edit_message(embed=embed1)
                    else:
                        cur_page = 1
                        await i.response.edit_message(embed=embed)
                
                async def interaction_check(self, interaction) -> bool:
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
                        return False
                    else:
                        return True
                
                async def on_timeout(self):
                    ref = err_util.new_error_reference()
                    to_embed = err_util.error_embed(
                        "Timed out",
                        f"<@{ctx.author.id}> You didn't respond in time, so this command closed.",
                        reference=ref,
                    )
                    await ctx.edit(content="", embed=to_embed)
                    
            await ctx.respond(embed=embed, content="", view=switch())
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
        await ctx.defer()
        if not nation:
            if isinstance(ctx.channel, discord.Thread) and "(" in ctx.channel.name and ")" in ctx.channel.name:
                nation_id = ctx.channel.name[ctx.channel.name.rfind("(")+1:-1]
                int(nation_id) # throw an error if not a number
            else:
                try:
                    person = await helpers.find_user(self.bot, ctx.author.id)
                    nation_id = person['id']
                except Exception:
                    await ctx.respond("I do not know who to find the war status of.")
                    return
        else:
            person = await helpers.find_nation_plus(self.bot, nation)
            if not person:
                await ctx.respond("I could not find that nation!")
                return
            nation_id = str(person['id'])

        nation = (await api_client.call(f"{{nations(first:1 id:{nation_id}) {{data{get_query(queries.WAR_STATUS)}}}}}", api_key))['data']['nations']['data'][0]

        if nation['pirate_economy']:
            max_offense = 6
        if nation['advanced_pirate_economy']:
            max_offense = 7
        else:
            max_offense = 5

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

        desc = f"[{nation['nation_name']}](https://politicsandwar.com/nation/id={nation['id']}) | {alliance}\n\nLast login: <t:{round(datetime.strptime(nation['last_active'], '%Y-%m-%dT%H:%M:%S%z').timestamp())}:R>\nOffensive wars: {len(nation['offensive_wars'])}/{max_offense}\nDefensive wars: {len(nation['defensive_wars'])}/3\nDefensive range: {round(nation['score'] / 2.5)} - {round(nation['score'] / 0.75)}\nCities: {nation['num_cities']}\nBeige (turns): {nation['beigeturns']}\n\nSoldiers: **{nation['soldiers']:,}** / {max_sol:,}\nTanks: **{nation['tanks']:,}** / {max_tnk:,}\nPlanes: **{nation['aircraft']:,}** / {max_pln:,}\nShips: **{nation['ships']:,}** / {max_shp:,}"
        embed = discord.Embed(title=f"{nation['nation_name']} ({nation['id']}) & their wars", description=desc, color=0xff5100)
        embed1 = discord.Embed(title=f"{nation['nation_name']} ({nation['id']}) & their wars", description=desc, color=0xff5100)
        embed2 = discord.Embed(title=f"{nation['nation_name']} ({nation['id']}) & their wars", description=desc, color=0xff5100)
        embed.set_footer(text=f"\nThe chance to get immense triumphs is if the nation attacks {nation['nation_name']}. On average, it's worth attacking if the % is above 13%. Use /battlesimulation for more detailed predictions.")
        embed1.set_footer(text=f"\nThe chance to get immense triumphs is if the nation attacks {nation['nation_name']}. On average, it's worth attacking if the % is above 13%. Use /battlesimulation for more detailed predictions.")
        embed2.set_footer(text=f"\nThese are the average net damage per MAP predictions for the nations in question. Negative numbers means the net damage would be negative (not good). Use /damage for more detailed predictions.")
        n = 1

        for war in nation['wars']:
            n += 1
            if n % 2 == 0:
                embed.add_field(name="\u200b", value="\u200b", inline=False)
                embed1.add_field(name="\u200b", value="\u200b", inline=False)
                embed2.add_field(name="\u200b", value="\u200b", inline=False)
            else:
                embed.add_field(name="\u200b", value="\u200b", inline=True)
                embed1.add_field(name="\u200b", value="\u200b", inline=True)
                embed2.add_field(name="\u200b", value="\u200b", inline=True)

            if war in nation['offensive_wars']:
                result = await self.battle_calc(nation1=nation, nation2_id=war['defender']['id'])
                war_emoji_1 = "<:offensive_swords:1054714270547447828>"
                war_emoji_2 = "<:defensive_shield:1054714196715110411>"
                x = war['defender']
                main_enemy_res = war['att_resistance']
                main_enemy_points = war['attpoints']
                their_enemy_points = war['defpoints']
                their_enemy_res = war['def_resistance']
            else:
                result = await self.battle_calc(nation1=nation, nation2_id=war['attacker']['id'])
                war_emoji_1 = "<:defensive_shield:1054714196715110411>"
                war_emoji_2 = "<:offensive_swords:1054714270547447828>"
                x = war['attacker']
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

            if x['pirate_economy']:
                max_offense = 6
            if x['advanced_pirate_economy']:
                max_offense = 7
            else:
                max_offense = 5
            
            if x['beigeturns'] > 0:
                beige = f"\nBeige (turns): {x['beigeturns']}"
            else:
                beige = ""

            x_milt = military_logic.militarization_checker(x)
            max_sol = x_milt['max_soldiers']
            max_tnk = x_milt['max_tanks']
            max_pln = x_milt['max_aircraft']
            max_shp = x_milt['max_ships']          

            if x['vmode'] > 0:
                vmstart = "~~"
                vmend = "~~"
            else:
                vmstart = ""
                vmend = ""

            x['offensive_wars'] = [y for y in x['wars'] if y['turnsleft'] > 0 and y['attid'] == x['id']]
            x['defensive_wars'] = [y for y in x['wars'] if y['turnsleft'] > 0 and y['defid'] == x['id']]

            if x['alliance']:
                alliance = f"[{x['alliance']['name']}](https://politicsandwar.com/alliance/id={x['alliance_id']})"
            else:
                alliance = "No alliance"

            embed.add_field(name=f"{x['nation_name']} ({x['id']})", value=f"{vmstart}[War timeline](https://politicsandwar.com/nation/war/timeline/war={war['id']}) | {alliance}\n\n{war_emoji_1} **[{nation['nation_name']}](https://politicsandwar.com/nation/id={nation['id']})**{result['nation1_append']}\n{main_enemy_bar}\n**{main_enemy_res}/100** | MAPs: **{main_enemy_points}/12**\n\n{war_emoji_2} **[{x['nation_name']}](https://politicsandwar.com/nation/id={x['id']})**{result['nation2_append']}\n{their_enemy_bar}\n**{their_enemy_res}/100** | MAPs: **{their_enemy_points}/12**\n\nExpiration (turns): {war['turnsleft']}\nLast login: <t:{round(datetime.strptime(x['last_active'], '%Y-%m-%dT%H:%M:%S%z').timestamp())}:R>\nOngoing wars: {len(x['offensive_wars'] + x['defensive_wars'])}\n\nGround IT chance: **{round(100 * result['nation2_ground_win_rate']**3)}%**\nAir IT chance: **{round(100 * result['nation2_air_win_rate']**3)}%**\nNaval IT chance: **{round(100 * result['nation2_naval_win_rate']**3)}%**{vmend}", inline=True)
            embed1.add_field(name=f"{x['nation_name']} ({x['id']})", value=f"{vmstart}[War timeline](https://politicsandwar.com/nation/war/timeline/war={war['id']}) | {alliance}\n\n{war_emoji_1} **[{nation['nation_name']}](https://politicsandwar.com/nation/id={nation['id']})**{result['nation1_append']}\n{war_emoji_2} **[{x['nation_name']}](https://politicsandwar.com/nation/id={x['id']})**{result['nation2_append']}\n\nOffensive wars: {len(x['offensive_wars'])}/{max_offense}\nDefensive wars: {len(x['defensive_wars'])}/3{beige}\n\n Soldiers: **{x['soldiers']:,}** / {max_sol:,}\nTanks: **{x['tanks']:,}** / {max_tnk:,}\nPlanes: **{x['aircraft']:,}** / {max_pln:,}\nShips: **{x['ships']:,}** / {max_shp:,}\nMissiles: {x['missiles']}\nNukes: {x['nukes']}\n\nGround IT chance: **{round(100 * result['nation2_ground_win_rate']**3)}%**\nAir IT chance: **{round(100 * result['nation2_air_win_rate']**3)}%**\nNaval IT chance: **{round(100 * result['nation2_naval_win_rate']**3)}%**{vmend}", inline=True)
            embed2.add_field(name=f"{x['nation_name']} ({x['id']})", value=f"{vmstart}[War timeline](https://politicsandwar.com/nation/war/timeline/war={war['id']}) | {alliance}\n\n{war_emoji_1} **[{nation['nation_name']}](https://politicsandwar.com/nation/id={nation['id']})**{result['nation1_append']}\nGround: **${result['nation1_ground_net']/3:,.0f}**\nAir vs Air: **${result['nation1_airvair_net']/4:,.0f}**\nNaval vs Other: **${result['nation1_navalvinfra_net']/4:,.0f}**\nNaval vs Naval: **${result['nation1_navalvships_net']/4:,.0f}**\nMissile: **${result['nation1_missile_net']/8:,.0f}**\nNuke: **${result['nation1_nuke_net']/12:,.0f}** **\n\n{war_emoji_2} [{x['nation_name']}](https://politicsandwar.com/nation/id={x['id']})**{result['nation2_append']}\nGround: **${result['nation2_ground_net']/3:,.0f}**\nAir vs Air: **${result['nation2_airvair_net']/4:,.0f}**\nNaval vs Other: **${result['nation2_navalvinfra_net']/4:,.0f}**\nNaval vs Naval: **${result['nation2_navalvships_net']/4:,.0f}**\nMissile: **${result['nation2_missile_net']/8:,.0f}**\nNuke: **${result['nation2_nuke_net']/12:,.0f}**{vmend}", inline=True)

        class status_view(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)

            @discord.ui.button(label="General", style=discord.ButtonStyle.primary, custom_id="status_general", disabled=True)
            async def general_callback(self, b: discord.Button, i: discord.Interaction):
                this_button = [x for x in self.children if x.custom_id == "status_general"][0]
                other_buttons = [x for x in self.children if x.custom_id != "status_general"]
                for button in other_buttons:
                    button.disabled = False
                this_button.disabled = True
                await i.response.edit_message(content="", embed=embed, view=view)
            
            @discord.ui.button(label="Military", style=discord.ButtonStyle.primary, custom_id="status_military")
            async def military_callback(self, b: discord.Button, i: discord.Interaction):
                this_button = [x for x in self.children if x.custom_id == "status_military"][0]
                other_buttons = [x for x in self.children if x.custom_id != "status_military"]
                for button in other_buttons:
                    button.disabled = False
                this_button.disabled = True
                await i.response.edit_message(content="", embed=embed1, view=view)
            
            @discord.ui.button(label="Damage", style=discord.ButtonStyle.primary, custom_id="status_damage")
            async def damage_callback(self, b: discord.Button, i: discord.Interaction):
                this_button = [x for x in self.children if x.custom_id == "status_damage"][0]
                other_buttons = [x for x in self.children if x.custom_id != "status_damage"]
                for button in other_buttons:
                    button.disabled = False
                this_button.disabled = True
                await i.response.edit_message(content="", embed=embed2, view=view)
        
        view = status_view()
        print(embed.__sizeof__())
        print(embed1.__sizeof__())
        print(embed2.__sizeof__())
        await ctx.respond(content="", embed=embed, view=view)
    
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
        try:
            await ctx.respond("Let me think for a second...")
            
            user = await helpers.find_nation_plus(self.bot, ctx.author.id)
            if not user:
                await ctx.edit(content="Make sure that you are verified with `/verify`!")
                return
            
            config = await db.guild_configs.find_one({"guild_id": ctx.guild.id})

            fail = False
            if not config:
                fail = True
            else:
                try:
                    alliance_ids = config['targets_alliance_ids']
                    if len(alliance_ids) == 0:
                        fail = True
                except (KeyError, TypeError):
                    fail = True
            if fail:
                view = views.YesOrNoView(ctx=ctx)
                embed = discord.Embed(title="Targets not configured", description="This command has not been configured for this server. To configure targeted alliances, someone with the `manage_server` permission must use `/config`.\n\nDo you want to continue with all alliances being targeted?", color=0xff5100)
                await ctx.edit(content="", embed=embed, view=view)
                timed_out = await view.wait()
                if timed_out:
                    return
                if view.result == True:
                    await ctx.edit(content="Let me think for a second...", view=None, embed=None)
                    res = await api_client.call(f"{{nations(first:1 id:{user['id']}){{data{get_query(queries.NUKETARGETS)}}}}}", api_key)
                    user_nation = res['data']['nations']['data'][0]
                    file_content = get_all_nations(get_nations_db_path())
                    all_nations = file_content['nations']
                elif view.result == False:
                    await ctx.edit(content="Parsing of command was cancelled <:kekw:984765354452602880>", embed=None, view=None)
                    return
                else:
                    return
            
            if not fail:
                res = await api_client.call(f"{{nations(first:1 id:{user['id']}){{data{get_query(queries.NUKETARGETS)}}}}}", api_key)
                user_nation = res['data']['nations']['data'][0]
                minscore = round(user_nation['score'] * 0.75)
                maxscore = round(user_nation['score'] * 2.5)
                all_nations = await api_client.paginate_call(f"{{nations(first:150 page:page_number vmode:false max_score:{maxscore} min_score:{minscore} alliance_id:[{' '.join(alliance_ids)}]) {{paginatorInfo{{hasMorePages}} data{get_query(queries.NUKETARGETS)}}}}}", "nations", api_key)

            minscore = round(user_nation['score'] * 0.75)
            maxscore = round(user_nation['score'] * 2.5)
            nation_list = []
            for nation in all_nations:
                try:
                    if nation['score'] < minscore or nation['score'] > maxscore:
                        continue
                    if not include_beige:
                        if nation['vacation_mode_turns'] > 0 or nation['color'] == "beige":
                            continue
                    if not include_slotted:
                        skip = False
                        for war in user_nation['wars']:
                            if (war['attid'] == nation['id'] or war['defid'] == nation['id']) and war['turnsleft'] > -12:
                                skip = True
                                break
                        if skip:
                            continue
                        def_wars = 0
                        for war in nation['wars']:
                            if war['turnsleft'] > 0 and war['defid'] == nation['id']:
                                def_wars += 1
                        if def_wars == 3:
                            continue
                    nation['max_infra'] = sorted(nation['cities'], key=lambda x: x['infrastructure'], reverse=True)[0]['infrastructure']
                    avg_infra = 0
                    for city in nation['cities']:
                        avg_infra += city['infrastructure']
                    results = await self.battle_calc(nation1=user_nation, nation2=nation)
                    # should parallelize this https://stackoverflow.com/a/56162461/14466960
                    nation['nuke_cost'] = results['nation1_nuke_nation2_total']
                    nation['missile_cost'] = results['nation1_missile_nation2_total']
                    nation["avg_infra"] = avg_infra / len(nation['cities'])
                    nation_list.append(nation)
                except IndexError:
                    # IndexError if for some reason nation['cities'] is empty
                    pass

            if len(nation_list) == 0:
                await ctx.edit(content="No eligible targets found!")
                return
            
            if sort == "Nuke damage":
                sort_key = "nuke_cost"
            elif sort == "Missile damage":
                sort_key = "missile_cost"
            nation_list = sorted(nation_list, key=lambda x: x[sort_key], reverse=True)

            embeds = []
            for n in range(0, len(nation_list), 8):
                embed = discord.Embed(title="Nuke Targets", description="The damage numbers are calculated for ordinary wars - for attrition wars the damage is doubled. War policies and projects are accounted for when calculating damage. Use /damage for more detailed information about the damage dealt.", color=0xff5100)
                for i in range(n, min(n+10, len(nation_list))):
                    if i == n:
                        pass
                    elif i % 2 == 0:
                        embed.add_field(name="\u200b", value="\u200b", inline=False)
                    else:
                        embed.add_field(name="\u200b", value="\u200b", inline=True)
                    if nation_list[i]['alliance']:
                        alliance = f"[{nation_list[i]['alliance']['name']}](https://politicsandwar.com/alliance/id={nation_list[i]['alliance']['id']}) ({nation_list[i]['alliance_position'].capitalize()})"
                    else:
                        alliance = "No alliance"
                    embed.add_field(name=f"{nation_list[i]['nation_name']}", value=f"[Nation](https://politicsandwar.com/nation/id={nation_list[i]['id']}) | {alliance}\nDamage/nuke: `${nation_list[i]['nuke_cost']:,.0f}`\nDamage/missile: `${nation_list[i]['missile_cost']:,.0f}`\nMax infra: `{nation_list[i]['max_infra']:.0f}`\nAvg. infra: `{nation_list[i]['avg_infra']:.0f}`\nVital Defense: {'✅' if nation_list[i]['vds'] else '<:redcross:862669500977905694>'}\nIron Dome: {'✅' if nation_list[i]['irond'] else '<:redcross:862669500977905694>'}")
                embed.set_footer(text=f"Page {n/8+1:.0f}/{math.ceil(len(nation_list)/8)}")
                embeds.append(embed)
            
            if len(embeds) > 1:
                view = views.Switch(ctx=ctx, embeds=embeds, max_page=len(embeds))
            else:
                view = None

            await ctx.edit(embed=embeds[0], content="", view=view)

        except Exception as e:
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

            if nation1 == None and nation2:
                nation1 = nation2
                nation2 = None
                
            if nation1 == None:
                nation1 = ctx.author.id
            nation1_nation = await helpers.find_nation_plus(self.bot, nation1)
            if not nation1_nation:
                if nation2 == None:
                    await ctx.respond(content='I could not find that nation!')
                    return
                else:
                    await ctx.respond(content='I could not find nation 1!')
                    return 
            nation1_id = str(nation1_nation['id'])

            done = False
            if isinstance(ctx.channel, discord.Thread) and nation2 == None:
                try:
                    chan = ctx.channel.name
                    nation2_id = str(chan[chan.index("(")+1:-1])
                    done = True
                except (ValueError, IndexError):
                    pass

            if not done:
                if nation2 == None:
                    nation2 = ctx.author.id
                nation2_nation = await helpers.find_nation_plus(self.bot, nation2)
                if not nation2_nation:
                    if nation2 == None:
                        await ctx.respond(content='I was able to find the nation you linked, but I could not find *your* nation!')
                        return
                    else:
                        await ctx.respond(content='I could not find nation 2!')
                        return 
                nation2_id = str(nation2_nation['id'])
            
            results = await self.battle_calc(nation1_id, nation2_id)

            # Build URL for the frontend damage page using live API
            damage_url = f"{WEB_BASE_URL}/damage?nation1={nation1_id}&nation2={nation2_id}"

            await ctx.respond(content=f"Go to {damage_url}")
        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="damage")
            return

        
    async def battle_calc(
        self,
        nation1_id: Optional[str] = None,
        nation2_id: Optional[str] = None,
        nation1: Optional[Dict[str, Any]] = None,
        nation2: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return await calculate_damage_logic(
            call_pnw=call_api,
            nation1_id=nation1_id,
            nation2_id=nation2_id,
            nation1=nation1,
            nation2=nation2,
        )

def setup(bot):
    bot.add_cog(TargetFinding(bot))


