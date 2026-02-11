# Используем версию образа, которая соответствует версии библиотеки (1.58.0)
FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

# Устанавливаем рабочую директорию
WORKDIR /app

# Сначала копируем зависимости (для кэширования слоев Docker)
COPY requirements.txt .

# Устанавливаем библиотеки
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код проекта
COPY . .

# ВАЖНО: Добавляем корневую папку в пути Python, чтобы imports работали везде
ENV PYTHONPATH="${PYTHONPATH}:/app"

# Открываем порт для Streamlit
EXPOSE 8501

# Команда запуска
CMD ["bash", "run.sh"]