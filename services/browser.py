import gc
import logging
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

logger = logging.getLogger(__name__)

# Ресурсы, которые нужно блокировать для экономии памяти
BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet", "texttrack", "eventsource", "websocket"}

# Домены рекламы и аналитики
BLOCKED_DOMAINS = [
    "google-analytics.com", "googletagmanager.com", "mc.yandex.ru",
    "doubleclick.net", "facebook.net", "vk.com/rtrg",
    "top-fwz1.mail.ru", "connect.facebook.net", "cdn.amplitude.com",
]

# Максимальные аргументы Chromium для экономии памяти
CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-breakpad",
    "--disable-component-extensions-with-background-pages",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-domain-reliability",
    "--disable-features=TranslateUI,BlinkGenPropertyTrees,AudioServiceOutOfProcess,IsolateOrigins,site-per-process",
    "--disable-hang-monitor",
    "--disable-ipc-flooding-protection",
    "--disable-popup-blocking",
    "--disable-prompt-on-repost",
    "--disable-renderer-backgrounding",
    "--disable-sync",
    "--enable-features=NetworkService,NetworkServiceInProcess",
    "--force-color-profile=srgb",
    "--metrics-recording-only",
    "--no-first-run",
    "--password-store=basic",
    "--use-mock-keychain",
    "--disable-blink-features=AutomationControlled",
    "--disable-software-rasterizer",
    "--disable-logging",
    "--disable-databases",
    "--disable-canvas-aa",
    "--disable-2d-canvas-clip-aa",
    "--disable-gl-drawing-for-tests",
    "--disable-remote-fonts",
    "--disable-notifications",
    "--disable-offer-store-unmasked-wallet-cards",
    "--disable-offer-upload-credit-cards",
    "--disable-speech-api",
    "--hide-scrollbars",
    "--mute-audio",
    "--no-default-browser-check",
    "--no-pings",
    "--disable-webgl",
    "--js-flags=--max-old-space-size=48",
    "--renderer-process-limit=1",
    "--disable-field-trial-config",
    "--single-process",
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


async def _block_resources(route):
    """Перехватчик запросов: блокирует тяжёлые ресурсы."""
    request = route.request
    resource_type = request.resource_type
    url = request.url

    if resource_type in BLOCKED_RESOURCE_TYPES:
        await route.abort()
        return

    for domain in BLOCKED_DOMAINS:
        if domain in url:
            await route.abort()
            return

    await route.continue_()


class BrowserManager:
    """Синглтон-менеджер общего Chromium-браузера.
    
    Запускает ОДИН браузер на весь цикл парсинга.
    Парсеры получают страницы через get_page() и возвращают через release_page().
    После цикла вызывается shutdown() для полного освобождения памяти.
    """

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None

    async def start(self, proxy: Optional[dict] = None):
        """Запускает Playwright и Chromium (один раз за цикл)."""
        if self._browser and self._browser.is_connected():
            return

        logger.info("[BrowserManager] Запуск Playwright и Chromium...")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            proxy=proxy,
            args=CHROMIUM_ARGS
        )
        logger.info("[BrowserManager] Chromium запущен.")

    async def get_page(self, proxy: Optional[dict] = None) -> tuple[BrowserContext, Page]:
        """Создаёт новый контекст и страницу с блокировкой ресурсов и опциональным прокси."""
        if not self._browser or not self._browser.is_connected():
            raise RuntimeError("BrowserManager: браузер не запущен. Вызовите start() сначала.")

        context_args = {
            "user_agent": USER_AGENT,
            "viewport": {"width": 800, "height": 600},
            "java_script_enabled": True,
        }
        if proxy:
            context_args["proxy"] = proxy

        context = await self._browser.new_context(**context_args)
        page = await context.new_page()
        try:
            from playwright_stealth import Stealth
            await Stealth().apply_stealth_async(page)
        except Exception as e:
            logger.warning(f"[BrowserManager] Ошибка применения stealth: {e}")
        await page.route("**/*", _block_resources)
        return context, page

    async def release_page(self, context: Optional[BrowserContext], page: Optional[Page]):
        """Закрывает страницу и контекст, освобождая память."""
        try:
            if page and not page.is_closed():
                await page.close()
        except Exception as e:
            logger.debug(f"[BrowserManager] Ошибка при закрытии page: {e}")
        try:
            if context:
                await context.close()
        except Exception as e:
            logger.debug(f"[BrowserManager] Ошибка при закрытии context: {e}")

    async def shutdown(self):
        """Полностью останавливает браузер и Playwright, освобождая всю память."""
        logger.info("[BrowserManager] Остановка Chromium...")
        import asyncio
        try:
            if self._browser:
                await asyncio.wait_for(self._browser.close(), timeout=5.0)
                self._browser = None
        except Exception as e:
            logger.error(f"[BrowserManager] Ошибка при закрытии браузера: {e}")
            self._browser = None
        try:
            if self._playwright:
                await asyncio.wait_for(self._playwright.stop(), timeout=5.0)
                self._playwright = None
        except Exception as e:
            logger.error(f"[BrowserManager] Ошибка при остановке Playwright: {e}")
            self._playwright = None

        gc.collect()
        logger.info("[BrowserManager] Chromium полностью остановлен, gc.collect() выполнен.")

        # Убиваем зомби-процессы Chromium (если остались после таймаута)
        try:
            import subprocess
            subprocess.run(["pkill", "-f", "chromium"], capture_output=True, timeout=3)
        except Exception:
            pass  # На Windows pkill не существует, игнорируем

    @property
    def is_running(self) -> bool:
        return self._browser is not None and self._browser.is_connected()


# Глобальный экземпляр
browser_manager = BrowserManager()
