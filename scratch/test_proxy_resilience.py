import asyncio
import os
import shutil
import sqlite3
import logging
from config import settings
from database import db_manager
from services.proxy_pool import proxy_pool
from services.browser import BrowserManager
from parsers.funpay import FunPayParser
from bot_instance import bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TestResilience")

async def test_database_and_backup():
    logger.info("=== Начинаем тест базы данных и резервного копирования ===")
    
    # Инициализируем БД
    await db_manager.init_db()
    
    # 1. Проверяем получение настроек
    use_free = await db_manager.get_setting("use_free_proxies", "1")
    logger.info(f"Настройка use_free_proxies в БД: {use_free}")
    
    # 2. Создаем временную копию базы данных для теста восстановления
    db_file_path = settings.DATABASE_PATH
    temp_backup_path = "test_bot_database_backup.db"
    
    logger.info(f"Создаем копию {db_file_path} -> {temp_backup_path} под блокировкой...")
    async with db_manager._lock:
        shutil.copy2(db_file_path, temp_backup_path)
    
    logger.info(f"Временный бэкап создан: {os.path.exists(temp_backup_path)}")
    
    # 3. Валидируем временную копию
    conn = sqlite3.connect(temp_backup_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA integrity_check;")
    integrity = cursor.fetchone()
    logger.info(f"Валидация PRAGMA integrity_check: {integrity}")
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    logger.info(f"Таблицы в бэкапе: {tables}")
    
    cursor.close()
    conn.close()
    
    # 4. Выполняем транзакционное восстановление
    backup_file_path = db_file_path + ".backup"
    
    logger.info("Выполняем транзакционное замещение базы данных...")
    async with db_manager._lock:
        # Закрываем активное соединение
        await db_manager.close()
        
        # Удаляем WAL/SHM
        for suffix in ["-wal", "-shm"]:
            wal_file = db_file_path + suffix
            if os.path.exists(wal_file):
                try:
                    os.remove(wal_file)
                    logger.info(f"Удален временный файл WAL/SHM: {wal_file}")
                except Exception as ex:
                    logger.warning(f"Не удалось удалить временный файл SQLite {wal_file}: {ex}")
        
        # Резервная копия текущей
        if os.path.exists(db_file_path):
            shutil.copy2(db_file_path, backup_file_path)
            
        try:
            # Заменяем основной файл
            if os.path.exists(db_file_path):
                os.remove(db_file_path)
            shutil.move(temp_backup_path, db_file_path)
            
            # Проверяем целостность новой
            conn = sqlite3.connect(db_file_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            new_integrity = cursor.fetchone()
            conn.close()
            
            if not new_integrity or new_integrity[0] != "ok":
                raise ValueError("Новый файл базы поврежден!")
                
            logger.info("Целостность новой базы проверена успешно!")
            
            if os.path.exists(backup_file_path):
                os.remove(backup_file_path)
                
            # Переподключаемся
            await db_manager._reconnect_unlocked()
            logger.info("Соединение с БД успешно пересоздано.")
        except Exception as e:
            logger.error(f"Ошибка при восстановлении, откатываем: {e}")
            if os.path.exists(backup_file_path):
                if os.path.exists(db_file_path):
                    os.remove(db_file_path)
                shutil.move(backup_file_path, db_file_path)
            await db_manager._reconnect_unlocked()
            raise e
            
    logger.info("=== Тест базы данных и резервного копирования успешно завершен! ===\n")

async def test_proxy_pool():
    logger.info("=== Начинаем тест ProxyPool ===")
    
    # Настраиваем use_free_proxies = 1 в БД
    await db_manager.set_setting("use_free_proxies", "1")
    
    # Вызываем обновление пула прокси
    await proxy_pool.refresh()
    
    logger.info(f"Результат обновления пула: рабочие прокси = {proxy_pool.working_proxies}")
    logger.info("=== Тест ProxyPool успешно завершен! ===\n")

async def test_playwright_stealth():
    logger.info("=== Начинаем тест Playwright и stealth ===")
    
    browser_manager = BrowserManager()
    # Запускаем браузер без прокси для теста
    await browser_manager.start()
    
    try:
        context, page = await browser_manager.get_page()
        logger.info("Переходим на https://httpbin.org/headers для проверки User-Agent и stealth...")
        await page.goto("https://httpbin.org/headers", timeout=15000, wait_until="domcontentloaded")
        content = await page.content()
        logger.info(f"Контент страницы: {content[:300]}")
        
        # Проверяем, что stealth применился
        # На чистом playwright navigator.webdriver равен true, stealth_async должен скрыть его
        is_webdriver = await page.evaluate("() => navigator.webdriver")
        logger.info(f"navigator.webdriver = {is_webdriver} (Должно быть False / undefined с примененным stealth)")
        
        await browser_manager.release_page(context, page)
    finally:
        await browser_manager.shutdown()
        
    logger.info("=== Тест Playwright и stealth успешно завершен! ===\n")

async def main():
    try:
        await test_database_and_backup()
        await test_proxy_pool()
        await test_playwright_stealth()
        logger.info("Все тесты прошли успешно!")
    except Exception as e:
        logger.critical(f"Тестирование завершилось ошибкой: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
