# Utils.py
import traceback
import datetime
import logging
import json
import asyncio
import os

from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from nextcord import File, ButtonStyle
from threading import Lock

# Global lock to be imported by other modules
lock = Lock()

# Set up logging, as 'logger' to be imported by other modules
# Save logs to a file with the current date in the name
os.chdir(os.path.dirname(os.path.abspath(__file__)))
log_file_name = os.path.join('..', '..', '..', 'logs', f'tomibotchi-{datetime.datetime.now().strftime("%Y-%m-%d")}.log')
log_file_name = os.path.abspath(log_file_name)
logging.basicConfig(filename=log_file_name, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'config.json')
    print(f"Loading config from: {config_path}")  # Enhanced debug message
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            print(f"Config loaded successfully: {list(config.keys())}")  # Debug loaded config
            return config
    except FileNotFoundError:
        logger.error(f"Config file not found at {config_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error loading config: {e}")
        raise

# Load the config file and set the paused games list as a global variables 
config = get_config()
paused_games = []

# Constants
COLOR_STATES = [
    (194, 65, 65),    # Red
    (219, 124, 48),   # Orange
    (203, 166, 53),   # Yellow
    (80, 155, 105),   # Green
    (64, 105, 192),   # Blue
    (106, 76, 147)    # Purple
]

def get_color_state(timer_value, timer_duration=43200):
    """
    Get the color state based on the remaining time, with precise decimal handling.
    """
    timer_value = max(0, min(float(timer_value), float(timer_duration)))
    timer_duration = max(1, float(timer_duration))
    
    # Use ROUND to match SQL precision
    percentage = round((timer_value / timer_duration) * 100, 2)
    
    logger.debug(f"Color calculation: timer_value={timer_value}, duration={timer_duration}, percentage={percentage}")
    
    if percentage >= 83.33:
        return COLOR_STATES[5]  # Purple
    elif percentage >= 66.67:
        return COLOR_STATES[4]  # Blue
    elif percentage >= 50.00:
        return COLOR_STATES[3]  # Green
    elif percentage >= 33.33:
        return COLOR_STATES[2]  # Yellow
    elif percentage >= 16.67:
        return COLOR_STATES[1]  # Orange
    else:
        return COLOR_STATES[0]  # Red

def get_color_emoji(timer_value, timer_duration=43200):
    """
    Get the color emoji based on the remaining time, with precise decimal handling.
    """
    timer_value = max(0, min(float(timer_value), float(timer_duration)))
    timer_duration = max(1, float(timer_duration))
    
    # Use ROUND to match SQL precision
    percentage = round((timer_value / timer_duration) * 100, 2)
    
    if percentage >= 83.33:
        return '🟣'  # Purple
    elif percentage >= 66.67:
        return '🔵'  # Blue
    elif percentage >= 50.00:
        return '🟢'  # Green
    elif percentage >= 33.33:
        return '🟡'  # Yellow
    elif percentage >= 16.67:
        return '🟠'  # Orange
    else:
        return '🔴'  # Red

def get_color_name(timer_value, timer_duration=43200):
    """
    Get the color name based on the remaining time, scaled to the timer duration.
    """
    timer_value = max(0, min(timer_value, timer_duration))
    timer_duration = max(1, timer_duration)
    
    percentage = (timer_value / timer_duration) * 100
    
    if percentage >= 83.33:
        return 'Purple'
    elif percentage >= 66.67:
        return 'Blue'
    elif percentage >= 50:
        return 'Green'
    elif percentage >= 33.33:
        return 'Yellow'
    elif percentage >= 16.67:
        return 'Orange'
    else:
        return 'Red'

def get_button_style(color):
    style = ButtonStyle.gray
    if color == COLOR_STATES[0]: style = ButtonStyle.danger
    elif color == COLOR_STATES[1]: style = ButtonStyle.secondary
    elif color == COLOR_STATES[2]: style = ButtonStyle.secondary
    elif color == COLOR_STATES[3]: style = ButtonStyle.success
    elif color == COLOR_STATES[4]: style = ButtonStyle.primary
    elif color == COLOR_STATES[5]: style = ButtonStyle.primary
    return style

def format_time(timer_value):
    timer_value = int(timer_value)
    time = str(datetime.timedelta(seconds=timer_value))
    return time

# Generate an image of the timer with text, color, and time left.
# Utilizes templates for each color state.
# Uses Pillow for image manipulation.
def generate_timer_image(timer_value, timer_duration=43200):
    try:
        # Prepare the image data and template
        color = get_color_state(timer_value, timer_duration)
        image_number = 6 - (COLOR_STATES.index(color))
        image_path = f"..\\..\\assets\\TheButtonTemplate{image_number:02d}.png"
        image = Image.open(image_path)
        
        # Draw the timer text on the image
        draw = ImageDraw.Draw(image)
        font_size = int(120 * 0.32)
        font = ImageFont.truetype('..\\..\\assets\\Mercy Christole.ttf', font_size)
        text = f"{format(int(timer_value//3600), '02d')}:{format(int(timer_value%3600//60), '02d')}:{format(int(timer_value%60), '02d')}"
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        position = ((image.width - text_width) // 2, (image.height - text_height) // 2 + 35)
        draw.text(position, text, font=font, fill=(0, 0, 0), stroke_width=6, stroke_fill=(255, 255, 255))

        # Add the "Time Left" text
        additional_text = "Time Left".upper()
        additional_font_size = int(100 * 0.32) 
        additional_font = ImageFont.truetype('..\\..\\assets\\Mercy Christole.ttf', additional_font_size)
        additional_text_bbox = draw.textbbox((0, 0), additional_text, font=additional_font)
        additional_text_width = additional_text_bbox[2] - additional_text_bbox[0]
        additional_text_height = additional_text_bbox[3] - additional_text_bbox[1]
        additional_position = ((image.width - additional_text_width) // 2, 70, ((image.height - additional_text_height) // 2) + 50)
        draw.text(additional_position, additional_text, font=additional_font, fill=(0, 0, 0), stroke_width=6, stroke_fill=(255, 255, 255))

        # Save the image to an in-memory buffer
        buffer = BytesIO()
        image.save(buffer, 'PNG')
        buffer.seek(0)

        # Create a Discord File object from the buffer
        file = File(buffer, filename='timer.png')
        return file
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f'Error generating timer image: {e}, {tb}')

        return None