# TomibotchiDiscordBot

A multiplayer virtual pet Discord bot that lets users raise and interact with their digital pets in a social environment. Similar to Tamagotchi, but with multiplayer features and Discord integration.

## 🌟 Features

- Create and manage multiple virtual pets
- Real-time pet stat tracking (hunger, happiness, energy, hygiene)
- Interactive pet care commands
- Pet state management (normal, sleeping, sick, unhappy)
- Multiplayer interactions
- Persistent pet data storage
- Cooldown system for interactions
- Detailed pet statistics tracking

## 📁 Project Structure

```plaintext
tomibotchiDiscordBot/
├── code/
│   ├── bot_code/
│   │   ├── commands/         # Discord bot commands
│   │   │   └── commands.py   # Main command implementations
│   │   └── game/            # Core game logic
│   │       ├── state.py     # Pet state management
│   │       ├── cache.py     # Data caching
│   │       └── interaction.py # Pet interaction logic
│   ├── database/           # Database operations
│   │   └── database.py     # Database queries and management
│   └── requirements.txt    # Project dependencies
└── README.md
```

## 🔄 Data Flow & Component Interaction

1. **Command Layer** (`commands.py`)
   - Handles Discord user interactions
   - Validates user input
   - Manages command cooldowns
   - Routes commands to appropriate game logic

2. **Game Logic Layer** (`game/`)
   - `state.py`: Manages pet states and transitions
   - `interaction.py`: Processes pet interactions and effects
   - `cache.py`: Handles in-memory caching of pet data

3. **Database Layer** (`database.py`)
   - Manages persistent storage
   - Handles CRUD operations for pets and interactions
   - Maintains interaction history

## 🛠 Technical Components

### State Management
- Uses enum-based state system (`PetStatus`)
- Implements atomic operations for thread safety
- Manages pet stats with bounds checking
- Handles state transitions based on pet conditions

### Interaction System
- Defines various interaction types (feed, clean, sleep, etc.)
- Implements cooldown mechanics
- Calculates interaction effects on pet stats
- Validates interaction conditions

### Database Integration
- MySQL-based persistent storage
- Asynchronous database operations
- Transaction management
- Data validation and sanitization

## 🚀 Getting Started

1. **Prerequisites**
   - Python 3.8+
   - MySQL database
   - Discord Bot Token

2. **Installation**
```bash
git clone <repository-url>
cd tomibotchiDiscordBot
pip install -r code/requirements.txt
```

3. **Configuration**
   - Create a `.env` file with your Discord token and database credentials
   - Configure database connection settings

4. **Running the Bot**
```bash
python main.py
```

## 🎮 Basic Commands

- `!create <name> <species>` - Create a new pet
- `!show [pet_name]` - Display pet status
- `!feed <pet_name>` - Feed your pet
- `!clean <pet_name>` - Clean your pet
- `!sleep <pet_name>` - Put your pet to sleep
- `!play <pet_name>` - Play with your pet
- `!stats <pet_name>` - View detailed pet statistics

## 🔒 Security Features

- Input validation and sanitization
- Rate limiting on commands
- Atomic operations for thread safety
- Secure database connections
- Permission-based command access

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.