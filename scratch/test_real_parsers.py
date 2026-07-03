import asyncio
import logging
import sys
from database import db_manager
from parsers.plati import PlatiParser
from parsers.ggsel import GGSelParser
from parsers.funpay import FunPayParser
from parsers.playerok import PlayerokParser
from services.browser import browser_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", stream=sys.stdout)
logger = logging.getLogger("TestRealParsers")

async def test_parser(parser_instance, keyword: str):
    logger.info(f"=== Тестирование парсера: {parser_instance.platform_name} ===")
    try:
        items = await parser_instance.parse(keyword)
        logger.info(f"[{parser_instance.platform_name}] Успешно. Найдено товаров: {len(items)}")
        for idx, item in enumerate(items[:3]):
            logger.info(f"  {idx+1}. {item.title} | {item.price_rub} руб / {item.price_usd} usd | {item.url}")
    except Exception as e:
        logger.error(f"[{parser_instance.platform_name}] Ошибка: {e}", exc_info=True)

async def main():
    # Инициализация БД для корректной работы get_route_proxy
    await db_manager.init_db()
    
    # Отключаем бесплатные прокси в БД на время теста, чтобы проверить прямые запросы
    # или используем их, если они настроены
    await db_manager.set_setting("use_free_proxies", "0")
    
    keyword = "ChatGPT"
    
    # 1. Тестируем HTTP-парсеры
    await test_parser(PlatiParser(), keyword)
    await test_parser(GGSelParser(), keyword)
    
    # 2. Тестируем Playwright-парсеры
    logger.info("Запускаем BrowserManager для браузерных парсеров...")
    await browser_manager.start()
    try:
        await test_parser(FunPayParser(), keyword)
        await test_parser(PlayerokParser(), keyword)
    finally:
        await browser_manager.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
