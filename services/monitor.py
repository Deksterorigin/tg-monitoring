import logging
import asyncio
import gc
from typing import List
from bot_instance import bot
from database import db_manager
from parsers.base import ParsedItem
from parsers.funpay import FunPayParser
from parsers.plati import PlatiParser
from parsers.ggsel import GGSelParser
from parsers.playerok import PlayerokParser

logger = logging.getLogger(__name__)

# Инициализируем парсеры: сначала лёгкие (HTTP), потом тяжёлые (Playwright)
# Это позволяет минимизировать пиковое потребление памяти
PARSERS = [
    PlatiParser(),     # HTTP-парсер (лёгкий)
    GGSelParser(),     # HTTP-парсер (лёгкий)
    FunPayParser(),    # Playwright (тяжёлый) — запускается после лёгких
    PlayerokParser()   # Playwright (тяжёлый) — запускается последним
]

# Парсеры, использующие Playwright (требуют gc.collect() после работы)
HEAVY_PARSERS = {"FunPay", "Playerok"}

async def send_notification_to_admins(item: ParsedItem):
    """Отправляет оповещение всем администраторам."""
    admins = await db_manager.get_admins()
    
    # Форматируем сообщение
    message_text = (
        f"🔔 <b>Найден дешевый товар!</b>\n\n"
        f"<b>Платформа:</b> {item.platform}\n"
        f"<b>Название:</b> {item.title}\n"
        f"<b>Цена:</b> {item.price_rub} ₽ (~{item.price_usd} $)\n\n"
        f"🔗 <a href='{item.url}'>Открыть объявление</a>"
    )

    for admin_id in admins:
        try:
            # Используем HTML-разметку для ссылок
            await bot.send_message(
                chat_id=admin_id,
                text=message_text,
                parse_mode="HTML",
                disable_web_page_preview=False
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")

async def run_monitoring_cycle():
    """Один полный цикл мониторинга по всем площадкам и ключевым словам."""
    # Проверяем, включен ли мониторинг
    enabled = await db_manager.get_setting("monitoring_enabled", "1")
    if enabled != "1":
        logger.info("Мониторинг приостановлен пользователем.")
        return

    # Загружаем настройки поиска
    try:
        max_price_usd = float(await db_manager.get_setting("max_price_usd", "10.0"))
    except ValueError:
        max_price_usd = 10.0

    keywords_str = await db_manager.get_setting("keywords", "")
    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]

    if not keywords:
        logger.warning("Список ключевых слов пуст. Мониторинг пропущен.")
        return

    logger.info(f"Запуск мониторинга: ключевые слова={keywords}, макс. цена={max_price_usd}$")

    # Для каждого ключевого слова запускаем все парсеры
    for keyword in keywords:
        for parser in PARSERS:
            try:
                # Запускаем парсинг
                items: List[ParsedItem] = await parser.parse(keyword)
                
                for item in items:
                    # Проверяем условия (цена и не видели ли ранее)
                    if item.price_usd <= max_price_usd:
                        seen = await db_manager.is_item_seen(item.id)
                        if not seen:
                            # Добавляем в просмотренные
                            await db_manager.add_seen_item(item.id)
                            # Отправляем уведомление
                            await send_notification_to_admins(item)
                            # Небольшая пауза между отправкой уведомлений
                            await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Ошибка парсера {parser.platform_name} по запросу '{keyword}': {e}", exc_info=True)
            
            # Принудительная сборка мусора после тяжёлых парсеров (Playwright/Chromium)
            if parser.platform_name in HEAVY_PARSERS:
                gc.collect()
                logger.debug(f"gc.collect() выполнен после {parser.platform_name}")
            
            # Пауза между запросами к разным парсерам для снижения нагрузки
            await asyncio.sleep(2)
        
        await asyncio.sleep(2)

    logger.info("Цикл мониторинга успешно завершен.")

def update_monitoring_job(interval_minutes: int):
    """Обновляет интервал или добавляет задачу мониторинга в планировщик."""
    from scheduler_instance import scheduler
    
    if scheduler.get_job("monitoring_job"):
        scheduler.remove_job("monitoring_job")
        
    scheduler.add_job(
        run_monitoring_cycle,
        "interval",
        minutes=interval_minutes,
        id="monitoring_job"
    )
    logger.info(f"Интервал мониторинга обновлен: {interval_minutes} минут.")

def toggle_monitoring_job(enabled: bool):
    """Включает или выключает задачу мониторинга в планировщике."""
    from scheduler_instance import scheduler
    
    job = scheduler.get_job("monitoring_job")
    if not job:
        # Если задачи нет, создаем её с интервалом из БД
        return
        
    if enabled:
        try:
            scheduler.resume_job("monitoring_job")
            logger.info("Задача мониторинга возобновлена в планировщике.")
        except Exception:
            # Если не получается возобновить (например, не была запущена), ничего страшного
            pass
    else:
        try:
            scheduler.pause_job("monitoring_job")
            logger.info("Задача мониторинга приостановлена в планировщике.")
        except Exception:
            pass

