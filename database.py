import aiosqlite
import asyncpg
import logging
import asyncio
from typing import List, Optional, Tuple
from config import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    _instance: Optional['DatabaseManager'] = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_path: str = settings.DATABASE_PATH, db_url: str = settings.DATABASE_URL):
        if not hasattr(self, 'initialized'):
            self.db_path = db_path
            self.db_url = db_url
            self.is_postgres = bool(db_url)
            self.pg_pool: Optional[asyncpg.Pool] = None
            self.initialized = True

    async def init_db(self):
        """Инициализация базы данных (PostgreSQL или SQLite) и создание таблиц."""
        if self.is_postgres:
            logger.info("Инициализация базы данных PostgreSQL...")
            # Исправляем формат схемы в строке URL (иногда Render выдает postgres:// вместо postgresql://)
            if self.db_url.startswith("postgres://"):
                self.db_url = self.db_url.replace("postgres://", "postgresql://", 1)
                
            self.pg_pool = await asyncpg.create_pool(self.db_url)
            async with self.pg_pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS admins (
                        telegram_id BIGINT PRIMARY KEY
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        key VARCHAR(255) PRIMARY KEY,
                        value TEXT
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS proxies (
                        proxy VARCHAR(255) PRIMARY KEY,
                        status INTEGER DEFAULT 1
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS seen_items (
                        item_id VARCHAR(255) PRIMARY KEY,
                        found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
        else:
            logger.info("Инициализация базы данных SQLite...")
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS admins (
                        telegram_id INTEGER PRIMARY KEY
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS proxies (
                        proxy TEXT PRIMARY KEY,
                        status INTEGER DEFAULT 1
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS seen_items (
                        item_id TEXT PRIMARY KEY,
                        found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                await db.commit()

        # Добавляем первого администратора
        await self.add_admin(settings.FIRST_ADMIN_ID)

        # Инициализация дефолтных настроек
        default_settings = {
            "max_price_usd": str(settings.DEFAULT_MAX_PRICE_USD),
            "keywords": settings.DEFAULT_KEYWORDS,
            "interval_minutes": str(settings.DEFAULT_PARSE_INTERVAL_MINUTES),
            "monitoring_enabled": "1"
        }

        for key, val in default_settings.items():
            if self.is_postgres:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING",
                        key, val
                    )
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                        (key, val)
                    )
                    await db.commit()
                    
        logger.info("База данных успешно инициализирована.")

    # --- Управление администраторами ---
    async def add_admin(self, telegram_id: int) -> bool:
        try:
            if self.is_postgres:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO admins (telegram_id) VALUES ($1) ON CONFLICT (telegram_id) DO NOTHING",
                        telegram_id
                    )
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute("INSERT OR IGNORE INTO admins (telegram_id) VALUES (?)", (telegram_id,))
                    await db.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка при добавлении админа {telegram_id}: {e}")
            return False

    async def remove_admin(self, telegram_id: int) -> bool:
        if telegram_id == settings.FIRST_ADMIN_ID:
            logger.warning("Попытка удалить главного администратора заблокирована.")
            return False
        try:
            if self.is_postgres:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute("DELETE FROM admins WHERE telegram_id = $1", telegram_id)
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute("DELETE FROM admins WHERE telegram_id = ?", (telegram_id,))
                    await db.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении админа {telegram_id}: {e}")
            return False

    async def get_admins(self) -> List[int]:
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                rows = await conn.fetch("SELECT telegram_id FROM admins")
                return [row['telegram_id'] for row in rows]
        else:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT telegram_id FROM admins") as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]

    async def is_admin(self, telegram_id: int) -> bool:
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                val = await conn.fetchval("SELECT 1 FROM admins WHERE telegram_id = $1", telegram_id)
                return val is not None
        else:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT 1 FROM admins WHERE telegram_id = ?", (telegram_id,)) as cursor:
                    return await cursor.fetchone() is not None

    # --- Управление настройками ---
    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                val = await conn.fetchval("SELECT value FROM settings WHERE key = $1", key)
                return val if val is not None else default
        else:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else default

    async def set_setting(self, key: str, value: str):
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    key, value
                )
        else:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (key, value)
                )
                await db.commit()

    # --- Управление прокси ---
    async def add_proxy(self, proxy_str: str) -> bool:
        try:
            if self.is_postgres:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO proxies (proxy, status) VALUES ($1, 1) ON CONFLICT (proxy) DO NOTHING",
                        proxy_str
                    )
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute("INSERT OR IGNORE INTO proxies (proxy, status) VALUES (?, 1)", (proxy_str,))
                    await db.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка при добавлении прокси {proxy_str}: {e}")
            return False

    async def get_all_proxies(self) -> List[Tuple[str, int]]:
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                rows = await conn.fetch("SELECT proxy, status FROM proxies")
                return [(row['proxy'], row['status']) for row in rows]
        else:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT proxy, status FROM proxies") as cursor:
                    return await cursor.fetchall()

    async def get_active_proxies(self) -> List[str]:
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                rows = await conn.fetch("SELECT proxy FROM proxies WHERE status = 1")
                return [row['proxy'] for row in rows]
        else:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT proxy FROM proxies WHERE status = 1") as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]

    async def update_proxy_status(self, proxy_str: str, status: int):
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                await conn.execute("UPDATE proxies SET status = $1 WHERE proxy = $2", status, proxy_str)
        else:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("UPDATE proxies SET status = ? WHERE proxy = ?", (status, proxy_str))
                await db.commit()

    async def delete_proxy(self, proxy_str: str):
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                await conn.execute("DELETE FROM proxies WHERE proxy = $1", proxy_str)
        else:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM proxies WHERE proxy = ?", (proxy_str,))
                await db.commit()

    async def delete_dead_proxies(self):
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                await conn.execute("DELETE FROM proxies WHERE status = 0")
        else:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM proxies WHERE status = 0")
                await db.commit()

    # --- История найденных товаров (seen_items) ---
    async def is_item_seen(self, item_id: str) -> bool:
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                val = await conn.fetchval("SELECT 1 FROM seen_items WHERE item_id = $1", item_id)
                return val is not None
        else:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT 1 FROM seen_items WHERE item_id = ?", (item_id,)) as cursor:
                    return await cursor.fetchone() is not None

    async def add_seen_item(self, item_id: str):
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO seen_items (item_id) VALUES ($1) ON CONFLICT (item_id) DO NOTHING",
                    item_id
                )
        else:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("INSERT OR IGNORE INTO seen_items (item_id) VALUES (?)", (item_id,))
                await db.commit()

# Экземпляр синглтона базы данных
db_manager = DatabaseManager()
