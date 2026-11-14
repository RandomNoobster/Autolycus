"""Discord modal UI components for user input.

Handles modal dialogs for collecting user text input within Discord commands.
"""

from __future__ import annotations

import logging

import discord

logger = logging.getLogger(__name__)

# Discord sends nothing when a modal is closed, so a wait needs its own limit.
DEFAULT_MODAL_TIMEOUT_SECONDS = 300


class SimpleModal(discord.ui.Modal):
    """Simple single-input text modal for user interaction.

    Captures text input from user and stores in self.text attribute; ``submitted``
    tells a submission apart from a timeout, since py-cord's ``wait()`` returns
    True for both.
    """

    def __init__(
        self,
        label: str,
        placeholder: str,
        *args,
        timeout: float | None = DEFAULT_MODAL_TIMEOUT_SECONDS,
        **kwargs,
    ) -> None:
        """Initialize the modal with a single text input field.

        Args:
            label: Label shown above the input field
            placeholder: Placeholder text in the input field
            timeout: Seconds to wait for a submission
            *args, **kwargs: Additional arguments for discord.ui.Modal
        """
        super().__init__(*args, timeout=timeout, **kwargs)
        self.text = ""
        self.submitted = False
        self.add_item(discord.ui.InputText(label=label, placeholder=placeholder))

    async def callback(self, interaction: discord.Interaction):
        """Store the text input and acknowledge the interaction."""
        self.text = self.children[0].value or ""
        self.submitted = True
        try:
            await interaction.response.defer()
        except discord.HTTPException:
            logger.debug("Could not acknowledge modal submission", exc_info=True)
        finally:
            self.stop()
