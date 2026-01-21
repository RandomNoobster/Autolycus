"""General commands cog for Autolycus bot.

This module contains general-purpose commands including nation info,
revenue calculations, builds optimizer, and user management.
"""

import inspect
import json
import os
import pathlib
import re
from datetime import datetime, timedelta
from functools import partial
from typing import Any, Dict, List, Optional

import discord
from discord.commands import Option, SlashCommandGroup, slash_command
from discord.ext import commands

import queries
from database.mongo import find_nation, get_db, get_global_user_by_any, listify
from database.users import (delete_verification, get_verification,
                            set_verification)
from discord_utils import helpers
from discord_utils.embeds import nation_overview_embed
from logic.api_client import call, paginate_call
from logic.builds import calculate_builds as calculate_builds_logic
from logic.builds import generate_build_template
from logic.common import str_to_int
from logic.merge_utils import get_query
from logic.military import militarization_checker
from logic.revenue import pre_revenue_calc, revenue_calc
from main import logger
from utils import db_utils

api_key = os.getenv("api_key")
call_api = partial(call, api_key=api_key)

class Background(commands.Cog):
    """General commands cog containing nation info, revenue, and builds commands."""

    def __init__(self, bot: discord.Bot) -> None:
        """Initialize the Background cog.
        
        Args:
            bot: The Discord bot instance.
        """
        self.bot = bot

    @slash_command(
        name="who",
        description="Get more information about someone's nation"
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
            logger.error(e, exc_info=True)
            raise e

    @slash_command(
        name="builds",
        description="Shows you the best city builds"
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
        try:
            await ctx.respond("Let me think a bit...")

            target = person or ctx.author.id
            db_nation = await helpers.find_nation_plus(self.bot, target)
            if not db_nation:
                await ctx.edit(content="I could not find the specified person!")
                return

            infra_level = str_to_int(infra)
            if infra_level % 50 != 0:
                await ctx.edit(content="The amount of infra must be a multiple of 50!")
                return

            land_amount = str_to_int(land)

            try:
                results = await calculate_builds_logic(
                    call_pnw=call_api,
                    nation_id=str(db_nation['id']),
                    infra=infra_level,
                    land=land_amount,
                    mmr=mmr,
                )
            except ValueError as exc:
                await ctx.edit(content=str(exc))
                return

            unique_builds = results.get("uniqueBuilds", [])
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
            builds_url = f"http://132.145.71.195:3000/builds?nationId={db_nation['id']}"

            embed = discord.Embed(
                title=f"Optimal City Builds for {infra_level} Infrastructure",
                url=builds_url,
                description=f"Found **{len(unique_builds):,}** unique build configurations.",
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

            link_text = f"[Click here to see all builds]({builds_url})"
            embed.add_field(name="View Detailed Results", value=link_text, inline=False)

            embed.set_footer(text="Contact RandomNoobster#0093 for help or bug reports")

            content = ""
            if best_build:
                net_income = best_build.get("net income", 0)
                build_template = generate_build_template(best_build)
                content = (
                    f"Top build (net income: ${net_income:,.2f}/day)\n"
                    f"```json\n{build_template}\n```"
                )

            await ctx.edit(content=content, embed=embed)
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e


    revenue_group = SlashCommandGroup("revenue", "Revenue calculators.")
    
    @revenue_group.command(
        name="nation",
        description="The revenue of a nation"
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
        try:
            await ctx.respond('Stay with me...')
            if person is None:
                person = ctx.author.id
            db_nation = await helpers.find_user(self.bot, person)

            if not db_nation:
                db_nation = await find_nation(person)
                if not db_nation:
                    await ctx.edit(content='I could not find that person!')
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

            await ctx.edit(content="", embed=embed)
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
    
    @revenue_group.command(
        name="alliance",
        description="The revenue of an alliance"
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
        try:
            await ctx.defer()

            alliance_id = None
            for aa in await listify(get_db().alliances.find({})):
                if alliance in (f"{aa['name']} ({aa['id']})", aa['id'], aa['name'], aa['acronym']):
                    alliance_id = aa['id']
                    break
                                
            if alliance_id is None:
                await ctx.respond(f"I could not find a match to `{alliance}` in the database!")
                return

            await ctx.respond('Calling the API...')

            nations = await paginate_call(
                f"{{nations(alliance_id:{alliance_id} page:page_number alliance_position:[2,3,4,5]){{paginatorInfo{{hasMorePages}} data{get_query(queries.REVENUE)}}}}}",
                "nations",
                api_key,
            )

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
                    except:
                        pass
            
            if len(nations) == 0:
                await ctx.respond(f"They have no valid members!")
                return
                
            embed = discord.Embed(title=f"{nations[0]['alliance']['name']}'s daily revenue:", url=f"https://politicsandwar.com/alliance/id={alliance_id}", description="", color=0xff5100)

            for rs in RSS[:-2]:
                embed.add_field(name=f"{rs.capitalize()}", value=f"{income[rs]:,.2f}\n")
            
            embed.add_field(name="Money", value=f"{income[RSS[-2]]:,.2f}\n")
            embed.add_field(name="Net income", value=f"{income[RSS[-1]]:,.2f}\n")
            
            await ctx.edit(content="", embed=embed)
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    @slash_command(
        name="botinfo",
        description="Information about the bot"
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
                "> [GitHub Repository](https://github.com/RandomNoobster/Autolycus/tree/oracle)\n"
                "> [Invite Link](https://discord.com/api/oauth2/authorize?client_id=946351598223888414&permissions=326417827840&scope=applications.commands%20bot)\n"
                "> [Privacy Policy](https://docs.google.com/document/d/1SXfqzBq_UPuJpPyaXjGBE0UFSfplwMIbeSS6pO4e4f8/)\n"
                "> [Terms of Service](https://docs.google.com/document/d/1sR398ZaqVb6YId7jKIyx0laTxbA14QP0GnwmjY74yWw/)\n"
                "\u200b"
            )
            embed = discord.Embed(title="About me", description=content, color=0xff5100)
            embed.set_footer(text="Contact RandomNoobster#0093 for help or bug reports")
            await ctx.respond(embed=embed)
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    @slash_command(
        name="verify",
        description='Link your nation with your discord account',
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
            user = await get_verification(ctx.author.id)
            if user is not None:
                await ctx.respond("You are already verified!")
                return
            nation_id = re.sub("[^0-9]", "", nation_id)
            res = await call_api(f'{{nations(first:1 id:{nation_id}){{data{get_query(queries.VERIFY)}}}}}')
            try:
                if str(ctx.author.name).lower() == res['data']['nations']['data'][0]['discord'].lower():
                    await set_verification(ctx.author.id, nation_id)
                    await ctx.respond("You have successfully verified your nation!")
                else:
                    await ctx.respond(
                        f'1. Go to <https://politicsandwar.com/nation/edit/>\n'
                        f'2. Scroll down to where it says "Discord Username"\n'
                        f'3. Type `{ctx.author.name}` in the adjacent field\n'
                        f'4. Come back to discord\n'
                        f'5. Type `/verify {nation_id}` again'
                    )
            except (KeyError, IndexError):
                await ctx.respond(f"I could not find a nation with an id of `{nation_id}`")
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    @slash_command(
        name="unverify",
        description='Unlink your nation from your discord account',
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
                await ctx.respond("You are not verified!")
            else:
                await ctx.respond("Your discord account was successfully unlinked from your nation.")
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    @slash_command(
        name="help",
        description="Returns all commands",
    )
    async def help(self, ctx: discord.ApplicationContext) -> None:
        """Display all available bot commands.
        
        Args:
            ctx: Discord application context.
        """
        try:
            cmds = sorted(self.bot.application_commands, key=lambda x: f"{x}")
            embed = discord.Embed(title="Command list", color=0xff5100)

            seen = set()
            for command in cmds:
                command_name = getattr(command, "qualified_name", str(command))
                if command_name in seen:
                    continue
                seen.add(command_name)

                short_help = getattr(command, "description", None) or "No short description provided."
                long_help = inspect.getdoc(command.callback) if hasattr(command, "callback") else None
                if long_help:
                    long_help = long_help.split("Args:")[0].strip()
                else:
                    long_help = short_help

                if len(long_help) > 900:
                    long_help = f"{long_help[:897]}..."

                embed.add_field(
                    name=f"/{command_name}",
                    value=f"**Short:** {short_help}\n**Long:** {long_help}",
                    inline=False,
                )

            embed.description = (
                "Here you can find the [Privacy Policy](https://docs.google.com/document/d/1SXfqzBq_UPuJpPyaXjGBE0UFSfplwMIbeSS6pO4e4f8/) "
                "and [Terms of Service](https://docs.google.com/document/d/1sR398ZaqVb6YId7jKIyx0laTxbA14QP0GnwmjY74yWw/)"
            )
            embed.set_footer(text="Contact RandomNoobster#0093 for help or bug reports")
            await ctx.respond(embed=embed)
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

def setup(bot: discord.Bot) -> None:
    """Register the Background cog with the bot.
    
    Args:
        bot: The Discord bot instance.
    """
    bot.add_cog(Background(bot))
