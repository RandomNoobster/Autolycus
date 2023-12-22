from __future__ import annotations
import asyncio
import discord
import math
from . import EMBED_COLOR
from .. import LOGGER


__all__ = ["embed_pager", "reaction_checker", "SimpleModal"]


def embed_pager(title: str, fields: list, fields_per_embed: int = 24, description: str = "", color: int = EMBED_COLOR, inline: bool = True) -> list[discord.Embed]:
    """
    Takes a list of fields and returns a list of embeds.
    """
    embeds = []
    for i in range(math.ceil(len(fields)/24)):
        embeds.append(discord.Embed(
            title=f"{title} page {i+1}", description=description, color=color))
    index = 0
    n = 0
    for field in fields:
        embeds[index].add_field(
            name=f"{field['name']}", value=field['value'], inline=inline)
        n += 1
        if n % fields_per_embed == 0:
            index += 1
    return embeds


async def reaction_checker(self, message: discord.Message, embeds: list[discord.Embed]) -> None:
    """
    A reaction checker for embeds. Takes a message and a list of embeds. The user can then use reactions to change the embed.
    """
    reactions = []
    for i in range(len(embeds)):
        reactions.append(asyncio.create_task(message.add_reaction(
            f"{i+1}\N{variation selector-16}\N{combining enclosing keycap}")))
    await asyncio.gather(*reactions)
    while True:
        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=600)
            if user.bot == True or reaction.message != message:
                continue

            elif "\N{variation selector-16}\N{combining enclosing keycap}" in str(reaction.emoji):
                await message.edit(embed=embeds[int(str(reaction.emoji)[0])-1])
                await message.remove_reaction(reaction, user)

        except asyncio.TimeoutError:
            await message.edit(content="**Command timed out!**")
            break


class SimpleModal(discord.ui.Modal):
    """
    A simple modal. Takes a label and a placeholder. When the user is done interacting (you can use `await SimpleModal.wait()`), the user input can be found in `SimpleModal.text`.
    """

    def __init__(self, label: str, placeholder: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.text = ""
        self.add_item(discord.ui.InputText(
            label=label, placeholder=placeholder))

    async def callback(self, interaction: discord.Interaction) -> None:
        self.text = self.children[0].value
        await interaction.response.edit_message()
        self.stop()


class yes_or_no_view(discord.ui.View):
    def __init__(self, ctx, positive: str = "Yes", negative: str = "No", positive_style: discord.ButtonStyle = discord.ButtonStyle.green, negative_style: discord.ButtonStyle = discord.ButtonStyle.red, timeout: int = 600, author_check: bool = True):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.author_check = author_check
        self.result = None

        self.positive = positive
        positive_button = discord.ui.Button(
            label=self.positive, style=positive_style)
        positive_button.callback = self.primary_callback
        self.add_item(positive_button)

        self.negative = negative
        negative_button = discord.ui.Button(
            label=self.negative, style=negative_style)
        negative_button.callback = self.secondary_callback
        self.add_item(negative_button)

    async def primary_callback(self, i: discord.Interaction):
        self.result = True
        await i.response.edit_message()
        self.stop()

    async def secondary_callback(self, i: discord.Interaction):
        self.result = False
        await i.response.edit_message()
        self.stop()

    async def interaction_check(self, interaction) -> bool:
        if interaction.user != self.ctx.author and self.author_check:
            await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
            return False
        else:
            return True

    async def on_timeout(self):
        await run_timeout(self.ctx, self)


class Dropdown(discord.ui.Select):
    """
    select_options: Needs `embeds`, `placeholder`, `min_values`, `max_values` and `options` -> list of dicts with `label`, `description`, `emoji`, `value` (index) and `default`.
    """

    def __init__(self, main_view, select_options: dict = {}):
        self.apples = main_view
        options = []
        n = 0
        for x in select_options['options']:
            options.append(discord.SelectOption(
                label=x['label'], description=x['description'], emoji=x['emoji'], value=n, default=x['default']))
            n += 1
        self.selectable_options = options

        # The placeholder is what will be shown when no option is selected.
        # The min and max values indicate we can only pick one of the three options.
        # The options parameter, contents shown above, define the dropdown options.
        super().__init__(
            placeholder=select_options['placeholder'] or "Select an option from the dropdown",
            min_values=select_options['min_values'] or 1,
            max_values=select_options['max_values'] or 1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.apples.embeds = sorted(self.apples.embeds, key=self.selectable_options[int(
            interaction.data['values'][0])]['sort_by'], reverse=True)
        await interaction.response.edit_message(embed=self.apples.embeds[0])
        print("gg")


class switch(discord.ui.View):
    """
    select_options: Needs `embeds`, `placeholder`, `min_values`, `max_values` and `options` -> list of dicts with `label`, `description`, `emoji`, `value` and `default`.
    """

    def __init__(self, ctx, max_page: int, embeds: list, timeout: int = 600, author_check: bool = True, cur_page: int = 0, select_options: dict = {}):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.author_check = author_check
        self.cur_page = cur_page
        self.max_page = max_page - 1
        self.embeds = embeds
        if select_options:
            self.add_item(Dropdown(self, select_options))

    @discord.ui.button(label="<<", style=discord.ButtonStyle.primary)
    async def far_left_callback(self, b: discord.Button, i: discord.Interaction):
        self.cur_page = 0
        await i.response.edit_message(embed=self.embeds[0])

    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
    async def left_callback(self, b: discord.Button, i: discord.Interaction):
        if self.cur_page == 0:
            self.cur_page = self.max_page
            await i.response.edit_message(embed=self.embeds[self.cur_page])
        else:
            self.cur_page -= 1
            await i.response.edit_message(embed=self.embeds[self.cur_page])

    @discord.ui.button(label=">", style=discord.ButtonStyle.primary)
    async def right_callback(self, b: discord.Button, i: discord.Interaction):
        if self.cur_page == self.max_page:
            self.cur_page = 0
            await i.response.edit_message(embed=self.embeds[self.cur_page])
        else:
            self.cur_page += 1
            await i.response.edit_message(embed=self.embeds[self.cur_page])

    @discord.ui.button(label=">>", style=discord.ButtonStyle.primary)
    async def far_right_callback(self, b: discord.Button, i: discord.Interaction):
        self.cur_page = self.max_page
        await i.response.edit_message(embed=self.embeds[self.max_page])

    async def interaction_check(self, interaction) -> bool:
        if interaction.user != self.ctx.author and self.author_check:
            await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
            return False
        else:
            return True

    async def on_timeout(self):
        await run_timeout(self.ctx, self)


async def run_timeout(ctx, view):
    try:
        await ctx.edit(content=f"<@{ctx.author.id}> The command timed out!")
        if view:
            for x in view.children:
                x.disabled = True
            await ctx.edit(view=view)
    except Exception as e:
        LOGGER.error(str(e) + "|| This error was ignored", exc_info=False)

async def yes_or_no(self, ctx) -> Union[bool, None]:
    try:
        msg = await self.bot.wait_for('message', check=lambda message: message.author == ctx.author and message.channel.id == ctx.channel.id, timeout=40)
        if msg.content.lower() in ['yes', 'y']:
            return True
        elif msg.content.lower() in ['no', 'n']:
            return False
    except asyncio.TimeoutError:
        return None