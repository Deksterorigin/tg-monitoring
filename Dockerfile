FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Переменные окружения для экономии памяти
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    NODE_OPTIONS="--max-old-space-size=64"

# Устанавливаем минимальные системные зависимости для Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libxml2-dev \
    libxslt1-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Принудительно устанавливаем только chromium для Playwright
# (firefox и webkit не нужны — экономия ~200 МБ)
RUN playwright install --with-deps chromium

# Финальная очистка
RUN apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Копируем все остальные файлы проекта
COPY . .

# Запуск приложения
CMD ["python", "main.py"]
