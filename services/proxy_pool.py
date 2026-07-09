import aiohttp
import asyncio
import logging
import random
from typing import List, Optional
from database import db_manager
from services.proxy_checker import parse_proxy_string

logger = logging.getLogger(__name__)

# Ссылки на репозитории со списками бесплатных HTTP-прокси
PROXY_SOURCES = [
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
]

class ProxyPool:
    def __init__(self):
        self.working_proxies: List[str] = []

    def get_random_proxy(self) -> Optional[str]:
        """Возвращает случайный работающий прокси из пула."""
        if not self.working_proxies:
            return None
        return random.choice(self.working_proxies)

    async def refresh(self):
        """Скачивает бесплатные прокси, проверяет работоспособность и наполняет пул."""

        # Проверяем, включено ли использование авто-прокси в БД
        use_free = await db_manager.get_setting("use_free_proxies", "1")
        if use_free != "1":
            logger.info("[ProxyPool] Использование авто-прокси отключено в настройках.")
            return

        logger.info("[ProxyPool] Запуск обновления пула прокси...")
        candidates = set()

        # 1. Скачиваем списки прокси
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for url in PROXY_SOURCES:
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            text = await response.text()
                            lines = text.strip().split("\n")
                            count = 0
                            for line in lines:
                                line = line.strip()
                                if line:
                                    candidates.add(line)
                                    count += 1
                            logger.info(f"[ProxyPool] Загружено {count} кандидатов из {url}")
                except Exception as e:
                    logger.warning(f"[ProxyPool] Не удалось загрузить прокси из {url}: {e}")

        # 2. Подмешиваем активные прокси из БД (чтобы приватные прокси пользователя тоже участвовали)
        try:
            db_proxies = await db_manager.get_active_proxies()
            if db_proxies:
                candidates.update(db_proxies)
                logger.info(f"[ProxyPool] Добавлено {len(db_proxies)} активных прокси из базы данных.")
        except Exception as e:
            logger.error(f"[ProxyPool] Ошибка при чтении прокси из БД: {e}")

        if not candidates:
            logger.warning("[ProxyPool] Нет кандидатов для проверки.")
            return

        # 3. Запуск верификации порциями по 30 кандидатов для экономии памяти и времени
        candidate_list = list(candidates)
        random.shuffle(candidate_list)

        logger.info(f"[ProxyPool] Запуск проверки кандидатов (всего найдено: {len(candidate_list)})...")

        working = []
        chunk_size = 30
        limit = 5

        for i in range(0, len(candidate_list), chunk_size):
            chunk = candidate_list[i : i + chunk_size]
            needed = limit - len(working)
            logger.info(f"[ProxyPool] Проверка пачки кандидатов {i + 1} - {i + len(chunk)} (нужно еще {needed})...")
            
            chunk_working = await self._find_working_proxies(chunk, limit=needed, max_concurrent=5)
            working.extend(chunk_working)
            
            if len(working) >= limit:
                break

        self.working_proxies = working
        logger.info(f"[ProxyPool] Пул успешно обновлен. Найдено рабочих прокси: {len(self.working_proxies)}")

    async def _find_working_proxies(self, candidates: List[str], limit: int = 5, max_concurrent: int = 5) -> List[str]:
        """
        Проверяет кандидатов с ограничением параллельности и ранним выходом.
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        results_queue = asyncio.Queue()

        timeout = aiohttp.ClientTimeout(total=5)  # Короткий таймаут 5с для отсеивания медленных прокси
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = []
            for proxy in candidates:
                task = asyncio.create_task(self._check_proxy_task(proxy, semaphore, session, results_queue))
                tasks.append(task)

            working = []
            try:
                while len(working) < limit and len(working) < len(candidates):
                    # Проверяем, завершены ли все задачи
                    all_done = all(t.done() for t in tasks)
                    if all_done and results_queue.empty():
                        break

                    try:
                        # Ожидаем рабочий прокси из очереди
                        proxy = await asyncio.wait_for(results_queue.get(), timeout=0.2)
                        working.append(proxy)
                        logger.info(f"[ProxyPool] Найден рабочий прокси: {proxy}")
                    except asyncio.TimeoutError:
                        if all(t.done() for t in tasks) and results_queue.empty():
                            break
            finally:
                # Отменяем все оставшиеся проверки, чтобы освободить ресурсы
                for task in tasks:
                    if not task.done():
                        task.cancel()

                # Даем отмененным задачам завершиться
                await asyncio.gather(*tasks, return_exceptions=True)

        return working

    async def _check_proxy_task(self, proxy: str, semaphore: asyncio.Semaphore, session: aiohttp.ClientSession, results_queue: asyncio.Queue):
        """
        Фоновая задача проверки отдельного прокси на доступность к plati.io.
        """
        async with semaphore:
            try:
                proxy_url = parse_proxy_string(proxy)
                if not proxy_url:
                    return

                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                }
                # Делаем легкий GET-запрос на plati.io без проверки SSL
                async with session.get("https://plati.io/", proxy=proxy_url, headers=headers, ssl=False) as response:
                    if response.status == 200:
                        await results_queue.put(proxy)
            except Exception:
                pass

proxy_pool = ProxyPool()
