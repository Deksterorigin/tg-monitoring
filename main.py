import asyncio
import logging
import sys
from bot_instance import bot, dp
from database import db_manager
from scheduler_instance import scheduler
from keep_alive import start_web_server, self_ping
from services.monitor import run_monitoring_cycle
from bot.middlewares.db_middleware import DatabaseMiddleware

# Импортируем роутеры
from bot.handlers.admin import router as admin_router
from bot.handlers.settings import router as settings_router
from bot.handlers.interval import router as interval_router
from bot.handlers.proxies import router as proxies_router
from bot.handlers.admins_mgmt import router as admins_router
from bot.handlers.backup import router as backup_router

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Запуск инициализации бота...")
    
    # 1. Инициализируем базу данных
    await db_manager.init_db()
    
    # 2. Регистрируем middleware
    dp.update.outer_middleware(DatabaseMiddleware())
    
    # 3. Регистрируем роутеры
    dp.include_router(admin_router)
    dp.include_router(settings_router)
    dp.include_router(interval_router)
    dp.include_router(proxies_router)
    dp.include_router(admins_router)
    dp.include_router(backup_router)

    # 4. Настраиваем планировщик фоновых задач
    interval_setting = await db_manager.get_setting("interval_minutes", "60")
    try:
        interval_minutes = int(interval_setting)
    except ValueError:
        interval_minutes = 60

    # Задача для парсинга маркетплейсов
    # ВАЖНО: первый запуск через 30 секунд (чтобы бот успел инициализироваться),
    # дальше — по интервалу. НЕ используем create_task, чтобы исключить
    # параллельный запуск двух циклов и двойное потребление памяти Chromium.
    from datetime import datetime, timedelta
    scheduler.add_job(
        run_monitoring_cycle,
        "interval",
        minutes=interval_minutes,
        id="monitoring_job",
        next_run_time=datetime.now() + timedelta(seconds=30)
    )
    
    # Настраиваем задачу утреннего дайджеста
    from services.digest import update_digest_job
    await update_digest_job()
    
    # Задача self-ping (каждые 5 минут для Render)
    scheduler.add_job(
        self_ping,
        "interval",
        minutes=5,
        id="self_ping_job"
    )
    
    scheduler.start()
    logger.info("Планировщик APScheduler успешно запущен.")

    # 5. Запускаем keep-alive веб-сервер
    web_runner = await start_web_server()

    try:
        # 6. Запуск polling бота
        logger.info("Бот запущен и готов к работе.")
        await dp.start_polling(bot)
    finally:
        # Очистка ресурсов при выключении
        logger.info("Остановка планировщика и веб-сервера...")
        scheduler.shutdown()
        await db_manager.close()
        await web_runner.cleanup()
        await bot.session.close()
        logger.info("Бот полностью остановлен.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен пользователем.")
