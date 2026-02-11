# Используем официальный образ Playwright (в нем есть Python и браузеры)
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Ставим питоновские либы
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем браузеры Playwright (на всякий случай)
RUN playwright install chromium

# Копируем весь проект
COPY . .

# Запускаем дашборд (или ваш скрипт входа)
CMD ["streamlit", "run", "Web_Dashboard.py", "--server.port=8501", "--server.address=0.0.0.0"]