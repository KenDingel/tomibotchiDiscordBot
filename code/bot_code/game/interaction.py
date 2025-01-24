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

class PetState(Enum):
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
        self.stats = initial_stats['stats'].copy()  # Create a copy to avoid mutations
        self.state = self._calculate_state()
        self.last_update = initial_stats['last_update']
        self.interaction_history: Dict[InteractionType, datetime] = {}
        self.treat_count = 0
        self.last_treat_reset = datetime.now(timezone.utc)
        self._lock = asyncio.Lock()
    
    async def update(self) -> None:
        """Updates pet stats based on time elapsed since last update."""
        async with self._lock:
            try:
                now = datetime.now(timezone.utc)
                elapsed_hours = (now - self.last_update).total_seconds() / 3600
                
                # Reset daily treat count if needed
                if (now - self.last_treat_reset).total_seconds() >= 86400:  # 24 hours
                    self.treat_count = 0
                    self.last_treat_reset = now
                
                # Calculate and apply decay
                decay = self._calculate_decay(elapsed_hours)
                self._apply_stat_changes(decay)
                
                # Update state and persist changes
                self.state = self._calculate_state()
                await self._persist_stats()
                self.last_update = now
                
            except Exception as e:
                logger.error(f"Error updating pet {self.pet_id}: {e}")
                logger.error(traceback.format_exc())
                raise
    
    def _calculate_decay(self, elapsed_hours: float) -> Dict[str, float]:
        """
        Calculates stat decay based on elapsed time and current state.
        
        Args:
            elapsed_hours: Number of hours since last update
            
        Returns:
            Dictionary of stat changes
        """
        base_decay = {
            'hunger': -2 * elapsed_hours,
            'hygiene': -3 * elapsed_hours,
            'happiness': -1 * elapsed_hours
        }
        
        # Energy changes based on sleep state
        if self.state == PetState.SLEEPING:
            base_decay['energy'] = 10 * elapsed_hours  # Regenerate while sleeping
        else:
            base_decay['energy'] = -5 * elapsed_hours  # Deplete while awake
        
        # Apply state-based modifiers
        if self.state == PetState.SICK:
            base_decay['happiness'] *= 1.5  # Faster happiness decay when sick
            base_decay['energy'] *= 1.2  # More energy drain when sick
        
        # Additional happiness decay if basic needs aren't met
        if any(self.stats[stat] < 20 for stat in ['hunger', 'energy', 'hygiene']):
            base_decay['happiness'] -= 2 * elapsed_hours
        
        return base_decay
    
    def _calculate_state(self) -> PetState:
        """
        Determines pet state based on current stats.
        
        Returns:
            Current PetState enum value
        """
        if self.stats['energy'] < 20:
            return PetState.SLEEPING
        elif self.stats['hygiene'] < 30 or self.stats['hunger'] < 20:
            return PetState.SICK
        elif self.stats['happiness'] < 25:
            return PetState.UNHAPPY
        return PetState.NORMAL
    
    async def _persist_stats(self) -> None:
        """Persists current stats to database."""
        try:
            success = await asyncio.to_thread(
                update_pet_stats,
                self.pet_id,
                self.stats
            )
            if not success:
                raise Exception("Failed to persist pet stats")
        except Exception as e:
            logger.error(f"Error persisting stats for pet {self.pet_id}: {e}")
            raise

    def _apply_stat_changes(self, changes: Dict[str, float]) -> None:
        """
        Applies stat changes with bounds checking.
        
        Args:
            changes: Dictionary of stat changes to apply
        """
        for stat, change in changes.items():
            if stat in self.stats:
                self.stats[stat] = max(0, min(100, self.stats[stat] + change))

    async def process_interaction(
        self,
        interaction_type: InteractionType
    ) -> Tuple[bool, str]:
        """
        Processes a user interaction with the pet.
        
        Args:
            interaction_type: Type of interaction to process
            
        Returns:
            Tuple of (success, message)
        """
        if interaction_type not in INTERACTION_EFFECTS:
            return False, "Invalid interaction type"
            
        async with self._lock:
            try:
                effect = INTERACTION_EFFECTS[interaction_type]
                
                # Validate interaction
                if not await self._check_cooldown(interaction_type):
                    return False, "This interaction is on cooldown"
                
                if not self._validate_conditions(effect):
                    return False, self._get_failure_message(effect)
                
                # Process treat count
                if interaction_type == InteractionType.TREAT:
                    self.treat_count += 1
                
                # Apply effects
                changes = {
                    'happiness': effect.happiness,
                    'hunger': effect.hunger,
                    'energy': effect.energy,
                    'hygiene': effect.hygiene
                }
                
                self._apply_stat_changes(changes)
                self.state = self._calculate_state()
                
                # Record interaction
                self.interaction_history[interaction_type] = datetime.now(timezone.utc)
                
                # Persist changes
                await self._persist_stats()
                
                return True, "Interaction successful!"
                
            except Exception as e:
                logger.error(f"Error processing interaction for pet {self.pet_id}: {e}")
                return False, f"An error occurred: {str(e)}"

    async def _check_cooldown(self, interaction_type: InteractionType) -> bool:
        """
        Checks if an interaction is on cooldown.
        
        Args:
            interaction_type: Type of interaction to check
            
        Returns:
            bool: True if interaction is available, False if on cooldown
        """
        if interaction_type not in self.interaction_history:
            return True
            
        last_time = self.interaction_history[interaction_type]
        cooldown = INTERACTION_EFFECTS[interaction_type].cooldown
        return datetime.now(timezone.utc) - last_time >= cooldown

    def _validate_conditions(self, effect: InteractionEffect) -> bool:
        """
        Validates all conditions for an interaction.
        
        Args:
            effect: InteractionEffect to validate
            
        Returns:
            bool: True if all conditions are met
        """
        conditions = effect.conditions
        
        # Check sleeping conditions
        if conditions.get("not_sleeping") and self.state == PetState.SLEEPING:
            return False
        if conditions.get("is_sleeping") and self.state != PetState.SLEEPING:
            return False
            
        # Check stat-based conditions
        if "max_hunger" in conditions and self.stats['hunger'] >= conditions["max_hunger"]:
            return False
        if "min_energy" in conditions and self.stats['energy'] < conditions["min_energy"]:
            return False
        if "max_energy" in conditions and self.stats['energy'] >= conditions["max_energy"]:
            return False
            
        # Check treat limit
        if "max_treats_per_day" in conditions and self.treat_count >= conditions["max_treats_per_day"]:
            return False
            
        # Check sick condition
        if conditions.get("is_sick") and self.state != PetState.SICK:
            return False
            
        return True

    def _get_failure_message(self, effect: InteractionEffect) -> str:
        """Generates appropriate failure message based on conditions."""
        conditions = effect.conditions
        
        if conditions.get("not_sleeping") and self.state == PetState.SLEEPING:
            return "Pet is sleeping"
        if conditions.get("is_sleeping") and self.state != PetState.SLEEPING:
            return "Pet must be sleeping for this interaction"
        if "max_treats_per_day" in conditions and self.treat_count >= conditions["max_treats_per_day"]:
            return "Daily treat limit reached"
        if "is_sick" in conditions and self.state != PetState.SICK:
            return "Pet must be sick to use medicine"
            
        return "Interaction conditions not met"

class StateManager:
    """Manages collection of pet states and coordinates updates."""
    
    def __init__(self, cache_timeout: int = 3600):
        """
        Initialize state manager.
        
        Args:
            cache_timeout: Time in seconds before cached pet states are cleaned up
        """
        self._pet_states: Dict[int, PetStateManager] = {}
        self._cache_timeout = cache_timeout
        self._last_access: Dict[int, datetime] = {}
        self._lock = asyncio.Lock()
    
    async def load_pet(self, pet_id: int) -> Optional[PetStateManager]:
        """
        Loads or retrieves a pet's state from cache.
        
        Args:
            pet_id: ID of pet to load
            
        Returns:
            PetStateManager instance if successful, None if failed
        """
        async with self._lock:
            try:
                # Check cache first
                if pet_id in self._pet_states:
                    self._last_access[pet_id] = datetime.now(timezone.utc)
                    await self._pet_states[pet_id].update()  # Ensure stats are current
                    return self._pet_states[pet_id]
                
                # Load from database
                stats = await asyncio.to_thread(get_pet_stats, pet_id)
                if not stats:
                    logger.error(f"Failed to load stats for pet {pet_id}")
                    return None
                
                # Create new state manager
                pet_state = PetStateManager(pet_id, stats)
                self._pet_states[pet_id] = pet_state
                self._last_access[pet_id] = datetime.now(timezone.utc)
                
                return pet_state
                
            except Exception as e:
                logger.error(f"Error loading pet {pet_id}: {e}")
                logger.error(traceback.format_exc())
                return None
    
    async def update_all(self) -> None:
        """Updates all cached pet states."""
        async with self._lock:
            update_tasks = []
            for pet_id, state in list(self._pet_states.items()):
                update_tasks.append(state.update())
            
            if update_tasks:
                results = await asyncio.gather(*update_tasks, return_exceptions=True)
                
                # Log any errors that occurred during updates
                for pet_id, result in zip(self._pet_states.keys(), results):
                    if isinstance(result, Exception):
                        logger.error(f"Error updating pet {pet_id}: {result}")
    
    async def cleanup_cache(self) -> None:
        """Removes stale pet states from cache."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            stale_pets = [
                pet_id for pet_id, last_access in self._last_access.items()
                if (now - last_access).total_seconds() > self._cache_timeout
            ]
            
            for pet_id in stale_pets:
                try:
                    # Ensure final state is persisted before removing
                    if pet_id in self._pet_states:
                        await self._pet_states[pet_id].update()
                    del self._pet_states[pet_id]
                    del self._last_access[pet_id]
                    logger.info(f"Removed stale pet state for pet {pet_id}")
                except Exception as e:
                    logger.error(f"Error cleaning up pet {pet_id}: {e}")
    
    @asynccontextmanager
    async def get_pet_state(self, pet_id: int) -> Optional[PetStateManager]:
        """
        Context manager for safely accessing pet state.
        
        Args:
            pet_id: ID of pet to access
            
        Yields:
            PetStateManager instance if successful, None if failed
            
        Example:
            async with state_manager.get_pet_state(pet_id) as pet:
                if pet:
                    await pet.process_interaction(InteractionType.FEED)
        """
        state = await self.load_pet(pet_id)
        if not state:
            yield None
            return
            
        try:
            yield state
        finally:
            self._last_access[pet_id] = datetime.now(timezone.utc)
    
    async def force_update(self, pet_id: int) -> bool:
        """
        Forces an immediate update of a specific pet's state.
        
        Args:
            pet_id: ID of pet to update
            
        Returns:
            bool: True if update successful, False otherwise
        """
        async with self._lock:
            if pet_id not in self._pet_states:
                return False
                
            try:
                await self._pet_states[pet_id].update()
                return True
            except Exception as e:
                logger.error(f"Error force updating pet {pet_id}: {e}")
                return False
    
    async def remove_pet(self, pet_id: int) -> bool:
        """
        Removes a pet from the cache.
        
        Args:
            pet_id: ID of pet to remove
            
        Returns:
            bool: True if pet was removed, False if not found
        """
        async with self._lock:
            if pet_id not in self._pet_states:
                return False
                
            try:
                # Ensure final state is persisted
                await self._pet_states[pet_id].update()
                
                del self._pet_states[pet_id]
                del self._last_access[pet_id]
                logger.info(f"Manually removed pet {pet_id} from cache")
                return True
            except Exception as e:
                logger.error(f"Error removing pet {pet_id}: {e}")
                return False