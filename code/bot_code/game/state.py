from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any, Tuple
import logging
from dataclasses import dataclass
from enum import Enum
import traceback
from contextlib import asynccontextmanager

from database.database import get_pet_stats, update_pet_stats

# Configure logging
logger = logging.getLogger(__name__)

# Change the Enum class name from PetState to PetStatus
class PetStatus(Enum):
    NORMAL = "normal"
    SLEEPING = "sleeping"
    SICK = "sick"
    UNHAPPY = "unhappy"

class InteractionType(Enum):
    FEED = "feed"
    CLEAN = "clean"
    SLEEP = "sleep"
    WAKE = "wake"
    PLAY = "play"
    PET = "pet"
    EXERCISE = "exercise"
    TREAT = "treat"
    MEDICINE = "medicine"

@dataclass
class InteractionEffect:
    """Defines the effects and requirements of a pet interaction."""
    happiness: int
    hunger: int
    energy: int
    hygiene: int
    cooldown: timedelta
    conditions: Dict[str, Any]

# Define interaction effects and requirements
INTERACTION_EFFECTS = {
    InteractionType.FEED: InteractionEffect(
        happiness=5, hunger=30, energy=0, hygiene=-5,
        cooldown=timedelta(hours=1),
        conditions={"max_hunger": 90, "not_sleeping": True}
    ),
    InteractionType.CLEAN: InteractionEffect(
        happiness=5, hunger=0, energy=-5, hygiene=40,
        cooldown=timedelta(hours=2),
        conditions={"not_sleeping": True}
    ),
    InteractionType.SLEEP: InteractionEffect(
        happiness=0, hunger=-5, energy=20, hygiene=0,
        cooldown=timedelta(hours=4),
        conditions={"not_sleeping": True, "max_energy": 80}
    ),
    InteractionType.WAKE: InteractionEffect(
        happiness=0, hunger=0, energy=0, hygiene=0,
        cooldown=timedelta(minutes=30),
        conditions={"is_sleeping": True, "min_energy": 50}
    ),
    InteractionType.PLAY: InteractionEffect(
        happiness=15, hunger=-10, energy=-15, hygiene=-10,
        cooldown=timedelta(hours=1),
        conditions={"not_sleeping": True, "min_energy": 30}
    ),
    InteractionType.PET: InteractionEffect(
        happiness=10, hunger=0, energy=0, hygiene=0,
        cooldown=timedelta(minutes=30),
        conditions={}  # Can pet anytime
    ),
    InteractionType.EXERCISE: InteractionEffect(
        happiness=10, hunger=-15, energy=-20, hygiene=-15,
        cooldown=timedelta(hours=2),
        conditions={"not_sleeping": True, "min_energy": 40}
    ),
    InteractionType.TREAT: InteractionEffect(
        happiness=20, hunger=10, energy=5, hygiene=-5,
        cooldown=timedelta(hours=3),
        conditions={"max_treats_per_day": 3, "not_sleeping": True}
    ),
    InteractionType.MEDICINE: InteractionEffect(
        happiness=-5, hunger=0, energy=-10, hygiene=20,
        cooldown=timedelta(hours=6),
        conditions={"is_sick": True}
    )
}

class AtomicCounter:
    """Thread-safe counter for tracking atomic operations."""
    def __init__(self):
        self._value = 0
        self._lock = asyncio.Lock()
    
    async def increment(self) -> int:
        async with self._lock:
            self._value += 1
            return self._value
    
    async def get_value(self) -> int:
        async with self._lock:
            return self._value
            
class PetState:
    def __init__(self, pet_id: int, name: str, species: str, stats: Dict[str, int]):
        """Initialize pet state."""
        self.pet_id = pet_id
        self.name = name
        self.species = species
        self.stats = stats
        self._state = PetStatus.NORMAL  # Update to use PetStatus enum
        self._lock = asyncio.Lock()
        self.last_update = datetime.now(timezone.utc)
        self.interaction_history = {}
    @property
    def state(self) -> PetStatus:
        """Get current pet state."""
        return self._state
    async def set_state(self, new_state: PetStatus) -> None:
        """Thread-safe setter for pet state."""
        async with self._lock:
            self._state = new_state
    async def update(self) -> None:
        """Update pet stats based on time elapsed."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            time_elapsed = (now - self.last_update).total_seconds()
            
            # Update stats based on time elapsed (every hour)
            hours_elapsed = time_elapsed / 3600
            if hours_elapsed >= 1:
                # Decrease stats over time
                self.stats['hunger'] = max(0, self.stats['hunger'] - int(5 * hours_elapsed))
                self.stats['energy'] = max(0, self.stats['energy'] - int(3 * hours_elapsed))
                self.stats['hygiene'] = max(0, self.stats['hygiene'] - int(4 * hours_elapsed))
                self.stats['happiness'] = max(0, self.stats['happiness'] - int(2 * hours_elapsed))
                
                # Update state based on stats
                if self.stats['hygiene'] < 30:
                    await self.set_state(PetStatus.SICK)
                elif self.stats['happiness'] < 30:
                    await self.set_state(PetStatus.UNHAPPY)
                else:
                    await self.set_state(PetStatus.NORMAL)
                
                self.last_update = now
class PetStateManager:
    """Manages pet states and handles stat calculations."""
    def __init__(self):
        self._pet_states = {}
        self._lock = asyncio.Lock()
        self._operation_counter = AtomicCounter()
        
    async def get_pet_state(self, pet_id: int) -> Optional[PetState]:
        """Get or create a pet state for the given pet ID."""
        try:
            async with self._lock:
                if pet_id not in self._pet_states:
                    # Load pet data from database
                    pet_data = get_pet_stats(pet_id)
                    if not pet_data:
                        logger.error(f"Failed to load stats for pet {pet_id}")
                        return None
                    
                    # Create new pet state
                    self._pet_states[pet_id] = PetState(
                        pet_id=pet_id,
                        name=pet_data['name'],
                        species=pet_data['species'],
                        stats=pet_data['stats']
                    )
                
                return self._pet_states[pet_id]
                
        except Exception as e:
            logger.error(f"Error getting pet state: {e}")
            logger.error(traceback.format_exc())
            return None
        if pet_id not in self.states:
            # Load initial stats from database or use defaults
            initial_stats = await self.load_pet_stats(pet_id)
            self.states[pet_id] = PetState(pet_id, initial_stats)
        return self.states[pet_id]
        
    async def load_pet_stats(self, pet_id: int):
        """Load pet stats from database"""
        # Implement database loading logic here
        # For now, return default stats
        return {
            'hunger': 100,
            'happiness': 100,
            'energy': 100,
            'hygiene': 100
        }

@dataclass
class InteractionEffect:
    """Defines the effects and requirements of a pet interaction."""
    happiness: int
    hunger: int
    energy: int
    hygiene: int
    cooldown: timedelta
    conditions: Dict[str, Any]
    """Thread-safe counter for tracking atomic operations."""
    def __init__(self):
        self._value = 0
        self._lock = asyncio.Lock()
    
    async def increment(self) -> int:
        async with self._lock:
            self._value += 1
            return self._value
    
    async def get_value(self) -> int:
        async with self._lock:
            return self._value
        class PetStateManager:
            """Manages individual pet state and handles stat calculations."""
            def __init__(self, pet_id: int, initial_stats: Dict[str, Any]):
                """
                Initialize pet state manager.
                
                Args:
                    pet_id: Unique identifier for the pet
                    initial_stats: Dictionary containing pet's initial stats
                """
                self.pet_id = pet_id
                self.name = initial_stats['name']
                self.species = initial_stats['species']
                self.stats = initial_stats['stats'].copy()
                self._state = PetState.NORMAL  # Private state variable
                self._state_lock = asyncio.Lock()  # Lock for state transitions
                self._stats_lock = asyncio.Lock()  # Lock for stats modifications
                self.last_update = initial_stats['last_update']
                self.interaction_history: Dict[InteractionType, datetime] = {}
                self.treat_count = 0
                self.last_treat_reset = datetime.now(timezone.utc)
                self._operation_counter = AtomicCounter()
                self._pending_changes: Dict[int, Dict[str, Any]] = {}
                self._last_verified_state: Optional[Dict[str, Any]] = None
                self._last_persistence_time = datetime.now(timezone.utc)
                self._lock = asyncio.Lock()  # Add lock attribute
                def __init__(self, pet_id: int, initial_stats: Dict[str, Any]):
                    """
                    Initialize pet state manager.
                    
                    Args:
                        pet_id: Unique identifier for the pet
                        initial_stats: Dictionary containing pet's initial stats
                    """
                    self.pet_id = pet_id
                    self.name = initial_stats['name']
                    self.species = initial_stats['species']
                    self.stats = initial_stats['stats'].copy()
                    self._state = PetState.NORMAL  # Private state variable
                    self._state_lock = asyncio.Lock()  # Lock for state transitions
                    self._stats_lock = asyncio.Lock()  # Lock for stats modifications
                    self.last_update = initial_stats['last_update']
                    self.interaction_history: Dict[InteractionType, datetime] = {}
                    self.treat_count = 0
                    self.last_treat_reset = datetime.now(timezone.utc)
                    self._operation_counter = AtomicCounter()
                    self._pending_changes: Dict[int, Dict[str, Any]] = {}
                    self._last_verified_state: Optional[Dict[str, Any]] = None
                    self._last_persistence_time = datetime.now(timezone.utc)
                    self._lock = asyncio.Lock()  # Add lock attribute
                    class PetStateManager:
                        """Initialize the pet state manager."""
                        self._pet_states = {}
                        self._lock = asyncio.Lock()
                    
                    async def get_pet_state(self, pet_id: int) -> Optional[PetState]:
                        """Get or create a pet state for the given pet ID."""
                        try:
                            async with self._lock:
                                if pet_id not in self._pet_states:
                                    # Load pet data from database
                                    pet_data = get_pet_stats(pet_id)
                                    if not pet_data:
                                        logger.error(f"Failed to load stats for pet {pet_id}")
                                        return None
                                    
                                    # Create new pet state
                                    self._pet_states[pet_id] = PetState(
                                        pet_id=pet_id,
                                        name=pet_data['name'],
                                        species=pet_data['species'],
                                        stats=pet_data['stats']
                                    )
                                
                                return self._pet_states[pet_id]
                                
                        except Exception as e:
                            logger.error(f"Error getting pet state: {e}")
                            logger.error(traceback.format_exc())
class PetState:
    def __init__(self, pet_id: int, name: str, species: str, stats: Dict[str, int]):
        """Initialize pet state."""
        self.pet_id = pet_id
        self.name = name
        self.species = species
        self.stats = stats
        self._state = PetStatus.NORMAL  # Update to use PetStatus enum
        self._lock = asyncio.Lock()
        self.last_update = datetime.now(timezone.utc)
        self.interaction_history = {}
    @property
    def state(self) -> PetStatus:
        """Get current pet state."""
        return self._state
    async def set_state(self, new_state: PetStatus) -> None:
        """Thread-safe setter for pet state."""
        async with self._lock:
            self._state = new_state
    async def update(self) -> None:
        """Update pet stats based on time elapsed."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            time_elapsed = (now - self.last_update).total_seconds()
            
            # Update stats based on time elapsed (every hour)
            hours_elapsed = time_elapsed / 3600
            if hours_elapsed >= 1:
                # Decrease stats over time
                self.stats['hunger'] = max(0, self.stats['hunger'] - int(5 * hours_elapsed))
                self.stats['energy'] = max(0, self.stats['energy'] - int(3 * hours_elapsed))
                self.stats['hygiene'] = max(0, self.stats['hygiene'] - int(4 * hours_elapsed))
                self.stats['happiness'] = max(0, self.stats['happiness'] - int(2 * hours_elapsed))
                
                # Update state based on stats
                if self.stats['hygiene'] < 30:
                    await self.set_state(PetStatus.SICK)
                elif self.stats['happiness'] < 30:
                    await self.set_state(PetStatus.UNHAPPY)
                else:
                    await self.set_state(PetStatus.NORMAL)
                
                self.last_update = now
class PetStateManager:
    """Manages pet states and handles stat calculations."""
    def __init__(self):
        self._pet_states = {}
        self._lock = asyncio.Lock()
        self._operation_counter = AtomicCounter()
        
    async def get_pet_state(self, pet_id: int) -> Optional[PetState]:
        """Get or create a pet state for the given pet ID."""
        try:
            async with self._lock:
                if pet_id not in self._pet_states:
                    # Load pet data from database
                    pet_data = get_pet_stats(pet_id)
                    if not pet_data:
                        logger.error(f"Failed to load stats for pet {pet_id}")
                        return None
                    
                    # Create new pet state
                    self._pet_states[pet_id] = PetState(
                        pet_id=pet_id,
                        name=pet_data['name'],
                        species=pet_data['species'],
                        stats=pet_data['stats']
                    )
                
                return self._pet_states[pet_id]
                
        except Exception as e:
            logger.error(f"Error getting pet state: {e}")
            logger.error(traceback.format_exc())
            return None
        if pet_id not in self.states:
            # Load initial stats from database or use defaults
            initial_stats = await self.load_pet_stats(pet_id)
            self.states[pet_id] = PetState(pet_id, initial_stats)
        return self.states[pet_id]
        
    async def load_pet_stats(self, pet_id: int):
        """Load pet stats from database"""
        # Implement database loading logic here
        # For now, return default stats
        return {
            'hunger': 100,
            'happiness': 100,
            'energy': 100,
            'hygiene': 100
        }

@dataclass
class InteractionEffect:
    """Defines the effects and requirements of a pet interaction."""
    happiness: int
    hunger: int
    energy: int
    hygiene: int
    cooldown: timedelta
    conditions: Dict[str, Any]
    """Thread-safe counter for tracking atomic operations."""
    def __init__(self):
        self._value = 0
        self._lock = asyncio.Lock()
    
    async def increment(self) -> int:
        async with self._lock:
            self._value += 1
            return self._value
    
    async def get_value(self) -> int:
        async with self._lock:
            return self._value
        class PetStateManager:
            """Manages individual pet state and handles stat calculations."""
            def __init__(self, pet_id: int, initial_stats: Dict[str, Any]):
                """
                Initialize pet state manager.
                
                Args:
                    pet_id: Unique identifier for the pet
                    initial_stats: Dictionary containing pet's initial stats
                """
                self.pet_id = pet_id
                self.name = initial_stats['name']
                self.species = initial_stats['species']
                self.stats = initial_stats['stats'].copy()
                self._state = PetState.NORMAL  # Private state variable
                self._state_lock = asyncio.Lock()  # Lock for state transitions
                self._stats_lock = asyncio.Lock()  # Lock for stats modifications
                self.last_update = initial_stats['last_update']
                self.interaction_history: Dict[InteractionType, datetime] = {}
                self.treat_count = 0
                self.last_treat_reset = datetime.now(timezone.utc)
                self._operation_counter = AtomicCounter()
                self._pending_changes: Dict[int, Dict[str, Any]] = {}
                self._last_verified_state: Optional[Dict[str, Any]] = None
                self._last_persistence_time = datetime.now(timezone.utc)
                self._lock = asyncio.Lock()  # Add lock attribute
                def __init__(self, pet_id: int, initial_stats: Dict[str, Any]):
                    """
                    Initialize pet state manager.
                    
                    Args:
                        pet_id: Unique identifier for the pet
                        initial_stats: Dictionary containing pet's initial stats
                    """
                    self.pet_id = pet_id
                    self.name = initial_stats['name']
                    self.species = initial_stats['species']
                    self.stats = initial_stats['stats'].copy()
                    self._state = PetState.NORMAL  # Private state variable
                    self._state_lock = asyncio.Lock()  # Lock for state transitions
                    self._stats_lock = asyncio.Lock()  # Lock for stats modifications
                    self.last_update = initial_stats['last_update']
                    self.interaction_history: Dict[InteractionType, datetime] = {}
                    self.treat_count = 0
                    self.last_treat_reset = datetime.now(timezone.utc)
                    self._operation_counter = AtomicCounter()
                    self._pending_changes: Dict[int, Dict[str, Any]] = {}
                    self._last_verified_state: Optional[Dict[str, Any]] = None
                    self._last_persistence_time = datetime.now(timezone.utc)
                    self._lock = asyncio.Lock()  # Add lock attribute
                    class PetStateManager:
                        """Initialize the pet state manager."""
                        self._pet_states = {}
                        self._lock = asyncio.Lock()
                    
                    async def get_pet_state(self, pet_id: int) -> Optional[PetState]:
                        """Get or create a pet state for the given pet ID."""
                        try:
                            async with self._lock:
                                if pet_id not in self._pet_states:
                                    # Load pet data from database
                                    pet_data = get_pet_stats(pet_id)
                                    if not pet_data:
                                        logger.error(f"Failed to load stats for pet {pet_id}")
                                        return None
                                    
                                    # Create new pet state
                                    self._pet_states[pet_id] = PetState(
                                        pet_id=pet_id,
                                        name=pet_data['name'],
                                        species=pet_data['species'],
                                        stats=pet_data['stats']
                                    )
                                
                                return self._pet_states[pet_id]
                                
                        except Exception as e:
                            logger.error(f"Error getting pet state: {e}")
                            logger.error(traceback.format_exc())
class PetState:
    def __init__(self, pet_id: int, name: str, species: str, stats: Dict[str, int]):
        """Initialize pet state."""
        self.pet_id = pet_id
        self.name = name
        self.species = species
        self.stats = stats
        self._state = PetStatus.NORMAL  # Update to use PetStatus enum
        self._lock = asyncio.Lock()
        self.last_update = datetime.now(timezone.utc)
        self.interaction_history = {}
    @property
    def state(self) -> PetStatus:
        """Get current pet state."""
        return self._state
    async def set_state(self, new_state: PetStatus) -> None:
        """Thread-safe setter for pet state."""
        async with self._lock:
            self._state = new_state
    async def update(self) -> None:
        """Update pet stats based on time elapsed."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            time_elapsed = (now - self.last_update).total_seconds()
            
            # Update stats based on time elapsed (every hour)
            hours_elapsed = time_elapsed / 3600
            if hours_elapsed >= 1:
                # Decrease stats over time
                self.stats['hunger'] = max(0, self.stats['hunger'] - int(5 * hours_elapsed))
                self.stats['energy'] = max(0, self.stats['energy'] - int(3 * hours_elapsed))
                self.stats['hygiene'] = max(0, self.stats['hygiene'] - int(4 * hours_elapsed))
                self.stats['happiness'] = max(0, self.stats['happiness'] - int(2 * hours_elapsed))
                
                # Update state based on stats
                if self.stats['hygiene'] < 30:
                    await self.set_state(PetStatus.SICK)
                elif self.stats['happiness'] < 30:
                    await self.set_state(PetStatus.UNHAPPY)
                else:
                    await self.set_state(PetStatus.NORMAL)
                
                self.last_update = now
class PetStateManager:
    """Manages pet states and handles stat calculations."""
    def __init__(self):
        self._pet_states = {}
        self._lock = asyncio.Lock()
        self._operation_counter = AtomicCounter()
        
    async def get_pet_state(self, pet_id: int) -> Optional[PetState]:
        """Get or create a pet state for the given pet ID."""
        try:
            async with self._lock:
                if pet_id not in self._pet_states:
                    # Load pet data from database
                    pet_data = get_pet_stats(pet_id)
                    if not pet_data:
                        logger.error(f"Failed to load stats for pet {pet_id}")
                        return None
                    
                    # Create new pet state
                    self._pet_states[pet_id] = PetState(
                        pet_id=pet_id,
                        name=pet_data['name'],
                        species=pet_data['species'],
                        stats=pet_data['stats']
                    )
                
                return self._pet_states[pet_id]
                
        except Exception as e:
            logger.error(f"Error getting pet state: {e}")
            logger.error(traceback.format_exc())
            return None
        if pet_id not in self.states:
            # Load initial stats from database or use defaults
            initial_stats = await self.load_pet_stats(pet_id)
            self.states[pet_id] = PetState(pet_id, initial_stats)
        return self.states[pet_id]
        
    async def load_pet_stats(self, pet_id: int):
        """Load pet stats from database"""
        # Implement database loading logic here
        # For now, return default stats
        return {
            'hunger': 100,
            'happiness': 100,
            'energy': 100,
            'hygiene': 100
        }

@dataclass
class InteractionEffect:
    """Defines the effects and requirements of a pet interaction."""
    happiness: int
    hunger: int
    energy: int
    hygiene: int
    cooldown: timedelta
    conditions: Dict[str, Any]
    """Thread-safe counter for tracking atomic operations."""
    def __init__(self):
        self._value = 0
        self._lock = asyncio.Lock()
    
    async def increment(self) -> int:
        async with self._lock:
            self._value += 1
            return self._value
    
    async def get_value(self) -> int:
        async with self._lock:
            return self._value
        class PetStateManager:
            """Manages individual pet state and handles stat calculations."""
            def __init__(self, pet_id: int, initial_stats: Dict[str, Any]):
                """
                Initialize pet state manager.
                
                Args:
                    pet_id: Unique identifier for the pet
                    initial_stats: Dictionary containing pet's initial stats
                """
                self.pet_id = pet_id
                self.name = initial_stats['name']
                self.species = initial_stats['species']
                self.stats = initial_stats['stats'].copy()
                self._state = PetState.NORMAL  # Private state variable
                self._state_lock = asyncio.Lock()  # Lock for state transitions
                self._stats_lock = asyncio.Lock()  # Lock for stats modifications
                self.last_update = initial_stats['last_update']
                self.interaction_history: Dict[InteractionType, datetime] = {}
                self.treat_count = 0
                self.last_treat_reset = datetime.now(timezone.utc)
                self._operation_counter = AtomicCounter()
                self._pending_changes: Dict[int, Dict[str, Any]] = {}
                self._last_verified_state: Optional[Dict[str, Any]] = None
                self._last_persistence_time = datetime.now(timezone.utc)
                self._lock = asyncio.Lock()  # Add lock attribute
                def __init__(self, pet_id: int, initial_stats: Dict[str, Any]):
                    """
                    Initialize pet state manager.
                    
                    Args:
                        pet_id: Unique identifier for the pet
                        initial_stats: Dictionary containing pet's initial stats
                    """
                    self.pet_id = pet_id
                    self.name = initial_stats['name']
                    self.species = initial_stats['species']
                    self.stats = initial_stats['stats'].copy()
                    self._state = PetState.NORMAL  # Private state variable
                    self._state_lock = asyncio.Lock()  # Lock for state transitions
                    self._stats_lock = asyncio.Lock()  # Lock for stats modifications
                    self.last_update = initial_stats['last_update']
                    self.interaction_history: Dict[InteractionType, datetime] = {}
                    self.treat_count = 0
                    self.last_treat_reset = datetime.now(timezone.utc)
                    self._operation_counter = AtomicCounter()
                    self._pending_changes: Dict[int, Dict[str, Any]] = {}
                    self._last_verified_state: Optional[Dict[str, Any]] = None
                    self._last_persistence_time = datetime.now(timezone.utc)
                    self._lock = asyncio.Lock()  # Add lock attribute
                    class PetStateManager:
                        """Initialize the pet state manager."""
                        self._pet_states = {}
                        self._lock = asyncio.Lock()
                    
                    async def get_pet_state(self, pet_id: int) -> Optional[PetState]:
                        """Get or create a pet state for the given pet ID."""
                        try:
                            async with self._lock:
                                if pet_id not in self._pet_states:
                                    # Load pet data from database
                                    pet_data = get_pet_stats(pet_id)
                                    if not pet_data:
                                        logger.error(f"Failed to load stats for pet {pet_id}")
                                        return None
                                    
                                    # Create new pet state
                                    self._pet_states[pet_id] = PetState(
                                        pet_id=pet_id,
                                        name=pet_data['name'],
                                        species=pet_data['species'],
                                        stats=pet_data['stats']
                                    )
                                
                                return self._pet_states[pet_id]
                                
                        except Exception as e:
                            logger.error(f"Error getting pet state: {e}")
                            logger.error(traceback.format_exc())
class PetState:
    def __init__(self, pet_id: int, name: str, species: str, stats: Dict[str, int]):
        """Initialize pet state."""
        self.pet_id = pet_id
        self.name = name
        self.species = species
        self.stats = stats
        self._state = PetStatus.NORMAL  # Update to use PetStatus enum
        self._lock = asyncio.Lock()
        self.last_update = datetime.now(timezone.utc)
        self.interaction_history = {}
    @property
    def state(self) -> PetStatus:
        """Get current pet state."""
        return self._state
    async def set_state(self, new_state: PetStatus) -> None:
        """Thread-safe setter for pet state."""
        async with self._lock:
            self._state = new_state
    async def update(self) -> None:
        """Update pet stats based on time elapsed."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            time_elapsed = (now - self.last_update).total_seconds()
            
            # Update stats based on time elapsed (every hour)
            hours_elapsed = time_elapsed / 3600
            if hours_elapsed >= 1:
                # Decrease stats over time
                self.stats['hunger'] = max(0, self.stats['hunger'] - int(5 * hours_elapsed))
                self.stats['energy'] = max(0, self.stats['energy'] - int(3 * hours_elapsed))
                self.stats['hygiene'] = max(0, self.stats['hygiene'] - int(4 * hours_elapsed))
                self.stats['happiness'] = max(0, self.stats['happiness'] - int(2 * hours_elapsed))
                
                # Update state based on stats
                if self.stats['hygiene'] < 30:
                    await self.set_state(PetStatus.SICK)
                elif self.stats['happiness'] < 30:
                    await self.set_state(PetStatus.UNHAPPY)
                else:
                    await self.set_state(PetStatus.NORMAL)
                
                self.last_update = now
class PetStateManager:
    """Manages pet states and handles stat calculations."""
    def __init__(self):
        self._pet_states = {}
        self._lock = asyncio.Lock()
        self._operation_counter = AtomicCounter()
        
    async def get_pet_state(self, pet_id: int) -> Optional[PetState]:
        """Get or create a pet state for the given pet ID."""
        try:
            async with self._lock:
                if pet_id not in self._pet_states:
                    # Load pet data from database
                    pet_data = get_pet_stats(pet_id)
                    if not pet_data:
                        logger.error(f"Failed to load stats for pet {pet_id}")
                        return None
                    
                    # Create new pet state
                    self._pet_states[pet_id] = PetState(
                        pet_id=pet_id,
                        name=pet_data['name'],
                        species=pet_data['species'],
                        stats=pet_data['stats']
                    )
                
                return self._pet_states[pet_id]
                
        except Exception as e:
            logger.error(f"Error getting pet state: {e}")
            logger.error(traceback.format_exc())
            return None
        if pet_id not in self.states:
            # Load initial stats from database or use defaults
            initial_stats = await self.load_pet_stats(pet_id)
            self.states[pet_id] = PetState(pet_id, initial_stats)
        return self.states[pet_id]
        
    async def load_pet_stats(self, pet_id: int):
        """Load pet stats from database"""
        # Implement database loading logic here
        # For now, return default stats
        return {
            'hunger': 100,
            'happiness': 100,
            'energy': 100,
            'hygiene': 100
        }

@dataclass
class InteractionEffect:
    """Defines the effects and requirements of a pet interaction."""
    happiness: int
    hunger: int
    energy: int
    hygiene: int
    cooldown: timedelta
    conditions: Dict[str, Any]
    """Thread-safe counter for tracking atomic operations."""
    def __init__(self):
        self._value = 0
        self._lock = asyncio.Lock()
    
    async def increment(self) -> int:
        async with self._lock:
            self._value += 1
            return self._value
    
    async def get_value(self) -> int:
        async with self._lock:
            return self._value
        class PetStateManager:
            """Manages individual pet state and handles stat calculations."""
            def __init__(self, pet_id: int, initial_stats: Dict[str, Any]):
                """
                Initialize pet state manager.
                
                Args:
                    pet_id: Unique identifier for the pet
                    initial_stats: Dictionary containing pet's initial stats
                """
                self.pet_id = pet_id
                self.name = initial_stats['name']
                self.species = initial_stats['species']
                self.stats = initial_stats['stats'].copy()
                self._state = PetState.NORMAL  # Private state variable
                self._state_lock = asyncio.Lock()  # Lock for state transitions
                self._stats_lock = asyncio.Lock()  # Lock for stats modifications
                self.last_update = initial_stats['last_update']
                self.interaction_history: Dict[InteractionType, datetime] = {}
                self.treat_count = 0
                self.last_treat_reset = datetime.now(timezone.utc)
                self._operation_counter = AtomicCounter()
                self._pending_changes: Dict[int, Dict[str, Any]] = {}
                self._last_verified_state: Optional[Dict[str, Any]] = None
                self._last_persistence_time = datetime.now(timezone.utc)
                self._lock = asyncio.Lock()  # Add lock attribute
                def __init__(self, pet_id: int, initial_stats: Dict[str, Any]):
                    """
                    Initialize pet state manager.
                    
                    Args:
                        pet_id: Unique identifier for the pet
                        initial_stats: Dictionary containing pet's initial stats
                    """
                    self.pet_id = pet_id
                    self.name = initial_stats['name']
                    self.species = initial_stats['species']
                    self.stats = initial_stats['stats'].copy()
                    self._state = PetState.NORMAL  # Private state variable
                    self._state_lock = asyncio.Lock()  # Lock for state transitions
                    self._stats_lock = asyncio.Lock()  # Lock for stats modifications
                    self.last_update = initial_stats['last_update']
                    self.interaction_history: Dict[InteractionType, datetime] = {}
                    self.treat_count = 0
                    self.last_treat_reset = datetime.now(timezone.utc)
                    self._operation_counter = AtomicCounter()
                    self._pending_changes: Dict[int, Dict[str, Any]] = {}
                    self._last_verified_state: Optional[Dict[str, Any]] = None
                    self._last_persistence_time = datetime.now(timezone.utc)
                    self._lock = asyncio.Lock()  # Add lock attribute
                    class PetStateManager:
                        """Initialize the pet state manager."""
                        self._pet_states = {}
                        self._lock = asyncio.Lock()
                    
                    async def get_pet_state(self, pet_id: int) -> Optional[PetState]:
                        """Get or create a pet state for the given pet ID."""
                        try:
                            async with self._lock:
                                if pet_id not in self._pet_states:
                                    # Load pet data from database
                                    pet_data = get_pet_stats(pet_id)
                                    if not pet_data:
                                        logger.error(f"Failed to load stats for pet {pet_id}")
                                        return None
                                    
                                    # Create new pet state
                                    self._pet_states[pet_id] = PetState(
                                        pet_id=pet_id,
                                        name=pet_data['name'],
                                        species=pet_data['species'],
                                        stats=pet_data['stats']
                                    )
                                
                                return self._pet_states[pet_id]
                                
                        except Exception as e:
                            logger.error(f"Error getting pet state: {e}")
                            logger.error(traceback.format_exc())
class PetState:
    def __init__(self, pet_id: int, name: str, species: str, stats: Dict[str, int]):
        """Initialize pet state."""
        self.pet_id = pet_id
        self.name = name
        self.species = species
        self.stats = stats
        self._state = PetStatus.NORMAL  # Update to use PetStatus enum
        self._lock = asyncio.Lock()
        self.last_update = datetime.now(timezone.utc)
        self.interaction_history = {}
    @property
    def state(self) -> PetStatus:
        """Get current pet state."""
        return self._state
    async def set_state(self, new_state: PetStatus) -> None:
        """Thread-safe setter for pet state."""
        async with self._lock:
            self._state = new_state
    async def update(self) -> None:
        """Update pet stats based on time elapsed."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            time_elapsed = (now - self.last_update).total_seconds()
            
            # Update stats based on time elapsed (every hour)
            hours_elapsed = time_elapsed / 3600
            if hours_elapsed >= 1:
                # Decrease stats over time
                self.stats['hunger'] = max(0, self.stats['hunger'] - int(5 * hours_elapsed))
                self.stats['energy'] = max(0, self.stats['energy'] - int(3 * hours_elapsed))
                self.stats['hygiene'] = max(0, self.stats['hygiene'] - int(4 * hours_elapsed))
                self.stats['happiness'] = max(0, self.stats['happiness'] - int(2 * hours_elapsed))
                
                # Update state based on stats
                if self.stats['hygiene'] < 30:
                    await self.set_state(PetStatus.SICK)
                elif self.stats['happiness'] < 30:
                    await self.set_state(PetStatus.UNHAPPY)
                else:
                    await self.set_state(PetStatus.NORMAL)
                
                self.last_update = now
class PetStateManager:
    """Manages pet states and handles stat calculations."""
    def __init__(self):
        self._pet_states = {}
        self._lock = asyncio.Lock()
        self._operation_counter = AtomicCounter()
        
    async def get_pet_state(self, pet_id: int) -> Optional[PetState]:
        """Get or create a pet state for the given pet ID."""
        try:
            async with self._lock:
                if pet_id not in self._pet_states:
                    # Load pet data from database
                    pet_data = get_pet_stats(pet_id)
                    if not pet_data:
                        logger.error(f"Failed to load stats for pet {pet_id}")
                        return None
                    
                    # Create new pet state
                    self._pet_states[pet_id] = PetState(
                        pet_id=pet_id,
                        name=pet_data['name'],
                        species=pet_data['species'],
                        stats=pet_data['stats']
                    )
                
                return self._pet_states[pet_id]
                
        except Exception as e:
            logger.error(f"Error getting pet state: {e}")
            logger.error(traceback.format_exc())
            return None
        if pet_id not in self.states:
            # Load initial stats from database or use defaults
            initial_stats = await self.load_pet_stats(pet_id)
            self.states[pet_id] = PetState(pet_id, initial_stats)
        return self.states[pet_id]
        
    async def load_pet_stats(self, pet_id: int):
        """Load pet stats from database"""
        # Implement database loading logic here
        # For now, return default stats
        return {
            'hunger': 100,
            'happiness': 100,
            'energy': 100,
            'hygiene': 100
        }

@dataclass
class InteractionEffect:
    """Defines the effects and requirements of a pet interaction."""
    happiness: int
    hunger: int
    energy: int
    hygiene: int
    cooldown: timedelta
    conditions: Dict[str, Any]
    """Thread-safe counter for tracking atomic operations."""
    def __init__(self):
        self._value = 0
        self._lock = asyncio.Lock()
    
    async def increment(self) -> int:
        async with self._lock:
            self._value += 1
            return self._value
    
    async def get_value(self) -> int:
        async with self._lock:
            return self._value
        class PetStateManager:
            """Manages individual pet state and handles stat calculations."""
            def __init__(self, pet_id: int, initial_stats: Dict[str, Any]):
                """
                Initialize pet state manager.
                
                Args:
                    pet_id: Unique identifier for the pet
                    initial_stats: Dictionary containing pet's initial stats
                """
                self.pet_id = pet_id
                self.name = initial_stats['name']
                self.species = initial_stats['species']
                self.stats = initial_stats['stats'].copy()
                self._state = PetState.NORMAL  # Private state variable
                self._state_lock = asyncio.Lock()  # Lock for state transitions
                self._stats_lock = asyncio.Lock()  # Lock for stats modifications
                self.last_update = initial_stats['last_update']
                self.interaction_history: Dict[InteractionType, datetime] = {}
                self.treat_count = 0
                self.last_treat_reset = datetime.now(timezone.utc)
                self._operation_counter = AtomicCounter()
                self._pending_changes: Dict[int, Dict[str, Any]] = {}
                self._last_verified_state: Optional[Dict[str, Any]] = None
                self._last_persistence_time = datetime.now(timezone.utc)
                self._lock = asyncio.Lock()  # Add lock attribute
                def __init__(self, pet_id: int, initial_stats: Dict[str, Any]):
                    """
                    Initialize pet state manager.
                    
                    Args:
                        pet_id: Unique identifier for the pet
                        initial_stats: Dictionary containing pet's initial stats
                    """
                    self.pet_id = pet_id
                    self.name = initial_stats['name']
                    self.species = initial_stats['species']
                    self.stats = initial_stats['stats'].copy()
                    self._state = PetState.NORMAL  # Private state variable
                    self._state_lock = asyncio.Lock()  # Lock for state transitions
                    self._stats_lock = asyncio.Lock()  # Lock for stats modifications
                    self.last_update = initial_stats['last_update']
                    self.interaction_history: Dict[InteractionType, datetime] = {}
                    self.treat_count = 0
                    self.last_treat_reset = datetime.now(timezone.utc)
                    self._operation_counter = AtomicCounter()
                    self._pending_changes: Dict[int, Dict[str, Any]] = {}
                    self._last_verified_state: Optional[Dict[str, Any]] = None
                    self._last_persistence_time = datetime.now(timezone.utc)
                    self._lock = asyncio.Lock()  # Add lock attribute
                    class PetStateManager:
                        """Initialize the pet state manager."""
                        self._pet_states = {}
                        self._lock = asyncio.Lock()
                    
                    async def get_pet_state(self, pet_id: int) -> Optional[PetState]:
                        """Get or create a pet state for the given pet ID."""
                        try:
                            async with self._lock:
                                if pet_id not in self._pet_states:
                                    # Load pet data from database
                                    pet_data = get_pet_stats(pet_id)
                                    if not pet_data:
                                        logger.error(f"Failed to load stats for pet {pet_id}")
                                        return None
                                    
                                    # Create new pet state
                                    self._pet_states[pet_id] = PetState(
                                        pet_id=pet_id,
                                        name=pet_data['name'],
                                        species=pet_data['species'],
                                        stats=pet_data['stats']
                                    )
                                
                                return self._pet_states[pet_id]
                                
                        except Exception as e:
                            logger.error(f"Error getting pet state: {e}")
                            logger.error(traceback.format_exc())
class PetState:
    def __init__(self, pet_id: int, name: str, species: str, stats: Dict[str, int]):
        """Initialize pet state."""
        self.pet_id = pet_id
        self.name = name
        self.species = species
        self.stats = stats
        self._state = PetStatus.NORMAL  # Update to use PetStatus enum
        self._lock = asyncio.Lock()
        self.last_update = datetime.now(timezone.utc)
        self.interaction_history = {}
    @property
    def state(self) -> PetStatus:
        """Get current pet state."""
        return self._state
    async def set_state(self, new_state: PetStatus) -> None:
        """Thread-safe setter for pet state."""
        async with self._lock:
            self._state = new_state
    async def update(self) -> None:
        """Update pet stats based on time elapsed."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            time_elapsed = (now - self.last_update).total_seconds()
            
            # Update stats based on time elapsed (every hour)
            hours_elapsed = time_elapsed / 3600
            if hours_elapsed >= 1:
                # Decrease stats over time
                self.stats['hunger'] = max(0, self.stats['hunger'] - int(5 * hours_elapsed))
                self.stats['energy'] = max(0, self.stats['energy'] - int(3 * hours_elapsed))
                self.stats['hygiene'] = max(0, self.stats['hygiene'] - int(4 * hours_elapsed))
                self.stats['happiness'] = max(0, self.stats['happiness'] - int(2 * hours_elapsed))
                
                # Update state based on stats
                if self.stats['hygiene'] < 30:
                    await self.set_state(PetStatus.SICK)
                elif self.stats['happiness'] < 30:
                    await self.set_state(PetStatus.UNHAPPY)
                else:
                    await self.set_state(PetStatus.NORMAL)
                
                self.last_update = now
class PetStateManager:
    """Manages pet states and handles stat calculations."""
    def __init__(self):
        self._pet_states = {}
        self._lock = asyncio.Lock()
        self._operation_counter = AtomicCounter()
        
    async def get_pet_state(self, pet_id: int) -> Optional[PetState]:
        """Get or create a pet state for the given pet ID."""
        try:
            async with self._lock:
                if pet_id not in self._pet_states:
                    # Load pet data from database
                    pet_data = get_pet_stats(pet_id)
                    if not pet_data:
                        logger.error(f"Failed to load stats for pet {pet_id}")
                        return None
                    
                    # Create new pet state
                    self._pet_states[pet_id] = PetState(
                        pet_id=pet_id,
                        name=pet_data['name'],
                        species=pet_data['species'],
                        stats=pet_data['stats']
                    )
                
                return self._pet_states[pet_id]
                
        except Exception as e:
            logger.error(f"Error getting pet state: {e}")
            logger.error(traceback.format_exc())
            return None
        if pet_id not in self.states:
            # Load initial stats from database or use defaults
            initial_stats = await self.load_pet_stats(pet_id)
            self.states[pet_id] = PetState(pet_id, initial_stats)
        return self.states[pet_id]
        
    async def load_pet_stats(self, pet_id: int):
        """Load pet stats from database"""
        # Implement database loading logic here
        # For now, return default stats
        return {
            'hunger': 100,
            'happiness': 100,
            'energy': 100,
            'hygiene': 100
        }

@dataclass
class InteractionEffect:
    """Defines the effects and requirements of a pet interaction."""
    happiness: int
    hunger: int
    energy: int
    hygiene: int
    cooldown: timedelta
    conditions: Dict[str, Any]
    """Thread-safe counter for tracking atomic operations."""
    def __init__(self):
        self._value = 0
        self._lock = asyncio.Lock()
    
    async def increment(self) -> int:
        async with self._lock:
            self._value += 1
            return self._value
    
    async def get_value(self) -> int:
        async with self._lock:
            return self._value
        class PetStateManager:
            """Manages individual pet state and handles stat calculations."""
            def __init__(self, pet_id: int, initial_stats: Dict[str, Any]):
                """
                Initialize pet state manager.
                
                Args:
                    pet_id: Unique identifier for the pet
                    initial_stats: Dictionary containing pet's initial stats
                """
                self.pet_id = pet_id
                self.name = initial_stats['name']
                self.species = initial_stats['species']
                self.stats = initial_stats['stats'].copy()
                self._state = PetState.NORMAL  # Private state variable
                self._state_lock = asyncio.Lock()  # Lock for state transitions
                self._stats_lock = asyncio.Lock()  # Lock for stats modifications
                self.last_update = initial_stats['last_update']
                self.interaction_history: Dict[InteractionType, datetime] = {}
                self.treat_count = 0
                self.last_treat_reset = datetime.now(timezone.utc)
                self._operation_counter = AtomicCounter()
                self._pending_changes: Dict[int, Dict[str, Any]] = {}
                self._last_verified_state: Optional[Dict[str, Any]] = None
                self._last_persistence_time = datetime.now(timezone.utc)
                self._lock = asyncio.Lock()  # Add lock attribute
                def __init__(self, pet_id: int, initial_stats: Dict[str, Any]):
                    """
                    Initialize pet state manager.
                    
                    Args:
                        pet_id: Unique identifier for the pet
                        initial_stats: Dictionary containing pet's initial stats
                    """
                    self.pet_id = pet_id
                    self.name = initial_stats['name']
                    self.species = initial_stats['species']
                    self.stats = initial_stats['stats'].copy()
                    self._state = PetState.NORMAL  # Private state variable
                    self._state_lock = asyncio.Lock()  # Lock for state transitions
                    self._stats_lock = asyncio.Lock()  # Lock for stats modifications
                    self.last_update = initial_stats['last_update']
                    self.interaction_history: Dict[InteractionType, datetime] = {}
                    self.treat_count = 0
                    self.last_treat_reset = datetime.now(timezone.utc)
                    self._operation_counter = AtomicCounter()
                    self._pending_changes: Dict[int, Dict[str, Any]] = {}
                    self._last_verified_state: Optional[Dict[str, Any]] = None
                    self._last_persistence_time = datetime.now(timezone.utc)
                    self._lock = asyncio.Lock()  # Add lock attribute
                    class PetStateManager:
                        """Initialize the pet state manager."""
                        self._pet_states = {}
                        self._lock = asyncio.Lock()
                    
                    async def get_pet_state(self, pet_id: int) -> Optional[PetState]:
                        """Get or create a pet state for the given pet ID."""
                        try:
                            async with self._lock:
                                if pet_id not in self._pet_states:
                                    # Load pet data from database
                                    pet_data = get_pet_stats(pet_id)
                                    if not pet_data:
                                        logger.error(f"Failed to load stats for pet {pet_id}")
                                        return None
                                    
                                    # Create new pet state
                                    self._pet_states[pet_id] = PetState(
                                        pet_id=pet_id,
                                        name=pet_data['name'],
                                        species=pet_data['species'],
                                        stats=pet_data['stats']
                                    )
                                
                                return self._pet_states[pet_id]
                                
                        except Exception as e:
                            logger.error(f"Error getting pet state: {e}")
                            logger.error(traceback.format_exc())
class PetState:
    def __init__(self, pet_id: int, name: str, species: str, stats: Dict[str, int]):
        """Initialize pet state."""
        self.pet_id = pet_id
        self.name = name
        self.species = species
        self.stats = stats
        self._state = PetStatus.NORMAL  # Update to use PetStatus enum
        self._lock = asyncio.Lock()
        self.last_update = datetime.now(timezone.utc)
        self.interaction_history = {}
    @property
    def state(self) -> PetStatus:
        """Get current pet state."""
        return self._state
    async def set_state(self, new_state: PetStatus) -> None:
        """Thread-safe setter for pet state."""
        async with self._lock:
            self._state = new_state
    async def update(self) -> None:
        """Update pet stats based on time elapsed."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            time_elapsed = (now - self.last_update).total_seconds()
            
            # Update stats based on time elapsed (every hour)
            hours_elapsed = time_elapsed / 3600
            if hours_elapsed >= 1:
                # Decrease stats over time
                self.stats['hunger'] = max(0, self.stats['hunger'] - int(5 * hours_elapsed))
                self.stats['energy'] = max(0, self.stats['energy'] - int(3 * hours_elapsed))
                self.stats['hygiene'] = max(0, self.stats['hygiene'] - int(4 * hours_elapsed))
                self.stats['happiness'] = max(0, self.stats['happiness'] - int(2 * hours_elapsed))
                
                # Update state based on stats
                if self.stats['hygiene'] < 30:
                    await self.set_state(PetStatus.SICK)
                elif self.stats['happiness'] < 30:
                    await self.set_state(PetStatus.UNHAPPY)
                else:
                    await self.set_state(PetStatus.NORMAL)
                
                self.last_update = now
class PetStateManager:
    """Manages pet states and handles stat calculations."""
    def __init__(self):
        self._pet_states = {}
        self._lock = asyncio.Lock()
        self._operation_counter = AtomicCounter()
        
    async def get_pet_state(self, pet_id: int) -> Optional[PetState]:
        """Get or create a pet state for the given pet ID."""
        try:
            async with self._lock:
                if pet_id not in self._pet_states:
                    # Load pet data from database
                    pet_data = get_pet_stats(pet_id)
                    if not pet_data:
                        logger.error(f"Failed to load stats for pet {pet_id}")
                        return None
                    
                    # Create new pet state
                    self._pet_states[pet_id] = PetState(
                        pet_id=pet_id,
                        name=pet_data['name'],
                        species=pet_data['species'],
                        stats=pet_data['stats']
                    )
                
                return self._pet_states[pet_id]
                
        except Exception as e:
            logger.error(f"Error getting pet state: {e}")
            logger.error(traceback.format_exc())
            return None
        if pet_id not in self.states:
            # Load initial stats from database or use defaults
            initial_stats = await self.load_pet_stats(pet_id)
            self.states[pet_id] = PetState(pet_id, initial_stats)
        return self.states[pet_id]
        
    async def load_pet_stats(self, pet_id: int):
        """Load pet stats from database"""
        # Implement database loading logic here
        # For now, return default stats
        return {
            'hunger': 100,
            'happiness': 100,
            'energy': 100,
            'hygiene': 100
        }

@dataclass
class InteractionEffect:
    """Defines the effects and requirements of a pet interaction."""
    happiness: int
    hunger: int
    energy: int
    hygiene: int
    cooldown: timedelta
    conditions: Dict[str, Any]
    """Thread-safe counter for tracking atomic operations."""
    def __init__(self):
        self._value = 0
        self._lock = asyncio.Lock()
    
    async def increment(self) -> int:
        async with self._lock:
            self._value += 1
            return self._value
    
    async def get_value(self) -> int:
        async with self._lock:
            return self._value
        class PetStateManager:
            """Manages individual pet state and handles stat calculations."""
            def __init__(self, pet_id: int, initial_stats: Dict[str, Any]):
                """
                Initialize pet state manager.
                
                Args:
                    pet_id: Unique identifier for the pet
                    initial_stats: Dictionary containing pet's initial stats
                """
                self.pet_id = pet_id
                self.name = initial_stats['name']
                self.species = initial_stats['species']
                self.stats = initial_stats['stats'].copy()
                self._state = PetState.NORMAL  # Private state variable
                self._state_lock = asyncio.Lock()  # Lock for state transitions
                self._stats_lock = asyncio.Lock()  # Lock for stats modifications
                self.last_update = initial_stats['last_update']
                self.interaction_history: Dict[InteractionType, datetime] = {}
                self.treat_count = 0
                self.last_treat_reset = datetime.now(timezone.utc)
                self._operation_counter = AtomicCounter()
                self._pending_changes: Dict[int, Dict[str, Any]] = {}
                self._last_verified_state: Optional[Dict[str, Any]] = None
                self._last_persistence_time = datetime.now(timezone.utc)
                self._lock = asyncio.Lock()  # Add lock attribute
                def __init__(self, pet_id: int, initial_stats: Dict[str, Any]):
                    """
                    Initialize pet state manager.
                    
                    Args:
                        pet_id: Unique identifier for the pet
                        initial_stats: Dictionary containing pet's initial stats
                    """
                    self.pet_id = pet_id
                    self.name = initial_stats['name']
                    self.species = initial_stats['species']
                    self.stats = initial_stats['stats'].copy()
                    self._state = PetState.NORMAL  # Private state variable
                    self._state_lock = asyncio.Lock()  # Lock for state transitions
                    self._stats_lock = asyncio.Lock()  # Lock for stats modifications
                    self.last_update = initial_stats['last_update']
                    self.interaction_history: Dict[InteractionType, datetime] = {}
                    self.treat_count = 0
                    self.last_treat_reset = datetime.now(timezone.utc)
                    self._operation_counter = AtomicCounter()
                    self._pending_changes: Dict[int, Dict[str, Any]] = {}
                    self._last_verified_state: Optional[Dict[str, Any]] = None
                    self._last_persistence_time = datetime.now(timezone.utc)
                    self._lock = asyncio.Lock()  # Add lock attribute
                    class PetStateManager:
                        """Initialize the pet state manager."""
                        self._pet_states = {}
                        self._lock = asyncio.Lock()
                    
                    async def get_pet_state(self, pet_id: int) -> Optional[PetState]:
                        """Get or create a pet state for the given pet ID."""
                        try:
                            async with self._lock:
                                if pet_id not in self._pet_states:
                                    # Load pet data from database
                                    pet_data = get_pet_stats(pet_id)
                                    if not pet_data:
                                        logger.error(f"Failed to load stats for pet {pet_id}")
                                        return None
                                    
                                    # Create new pet state
                                    self._pet_states[pet_id] = PetState(
                                        pet_id=pet_id,
                                        name=pet_data['name'],
                                        species=pet_data['species'],
                                        stats=pet_data['stats']
                                    )
                                
                                return self._pet_states[pet_id]
                                
                        except Exception as e:
                            logger.error(f"Error getting pet state: {e}")
                            logger.error(traceback.format_exc())
class PetState:
    def __init__(self, pet_id: int, name: str, species: str, stats: Dict[str, int]):
        """Initialize pet state."""
        self.pet_id = pet_id
        self.name = name
        self.species = species
        self.stats = stats
        self._state = PetStatus.NORMAL  # Update to use PetStatus enum
        self._lock = asyncio.Lock()
        self.last_update = datetime.now(timezone.utc)
        self.interaction_history = {}
    @property
    def state(self) -> PetStatus:
        """Get current pet state."""
        return self._state
    async def set_state(self, new_state: PetStatus) -> None:
        """Thread-safe setter for pet state."""
        async with self._lock:
            self._state = new_state
    async def update(self) -> None:
        """Update pet stats based on time elapsed."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            time_elapsed = (now - self.last_update).total_seconds()
            
            # Update stats based on time elapsed (every hour)
            hours_elapsed = time_elapsed / 3600
            if hours_elapsed >= 1:
                # Decrease stats over time
                self.stats['hunger'] = max(0, self.stats['hunger'] - int(5 * hours_elapsed))
                self.stats['energy'] = max(0, self.stats['energy'] - int(3 * hours_elapsed))
                self.stats['hygiene'] = max(0, self.stats['hygiene'] - int(4 * hours_elapsed))
                self.stats['happiness'] = max(0, self.stats['happiness'] - int(2 * hours_elapsed))
                
                # Update state based on stats
                if self.stats['hygiene'] < 30:
                    await self.set_state(PetStatus.SICK)
                elif self.stats['happiness'] < 30:
                    await self.set_state(PetStatus.UNHAPPY)
                else:
                    await self.set_state(PetStatus.NORMAL)
                
                self.last_update = now
class PetStateManager:
    """Manages pet states and handles stat calculations."""
    def __init__(self):
        self._pet_states = {}
        self._lock = asyncio.Lock()
        self._operation_counter = AtomicCounter()
        
    async def get_pet_state(self, pet_id: int) -> Optional[PetState]:
        """Get or create a pet state for the given pet ID."""
        try:
            async with self._lock:
                if pet_id not in self._pet_states:
                    # Load pet data from database
                    pet_data = get_pet_stats(pet_id)
                    if not pet_data:
                        logger.error(f"Failed to load stats for pet {pet_id}")
                        return None
                    
                    # Create new pet state
                    self._pet_states[pet_id] = PetState(
                        pet_id=pet_id,
                        name=pet_data['name'],
                        species=pet_data['species'],
                        stats=pet_data['stats']
                    )
                
                return self._pet_states[pet_id]
                
        except Exception as e:
            logger.error(f"Error getting pet state: {e}")
            logger.error(traceback.format_exc())
            return None
        if pet_id not in self.states:
            # Load initial stats from database or use defaults
            initial_stats = await self.load_pet_stats(pet_id)
            self.states[pet_id] = PetState(pet_id, initial_stats)
        return self.states[pet_id]
        
    async def load_pet_stats(self, pet_id: int):
        """Load pet stats from database"""
        # Implement database loading logic here
        # For now, return default stats
        return {
            'hunger': 100,
            'happiness': 100,
            'energy': 100,
            'hygiene': 100
        }

@dataclass
class InteractionEffect:
    """Defines the effects and requirements of a pet interaction."""
    happiness: int
    hunger: int
    energy: int
    hygiene: int
    cooldown: timedelta
    conditions: Dict[str, Any]
    """Thread-safe counter for tracking atomic operations."""
    def __init__(self):
        self._value = 0
        self._lock = asyncio.Lock()
    
    async def increment(self) -> int:
        async with self._lock:
            self._value += 1
            return self._value
    
    async def get_value(self) -> int:
        async with self._lock:
            return self._value
        class PetStateManager:
            """Manages individual pet state and handles stat calculations."""
            def __init__(self, pet_id: int, initial_stats: Dict[str, Any]):
                """
                Initialize pet state manager.
                
                Args:
                    pet_id: Unique identifier for the pet
                    initial_stats: Dictionary containing pet's initial stats
                """
                self.pet_id = pet_id
                self.name = initial_stats['name']
                self.species = initial_stats['species']
                self.stats = initial_stats['stats'].copy()
                self._state = PetState.NORMAL  # Private state variable
                self._state_lock = asyncio.Lock()  # Lock for state transitions
                self._stats_lock = asyncio.Lock()  # Lock for stats modifications
                self.last_update = initial_stats['last_update']
                self.interaction_history: Dict[InteractionType, datetime] = {}
                self.treat_count = 0
                self.last_treat_reset = datetime.now(timezone.utc)
                self._operation_counter = AtomicCounter()
                self._pending_changes: Dict[int, Dict[str, Any]] = {}
                self._last_verified_state: Optional[Dict[str, Any]] = None
                self._last_persistence_time = datetime.now(timezone.utc)
                self._lock = asyncio.Lock()  # Add lock attribute
                def __init__(self, pet_id: int, initial_stats: Dict[str, Any]):
                    """
                    Initialize pet state manager.
                    
                    Args:
                        pet_id: Unique identifier for the pet
                        initial_stats: Dictionary containing pet's initial stats
                    """
                    self.pet_id = pet_id
                    self.name = initial_stats['name']
                    self.species = initial_stats['species']
                    self.stats = initial_stats['stats'].copy()
                    self._state = PetState.NORMAL  # Private state variable
                    self._state_lock = asyncio.Lock()  # Lock for state transitions
                    self._stats_lock = asyncio.Lock()  # Lock for stats modifications
                    self.last_update = initial_stats['last_update']
                    self.interaction_history: Dict[InteractionType, datetime] = {}
                    self.treat_count = 0
                    self.last_treat_reset = datetime.now(timezone.utc)
                    self._operation_counter = AtomicCounter()
                    self._pending_changes: Dict[int, Dict[str, Any]] = {}
                    self._last_verified_state: Optional[Dict[str, Any]] = None