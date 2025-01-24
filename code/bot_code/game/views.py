from __future__ import annotations
import asyncio
import logging
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timezone
import traceback

import nextcord as discord
from nextcord.ext import commands, tasks
from nextcord import ButtonStyle
from nextcord.ui import Button, View

from utils.sprite_handler import SpriteHandler

from .state import (
    PetStateManager, PetState, PetStatus, InteractionType, InteractionEffect,
    INTERACTION_EFFECTS
)

# Configure logging
logger = logging.getLogger(__name__)

# Define color schemes for different pet states
STATE_COLORS = {
    PetStatus.NORMAL: discord.Color.green(),
    PetStatus.SLEEPING: discord.Color.blue(),
    PetStatus.SICK: discord.Color.red(),
    PetStatus.UNHAPPY: discord.Color.gold()
}
def create_progress_bar(value: int, max_value: int = 100, length: int = 10) -> str:
    """
    Creates a visual progress bar for stats.
    
    Args:
        value: Current value
        max_value: Maximum possible value
        length: Length of the progress bar in characters
        
    Returns:
        String representation of progress bar with value
    """
    filled = int((value / max_value) * length)
    empty = length - filled
    bar = '█' * filled + '░' * empty
    return f"{bar} {value}%"

async def get_pet_image(pet_state: PetStateManager) -> str:
    """
    Gets appropriate pet image URL based on pet state.
    
    Args:
        pet_state: Current pet state manager instance
        
    Returns:
        URL string for pet image
    """
    # Base image path format: assets/{species}_{state}.png
    base_path = f"assets/{pet_state.species.lower()}/{pet_state.species.lower()}"
    current_state = pet_state.state
    return f"{base_path}-{current_state.value}.png"

def format_cooldown(seconds: float) -> str:
    """
    Formats cooldown time remaining in a human-readable format.
    
    Args:
        seconds: Number of seconds remaining
        
    Returns:
        Formatted string (e.g., "2h 30m" or "45s")
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}m"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"

class InteractionButton(Button):
    """Button for pet interactions with cooldown and state management."""
    def __init__(
        self,
        interaction_type: InteractionType,
        style: ButtonStyle,
        pet_view: 'PetView'  # Forward reference for type hint
    ):
        self.interaction_type = interaction_type
        self.pet_view = pet_view
        self.effect = INTERACTION_EFFECTS[interaction_type]
        
        # Add unique identifier using pet_id to prevent duplicates
        custom_id = f"pet_interaction_{interaction_type.value}_{pet_view.pet_state.pet_id}"
        
        super().__init__(
            style=style,
            label=interaction_type.value.title(),
            custom_id=custom_id
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            success, message = await self.pet_view.pet_state.process_interaction(
                self.interaction_type
            )
            
            if success:
                await self.pet_view.update_display(interaction)
                await interaction.followup.send(f"✅ {message}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ {message}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error processing interaction {self.interaction_type}: {e}")
            logger.error(traceback.format_exc())
            await interaction.followup.send(
                "❌ An error occurred processing your interaction!",
                ephemeral=True
            )
    def _get_button_row(self) -> int:
        """Determines button row based on interaction type."""
        interaction_rows = {
            InteractionType.FEED: 0,
            InteractionType.CLEAN: 0,
            InteractionType.SLEEP: 1,
            InteractionType.WAKE: 1,
            InteractionType.PLAY: 2,
            InteractionType.PET: 2,
            InteractionType.EXERCISE: 3,
            InteractionType.TREAT: 3,
            InteractionType.MEDICINE: 4
        }
        return interaction_rows.get(self.interaction_type, 0)

class PetView(View):
    """Main view for pet display and interactions."""
    
    def __init__(self, pet_state: PetStateManager, bot: commands.Bot):
        """
        Initialize pet view.
        
        Args:
            pet_state: Pet state manager instance
            bot: Discord bot instance
        """
        super().__init__(timeout=None)
        self.pet_state = pet_state
        self.bot = bot
        self.sprite_handler = SpriteHandler()
        self.message: Optional[discord.Message] = None
        self._lock = asyncio.Lock()
        self.setup_buttons()
        self.start_update_loop()

    def setup_buttons(self):
        """Set up interaction buttons."""
        button_styles = {
            InteractionType.FEED: ButtonStyle.green,
            InteractionType.CLEAN: ButtonStyle.blurple,
            InteractionType.SLEEP: ButtonStyle.gray,
            InteractionType.WAKE: ButtonStyle.blurple,
            InteractionType.PLAY: ButtonStyle.green,
            InteractionType.PET: ButtonStyle.gray,
            InteractionType.EXERCISE: ButtonStyle.red,
            InteractionType.TREAT: ButtonStyle.green,
            InteractionType.MEDICINE: ButtonStyle.red
        }
        
        for interaction_type, style in button_styles.items():
            button = InteractionButton(
                interaction_type=interaction_type,
                style=style,
                pet_view=self
            )
            self.add_item(button)
    def _get_active_effects(self) -> List[str]:
        """
        Gets list of active effects on the pet.
        
        Returns:
            List of formatted strings describing active effects
        """
        active_effects = []
        
        # Add status-based effects
        if self.pet_state.state == PetStatus.SLEEPING:
            active_effects.append("💤 Sleeping - Energy recovery increased")
        elif self.pet_state.state == PetStatus.SICK:
            active_effects.append("🤒 Sick - Stats decay faster")
        elif self.pet_state.state == PetStatus.UNHAPPY:
            active_effects.append("😢 Unhappy - Needs attention")
            
        return active_effects
    async def create_status_embed(self) -> discord.Embed:
        """Creates pet status embed with current stats."""
        try:
            # Get current state
            current_state = self.pet_state.state
            
            # Get sprite URL
            sprite_url = await self.sprite_handler.get_sprite_url(
                self.pet_state.species,
                self.pet_state.state
            )
            
            embed = discord.Embed(
                title=f"{self.pet_state.name} the {self.pet_state.species}",
                description="Your virtual pet!",
                color=STATE_COLORS[current_state],
                timestamp=datetime.now(timezone.utc)
            )
            
            # Set the sprite as the embed's image
            if sprite_url:
                embed.set_image(url=sprite_url)
            
            # Add status field
            time_ago = format_cooldown(
                (datetime.now(timezone.utc) - self.pet_state.last_update)
                .total_seconds()
            )
            
            embed.add_field(
                name="Status",
                value=f"Currently: {current_state.value}\n"
                      f"Last interaction: {time_ago} ago",
                inline=False
            )
            
            # Add stats with progress bars
            stats_text = []
            for stat, value in self.pet_state.stats.items():
                icon = {
                    'happiness': '❤️',
                    'hunger': '🍖',
                    'energy': '⚡',
                    'hygiene': '✨'
                }.get(stat, '📊')
                
                stats_text.append(
                    f"{icon} {stat.title()}: {create_progress_bar(value)}"
                )
            
            embed.add_field(
                name="Stats",
                value='\n'.join(stats_text),
                inline=False
            )
            
            # Get and add active effects
            active_effects = self._get_active_effects()
            if active_effects:
                embed.add_field(
                    name="Active Effects",
                    value='\n'.join(active_effects),
                    inline=False
                )
            
            return embed
            
        except Exception as e:
            logger.error(f"Error creating status embed: {e}")
            logger.error(traceback.format_exc())
            raise
    async def update_display(self, interaction: Optional[discord.Interaction] = None):
        """Updates the pet display."""
        async with self._lock:
            try:
                # Update pet state
                await self.pet_state.update()
                
                # Create new embed
                embed = await self.create_status_embed()
                
                # Update message
                if interaction:
                    await interaction.edit_original_response(
                        embed=embed,
                        view=self
                    )
                elif self.message:
                    await self.message.edit(
                        embed=embed,
                        view=self
                    )
                    
            except Exception as e:
                logger.error(f"Error updating display: {e}")
                logger.error(traceback.format_exc())
                
                if interaction:
                    await interaction.followup.send(
                        "❌ Failed to update display!",
                        ephemeral=True
                    )
                elif self.message:
                    try:
                        await self.message.edit(embed=embed, view=self)
                    except Exception as e:
                        logger.error(f"Error in fallback message edit: {e}")
                        logger.error(traceback.format_exc())
                        
    def start_update_loop(self):
        """Starts the automatic update loop."""
        self.update_loop.start()

    def stop_update_loop(self):
        """Stops the automatic update loop."""
        self.update_loop.cancel()

    @tasks.loop(seconds=15)
    async def update_loop(self):
        """Periodically updates the display."""
        await self.update_display()

    @update_loop.error
    async def update_error(self, error: Exception):
        """
        Handles errors in the update loop.
        
        Args:
            error: Exception that occurred
        """
        logger.error(f"Error in update loop: {error}")
        logger.error(traceback.format_exc())
        
        # Try to restart the loop
        self.update_loop.restart()

    async def on_timeout(self):
        """Handles view timeout."""
        self.stop_update_loop()
        if self.message:
            try:
                await self.message.edit(view=None)
            except Exception as e:
                logger.error(f"Error removing view on timeout: {e}")

    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.stop_update_loop()
        except Exception as e:
            logger.error(f"Error during view cleanup: {e}")