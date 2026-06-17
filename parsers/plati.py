import aiohttp
import logging
from typing import List
from parsers.base import BaseParser, ParsedItem

logger = logging.getLogger(__name__)

class PlatiParser(BaseParser):
    def __init__(self):
        super().__init__("Plati.Market")

    async def parse(self, keyword: str) -> List[ParsedItem]:
        logger.info(f"[{self.platform_name}] Начало парсинга по запросу: {keyword}")
        parsed_items: List[ParsedItem] = []
        
        # Получаем прокси
        proxy = await self.get_route_proxy()
        
        # Plati.Market предоставляет публичный API для поиска
        url = f"https://plati.io/api/search.ashx?query={keyword}&response=json"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url, proxy=proxy) as response:
                    if response.status != 200:
                        logger.warning(f"[{self.platform_name}] Ошибка запроса к API Plati: {response.status}")
                        return parsed_items
                        
                    data = await response.json(content_type=None)
                    
                    # Структура ответа API Plati содержит поле "items" со списком товаров
                    rows = data.get("items", [])
                    logger.info(f"[{self.platform_name}] API вернуло {len(rows)} товаров.")
                    
                    for row in rows:
                        try:
                            item_id = str(row.get("id"))
                            title = row.get("name", "")
                            
                            # Проверяем ключевое слово в названии
                            if keyword.lower() not in title.lower():
                                continue
                                
                            # Цены
                            price_usd = float(row.get("price_usd", 0.0))
                            price_rub = float(row.get("price_rur", 0.0))
                            
                            # URL товара
                            item_url = f"https://plati.market/itm/{item_id}"
                            
                            parsed_items.append(ParsedItem(
                                id=f"plati_{item_id}",
                                title=title,
                                price_rub=price_rub,
                                price_usd=price_usd,
                                url=item_url,
                                platform=self.platform_name
                            ))
                        except Exception as row_err:
                            logger.error(f"[{self.platform_name}] Ошибка обработки строки товара: {row_err}")
                            continue
        except Exception as e:
            logger.error(f"[{self.platform_name}] Ошибка при запросе к Plati.Market: {e}")
            
        return parsed_items
