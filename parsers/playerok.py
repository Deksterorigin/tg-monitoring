import aiohttp
import logging
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import List
from parsers.base import BaseParser, ParsedItem
from services.currency import currency_service

logger = logging.getLogger(__name__)

class PlayerokParser(BaseParser):
    def __init__(self):
        super().__init__("Playerok")

    async def parse(self, keyword: str) -> List[ParsedItem]:
        logger.info(f"[{self.platform_name}] Начало парсинга по запросу: {keyword}")
        parsed_items: List[ParsedItem] = []
        
        # Получаем прокси
        proxy = await self.get_route_proxy()
        
        # Обычно поиск на Playerok происходит по URL: https://playerok.com/products?search={keyword}
        # или https://playerok.com/?search={keyword}
        url = f"https://playerok.com/products?search={keyword}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url, proxy=proxy) as response:
                    if response.status != 200:
                        logger.warning(f"[{self.platform_name}] Ошибка запроса к Playerok: {response.status}")
                        return parsed_items
                        
                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")
                    
                    # Пытаемся найти товары на странице.
                    # По умолчанию ищем теги <a>, ссылки которых содержат "/product/" или "/goods/"
                    cards = soup.find_all("a", href=re.compile(r"/product/|/goods/"))
                    if not cards:
                        # Если не нашли, ищем по классам карточек
                        cards = soup.select("[class*='card'], [class*='product'], [class*='item']")
                        
                    logger.info(f"[{self.platform_name}] Найдено {len(cards)} потенциальных товаров.")
                    
                    for card in cards:
                        try:
                            # Ссылка
                            href = card.get("href") if card.name == "a" else None
                            if not href:
                                link_el = card.find("a", href=re.compile(r"/product/|/goods/")) or card.find("a")
                                if link_el:
                                    href = link_el.get("href")
                                    
                            if not href:
                                continue
                                
                            item_url = urljoin("https://playerok.com/", href)
                            
                            # ID товара
                            item_id_match = re.search(r"/(product|goods)/([\w\d_-]+)", href)
                            item_id = item_id_match.group(2) if item_id_match else href.replace("/", "_")
                            
                            # Название
                            title_el = card.select_one("[class*='title'], [class*='name']") or card.find(class_=re.compile(r"title|name"))
                            title = title_el.text.strip() if title_el else ""
                            if not title and card.name == "a":
                                title = card.text.strip()
                                
                            if not title or keyword.lower() not in title.lower():
                                continue
                                
                            # Цена
                            price_el = card.select_one("[class*='price'], [class*='cost']") or card.find(class_=re.compile(r"price|cost"))
                            price_text = price_el.text.strip() if price_el else ""
                            
                            if not price_text:
                                text_content = card.text
                                price_match = re.search(r"(\d[\d\s.,]*)\s*(₽|руб|usd|\$)", text_content, re.IGNORECASE)
                                if price_match:
                                    price_text = price_match.group(0)
                                    
                            if not price_text:
                                continue
                                
                            # Чистим цену
                            price_num_match = re.search(r"([\d\s.,]+)", price_text)
                            if not price_num_match:
                                continue
                                
                            price_val = float(price_num_match.group(1).replace(" ", "").replace(",", ".").strip())
                            
                            if "$" in price_text or "usd" in price_text.lower():
                                price_usd = price_val
                                price_rub = price_usd * 90.0
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
        except Exception as e:
            logger.error(f"[{self.platform_name}] Ошибка запроса к Playerok: {e}")
            
        return parsed_items
