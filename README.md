# Telegram Marketplace Monitoring Bot 🤖📈

An advanced, asynchronous Telegram bot built with `aiogram 3` and `Playwright` to monitor prices on digital marketplaces (such as FunPay and Playerok). The bot tracks specific keywords, compares prices, and sends instant alerts when a price drop (dumping) is detected.

## 🚀 Key Features

*   **Multi-Marketplace Parsing**: Simultaneously monitors multiple platforms using Headless Chromium via `Playwright`.
*   **Price Drop Detection (Dumping)**: Automatically compares new prices with previous snapshots and alerts administrators if the price drops, even for already known items.
*   **Memory Optimized**: Runs a single shared Chromium instance, actively blocks heavy web resources (images, fonts, ads, analytics), and explicitly clears memory to easily fit inside a 512MB RAM constraint.
*   **Admin Dashboard**: Manage your bot directly from Telegram! Change keywords, set min/max prices, filter by reviews, add proxies, and toggle monitoring on/off.
*   **Do Not Disturb (DND) Mode**: Set a "quiet hours" schedule. During this time, the bot suppresses notifications and instead sends a comprehensive Morning Digest when the quiet period ends.
*   **Proxy Rotation & Auto-Banning**: Supports HTTP/SOCKS proxies with automatic health checking. Dead proxies are automatically disabled to ensure uninterrupted parsing.
*   **SQLite Database**: Stores settings, proxies, and historic price data persistently using asynchronous `aiosqlite`.

---

## 🛠️ Tech Stack
*   **Python 3.11+**
*   **aiogram 3.x** - Telegram Bot API Framework
*   **Playwright (async)** - Dynamic JS rendering and headless browser scraping
*   **BeautifulSoup4 & lxml** - Lightning-fast HTML parsing
*   **APScheduler** - Background task scheduling
*   **SQLite3 (aiosqlite)** - Lightweight async database

---

## ⚙️ Configuration (.env)

Create a `.env` file in the root directory:

```env
BOT_TOKEN=your_telegram_bot_token
FIRST_ADMIN_ID=your_telegram_user_id

# (Optional) For Render keep-alive
RENDER_EXTERNAL_URL=https://your-app.onrender.com
PORT=8080
```

---

## 🐳 Deployment on Render.com (Free Tier)

This bot is fully optimized to run on Render's Free Tier (512 MB RAM). 

### 1. Create a Web Service
1. Connect your GitHub repository to Render.
2. Create a new **Web Service**.
3. Choose the `Docker` runtime environment.
4. Set the following environment variables in the Render Dashboard:
   - `BOT_TOKEN`
   - `FIRST_ADMIN_ID`
   - `RENDER_EXTERNAL_URL` (set to your generated Render URL, e.g., `https://my-bot.onrender.com`)

### 2. ⚠️ CRITICAL: Keeping the Bot Awake (UptimeRobot)
**Render's Free Tier puts apps to sleep after 15 minutes of inactivity.** Internal pings (`self_ping`) are blocked by Render and will **not** keep your bot awake. If the bot sleeps, it will stop responding to Telegram messages!

To fix this, you **must** set up an external pinger:
1. Go to [UptimeRobot](https://uptimerobot.com) (or cron-job.org) and create a free account.
2. Click **Add New Monitor**.
3. Monitor Type: `HTTP(s)`
4. URL: Your Render app URL (e.g., `https://my-bot.onrender.com/`)
5. Interval: `5 minutes`
6. Save and start the monitor.
*This ensures Render receives an external HTTP request every 5 minutes, keeping your bot online 24/7.*

---

## 📁 Project Structure

*   `main.py`: Entry point. Initializes the bot, APScheduler, and Web Server.
*   `config.py`: Environment variables parsing using `pydantic-settings`.
*   `database.py`: Async SQLite manager (admins, settings, proxies, items history).
*   `keep_alive.py`: Lightweight `aiohttp` web server to bind `$PORT` for PaaS providers like Render.
*   `scheduler_instance.py`: Centralized `APScheduler` instance.
*   `bot_instance.py`: Centralized `aiogram` Bot and Dispatcher instances.
*   **`services/`**:
    *   `browser.py`: Singleton `BrowserManager` for Playwright. Reuses one Chromium instance to save memory.
    *   `monitor.py`: Core logic for monitoring cycles, comparing price snapshots, and sending alerts.
    *   `digest.py`: Generates the Morning Digest.
    *   `proxy_checker.py`: Validates proxies in the background.
    *   `currency.py`: Fetches real-time exchange rates (CBR API) to normalize prices to USD/RUB.
*   **`parsers/`**:
    *   `base.py`: Abstract Base Class for parsers.
    *   `funpay.py` & `playerok.py`: Concrete parser implementations.
*   **`bot/`**:
    *   Contains aiogram handlers, filters, middlewares, and inline keyboards for the Telegram UI.

---

## 🛡️ Bot Commands (For Admins Only)

*   `/start` - Opens the main interactive Dashboard.
*   **Dashboard Options:**
    *   **Settings**: Configure keywords, minus-words, and price filters (Min/Max).
    *   **Interval**: Change how often the bot scrapes the marketplaces (e.g., every 60 mins).
    *   **Proxies**: Add new proxies (format: `http://user:pass@ip:port`), list active proxies, or force a proxy health check.
    *   **Admins**: Add or remove co-administrators.
    *   **DND (Quiet Hours)**: Set a timeframe where notifications are muted.
    *   **Database Backup**: Download a `.db` backup file directly from Telegram.

---

## 📝 License
MIT License. Feel free to modify and use it for your own projects.
