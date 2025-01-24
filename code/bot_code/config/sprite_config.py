from typing import Dict
from game.state import PetStatus

# Mapping of species -> state -> URL
PET_SPRITE_URLS: Dict[str, Dict[str, str]] = {
    "cat": {
        PetStatus.NORMAL.value: "https://your-cdn.com/cat/normal.gif",
        PetStatus.SLEEPING.value: "https://your-cdn.com/cat/sleeping.gif",
        PetStatus.SICK.value: "https://your-cdn.com/cat/sick.gif",
        PetStatus.UNHAPPY.value: "https://your-cdn.com/cat/unhappy.gif",
    },
    "dog": {
        PetStatus.NORMAL.value: "https://your-cdn.com/dog/normal.gif",
        PetStatus.SLEEPING.value: "https://your-cdn.com/dog/sleeping.gif",
        PetStatus.SICK.value: "https://your-cdn.com/dog/sick.gif",
        PetStatus.UNHAPPY.value: "https://your-cdn.com/dog/unhappy.gif",
    }
}