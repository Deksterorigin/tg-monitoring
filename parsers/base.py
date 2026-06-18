import random
import logging
from abc import ABC, abstractmethod
from typing import List, Optional
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
        """Возвращает случайный рабочий прокси из базы данных в формате для запросов."""
        active_proxies = await db_manager.get_active_proxies()
        if not active_proxies:
            return None
        
        proxy_raw = random.choice(active_proxies)
        proxy_parsed = parse_proxy_string(proxy_raw)
        return proxy_parsed

    @abstractmethod
    async def parse(self, keyword: str) -> List[ParsedItem]:
        """Метод парсинга по ключевому слову. Должен быть реализован в каждом парсере."""
        pass
