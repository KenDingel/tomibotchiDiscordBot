# Button Functions
import traceback
import asyncio
import datetime
from datetime import timezone

# Nextcord
import nextcord
from nextcord.ext import tasks

# Local imports
from utils.utils import logger, lock, COLOR_STATES, paused_games, get_color_name, get_color_emoji, get_color_state, generate_timer_image
from code.bot_code.game.cache import game_cache, button_message_cache
from database.database import execute_query, get_game_session_by_id, game_sessions_dict, update_local_game_sessions
from text.full_text import EXPLAINATION_TEXT
from game.end_game import get_end_game_embed
from button.button_utils import get_button_message, Failed_Interactions
from button.button_view import ButtonView

async def setup_roles(guild_id, bot):
    guild = bot.get_guild(guild_id)
    for color_name, color_value in zip(['Red', 'Orange', 'Yellow', 'Green', 'Blue', 'Purple'], COLOR_STATES):
        role = nextcord.utils.get(guild.roles, name=color_name)
        if role is None: role = await guild.create_role(name=color_name, color=nextcord.Color.from_rgb(*color_value))
        else: await role.edit(color=nextcord.Color.from_rgb(*color_value))
    logger.info(f"In {guild.name}, roles have been set up.")

async def create_button_message(game_id, bot, force_new=False):
    """
    Create a new button message or find existing one
    
    Args:
        game_id: The game session ID
        bot: The Discord bot instance
        force_new: Whether to force create a new message (default: False)
    """
    logger.info(f'Creating/finding button message for game {game_id}...')
    try:
        game_session_config = get_game_session_by_id(game_id)
        if game_session_config is None:
            logger.error(f'No game session found for game {game_id}')
            game_session = update_local_game_sessions()
            logger.info(f'Updated game sessions: {game_session}')
            game_sessions = game_sessions_dict(game_session)
            logger.info(f'Game sessions dict: {game_sessions}')
            game_session_config = game_sessions.get(game_id)
            if game_session_config is None:
                logger.error(f'No game session found for game {game_id} after update')
                return
            else:
                logger.info(f'Game session config: {game_session_config}')
        else:
            logger.info(f'Game session config: {game_session_config}')
            
        logger.info(f'Game session config: {game_session_config}')
        button_channel = bot.get_channel(game_session_config['button_channel_id'])

        if not force_new:
            async for message in button_channel.history(limit=15):
                if message.author == bot.user and message.embeds:
                    logger.info(f'Found existing button message for game {game_id}')
                    # Add the view back to the existing message
                    view = ButtonView(game_session_config['timer_duration'], bot, game_id)
                    message_id = message.id
                    bot.add_view(view, message_id=message_id)
                    button_message_cache.update_message_cache(message, game_id)
                    return message

        # If no message found or forcing new, create new message
        cooldown_hours = game_session_config['cooldown_duration']
        embed = nextcord.Embed(
            title='🚨 THE BUTTON! 🚨', 
            description=f'**Keep the button alive!**\nEach adventurer must wait **{cooldown_hours} hours** between clicks to regain their strength!'
        )
        
        if force_new:
            # Only clear old messages if forcing new
            async for message in button_channel.history(limit=15):
                if message.author == bot.user and message.embeds:
                    # If embed title includes "🚨" then delete
                    if '🚨' in message.embeds[0].title:
                        await message.delete()
                
        if not EXPLAINATION_TEXT in [msg.content async for msg in button_channel.history(limit=5)]:
            await button_channel.send(EXPLAINATION_TEXT)
        
        view = ButtonView(game_session_config['timer_duration'], bot, game_id)
        message = await button_channel.send(embed=embed, view=view)
        message_id = message.id
        button_message_cache.update_message_cache(message, game_id)
        return message
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f'Error creating button message: {e}, {tb}')
        return None

def calculate_time_to_next_color(timer_value, timer_duration):
    """
    Calculate time remaining until the next color change.
    
    Args:
        timer_value (float): Current time remaining in seconds
        timer_duration (float): Total timer duration for the game session
        
    Returns:
        tuple: (seconds_to_next_color, next_color_name)
    """
    percentage = (timer_value / timer_duration) * 100
    
    thresholds = [
        (83.33, "Purple"),
        (66.67, "Blue"),
        (50.00, "Green"),
        (33.33, "Yellow"),
        (16.67, "Orange"),
        (0.00, "Red")
    ]
    
    current_color = get_color_name(timer_value, timer_duration)
    
    # Find the next threshold
    for i, (threshold, color) in enumerate(thresholds):
        if percentage >= threshold:
            if i + 1 < len(thresholds):
                next_threshold = thresholds[i + 1][0]
                next_color = thresholds[i + 1][1]
                seconds_to_next = timer_duration * (percentage - next_threshold) / 100
                return abs(seconds_to_next) / 4, next_color
            break
    
    return 0, "Red"

# Menu Timer class 
# This class uses Nextcord's View class to create a timer that updates every 10 seconds.
# The loop utilizes tasks from Nextcord's ext module to update the timer.
# Handles game mechanics, cache, and button message updates.
class MenuTimer(nextcord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.button_message_restore_attempts = {}  # Track restore attempts per game
        
    @tasks.loop(seconds=10)
    async def update_timer_task(self):
        global lock, paused_games, game_cache, logger
        
        await asyncio.sleep(0.25)
        
        for game_id, game_session in game_sessions_dict().items():
            if paused_games and game_id in paused_games: 
                logger.info(f'Game {game_id} is paused, skipping...') 
                continue
            await asyncio.sleep(0.25)
            try:
                # Get or create button message
                button_message = await get_button_message(game_id, self.bot)
                if not button_message:
                    logger.error(f'Could not get or create button message for game {game_id}')
                    Failed_Interactions.increment()
                    continue

                # Update the timer for the button game
                try:
                    game_id = str(game_id)
                    with lock: 
                        cache_data = game_cache.get_game_cache(game_id)
                    
                    last_update_time = None
                    if cache_data:
                        latest_click_time_overall = cache_data['latest_click_time']
                        total_clicks = cache_data['total_clicks']
                        last_update_time = cache_data['last_update_time']
                        total_players = cache_data['total_players']
                        user_name = cache_data['latest_player_name']
                        last_timer_value = cache_data['last_timer_value']
                    else:
                        # Query database if cache miss
                        query = f'''
                            SELECT users.user_name, button_clicks.click_time, button_clicks.timer_value,
                                (SELECT COUNT(*) FROM button_clicks WHERE game_id = {game_id}) AS total_clicks,
                                (SELECT COUNT(DISTINCT user_id) FROM button_clicks WHERE game_id = {game_id}) AS total_players
                            FROM button_clicks
                            INNER JOIN users ON button_clicks.user_id = users.user_id
                            WHERE button_clicks.game_id = {game_id}
                            ORDER BY button_clicks.id DESC
                            LIMIT 1
                        '''
                        params = ()
                        result = execute_query(query, params, is_timer=True)
                        if not result: 
                            logger.error(f'No results found for game {game_id} cache')
                            if paused_games: 
                                paused_games = paused_games.append(game_id)
                            else: 
                                paused_games = [game_id]
                            continue
                            
                        result = result[0]
                        user_name, latest_click_time_overall, last_timer_value, total_clicks, total_players = result
                        latest_click_time_overall = latest_click_time_overall.replace(tzinfo=timezone.utc) if latest_click_time_overall.tzinfo is None else latest_click_time_overall
                        last_update_time = datetime.datetime.now(timezone.utc)
                        game_cache.update_game_cache(game_id, latest_click_time_overall, total_clicks, total_players, user_name, last_timer_value)
                        
                    elapsed_time = (datetime.datetime.now(timezone.utc) - latest_click_time_overall).total_seconds()
                    timer_value = max(game_session['timer_duration'] - elapsed_time, 0)

                    # Clear cache if last update was too long ago
                    if last_update_time is None or not last_update_time: 
                        last_update_time = datetime.datetime.now(timezone.utc)
                    if datetime.datetime.now(timezone.utc) - last_update_time > datetime.timedelta(hours=0.25):
                        logger.info(f'Clearing cache for game {game_id}, since last update was more than 15 minutes ago...')
                        game_cache.clear_game_cache(game_id)

                    # Prepare the latest user info for the embed
                    color_name = get_color_name(last_timer_value, game_session['timer_duration'])
                    color_emoji = get_color_emoji(last_timer_value, game_session['timer_duration'])
                    hours_remaining = int(last_timer_value) // 3600
                    minutes_remaining = int(last_timer_value) % 3600 // 60
                    seconds_remaining = int(int(last_timer_value) % 60)
                    formatted_timer_value = f'{hours_remaining:02d}:{minutes_remaining:02d}:{seconds_remaining:02d}'
                    formatted_time = f'<t:{int(latest_click_time_overall.timestamp())}:R>'
                    latest_user_info = f'{formatted_time} {user_name} clicked {color_emoji} {color_name} with {formatted_timer_value} left on the clock!'

                    # Handle game end condition
                    if timer_value <= 0:
                        guild_id = game_session['guild_id']
                        guild = self.bot.get_guild(guild_id)
                        embed, file = get_end_game_embed(game_id, guild)
                        try:
                            await button_message.edit(embed=embed, file=file)
                            #self.update_timer_task.stop()
                            logger.info(f'Game {game_id} Ended!')
                        except nextcord.NotFound:
                            logger.error(f'Message was deleted when trying to end game {game_id}')
                        continue

                    # Update the embed with current game state
                    embed = nextcord.Embed(title='🚨 THE BUTTON! 🚨', description='**Keep the button alive!**')
                    embed.clear_fields()
                    
                    start_time = game_session['start_time'].replace(tzinfo=timezone.utc)
                    elapsed_time = datetime.datetime.now(timezone.utc) - start_time

                    elapsed_days = elapsed_time.days
                    elapsed_hours = elapsed_time.seconds // 3600
                    elapsed_minutes = (elapsed_time.seconds % 3600) // 60
                    elapsed_seconds = elapsed_time.seconds % 60
                    elapsed_seconds = round(elapsed_seconds, 2)
                    elapsed_time_str = f'{elapsed_days} days, {elapsed_hours} hours, {elapsed_minutes} minutes, {elapsed_seconds} seconds'

                    # Calculate time to next color change
                    try:
                        seconds_to_next, next_color = calculate_time_to_next_color(timer_value, game_session['timer_duration'])
                        hours_to_next = int(seconds_to_next) // 3600
                        minutes_to_next = int(seconds_to_next) % 3600 // 60
                        seconds_to_next = int(seconds_to_next) % 60
                        next_color_time = f'{hours_to_next:02d}:{minutes_to_next:02d}:{seconds_to_next:02d}'
                        color_change_info = f'⏳ Time until {next_color}: **{next_color_time}**'
                    except Exception as e:
                        logger.error(f'Error calculating next color time: {e}')
                        color_change_info = "⏳ Color change time calculation unavailable"

                    # Add fields to embed
                    embed.add_field(
                        name='🗺️ The Saga Unfolds',
                        value=f'Valiant clickers in the pursuit of glory, have kept the button alive for...\n**{elapsed_time_str}**!\n**{total_clicks} clicks** have been made by **{total_players} adventurers**! 🛡️🗡️🏰',
                        inline=False
                    )
                    embed.add_field(name='🎉 Latest Heroic Click', value=latest_user_info, inline=False)
                    embed.add_field(name='🎨 Next Color Change', value=color_change_info, inline=False)
                    
                    embed.description = f'__The game ends when the timer hits 0__.\nClick the button to reset the clock and keep the game going!\n\nWill you join the ranks of the brave and keep the button alive? 🛡️🗡️'
                    embed.set_footer(text=f'The Button Game by Regen2Moon; Inspired by Josh Wardle\nLive Stats: https://thebuttongame.click/')
                    
                    # Generate and add timer image
                    file_buffer = generate_timer_image(timer_value, game_session['timer_duration'])
                    embed.set_image(url=f'attachment://{file_buffer.filename}')
                    
                    # Set embed color
                    pastel_color = get_color_state(timer_value, game_session['timer_duration'])
                    embed.color = nextcord.Color.from_rgb(*pastel_color)
                    
                    # Update the message
                    button_view = ButtonView(timer_value, self.bot)
                    try:
                        await button_message.edit(embed=embed, file=file_buffer, view=button_view)
                    except nextcord.NotFound:
                        logger.warning(f'Message was deleted, creating new one for game {game_id}')
                        button_message = await create_button_message(game_id, self.bot, force_new=True)
                    except Exception as e:
                        logger.error(f'Error updating button message: {str(e)}')
                        Failed_Interactions.increment()

                    try:
                        await button_message.clear_reactions()
                    except:
                        logger.error(f'Error clearing reactions for game {game_id}')
                        pass

                except Exception as e:
                    tb = traceback.format_exc()
                    logger.error(f'Error updating timer: {e}\n{tb}')
                    Failed_Interactions.increment()
                    
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error processing game {game_id}: {e}\n{tb}')
                continue

    # Ensure the loop waits for the bot to be ready before starting
    @update_timer_task.before_loop
    async def before_update_timer(self): 
        await self.bot.wait_until_ready()

    # Ensure the loop is canceled if timeout occurs
    async def on_timeout(self): 
        self.update_timer_task.cancel()
        # Add a delay before restarting the task
        await asyncio.sleep(2)
        self.update_timer_task.start()