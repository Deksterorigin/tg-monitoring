import aiohttp
import xml.etree.ElementTree as ET
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

class CurrencyService:
    _instance: Optional['CurrencyService'] = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(CurrencyService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.rub_to_usd_rate: float = 0.011  # Дефолтный курс (1/90)
            self.last_updated: float = 0.0
            self.cache_duration: float = 3600.0  # Кэш на 1 час
            self.initialized = True

    async def update_rate(self) -> float:
        """Получает текущий курс USD к RUB из API ЦБ РФ и считает обратный курс RUB к USD."""
        now = time.time()
        if now - self.last_updated < self.cache_duration and self.rub_to_usd_rate != 0.011:
            return self.rub_to_usd_rate

        url = "https://www.cbr.ru/scripts/XML_daily.asp"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        xml_data = await response.text(encoding='windows-1251')
                        root = ET.fromstring(xml_data)
                        usd_val = None
                        for valute in root.findall('Valute'):
                            char_code = valute.find('CharCode')
                            if char_code is not None and char_code.text == 'USD':
                                value_node = valute.find('Value')
                                if value_node is not None and value_node.text:
                                    # Заменяем запятую на точку для преобразования в float
                                    usd_val_str = value_node.text.replace(',', '.')
                                    usd_val = float(usd_val_str)
                                    break
                        
                        if usd_val:
                            # usd_val — это сколько рублей стоит 1 доллар.
                            # Нам нужен курс: сколько долларов стоит 1 рубль (RUB -> USD)
                            self.rub_to_usd_rate = 1.0 / usd_val
                            self.last_updated = now
                            logger.info(f"Курс валют обновлен. 1 USD = {usd_val} RUB (1 RUB = {self.rub_to_usd_rate:.5f} USD)")
                            return self.rub_to_usd_rate
        except Exception as e:
            logger.error(f"Не удалось обновить курс валют из ЦБ РФ: {e}. Используется дефолтный курс.")
        
        return self.rub_to_usd_rate

    async def convert_rub_to_usd(self, rub_amount: float) -> float:
        rate = await self.update_rate()
        return rub_amount * rate

currency_service = CurrencyService()
