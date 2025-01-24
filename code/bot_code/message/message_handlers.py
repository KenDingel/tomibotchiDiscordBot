# message_handlers.py
import datetime
from datetime import timezone
import traceback
from typing import Dict, List, Tuple
import nextcord

# Local imports
from database.database import get_game_session_by_guild_id, create_game_session, get_game_session_by_id, get_all_game_channels, execute_query, game_sessions_dict, update_local_game_sessions, insert_first_click
from utils.utils import config, logger, lock, format_time, get_color_emoji, get_color_state
from text.full_text import LORE_TEXT
from button.button_functions import setup_roles, create_button_message, paused_games


# Handle message function
# This function is responsible for handling messages in the game channels.
# Command List: <command_name>: <command_in_discord> **<description>**
# - startbutton: sb **Starts the button game**
# - myrank: rank **Check your personal stats**
# - leaderboard: scores, scoreboard, top **Check the top 10 clickers**
# - check **Check if you have a click ready**
async def handle_message(message, bot, menu_timer):
    global paused_games, lock, logger
    if message.author == bot.user and message.content.lower() != "sb": return
    if not isinstance(message.channel, nextcord.DMChannel) and message.channel.id not in [
        1236468062107209758, 1236468247856156722, # Moon's Server
        1305588554210087105, 1305588592147693649, 
        1305622604261883955, 1305683310525288448, 
        1308486315502997574, 1308488586215292988, # Goon Squad
        1310445586394382357, 1310445611652223047, # Lilith's Den
        1311011995868336209, 1311012042907586601, # BlackRoseThorns
        1315352789034995782, 1315353475328245874 # Midnight Vibes
        ]: return #get_all_game_channels() and message.content.lower() != 'sb': return
    
    try:
        logger.info(f"Message received in {message.guild.name}: {message.content}")
    except:
        logger.info(f"Message received in DM: {message.content}")
    try:
        
        if message.content.lower() == 'startbutton' or message.content.lower() == 'sb':
            logger.info(f"Starting button game in {message.guild.name}")
            # Check if the user has admin permissions or is the bot
            if (message.author.guild_permissions.administrator or message.author.id == 692926265405079632) or message.author == bot.user:
                #await message.channel.purge(limit=10, check=lambda m: m.author == bot.user)
                
                async for m in message.channel.history(limit=5):
                    if m.author == bot.user and (m.content.lower() == "sb" or m.content.lower() == "startbutton"):
                        try: await m.delete()
                        except: pass
                        
                game_session = get_game_session_by_guild_id(message.guild.id)
                if game_session:
                    await create_button_message(game_session['game_id'], bot)
                    logger.info(f"Button game already started in {message.guild.name}")
                else:
                    logger.info(f"Starting button game in {message.guild.name}")
                    start_time = datetime.datetime.now(timezone.utc)
                    timer_duration = message.content.split(" ")[1] if len(message.content.split(" ")) > 2 else config['timer_duration']
                    cooldown_duration = message.content.split(" ")[2] if len(message.content.split(" ")) > 2 else config['cooldown_duration']
                    chat_channel_id = message.content.split(" ")[3] if len(message.content.split(" ")) > 3 else message.channel.id
                    
                    admin_role_id = 0
                    try:
                        admin_role = nextcord.utils.get(message.guild.roles, name='Button Master')
                        if not admin_role: admin_role = await message.guild.create_role(name='Button Master')
                        if not admin_role in message.author.roles: await message.author.add_roles(admin_role)
                        admin_role_id = admin_role.id
                    except Exception as e:
                        tb = traceback.format_exc()
                        logger.error(f'Error adding role: {e}, {tb}')
                        logger.info('Skipping role addition...')
                    
                    game_id = create_game_session(admin_role_id, message.guild.id, message.channel.id, chat_channel_id, start_time, timer_duration, cooldown_duration)
                    
                    game_session = get_game_session_by_id(game_id)
                    game_sessions_as_dict = game_sessions_dict()
                    if game_sessions_as_dict:
                        game_sessions_as_dict[game_id] = game_session
                    else:
                        game_sessions_as_dict = {game_id: game_session}

                    update_local_game_sessions()
                    
                    if game_id in paused_games: 
                        try:
                            paused_games.remove(game_id)
                            logger.info(f'Game session {game_id} removed from paused games.')
                        except Exception as e:
                            tb = traceback.format_exc()
                            logger.error(f'Error removing game session from paused games: {e}, {tb}')
                            pass
                    
                    await setup_roles(message.guild.id, bot)
                    update_local_game_sessions()
                    await create_button_message(game_id, bot)
                
                if menu_timer and not menu_timer.update_timer_task.is_running():
                    logger.info('Starting update timer task...')
                    menu_timer.update_timer_task.start()
                elif not menu_timer:
                    logger.error('Menu timer not found.')
        
            else: await message.channel.send('You do not have permission to start the button game.')
                
            try: await message.delete()
            except: pass

        elif message.content.lower() == 'insert_first_click': #insert_first_click from database
            try:
                user_id = message.author.id
                game_session = get_game_session_by_guild_id(message.guild.id)
                username = message.author.display_name if message.author.display_name else message.author.name
                now = 43200
                result = insert_first_click(game_session['game_id'], user_id, username, now)
                if result:
                    logger.info(f'First click inserted for {username}')
                    await message.channel.send(f'First click inserted for {username}')
                else:
                    logger.error('Failed to insert first click.')
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error inserting first click: {e}, {tb}')
        
        elif message.content.lower().startswith(('myrank', 'rank', 'urrank')):
            await message.add_reaction('⌛')
            game_session = get_game_session_by_guild_id(message.guild.id)
            if not game_session:
                await message.channel.send('No active game session found in this server!')
                return

            # Determine target user
            target_user_id = message.author.id
            is_other_user = False
            
            # Check if this is a urrank command or if additional arguments are provided
            command_parts = message.content.lower().split()
            if len(command_parts) > 1:
                # Check for user mention
                if len(message.mentions) > 0:
                    target_user_id = message.mentions[0].id
                    is_other_user = True
                # Handle the existing ID extraction from message content
                elif command_parts[0] != 'urrank' and command_parts[1].startswith('<@') and command_parts[1].endswith('>'):
                    try:
                        target_user_id = int(command_parts[1][2:-1].replace('!', ''))
                        is_other_user = True
                    except ValueError:
                        await message.channel.send('Invalid user mention format!')
                        await message.remove_reaction('⌛', bot.user)
                        return

            try:
                # Get user's clicks for current game session
                query = '''
                    SELECT 
                        bc.timer_value,
                        bc.click_time,
                        (
                            SELECT COUNT(DISTINCT u2.user_id)
                            FROM button_clicks bc2 
                            JOIN users u2 ON bc2.user_id = u2.user_id 
                            WHERE bc2.game_id = %s 
                            AND u2.total_clicks > (
                                SELECT COUNT(*) 
                                FROM button_clicks bc3 
                                WHERE bc3.user_id = %s 
                                AND bc3.game_id = %s
                            )
                        ) + 1 AS user_rank,
                        (
                            SELECT COUNT(DISTINCT user_id) 
                            FROM button_clicks 
                            WHERE game_id = %s
                        ) AS total_players
                    FROM button_clicks bc
                    WHERE bc.game_id = %s 
                    AND bc.user_id = %s
                    ORDER BY bc.click_time
                '''
                params = (game_session['game_id'], target_user_id, game_session['game_id'], 
                         game_session['game_id'], game_session['game_id'], target_user_id)
                success = execute_query(query, params)
                if not success: 
                    logger.error('Error retrieving user rank data')
                    await message.channel.send('An error occurred while retrieving rank data!')
                    await message.remove_reaction('⌛', bot.user)
                    await message.add_reaction('❌')
                    return

                clicks = success

                def Counter(emojis):
                    counts = {}
                    for emoji in emojis:
                        if emoji in counts:
                            counts[emoji] += 1
                        else:
                            counts[emoji] = 1
                    return counts

                if clicks:
                    color_emojis = [get_color_emoji(timer_value, game_session['timer_duration']) for timer_value, _, _, _ in clicks]
                    color_counts = Counter(color_emojis)
                    total_claimed_time = sum(config['timer_duration'] - timer_value for timer_value, _, _, _ in clicks)
                    emoji_sequence = ' '.join(color_emojis)
                    color_summary = ', '.join(f'{emoji} x{count}' for emoji, count in color_counts.items())
                    rank = clicks[0][2]  # Get rank from first row
                    total_players = clicks[0][3]  # Get total players from first row

                    if not is_other_user:
                        user_name = message.author.display_name if message.author.display_name else message.author.name
                        embed = nextcord.Embed(title='Your Heroic Journey')
                        embed.add_field(name='🎑☘ Adventurer', value=user_name, inline=False)
                    else:
                        target_user = await bot.fetch_user(target_user_id)
                        if target_user is None:
                            await message.channel.send('Unable to find that user!')
                            await message.remove_reaction('⌛', bot.user)
                            return
                        user_name = target_user.display_name if hasattr(target_user, 'display_name') else target_user.name
                        embed = nextcord.Embed(title=f'Heroic Journey of {user_name}')
                        embed.add_field(name='🎑☘ Adventurer', value=user_name, inline=False)

                    embed.add_field(name='🎎 Current Rank', value=f'#{rank} out of {total_players} adventurers', inline=False)
                    embed.add_field(name='🎚 Click History', value=emoji_sequence, inline=False)
                    embed.add_field(name='🎨 Color Summary', value=color_summary, inline=False)
                    embed.add_field(name='⏱☘ Total Time Claimed*', value=format_time(total_claimed_time), inline=False)
                    
                    footer_text = "Total time claimed represents the amount of time "
                    footer_text += "you've" if not is_other_user else "they've"
                    footer_text += " prevented the clock from reaching zero."
                    embed.set_footer(text=footer_text)
                    
                    await message.channel.send(embed=embed)
                else:
                    msg = 'Alas, noble warrior, '
                    if not is_other_user:
                        msg += 'your journey has yet to begin. Step forth and make your mark upon the button!'
                    else:
                        msg += 'their journey has yet to begin. They must step forth and make their mark upon the button!'
                    await message.channel.send(msg)

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving user rank: {e}\n{tb}')
                msg = 'An error occurred while retrieving '
                msg += 'your' if not is_other_user else 'the user\'s'
                msg += ' rank. The button spirits are displeased!'
                await message.channel.send(msg)
            finally:
                try:
                    await message.remove_reaction('⌛', bot.user)
                except:
                    pass

        elif message.content.lower() == 'showclicks':
            await message.add_reaction('🔄')
            try:
                game_session = get_game_session_by_guild_id(message.guild.id)
                if not game_session:
                    await message.channel.send('No active game session found in this server!')
                    return

                # Get all clicks for the current game session ordered by click time
                query = '''
                    SELECT timer_value 
                    FROM button_clicks 
                    WHERE game_id = %s 
                    ORDER BY click_time ASC
                '''
                params = (game_session['game_id'],)
                success = execute_query(query, params)
                
                if not success:
                    logger.error('Failed to retrieve click data')
                    await message.channel.send('An error occurred while retrieving click data!')
                    await message.remove_reaction('🔄', bot.user)
                    return

                clicks = success
                if not clicks:
                    await message.channel.send('No clicks found for this game session!')
                    await message.remove_reaction('🔄', bot.user)
                    return

                # Convert timer values to emojis
                click_emojis = [get_color_emoji(click[0], game_session['timer_duration']) for click in clicks]
                
                # Count occurrences of each emoji
                emoji_counts = {
                    '🟣': click_emojis.count('🟣'),  # Purple
                    '🔵': click_emojis.count('🔵'),  # Blue
                    '🟢': click_emojis.count('🟢'),  # Green
                    '🟡': click_emojis.count('🟡'),  # Yellow
                    '🟠': click_emojis.count('🟠'),  # Orange
                    '🔴': click_emojis.count('🔴')   # Red
                }

                # Create rows of 10 emojis
                rows = []
                current_row = []
                for emoji in click_emojis:
                    current_row.append(emoji)
                    if len(current_row) == 10:
                        rows.append(''.join(current_row))
                        current_row = []
                
                # Add any remaining emojis
                if current_row:
                    rows.append(''.join(current_row))

                # Create the embed
                embed = nextcord.Embed(
                    title=f'All Clicks From Game #{game_session["game_id"]}',
                    description='\n'.join(rows)
                )

                # Add color summary
                summary = '\n'.join([f'{emoji}: {count}' for emoji, count in emoji_counts.items() if count > 0])
                embed.add_field(name='Color Summary', value=summary, inline=False)

                # Add total clicks
                embed.add_field(name='Total Clicks', value=str(len(click_emojis)), inline=False)

                try:
                    await message.channel.send(embed=embed)
                except nextcord.errors.HTTPException as e:
                    if e.status == 400:
                        # If the message is too long, send a truncated version
                        logger.warning(f'Message too long, truncating clicks for game {game_session["game_id"]}')
                        truncated_rows = rows[:50]  # Show first 500 clicks (50 rows of 10)
                        embed.description = '\n'.join(truncated_rows) + '\n... [Additional clicks truncated]'
                        await message.channel.send(embed=embed)
                    else:
                        raise e

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error showing clicks: {e}\n{tb}')
                await message.channel.send('An error occurred while showing clicks!')
            finally:
                await message.remove_reaction('🔄', bot.user)

        elif 'leaderboard' in message.content.lower() and len(message.content.split()) <= 2 and message.content.split()[0].lower() == 'leaderboard':
            await message.add_reaction('⏳')
            game_session = get_game_session_by_guild_id(message.guild.id)
            if not game_session:
                await message.channel.send('No active game session found in this server!')
                return

            num_entries = 5
            if len(message.content.split()) > 1:
                try:
                    num_entries = int(message.content.split(" ")[1])
                except ValueError:
                    pass

            try:
                # Most clicks in current game session
                # Update the leaderboard query
                query = '''
                    SELECT 
                        u.user_name,
                        COUNT(*) AS total_clicks,
                        GROUP_CONCAT(
                            CASE
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 83.33 THEN '🟣'
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 66.67 THEN '🔵'
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 50.00 THEN '🟢'
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 33.33 THEN '🟡'
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 16.67 THEN '🟠'
                                ELSE '🔴'
                            END
                            ORDER BY bc.timer_value
                            SEPARATOR ''
                        ) AS color_sequence,
                        SUM(
                            POWER(2, 5 - FLOOR((bc.timer_value / %s) * 100 / 16.66667)) * 
                            (1 + 
                                CASE 
                                    WHEN (bc.timer_value / %s) * 100 < 33.33 
                                    THEN 1 - ((bc.timer_value / %s) * 100 % 16.66667) / 16.66667
                                    ELSE 1 - ABS(0.5 - ((bc.timer_value / %s) * 100 % 16.66667) / 16.66667)
                                END
                            ) * (%s / 43200)
                        ) AS mmr_score
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    WHERE bc.game_id = %s
                    GROUP BY u.user_id
                    ORDER BY mmr_score DESC, total_clicks DESC
                    LIMIT %s
                '''
                params = (
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['game_id'],
                    num_entries
                )
                success = execute_query(query, params)
                most_clicks = success

                # Lowest individual clicks in current game session
                query = '''
                    SELECT u.user_name, bc.timer_value
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    WHERE bc.game_id = %s
                    ORDER BY bc.timer_value
                    LIMIT %s
                '''
                success = execute_query(query, (game_session['game_id'], num_entries))
                lowest_individual_clicks = success

                # Lowest user clicks in current game session
                # Update the Lowest individual clicks query
                query = '''
                    SELECT 
                        u.user_name, 
                        bc.timer_value,
                        CASE
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 83.33 THEN '🟣'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 66.67 THEN '🔵'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 50.00 THEN '🟢'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 33.33 THEN '🟡'
                            WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 16.67 THEN '🟠'
                            ELSE '🔴'
                        END as color_emoji
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    WHERE bc.game_id = %s
                    ORDER BY bc.timer_value
                    LIMIT %s
                '''
                params = (
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['timer_duration'],
                    game_session['game_id'],
                    num_entries
                )
                success = execute_query(query, params)
                lowest_individual_clicks = success

                # Most time claimed in current game session
                query = '''
                    SELECT
                        u.user_name,
                        SUM(
                            CASE 
                                WHEN bc.timer_value <= %s THEN %s - bc.timer_value
                                ELSE 0  -- Safety check for any invalid timer values
                            END
                        ) AS total_time_claimed
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    WHERE bc.game_id = %s
                    GROUP BY u.user_id
                    ORDER BY total_time_claimed DESC
                    LIMIT %s
                '''
                params = (
                    game_session['timer_duration'],  # For the <= check
                    game_session['timer_duration'],  # For the subtraction
                    game_session['game_id'],
                    num_entries
                )
                success = execute_query(query, params)
                most_time_claimed = success
                embed = nextcord.Embed(
                    title='🏆 The Leaderboard Legends of the Button 🏆')

                # Helper function to get display name
                def get_display_name(username):
                    try:
                        # First try to get member object
                        member = message.guild.get_member_named(username)
                        if member:
                            return member.nick or member.display_name or member.name.replace(".", "")
                        return username.replace(".", "")
                    except:
                        return username.replace(".", "")

                top_clicks_value = '\n'.join(
                    f'__{get_display_name(user)}__: {clicks} clicks (MMR: {mmr_score:.1f})\n'
                    f'{" ".join(emoji + "x" + str(seq.count(emoji)) for emoji in ["🟣", "🔵", "🟢", "🟡", "🟠", "🔴"] if emoji in seq)}'
                    for user, clicks, seq, mmr_score in most_clicks
                ) + '\n'
                embed.add_field(name='⚔️ Mightiest Clickers ⚔️', 
                              value='The adventurers who have clicked the button the most times in this game, ranked by MMR.', 
                              inline=False)
                embed.add_field(name='Top Clickers', 
                              value=top_clicks_value if top_clicks_value else 'No data available', 
                              inline=False)

                lowest_individual_clicks_value = '\n'.join(
                    f'{color_emoji} __{get_display_name(user)}__: {format_time(click_time)}'
                    for user, click_time, color_emoji in lowest_individual_clicks
                ) + '\n'

                embed.add_field(name='⚡ Swiftest Clicks ⚡', 
                              value='The adventurers who have clicked the button with the lowest time remaining in this game.', 
                              inline=False)
                embed.add_field(name='Fastest Clicks', 
                              value=lowest_individual_clicks_value if lowest_individual_clicks_value else 'No data available', 
                              inline=False)

                # lowest_user_clicks_value = '\n'.join(
                #     f'{get_color_emoji(click_time)} __{get_display_name(user)}__: {format_time(click_time)}'
                #     for user, click_time in lowest_user_clicks
                # ) + '\n'
                # embed.add_field(name='🎯 Nimblest Warriors 🎯', 
                #               value='The adventurers who have the lowest personal best click time in this game.', 
                #               inline=False)
                # embed.add_field(name='Lowest Personal Best', 
                #               value=lowest_user_clicks_value if lowest_user_clicks_value else 'No data available', 
                #               inline=False)

                most_time_claimed_value = '\n'.join(
                    f'__{get_display_name(username)}__: {format_time(time_claimed)}'
                    for username, time_claimed in most_time_claimed
                ) + '\n'
                embed.add_field(name='⏳ Temporal Titans ⏳', 
                              value='The adventurers who have claimed the most time by resetting the clock in this game.', 
                              inline=False)
                embed.add_field(name='Most Time Claimed', 
                              value=most_time_claimed_value if most_time_claimed_value else 'No data available', 
                              inline=False)

                if lowest_individual_clicks:
                    color = get_color_state(lowest_individual_clicks[0][1], game_session['timer_duration'])
                    embed.color = nextcord.Color.from_rgb(*color)
                else:
                    embed.color = nextcord.Color.from_rgb(106, 76, 147)  # Default color if no data available

                embed.description = f"Gather round, brave adventurers, and marvel at the legends whose names shall be etched in the button's eternal memory for Game #{game_session['game_id']}!"

                await message.channel.send(embed=embed)

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving leaderboard: {e}, {tb}')
                await message.channel.send('An error occurred while retrieving the leaderboard. The button archives are in disarray!')
            finally:
                await message.remove_reaction('⏳', bot.user)

        elif message.content.lower().startswith('clicklist'):
            await message.add_reaction('⌛')
            try:
                # Parse command arguments
                args = message.content.lower().split()
                limit = 25  # Default limit
                is_global = False
                
                # Process arguments
                for arg in args[1:]:
                    if arg.isdigit():
                        limit = min(int(arg), 100)  # Cap at 100 entries
                    elif arg == 'global':
                        is_global = True

                game_session = get_game_session_by_guild_id(message.guild.id)
                if not game_session and not is_global:
                    await message.channel.send('No active game session found in this server!')
                    return

                # Construct the SQL query based on whether it's global or server-specific
                if is_global:
                    query = '''
                        SELECT 
                            bc.timer_value,
                            bc.click_time,
                            u.user_name,
                            gs.guild_id,
                            gs.id as game_session_id
                        FROM button_clicks bc
                        JOIN users u ON bc.user_id = u.user_id
                        JOIN game_sessions gs ON bc.game_id = gs.id
                        ORDER BY bc.timer_value ASC
                        LIMIT %s
                    '''
                    params = (limit,)
                else:
                    query = '''
                        SELECT 
                            bc.timer_value,
                            bc.click_time,
                            u.user_name,
                            gs.guild_id,
                            gs.id as game_session_id
                        FROM button_clicks bc
                        JOIN users u ON bc.user_id = u.user_id
                        JOIN game_sessions gs ON bc.game_id = gs.id
                        WHERE bc.game_id = %s
                        ORDER BY bc.timer_value ASC
                        LIMIT %s
                    '''
                    params = (game_session['game_id'], limit)

                results = execute_query(query, params)
                
                if not results:
                    await message.channel.send('No clicks found!')
                    await message.remove_reaction('⌛', bot.user)
                    return

                # Create embed
                title = f"🎯 The Button - {'Global ' if is_global else ''}Lowest {limit} Clicks"
                embed = nextcord.Embed(title=title)
                
                # Process results in chunks to respect Discord's field length limits
                current_field = ""
                field_count = 1
                
                for timer_value, click_time, user_name, guild_id, game_session_id in results:
                    # Get color emoji based on timer value
                    color_emoji = get_color_emoji(timer_value)
                    
                    # Format the click entry
                    entry = f"{color_emoji} **{user_name}** - {format_time(timer_value)} - "
                    entry += f"<t:{int(click_time.timestamp())}:R>\n"
                    
                    if is_global:
                        guild = bot.get_guild(guild_id)
                        guild_name = guild.name if guild else f"Unknown Server ({guild_id})"
                        entry += f"Server: {guild_name}\n"
                    
                    entry += "\n"  # Add spacing between entries
                    
                    # Check if adding this entry would exceed Discord's field limit
                    if len(current_field) + len(entry) > 1024:
                        embed.add_field(
                            name=f"Clicks (Part {field_count})", 
                            value=current_field, 
                            inline=False
                        )
                        current_field = entry
                        field_count += 1
                    else:
                        current_field += entry

                # Add the last field if there's any content
                if current_field:
                    embed.add_field(
                        name=f"Clicks {f'(Part {field_count})' if field_count > 1 else ''}", 
                        value=current_field, 
                        inline=False
                    )

                await message.channel.send(embed=embed)

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving click list: {e}\n{tb}')
                await message.channel.send('An error occurred while retrieving the click list!')
            finally:
                await message.remove_reaction('⌛', bot.user)

        elif message.content.lower() == 'help':
            embed = nextcord.Embed(title='Help', description='Available Commands')
            embed.add_field(name='myrank', value='Check your personal stats', inline=False)
            embed.add_field(name='leaderboard', value='Check the top 10 clickers', inline=False)
            embed.add_field(name='check', value='Check if you have a click ready', inline=False)
            embed.add_field(name='clicklist [number] [global]', 
                          value='View the lowest click times. Add number (max 100) to see more entries, add global to see all servers.', 
                          inline=False)
            embed.set_footer(text='May your clicks be swift and true, adventurer!')
            color = (106, 76, 147)
            embed.color = nextcord.Color.from_rgb(*color)
            await message.channel.send(embed=embed)

        elif message.content.lower() == 'check':
            await message.add_reaction('⏳')
            user_check_id = message.author.id
            try:
                # Get the game session to access the cooldown duration
                game_session = get_game_session_by_guild_id(message.guild.id)
                if not game_session:
                    await message.channel.send('No active game session found in this server!')
                    await message.remove_reaction('‚è≥', bot.user)
                    return

                cooldown_duration = game_session['cooldown_duration']
                
                query = '''
                    SELECT COUNT(*) AS click_count 
                    FROM button_clicks 
                    WHERE user_id = %s 
                    AND click_time >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s HOUR)
                '''
                params = (user_check_id, cooldown_duration)
                success = execute_query(query, params)
                if not success:
                    logger.error('Failed to retrieve data.')
                    await message.add_reaction('‚ùå')
                    return
                
                result = success[0]
                click_count = result[0]
                if click_count == 0: response = "✅ Ah, my brave adventurer! Your spirit is ready, and the button awaits your valiant click. Go forth and claim your glory!"
                else: response = "❌ Alas, noble warrior, you must rest and gather your strength. The button shall beckon you again when the time is right."

                embed = nextcord.Embed(description=response)
                await message.channel.send(embed=embed)
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error checking user cooldown: {e}, {tb}')
                await message.channel.send('Alas noble warrior, an error occurred while checking your cooldown. The button spirits are in disarray!')
            finally:
                await message.remove_reaction('⏳', bot.user)

        elif message.content.lower() == 'force_update_button':
            if message.author.id != 692926265405079632:
                if not message.author.guild_permissions.administrator:
                    await message.channel.send('You need administrator permissions to use this command.')
                    return
            try:
                game_session = get_game_session_by_guild_id(message.guild.id)
                if not game_session:
                    await message.channel.send('No active game session found in this server!')
                    return
                
                # Clear the button message cache for this game
                button_message_cache.messages.pop(game_session['game_id'], None)
                
                # Create new button message with forced new creation
                new_message = await create_button_message(game_session['game_id'], bot, force_new=True)
                
                if new_message:
                    await message.channel.send('Button message has been reset successfully!', delete_after=5)
                else:
                    await message.channel.send('Failed to reset button message. Please try again.')
                
                try:
                    await message.delete()
                except:
                    pass
                    
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error resetting button message: {e}\n{tb}')
                await message.channel.send('An error occurred while resetting the button message.')

        elif message.content.lower() == 'ended':
            try:
                query = '''
                    SELECT 
                        u.user_name,
                        COUNT(*) AS total_clicks,
                        MIN(bc.timer_value) AS lowest_click_time,
                        GROUP_CONCAT(
                            CASE
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 83.33 THEN '🟣'
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 66.67 THEN '🔵'
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 50.00 THEN '🟢'
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 33.33 THEN '🟡'
                                WHEN ROUND((bc.timer_value / %s) * 100, 2) >= 16.67 THEN '🟠'
                                ELSE '🔴'
                            END
                            ORDER BY bc.timer_value
                            SEPARATOR ''
                        ) AS color_sequence
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    GROUP BY u.user_id
                    ORDER BY lowest_click_time
                '''
                params = (game_session['timer_duration'],) * 5  # For each CASE condition
                success = execute_query(query, params)
                all_users_data = success
                
                embed = nextcord.Embed(
                    title='🎉 The Button Game Has Ended! 🎉',
                    description='Here are the final results of all the brave adventurers who participated in this epic journey!'
                )
                
                max_field_length = 1024
                field_count = 1
                all_users_value = ""
                
                for user, clicks, lowest_time, seq in all_users_data:
                    user_data = f'{user.replace(".", "")}: {clicks} clicks, Lowest: {format_time(lowest_time)} {" ".join(emoji + "x" + str(seq.count(emoji)) for emoji in ["🟣", "🔵", "🟢", "🟡", "🟠", "🔴"] if emoji in seq)}\n'
                    
                    if len(all_users_value) + len(user_data) > max_field_length:
                        embed.add_field(name=f'🏅 Adventurers of the Button (Part {field_count}) 🏅', value=all_users_value, inline=False)
                        all_users_value = ""
                        field_count += 1
                    
                    all_users_value += user_data
                
                if all_users_value: embed.add_field(name=f'🏅 Adventurers of the Button (Part {field_count}) 🏅', value=all_users_value, inline=False)
                
                if not all_users_data: embed.add_field(name='🏅 Adventurers of the Button 🏅', value='No data available', inline=False)
                
                if all_users_data: color = get_color_state(all_users_data[0][2]); embed.color = nextcord.Color.from_rgb(*color)
                else: embed.color = nextcord.Color.from_rgb(106, 76, 147)  # Default color if no data available

                await message.channel.send(embed=embed)
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving end game data: {e}, {tb}')
                await message.channel.send('An error occurred while retrieving the end game data. The button spirits are in turmoil!')

        elif message.content.lower() == 'lore':
            try:
                embed = nextcord.Embed(title="📜 __The Lore of The Button__ 📜", description=LORE_TEXT)
                embed.set_footer(text="⚡ *May your clicks be swift and true, adventurer!* ⚡")
                await message.channel.send(embed=embed)
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving lore: {e}, {tb}')
                await message.channel.send('❌ **An error occurred while retrieving the lore.** *The ancient archives seem to be temporarily sealed!* ❌')

        elif message.content.lower() == 'add_new_game':
            try:
                query = 'SELECT * FROM game_sessions'
                success = execute_query(query)
                game_sessions = success
                if game_sessions:
                    for game_session in game_sessions:
                        game_id = game_session[0]
                        game_channel_id = game_session[1]
                        chat_channel_id = game_session[2]
                        start_time = game_session[3]
                        timer_duration = game_session[4]
                        cooldown_duration = game_session[5]
                        admin_role_id = game_session[6]
                        guild_id = game_session[7]
                        paused_games.append(game_id)
                        create_game_session(admin_role_id, guild_id, game_channel_id, chat_channel_id, start_time, timer_duration, cooldown_duration)
                        logger.info(f'Game session {game_id} added to paused games.')
                    await message.channel.send('Game sessions added to paused games.')
                else:
                    await message.channel.send('No game sessions found.')
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error adding game sessions: {e}, {tb}')
                await message.channel.send('An error occurred while adding game sessions.')
    
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f'Error processing message: {e}, {tb}')

async def start_boot_game(bot, button_guild_id, message_button_channel, menu_timer):
    global paused_games, lock, logger
    game_session = get_game_session_by_guild_id(button_guild_id)
    guild = bot.get_guild(button_guild_id)
    if game_session:
        await create_button_message(game_session['game_id'], bot)
        logger.info(f"Button game already started in {button_guild_id}")
    else:
        logger.info(f"Starting button game in {button_guild_id}")
        start_time = datetime.datetime.now(timezone.utc)
        timer_duration = config['timer_duration']
        cooldown_duration = config['cooldown_duration']
        chat_channel_id = message_button_channel
        
        admin_role_id = 0
        try:
            admin_role = nextcord.utils.get(guild.roles, name='Button Master')
            if not admin_role: admin_role = await guild.create_role(name='Button Master')
            admin_role_id = admin_role.id
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f'Error adding role: {e}, {tb}')
            logger.info('Skipping role addition...')
            pass
            
        game_id = create_game_session(admin_role_id, guild.id, message_button_channel, chat_channel_id, start_time, timer_duration, cooldown_duration)
        
        game_session = get_game_session_by_id(game_id)
        game_sessions_as_dict = game_sessions_dict()
        if game_sessions_as_dict:
            game_sessions_as_dict[game_id] = game_session
        else:
            game_sessions_as_dict = {game_id: game_session}

        update_local_game_sessions()
        
        if game_id in paused_games: 
            try:
                paused_games.remove(game_id)
                logger.info(f'Game session {game_id} removed from paused games.')
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error removing game session from paused games: {e}, {tb}')
                pass
        
        await setup_roles(guild.id, bot)
        update_local_game_sessions()
        await create_button_message(game_id, bot)
        
    if menu_timer and not menu_timer.update_timer_task.is_running():
        logger.info('Starting update timer task...')
        menu_timer.update_timer_task.start()

def calculate_mmr(timer_value, timer_duration):
    """
    Calculate MMR for a click based on:
    1. Color bracket (16.66% intervals)
    2. Precise timing within bracket
    3. Scaled against timer_duration
    
    Args:
        timer_value (int): Time remaining when button was clicked
        timer_duration (int): Total duration of timer (cooldown)
    
    Returns:
        float: Calculated MMR value
    """
    percentage = (timer_value / timer_duration) * 100
    bracket_size = 16.66667  # Each color represents 16.66667% of the timer
    
    # Determine which bracket (0-5, where 0 is red and 5 is purple)
    bracket = min(5, int(percentage / bracket_size))
    
    # Calculate position within bracket (0.0 to 1.0)
    bracket_position = (percentage % bracket_size) / bracket_size
    
    # Base points exponentially increase as brackets get rarer
    # Red (0) = 32, Orange (1) = 16, Yellow (2) = 8, Green (3) = 4, Blue (4) = 2, Purple (5) = 1
    base_points = 2 ** (5 - bracket)
    
    # Position multiplier: rewards riskier timing within each bracket
    # For red/orange (rarest), rewards getting closer to zero
    # For other colors, rewards consistency in hitting the bracket
    if bracket <= 1:  # Red or Orange
        position_multiplier = 1 - bracket_position
    else:
        position_multiplier = 1 - abs(0.5 - bracket_position)
    
    # Scale final score by timer_duration to account for game difficulty
    time_scale = timer_duration / 43200  # Normalize to 12-hour standard
    
    mmr = base_points * (1 + position_multiplier) * time_scale
    
    return mmr