import discord
from discord.ext import commands
from discord.commands import slash_command, Option, SlashCommandGroup, permissions
import re
from typing import Union
import os
import utils
import traceback
from main import mongo

api_key = os.getenv("api_key")

class Config(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
    
    def str_to_id_list(self, str_var: str) -> tuple[list, str]:
        str_var = re.sub("[^0-9]", " ", str_var)
        str_var = str_var.strip().replace(" ", ",")
        index = 0
        while True:
            try:
                if str_var[index] == str_var[index+1] and not str_var[index].isdigit():
                    str_var = str_var[:index] + str_var[index+1:]
                    index -= 1
                index += 1
            except Exception as e: 
                break
        return str_var.split(","), str_var

    config_group = SlashCommandGroup("config", "Configure commands that need configuration")

    @config_group.command(
        name="counters",
        description="Configure the counters command"
    )
    @commands.has_permissions(manage_guild=True)
    async def config_counters(
        self,
        ctx: discord.ApplicationContext,
        alliance_ids: Option(str, "The alliance id(s) to include in the counters command")
    ):        
        id_list, id_str = self.str_to_id_list(alliance_ids)
        mongo.guild_configs.find_one_and_update({"guild_id": ctx.guild.id}, {"$set": {"counters_alliance_ids": id_list}}, upsert=True)
        await ctx.respond(f"Alliance id(s) for `/counters` set to `{id_str}`")

    @config_group.command(
        name="targets",
        description="Configure the targets command"
    )
    @commands.has_permissions(manage_guild=True)
    async def config_targets(
        self,
        ctx: discord.ApplicationContext,
        alliance_ids: Option(str, "The enemy alliance id(s) to include in the targets command")
    ):        
        id_list, id_str = self.str_to_id_list(alliance_ids)
        mongo.guild_configs.find_one_and_update({"guild_id": ctx.guild.id}, {"$set": {"targets_alliance_ids": id_list}}, upsert=True)
        await ctx.respond(f"Alliance id(s) for `/targets` set to `{id_str}`")

def setup(bot):
    bot.add_cog(Config(bot))