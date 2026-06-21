import re
import gc
import logging
from typing import List
from bs4 import BeautifulSoup
from parsers.base import BaseParser, ParsedItem
from services.currency import currency_service
from services.browser import browser_manager
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class FunPayParser(BaseParser):
    def __init__(self):
        super().__init__("FunPay")

    async def parse(self, keyword: str) -> List[ParsedItem]:
        logger.info(f"[{self.platform_name}] Начало парсинга по запросу: {keyword}")
        parsed_items: List[ParsedItem] = []

        # Получаем и парсим прокси для Playwright
        proxy_str = await self.get_route_proxy()
        proxy_dict = None
        if proxy_str:
            from services.proxy_checker import parse_proxy_to_playwright
            proxy_dict = parse_proxy_to_playwright(proxy_str)

        context = None
        page = None
        try:
            context, page = await browser_manager.get_page(proxy=proxy_dict)

            # Шаг 1. Переходим на главную страницу FunPay
            logger.info(f"[{self.platform_name}] Открытие главной страницы")
            await page.goto("https://funpay.com/", timeout=30000, wait_until="domcontentloaded")

            # Шаг 2. Вводим ключевое слово в форму поиска
            logger.info(f"[{self.platform_name}] Ввод ключевого слова '{keyword}'")
            await page.fill("input[name='query']", keyword)

            # Шаг 3. Ждем автокомплит
            try:
                await page.wait_for_selector(".dropdown-autocomplete a", timeout=5000)
            except Exception:
                logger.warning(f"[{self.platform_name}] Не дождались ссылок автокомплита")

            # Считываем ссылки на категории
            autocomplete_links = await page.query_selector_all(".dropdown-autocomplete a")
            category_urls = []
            for link in autocomplete_links:
                href = await link.get_attribute("href")
                text = await link.inner_text()
                text = text.replace("\n", " ").strip()
                if href and ("/lots/" in href or "/chips/" in href or "/accounts/" in href):
                    full_url = urljoin("https://funpay.com/", href)
                    category_urls.append((full_url, text))

            logger.info(f"[{self.platform_name}] Найдено {len(category_urls)} разделов для парсинга")

            if not category_urls:
                if keyword.isdigit():
                    category_urls.append((f"https://funpay.com/lots/{keyword}/", f"Раздел {keyword}"))

            # Шаг 4. Обходим категории и парсим лоты
            for target_url, category_name in category_urls[:3]:
                logger.info(f"[{self.platform_name}] Парсинг категории '{category_name}': {target_url}")
                try:
                    await page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)

                    content = await page.content()
                    soup = BeautifulSoup(content, "lxml")
                    items = soup.select(".tc-item")
                    logger.info(f"[{self.platform_name}] Найдено {len(items)} элементов в категории '{category_name}'")

                    for item in items:
                        try:
                            href = item.get("href")
                            if not href:
                                continue
                            item_url = urljoin("https://funpay.com/", href)

                            # ID товара
                            item_id = href.split("?id=")[-1] if "?id=" in href else href.replace("/", "_")

                            # Описание / Название
                            desc_el = item.select_one(".tc-desc")
                            if not desc_el:
                                continue
                            title = desc_el.text.strip()

                            # Фильтр по ключевому слову в названии
                            if keyword.lower() not in title.lower():
                                continue

                            # Цена
                            price_el = item.select_one(".tc-price")
                            if not price_el:
                                continue
                            price_text = price_el.text

                            price_num_match = re.search(r"([\d\s.,]+)", price_text)
                            if not price_num_match:
                                continue

                            # Очищаем цену
                            price_val_str = re.sub(r"\s+", "", price_num_match.group(1)).replace(",", ".")
                            price_val = float(price_val_str)

                            # Конвертация валют
                            if "$" in price_text or "usd" in price_text.lower():
                                price_usd = price_val
                                price_rub = price_usd * 90.0
                            elif "€" in price_text or "eur" in price_text.lower():
                                price_usd = await currency_service.convert_eur_to_usd(price_val)
                                price_rub = await currency_service.convert_eur_to_rub(price_val)
                            else:
                                price_rub = price_val
                                price_usd = await currency_service.convert_rub_to_usd(price_rub)

                            # Отзывы
                            seller_reviews = 0
                            reviews_match = re.search(r'(\d+)\s*отзыв', item.text, re.IGNORECASE)
                            if reviews_match:
                                seller_reviews = int(reviews_match.group(1))

                            parsed_items.append(ParsedItem(
                                id=f"funpay_{item_id}",
                                title=title,
                                price_rub=round(price_rub, 2),
                                price_usd=round(price_usd, 2),
                                url=item_url,
                                platform=self.platform_name,
                                seller_reviews=seller_reviews
                            ))
                        except Exception as item_err:
                            logger.error(f"[{self.platform_name}] Ошибка разбора элемента: {item_err}")
                            continue

                    # Явно освобождаем память после каждой категории
                    del soup
                    del content
                    del items
                except Exception as cat_err:
                    logger.error(f"[{self.platform_name}] Ошибка парсинга категории {target_url}: {cat_err}")
                    continue

        except Exception as e:
            logger.error(f"[{self.platform_name}] Критическая ошибка при парсинге Playwright: {e}")
        finally:
            await browser_manager.release_page(context, page)

        gc.collect()
        return parsed_items
