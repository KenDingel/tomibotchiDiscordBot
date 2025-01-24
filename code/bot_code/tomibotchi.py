from __future__ import annotations

import asyncio
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import signal
import json
import nextcord as discord
from nextcord.ext import commands, tasks
from pathlib import Path
import ssl
import os

from database.database import setup_pool, create_tables, execute_query
from commands.commands import TomibotchiCommands, setup

# Configure root logger
log_file_name = os.path.join('..', '..', '..', 'logs', f'tomibotchi-{datetime.now().strftime("%Y-%m-%d")}.log')
log_file_name = os.path.abspath(log_file_name)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file_name)
    ]
)

logger = logging.getLogger(__name__)

class ConfigError(Exception):
    """Configuration related errors"""
    pass

class Tomibotchi(commands.Bot):
    """Main bot class for Tomibotchi virtual pet system."""
    
    def __init__(self):
        """Initialize bot with required intents and configurations"""
        # Setup intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        # Initialize bot with command prefix
        super().__init__(
            command_prefix="!",
            intents=intents
        )
        
        # Internal state
        self.config: Dict[str, Any] = {}
        self.start_time: Optional[datetime] = None
        self.ready_event = asyncio.Event()
        self.shutting_down = False
        self._status_task: Optional[asyncio.Task] = None
        self._cleanup_lock = asyncio.Lock()
        
        # Setup signal handlers
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._handle_shutdown_signal)
            
        # Track rate limits
        self.rate_limit_hits = 0
        self.last_rate_limit_reset = datetime.now(timezone.utc)
        # Load Config
        self.config = {}
        asyncio.run(self.load_config())

    async def setup_hook(self):
        try:
            print("DEBUG: Starting setup_hook")
            # Load config first
            await self.load_config()
            
            # Setup database
            if not setup_pool(self.config):
                raise ConfigError("Failed to setup database pools")
            create_tables()
            
            # Load extensions
            await self.load_extensions()
            
            # Start tasks after everything is set up
            self.update_status.start()
            self.monitor_rate_limits.start()
            
        except Exception as e:
            logger.error(f"Error during setup: {e}")
            logger.error(traceback.format_exc())
            await self.close()
            sys.exit(1)
            
    async def on_ready(self):
        try:
            self.start_time = datetime.now(timezone.utc)
            
            # Initialize guild settings first
            await self._init_guild_settings()
            
            # Load extensions
            await self.load_extensions()
            
            # Update presence
            activity = discord.Game(name="with virtual pets | !help")
            await self.change_presence(activity=activity)
            
            # Signal ready
            self.ready_event.set()
            
        except Exception as e:
            logger.error(f"Error in on_ready: {e}")
            logger.error(traceback.format_exc())


    async def load_config(self) -> None:
        """Load configuration from JSON file"""
        config_path = Path(__file__).parent.parent / 'assets' / 'config.json'
        try:
            if not config_path.exists():
                raise ConfigError("Configuration file not found")
                
            with open(config_path) as f:
                self.config = json.load(f)
                
            # Validate required fields
            required_fields = {
                'token', 'sql_host', 'sql_user', 'sql_password',
                'sql_database', 'sql_port'
            }
            
            if not all(field in self.config for field in required_fields):
                raise ConfigError("Missing required configuration fields")
                
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            raise

    async def load_extensions(self):
        try:
            extensions = ['commands.commands']
            for extension in extensions:
                try:
                    if extension:  # Add null check
                        await self.load_extension(extension)
                        logger.info(f"Loaded extension: {extension}")
                except Exception as e:
                    logger.error(f"Failed to load extension {extension}: {e}")
                    logger.error(traceback.format_exc())
                    raise
        except Exception as e:
            logger.error(f"Error loading extensions: {e}")
            raise


    async def _init_guild_settings(self) -> None:
        """Initialize settings for all connected guilds"""
        query = """
            INSERT IGNORE INTO guild_settings (guild_id)
            VALUES (%s)
        """
        
        for guild in self.guilds:
            try:
                await asyncio.to_thread(
                    execute_query,
                    query,
                    (guild.id,)
                )
            except Exception as e:
                logger.error(f"Error initializing guild {guild.id}: {e}")

    @tasks.loop(minutes=5.0)
    async def update_status(self):
        """Update bot status with current stats"""
        try:
            if not self.is_ready():
                return
                
            # Get active pets count
            query = "SELECT COUNT(*) FROM pets WHERE active = TRUE"
            result = await asyncio.to_thread(execute_query, query)
            pet_count = result[0][0] if result else 0
            
            # Update status
            activity = discord.Game(
                name=f"with {pet_count} pets | !help"
            )
            await self.change_presence(activity=activity)
            
        except Exception as e:
            logger.error(f"Error updating status: {e}")

    @tasks.loop(minutes=1.0)
    async def monitor_rate_limits(self):
        """Monitor and handle Discord API rate limits"""
        try:
            now = datetime.now(timezone.utc)
            
            # Reset counter every hour
            if (now - self.last_rate_limit_reset).total_seconds() >= 3600:
                self.rate_limit_hits = 0
                self.last_rate_limit_reset = now
                
            # Log if hitting limits frequently
            if self.rate_limit_hits > 50:  # Arbitrary threshold
                logger.warning(
                    f"High rate limit hits: {self.rate_limit_hits} in the last hour"
                )
                
        except Exception as e:
            logger.error(f"Error in rate limit monitor: {e}")

    async def on_error(self, event_method: str, *args, **kwargs):
        """Handle errors in event handlers"""
        logger.error(f"Error in {event_method}")
        logger.error(traceback.format_exc())

    async def handle_error(self, error: Exception):
        """Global error handler"""
        try:
            if isinstance(error, commands.CommandNotFound):
                return  # Ignore invalid commands
                
            elif isinstance(error, commands.MissingPermissions):
                return  # Handled by command error handlers
                
            elif isinstance(error, discord.HTTPException):
                logger.error(f"Discord API Error: {error}")
                
                if error.status == 429:  # Rate limit
                    self.rate_limit_hits += 1
                    
            else:
                logger.error(f"Unhandled error: {error}")
                logger.error(traceback.format_exc())
                
        except Exception as e:
            logger.error(f"Error in error handler: {e}")

    def _handle_shutdown_signal(self, signum, frame):
        """Handle shutdown signals"""
        if self.shutting_down:
            logger.warning("Received second shutdown signal, forcing exit")
            sys.exit(1)
            
        self.shutting_down = True
        logger.info("Shutdown signal received, cleaning up...")
        
        # Schedule cleanup
        asyncio.create_task(self.cleanup())

    async def cleanup(self):
        """Cleanup resources on shutdown"""
        async with self._cleanup_lock:
            try:
                logger.info("Starting cleanup...")
                
                # Cancel tasks
                if self._status_task and not self._status_task.done():
                    self._status_task.cancel()
                    
                self.update_status.cancel()
                self.monitor_rate_limits.cancel()
                
                # Update all pets one final time
                if hasattr(self, 'cogs') and 'TomibotchiCommands' in self.cogs:
                    cog = self.cogs['TomibotchiCommands']
                    await cog.state_manager.update_all()
                
                # Close bot
                await self.close()
                
                logger.info("Cleanup completed")
                
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
                logger.error(traceback.format_exc())
            finally:
                sys.exit(0)

    def run(self):
        """Run the bot with error handling"""
        try:
            logger.info("Starting Tomibotchi bot...")
            print("DEBUG: Registered commands:")
            print(self.commands)  # This will show all registered commands
            print("DEBUG: Registered cogs:")
            print(self.cogs)      # This will show all registered cogs
            super().run(self.config['token'])
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            logger.error(traceback.format_exc())
            sys.exit(1)
            
        finally:
            if not self.shutting_down:
                asyncio.run(self.cleanup())

if __name__ == "__main__":
    try:
        print("Starting Tomibotchi")
        bot = Tomibotchi()
        bot.run()
    except KeyboardInterrupt:
        pass  # Handle via signal handler
    except Exception as e:
        logger.critical(f"Bot crashed: {e}")
        logger.critical(traceback.format_exc())
        sys.exit(1)