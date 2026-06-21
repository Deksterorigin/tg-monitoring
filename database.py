import aiosqlite
import logging
import asyncio
from typing import List, Optional, Tuple
from config import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    _instance: Optional['DatabaseManager'] = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_path: str = settings.DATABASE_PATH):
        if not hasattr(self, 'initialized'):
            self.db_path = db_path
            self._conn: Optional[aiosqlite.Connection] = None
            self._lock = asyncio.Lock()
            self.initialized = True

    async def _get_conn(self) -> aiosqlite.Connection:
        """Возвращает персистентное соединение с БД (создаёт при первом вызове)."""
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path)
            await self._conn.execute("PRAGMA journal_mode=WAL;")
            await self._conn.execute("PRAGMA synchronous=NORMAL;")
            # WAL + NORMAL = быстрее и меньше блокировок
        return self._conn

    async def close(self):
        """Закрывает персистентное соединение."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def init_db(self):
        """Инициализация базы данных SQLite и создание таблиц."""
        logger.info("Инициализация базы данных SQLite...")
        async with self._lock:
            db = await self._get_conn()
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

        # Инициализация дефолтных настроек (одним батчем)
        default_settings = {
            "minus_words": "",
            "min_price_usd": "0.0",
            "max_price_usd": str(settings.DEFAULT_MAX_PRICE_USD),
            "min_reviews": "10",
            "keywords": settings.DEFAULT_KEYWORDS,
            "interval_minutes": str(settings.DEFAULT_PARSE_INTERVAL_MINUTES),
            "monitoring_enabled": "1",
            "dnd_enabled": "0",
            "dnd_start": "23:00",
            "dnd_end": "08:00"
        }

        async with self._lock:
            db = await self._get_conn()
            for key, val in default_settings.items():
                await db.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (key, val)
                )
            await db.commit()

        # Чистим старые seen_items (старше 7 дней) для экономии памяти
        await self.cleanup_seen_items()
                
        logger.info("База данных успешно инициализирована.")

    async def cleanup_seen_items(self, days: int = 7):
        """Удаляет старые записи из seen_items для экономии памяти БД."""
        try:
            async with self._lock:
                db = await self._get_conn()
                result = await db.execute(
                    "DELETE FROM seen_items WHERE found_at < datetime('now', ?)",
                    (f'-{days} days',)
                )
                await db.commit()
                logger.info(f"Очистка seen_items: удалено {result.rowcount} записей старше {days} дней.")
        except Exception as e:
            logger.error(f"Ошибка при очистке seen_items: {e}")

    # --- Управление администраторами ---
    async def add_admin(self, telegram_id: int) -> bool:
        try:
            async with self._lock:
                db = await self._get_conn()
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
            async with self._lock:
                db = await self._get_conn()
                await db.execute("DELETE FROM admins WHERE telegram_id = ?", (telegram_id,))
                await db.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении админа {telegram_id}: {e}")
            return False

    async def get_admins(self) -> List[int]:
        try:
            async with self._lock:
                db = await self._get_conn()
                async with db.execute("SELECT telegram_id FROM admins") as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении списка админов: {e}")
            return [settings.FIRST_ADMIN_ID]

    async def is_admin(self, telegram_id: int) -> bool:
        try:
            async with self._lock:
                db = await self._get_conn()
                async with db.execute("SELECT 1 FROM admins WHERE telegram_id = ?", (telegram_id,)) as cursor:
                    return await cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Ошибка при проверке админа {telegram_id}: {e}")
            return telegram_id == settings.FIRST_ADMIN_ID

    # --- Управление настройками ---
    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            async with self._lock:
                db = await self._get_conn()
                async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else default
        except Exception as e:
            logger.error(f"Ошибка при получении настройки {key}: {e}")
            return default

    async def set_setting(self, key: str, value: str):
        try:
            async with self._lock:
                db = await self._get_conn()
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (key, value)
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Ошибка при сохранении настройки {key}: {e}")

    async def set_latest_snapshot(self, snapshot_json: str):
        old_snapshot = await self.get_latest_snapshot()
        if old_snapshot:
            await self.set_setting("previous_snapshot", old_snapshot)
        await self.set_setting("latest_snapshot", snapshot_json)

    async def get_latest_snapshot(self) -> Optional[str]:
        return await self.get_setting("latest_snapshot", None)

    # --- Управление прокси ---
    async def add_proxy(self, proxy_str: str) -> bool:
        try:
            async with self._lock:
                db = await self._get_conn()
                await db.execute("INSERT OR IGNORE INTO proxies (proxy, status) VALUES (?, 1)", (proxy_str,))
                await db.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка при добавлении прокси {proxy_str}: {e}")
            return False

    async def get_all_proxies(self) -> List[Tuple[str, int]]:
        try:
            async with self._lock:
                db = await self._get_conn()
                async with db.execute("SELECT proxy, status FROM proxies") as cursor:
                    return await cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка при получении списка прокси: {e}")
            return []

    async def get_active_proxies(self) -> List[str]:
        try:
            async with self._lock:
                db = await self._get_conn()
                async with db.execute("SELECT proxy FROM proxies WHERE status = 1") as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении активных прокси: {e}")
            return []

    async def update_proxy_status(self, proxy_str: str, status: int):
        try:
            async with self._lock:
                db = await self._get_conn()
                await db.execute("UPDATE proxies SET status = ? WHERE proxy = ?", (status, proxy_str))
                await db.commit()
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса прокси {proxy_str}: {e}")

    async def delete_proxy(self, proxy_str: str):
        try:
            async with self._lock:
                db = await self._get_conn()
                await db.execute("DELETE FROM proxies WHERE proxy = ?", (proxy_str,))
                await db.commit()
        except Exception as e:
            logger.error(f"Ошибка при удалении прокси {proxy_str}: {e}")

    async def delete_dead_proxies(self):
        try:
            async with self._lock:
                db = await self._get_conn()
                await db.execute("DELETE FROM proxies WHERE status = 0")
                await db.commit()
        except Exception as e:
            logger.error(f"Ошибка при удалении мертвых прокси: {e}")

    # --- История найденных товаров (seen_items) ---
    async def is_item_seen(self, item_id: str) -> bool:
        try:
            async with self._lock:
                db = await self._get_conn()
                async with db.execute("SELECT 1 FROM seen_items WHERE item_id = ?", (item_id,)) as cursor:
                    return await cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Ошибка при проверке просмотренного товара {item_id}: {e}")
            return False

    async def add_seen_item(self, item_id: str):
        try:
            async with self._lock:
                db = await self._get_conn()
                await db.execute("INSERT OR IGNORE INTO seen_items (item_id) VALUES (?)", (item_id,))
                await db.commit()
        except Exception as e:
            logger.error(f"Ошибка при добавлении просмотренного товара {item_id}: {e}")

# Экземпляр синглтона базы данных
db_manager = DatabaseManager()
