from PIL import Image, ImageSequence
from io import BytesIO
from typing import List, Tuple, Optional
import asyncio
from pathlib import Path
import logging
import os
import nextcord

# Change relative imports to absolute imports
from config.sprite_config import PET_SPRITE_URLS
from config.pet_sprites import PET_SPRITES, DEFAULT_SPRITES

logger = logging.getLogger('tomibotchi')
current_directory = Path(__file__).parent.parent
sprites_directory = current_directory / ".." / "assets"
sprites_directory = os.path.join(sprites_directory, "sprites")

class SpriteHandler:
    def __init__(self):
        self.sprite_urls = PET_SPRITES
        self.default_urls = DEFAULT_SPRITES

    async def get_sprite_url(self, 
                           species: str, 
                           state: str, 
                           emotion: str = "neutral") -> str:
        """Get the CDN URL for the specified species, state and emotion."""
        try:
            species = species.lower()
            
            if hasattr(state, 'value'):
                state = state.value
                
            if hasattr(emotion, 'value'):
                emotion = emotion.value

            # Try to get the specific state/emotion combination
            return self.sprite_urls[species][state][emotion]
        except KeyError:
            try:
                # Try to get default emotion for this state
                return self.sprite_urls[species][state]["neutral"]
            except KeyError:
                # Fall back to species default
                logger.warning(f"No sprite found for {species} in {state} state with {emotion} emotion")
                return self.default_urls.get(species)

    def _load_sprite_sheet(self, species: str) -> Image.Image:
        """Load sprite sheet from file."""
        if species not in self.sprite_cache:
            try:
                sprite_path = self.sprite_dir / f"{species}.png"
                sprite_sheet = Image.open(sprite_path)
                self.sprite_cache[species] = sprite_sheet
                logger.info(f"Loaded sprite sheet for {species}")
            except FileNotFoundError:
                logger.error(f"Sprite sheet not found for {species}")
                raise
        return self.sprite_cache[species]

    def _get_sprite_coordinates(self, state: str, emotion: str) -> tuple:
        """Get coordinates for specific sprite state and emotion."""
        # Convert enum to string if needed
        if hasattr(state, 'value'):
            state = state.value.lower()
        else:
            state = state.lower()
            
        if hasattr(emotion, 'value'):
            emotion = emotion.value.lower()
        else:
            emotion = emotion.lower()
    
        states = ['idle', 'sleeping', 'eating', 'playing', 'sick', 'normal']
        emotions = ['neutral', 'happy', 'sad']
        
        try:
            state_idx = states.index(state)
            emotion_idx = emotions.index(emotion)
        except ValueError:
            logger.warning(f"Invalid state or emotion: {state}, {emotion}. Using default.")
            return (0, 0)  # Default to idle_neutral
            
        x = emotion_idx * self.frame_size[0]
        y = state_idx * self.frame_size[1]
        return (x, y)

    async def get_sprite(self, species: str, state: str = 'idle', emotion: str = 'neutral') -> nextcord.File:
        """
        Get sprite for specific species, state, and emotion.
        Returns a nextcord.File object containing the sprite.
        """
        try:
            sprite_sheet = self._load_sprite_sheet(species)
            x, y = self._get_sprite_coordinates(state, emotion)
            
            # Extract the specific sprite from the sheet
            sprite = sprite_sheet.crop((
                x, y,
                x + self.frame_size[0],
                y + self.frame_size[1]
            ))
            
            # Convert to bytes for nextcord.File
            buffer = BytesIO()
            sprite.save(buffer, format='PNG')
            buffer.seek(0)
            
            filename = f"{species}_{state}_{emotion}.png"
            return nextcord.File(buffer, filename=filename)
            
        except Exception as e:
            logger.error(f"Error getting sprite: {e}")
            raise

    def cleanup(self):
        """Close all cached images."""
        for sprite_sheet in self.sprite_cache.values():
            sprite_sheet.close()
        self.sprite_cache.clear()

    def _extract_frames(self, 
                       sprite_sheet: Image.Image, 
                       state: str) -> List[Image.Image]:
        """Extract appropriate frames based on pet state."""
        frame_indices = {
            'normal': [0, 1],    # First two frames
            'happy': [2, 3],     # Next two frames
            'sleeping': [4],     # Single sleeping frame
            'sick': [5]          # Single sick frame
        }[state.lower()]

        frames = []
        for i in frame_indices:
            left = i * self.frame_size[0]
            frame = sprite_sheet.crop(
                (left, 0, left + self.frame_size[0], self.frame_size[1])
            )
            frames.append(frame)

        return frames

    async def create_pet_gif(self, 
                           species: str, 
                           state: str,
                           duration: int = 500) -> BytesIO:
        """Create animated gif for pet state."""
        try:
            sprite_sheet = self._load_sprite_sheet(species)
            frames = self._extract_frames(sprite_sheet, state)

            # Create output buffer
            output = BytesIO()

            # Save animated gif
            frames[0].save(
                output,
                format='GIF',
                append_images=frames[1:],
                save_all=True,
                duration=duration,
                loop=0,
                transparency=0,
                disposal=2
            )

            output.seek(0)
            return output

        except Exception as e:
            logger.error(f"Error creating pet gif: {e}")

            raise