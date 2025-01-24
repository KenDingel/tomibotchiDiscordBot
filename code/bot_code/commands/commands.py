from __future__ import annotations

import nextcord as discord
from nextcord.ext import commands
import logging
import traceback
from typing import Optional
from datetime import datetime, timezone

from game.state import PetStateManager, PetState, InteractionType
from game.views import PetView
from database.database import create_pet, execute_query

# Configure logging
logger = logging.getLogger(__name__)

class PetError(Exception):
    """Base exception for pet-related errors"""
    pass

class PetNotFound(PetError):
    """Pet doesn't exist"""
    pass

class PetLimitReached(PetError):
    """User has reached pet limit"""
    pass

class InvalidPetName(PetError):
    """Invalid pet name"""
    pass

class TomibotchiCommands(commands.Cog):
    """Command handler for Tomibotchi virtual pet system"""
    def __init__(self, bot: commands.Bot):
        print("DEBUG: Initializing TomibotchiCommands")
        self.bot = bot
        self.state_manager = PetStateManager()  # Remove pet_id and initial_stats as they're managed per pet
        self.valid_species = {'cat', 'dog'} #, 'rabbit', 'hamster'}
        self.pet_limit = 2  # Default pet limit for regular users
        print("DEBUG: TomibotchiCommands initialized")
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Log when commands are ready"""
        print("DEBUG: TomibotchiCommands Cog is ready!")
        print("DEBUG: Available commands:", [command.name for command in self.get_cog_commands()])
        print("Bot has completed boot up sequence.")
    
    def get_cog_commands(self):
        """Get list of commands in this cog"""
        return [command for command in self.bot.get_cog('TomibotchiCommands').get_commands()]
    
    async def validate_pet_name(self, name: str) -> bool:
        """
        Validate pet name.
        
        Args:
            name: Name to validate
            
        Returns:
            bool: True if valid, raises InvalidPetName if not
        """
        if not 3 <= len(name) <= 20:
            raise InvalidPetName("Pet name must be between 3 and 20 characters")
            
        if not all(c.isalnum() or c.isspace() for c in name):
            raise InvalidPetName("Pet name can only contain letters, numbers, and spaces")
            
        # Could add profanity check here
        return True
        
    async def get_user_pet_count(self, user_id: int) -> int:
        """Get number of active pets for user."""
        query = """
            SELECT COUNT(*) FROM pets 
            WHERE user_id = %s AND active = TRUE
        """
        result = await self.bot.loop.run_in_executor(
            None, execute_query, query, (user_id,)
        )
        return result[0][0] if result else 0
    
    @commands.command()
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def create(self, ctx: commands.Context, name: str, species: str):
        """
        Create a new pet.
        
        Usage: !create <name> <species>
        Example: !create Fluffy cat
        """
        try:
            # Validate inputs
            species = species.lower()
            if species not in self.valid_species:
                await ctx.send(
                    embed=discord.Embed(
                        title="❌ Invalid Species",
                        description=f"Available species: {', '.join(self.valid_species)}",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
                return
                
            await self.validate_pet_name(name)
            
            # Check pet limit
            pet_count = await self.get_user_pet_count(ctx.author.id)
            if pet_count >= self.pet_limit:
                raise PetLimitReached()
            
            # Create pet
            pet_id = await self.bot.loop.run_in_executor(
                None, 
                create_pet,
                ctx.author.id,
                ctx.guild.id,
                name,
                species
            )
            
            if not pet_id:
                raise PetError("Failed to create pet")
            
            # Load pet state and create view
            async with self.state_manager.get_pet_state(pet_id) as pet_state:
                if not pet_state:
                    raise PetError("Failed to initialize pet state")
                    
                view = PetView(pet_state, self.bot)
                embed = await view.create_status_embed()
                    
                # Send initial message
                view.message = await ctx.send(
                    embed=embed,
                    view=view
                )
                
            logger.info(
                f"Pet created: {name} ({species}) for user {ctx.author.id}"
            )
            
        except InvalidPetName as e:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Invalid Pet Name",
                    description=str(e),
                    color=discord.Color.red()
                )
            )
        except PetLimitReached:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Pet Limit Reached",
                    description="You can only have 3 pets! Support us for more slots!",
                    color=discord.Color.red()
                )
            )
        except Exception as e:
            logger.error(f"Error creating pet: {e} tb: {traceback.format_exc()}")
            logger.error(traceback.format_exc())
            await ctx.send("❌ An error occurred creating your pet!")
    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def show(self, ctx: commands.Context, pet_name: Optional[str] = None):
        """Display your pet's status."""
        try:
            # Get user's pets
            query = """
                SELECT pet_id, name FROM pets
                WHERE user_id = %s AND active = TRUE
                ORDER BY creation_date DESC
            """
            logger.info(f"Fetching pets for user {ctx.author.id}")  # Added logging
            result = await self.bot.loop.run_in_executor(
                None, execute_query, query, (ctx.author.id,)
            )
            
            if not result:
                await ctx.send("You don't have any pets! Use !create to get started.")
                return
                
            # Find requested pet or use most recent
            pet_id = None
            if pet_name:
                for pid, name in result:
                    if name.lower() == pet_name.lower():
                        pet_id = pid
                        break
                if not pet_id:
                    await ctx.send(f"Couldn't find a pet named {pet_name}!")
                    return
            else:
                pet_id = result[0][0]
            
            logger.info(f"Loading pet state for pet_id: {pet_id}")  # Added logging
            # Show pet status
            pet_state = await self.state_manager.get_pet_state(pet_id)
            if not pet_state:
                raise PetError(f"Failed to load state for pet {pet_id}")
                
            view = PetView(pet_state, self.bot)
            embed = await view.create_status_embed()  # Unpack both embed and file
                
            # Send both embed and file together
            view.message = await ctx.send(
                embed=embed,
                view=view
            )
                
        except Exception as e:
            logger.error(f"Error showing pet: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            await ctx.send("❌ An error occurred showing your pet!")
    @commands.command()
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def rename(self, ctx: commands.Context, pet_name: str, new_name: str):
        """
        Rename your pet.
        
        Usage: !rename <current_name> <new_name>
        Example: !rename Fluffy Spot
        """
        try:
            # Validate new name
            await self.validate_pet_name(new_name)
            
            # Update pet name
            query = """
                UPDATE pets 
                SET name = %s
                WHERE user_id = %s AND name = %s AND active = TRUE
                RETURNING pet_id
            """
            result = await self.bot.loop.run_in_executor(
                None, execute_query, query, 
                (new_name, ctx.author.id, pet_name)
            )
            
            if not result:
                await ctx.send(f"Couldn't find a pet named {pet_name}!")
                return
                
            # Show updated pet
            pet_id = result[0][0]
            async with self.state_manager.get_pet_state(pet_id) as pet_state:
                if not pet_state:
                    raise PetError("Failed to load pet state")
                    
                pet_state.name = new_name
                view = PetView(pet_state, self.bot)
                embed = await view.create_status_embed()
                
                await ctx.send(
                    embed=discord.Embed(
                        title="✅ Pet Renamed",
                        description=f"Your pet is now called {new_name}",
                        color=discord.Color.blue()
                    )
                )
                
                view.message = await ctx.send(
                    embed=embed,
                    view=view
                )
                
        except InvalidPetName as e:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Invalid Pet Name",
                    description=str(e),
                    color=discord.Color.red()
                )
            )
        except Exception as e:
            logger.error(f"Error renaming pet: {e}")
            logger.error(traceback.format_exc())
            await ctx.send("❌ An error occurred renaming your pet!")
    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def info(self, ctx: commands.Context):
        """Show pet care instructions"""
        embed = discord.Embed(
            title="🐾 Pet Care Guide",
            description="How to take care of your Tomibotchi pet!",
            color=discord.Color.blue()
        )
        
        # Add basic info
        embed.add_field(
            name="Basic Needs",
            value=(
                "• Feed your pet regularly to maintain hunger\n"
                "• Clean your pet to maintain hygiene\n"
                "• Let your pet sleep when energy is low\n"
                "• Play and interact to maintain happiness"
            ),
            inline=False
        )
        
        # Add state info
        embed.add_field(
            name="Pet States",
            value=(
                "• Normal: Pet is healthy and happy\n"
                "• Sleeping: Pet is resting (low energy)\n"
                "• Sick: Pet needs medicine (low hygiene)\n"
                "• Unhappy: Pet needs attention (low happiness)"
            ),
            inline=False
        )
        
        # Add interaction info
        embed.add_field(
            name="Interactions",
            value=(
                "• Feed: +30 hunger, slight happiness boost\n"
                "• Clean: +40 hygiene, uses some energy\n"
                "• Play: Major happiness boost, uses energy\n"
                "• Exercise: Happiness boost, uses lots of energy\n"
                "• Treat: Major happiness boost (limit 3/day)"
            ),
            inline=False
        )
        
        await ctx.send(embed=embed)
    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def stats(self, ctx: commands.Context, pet_name: Optional[str] = None):
        """Show detailed pet statistics"""
        try:
            # Get pet info
            query = """
                SELECT p.pet_id, p.name, p.species, p.creation_date,
                       COUNT(DISTINCT i.interaction_id) as total_interactions,
                       MAX(i.interaction_time) as last_interaction
                FROM pets p
                LEFT JOIN interaction_history i ON p.pet_id = i.pet_id
                WHERE p.user_id = %s AND p.active = TRUE
                AND (p.name = %s OR %s IS NULL)
                GROUP BY p.pet_id, p.name, p.species, p.creation_date
                ORDER BY p.creation_date DESC
                LIMIT 1
            """
            result = await self.bot.loop.run_in_executor(
                None, execute_query, query,
                (ctx.author.id, pet_name, pet_name)
            )
            
            if not result:
                await ctx.send(
                    "Pet not found!" if pet_name 
                    else "You don't have any pets!"
                )
                return
                
            pet_id, name, species, created, interactions, last_interact = result[0]
            
            # Create stats embed
            embed = discord.Embed(
                title=f"📊 {name}'s Statistics",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            # Basic info
            embed.add_field(
                name="Basic Info",
                value=(
                    f"Species: {species}\n"
                    f"Created: <t:{int(created.timestamp())}:R>\n"
                    f"Total Interactions: {interactions}"
                ),
                inline=False
            )
            
            if last_interact:
                embed.add_field(
                    name="Last Interaction",
                    value=f"<t:{int(last_interact.timestamp())}:R>",
                    inline=False
                )
            
            # Get detailed interaction stats
            stats_query = """
                SELECT interaction_type, COUNT(*) as count
                FROM interaction_history
                WHERE pet_id = %s
                GROUP BY interaction_type
                ORDER BY count DESC
            """
            stats_result = await self.bot.loop.run_in_executor(
                None, execute_query, stats_query, (pet_id,)
            )
            
            if stats_result:
                stats_text = []
                for interaction_type, count in stats_result:
                    stats_text.append(f"{interaction_type}: {count}")
                    
                embed.add_field(
                    name="Interaction Breakdown",
                    value='\n'.join(stats_text),
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error showing pet stats: {e}")
            logger.error(traceback.format_exc())
            await ctx.send("❌ An error occurred showing pet stats!")
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def reset(self, ctx: commands.Context, user: discord.Member):
        """Reset a user's pet data"""
        try:
            # Deactivate all pets
            query = """
                UPDATE pets
                SET active = FALSE
                WHERE user_id = %s
                RETURNING pet_id
            """
            result = await self.bot.loop.run_in_executor(
                None, execute_query, query, (user.id,)
            )
            
            if not result:
                await ctx.send(f"{user.name} has no pets to reset!")
                return
            
            # Remove from state manager
            for pet_id, in result:
                await self.state_manager.remove_pet(pet_id)
            
            await ctx.send(
                embed=discord.Embed(
                    title="✅ Pet Data Reset",
                    description=f"Reset pet data for {user.name}",
                    color=discord.Color.green()
                )
            )
            
            logger.info(f"Reset pet data for user {user.id}")
            
        except Exception as e:
            logger.error(f"Error resetting pet data: {e}")
            logger.error(traceback.format_exc())
            await ctx.send("❌ An error occurred resetting pet data!")
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def configure(self, ctx: commands.Context, setting: str, value: str):
        """Configure server-specific settings"""
        try:
            setting = setting.lower()
            
            if setting == "pet_channel":
                # Extract channel ID from mention
                try:
                    channel_id = int(value.strip("<#>"))
                    channel = ctx.guild.get_channel(channel_id)
                    if not channel:
                        raise ValueError("Invalid channel")
                except ValueError:
                    await ctx.send("❌ Invalid channel! Please mention a valid channel.")
                    return
                
                # Update guild settings
                query = """
                    INSERT INTO guild_settings (guild_id, pet_channel_id)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE pet_channel_id = VALUES(pet_channel_id)
                """
                await self.bot.loop.run_in_executor(
                    None, execute_query, query,
                    (ctx.guild.id, channel_id)
                )
                
                await ctx.send(
                    embed=discord.Embed(
                        title="✅ Setting Updated",
                        description=f"Pet channel set to {channel.mention}",
                        color=discord.Color.green()
                    )
                )
                
            elif setting == "update_frequency":
                try:
                    frequency = int(value)
                    if not 5 <= frequency <= 60:
                        raise ValueError("Frequency must be between 5 and 60 minutes")
                except ValueError as e:
                    await ctx.send(f"❌ Invalid value: {str(e)}")
                    return
                
                # Update guild settings
                query = """
                    INSERT INTO guild_settings (guild_id, update_frequency)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE update_frequency = VALUES(update_frequency)
                """
                await self.bot.loop.run_in_executor(
                    None, execute_query, query,
                    (ctx.guild.id, frequency)
                )
                
                await ctx.send(
                    embed=discord.Embed(
                        title="✅ Setting Updated",
                        description=f"Update frequency set to {frequency} minutes",
                        color=discord.Color.green()
                    )
                )
                
            else:
                await ctx.send("❌ Unknown setting! Available settings: pet_channel, update_frequency")
                
        except Exception as e:
            logger.error(f"Error configuring settings: {e}")
            logger.error(traceback.format_exc())
            await ctx.send("❌ An error occurred updating settings!")
    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def tutorial(self, ctx: commands.Context):
        """Show game tutorial"""
        embed = discord.Embed(
            title="🎮 Tomibotchi Tutorial",
            description="Welcome to Tomibotchi! Here's how to get started:",
            color=discord.Color.blue()
        )
        
        # Getting Started
        embed.add_field(
            name="Getting Started",
            value=(
                "1. Create a pet with `!create <name> <species>`\n"
                "2. View your pet with `!show`\n"
                "3. Use the buttons below your pet to interact\n"
                "4. Keep your pet happy and healthy!"
            ),
            inline=False
        )
        
        # Basic Commands
        embed.add_field(
            name="Basic Commands",
            value=(
                "`!create` - Create a new pet\n"
                "`!show` - Display your pet\n"
                "`!rename` - Change your pet's name\n"
                "`!info` - View pet care guide\n"
                "`!stats` - View detailed statistics"
            ),
            inline=False
        )
        
        # Tips
        embed.add_field(
            name="Tips",
            value=(
                "• Keep hunger and hygiene high to prevent sickness\n"
                "• Let your pet sleep when energy is low\n"
                "• Regular interaction keeps happiness high\n"
                "• Treats give big happiness boosts but are limited"
            ),
            inline=False
        )
        
        await ctx.send(embed=embed)
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: Exception):
        """Global error handler for commands"""
        if isinstance(error, commands.CommandOnCooldown):
            # Format cooldown message
            await ctx.send(
                embed=discord.Embed(
                    title="⏳ Slow Down!",
                    description=f"Try again in {error.retry_after:.1f}s",
                    color=discord.Color.red()
                )
            )
            
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Missing Permissions",
                    description="You don't have permission to use this command!",
                    color=discord.Color.red()
                )
            )
            
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Missing Arguments",
                    description=f"Missing required argument: {error.param.name}",
                    color=discord.Color.red()
                )
            )
            
        else:
            logger.error(f"Command error in {ctx.command}: {error}")
            logger.error(traceback.format_exc())
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Error",
                    description="An unexpected error occurred!",
                    color=discord.Color.red()
                )
            )
    async def _cleanup_task(self):
        """Background task to clean up stale pet states"""
        try:
            while not self.bot.is_closed():
                await self.state_manager.cleanup_cache()
                await asyncio.sleep(300)  # Run every 5 minutes
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
            logger.error(traceback.format_exc())
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Initialize settings when bot joins a new guild"""
        try:
            query = """
                INSERT IGNORE INTO guild_settings (guild_id)
                VALUES (%s)
            """
            await self.bot.loop.run_in_executor(
                None, execute_query, query, (guild.id,)
            )
            logger.info(f"Initialized settings for guild {guild.id}")
            
        except Exception as e:
            logger.error(f"Error initializing guild {guild.id}: {e}")
            logger.error(traceback.format_exc())
            
    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """Cleanup when bot leaves a guild"""
        try:
            # Deactivate pets in guild
            query = """
                UPDATE pets
                SET active = FALSE
                WHERE guild_id = %s
                RETURNING pet_id
            """
            result = await self.bot.loop.run_in_executor(
                None, execute_query, query, (guild.id,)
            )
            
            # Remove from state manager
            if result:
                for pet_id, in result:
                    await self.state_manager.remove_pet(pet_id)
                    
            logger.info(f"Cleaned up {len(result) if result else 0} pets for guild {guild.id}")
            
        except Exception as e:
            logger.error(f"Error cleaning up guild {guild.id}: {e}")
            logger.error(traceback.format_exc())
    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        # Cancel background tasks
        self._cleanup_task.cancel()
        
        # Force update all pets one last time
        self.bot.loop.create_task(self.state_manager.update_all())
        logger.info("Tomibotchi commands unloaded")

def setup(bot):
    """Add the cog to the bot."""
    cog = TomibotchiCommands(bot)
    bot.add_cog(cog)
    print("DEBUG: TomibotchiCommands cog added to bot")