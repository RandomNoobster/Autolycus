from __future__ import annotations
import traceback
import src.utils as utils
import src.env as env
import discord

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




async def update_message(message: discord.Message):
    # create the embed, needs the guild id
    # keep the same view? 
    pass   

async def add_alliances(alliance_ids: str):
    pass

async def remove_alliances():
    pass

async def set_alliances(alliance_ids: str):
    id_list, id_str = utils.str_to_id_list(alliance_ids)
    await env.ASYNC_MONGO.guild_configs.find_one_and_update({"guild_id": ctx.guild.id}, {"$set": {"counters_alliance_ids": id_list}}, upsert=True)
    return id_str
    
class Dropdown(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Select an option...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Add alliances", description="This is the first option"),
                discord.SelectOption(label="Remove alliances", description="This is the second option"),
                discord.SelectOption(label="Set alliances", description="This is the second option"),
            ])
    
    async def callback(self, interaction: discord.Interaction):
        
        if self.values[0] == self.options[0].label:
            await interaction.response.send_modal(modals)
        
        await interaction.response.send_modal(Feedback())
        await interaction.message.reply(f"{self.values[0]} was selected.")
        await interaction.message.edit(view=None)

class DropdownView(discord.ui.View):
    def __init__(self):
        super().__init__()

        # Adds the dropdown to our view object.
        self.add_item(Dropdown())

class Feedback(discord.ui.Modal, title='Feedback'):
    # Our modal classes MUST subclass `discord.ui.Modal`,
    # but the title can be whatever you want.

    # This will be a short input, where the user can enter their name
    # It will also have a placeholder, as denoted by the `placeholder` kwarg.
    # By default, it is required and is a short-style input which is exactly
    # what we want.
    name = discord.ui.TextInput(
        label='Name',
        placeholder='Your name here...',
    )

    # This is a longer, paragraph style input, where user can submit feedback
    # Unlike the name, it is not required. If filled out, however, it will
    # only accept a maximum of 300 characters, as denoted by the
    # `max_length=300` kwarg.
    feedback = discord.ui.TextInput(
        label='What do you think of this new feature?',
        style=discord.TextStyle.long,
        placeholder='Type your feedback here...',
        required=False,
        max_length=300,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(f'Thanks for your feedback, {self.name.value}!', ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Oops! Something went wrong.', ephemeral=True)

        # Make sure we know what the error actually is
        traceback.print_exception(type(error), error, error.__traceback__)