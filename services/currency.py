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
            self.eur_to_rub_rate: float = 98.0   # Дефолтный курс EUR к RUB
            self.last_updated: float = 0.0
            self.cache_duration: float = 3600.0  # Кэш на 1 час
            self.initialized = True

    async def update_rates(self):
        """Получает текущие курсы USD и EUR к RUB из API ЦБ РФ."""
        now = time.time()
        if now - self.last_updated < self.cache_duration and self.last_updated != 0.0:
            return

        url = "https://www.cbr.ru/scripts/XML_daily.asp"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        xml_data = await response.text(encoding='windows-1251')
                        root = ET.fromstring(xml_data)
                        usd_val = None
                        eur_val = None
                        for valute in root.findall('Valute'):
                            char_code = valute.find('CharCode')
                            if char_code is not None:
                                if char_code.text == 'USD':
                                    value_node = valute.find('Value')
                                    if value_node is not None and value_node.text:
                                        usd_val = float(value_node.text.replace(',', '.'))
                                elif char_code.text == 'EUR':
                                    value_node = valute.find('Value')
                                    if value_node is not None and value_node.text:
                                        eur_val = float(value_node.text.replace(',', '.'))
                        
                        if usd_val is not None:
                            self.rub_to_usd_rate = 1.0 / usd_val
                        if eur_val is not None:
                            self.eur_to_rub_rate = eur_val
                        
                        if usd_val is not None or eur_val is not None:
                            self.last_updated = now
                            logger.info(
                                f"Курсы валют обновлены. 1 USD = {usd_val or 'N/A'} RUB, 1 EUR = {eur_val or 'N/A'} RUB"
                            )
        except Exception as e:
            logger.error(f"Не удалось обновить курс валют из ЦБ РФ: {e}. Используются дефолтные курсы.")

    async def convert_rub_to_usd(self, rub_amount: float) -> float:
        await self.update_rates()
        return rub_amount * self.rub_to_usd_rate

    async def convert_eur_to_usd(self, eur_amount: float) -> float:
        await self.update_rates()
        # EUR -> RUB -> USD
        rub_amount = eur_amount * self.eur_to_rub_rate
        return rub_amount * self.rub_to_usd_rate

    async def convert_eur_to_rub(self, eur_amount: float) -> float:
        await self.update_rates()
        return eur_amount * self.eur_to_rub_rate

    async def convert_usd_to_rub(self, usd_amount: float) -> float:
        await self.update_rates()
        if self.rub_to_usd_rate > 0:
            return usd_amount / self.rub_to_usd_rate
        return usd_amount * 90.0  # fallback

currency_service = CurrencyService()
