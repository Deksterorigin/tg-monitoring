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
        
        # URL страницы поиска
        url = f"https://ggsel.net/catalog?search={keyword}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                html = await self.request_with_retry(session, url, headers)
                if not html:
                    logger.warning(f"[{self.platform_name}] Не удалось получить данные по запросу '{keyword}'.")
                    return parsed_items
                    
                soup = BeautifulSoup(html, "lxml")
                    
                # Ищем карточки товаров по data-testid или классам
                cards = soup.select("[data-testid='card'], [data-test='item']")
                if not cards:
                    cards = soup.select("[class*='ProductCard'], .product-card, .main-item, .catalog-item")
                if not cards:
                    # Фолбэк на поиск всех ссылок на продукты
                    cards = soup.find_all("a", href=re.compile(r"/catalog/product/|/goods/"))
                    
                logger.info(f"[{self.platform_name}] Найдено {len(cards)} потенциальных карточек.")
                
                for card in cards:
                    try:
                        # Ссылка
                        href = None
                        if card.name == "a":
                            href = card.get("href")
                        else:
                            link_el = card.select_one("[data-testid='card-link']") or card.find("a", href=re.compile(r"/catalog/product/|/goods/"))
                            if link_el:
                                href = link_el.get("href")
                        
                        if not href:
                            continue
                            
                        item_url = urljoin("https://ggsel.net/", href)
                        
                        # ID товара
                        item_id_match = re.search(r"/(product|goods)/([\w\d_-]+)", href)
                        item_id = item_id_match.group(2) if item_id_match else href.replace("/", "_")
                        
                        # Название товара
                        title = ""
                        img_el = card.find("img")
                        if img_el:
                            title = img_el.get("alt", "").strip()
                        if not title:
                            title_el = card.select_one("[class*='description'], [class*='title'], [class*='name']")
                            if title_el:
                                title = title_el.text.strip()
                        if not title and card.name == "a":
                            title = card.text.strip()
                            
                        if not title or keyword.lower() not in title.lower():
                            continue
                            
                        # Цена
                        price_text = ""
                        price_el = card.select_one("[class*='price'], [class*='cost']")
                        if price_el:
                            price_text = price_el.text.strip()
                        else:
                            text_content = card.text
                            price_match = re.search(r"(\d[\d\s.,]*)\s*(₽|руб|usd|\$|EUR|€)", text_content, re.IGNORECASE)
                            if price_match:
                                price_text = price_match.group(0)
                                
                        if not price_text:
                            continue
                            
                        # Очищаем цену (поддержка non-breaking space и любых разделителей тысяч)
                        price_num_match = re.search(r"([\d\s.,]+)", price_text)
                        if not price_num_match:
                            continue
                            
                        price_val_str = re.sub(r"\s+", "", price_num_match.group(1)).replace(",", ".")
                        price_val = float(price_val_str)
                        
                        if "$" in price_text or "usd" in price_text.lower():
                            price_usd = price_val
                            price_rub = await currency_service.convert_usd_to_rub(price_usd)
                        elif "€" in price_text or "eur" in price_text.lower():
                            price_usd = await currency_service.convert_eur_to_usd(price_val)
                            price_rub = await currency_service.convert_eur_to_rub(price_val)
                        else:
                            price_rub = price_val
                            price_usd = await currency_service.convert_rub_to_usd(price_rub)
                            
                        parsed_items.append(ParsedItem(
                            id=f"ggsel_{item_id}",
                            title=title,
                            price_rub=round(price_rub, 2),
                            price_usd=round(price_usd, 2),
                            url=item_url,
                            platform=self.platform_name,
                            seller_reviews=-1
                        ))
                    except Exception as card_err:
                        logger.error(f"[{self.platform_name}] Ошибка разбора карточки: {card_err}")
                        continue
        except Exception as e:
            logger.error(f"[{self.platform_name}] Ошибка при запросе к GGSel: {e}")
            
        return parsed_items
