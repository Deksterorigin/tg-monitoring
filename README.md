# 🤖 TG-Monitoring Bot

A high-performance, asynchronous Telegram bot designed to monitor popular digital marketplaces (**FunPay**, **Playerok**, **GGSel**, and **Plati.Market**), extract listing data, track prices, aggregate the best deals, and alert administrators in real-time. 

Optimized to run seamlessly on low-memory environments (such as Render.com's Free Tier with 512MB RAM) through a shared browser instance, aggressive headless browser resource blocking, memory cleanup, the high-performance `lxml` parser, and lightweight SQLite database indexing.

---

## 🌟 Key Features

### 🔍 Multi-Platform Parsers
*   **Shared Playwright Browser Instance**: Launches a single shared Chromium instance via `BrowserManager` for all Playwright-based parsers (**FunPay**, **Playerok**), instead of spawning separate browser processes. This keeps peak memory overhead under **200MB** instead of the usual 400-500MB.
*   **BeautifulSoup with `lxml`**: High-performance, memory-efficient HTML tree parsing using the C-optimized `lxml` engine.
*   **Aggressive Resource Blocking**: Intercepts requests in the headless browser to block images, stylesheets, fonts, media, tracking scripts, and advertisements to drastically reduce RAM usage.
*   **BeautifulSoup & aiohttp**: Lightweight HTML and API parsing for **GGSel** and **Plati.Market** to achieve rapid executions without browser overhead.

### 📊 Aggregation & Analytics
*   **AI Category & Subscription Classifier**: Simple regex engine to extract categories (e.g., *ChatGPT, Claude, Midjourney, Perplexity*) and durations (e.g., *1 week, 1 month, 1 year*).
*   **Best Deals Aggregation**: Prevents notification spam by grouping similar listings and only sending the single best (cheapest) offer in each category-duration group.
*   **📉 Price Drop Analytics (Dumping Tracker)**: Automatically compares new parsing rounds with the previous price snapshots. If a price drops for a specific product category/duration, it highlights it with a visual tag: `📉 (Dropped by X $)`.
*   **Dashboard View**: Accessible from the menu to see the current snapshot of best prices across all platforms in real-time.

### 🛡️ Smart Filters & Settings
*   **Price Filter**: Excludes listings below `min_price_usd` or above `max_price_usd`.
*   **Review Filter**: Discards listings from sellers with less than `min_reviews` count.
*   **Minus-words Filter**: Filters out garbage listings containing blacklisted substrings (e.g., `"shared"`, `"аренда"`, `"общий"`).
*   **Keywords Filter**: Defines which queries the parser should loop through.

### 🌙 Do Not Disturb (DND) & Morning Digest
*   **Silent Hours (DND)**: Allows administrators to set a quiet window (e.g., `23:00` - `08:00`) using the Europe/Berlin timezone. While active, the bot continues to parse prices in the background, but mutes real-time alerts.
*   **Morning Digest**: Automatically triggers an executive summary dashboard when DND ends, detailing the best deals collected overnight.

### 🌐 Proxy Management
*   **Built-in Proxy Checker**: Periodically validates proxy credentials (`IP:PORT:USER:PASS`) to ensure only working connections are used during parsing cycles.

### 💾 Backup & Restore
*   **In-App Backup Management**: Allows administrators to download the SQLite database (`.db`) or restore it by uploading a `.db` file directly via Telegram. Restored databases are fully validated for schema integrity and admin access before application.

---

## 📂 Architecture

```
tg-monitoring/
│
├── bot/                     # Telegram bot handlers, keyboards, and middlewares
│   ├── filters/             # Custom filters (IsAdminFilter)
│   ├── handlers/            # Handlers for admin menus, backup, proxies, settings
│   ├── keyboards/           # Inline keyboards
│   └── middlewares/         # Database injection middlewares
│
├── parsers/                 # Web scrapers and parsers
│   ├── base.py              # Abstract parser base and ParsedItem model
│   ├── funpay.py            # Playwright parser for FunPay
│   ├── playerok.py          # Playwright parser for Playerok
│   ├── ggsel.py             # aiohttp parser for GGSel
│   └── plati.py             # JSON API parser for Plati
│
├── services/                # Background orchestrators
│   ├── browser.py           # Shared BrowserManager for Playwright Chromium
│   ├── currency.py          # Real-time exchange rate updates (via Central Bank of Russia)
│   ├── digest.py            # DND Morning Digest generation & dispatch
│   ├── monitor.py           # Parsing loop orchestration & item classification
│   └── proxy_checker.py     # Asynchronous proxy validation
│
├── config.py                # Pydantic Settings configuration loading
├── database.py              # aiosqlite wrapper (WAL mode enabled)
├── main.py                  # Entrypoint, bot initialization, and scheduler setup
└── scheduler_instance.py    # Shared APScheduler instance
```

---

## ⚙️ Prerequisites & Installation

### Local Setup

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/Deksterorigin/tg-monitoring.git
    cd tg-monitoring
    ```

2.  **Create and activate virtual environment**:
    ```bash
    python -m venv .venv
    # Windows:
    .venv\Scripts\activate
    # Linux/MacOS:
    source .venv/bin/activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Install Playwright browser binaries**:
    ```bash
    playwright install chromium
    ```

5.  **Create a `.env` file** in the root directory (based on `.env.example`):
    ```env
    BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ
    FIRST_ADMIN_ID=987654321
    DATABASE_PATH=bot_database.db
    PORT=8080
    RENDER_EXTERNAL_URL=
    ```

6.  **Run the bot**:
    ```bash
    python main.py
    ```

---

## 🚀 Deployment on Render.com

This bot is fully compatible with Render.com’s free Web Service tier.

### Dockerized Deployment (Recommended)
The repository includes a `Dockerfile` that automates installation of Python dependencies, system libraries, and Playwright's Chromium binary.

1.  Create a new **Web Service** on Render.com pointing to your repository.
2.  Set the **Runtime** to `Docker`.
3.  Add the following **Environment Variables**:
    *   `BOT_TOKEN`: Your Telegram Bot API token.
    *   `FIRST_ADMIN_ID`: Your numerical Telegram user ID.
    *   `PORT`: `8080` (or another port).
    *   `RENDER_EXTERNAL_URL`: The URL of your web service (e.g., `https://your-service.onrender.com`) to enable keep-alive self-pings (pings every 14 minutes to prevent the free tier container from sleeping).
4.  Ensure your service remains running 24/7.

---

## 🔒 Security Measures

*   **Role-Based Access Control (RBAC)**: All bot handlers are tightly guarded by a central `IsAdminFilter`. Non-administrators cannot query dashboards, change settings, upload backups, or add proxies.
*   **Safe Database Queries**: All SQLite queries are parametrized using `aiosqlite` placeholders (`?`) to prevent SQL Injection attacks.
*   **Backup Integrity Checks**: The database restoration handler verifies SQLite integrity, checks for the existence of vital schemas (`admins`, `settings`, `proxies`, `seen_items`), and blocks any uploaded database that contains no administrators (which would lock out all users).
*   **Secure Dependency Setup**: Configured with `pydantic-settings` to avoid hardcoded credentials. Keys are read securely from the system's environment.

---

## 📜 License
This project is open-source and available under the [MIT License](LICENSE).
