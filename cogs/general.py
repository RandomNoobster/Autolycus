"""General commands cog for Autolycus bot.

This module contains general-purpose commands including nation info,
revenue calculations, builds optimizer, and user management.
"""

import json
import sqlite3
import math
import os
import pathlib
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import discord
from discord.commands import Option, SlashCommandGroup, slash_command
from discord.ext import commands

import queries
from utils import pw_utils as utils
from utils import db_utils
from main import async_mongo, logger

api_key = os.getenv("api_key")

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
            nation = await utils.find_nation_plus(self, person)
            if nation is None:
                await ctx.respond(content="I did not find that nation!")
                return

            nation = (await utils.call(f"{{nations(first:1 id:{nation['id']}){{data{utils.get_query(queries.WHO)}}}}}"))['data']['nations']['data'][0]

            embed = discord.Embed(title=nation['nation_name'], url=f"https://politicsandwar.com/nation/id={nation['id']}", color=0xff5100)
            user = await utils.find_user(self, nation['id'])
            if not user:
                discord_info = "> Autolycus Verified: <:redcross:862669500977905694>"
                if nation['discord']:
                    discord_info += f"\n> Discord Username: {nation['discord']}"
            else:
                username = await self.bot.fetch_user(user['user'])
                discord_info = f"> Autolycus Verified: ✅\n> Discord Username: {username} `({username.id})`"
            embed.add_field(name="Discord Info", value=discord_info, inline=False)

            nation_info = f"> Nation Name: [{nation['nation_name']}](https://politicsandwar.com/nation/id={nation['id']})\n> Leader Name: {nation['leader_name']}\n> Cities: [{nation['num_cities']}](https://politicsandwar.com/city/manager/n={nation['nation_name'].replace(' ', '%20')})\n> War Policy: [{nation['warpolicy']}](https://politicsandwar.com/pwpedia/war-policy/)\n> Dom. Policy: [{nation['dompolicy']}](https://politicsandwar.com/pwpedia/domestic-policy/)"
            embed.add_field(name="Nation Info", value=nation_info)

            nation_info_2 = f"> Score: `{nation['score']}`\n> Def. Range: `{round(nation['score']/2.5)}`-`{round(nation['score']/0.75)}`\n> Off. Range: `{round(nation['score']*0.75)}`-`{round(nation['score']*2.5)}`\n> Color: [{nation['color'].capitalize()}](https://politicsandwar.com/leaderboards/display=color)\n> Turns of VM: `{nation['vmode']}`"
            embed.add_field(name="\u200b", value=nation_info_2)

            if nation['alliance']:
                members = len([temp for temp in nation['alliance']['nations'] if temp['alliance_position'] != "APPLICANT"])
                alliance_info = f"> Alliance: [{nation['alliance']['name']}](https://politicsandwar.com/alliance/id={nation['alliance']['id']})\n> Position: {nation['alliance_position'].capitalize()}\n> Seniority: {nation['alliance_seniority']:,} days\n> Score: `{nation['alliance']['score']:,}`\n> Color: [{nation['alliance']['color'].capitalize()}](https://politicsandwar.com/leaderboards/display=color)\n> Members: `{members}`"
            else:
                alliance_info = f"> Alliance: None"
            embed.add_field(name="Alliance Info", value=alliance_info, inline=False)

            milt = utils.militarization_checker(nation)
            military_info = "> Format: \u200b \u200b \u200b`" + "Current".center(9) + "` `" + "Cap".center(9) + "` `" + "Daily".center(7) + "`\n> Soldiers: \u200a\u200b\u200a`" + f"{nation['soldiers']:,.0f}".rjust(9) + "` `" + f"{milt['max_soldiers']:,.0f}".rjust(9) + "` `" + f"{milt['soldiers_daily']:,.0f}".rjust(7) + "`\n> Tanks: \u200a \u200a \u200a \u200a \u200b`" + f"{nation['tanks']:,.0f}".rjust(9) + "` `" + f"{milt['max_tanks']:,.0f}".rjust(9) + "` `" + f"{milt['tanks_daily']:,.0f}".rjust(7) + "`\n> Aircraft: \u200b \u200b`" + f"{nation['aircraft']:,.0f}".rjust(9) + "` `" + f"{milt['max_aircraft']:,.0f}".rjust(9) + "` `" + f"{milt['aircraft_daily']:,.0f}".rjust(7) + "`\n> Ships:\u200a \u200a \u200a \u200a \u200a \u200a`" + f"{nation['ships']:,.0f}".rjust(9) + "` `" + f"{milt['max_ships']:,.0f}".rjust(9) + "` `" + f"{milt['ships_daily']:,.0f}".rjust(7) + f"`\n> \n> MMR: `{milt['barracks_mmr']}`/`{milt['factory_mmr']}`/`{milt['hangar_mmr']}`/`{milt['drydock_mmr']}`"
            print(military_info)
            embed.add_field(name="Military Info", value=military_info)

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

            if nation['irond']:
                dome = "Yes"
            else:
                dome = "No"
            if nation['vds']:
                vital = "Yes"
            else:
                vital = "No"
            
            if nation['pirate_economy']:
                max_offense = 6
            if nation['advanced_pirate_economy']:
                max_offense = 7
            else:
                max_offense = 5

            military_info_2 = f"> Offensive Wars: `{o_wars}`/`{max_offense}`\n> Defensive Wars: `{d_wars}`/`3`\n> Missiles: `{missiles}`\n> Nukes: `{nukes}`\n> Iron Dome: {dome}\n> Vital Defense: {vital}\n> Turns of Beige: `{nation['beige_turns']}`"
            embed.add_field(name="\u200b", value=military_info_2, inline=True)

            embed.set_footer(text="Contact RandomNoobster#0093 for help or bug reports")

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
            
            if person is None:
                person = ctx.author.id
            db_nation = await utils.find_nation_plus(self, person)
            if not db_nation:
                await ctx.edit(content="I could not find the specified person!")
                return

            nation_data = (await utils.call(
                f"{{nations(first:1 id:{db_nation['id']}){{data{utils.get_query(queries.REVENUE)}}}}}"
            ))['data']['nations']['data']
            
            if len(nation_data) == 0:
                await ctx.edit(content="That person was not in the API!")
                return
            
            nation = nation_data[0]
            
            infra_level = utils.str_to_int(infra)
            
            if infra_level % 50 != 0:
                await ctx.edit(content="The amount of infra must be a multiple of 50!")
                return

            land_amount = utils.str_to_int(land)
            
            # Parse MMR requirement
            min_bar = min_fac = min_han = min_dry = 0
            mmr_display = "Any MMR"
            if mmr.lower() != "any":
                try:
                    mmr_clean = re.sub("[^0-9]", "", mmr)
                    min_bar = int(mmr_clean[0])
                    min_fac = int(mmr_clean[1])
                    min_han = int(mmr_clean[2])
                    min_dry = int(mmr_clean[3])
                    mmr_display = f"{min_bar}/{min_fac}/{min_han}/{min_dry}"
                except (IndexError, ValueError):
                    await ctx.edit(content="I did not understand that mmr, please try again!")
                    return

            # Calculate improvement limits based on projects
            max_recycling = 3 + int(nation['recycling_initiative'])
            max_hospital = 5 + int(nation['clinical_research_center'])
            max_bank = 5 + int(nation['itc'])
            max_mall = 4 + int(nation['telecom_satellite'])
            
            # Determine continent resource restrictions
            continent_resources = self._get_continent_resources(nation['continent'])
            all_resources = [
                'net income', 'aluminum', 'bauxite', 'coal', 'food', 'gasoline',
                'iron', 'lead', 'money', 'munitions', 'oil', 'steel', 'uranium'
            ]
            available_resources = [
                rs for rs in all_resources 
                if f"{rs}_mines" not in continent_resources['api_names'] 
                and f"{rs}_wells" not in continent_resources['api_names']
            ]

            await ctx.edit(content="Loading builds from database...")

            # Load builds from SQLite database via utils helpers
            to_scan = []
            try:
                db_path = db_utils.get_builds_db_path()
                if not db_path.exists():
                    await ctx.edit(content=f"Builds database not found at {db_path}.")
                    return

                nation_age = nation['date'][:nation['date'].index("T")]

                mmr_mins = {}
                if mmr.lower() != "any":
                    mmr_mins = {
                        'barracks': min_bar,
                        'factory': min_fac,
                        'airforcebase': min_han,
                        'drydock': min_dry,
                    }

                caps = {
                    'hospital': max_hospital,
                    'recyclingcenter': max_recycling,
                    'bank': max_bank,
                    'mall': max_mall,
                }

                restricted = self._get_continent_resources(nation['continent'])['json_names']
                rows = db_utils.fetch_build_rows(db_path, infra_level, mmr_mins, caps, restricted)

                for row in rows:
                    city = dict(row)
                    city['powered'] = "am powered"  # Must be string for webpage
                    city['land'] = land_amount
                    city['date'] = nation_age
                    to_scan.append(city)

                if not to_scan:
                    await ctx.edit(content=f"No builds found for infrastructure {infra_level} with the given criteria.")
                    return
            except Exception as e:
                logger.error(f"Error loading builds from SQLite: {e}", exc_info=True)
                await ctx.edit(content="An error occurred while loading builds data from the database.")
                return
                
            temp, colors, prices, treasures, radiation, seasonal_mod = await utils.pre_revenue_calc(
                ctx, query_for_nation=False, parsed_nation=nation
            )

            # Calculate revenue for each build
            cities = []
            for city in to_scan:
                nation['cities'] = [city]
                cities.append(
                    await utils.revenue_calc(
                        ctx, nation, radiation, treasures, prices, 
                        colors, seasonal_mod, single_city=True
                    )
                )

            if len(cities) == 0:
                await ctx.edit(content="No builds matched your criteria <:derp:846795730210783233>")
                return

            # Define improvement fields for uniqueness check
            improvement_fields = [
                'infrastructure', 'oilpower', 'windpower', 'coalpower', 'nuclearpower',
                'coalmine', 'oilwell', 'uramine', 'leadmine', 'ironmine', 'bauxitemine',
                'farm', 'gasrefinery', 'aluminumrefinery', 'steelmill', 'munitionsfactory',
                'policestation', 'hospital', 'recyclingcenter', 'subway', 'supermarket',
                'bank', 'mall', 'stadium', 'barracks', 'factory', 'airforcebase', 'drydock'
            ]
            
            # Find unique builds based only on improvement configuration
            unique_build_keys = set()
            unique_builds = []
            for city in cities:
                # Create a tuple of only the improvement values for uniqueness
                build_key = tuple(city.get(field, 0) for field in improvement_fields)
                if build_key not in unique_build_keys:
                    unique_build_keys.add(build_key)
                    unique_builds.append(city)
            
            unique_builds = sorted(unique_builds, key=lambda k: k['net income'], reverse=True)
                            
            # Find best builds for each resource
            builds = {}
            top_builds = []
            for rs in available_resources:
                sorted_builds = sorted(unique_builds, key=lambda k: k[rs], reverse=True)
                best_builds = [city for city in sorted_builds if city[rs] == sorted_builds[0][rs]]
                top_builds += best_builds[0:20]
                builds[rs] = sorted(best_builds, key=lambda k: k['net income'], reverse=True)[0]
                builds[rs]['template'] = self._generate_build_template(builds[rs])
                
            top_unique_builds = [dict(t) for t in {tuple(d.items()) for d in top_builds}]

            timestamp = round(datetime.utcnow().timestamp())

            await utils.write_web(
                "builds", ctx.author.id, 
                {"builds": builds, "rss": available_resources, "land": land_amount, "top_unique_builds": top_unique_builds}, 
                timestamp
            )

            # Create embed with results
            embed = discord.Embed(
                title=f"Optimal City Builds for {infra_level} Infrastructure",
                url=f"http://132.145.71.195:5000/builds/{ctx.author.id}/{timestamp}",
                description=f"Found **{len(unique_builds):,}** unique build configurations.",
                color=0xff5100
            )
            
            # Build criteria field
            criteria_text = (
                f"> Infrastructure: `{infra_level:,}`\n"
                f"> Land: `{land_amount:,}`\n"
                f"> MMR: `{mmr_display}`"
            )
            embed.add_field(name="Build Criteria", value=criteria_text, inline=False)
            
            # Best revenue field
            if unique_builds:
                best_build = unique_builds[0]
                revenue_text = f"> Net Income: `${best_build['net income']:,.2f}` per day"
                embed.add_field(name="Best Overall Build", value=revenue_text, inline=False)
            
            # Link field
            link_text = f"[Click here to see all builds](http://132.145.71.195:5000/builds/{ctx.author.id}/{timestamp})"
            embed.add_field(name="View Detailed Results", value=link_text, inline=False)
            
            embed.set_footer(text="Contact RandomNoobster#0093 for help or bug reports")

            await ctx.edit(content="", embed=embed)
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e

    def _get_continent_resources(self, continent: str) -> Dict[str, List[str]]:
        """Get restricted resources for a continent.
        
        Args:
            continent: Two-letter continent code (af, as, au, an, eu, na, sa).
            
        Returns:
            Dictionary containing 'api_names' and 'json_names' lists of restricted resources.
            
        Note:
            Per PWPedia: Resources NOT present in each continent.
        """
        continent_map = {
            "af": {
                'api_names': ['coal_mines', 'iron_mines', 'lead_mines'],
                'json_names': ['coalmine', 'ironmine', 'leadmine']
            },
            "as": {
                'api_names': ['coal_mines', 'bauxite_mines', 'lead_mines'],
                'json_names': ['coalmine', 'bauxitemine', 'leadmine']
            },
            "au": {
                'api_names': ['oil_wells', 'iron_mines', 'uranium_mines'],
                'json_names': ['oilwell', 'ironmine', 'uramine']
            },
            "an": {
                'api_names': ['iron_mines', 'lead_mines', 'bauxite_mines'],
                'json_names': ['ironmine', 'leadmine', 'bauxitemine']
            },
            "eu": {
                'api_names': ['oil_wells', 'bauxite_mines', 'uranium_mines'],
                'json_names': ['oilwell', 'bauxitemine', 'uramine']
            },
            "na": {
                'api_names': ['oil_wells', 'bauxite_mines', 'lead_mines'],
                'json_names': ['oilwell', 'bauxitemine', 'leadmine']
            },
            "sa": {
                'api_names': ['coal_mines', 'iron_mines', 'uranium_mines'],
                'json_names': ['coalmine', 'ironmine', 'uramine']
            }
        }
        return continent_map.get(continent, {'api_names': [], 'json_names': []})

    def _generate_build_template(self, build: Dict[str, Any]) -> str:
        """Generate JSON template string for a build configuration.
        
        Args:
            build: Build dictionary containing improvement counts.
            
        Returns:
            Formatted JSON string template.
        """
        return f"""
    {{
        "infra_needed": {build['infrastructure']},
        "imp_total": {math.floor(float(build['infrastructure'])/50)},
        "imp_coalpower": {build['coalpower']},
        "imp_oilpower": {build['oilpower']},
        "imp_windpower": {build['windpower']},
        "imp_nuclearpower": {build['nuclearpower']},
        "imp_coalmine": {build['coalmine']},
        "imp_oilwell": {build['oilwell']},
        "imp_uramine": {build['uramine']},
        "imp_leadmine": {build['leadmine']},
        "imp_ironmine": {build['ironmine']},
        "imp_bauxitemine": {build['bauxitemine']},
        "imp_farm": {build['farm']},
        "imp_gasrefinery": {build['gasrefinery']},
        "imp_aluminumrefinery": {build['aluminumrefinery']},
        "imp_munitionsfactory": {build['munitionsfactory']},
        "imp_steelmill": {build['steelmill']},
        "imp_policestation": {build['policestation']},
        "imp_hospital": {build['hospital']},
        "imp_recyclingcenter": {build['recyclingcenter']},
        "imp_subway": {build['subway']},
        "imp_supermarket": {build['supermarket']},
        "imp_bank": {build['bank']},
        "imp_mall": {build['mall']},
        "imp_stadium": {build['stadium']},
        "imp_barracks": {build['barracks']},
        "imp_factory": {build['factory']},
        "imp_hangars": {build['airforcebase']},
        "imp_drydock": {build['drydock']}
    }}"""

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
            db_nation = await utils.find_user(self, person)

            if not db_nation:
                db_nation = await utils.find_nation(person)
                if not db_nation:
                    await ctx.edit(content='I could not find that person!')
                    return
                db_nation['nationid'] = db_nation['id']

            nation, colors, prices, treasures, radiation, seasonal_mod = await utils.pre_revenue_calc(ctx, query_for_nation=True, nationid=db_nation['id'])

            build_txt = "daily revenue"
            single_city = False

            rev_obj = await utils.revenue_calc(ctx, nation, radiation, treasures, prices, colors, seasonal_mod, None, single_city, True)

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
        alliance: Option(str, "The alliance you want to see the revenue of.", autocomplete=utils.get_alliances),
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
            for aa in await utils.listify(async_mongo.alliances.find({})):
                if alliance in (f"{aa['name']} ({aa['id']})", aa['id'], aa['name'], aa['acronym']):
                    alliance_id = aa['id']
                    break
                                
            if alliance_id is None:
                await ctx.respond(f"I could not find a match to `{alliance}` in the database!")
                return

            await ctx.respond('Calling the API...')

            nations = await utils.paginate_call(f"{{nations(alliance_id:{alliance_id} page:page_number alliance_position:[2,3,4,5]){{paginatorInfo{{hasMorePages}} data{utils.get_query(queries.REVENUE)}}}}}", "nations")

            nation, colors, prices, treasures, radiation, seasonal_mod = await utils.pre_revenue_calc(ctx)

            income = {}
            RSS = ['coal', 'oil', 'uranium', 'iron', 'bauxite', 'lead', 'gasoline', 'munitions', 'steel', 'aluminum', 'food', 'net_cash_num', 'monetary_net_num']
            for rs in RSS:
                income[rs] = 0

            for nation in nations:
                if nation['color'] == "gray" and not include_grey:
                    continue
                rev_obj = await utils.revenue_calc(ctx, nation, radiation, treasures, prices, colors, seasonal_mod, None, False, False)
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
            verified_count = len(await utils.listify(async_mongo.global_users.find({})))
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
            user = await async_mongo.global_users.find_one({"user": ctx.author.id})
            if user is not None:
                await ctx.respond("You are already verified!")
                return
            nation_id = re.sub("[^0-9]", "", nation_id)
            res = await utils.call(f'{{nations(first:1 id:{nation_id}){{data{utils.get_query(queries.VERIFY)}}}}}')
            try:
                if str(ctx.author.name).lower() == res['data']['nations']['data'][0]['discord'].lower():
                    await async_mongo.global_users.insert_one({"user": ctx.author.id, "id": nation_id, "beige_alerts": []})
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
            user = await async_mongo.global_users.find_one_and_delete({"user": ctx.author.id})
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
            help_text = ""
            cmds = sorted(self.bot.application_commands, key=lambda x: f"{x}")
            for command in cmds:
                command_str = f"`{command}`"
                if command_str not in help_text:
                    help_text += f"{command_str} - {command.description}\n"
            help_text += (
                "\nHere you can find the [Privacy Policy](https://docs.google.com/document/d/1SXfqzBq_UPuJpPyaXjGBE0UFSfplwMIbeSS6pO4e4f8/) "
                "and [Terms of Service](https://docs.google.com/document/d/1sR398ZaqVb6YId7jKIyx0laTxbA14QP0GnwmjY74yWw/)"
            )
            embed = discord.Embed(title="Command list", description=help_text, color=0xff5100)
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
