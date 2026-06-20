import aiohttp
import logging
from aiohttp import web
from config import settings

logger = logging.getLogger(__name__)

async def handle_ping(request: web.Request) -> web.Response:
    """Хендлер для GET / - возвращает простой ответ OK."""
    return web.Response(text="OK", status=200)

async def start_web_server() -> web.AppRunner:
    """Запуск легковесного веб-сервера для Render.com."""
    app = web.Application()
    app.router.add_get("/", handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Слушаем порт, указанный в .env (по умолчанию 8080)
    port = settings.PORT
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    logger.info(f"Веб-сервер запущен на порту {port}")
    return runner

async def self_ping():
    """Отправка GET запроса на собственный URL через бесплатные прокси.
    Это обходит политику Render (запросы изнутри контейнера игнорируются).
    Внешний запрос через прокси не дает контейнеру уснуть."""
    url = settings.RENDER_EXTERNAL_URL
    if not url:
        logger.info("RENDER_EXTERNAL_URL не задан, self-ping пропущен.")
        return

    logger.info(f"Начинаем self-ping на {url} через публичные прокси...")
    
    proxies = []
    try:
        # Получаем актуальный список бесплатных HTTP прокси
        async with aiohttp.ClientSession() as session:
            async with session.get("https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt", timeout=10) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    proxies = [f"http://{line.strip()}" for line in text.splitlines() if line.strip()]
    except Exception as e:
        logger.error(f"Не удалось получить список бесплатных прокси: {e}")

    import random
    if proxies:
        random.shuffle(proxies)
        # Пробуем до 5 разных прокси
        for proxy in proxies[:5]:
            try:
                logger.debug(f"Пробуем пинг через прокси {proxy}")
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, proxy=proxy, timeout=10) as response:
                        if response.status == 200:
                            logger.info(f"Успешный self-ping через прокси {proxy}!")
                            return # Успех, выходим
            except Exception:
                continue # Прокси не сработал, пробуем следующий

    # Если прокси не сработали или их нет, делаем прямой пинг (как запасной вариант)
    logger.warning("Все прокси не сработали. Выполняю прямой self-ping (может быть проигнорирован Render).")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    logger.info("Прямой self-ping выполнен успешно.")
    except Exception as e:
        logger.error(f"Ошибка при выполнении прямого self-ping: {e}")
