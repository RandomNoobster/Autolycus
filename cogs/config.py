import discord
from discord.ext import commands
from discord.commands import Option, SlashCommandGroup
import os
import utils
from datetime import datetime
from main import async_mongo, logger

api_key = os.getenv("api_key")

class Config(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    config_group = SlashCommandGroup("config", "Configure commands that need configuration")

    @config_group.command(
        name="counters",
        description="Configure the counters command",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def config_counters(
        self,
        ctx: discord.ApplicationContext,
        alliance_ids: Option(str, "The alliance id(s) to include in the counters command") = []
    ):      
        try:  
            if alliance_ids != []:
                id_list, id_str = utils.str_to_id_list(alliance_ids)
            else:
                id_list = []
                id_str = "None"
            await async_mongo.guild_configs.find_one_and_update({"guild_id": ctx.guild.id}, {"$set": {"counters_alliance_ids": id_list}}, upsert=True)
            await ctx.respond(f"Alliance id(s) for `/counters` set to `{id_str}`")
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
    
    @config_group.command(
        name="war_threads",
        description="Configure automated war threads"
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def config_war_threads(
        self,
        ctx: discord.ApplicationContext,
        alliance_ids: Option(str, "The alliance id(s) to create war threads for; your alliance and optionally allied alliances.") = [],
        channel: Option(discord.TextChannel, "The channel to create the war threads in") = None
    ):      
        try:  
            content = ""
            changes = {}
            if alliance_ids != []:
                id_list, id_str = utils.str_to_id_list(alliance_ids)
                changes['war_threads_alliance_ids'] = id_list
                content += f"Alliance id(s) for `war threads` set to `{id_str}`"
            elif not channel:
                changes['war_threads_alliance_ids'] = []
                content += f"Alliance id(s) for `war threads` set to `None`"
            if channel:
                content += f"\nChannel for `war threads` set to <#{channel.id}>"
                perms = channel.permissions_for(ctx.guild.me)
                if not perms.view_channel:
                    await ctx.respond(f"I need the `view_channel` permission, but I do not have it in <#{channel.id}>")
                    return
                if not perms.manage_threads:
                    await ctx.respond(f"I need the `manage_threads` permission, but I do not have it in <#{channel.id}>")
                    return
                elif not perms.send_messages:
                    await ctx.respond(f"I need the `send_messages` permission, but I do not have it in <#{channel.id}>")
                    return
                elif not perms.embed_links:
                    await ctx.respond(f"I need the `embed_links` permission, but I do not have it in <#{channel.id}>")
                    return
                elif not perms.read_message_history:
                    await ctx.respond(f"I need the `read_message_history` permission, but I do not have it in <#{channel.id}>")
                    return
                changes['war_threads_channel_id'] = channel.id
            elif not alliance_ids:
                content += f"\nChannel for `war threads` set to `None`"
                changes['war_threads_channel_id'] = None
            await async_mongo.guild_configs.find_one_and_update({"guild_id": ctx.guild_id}, {"$set": changes}, upsert=True)
            await ctx.respond(content)
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
    
    @config_group.command(
        name="transactions",
        description="Configure transactions"
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def config_transactions(
        self,
        ctx: discord.ApplicationContext,
        banker_role: Option(discord.Role, "The role people must have to accept requests made via /request."),
        api_keys: Option(str, "The api key(s) you want to use for tracking transactions and for withdrawals via /request.") = [],
        track_taxes: Option(bool, "If taxes should be tracked and added to people's balances.") = False,
        retroactive: Option(bool, "If taxes and transactions should be tracked retroactively (up to 14 days).") = False,
        subtract_beige_loot: Option(bool, "If beige loot should be subtracted from the balance.") = False,
        exempt_notes: Option(str, "Comma-separated list of phrases that exempt a transaction from tracking.") = ""
    ):      
        try:  
            await ctx.defer(ephemeral=True)
            content = ""
            changes = {}

            key_list = utils.str_to_api_key_list(api_keys)
            if len(key_list) > 5:
                await ctx.edit(content=f"A maximum of 5 API keys is allowed, but you supplied {len(key_list)}!")
                return
            for key in key_list.copy():
                # similar check in scanner.py
                try:
                    res = (await utils.call(f"{{me{{nation{{alliance_position_info{{withdraw_bank view_bank}}}}}}}}", key))['data']['me']['nation']
                    if not res['alliance_position_info']['withdraw_bank']:
                        await ctx.edit(content=f"API key `{key}` does not have the `withdraw_bank` permission!")
                        return
                    elif not res['alliance_position_info']['view_bank']:
                        await ctx.edit(content=f"API key `{key}` does not have the `view_bank` permission!")
                        return
                    else:
                        pass
                except Exception as e:
                    if "Invalid API key" in str(e):
                        await ctx.edit(content=f"API key `{key}` is invalid!")
                        return

            changes['transactions_api_keys'] = key_list
            content += f"Api key(s) for tracking taxes and bank transactions as well as sending the withdrawals via `/request` set to `{key_list}`\n"

            changes['transactions_banker_role'] = banker_role.id
            content += f"Banker role set to set to {banker_role.mention}\n"

            changes['transactions_track_taxes'] = track_taxes
            content += f"Track taxes set to `{track_taxes}`\n"
        
            changes['transactions_retroactive'] = retroactive
            changes['transactions_retroactive_date'] = datetime.utcnow()
            content += f"Retroactive set to `{retroactive}`\n"

            changes['transactions_subtract_beige_loot'] = subtract_beige_loot
            content += f"Subtract beige loot set to `{subtract_beige_loot}`\n"

            exempt_list = [x.strip() for x in exempt_notes.split(",")]
            changes['transactions_exempt_notes'] = exempt_list
            content += f"Exempt notes (caps are ignored) set to `{exempt_list}`\n"

            await async_mongo.guild_configs.find_one_and_update({"guild_id": ctx.guild_id}, {"$set": changes}, upsert=True)
            await ctx.edit(content=content, allowed_mentions=discord.AllowedMentions.none())
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
    
    @config_group.command(
        name="view_current_settings",
        description="Get an overview of how Autolycus is configured in this server."
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def config_view_current_settings(
        self,
        ctx: discord.ApplicationContext,
    ):      
        try:  
            await ctx.defer(ephemeral=True)
            server = await async_mongo.guild_configs.find_one({"guild_id": ctx.guild.id})
            if not server:
                await ctx.edit("No configurable commands have been configured in this server!")
            else:
                content = "The configuration for this guild is as follows:\n\n```\n"
                for k,v in server.items():
                    content += f"{k}: {v}\n"
                await ctx.edit(content=content + "```")
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
        
    @config_group.command(
        name="reminders",
        description="Configure your personal beige reminders"
    )
    @commands.has_permissions(manage_guild=True)
    async def config_beige_reminders(
        self,
        ctx: discord.ApplicationContext,
    ):      
        try:  
            await ctx.defer()
            user = await async_mongo.global_users.find_one({"user": ctx.user.id})
            if not user:
                await ctx.edit(f"I could not find you in my database! Please use {ctx.bot.get_application_command('verify').mention} first.")
                return
            if "beige_alerts" not in user:
                user['beige_alerts'] = []
            if "beige_alerts_config" not in user:
                user['beige_alerts_config'] = []
            elif user['beige_alerts_config'] == None:
                user['beige_alerts_config'] = []
                
            while True:
                if not user['beige_alerts_config'] == []:
                    description = f"Your current configuration is to recieve reminders {utils.comma_and_list([f'{x} minutes' for x in user['beige_alerts_config']])} before a nation exits beige. Do you want to keep this configuration (and have the option to add more reminders) or do you want to discard it?"
                    embed = discord.Embed(title="Configuration of beige reminders", description=description, color=utils.EMBED_COLOR)
                    view = utils.yes_or_no_view(ctx, positive="Keep", negative="Discard")
                    await ctx.edit(embed=embed, view=view)
                    timed_out = await view.wait()
                    if timed_out:
                        return
                    if not view.result:
                        user['beige_alerts_config'] = []
                
                if not user['beige_alerts_config'] == []:
                    description = f"Your current configuration is to recieve reminders {utils.comma_and_list([f'{x} minutes' for x in user['beige_alerts_config']])} before a nation exits beige. Do you want to get another reminder at some other time?"
                else:
                    description = "You currently have no reminders configured. Do you want to add a reminder for when a nation exits beige?"

                embed = discord.Embed(title="Configuration of beige reminders", description=description, color=utils.EMBED_COLOR)
                modal = utils.SimpleModal(title="Configuration of beige reminders", label="Minutes before exiting beige", placeholder="Enter an integer, e.g. 5")
                view = utils.yes_or_no_view(ctx, positive="Add more", negative="Finish configuration", positive_style=discord.ButtonStyle.blurple, negative_style=discord.ButtonStyle.blurple)
                
                async def primary_callback(i: discord.Interaction):
                    self = view
                    self.result = True
                    await i.response.send_modal(modal)
                    self.stop()

                view.children[0].callback = primary_callback
                await ctx.edit(embed=embed, view=view)
                timed_out = await view.wait()
                if timed_out:
                    return
                
                if not view.result:
                    if user['beige_alerts_config'] == []:
                        description = "You finished the configuration without adding any reminders. The system default of 15 minutes will be used."
                    else:
                        description = f"You will be reminded {utils.comma_and_list([f'{x} minutes' for x in user['beige_alerts_config']])} before a nation exits beige."
                    embed = discord.Embed(title="Configuration of beige reminders", description=description, color=utils.EMBED_COLOR)
                    view.disable_all_items()
                    await ctx.edit(embed=embed, view=view)
                    break                        
                
                submitted = await modal.wait()
                if not submitted:
                    return
                reminder = modal.text
                if reminder.isdigit():
                    reminder = int(reminder)
                    if reminder not in user['beige_alerts_config']:
                        user['beige_alerts_config'].append(reminder)
                        user['beige_alerts_config'].sort()
                    await async_mongo.global_users.find_one_and_update({"user": ctx.user.id}, {"$set": {"beige_alerts_config": user["beige_alerts_config"]}}, upsert=True)
                else:
                    await ctx.edit(content="The input must be a positive integer!", embed=None, view=None)
                    return
            
        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
    
    @config_group.command(
        name="targets",
        description="Configure the targets command"
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def config_targets(
        self,
        ctx: discord.ApplicationContext,
        add_alliance: Option(str, "An enemy alliance to add to the targets command", autocomplete=utils.get_alliances) = None,
        remove_alliance: Option(str, "An enemy alliance to remove from the targets command", autocomplete=utils.get_target_alliances) = None,
        set_alliances: Option(str, "Overwrite existing alliances with a list of alliance ids") = [],
        view_alliances: Option(bool, "Whether or not you want to see the currently targeted alliances") = False
    ):        
        try:
            await ctx.defer()
            
            if add_alliance:
                alliance_id = None
                for aa in await utils.listify(async_mongo.alliances.find({})):
                    if add_alliance == f"{aa['name']} ({aa['id']})":
                        alliance_id = aa['id']
                        break
                    elif add_alliance == aa['id']:
                        alliance_id = aa['id']
                        break
                    elif add_alliance == aa['name']:
                        alliance_id = aa['id']
                        break
                    elif add_alliance == aa['acronym']:
                        alliance_id = aa['id']
                        break
                                    
                if alliance_id is None:
                    await ctx.respond(f"I could not find a match to `{add_alliance}` in the database!")
                    return
                
                config = await async_mongo.guild_configs.find_one({"guild_id": ctx.guild.id})
                try:
                    if alliance_id in config['targets_alliance_ids']:
                        await ctx.respond(f"An alliance with the id of `{alliance_id}` is already in the list of targeted alliances!")
                        return
                except:
                    pass

                await async_mongo.guild_configs.find_one_and_update({"guild_id": ctx.guild.id}, {"$push": {"targets_alliance_ids": alliance_id}}, upsert=True)
                await ctx.respond(f"Added `{aa['name']} ({aa['id']})` to the `/targets` command")
            
            if remove_alliance:
                alliance_id = None
                config = await async_mongo.guild_configs.find_one({"guild_id": ctx.guild.id})
                if config is None:
                    await ctx.respond(f"I could not find a match to `{remove_alliance}` amongst the targeted alliances!")
                    return
                else:
                    try:
                        ids = config['targets_alliance_ids']
                    except:
                        await ctx.respond(f"I could not find a match to `{remove_alliance}` amongst the targeted alliances!")
                        return
                alliances = await utils.listify(async_mongo.alliances.find({"id": {"$in": ids}}))
                for aa in alliances:
                    if remove_alliance == f"{aa['name']} ({aa['id']})":
                        alliance_id = aa['id']
                        break
                    elif remove_alliance == aa['id']:
                        alliance_id = aa['id']
                        break
                    elif remove_alliance == aa['name']:
                        alliance_id = aa['id']
                        break
                    elif remove_alliance == aa['acronym']:
                        alliance_id = aa['id']
                        break
                                    
                if alliance_id is None:
                    await ctx.respond(f"I could not find a match to `{remove_alliance}` amongst the targeted alliances!")
                    return

                await async_mongo.guild_configs.find_one_and_update({"guild_id": ctx.guild.id}, {"$pull": {"targets_alliance_ids": alliance_id}}, upsert=True)
                await ctx.respond(f"Removed `{aa['name']} ({aa['id']})` from the `/targets` command")
            
            if set_alliances != []:
                id_list, id_str = utils.str_to_id_list(set_alliances)
                await async_mongo.guild_configs.find_one_and_update({"guild_id": ctx.guild.id}, {"$set": {"targets_alliance_ids": id_list}}, upsert=True)
                await ctx.respond(f"Alliance id(s) for `/targets` set to `{id_str}`")
            elif not add_alliance and not remove_alliance and not view_alliances:
                id_list = []
                id_str = "None"
                await async_mongo.guild_configs.find_one_and_update({"guild_id": ctx.guild.id}, {"$set": {"targets_alliance_ids": id_list}}, upsert=True)
                await ctx.respond(f"Alliance id(s) for `/targets` set to `{id_str}`")
            
            if view_alliances:
                config = await async_mongo.guild_configs.find_one({"guild_id": ctx.guild.id})
                if config is None:
                    ids = None
                else:
                    try:
                        ids = config['targets_alliance_ids']
                    except:
                        ids = None
                alliances = await utils.listify(async_mongo.alliances.find({"id": {"$in": ids}}))
                alliance_list = []
                for aa in alliances:
                    alliance_list.append(f"`{aa['name']} ({aa['id']})`")
                if len(alliance_list) == 0:
                    await ctx.respond(f"No alliances are currently targeted!")
                    return
                await ctx.respond(f"Alliance(s) for `/targets` are set to {', '.join(alliance_list)}")

        except Exception as e:
            logger.error(e, exc_info=True)
            raise e
            
def setup(bot):
    bot.add_cog(Config(bot))