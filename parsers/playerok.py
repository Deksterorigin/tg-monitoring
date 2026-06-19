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


class PlayerokParser(BaseParser):
    def __init__(self):
        super().__init__("Playerok")

    async def parse(self, keyword: str) -> List[ParsedItem]:
        logger.info(f"[{self.platform_name}] Начало парсинга по запросу: {keyword}")
        parsed_items: List[ParsedItem] = []

        context = None
        page = None
        try:
            context, page = await browser_manager.get_page()

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
                await page.wait_for_timeout(2000)  # Уменьшено с 3000

                # Извлекаем все ссылки на категории из автокомплита
                content = await page.content()
                soup = BeautifulSoup(content, "lxml")

                for link in soup.find_all("a"):
                    href = link.get("href")
                    if href and keyword.lower() in href.lower():
                        # Игнорируем внешние и служебные ссылки
                        if not any(x in href for x in ["http", "privacy", "happy-birthday", "profile", "seller"]):
                            full_url = urljoin("https://playerok.com/", href)
                            category_urls.add(full_url)

                del soup
                del content

            # Фолбэки, если автокомплит не дал ссылок
            category_urls.add(f"https://playerok.com/games/{keyword.lower()}")
            category_urls.add(f"https://playerok.com/{keyword.lower()}")

            category_urls_list = list(category_urls)
            logger.info(f"[{self.platform_name}] Сформировано {len(category_urls_list)} потенциальных разделов для проверки")

            # Обходим разделы и парсим товары
            for target_url in category_urls_list[:3]:
                logger.info(f"[{self.platform_name}] Проверка раздела: {target_url}")
                try:
                    await page.goto(target_url, timeout=20000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)  # Уменьшено с 3000

                    content = await page.content()
                    soup = BeautifulSoup(content, "lxml")

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

                            # Очищаем цену
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

                    # Явно освобождаем память после каждой категории
                    del soup
                    del content
                    del product_links
                except Exception as cat_err:
                    logger.warning(f"[{self.platform_name}] Не удалось загрузить раздел {target_url}: {cat_err}")
                    continue

        except Exception as e:
            logger.error(f"[{self.platform_name}] Критическая ошибка при парсинге Playwright: {e}")
        finally:
            await browser_manager.release_page(context, page)

        gc.collect()
        return parsed_items
