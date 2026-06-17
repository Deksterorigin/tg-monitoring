FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Принудительно устанавливаем chromium для Playwright, 
# а также системные зависимости браузера
RUN playwright install chromium

# Копируем все остальные файлы проекта
COPY . .

# Запуск приложения
CMD ["python", "main.py"]
