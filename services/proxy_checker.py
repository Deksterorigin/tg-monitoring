import aiohttp
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

def parse_proxy_string(proxy_str: str) -> Optional[str]:
    """
    Парсит строку прокси и приводит её к формату aiohttp (http://[user:pass@]ip:port)
    Форматы на входе:
    - IP:PORT
    - IP:PORT:USER:PASS
    - USER:PASS@IP:PORT
    - http://...
    """
    proxy_str = proxy_str.strip()
    if not proxy_str:
        return None
        
    if proxy_str.startswith("http://") or proxy_str.startswith("https://"):
        return proxy_str

    parts = proxy_str.split(":")
    if len(parts) == 2:
        # IP:PORT
        return f"http://{parts[0]}:{parts[1]}"
    elif len(parts) == 4:
        # IP:PORT:USER:PASS
        ip, port, user, password = parts
        return f"http://{user}:{password}@{ip}:{port}"
    elif "@" in proxy_str:
        return f"http://{proxy_str}"
        
    return f"http://{proxy_str}"

class ProxyChecker:
    @staticmethod
    async def check(proxy_raw: str, timeout_sec: int = 10) -> bool:
        """
        Проверяет работоспособность прокси, отправляя запрос на api.ipify.org.
        """
        proxy_url = parse_proxy_string(proxy_raw)
        if not proxy_url:
            logger.error(f"Не удалось распарсить строку прокси: {proxy_raw}")
            return False

        try:
            # Для aiohttp нужен proxy аргумент.
            # aiohttp принимает прокси в формате http://user:pass@ip:port
            timeout = aiohttp.ClientTimeout(total=timeout_sec)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get("https://api.ipify.org?format=json", proxy=proxy_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Прокси {proxy_raw} рабочий. Внешний IP: {data.get('ip')}")
                        return True
        except Exception as e:
            logger.warning(f"Прокси {proxy_raw} не прошел проверку: {e}")
            
        return False

def parse_proxy_to_playwright(proxy_url: str) -> Optional[dict]:
    """
    Конвертирует строку прокси (aiohttp формат или сырой) в формат для Playwright:
    {"server": "http://ip:port", "username": "...", "password": "..."}
    """
    if not proxy_url:
        return None

    if proxy_url.startswith("http://") or proxy_url.startswith("https://"):
        from urllib.parse import urlparse
        parsed = urlparse(proxy_url)
        # Обрабатываем hostname и scheme
        scheme = parsed.scheme or "http"
        hostname = parsed.hostname or ""
        server = f"{scheme}://{hostname}"
        if parsed.port:
            server += f":{parsed.port}"
        
        res = {"server": server}
        if parsed.username:
            res["username"] = parsed.username
        if parsed.password:
            res["password"] = parsed.password
        return res

    parts = proxy_url.split(":")
    if len(parts) == 2:
        return {"server": f"http://{parts[0]}:{parts[1]}"}
    elif len(parts) == 4:
        ip, port, user, password = parts
        return {
            "server": f"http://{ip}:{port}",
            "username": user,
            "password": password
        }
    return {"server": f"http://{proxy_url}"}
