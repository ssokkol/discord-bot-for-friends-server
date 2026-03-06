import aiosqlite
import asyncio
from typing import Optional, Tuple, List
import logging

logger = logging.getLogger(__name__)

MIGRATIONS = [
    # Migration 1: Level system, daily, shop, transactions, twitch, settings
    [
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);",
        "CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);",
        # Level system columns on users
        "ALTER TABLE users ADD COLUMN xp INTEGER DEFAULT 0;",
        "ALTER TABLE users ADD COLUMN level INTEGER DEFAULT 0;",
        "CREATE TABLE IF NOT EXISTS level_roles (level INTEGER PRIMARY KEY, role_id INTEGER NOT NULL);",
        # Daily bonus columns on users
        "ALTER TABLE users ADD COLUMN last_daily TIMESTAMP;",
        "ALTER TABLE users ADD COLUMN daily_streak INTEGER DEFAULT 0;",
        # Shop
        """CREATE TABLE IF NOT EXISTS shop_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, description TEXT,
            category TEXT NOT NULL,
            price INTEGER NOT NULL,
            item_data TEXT,
            is_active INTEGER DEFAULT 1
        );""",
        """CREATE TABLE IF NOT EXISTS user_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, item_id INTEGER NOT NULL,
            purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES shop_items(id)
        );""",
        """CREATE TABLE IF NOT EXISTS user_equipment (
            user_id INTEGER PRIMARY KEY,
            background_id INTEGER, badge_id INTEGER
        );""",
        # Transactions
        """CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );""",
        # Twitch
        """CREATE TABLE IF NOT EXISTS twitch_streamers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL, twitch_id TEXT,
            is_live INTEGER DEFAULT 0, last_stream_id TEXT, added_by INTEGER
        );""",
        """CREATE TABLE IF NOT EXISTS drops_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_name TEXT UNIQUE NOT NULL, twitch_game_id TEXT, added_by INTEGER
        );""",
    ],
    # Migration 2: (removed - was shop seed items, kept as empty for schema_version compat)
    [],
]


class DatabaseManager:
    """Database manager for the Discord bot"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = asyncio.Lock()

    async def _init_database(self):
        """Initialize the database with required tables"""
        import os
        import stat
        try:
            if not os.path.isabs(self.db_path):
                self.db_path = os.path.abspath(self.db_path)

            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            if os.path.exists(self.db_path) and os.path.isdir(self.db_path):
                logger.warning(f"Path {self.db_path} is a directory, using data/club.db")
                data_dir = self.db_path
                self.db_path = os.path.join(data_dir, 'club.db')

            if not os.path.exists(self.db_path):
                try:
                    with open(self.db_path, 'wb') as f:
                        pass
                    try:
                        os.chmod(self.db_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"Failed to create DB file {self.db_path}: {e}")
                    raise

            if os.path.isdir(self.db_path):
                raise Exception(f"Path {self.db_path} is a directory, not a file")

            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER UNIQUE NOT NULL,
                        messages INTEGER DEFAULT 0,
                        voice_time INTEGER DEFAULT 0,
                        money INTEGER DEFAULT 0
                    )
                ''')
                await conn.commit()
                logger.info(f"Database initialized: {self.db_path}")

            await self._run_migrations()

        except Exception as e:
            logger.error(f"Database init error {self.db_path}: {e}")
            raise

    async def _run_migrations(self):
        """Run pending database migrations"""
        async with aiosqlite.connect(self.db_path) as conn:
            # Ensure schema_version table exists
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
            )
            await conn.commit()

            # Get current version
            async with conn.execute("SELECT MAX(version) FROM schema_version") as cursor:
                row = await cursor.fetchone()
                current_version = row[0] if row and row[0] is not None else 0

            # Apply pending migrations
            for i, migration_statements in enumerate(MIGRATIONS, 1):
                if i <= current_version:
                    continue
                logger.info(f"Applying migration {i}...")
                for stmt in migration_statements:
                    try:
                        await conn.execute(stmt)
                    except Exception as e:
                        # Ignore "duplicate column" errors from ALTER TABLE
                        if "duplicate column" in str(e).lower():
                            continue
                        logger.warning(f"Migration {i} statement warning: {e}")
                await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (i,))
                await conn.commit()
                logger.info(f"Migration {i} applied successfully")

    async def execute_query(self, query: str, params: tuple = ()) -> bool:
        """Execute a SQL query with locking"""
        async with self._lock:
            try:
                if not hasattr(self, '_initialized'):
                    try:
                        await self._init_database()
                        self._initialized = True
                    except Exception as e:
                        logger.error(f"Critical DB init error: {e}")
                        return False

                async with aiosqlite.connect(self.db_path) as conn:
                    await conn.execute(query, params)
                    await conn.commit()
                    return True
            except Exception as e:
                logger.error(f"Query error: {e}")
                return False

    async def fetch_one(self, query: str, params: tuple = ()) -> Optional[tuple]:
        """Fetch a single record"""
        async with self._lock:
            try:
                if not hasattr(self, '_initialized'):
                    try:
                        await self._init_database()
                        self._initialized = True
                    except Exception as e:
                        logger.error(f"Critical DB init error: {e}")
                        return None

                async with aiosqlite.connect(self.db_path) as conn:
                    async with conn.execute(query, params) as cursor:
                        return await cursor.fetchone()
            except Exception as e:
                logger.error(f"Fetch one error: {e}")
                return None

    async def fetch_all(self, query: str, params: tuple = ()) -> List[tuple]:
        """Fetch all records"""
        async with self._lock:
            try:
                if not hasattr(self, '_initialized'):
                    try:
                        await self._init_database()
                        self._initialized = True
                    except Exception as e:
                        logger.error(f"Critical DB init error: {e}")
                        return []

                async with aiosqlite.connect(self.db_path) as conn:
                    async with conn.execute(query, params) as cursor:
                        return await cursor.fetchall()
            except Exception as e:
                logger.error(f"Fetch all error: {e}")
                return []


class UserDatabase:
    """User database operations"""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def user_exists(self, user_id: int) -> bool:
        result = await self.db.fetch_one(
            "SELECT `id` FROM `users` WHERE `user_id` = ?",
            (user_id,)
        )
        return bool(result)

    async def add_user(self, user_id: int) -> bool:
        try:
            await self.db.execute_query(
                "INSERT INTO `users` (user_id, messages, voice_time, money) VALUES (?,?,?,?)",
                (user_id, 0, 0, 0)
            )
            return True
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False

    async def get_messages(self, user_id: int) -> int:
        result = await self.db.fetch_one(
            "SELECT `messages` FROM `users` WHERE `user_id` = ?",
            (user_id,)
        )
        return result[0] if result else 0

    async def add_message(self, user_id: int, count: int = 1) -> bool:
        try:
            await self.db.execute_query(
                "UPDATE `users` SET `messages` = messages + ? WHERE user_id = ?",
                (count, user_id)
            )
            return True
        except Exception as e:
            logger.error(f"Error adding messages: {e}")
            return False

    async def get_voice_time(self, user_id: int) -> int:
        result = await self.db.fetch_one(
            "SELECT `voice_time` FROM `users` WHERE `user_id` = ?",
            (user_id,)
        )
        return result[0] if result else 0

    async def add_voice_time(self, user_id: int, minutes: int) -> bool:
        try:
            await self.db.execute_query(
                "UPDATE `users` SET `voice_time` = voice_time + ? WHERE user_id = ?",
                (minutes, user_id)
            )
            return True
        except Exception as e:
            logger.error(f"Error adding voice time: {e}")
            return False


class TopDatabase:
    """Leaderboard database operations"""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def get_voice_top(self, limit: int = 5) -> List[Tuple[int, int]]:
        return await self.db.fetch_all(
            "SELECT user_id, voice_time FROM users ORDER BY voice_time DESC LIMIT ?",
            (limit,)
        )

    async def get_messages_top(self, limit: int = 5) -> List[Tuple[int, int]]:
        return await self.db.fetch_all(
            "SELECT user_id, messages FROM users ORDER BY messages DESC LIMIT ?",
            (limit,)
        )

    async def get_level_top(self, limit: int = 10, offset: int = 0) -> List[Tuple[int, int, int]]:
        """Get top users by level. Returns (user_id, level, xp)."""
        return await self.db.fetch_all(
            "SELECT user_id, level, xp FROM users ORDER BY level DESC, xp DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )


class LevelDatabase:
    """Level/XP database operations"""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def get_xp_level(self, user_id: int) -> Tuple[int, int]:
        """Returns (xp, level)"""
        result = await self.db.fetch_one(
            "SELECT xp, level FROM users WHERE user_id = ?",
            (user_id,)
        )
        if result:
            return result[0] or 0, result[1] or 0
        return 0, 0

    async def set_xp_level(self, user_id: int, xp: int, level: int) -> bool:
        return await self.db.execute_query(
            "UPDATE users SET xp = ?, level = ? WHERE user_id = ?",
            (xp, level, user_id)
        )

    async def get_rank_position(self, user_id: int) -> int:
        result = await self.db.fetch_one(
            "SELECT COUNT(*) FROM users WHERE level > (SELECT level FROM users WHERE user_id = ?) OR "
            "(level = (SELECT level FROM users WHERE user_id = ?) AND xp > (SELECT xp FROM users WHERE user_id = ?))",
            (user_id, user_id, user_id)
        )
        return (result[0] + 1) if result else 1

    async def get_level_roles(self) -> List[Tuple[int, int]]:
        """Returns list of (level, role_id)"""
        return await self.db.fetch_all("SELECT level, role_id FROM level_roles ORDER BY level")

    async def set_level_role(self, level: int, role_id: int) -> bool:
        return await self.db.execute_query(
            "INSERT OR REPLACE INTO level_roles (level, role_id) VALUES (?, ?)",
            (level, role_id)
        )

    async def remove_level_role(self, level: int) -> bool:
        return await self.db.execute_query(
            "DELETE FROM level_roles WHERE level = ?",
            (level,)
        )

    async def get_daily_info(self, user_id: int) -> Tuple[Optional[str], int]:
        """Returns (last_daily, daily_streak)"""
        result = await self.db.fetch_one(
            "SELECT last_daily, daily_streak FROM users WHERE user_id = ?",
            (user_id,)
        )
        if result:
            return result[0], result[1] or 0
        return None, 0

    async def set_daily_info(self, user_id: int, last_daily: str, streak: int) -> bool:
        return await self.db.execute_query(
            "UPDATE users SET last_daily = ?, daily_streak = ? WHERE user_id = ?",
            (last_daily, streak, user_id)
        )


class SettingsDatabase:
    """Bot settings key-value store"""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def get(self, key: str) -> Optional[str]:
        result = await self.db.fetch_one(
            "SELECT value FROM bot_settings WHERE key = ?",
            (key,)
        )
        return result[0] if result else None

    async def set(self, key: str, value: str) -> bool:
        return await self.db.execute_query(
            "INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)",
            (key, value)
        )

    async def delete(self, key: str) -> bool:
        return await self.db.execute_query(
            "DELETE FROM bot_settings WHERE key = ?",
            (key,)
        )

    async def get_all(self) -> dict:
        rows = await self.db.fetch_all("SELECT key, value FROM bot_settings")
        return {k: v for k, v in rows}


class TwitchDatabase:
    """Twitch database operations"""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def add_streamer(self, username: str, twitch_id: str = None, added_by: int = None) -> bool:
        return await self.db.execute_query(
            "INSERT OR IGNORE INTO twitch_streamers (username, twitch_id, added_by) VALUES (?, ?, ?)",
            (username.lower(), twitch_id, added_by)
        )

    async def remove_streamer(self, username: str) -> bool:
        return await self.db.execute_query(
            "DELETE FROM twitch_streamers WHERE username = ?",
            (username.lower(),)
        )

    async def get_streamers(self) -> List[tuple]:
        return await self.db.fetch_all(
            "SELECT id, username, twitch_id, is_live, last_stream_id FROM twitch_streamers"
        )

    async def set_live_status(self, username: str, is_live: bool, stream_id: str = None) -> bool:
        return await self.db.execute_query(
            "UPDATE twitch_streamers SET is_live = ?, last_stream_id = ? WHERE username = ?",
            (1 if is_live else 0, stream_id, username.lower())
        )

    async def add_drops_game(self, game_name: str, twitch_game_id: str = None, added_by: int = None) -> bool:
        return await self.db.execute_query(
            "INSERT OR IGNORE INTO drops_games (game_name, twitch_game_id, added_by) VALUES (?, ?, ?)",
            (game_name, twitch_game_id, added_by)
        )

    async def remove_drops_game(self, game_name: str) -> bool:
        return await self.db.execute_query(
            "DELETE FROM drops_games WHERE game_name = ?",
            (game_name,)
        )

    async def get_drops_games(self) -> List[tuple]:
        return await self.db.fetch_all(
            "SELECT id, game_name, twitch_game_id FROM drops_games"
        )
