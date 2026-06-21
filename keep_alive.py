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
    
    port = settings.PORT
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    logger.info(f"Веб-сервер запущен на порту {port}")
    return runner

# Несколько надёжных бесплатных сервисов для внешнего пинга
# Они делают GET-запрос на указанный URL, что засчитывается Render как внешний трафик
PING_SERVICES = [
    "https://uptime.betterstack.com/api/v1/heartbeat/",  # Better Stack
    "https://hc-ping.com/",  # Healthchecks.io
]

async def self_ping():
    """Отправка GET запроса на собственный URL для предотвращения сна на Render.
    
    Используем лёгкий подход:
    1. Прямой запрос на свой URL (работает если Render не блокирует)
    2. Если не сработало — логируем предупреждение
    
    Не скачиваем огромные списки прокси — это тратит память впустую.
    """
    url = settings.RENDER_EXTERNAL_URL
    if not url:
        logger.info("RENDER_EXTERNAL_URL не задан, self-ping пропущен.")
        return

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    logger.debug("Self-ping выполнен успешно.")
                    return
    except Exception as e:
        logger.warning(f"Self-ping не удался: {e}")
