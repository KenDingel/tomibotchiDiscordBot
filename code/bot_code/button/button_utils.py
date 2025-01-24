# Button 
import datetime
from datetime import timezone
import traceback
import nextcord

# Local imports
from utils.utils import logger
from code.bot_code.game.cache import button_message_cache
from database.database import update_local_game_sessions, game_sessions_dict

# Get button message
# This function is used to get the button message for the timer button.
# It first checks the cache for the button message, and if it is not found, it creates a new one.
async def get_button_message(game_id, bot):
    """
    Get button message with improved error handling and fallback logic
    """
    game_id = int(game_id)
    task_run_time = datetime.datetime.now(timezone.utc)
    
    try:
        # Clean up stale messages periodically
        await button_message_cache.cleanup_stale_messages()

        # Try to get message from cache first
        if game_id in button_message_cache.messages:
            try:
                message_id = await button_message_cache.get_message_cache(game_id)
                if message_id:
                    #logger.info(f'Fetching message {message_id} from cache for game {game_id}')
                    sessions_dict = game_sessions_dict()
                    game_session = sessions_dict.get(game_id)
                    
                    if game_session:
                        channel_id = game_session['button_channel_id']
                        channel = bot.get_channel(int(channel_id))
                        
                        if channel:
                            try:
                                message = await channel.fetch_message(message_id)
                                if message:
                                    return message
                                else: 
                                    logger.error(f'Failed to fetch message {message_id} from channel {channel_id}')
                            except nextcord.NotFound:
                                logger.warning(f'Message {message_id} not found in channel {channel_id}')
                            except Exception as e:
                                logger.error(f'Error fetching message: {e}')
                        else:
                            logger.error(f'Could not find button channel for game {game_id}')
                else:
                    logger.error(f'Failed to fetch message from cache for game {game_id}')
            except Exception as e:
                logger.error(f'Error getting message from cache: {e}')
                    
        # If we get here, either no cached message or failed to fetch it
        # Get the game session config to get the button channel id
        sessions_dict = game_sessions_dict()
        game_session = sessions_dict.get(game_id)

        if not game_session:
            logger.error(f'No game session found for game {game_id}, updating sessions...')
            game_sessions = update_local_game_sessions()
            sessions_dict = game_sessions_dict()
            game_session = sessions_dict.get(game_id)
            
            if not game_session:
                logger.error(f'Still no game session found for game {game_id} after update')
                return None

        channel = bot.get_channel(int(game_session['button_channel_id']))
        if not channel:
            logger.error(f'Could not find button channel for game {game_id}')
            return None

        # Look for existing message in channel
        async for message in channel.history(limit=10):
            if message.author == bot.user and message.embeds:
                button_message_cache.update_message_cache(message, game_id)
                logger.info(f'Found and cached existing message for game {game_id}')
                return message

        # If no existing message found, create new one
        logger.info(f'Creating new button message for game {game_id}')
        from button.button_functions import create_button_message
        message = await create_button_message(game_id, bot)
        if message:
            button_message_cache.update_message_cache(message, game_id)
            task_run_time = datetime.datetime.now(timezone.utc) - task_run_time
            logger.info(f'Created new button message. Run time: {task_run_time.total_seconds()}s')
            return message
            
        return None
        
    except Exception as e:
        logger.error(f'Error in get_button_message: {str(e)}')
        return None


# Only updating the Failed_Interaction_Count class - rest of file remains identical
class Failed_Interaction_Count:
    def __init__(self):
        self.failed_count = 0
        self.last_reset = datetime.datetime.now(timezone.utc)
        self.failure_threshold = 10

    def increment(self):
        self.failed_count += 1
        current_time = datetime.datetime.now(timezone.utc)
        # Auto-reset if it's been more than an hour
        if (current_time - self.last_reset).total_seconds() > 3600:
            self.reset()
        # Log if we hit threshold
        if self.failed_count >= self.failure_threshold:
            logger.warning(f"High interaction failure rate detected: {self.failed_count} failures since {self.last_reset}")

    def reset(self):
        self.failed_count = 0
        self.last_reset = datetime.datetime.now(timezone.utc)

    def get(self):
        return self.failed_count
    
# Create the Failed_Interactions instance
Failed_Interactions = Failed_Interaction_Count()