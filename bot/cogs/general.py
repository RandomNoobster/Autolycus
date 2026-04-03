"""General commands cog for Autolycus bot.

This module contains general-purpose commands including nation info,
revenue calculations, builds optimizer, and user management.
"""

import asyncio
import json
import logging
import os
import pathlib
import time
from datetime import datetime, timedelta
from functools import partial
from typing import Any, Dict, List, Optional

import discord
from discord.commands import Option, SlashCommandGroup, slash_command
from discord.ext import commands

from logic import queries
from database.mongo import get_db, get_global_user_by_any, listify
from database import sqlite_cache as db_utils
from database.users import delete_verification
from bot.discord_utils import help_data, helpers
from bot.discord_utils import errors as err_util
from bot.discord_utils.embeds import nation_overview_embed, verification_success_embed, verification_unlinked_embed
from bot.discord_utils.loading_display import LoadingDisplay
from logic.api_client import call, paginate_call
from logic.builds import calculate_builds as calculate_builds_logic
from logic.builds import generate_build_template
from logic.common import str_to_int
from logic.merge_utils import get_query
from logic.military import militarization_checker
from logic.revenue import pre_revenue_calc, revenue_calc
from logic.verification import verify_discord_nation_link
from core.config import AUTOLYCUS_WEB_BASE_URL

logger = logging.getLogger(__name__)

api_key = os.getenv("API_KEY")
call_api = partial(call, api_key=api_key)

class Background(commands.Cog):
    """General commands cog containing nation info, revenue, and builds commands."""

    def __init__(self, bot: discord.Bot) -> None:
        """Initialize the Background cog.
        
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
            "Command failed",
            (
                err_util.PNW_SERVER_USER_MESSAGE
                if err_util.is_pnw_server_error(error)
                else "I couldn't complete that request. Please try again in a moment."
            ),
            reference=ref,
        )
        await err_util.safe_reply_error(ctx, embed, ephemeral=True, reference=ref, log=logger)

    @slash_command(
        name="who",
        description="Look up detailed information about any nation",
    )
    async def who(
        self,
        ctx: discord.ApplicationContext,
        person: Option(str, "The person to look up") = None,
    ) -> None:
        """Display detailed information about a nation.
        
        Args:
            ctx: Discord application context.
            person: Discord ID or nation identifier (defaults to command author).
        """
        try:
            await ctx.defer()
            if person is None:
                person = ctx.author.id
            nation = await helpers.find_nation_plus(self.bot, person)
            if nation is None:
                await ctx.respond(content="I did not find that nation!")
                return

            nation = (await call_api(f"{{nations(first:1 id:{nation['id']}){{data{get_query(queries.WHO)}}}}}"))['data']['nations']['data'][0]

            user = await get_global_user_by_any(nation['id'])
            if not user:
                discord_info = "> Autolycus Verified: <:redcross:862669500977905694>"
                if nation['discord']:
                    discord_info += f"\n> Discord Username: {nation['discord']}"
            else:
                username = await self.bot.fetch_user(user['user'])
                discord_info = f"> Autolycus Verified: ✅\n> Discord Username: {username} `({username.id})`"

            if nation['alliance']:
                members = len([temp for temp in nation['alliance']['nations'] if temp['alliance_position'] != "APPLICANT"])
                alliance_info = f"> Alliance: [{nation['alliance']['name']}](https://politicsandwar.com/alliance/id={nation['alliance']['id']})\n> Position: {nation['alliance_position'].capitalize()}\n> Seniority: {nation['alliance_seniority']:,} days\n> Score: `{nation['alliance']['score']:,}`\n> Color: [{nation['alliance']['color'].capitalize()}](https://politicsandwar.com/leaderboards/display=color)\n> Members: `{members}`"
            else:
                alliance_info = f"> Alliance: None"

            milt = militarization_checker(nation)
            military_info = "> Format: \u200b \u200b \u200b`" + "Current".center(9) + "` `" + "Cap".center(9) + "` `" + "Daily".center(7) + "`\n> Soldiers: \u200a\u200b\u200a`" + f"{nation['soldiers']:,.0f}".rjust(9) + "` `" + f"{milt['max_soldiers']:,.0f}".rjust(9) + "` `" + f"{milt['soldiers_daily']:,.0f}".rjust(7) + "`\n> Tanks: \u200a \u200a \u200a \u200a \u200b`" + f"{nation['tanks']:,.0f}".rjust(9) + "` `" + f"{milt['max_tanks']:,.0f}".rjust(9) + "` `" + f"{milt['tanks_daily']:,.0f}".rjust(7) + "`\n> Aircraft: \u200b \u200b`" + f"{nation['aircraft']:,.0f}".rjust(9) + "` `" + f"{milt['max_aircraft']:,.0f}".rjust(9) + "` `" + f"{milt['aircraft_daily']:,.0f}".rjust(7) + "`\n> Ships:\u200a \u200a \u200a \u200a \u200a \u200a`" + f"{nation['ships']:,.0f}".rjust(9) + "` `" + f"{milt['max_ships']:,.0f}".rjust(9) + "` `" + f"{milt['ships_daily']:,.0f}".rjust(7) + f"`\n> \n> MMR: `{milt['barracks_mmr']}`/`{milt['factory_mmr']}`/`{milt['hangar_mmr']}`/`{milt['drydock_mmr']}`"

            missiles = str(nation['missiles'])
            if not nation['mlp']:
                missiles += " (No Project)"
            nukes = str(nation['nukes'])
            if not nation['nrf']:
                nukes += " (No Project)"

            o_wars = 0
            d_wars = 0
            for war in nation['wars']:
                if war['turnsleft'] > 0:
                    if war['attid'] == nation['id']:
                        o_wars += 1
                    else:
                        d_wars += 1

            dome = "Yes" if nation['irond'] else "No"
            vital = "Yes" if nation['vds'] else "No"
            max_offense = 7 if nation['advanced_pirate_economy'] else (6 if nation['pirate_economy'] else 5)

            military_info_2 = f"> Offensive Wars: `{o_wars}`/`{max_offense}`\n> Defensive Wars: `{d_wars}`/`3`\n> Missiles: `{missiles}`\n> Nukes: `{nukes}`\n> Iron Dome: {dome}\n> Vital Defense: {vital}\n> Turns of Beige: `{nation['beige_turns']}`"

            embed = nation_overview_embed(nation, discord_info, alliance_info, military_info, military_info_2)
            await ctx.respond(embed=embed)
        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="who")
            return

    @slash_command(
        name="builds",
        description="Find the optimal city builds for a given infra & land level",
    )
    async def build(
        self,
        ctx: discord.ApplicationContext,
        infra: Option(str, "How much infra the builds should be for"),
        land: Option(str, "How much land the builds should be for"),
        mmr: Option(str, "The minimum military requirement for the builds. Defaults to 0/0/0/0.") = "0/0/0/0",
        person: Option(str, "The person the builds should be for. Defaults to you.") = None
    ) -> None:
        """Find optimal city builds from stored JSON configurations.
        
        Args:
            ctx: Discord application context.
            infra: Target infrastructure level (must be multiple of 50).
            land: Target land amount.
            mmr: Military requirement (format: barracks/factory/hangar/drydock or "any").
            person: Discord ID or nation identifier (defaults to command author).
        """
        loading: LoadingDisplay | None = None
        try:
            await ctx.respond("Let me think a bit...")
            loading = LoadingDisplay(ctx, show_after=0)
            await loading.start("Let me think a bit...")

            target = person or ctx.author.id
            db_nation = await helpers.find_nation_plus(self.bot, target)
            if not db_nation:
                await ctx.edit(content="I could not find the specified person!", attachments=[])
                return

            infra_level = str_to_int(infra)
            if infra_level % 50 != 0:
                await ctx.edit(content="The amount of infra must be a multiple of 50!", attachments=[])
                return

            land_amount = str_to_int(land)

            try:
                perf_start = time.perf_counter()
                results = await calculate_builds_logic(
                    call_pnw=call_api,
                    nation_id=str(db_nation['id']),
                    infra=infra_level,
                    land=land_amount,
                    mmr=mmr,
                )
                perf_ms = int((time.perf_counter() - perf_start) * 1000)
                logger.info(
                    "[builds] completed ms=%s nation_id=%s infra=%s land=%s mmr=%s totalUnique=%s displayed=%s",
                    perf_ms,
                    db_nation.get("id"),
                    infra_level,
                    land_amount,
                    mmr,
                    results.get("totalUniqueBuilds"),
                    results.get("displayedUniqueBuilds"),
                )
            except ValueError as exc:
                reference = err_util.new_error_reference()
                err_util.log_command_error(logger, exc, ctx=ctx, reference=reference)
                embed = err_util.error_embed(
                    "Builds request failed",
                    "Could not run that builds query. Check **infrastructure** (multiple of 50), **land**, and **MMR** "
                    "using `barracks/factory/hangar/drydock` or `any`, then try again.",
                    reference=reference,
                )
                await ctx.edit(content="", embed=embed, attachments=[])
                return

            unique_builds = results.get("uniqueBuilds", [])
            total_unique_builds = results.get("totalUniqueBuilds", len(unique_builds))
            displayed_unique_builds = results.get("displayedUniqueBuilds", len(unique_builds))
            resources = results.get("resources", [])
            builds = results.get("builds", {})
            top_unique_builds = results.get("topUniqueBuilds", [])

            mmr_values = results.get("mmr") or {}
            mmr_display = "Any MMR"
            if mmr.lower() != "any" and isinstance(mmr_values, dict):
                mmr_display = "{}/{}/{}/{}".format(
                    mmr_values.get("barracks", 0),
                    mmr_values.get("factory", 0),
                    mmr_values.get("airforcebase", 0),
                    mmr_values.get("drydock", 0),
                )

            # Build URL parameters for the frontend builds page
            # The frontend will call the live API with these parameters
            builds_url = f"{AUTOLYCUS_WEB_BASE_URL}/builds?nationId={db_nation['id']}"

            embed = discord.Embed(
                title=f"Optimal City Builds for {infra_level} Infrastructure",
                url=builds_url,
                description=f"Evaluated **{total_unique_builds:,}** valid builds. Showing top **{displayed_unique_builds:,}**.",
                color=0xff5100,
            )

            criteria_text = (
                f"> Infrastructure: `{infra_level:,}`\n"
                f"> Land: `{land_amount:,}`\n"
                f"> MMR: `{mmr_display}`"
            )
            embed.add_field(name="Build Criteria", value=criteria_text, inline=False)

            best_build = None
            if unique_builds:
                best_build = unique_builds[0]
                revenue_text = f"> Net Income: `${best_build.get('net income', 0):,.2f}` per day"
                embed.add_field(name="Best Overall Build", value=revenue_text, inline=False)
                build_template = generate_build_template(best_build)
                embed.add_field(
                    name="Best Build Template",
                    value=f"```json\n{build_template}\n```",
                    inline=False,
                )

            link_text = f"[Click here to see all builds]({builds_url})"
            embed.add_field(name="View Detailed Results", value=link_text, inline=False)

            embed.set_footer(text="Contact randomnoobster for help or bug reports")

            await ctx.edit(content="", embed=embed, attachments=[])
        except Exception as e:
            if loading is not None:
                await loading.clear()
            await self._handle_command_exception(ctx, e, command_name="builds")
            return


    revenue_group = SlashCommandGroup("revenue", "Revenue calculators for nations and alliances")
    
    @revenue_group.command(
        name="nation",
        description="View a nation's full daily revenue breakdown",
    )
    async def nation_revenue(
        self,
        ctx: discord.ApplicationContext,
        person: Option(str, "The person you want to see the revenue of. Defaults to you.") = None
    ) -> None:
        """Calculate and display a nation's daily revenue.
        
        Args:
            ctx: Discord application context.
            person: Discord ID or nation identifier (defaults to command author).
        """
        loading: LoadingDisplay | None = None
        try:
            await ctx.respond('Stay with me...')
            loading = LoadingDisplay(ctx, show_after=0)
            await loading.start("Stay with me...")
            if person is None:
                person = ctx.author.id
            db_nation = await helpers.find_user(self.bot, person)

            if not db_nation:
                db_nation = await asyncio.to_thread(db_utils.find_nation, person)
                if not db_nation:
                    await ctx.edit(content='I could not find that person!', attachments=[])
                    return
                db_nation['nationid'] = db_nation['id']

            nation, colors, prices, treasures, radiation, seasonal_mod = await pre_revenue_calc(
                ctx,
                query_for_nation=True,
                nationid=db_nation['id'],
                call_func=call_api,
                get_query_func=get_query,
                queries_module=queries,
            )

            build_txt = "daily revenue"
            single_city = False

            rev_obj = await revenue_calc(
                ctx,
                nation,
                radiation,
                treasures,
                prices,
                colors,
                seasonal_mod,
                None,
                single_city,
                True,
            )

            embed = discord.Embed(
                title=f"{nation['leader_name']}'s {build_txt}:", url=f"https://politicsandwar.com/nation/id={db_nation['id']}", description="", color=0xff5100)
            
            embed.add_field(name="Incomes", value=rev_obj['income_txt'])
            embed.add_field(name="Expenses", value=rev_obj['expenses_txt'])
            embed.add_field(name="Net Revenue", value=rev_obj['net_rev_txt'])
            embed.add_field(name="Monetary Net Income", inline=False, value=rev_obj['mon_net_txt'])
            embed.set_footer(text=rev_obj['footer'])

            await ctx.edit(content="", embed=embed, attachments=[])
        except Exception as e:
            if loading is not None:
                await loading.clear()
            await self._handle_command_exception(ctx, e, command_name="revenue nation")
            return
    
    @revenue_group.command(
        name="alliance",
        description="View an alliance's total daily revenue across all members",
    )
    async def alliance_revenue(
        self,
        ctx: discord.ApplicationContext,
        alliance: Option(str, "The alliance you want to see the revenue of.", autocomplete=helpers.autocomplete_alliances),
        include_grey: Option(bool, "Do you want to include gray nations? Defaults to no.") = False
    ) -> None:
        """Calculate and display an alliance's total daily revenue.
        
        Args:
            ctx: Discord application context.
            alliance: Alliance name, ID, or acronym.
            include_grey: Whether to include gray nations in calculation.
        """
        loading: LoadingDisplay | None = None
        try:
            await ctx.defer()

            alliance_id = None
            all_alliances = await asyncio.to_thread(db_utils.list_all_alliances)
            for aa in all_alliances:
                aa_id = str(aa['id'])
                if alliance in (f"{aa['name']} ({aa_id})", aa_id, aa['name'], aa['acronym']):
                    alliance_id = aa_id
                    break
                                
            if alliance_id is None:
                await ctx.respond(f"I could not find a match to `{alliance}` in the database!")
                return

            loading = LoadingDisplay(ctx, show_after=0)
            await loading.start("Calling the API...")

            nations = await paginate_call(
                f"{{nations(alliance_id:{alliance_id} page:page_number alliance_position:[2,3,4,5]){{paginatorInfo{{hasMorePages}} data{get_query(queries.REVENUE)}}}}}",
                "nations",
                api_key,
            )
            await loading.update("Calculating alliance revenue...")

            nation, colors, prices, treasures, radiation, seasonal_mod = await pre_revenue_calc(
                ctx,
                call_func=call_api,
                get_query_func=get_query,
                queries_module=queries,
            )

            income = {}
            RSS = ['coal', 'oil', 'uranium', 'iron', 'bauxite', 'lead', 'gasoline', 'munitions', 'steel', 'aluminum', 'food', 'net_cash_num', 'monetary_net_num']
            for rs in RSS:
                income[rs] = 0

            for nation in nations:
                if nation['color'] == "gray" and not include_grey:
                    continue
                rev_obj = await revenue_calc(
                    ctx,
                    nation,
                    radiation,
                    treasures,
                    prices,
                    colors,
                    seasonal_mod,
                    None,
                    False,
                    False,
                )
                for rs in RSS:
                    try:
                        income[rs] += rev_obj[rs]
                    except KeyError:
                        pass
            
            if len(nations) == 0:
                await ctx.respond(f"They have no valid members!")
                return
                
            embed = discord.Embed(title=f"{nations[0]['alliance']['name']}'s daily revenue:", url=f"https://politicsandwar.com/alliance/id={alliance_id}", description="", color=0xff5100)

            for rs in RSS[:-2]:
                embed.add_field(name=f"{rs.capitalize()}", value=f"{income[rs]:,.2f}\n")
            
            embed.add_field(name="Money", value=f"{income[RSS[-2]]:,.2f}\n")
            embed.add_field(name="Net income", value=f"{income[RSS[-1]]:,.2f}\n")
            
            await ctx.edit(content="", embed=embed, attachments=[])
        except Exception as e:
            if loading is not None:
                await loading.clear()
            await self._handle_command_exception(ctx, e, command_name="revenue alliance")
            return

    @slash_command(
        name="botinfo",
        description="View bot statistics and useful links",
    )
    async def botinfo(self, ctx: discord.ApplicationContext) -> None:
        """Display bot statistics and useful links.
        
        Args:
            ctx: Discord application context.
        """
        try:
            await ctx.defer()
            verified_count = len(await listify(get_db().global_users.find({})))
            content = (
                f"{len(self.bot.users)} people across {len(self.bot.guilds)} servers have access to me, "
                f"but only {verified_count} have verified themselves.\n\n"
                "Here you can find the:\n"
                "> [GitHub Repository](https://github.com/randomnoobster/Autolycus/tree/oracle)\n"
                "> [Invite Link](https://discord.com/api/oauth2/authorize?client_id=946351598223888414&permissions=326417827840&scope=applications.commands%20bot)\n"
                "> [Privacy Policy](https://docs.google.com/document/d/1SXfqzBq_UPuJpPyaXjGBE0UFSfplwMIbeSS6pO4e4f8/)\n"
                "> [Terms of Service](https://docs.google.com/document/d/1sR398ZaqVb6YId7jKIyx0laTxbA14QP0GnwmjY74yWw/)\n"
                "\u200b"
            )
            embed = discord.Embed(title="About me", description=content, color=0xff5100)
            embed.set_footer(text="Contact randomnoobster for help or bug reports")
            await ctx.respond(embed=embed)
        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="botinfo")
            return

    @slash_command(
        name="verify",
        description="Link your Discord account to your Politics & War nation",
    )
    async def verify(
        self,
        ctx: discord.ApplicationContext,
        nation_id: Option(str, "Your nation id or nation link"),
    ) -> None:
        """Link a Discord account to a Politics & War nation.
        
        Args:
            ctx: Discord application context.
            nation_id: Nation ID or link from Politics & War.
        """
        try:
            result = await verify_discord_nation_link(
                discord_user_id=ctx.author.id,
                discord_username=str(ctx.author.name),
                nation_input=nation_id,
                call_func=call_api,
            )

            if result["ok"]:
                embed = verification_success_embed(relinked=result["relinked"])
                await ctx.respond(embed=embed)
                return

            code = result["code"]
            resolved_nation_id = result["nation_id"] or nation_id
            if code == "OWNERSHIP_MISMATCH":
                steps = (
                    f"1. Go to [nation settings](https://politicsandwar.com/nation/edit/)\n"
                    f'2. Find **Discord Username** and set it to `{ctx.author.name}`\n'
                    f"3. Save, then run `/verify {resolved_nation_id}` again here"
                )
                embed = discord.Embed(
                    title="Discord name does not match",
                    description=(
                        "We require your in-game **Discord Username** field to match "
                        "your Discord name before we can link the account.\n\n" + steps
                    ),
                    color=0xFEE75C,
                )
                embed.set_footer(text="Contact randomnoobster for help or bug reports")
                await ctx.respond(embed=embed)
                return
            if code == "NOT_FOUND":
                await ctx.respond(
                    embed=err_util.error_embed(
                        "Nation not found",
                        f"There is no nation with id `{resolved_nation_id}`. Check the id or link and try again.",
                    )
                )
                return
            if code == "LINK_CONFLICT":
                await ctx.respond(
                    embed=err_util.error_embed(
                        "Already linked",
                        "That nation is already linked to a different Discord account.",
                    )
                )
                return
            if code == "INVALID_NATION_ID":
                await ctx.respond(
                    embed=err_util.error_embed(
                        "Invalid input",
                        "Please provide a valid nation id or a politicsandwar.com nation URL.",
                    )
                )
                return
            await ctx.respond(
                embed=err_util.error_embed(
                    "Verification failed",
                    "Something went wrong. Please try again in a moment.",
                )
            )
        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="verify")
            return

    @slash_command(
        name="unverify",
        description="Unlink your Discord account from your P&W nation",
    )
    async def unverify(
        self,
        ctx: discord.ApplicationContext,
    ) -> None:
        """Unlink Discord account from Politics & War nation.
        
        Args:
            ctx: Discord application context.
        """
        try:
            user = await delete_verification(ctx.author.id)
            if user is None:
                await ctx.respond(
                    embed=err_util.error_embed(
                        "Not linked",
                        "Your Discord account is not linked to any nation. Use `/verify` to link one.",
                    )
                )
            else:
                await ctx.respond(embed=verification_unlinked_embed())
        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="unverify")
            return

    @staticmethod
    async def _autocomplete_commands(ctx: discord.AutocompleteContext) -> list[str]:
        """Autocomplete callback for the /help command parameter."""
        names = help_data.get_all_command_names()
        value = (ctx.value or "").lower()
        return [n for n in names if value in n][:25]

    @slash_command(
        name="help",
        description="Show all commands or get detailed help for one",
    )
    async def help(
        self,
        ctx: discord.ApplicationContext,
        command: Option(
            str,
            "The command to get detailed help for (e.g. raids, revenue nation)",
            autocomplete=_autocomplete_commands.__func__,
            required=False,
        ) = None,
    ) -> None:
        """Display all available bot commands, or detailed help for a specific one.

        Args:
            ctx: Discord application context.
            command: Optional command name to get detailed help for.
        """
        try:
            # Prevent "Unknown interaction" if embed construction takes >3 seconds.
            await ctx.defer()
            if command:
                # ── Detailed help for a single command ──
                cmd_help = help_data.get_help(command.lower())
                if not cmd_help:
                    await ctx.edit(
                        content=f"Unknown command `{command}`. Use `/help` to see all commands."
                    )
                    return

                embed = discord.Embed(
                    title=f"/{command}",
                    description=cmd_help.get("long", cmd_help.get("short", "")),
                    color=0xff5100,
                )

                # Parameters
                params = cmd_help.get("parameters", {})
                if params:
                    param_lines = []
                    for name, desc in params.items():
                        param_lines.append(f"**`{name}`** — {desc}")
                    embed.add_field(
                        name="Parameters",
                        value="\n".join(param_lines),
                        inline=False,
                    )

                # Examples
                examples = cmd_help.get("examples", [])
                if examples:
                    embed.add_field(
                        name="Examples",
                        value="\n".join(examples),
                        inline=False,
                    )

                # Notes
                notes = cmd_help.get("notes")
                if notes:
                    embed.add_field(
                        name="💡 Tips",
                        value=notes,
                        inline=False,
                    )

                embed.set_footer(text="Contact randomnoobster for help or bug reports")
                await ctx.edit(content="", embed=embed)
            else:
                # ── Compact list of all commands ──
                cmds = sorted(self.bot.application_commands, key=lambda x: f"{x}")
                embed = discord.Embed(title="Autolycus Command List", color=0xff5100)
                embed.description = (
                    "Use `/help <command>` for detailed info, parameters, and examples."
                )

                seen: set[str] = set()
                for cmd in cmds:
                    cmd_name = getattr(cmd, "qualified_name", str(cmd))
                    if cmd_name in seen:
                        continue
                    seen.add(cmd_name)

                    cmd_help = help_data.get_help(cmd_name)
                    short = (
                        cmd_help["short"]
                        if cmd_help
                        else getattr(cmd, "description", "No description.")
                    )
                    embed.add_field(
                        name=f"/{cmd_name}",
                        value=short,
                        inline=False,
                    )

                embed.set_footer(text="Contact randomnoobster for help or bug reports")
                await ctx.edit(content="", embed=embed)
        except Exception as e:
            await self._handle_command_exception(ctx, e, command_name="help")
            return

def setup(bot: discord.Bot) -> None:
    """Register the Background cog with the bot.
    
    Args:
        bot: The Discord bot instance.
    """
    bot.add_cog(Background(bot))
