# Используем образ с Playwright (он тяжелый, но нужный для парсера)
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

# 1. Сначала копируем только requirements.txt (для кэширования слоев Docker)
COPY requirements.txt .

# 2. Устанавливаем зависимости
# --no-cache-dir уменьшает размер образа
RUN pip install --no-cache-dir -r requirements.txt

# 3. Теперь копируем ВЕСЬ проект (включая .env, скрипты и папки)
COPY . .

# 4. Прописываем переменную окружения, чтобы Python видел модули в корне
ENV PYTHONPATH="${PYTHONPATH}:/app"

# 5. Открываем порт для Дашборда
EXPOSE 8501

# 6. Запускаем главный скрипт
CMD ["bash", "run.sh"]