import logging
import asyncio
import gc
import re
import json
from typing import Dict, List, Tuple
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

# --- Словари для классификации товаров ---

# Категории ИИ-сервисов: ключ — каноническое название, значения — паттерны для поиска
AI_CATEGORIES = {
    "ChatGPT": [r"chatgpt", r"chat\s*gpt", r"openai", r"gpt[\s\-]?4", r"gpt[\s\-]?3"],
    "Claude": [r"claude", r"anthropic"],
    "Midjourney": [r"midjourney", r"mid\s*journey", r"миджорни"],
    "Perplexity": [r"perplexity", r"перплексити"],
    "Gemini": [r"gemini", r"google\s*ai", r"джемини"],
    "Copilot": [r"copilot", r"github\s*copilot"],
    "Cursor": [r"cursor"],
    "Suno": [r"suno"],
    "Runway": [r"runway"],
    "Pika": [r"pika"],
    "Adobe Firefly": [r"firefly", r"adobe\s*firefly"],
    "Notion AI": [r"notion\s*ai"],
    "Sora": [r"sora"],
}

# Паттерны для определения срока подписки
# ВАЖНО: порядок имеет значение — более специфичные паттерны проверяются первыми
DURATION_PATTERNS = [
    # Годовые
    (r"\b(?:1\s*год|12\s*мес|на\s*год|годов|annual|yearly|1\s*year)", "1 год"),
    # Полугодовые
    (r"\b(?:6\s*мес|180\s*дн|полгод|6\s*month|half\s*year)", "6 месяцев"),
    # 3 месяца
    (r"\b(?:3\s*мес|90\s*дн|3\s*month)", "3 месяца"),
    # 2 месяца
    (r"\b(?:2\s*мес|60\s*дн|2\s*month)", "2 месяца"),
    # 1 месяц (самый общий — проверяется последним среди месячных)
    (r"\b(?:1\s*мес|мес(?:яц)?(?:\s|$)|30\s*дн|на\s*месяц|monthly|1\s*month)", "1 месяц"),
    # Недельные
    (r"\b(?:1\s*недел|7\s*дн|на\s*неделю|weekly|1\s*week)", "1 неделя"),
]


def analyze_item(title: str) -> Tuple[str, str]:
    """Анализирует название товара и определяет категорию ИИ и срок подписки.
    
    Args:
        title: Название товара.
    
    Returns:
        Кортеж (ai_category, duration), например ("ChatGPT", "1 месяц").
    """
    title_lower = title.lower()
    
    # --- Определяем категорию ИИ ---
    ai_category = "Другое"
    for category, patterns in AI_CATEGORIES.items():
        for pattern in patterns:
            if re.search(pattern, title_lower):
                ai_category = category
                break
        if ai_category != "Другое":
            break
    
    # --- Определяем срок подписки ---
    duration = "Без срока"
    for pattern, dur_label in DURATION_PATTERNS:
        if re.search(pattern, title_lower):
            duration = dur_label
            break
    
    return ai_category, duration


async def send_notification_to_admins(item: ParsedItem, ai_category: str, duration: str):
    """Отправляет оповещение всем администраторам."""
    admins = await db_manager.get_admins()
    
    # Форматируем сообщение
    message_text = (
        f"🔔 <b>Лучшая цена в категории!</b>\n\n"
        f"🤖 <b>Нейросеть:</b> {ai_category}\n"
        f"⏳ <b>Срок:</b> {duration}\n"
        f"🏪 <b>Платформа:</b> {item.platform}\n"
        f"📝 <b>Название:</b> {item.title}\n"
        f"💰 <b>Цена:</b> {item.price_rub} ₽ (~{item.price_usd} $)\n\n"
        f"🔗 <a href='{item.url}'>Открыть объявление</a>"
    )

    for admin_id in admins:
        try:
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
        min_price_usd = float(await db_manager.get_setting("min_price_usd", "0.0"))
    except ValueError:
        min_price_usd = 0.0

    try:
        max_price_usd = float(await db_manager.get_setting("max_price_usd", "10.0"))
    except ValueError:
        max_price_usd = 10.0

    keywords_str = await db_manager.get_setting("keywords", "")
    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]

    minus_words_str = await db_manager.get_setting("minus_words", "")
    minus_words = [w.strip().lower() for w in minus_words_str.split(",") if w.strip()]

    if not keywords:
        logger.warning("Список ключевых слов пуст. Мониторинг пропущен.")
        return

    logger.info(f"Запуск мониторинга: ключевые слова={keywords}, цена: от {min_price_usd}$ до {max_price_usd}$")

    # Словарь лучших сделок: ключ=(platform, ai_category, duration), значение=ParsedItem
    best_deals: Dict[Tuple[str, str, str], ParsedItem] = {}

    # Для каждого ключевого слова запускаем все парсеры
    for keyword in keywords:
        for parser in PARSERS:
            try:
                # Запускаем парсинг
                items: List[ParsedItem] = await parser.parse(keyword)
                
                for item in items:
                    # Проверка на минус-слова
                    if minus_words:
                        title_lower = item.title.lower()
                        if any(mw in title_lower for mw in minus_words):
                            continue

                    # Проверяем ценовой диапазон
                    if not (min_price_usd <= item.price_usd <= max_price_usd):
                        continue

                    # Классифицируем товар
                    ai_category, duration = analyze_item(item.title)
                    key = (item.platform, ai_category, duration)

                    # Сохраняем только самый дешёвый товар в каждой группе
                    if key not in best_deals or item.price_usd < best_deals[key].price_usd:
                        best_deals[key] = item

            except Exception as e:
                logger.error(f"Ошибка парсера {parser.platform_name} по запросу '{keyword}': {e}", exc_info=True)
            
            # Принудительная сборка мусора после тяжёлых парсеров (Playwright/Chromium)
            if parser.platform_name in HEAVY_PARSERS:
                gc.collect()
                logger.debug(f"gc.collect() выполнен после {parser.platform_name}")
            
            # Пауза между запросами к разным парсерам для снижения нагрузки
            await asyncio.sleep(2)
        
        await asyncio.sleep(2)

    # --- Отправка уведомлений только по лучшим сделкам ---
    sent_count = 0
    snapshot = []
    for (platform, ai_category, duration), item in best_deals.items():
        # Добавляем в снимок
        snapshot.append({
            "ai_category": ai_category,
            "duration": duration,
            "platform": platform,
            "title": item.title,
            "price_rub": item.price_rub,
            "price_usd": item.price_usd,
            "url": item.url
        })
        try:
            seen = await db_manager.is_item_seen(item.id)
            if not seen:
                await db_manager.add_seen_item(item.id)
                await send_notification_to_admins(item, ai_category, duration)
                sent_count += 1
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления для {item.id}: {e}", exc_info=True)

    # Сохраняем снимок в БД
    try:
        await db_manager.set_latest_snapshot(json.dumps(snapshot, ensure_ascii=False))
        logger.info("Срез лучших цен успешно сохранен в БД.")
    except Exception as e:
        logger.error(f"Ошибка при сохранении среза цен: {e}")

    logger.info(f"Цикл мониторинга завершён. Лучших сделок: {len(best_deals)}, отправлено: {sent_count}.")

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

