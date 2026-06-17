import aiohttp
import logging
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import List
from parsers.base import BaseParser, ParsedItem
from services.currency import currency_service

logger = logging.getLogger(__name__)

class GGSelParser(BaseParser):
    def __init__(self):
        super().__init__("GGSel")

    async def parse(self, keyword: str) -> List[ParsedItem]:
        logger.info(f"[{self.platform_name}] Начало парсинга по запросу: {keyword}")
        parsed_items: List[ParsedItem] = []
        
        # Получаем прокси
        proxy = await self.get_route_proxy()
        
        # URL страницы поиска
        url = f"https://ggsel.net/catalog?search={keyword}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url, proxy=proxy) as response:
                    if response.status != 200:
                        logger.warning(f"[{self.platform_name}] Ошибка запроса к сайту: {response.status}")
                        return parsed_items
                        
                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")
                    
                    # Пытаемся найти карточки товаров
                    # На GGSel карточки обычно имеют ссылки на "/goods/" или содержат определенные классы.
                    cards = soup.find_all("a", href=re.compile(r"/goods/\d+"))
                    if not cards:
                        # Вторая попытка: ищем по классам
                        cards = soup.select(".product-card, .main-item, .catalog-item")
                        
                    logger.info(f"[{self.platform_name}] Найдено {len(cards)} потенциальных карточек.")
                    
                    for card in cards:
                        try:
                            # Ссылка
                            href = card.get("href") if card.name == "a" else None
                            if not href:
                                link_el = card.find("a", href=re.compile(r"/goods/\d+")) or card.find("a")
                                if link_el:
                                    href = link_el.get("href")
                            
                            if not href:
                                continue
                                
                            item_url = urljoin("https://ggsel.net/", href)
                            
                            # ID товара
                            item_id_match = re.search(r"/goods/(\d+)", href)
                            item_id = item_id_match.group(1) if item_id_match else href.replace("/", "_")
                            
                            # Название товара
                            # Ищем внутри карточки подходящие элементы с текстом названия
                            title_el = card.select_one(".product-card__title, .title, .name") or card.find(class_=re.compile(r"title|name|desc"))
                            title = title_el.text.strip() if title_el else ""
                            if not title and card.name == "a":
                                # Если сама ссылка содержит текст
                                title = card.text.strip()
                                
                            if not title or keyword.lower() not in title.lower():
                                continue
                                
                            # Цена
                            price_el = card.select_one(".product-card__price, .price, .val") or card.find(class_=re.compile(r"price|cost"))
                            price_text = price_el.text.strip() if price_el else ""
                            
                            if not price_text:
                                # Ищем текст с цифрами и знаком валюты
                                text_content = card.text
                                price_match = re.search(r"(\d[\d\s.,]*)\s*(₽|руб|usd|\$|EUR|€)", text_content, re.IGNORECASE)
                                if price_match:
                                    price_text = price_match.group(0)
                                    
                            if not price_text:
                                continue
                                
                            # Очищаем цену
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
                                id=f"ggsel_{item_id}",
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
            logger.error(f"[{self.platform_name}] Ошибка при запросе к GGSel: {e}")
            
        return parsed_items
