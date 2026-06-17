import re
import logging
from typing import List, Optional, Dict
from playwright.async_api import async_playwright
from parsers.base import BaseParser, ParsedItem
from services.currency import currency_service
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class PlayerokParser(BaseParser):
    def __init__(self):
        super().__init__("Playerok")

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
                browser = await p.chromium.launch(
                    headless=True,
                    proxy=pw_proxy,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-extensions"
                    ]
                )
                
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                
                page = await context.new_page()
                
                # Шаг 1. Переходим на главную страницу Playerok
                logger.info(f"[{self.platform_name}] Открытие главной страницы")
                await page.goto("https://playerok.com/", timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                
                # Шаг 2. Ищем инпут поиска и вводим ключевое слово
                search_input = page.locator("input[placeholder*='Поиск'], input[placeholder*='поиск']")
                category_urls = set()
                
                if await search_input.count() > 0:
                    logger.info(f"[{self.platform_name}] Ввод ключевого слова '{keyword}'")
                    await search_input.first.fill(keyword)
                    await page.wait_for_timeout(3000) # Даем автокомплиту отработать
                    
                    # Извлекаем все ссылки на категории из автокомплита
                    content = await page.content()
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(content, "html.parser")
                    
                    for link in soup.find_all("a"):
                        href = link.get("href")
                        if href and keyword.lower() in href.lower():
                            # Игнорируем внешние и служебные ссылки
                            if not any(x in href for x in ["http", "privacy", "happy-birthday", "profile", "seller"]):
                                full_url = urljoin("https://playerok.com/", href)
                                category_urls.add(full_url)
                
                # Фолбэки, если автокомплит не дал ссылок
                # 1. Пробуем прямую ссылку на раздел игры
                category_urls.add(f"https://playerok.com/games/{keyword.lower()}")
                # 2. Пробуем прямую ссылку на подраздел
                category_urls.add(f"https://playerok.com/{keyword.lower()}")
                
                category_urls_list = list(category_urls)
                logger.info(f"[{self.platform_name}] Сформировано {len(category_urls_list)} потенциальных разделов для проверки")
                
                # Обходим разделы и парсим товары
                # Ограничиваем первыми 3 разделами
                for target_url in category_urls_list[:3]:
                    logger.info(f"[{self.platform_name}] Проверка раздела: {target_url}")
                    try:
                        await page.goto(target_url, timeout=20000, wait_until="domcontentloaded")
                        await page.wait_for_timeout(3000)
                        
                        content = await page.content()
                        soup = BeautifulSoup(content, "html.parser")
                        
                        # Карточки товаров на Playerok имеют ссылки на "/products/[id]-[slug]"
                        product_links = soup.find_all("a", href=re.compile(r"/products/"))
                        
                        # Группируем по href
                        links_by_href = {}
                        for link in product_links:
                            href = link.get("href")
                            if href:
                                links_by_href.setdefault(href, []).append(link)
                                
                        logger.info(f"[{self.platform_name}] Найдено {len(links_by_href)} уникальных карточек товаров в разделе")
                        
                        for href, links in links_by_href.items():
                            try:
                                item_url = urljoin("https://playerok.com/", href)
                                
                                # Уникальный ID товара
                                item_id_match = re.search(r"/products/([\w\d_-]+)", href)
                                item_id = item_id_match.group(1) if item_id_match else href.replace("/", "_")
                                
                                # Название
                                title = ""
                                for l in links:
                                    text = l.text.strip()
                                    if text:
                                        title = text
                                        break
                                        
                                if not title or keyword.lower() not in title.lower():
                                    continue
                                    
                                # Цена: ищем в родителях любой из ссылок
                                price_text = ""
                                for l in links:
                                    parent = l.parent
                                    if parent:
                                        parent_text = parent.text
                                        price_match = re.search(r"(\d[\d\s.,]*)\s*(₽|руб|usd|\$|EUR|€)", parent_text, re.IGNORECASE)
                                        if price_match:
                                            price_text = price_match.group(0)
                                            break
                                            
                                if not price_text:
                                    continue
                                    
                                # Очищаем цену (поддержка non-breaking space и любых разделителей тысяч)
                                price_num_match = re.search(r"([\d\s.,]+)", price_text)
                                if not price_num_match:
                                    continue
                                    
                                price_val_str = re.sub(r"\s+", "", price_num_match.group(1)).replace(",", ".")
                                price_val = float(price_val_str)
                                
                                # Конвертация валюты
                                if "$" in price_text or "usd" in price_text.lower():
                                    price_usd = price_val
                                    price_rub = price_usd * 90.0
                                elif "€" in price_text or "eur" in price_text.lower():
                                    price_usd = await currency_service.convert_eur_to_usd(price_val)
                                    price_rub = await currency_service.convert_eur_to_rub(price_val)
                                else:
                                    price_rub = price_val
                                    price_usd = await currency_service.convert_rub_to_usd(price_rub)
                                    
                                parsed_items.append(ParsedItem(
                                    id=f"playerok_{item_id}",
                                    title=title,
                                    price_rub=round(price_rub, 2),
                                    price_usd=round(price_usd, 2),
                                    url=item_url,
                                    platform=self.platform_name
                                ))
                            except Exception as card_err:
                                logger.error(f"[{self.platform_name}] Ошибка разбора карточки: {card_err}")
                                continue
                    except Exception as cat_err:
                        logger.warning(f"[{self.platform_name}] Не удалось загрузить раздел {target_url}: {cat_err}")
                        continue
                        
            except Exception as e:
                logger.error(f"[{self.platform_name}] Критическая ошибка при парсинге Playwright: {e}")
            finally:
                if context:
                    await context.close()
                if browser:
                    await browser.close()
                    
        return parsed_items
