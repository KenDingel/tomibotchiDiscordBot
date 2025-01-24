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
        
        # Initialize bot attributes
        self.shutting_down = False
        self.config = self.load_config()  # Add this line
        # Add to Tomibotchi class
        async def cleanup(self):
            """Cleanup resources before shutdown"""
            # Close any open connections
            if hasattr(self, 'pool'):
                await self.pool.close()
            if hasattr(self, 'timer_pool'):
                await self.timer_pool.close()
        # Initialize bot with command prefix
        super().__init__(command_prefix=commands.when_mentioned_or('!'), intents=intents)
        # Define the extensions to load
        self.initial_extensions = ['commands.commands']  # Add other extensions as needed
        # Load the extensions
        for extension in self.initial_extensions:
            try:
                self.load_extension(extension)
            except Exception as e:
                print(f'Failed to load extension {extension}: {e}')
    async def setup_hook(self):
        # This runs before the bot starts but after it's initialized
        for extension in self.initial_extensions:
            try:
                await self.load_extension(extension)
                print(f"Successfully loaded extension {extension}")
            except Exception as e:
                print(f'Failed to load extension {extension}: {e}')
                print(traceback.format_exc())
    async def on_ready(self):
        """Called when the bot is ready"""
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print("Available commands:", [command.name for command in self.commands])
        print("Loaded cogs:", list(self.cogs.keys()))
    def load_config(self):
        """Load configuration from config.json"""
        config_file_name = os.path.join('..', '..', 'assets', 'config.json')
        config_file_name = os.path.abspath(config_file_name)
        try:
            with open(config_file_name, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error("config.json not found")
            sys.exit(1)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in config.json")
            sys.exit(1)
    def run(self):
        """Run the bot with error handling"""
        try:
            logger.info("Starting Tomibotchi bot...")
            print("DEBUG: Registered commands:")
            print(self.commands)
            print("DEBUG: Registered cogs:")
            print(self.cogs)
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