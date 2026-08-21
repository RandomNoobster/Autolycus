"""Discord modal UI components for user input.

Handles modal dialogs for collecting user text input within Discord commands.
"""

from __future__ import annotations

import discord


class SimpleModal(discord.ui.Modal):
    """Simple single-input text modal for user interaction.
    
    Captures text input from user and stores in self.text attribute.
    """
    
    def __init__(self, label: str, placeholder: str, *args, **kwargs) -> None:
        """Initialize the modal with a single text input field.
        
        Args:
            label: Label shown above the input field
            placeholder: Placeholder text in the input field
            *args, **kwargs: Additional arguments for discord.ui.Modal
        """
        super().__init__(*args, **kwargs)
        self.text = ""
        self.add_item(discord.ui.InputText(label=label, placeholder=placeholder))

    async def callback(self, interaction: discord.Interaction):
        """Store the text input and acknowledge the interaction."""
        self.text = self.children[0].value
        await interaction.response.edit_message()
        self.stop()
