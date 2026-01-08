from __future__ import annotations

import asyncio
from typing import Optional

import discord

from discord_utils.modals import SimpleModal

# Discord UI components only. No business logic here.

async def run_timeout(ctx, view: Optional[discord.ui.View]) -> None:
    try:
        await ctx.edit(content=f"<@{ctx.author.id}> The command timed out!")
        if view:
            for x in view.children:
                x.disabled = True
            await ctx.edit(view=view)
    except Exception:
        # Swallow timeout errors silently; logging handled by caller
        pass

class YesOrNoView(discord.ui.View):
    def __init__(self, ctx, positive: str = "Yes", negative: str = "No", positive_style: discord.ButtonStyle = discord.ButtonStyle.green, negative_style: discord.ButtonStyle = discord.ButtonStyle.red, timeout: int = 600, author_check: bool = True):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.author_check = author_check
        self.result: Optional[bool] = None
        positive_button = discord.ui.Button(label=positive, style=positive_style)
        positive_button.callback = self.primary_callback
        self.add_item(positive_button)
        negative_button = discord.ui.Button(label=negative, style=negative_style)
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
        return True
    
    async def on_timeout(self):
        await run_timeout(self.ctx, self)

class Dropdown(discord.ui.Select):
    def __init__(self, main_view, select_options: dict = {}):
        self.apples = main_view
        options = []
        n = 0
        for x in select_options.get('options', []):
            options.append(discord.SelectOption(label=x['label'], description=x['description'], emoji=x['emoji'], value=n, default=x.get('default', False)))
            n += 1
        self.selectable_options = options
        super().__init__(
            placeholder=select_options.get('placeholder', "Select an option from the dropdown"),
            min_values=select_options.get('min_values', 1),
            max_values=select_options.get('max_values', 1),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.apples.embeds = sorted(self.apples.embeds, key=self.selectable_options[int(interaction.data['values'][0])]['sort_by'], reverse=True)
        await interaction.response.edit_message(embed=self.apples.embeds[0])

class Switch(discord.ui.View):
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
    async def far_left_callback(self, _button: discord.Button, interaction: discord.Interaction) -> None:
        self.cur_page = 0
        await interaction.response.edit_message(embed=self.embeds[0])

    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
    async def left_callback(self, _button: discord.Button, interaction: discord.Interaction) -> None:
        if self.cur_page == 0:
            self.cur_page = self.max_page
        else:
            self.cur_page -= 1
        await interaction.response.edit_message(embed=self.embeds[self.cur_page])
    
    @discord.ui.button(label=">", style=discord.ButtonStyle.primary)
    async def right_callback(self, _button: discord.Button, interaction: discord.Interaction) -> None:
        if self.cur_page == self.max_page:
            self.cur_page = 0
        else:
            self.cur_page += 1
        await interaction.response.edit_message(embed=self.embeds[self.cur_page])
    
    @discord.ui.button(label=">>", style=discord.ButtonStyle.primary)
    async def far_right_callback(self, _button: discord.Button, interaction: discord.Interaction) -> None:
        self.cur_page = self.max_page
        await interaction.response.edit_message(embed=self.embeds[self.max_page])
    
    async def interaction_check(self, interaction) -> bool:
        if interaction.user != self.ctx.author and self.author_check:
            await interaction.response.send_message("These buttons are reserved for someone else!", ephemeral=True)
            return False
        return True
    
    async def on_timeout(self) -> None:
        await run_timeout(self.ctx, self)

async def reaction_checker(bot: discord.Bot, message: discord.Message, embeds: list[discord.Embed]) -> None:
    reactions = []
    for i in range(len(embeds)):
        reactions.append(asyncio.create_task(message.add_reaction(f"{i+1}\N{variation selector-16}\N{combining enclosing keycap}")))
    await asyncio.gather(*reactions)
    while True:
        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=600)
            if user.bot or reaction.message != message:
                continue
            elif "\N{variation selector-16}\N{combining enclosing keycap}" in str(reaction.emoji):
                await message.edit(embed=embeds[int(str(reaction.emoji)[0])-1])
                await message.remove_reaction(reaction, user)
        except asyncio.TimeoutError:
            await message.edit(content="**Command timed out!**")
            break
