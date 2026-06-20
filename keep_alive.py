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
    """Отправка GET запроса на собственный URL. 
    ВНИМАНИЕ: На бесплатном тарифе Render это больше не работает для предотвращения сна!
    Render игнорирует внутренние запросы. Используйте UptimeRobot."""
    url = settings.RENDER_EXTERNAL_URL
    if not url:
        logger.info("RENDER_EXTERNAL_URL не задан, self-ping пропущен.")
        return
        
    logger.warning(
        f"ВНИМАНИЕ: Отправка self-ping на {url}. "
        "Render Free Tier блокирует этот способ! Бот уснет через 15 минут. "
        "Настройте UptimeRobot (см. README.md)."
    )
        
    logger.info(f"Отправка self-ping на {url}...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    logger.info("Self-ping выполнен успешно (статус 200).")
                else:
                    logger.warning(f"Self-ping вернул статус {response.status}")
    except Exception as e:
        logger.error(f"Ошибка при выполнении self-ping: {e}")
