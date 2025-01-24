from typing import Dict, List, Tuple
import datetime

def get_color_distribution(clicks: List[Tuple[int, int]], timer_duration: int) -> Dict[str, int]:
    """
    Calculate distribution of colors for all clicks
    
    Args:
        clicks: List of (timer_value, timestamp) tuples
        timer_duration: Total duration of timer
        
    Returns:
        Dict mapping color emoji to count
    """
    colors = {
        '🟣': 0, '🔵': 0, '🟢': 0, 
        '🟡': 0, '🟠': 0, '🔴': 0
    }
    
    for timer_value, _ in clicks:
        percentage = (timer_value / timer_duration) * 100
        if percentage >= 83.33:
            colors['🟣'] += 1
        elif percentage >= 66.67:
            colors['🔵'] += 1
        elif percentage >= 50:
            colors['🟢'] += 1
        elif percentage >= 33.33:
            colors['🟡'] += 1
        elif percentage >= 16.67:
            colors['🟠'] += 1
        else:
            colors['🔴'] += 1
            
    return colors

def get_hourly_activity(clicks: List[Tuple[int, int]]) -> Dict[int, int]:
    """
    Calculate click distribution by hour
    
    Args:
        clicks: List of (timer_value, timestamp) tuples
        
    Returns:
        Dict mapping hour (0-23) to click count
    """
    hours = {i: 0 for i in range(24)}
    
    for _, timestamp in clicks:
        hour = datetime.datetime.fromtimestamp(timestamp).hour
        hours[hour] += 1
        
    return hours

def get_mmr_over_time(clicks: List[Tuple[int, int, int, str]], timer_duration: int) -> List[Dict]:
    """
    Calculate cumulative MMR progression
    
    Args:
        clicks: List of (timer_value, timestamp, user_id, username) tuples
        timer_duration: Total duration of timer
        
    Returns:
        List of dicts with timestamp and MMR values per user
    """
    user_mmr = {}
    progression = []
    
    for timer_value, timestamp, user_id, username in sorted(clicks, key=lambda x: x[1]):
        # Calculate MMR for this click using same formula as leaderboard
        percentage = (timer_value / timer_duration) * 100
        bracket = min(5, int(percentage / 16.66667))
        bracket_position = (percentage % 16.66667) / 16.66667
        
        base_points = 2 ** (5 - bracket)
        
        if bracket <= 1:
            position_multiplier = 1 - bracket_position
        else:
            position_multiplier = 1 - abs(0.5 - bracket_position)
            
        mmr = base_points * (1 + position_multiplier) * (timer_duration / 43200)
        
        if user_id not in user_mmr:
            user_mmr[user_id] = {'mmr': 0, 'username': username}
            
        user_mmr[user_id]['mmr'] += mmr
        
        progression.append({
            'timestamp': timestamp,
            'username': username,
            'mmr': user_mmr[user_id]['mmr']
        })
        
    return progression