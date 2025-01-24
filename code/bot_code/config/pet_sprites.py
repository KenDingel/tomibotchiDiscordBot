from typing import Dict
from game.state import PetStatus

# Mapping of species -> state -> emotion -> URL
PET_SPRITES: Dict[str, Dict[str, Dict[str, str]]] = {
    "cat": {
        PetStatus.NORMAL.value: {
            "happy": "https://i.imgur.com/ZdCkGIO.gif",
            "neutral": "https://i.imgur.com/ZdCkGIO.gif",
            "sad": "https://i.imgur.com/ZdCkGIO.gif"
        },
        PetStatus.SLEEPING.value: {
            "neutral": "https://i.imgur.com/ZdCkGIO.gif"
        },
        PetStatus.SICK.value: {
            "neutral": "https://i.imgur.com/ZdCkGIO.gif"
        },
        PetStatus.UNHAPPY.value: {
            "neutral": "https://i.imgur.com/ZdCkGIO.gif"
        }
    }
    # Add more species as needed
}

# Default fallback URLs if state/emotion combination not found
DEFAULT_SPRITES = {
    "cat": "https://your-cdn/cat/normal_neutral.gif",
    # Add more species defaults as needed
}