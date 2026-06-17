import re
import logging
from typing import List, Optional, Dict
from playwright.async_api import async_playwright
from parsers.base import BaseParser, ParsedItem
from services.currency import currency_service
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class FunPayParser(BaseParser):
    def __init__(self):
        super().__init__("FunPay")

    def _parse_playwright_proxy(self, proxy_raw: str) -> Optional[Dict[str, str]]:
        """Конвертирует строку прокси (IP:PORT:USER:PASS) в формат Playwright."""
        parts = proxy_raw.split(":")
        if len(parts) == 2:
            return {"server": f"http://{parts[0]}:{parts[1]}"}
        elif len(parts) == 4:
            ip, port, user, password = parts
            return {
                "server": f"http://{ip}:{port}",
                "username": user,
                "password": password
            }
        return None

    async def parse(self, keyword: str) -> List[ParsedItem]:
        logger.info(f"[{self.platform_name}] Начало парсинга по запросу: {keyword}")
        parsed_items: List[ParsedItem] = []
        
        # Получаем прокси
        active_proxies = await self.get_route_proxy()
        # Для playwright нужен сырой прокси, разделенный на server/user/pass,
        # либо мы берем случайный из БД напрямую.
        from database import db_manager
        proxies_list = await db_manager.get_active_proxies()
        
        pw_proxy = None
        if proxies_list:
            import random
            selected_proxy = random.choice(proxies_list)
            pw_proxy = self._parse_playwright_proxy(selected_proxy)

        async with async_playwright() as p:
            browser = None
            context = None
            try:
                # Запускаем браузер с прокси, если он есть, и флагами оптимизации памяти для Render
                browser = await p.chromium.launch(
                    headless=True,
                    proxy=pw_proxy,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--single-process",
                        "--disable-extensions"
                    ]
                )
                
                # Добавляем юзер-агент для обхода простых проверок
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                
                page = await context.new_page()
                
                # Формируем URL поиска
                search_url = f"https://funpay.com/search/?q={keyword}"
                logger.info(f"[{self.platform_name}] Открытие страницы: {search_url}")
                
                await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
                
                # Даем время на рендеринг JS (если необходимо)
                await page.wait_for_timeout(3000)
                
                # Ищем элементы объявлений
                # На FunPay на странице общего поиска элементы имеют класс .tc-item
                items = await page.query_selector_all(".tc-item")
                logger.info(f"[{self.platform_name}] Найдено {len(items)} элементов на странице.")

                for item in items:
                    try:
                        # Ссылка
                        href = await item.get_attribute("href")
                        if not href:
                            continue
                        item_url = urljoin("https://funpay.com/", href)
                        
                        # Уникальный ID из ссылки или текста
                        # Ссылки бывают вида /lots/offer?id=123456 или /chips/123/
                        item_id = href.split("?id=")[-1] if "?id=" in href else href.replace("/", "_")
                        
                        # Название/описание товара
                        desc_el = await item.query_selector(".tc-desc")
                        if not desc_el:
                            continue
                        title = await desc_el.inner_text()
                        title = title.strip()
                        
                        # Проверяем, содержит ли название искомое слово (регистронезависимо)
                        if keyword.lower() not in title.lower():
                            continue

                        # Цена
                        price_el = await item.query_selector(".tc-price")
                        if not price_el:
                            continue
                        price_text = await price_el.inner_text()
                        
                        # Извлекаем числовое значение цены из строки вроде "150 руб." или "1.50 $"
                        price_num_match = re.search(r"([\d\s.,]+)", price_text)
                        if not price_num_match:
                            continue
                        
                        price_val = float(price_num_match.group(1).replace(" ", "").replace(",", ".").strip())
                        
                        # Конвертируем валюту
                        if "$" in price_text:
                            price_usd = price_val
                            price_rub = price_usd * 90.0  # Примерный обратный курс для справки
                        else:
                            price_rub = price_val
                            price_usd = await currency_service.convert_rub_to_usd(price_rub)
                        
                        parsed_items.append(ParsedItem(
                            id=f"funpay_{item_id}",
                            title=title,
                            price_rub=round(price_rub, 2),
                            price_usd=round(price_usd, 2),
                            url=item_url,
                            platform=self.platform_name
                        ))
                    except Exception as item_err:
                        logger.error(f"[{self.platform_name}] Ошибка парсинга элемента: {item_err}")
                        continue
            except Exception as e:
                logger.error(f"[{self.platform_name}] Критическая ошибка при парсинге Playwright: {e}")
            finally:
                if context:
                    await context.close()
                if browser:
                    await browser.close()
                
        return parsed_items
