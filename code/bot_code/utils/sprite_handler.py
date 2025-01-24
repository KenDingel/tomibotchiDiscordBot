# Create new file: utils/sprite_handler.py

from PIL import Image, ImageSequence
import io
from typing import List, Tuple
import asyncio
from pathlib import Path
import logging

logger = logging.getLogger('tomibotchi')

class SpriteHandler:
    def __init__(self, sprite_dir: str = "assets/sprites"):
        self.sprite_dir = Path(sprite_dir)
        self.frame_size = (200, 200)
        self.frames_per_sprite = 6
        self.sprite_cache = {}

    def _load_sprite_sheet(self, species: str) -> Image.Image:
        """Load sprite sheet from file."""
        if species not in self.sprite_cache:
            path = self.sprite_dir / f"{species}.png"
            self.sprite_cache[species] = Image.open(path)
        return self.sprite_cache[species]

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
                           duration: int = 500) -> io.BytesIO:
        """Create animated gif for pet state."""
        try:
            sprite_sheet = self._load_sprite_sheet(species)
            frames = self._extract_frames(sprite_sheet, state)

            # Create output buffer
            output = io.BytesIO()

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