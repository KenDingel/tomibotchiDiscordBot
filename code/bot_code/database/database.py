import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
from typing import Optional, Union, List, Dict, Any, Tuple
import traceback
import time
from datetime import datetime

from utils.utils import config, logger, lock

# Type aliases
DBConnection = mysql.connector.MySQLConnection
DBCursor = mysql.connector.cursor.MySQLCursor
QueryResult = Optional[List[Tuple[Any, ...]]]

# Connection pool configuration
MAIN_POOL_SIZE = 5
TIMER_POOL_SIZE = 1
CONNECTION_TIMEOUT = 120

# Global connection pools
db_pool: Optional[MySQLConnectionPool] = None
db_pool_timer: Optional[MySQLConnectionPool] = None

def get_db_connection() -> DBConnection:
    """
    Gets a connection from the main connection pool.
    
    Returns:
        DBConnection: A database connection from the main pool
        
    Raises:
        mysql.connector.Error: If unable to get connection
    """
    global db_pool
    if db_pool is None:
        setup_pool()
    return db_pool.get_connection()

def setup_pool(config_dict: dict = config) -> bool:
    global db_pool, db_pool_timer
    
    # Test existing pools if they exist
    if db_pool is not None and db_pool_timer is not None:
        try:
            conn = db_pool.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            
            conn = db_pool_timer.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            return True
        except mysql.connector.Error:
            logger.warning("Existing pools failed connection test - recreating...")
            db_pool = None
            db_pool_timer = None
    
    try:
        pool_config = {
            'host': config_dict['sql_host'],
            'user': config_dict['sql_user'],
            'password': config_dict['sql_password'],
            'database': config_dict['sql_database'],
            'port': config_dict['sql_port'],
            'pool_reset_session': True,
            'connect_timeout': CONNECTION_TIMEOUT
        }

        if db_pool is None:
            db_pool = MySQLConnectionPool(
                pool_name="tomibotchi_pool",
                pool_size=MAIN_POOL_SIZE,
                **pool_config
            )
            logger.info("Main connection pool created successfully")

        if db_pool_timer is None:
            db_pool_timer = MySQLConnectionPool(
                pool_name="tomibotchi_pool_timer",
                pool_size=TIMER_POOL_SIZE,
                **pool_config
            )
            logger.info("Timer connection pool created successfully")
            
        return True
        
    except mysql.connector.Error as error:
        logger.error(f"Error setting up connection pools: {error}")
        logger.error(traceback.format_exc())
        if db_pool is not None:
            db_pool = None
        if db_pool_timer is not None:
            db_pool_timer = None
        return False

def execute_query(
    query: str,
    params: Optional[Union[tuple, dict]] = None,
    is_timer: bool = False,
    retry_attempts: int = 3,
    commit: bool = False
) -> QueryResult:
    """
    Executes a database query with retry logic and connection pooling.
    
    Args:
        query: SQL query to execute
        params: Query parameters
        is_timer: Whether to use timer pool
        retry_attempts: Number of retry attempts
        commit: Whether to commit transaction
        
    Returns:
        Query results if SELECT, True if successful INSERT/UPDATE/DELETE
        
    Raises:
        mysql.connector.Error: If database error occurs after all retries
    """
    global db_pool, db_pool_timer
    
    if db_pool is None or db_pool_timer is None:
        if not setup_pool():
            logger.error("Failed to setup database pools")
            return None
            
    pool = db_pool_timer if is_timer else db_pool
    last_error = None
    
    for attempt in range(retry_attempts):
        connection = None
        cursor = None
        print("Connecting to DB with request")
        try:
            connection = pool.get_connection()
            cursor = connection.cursor()
            
            cursor.execute(query, params)
            
            if commit:
                connection.commit()
                
            if query.strip().upper().startswith('INSERT'):
                return cursor.lastrowid
                
            result = cursor.fetchall() if cursor.description else True
            return result
        except mysql.connector.Error as error:
            last_error = error
            logger.warning(
                f"Database error (attempt {attempt + 1}/{retry_attempts}): {error}\n"
                f"Query: {query}, Params: {params}"
            )
            if attempt < retry_attempts - 1:
                time.sleep(min(2 ** attempt, 10))
                
        except Exception as e:
            logger.error(f"Unexpected error executing query: {e}")
            logger.error(traceback.format_exc())
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    logger.error(
        f"Query failed after {retry_attempts} attempts. Last error: {last_error}\n"
        f"Query: {query}, Params: {params}"
    )
    raise last_error

def create_tables() -> None:
    """Creates all required database tables if they don't exist."""
    queries = [
        # Guild settings table
        """
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id BIGINT PRIMARY KEY,
            pet_channel_id BIGINT,
            update_frequency INT DEFAULT 15,
            last_updated DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            KEY idx_guild_channel (guild_id, pet_channel_id)
        )
        """,
        # Pets table
        """
        CREATE TABLE IF NOT EXISTS pets (
            pet_id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT,
            guild_id BIGINT,
            name VARCHAR(32),
            species VARCHAR(32),
            creation_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_interaction DATETIME,
            active BOOLEAN DEFAULT TRUE,
            KEY idx_user_guild (user_id, guild_id),
            KEY idx_active_pets (active, guild_id),
            FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id)
        )
        """,
        # Pet stats table
        """
        CREATE TABLE IF NOT EXISTS pet_stats (
            pet_id BIGINT PRIMARY KEY,
            happiness TINYINT DEFAULT 100,
            hunger TINYINT DEFAULT 100,
            energy TINYINT DEFAULT 100,
            hygiene TINYINT DEFAULT 100,
            last_update DATETIME,
            FOREIGN KEY (pet_id) REFERENCES pets(pet_id)
        )
        """,
        # User data table
        """
        CREATE TABLE IF NOT EXISTS user_data (
            user_id BIGINT PRIMARY KEY,
            username VARCHAR(32),
            total_pets INT DEFAULT 0,
            total_interactions INT DEFAULT 0,
            last_interaction DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
        # Interaction history table
        """
        CREATE TABLE IF NOT EXISTS interaction_history (
            interaction_id BIGINT AUTO_INCREMENT PRIMARY KEY,
            pet_id BIGINT,
            user_id BIGINT,
            interaction_type VARCHAR(32),
            interaction_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            stat_changes JSON,
            KEY idx_pet_time (pet_id, interaction_time),
            KEY idx_user_time (user_id, interaction_time),
            FOREIGN KEY (pet_id) REFERENCES pets(pet_id),
            FOREIGN KEY (user_id) REFERENCES user_data(user_id)
        )
        """
    ]
    
    for query in queries:
        execute_query(query, commit=True)
    logger.info("Database tables created successfully")

# Pet-related database functions
def create_pet(user_id: int, guild_id: int, name: str, species: str) -> Optional[int]:
    """Creates a new pet and initializes its stats."""
    try:
        with lock:
            # Create pet entry
            pet_query = """
                INSERT INTO pets (user_id, guild_id, name, species)
                VALUES (%s, %s, %s, %s)
            """
            pet_id = execute_query(
                pet_query, 
                (user_id, guild_id, name, species), 
                commit=True
            )
            
            if not pet_id:
                logger.error("Failed to create pet entry")
                return None
                
            # Initialize pet stats
            stats_query = """
                INSERT INTO pet_stats (pet_id, happiness, hunger, energy, hygiene, last_update)
                VALUES (%s, 100, 100, 100, 100, UTC_TIMESTAMP())
            """
            execute_query(stats_query, (pet_id,), commit=True)
            
            # Update user data
            user_query = """
                INSERT INTO user_data (user_id, username, total_pets)
                VALUES (%s, %s, 1)
                ON DUPLICATE KEY UPDATE 
                total_pets = total_pets + 1
            """
            execute_query(user_query, (user_id, str(user_id)), commit=True)
            
            return pet_id
            
    except Exception as e:
        logger.error(f"Database error creating pet: {e}")
        logger.error(traceback.format_exc())
        return None


def get_pet_stats(pet_id: int) -> Optional[Dict[str, Any]]:
    """Gets current stats for a pet."""
    try:
        query = """
            SELECT p.name, p.species, ps.happiness, ps.hunger, 
                   ps.energy, ps.hygiene, ps.last_update
            FROM pets p
            JOIN pet_stats ps ON p.pet_id = ps.pet_id
            WHERE p.pet_id = %s AND p.active = TRUE
        """
        result = execute_query(query, (pet_id,))
        
        if not result or not result[0]:
            logger.error(f"No stats found for pet {pet_id}")
            return None
            
        name, species, happiness, hunger, energy, hygiene, last_update = result[0]
        
        # Ensure all stats are within valid range
        stats = {
            'happiness': max(0, min(100, happiness or 100)),
            'hunger': max(0, min(100, hunger or 100)),
            'energy': max(0, min(100, energy or 100)),
            'hygiene': max(0, min(100, hygiene or 100))
        }
        
        return {
            'name': name,
            'species': species,
            'stats': stats,
            'last_update': last_update or datetime.now(timezone.utc)
        }
        
    except Exception as e:
        logger.error(f"Error getting pet stats: {e}")
        logger.error(traceback.format_exc())
        return None

def update_pet_stats(
    pet_id: int,
    stats: Dict[str, int],
    interaction_type: Optional[str] = None
) -> bool:
    """
    Updates pet stats and logs interaction if specified.
    
    Args:
        pet_id: Pet ID to update
        stats: Dictionary of stat changes
        interaction_type: Optional interaction to log
        
    Returns:
        bool: True if successful
    """
    try:
        with lock:
            # Update pet stats
            stats_query = """
                UPDATE pet_stats
                SET happiness = %s,
                    hunger = %s,
                    energy = %s,
                    hygiene = %s,
                    last_update = UTC_TIMESTAMP()
                WHERE pet_id = %s
            """
            stats_params = (
                stats['happiness'],
                stats['hunger'],
                stats['energy'],
                stats['hygiene'],
                pet_id
            )
            execute_query(stats_query, stats_params, commit=True)
            
            # Log interaction if specified
            if interaction_type:
                interaction_query = """
                    INSERT INTO interaction_history
                    (pet_id, user_id, interaction_type, stat_changes)
                    SELECT %s, user_id, %s, %s
                    FROM pets WHERE pet_id = %s
                """
                interaction_params = (
                    pet_id,
                    interaction_type,
                    str(stats),
                    pet_id
                )
                execute_query(interaction_query, interaction_params, commit=True)
                
            return True
            
    except Exception as e:
        logger.error(f"Error updating pet stats: {e}")
        logger.error(traceback.format_exc())
        return False

# Initialize pools and tables on module load
if setup_pool():
    logger.info('Connection pools set up successfully')
    create_tables()
else:
    logger.error('Error setting up connection pools')