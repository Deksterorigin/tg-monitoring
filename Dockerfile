FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Устанавливаем рабочую директорию
WORKDIR /app

# Переменные окружения для экономии памяти
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    NODE_OPTIONS="--max-old-space-size=128"

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Принудительно устанавливаем только chromium для Playwright
# (firefox и webkit не нужны — экономия ~200 МБ)
RUN playwright install --with-deps chromium

# Очистка кэша apt для экономии места и памяти в контейнере
RUN apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Копируем все остальные файлы проекта
COPY . .

# Запуск приложения
CMD ["python", "main.py"]
