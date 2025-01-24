from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any, Set, Tuple
import logging
from dataclasses import dataclass
from enum import Enum
import traceback
from concurrent.futures import ThreadPoolExecutor
import threading
from contextlib import asynccontextmanager

from database.database import (
    execute_query,
    get_pet_stats,
    update_pet_stats,
    logger as db_logger
)

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
    happiness: int
    hunger: int
    energy: int
    hygiene: int
    cooldown: timedelta
    conditions: Dict[str, Any]

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
    # ... Add other interaction effects
}

class PetStateManager:
    """Manages individual pet state and handles stat calculations."""
    
    def __init__(self, pet_id: int, initial_stats: Dict[str, Any]):
        self.pet_id = pet_id
        self.name = initial_stats['name']
        self.species = initial_stats['species']
        self.stats = initial_stats['stats']
        self.state = self._calculate_state()
        self.last_update = initial_stats['last_update']
        self.interaction_history: Dict[InteractionType, datetime] = {}
        self.treat_count = 0
        self.last_treat_reset = datetime.now(timezone.utc)
        self._lock = asyncio.Lock()
        
    async def update(self) -> None:
        """Updates pet stats based on time elapsed."""
        async with self._lock:
            try:
                now = datetime.now(timezone.utc)
                elapsed_hours = (now - self.last_update).total_seconds() / 3600
                
                # Calculate decay
                decay = self._calculate_decay(elapsed_hours)
                
                # Apply decay and state effects
                for stat, value in decay.items():
                    self.stats[stat] = max(0, min(100, self.stats[stat] + value))
                
                # Update state
                self.state = self._calculate_state()
                
                # Persist changes
                await self._persist_stats()
                self.last_update = now
                
            except Exception as e:
                logger.error(f"Error updating pet {self.pet_id}: {e}")
                logger.error(traceback.format_exc())
                raise
    
    def _calculate_decay(self, elapsed_hours: float) -> Dict[str, float]:
        """Calculates stat decay based on elapsed time."""
        decay = {
            'hunger': -2 * elapsed_hours,
            'hygiene': -3 * elapsed_hours,
            'happiness': -1 * elapsed_hours
        }
        
        # Energy decay/regen depends on sleep state
        if self.state == PetState.SLEEPING:
            decay['energy'] = 10 * elapsed_hours
        else:
            decay['energy'] = -5 * elapsed_hours
            
        # Additional happiness decay if other stats are low
        if any(self.stats[stat] < 20 for stat in ['hunger', 'energy', 'hygiene']):
            decay['happiness'] -= 5 * elapsed_hours
            
        # Sick pets lose happiness faster
        if self.state == PetState.SICK:
            decay['happiness'] *= 2
            
        return decay
    
    def _calculate_state(self) -> PetState:
        """Determines pet state based on current stats."""
        if self.stats['energy'] < 20:
            return PetState.SLEEPING
        elif self.stats['hygiene'] < 30:
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
        async with self._lock:
            try:
                # Get interaction effect
                effect = INTERACTION_EFFECTS[interaction_type]
                
                # Check cooldown
                if not await self._check_cooldown(interaction_type):
                    return False, "Interaction on cooldown"
                
                # Validate conditions
                if not self._validate_interaction(effect):
                    return False, "Interaction conditions not met"
                
                # Calculate and apply effects
                changes = self._calculate_interaction_effects(effect)
                self._apply_stat_changes(changes)
                
                # Update state and persist
                self.state = self._calculate_state()
                await self._persist_stats()
                
                # Record interaction
                self.interaction_history[interaction_type] = datetime.now(timezone.utc)
                
                return True, "Interaction successful"
                
            except Exception as e:
                logger.error(f"Error processing interaction {interaction_type} for pet {self.pet_id}: {e}")
                return False, f"Error: {str(e)}"
    
    async def _check_cooldown(self, interaction_type: InteractionType) -> bool:
        """Checks if interaction is on cooldown."""
        if interaction_type not in self.interaction_history:
            return True
            
        last_time = self.interaction_history[interaction_type]
        cooldown = INTERACTION_EFFECTS[interaction_type].cooldown
        return datetime.now(timezone.utc) - last_time >= cooldown
    
    def _validate_interaction(self, effect: InteractionEffect) -> bool:
        """Validates interaction conditions."""
        conditions = effect.conditions
        
        if conditions.get("not_sleeping") and self.state == PetState.SLEEPING:
            return False
            
        if "max_hunger" in conditions and self.stats['hunger'] >= conditions["max_hunger"]:
            return False
            
        return True
    
    def _calculate_interaction_effects(self, effect: InteractionEffect) -> Dict[str, int]:
        """Calculates final effects of an interaction."""
        changes = {
            'happiness': effect.happiness,
            'hunger': effect.hunger,
            'energy': effect.energy,
            'hygiene': effect.hygiene
        }
        
        # Apply happiness bonus
        if self.stats['happiness'] > 80:
            for stat in changes:
                if changes[stat] > 0:
                    changes[stat] = int(changes[stat] * 1.2)
        
        return changes
    
    def _apply_stat_changes(self, changes: Dict[str, int]) -> None:
        """Applies stat changes with clamping."""
        for stat, change in changes.items():
            self.stats[stat] = max(0, min(100, self.stats[stat] + change))


class StateManager:
    """Manages all active pet states and coordinates updates."""
    
    def __init__(self, cache_timeout: int = 3600):
        self._pet_states: Dict[int, PetStateManager] = {}
        self._cache_timeout = cache_timeout
        self._last_access: Dict[int, datetime] = {}
        self._lock = asyncio.Lock()
        self._executor = ThreadPoolExecutor(max_workers=4)
        
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
            for pet_id, state in self._pet_states.items():
                update_tasks.append(state.update())
            
            if update_tasks:
                await asyncio.gather(*update_tasks, return_exceptions=True)
    
    async def cleanup_cache(self) -> None:
        """Removes stale pet states from cache."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            stale_pets = [
                pet_id for pet_id, last_access in self._last_access.items()
                if (now - last_access).total_seconds() > self._cache_timeout
            ]
            
            for pet_id in stale_pets:
                del self._pet_states[pet_id]
                del self._last_access[pet_id]
                logger.info(f"Removed stale pet state for pet {pet_id}")
    
    @asynccontextmanager
    async def get_pet_state(self, pet_id: int) -> Optional[PetStateManager]:
        """Context manager for safely accessing pet state."""
        state = await self.load_pet(pet_id)
        if not state:
            yield None
            return
            
        try:
            yield state
        finally:
            self._last_access[pet_id] = datetime.now(timezone.utc)