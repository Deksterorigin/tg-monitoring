import random
import logging
import aiohttp
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from pydantic import BaseModel
from database import db_manager
from services.proxy_checker import parse_proxy_string

logger = logging.getLogger(__name__)

class ParsedItem(BaseModel):
    id: str         # Уникальный ID объявления (например, ID товара или URL)
    title: str      # Название товара
    price_rub: float # Цена в рублях
    price_usd: float # Цена в долларах (после конвертации)
    url: str        # Ссылка на товар
    platform: str   # Название платформы (FunPay, Plati и т.д.)
    seller_reviews: int = 0 # Количество отзывов у продавца

class BaseParser(ABC):
    def __init__(self, platform_name: str):
        self.platform_name = platform_name

    async def get_route_proxy(self) -> Optional[str]:
        """Возвращает случайный рабочий прокси из пула или базы данных в формате для запросов."""
        try:
            from services.proxy_pool import proxy_pool
            proxy_raw = proxy_pool.get_random_proxy()
            if proxy_raw:
                return parse_proxy_string(proxy_raw)
        except Exception as e:
            logger.error(f"Ошибка получения прокси из пула: {e}")

        # Фолбэк на прокси из базы данных
        active_proxies = await db_manager.get_active_proxies()
        if not active_proxies:
            return None
        
        proxy_raw = random.choice(active_proxies)
        proxy_parsed = parse_proxy_string(proxy_raw)
        return proxy_parsed

    async def request_with_retry(self, session: aiohttp.ClientSession, url: str, headers: dict, max_retries: int = 3) -> Optional[str]:
        """Выполняет запрос с автоматической ротацией прокси при ошибках (403, 429, тайм-аут)."""
        for attempt in range(max_retries):
            proxy = await self.get_route_proxy()
            try:
                logger.info(f"[{self.platform_name}] Попытка HTTP запроса {attempt + 1}/{max_retries} через прокси: {proxy or 'БЕЗ ПРОКСИ'}")
                async with session.get(url, proxy=proxy, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        return await response.text()
                    logger.warning(f"[{self.platform_name}] Прокси вернул код {response.status}. Пробуем другой...")
            except Exception as e:
                logger.warning(f"[{self.platform_name}] Ошибка HTTP запроса через прокси {proxy}: {e}. Пробуем другой...")
        return None

    async def get_working_browser_page(self, browser_manager, max_retries: int = 3) -> Tuple[Optional['BrowserContext'], Optional['Page']]:
        """Создает контекст и страницу Playwright с проверкой работоспособности прокси на целевом сайте и очисткой ресурсов."""
        test_url = "https://funpay.com/" if self.platform_name == "FunPay" else "https://playerok.com/"
        import playwright.async_api
        import asyncio

        for attempt in range(max_retries):
            proxy_str = await self.get_route_proxy()
            proxy_dict = None
            if proxy_str:
                from services.proxy_checker import parse_proxy_to_playwright
                proxy_dict = parse_proxy_to_playwright(proxy_str)

            context = None
            page = None
            try:
                logger.info(f"[{self.platform_name}] Попытка запуска браузера {attempt + 1}/{max_retries} через прокси: {proxy_str or 'БЕЗ ПРОКСИ'}")
                context, page = await browser_manager.get_page(proxy=proxy_dict)

                # Загружаем целевой сайт для проверки блокировок
                await page.goto(test_url, timeout=15000, wait_until="domcontentloaded")

                # Проверяем, нет ли блокировки Cloudflare
                title = await page.title()
                content = await page.content()
                if "Just a moment" in title or "Cloudflare" in title or "Forbidden" in title or "cf-challenge" in content:
                    logger.warning(f"[{self.platform_name}] Прокси заблокирован Cloudflare. Закрываем страницу и контекст...")
                    await browser_manager.release_page(context, page)
                    continue

                return context, page
            except (playwright.async_api.TimeoutError, asyncio.TimeoutError) as timeout_err:
                logger.warning(f"[{self.platform_name}] Таймаут подключения Playwright через прокси {proxy_str}: {timeout_err}")
                if context or page:
                    await browser_manager.release_page(context, page)
            except playwright.async_api.Error as playwright_err:
                logger.warning(f"[{self.platform_name}] Сетевая ошибка Playwright через прокси {proxy_str}: {playwright_err}")
                if context or page:
                    await browser_manager.release_page(context, page)
            except Exception as e:
                logger.warning(f"[{self.platform_name}] Критическая ошибка браузера с прокси {proxy_str}: {e}")
                if context or page:
                    await browser_manager.release_page(context, page)

        logger.error(f"[{self.platform_name}] Не удалось создать рабочую страницу браузера после {max_retries} попыток.")
        return None, None

    @abstractmethod
    async def parse(self, keyword: str) -> List[ParsedItem]:
        """Метод парсинга по ключевому слову. Должен быть реализован в каждом парсере."""
        pass
